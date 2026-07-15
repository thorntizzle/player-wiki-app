from __future__ import annotations

import ast
from dataclasses import fields, replace
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import player_wiki.api as api_module
from player_wiki.character_store import CharacterStateConflictError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = "/api/v1/campaigns/linden-pass/characters/arden-march/retraining"
READ_ENDPOINT = "api.character_retraining_read"
SUBMIT_ENDPOINT = "api.character_retraining_submit"


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
        "load_character_retraining_target",
        "normalize_character_retraining_values",
        "character_retraining_availability",
        "serialize_character_retraining_response",
        "character_retraining_is_supported",
        "json_error",
        "load_json_object",
        "build_character_retraining_context_parts",
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
        source={"source_type": "markdown_import"},
        resource_templates=[{"id": "old"}, {"id": "kept"}],
        to_dict=lambda: {"character_slug": "arden-march"},
    )
    updated_definition = SimpleNamespace(
        source={"source_type": "markdown_import"},
        resource_templates=[{"id": "kept"}],
        to_dict=lambda: {"character_slug": "arden-march", "updated": True},
    )
    import_metadata = SimpleNamespace(to_dict=lambda: {"source": "import"})
    record = SimpleNamespace(
        definition=definition,
        import_metadata=import_metadata,
        state_record=SimpleNamespace(revision=7, state={"resources": {"old": 1}}),
    )
    refreshed = SimpleNamespace(
        definition=updated_definition,
        import_metadata=import_metadata,
        state_record=SimpleNamespace(revision=8, state={"resources": {"kept": 2}}),
    )
    campaign = SimpleNamespace(system="DND-5E", current_session=3)
    user = SimpleNamespace(id=41)
    character_dir = tmp_path / "characters" / "arden-march"

    def event(name, result=None):
        def invoke(*args, **kwargs):
            events.append((name, args, kwargs))
            return result

        return invoke

    def availability(campaign_slug, campaign_value, record_value, **kwargs):
        events.append(("availability", (campaign_slug, campaign_value, record_value), kwargs))
        return {
            "status": "ready",
            "message": "",
            "retraining_context": {"feature_rows": [{"id": "feature"}]},
        }

    def parts(*args, **kwargs):
        events.append(("parts", args, kwargs))
        return (
            {"feature_rows": [{"id": "feature"}]},
            ["page"],
            {"optional": object()},
            {"spell": object()},
            {"item": object()},
        )

    def apply(*args, **kwargs):
        events.append(("apply", args, kwargs))
        return updated_definition, import_metadata, {"item": 2}

    def merge(*args, **kwargs):
        events.append(("merge", args, kwargs))
        return {"resources": {"kept": 2}}

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
            "load_character_retraining_target": event(
                "target", (campaign, record, None)
            ),
            "normalize_character_retraining_values": event(
                "normalize", {"choice": "replacement"}
            ),
            "character_retraining_availability": availability,
            "serialize_character_retraining_response": event(
                "serialize", ({"ok": True}, 200)
            ),
            "character_retraining_is_supported": event("supported", True),
            "json_error": lambda message, status, *, code: (
                {"ok": False, "error": {"code": code, "message": message}},
                status,
            ),
            "load_json_object": event(
                "json", {"expected_revision": "7", "values": {"choice": "replacement"}}
            ),
            "build_character_retraining_context_parts": parts,
            "load_character_record": event("reload", refreshed),
            "finalize_character_definition_for_write": event(
                "finalize", updated_definition
            ),
            "get_current_user": event("user", user),
            "apply_native_character_retraining": apply,
            "merge_state_with_definition": merge,
            "load_campaign_character_config": config,
            "write_yaml": write,
        },
    }


def test_transport_has_exact_dependency_and_composition_shape() -> None:
    expected_order = [
        "api_campaign_scope_access_required",
        "api_login_required",
        "load_character_retraining_target",
        "normalize_character_retraining_values",
        "character_retraining_availability",
        "serialize_character_retraining_response",
        "character_retraining_is_supported",
        "json_error",
        "load_json_object",
        "build_character_retraining_context_parts",
        "load_character_record",
        "finalize_character_definition_for_write",
        "get_current_user",
        "apply_native_character_retraining",
        "merge_state_with_definition",
        "load_campaign_character_config",
        "write_yaml",
    ]
    source_root = PROJECT_ROOT / "player_wiki"
    route_path = source_root / "character_retraining_api_routes.py"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    if not route_path.exists():
        inline = {
            node.name
            for node in ast.walk(api_tree)
            if isinstance(node, ast.FunctionDef)
            and node.name in {"character_retraining_read", "character_retraining_submit"}
        }
        assert inline == {"character_retraining_read", "character_retraining_submit"}
        return

    route_module = importlib.import_module("player_wiki.character_retraining_api_routes")
    assert [
        field.name for field in fields(route_module.CharacterRetrainingApiDependencies)
    ] == expected_order
    route_tree = ast.parse(route_path.read_text(encoding="utf-8"))
    handlers = {
        node.name: node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name in {"character_retraining_read", "character_retraining_submit"}
    }
    assert set(handlers) == {"character_retraining_read", "character_retraining_submit"}
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
        and node.func.id == "CharacterRetrainingApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    direct = set(expected_order[:10])
    assert all(isinstance(by_name[name], ast.Name) for name in direct)
    assert all(isinstance(by_name[name], ast.Lambda) for name in set(by_name) - direct)


def test_route_identity_methods_and_neighbor_order(app, client) -> None:
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    read = next(rule for rule in rules if rule.endpoint == READ_ENDPOINT)
    submit = next(rule for rule in rules if rule.endpoint == SUBMIT_ENDPOINT)
    assert read.rule == "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/retraining"
    assert submit.rule == read.rule
    assert read.methods == {"GET", "HEAD", "OPTIONS"}
    assert submit.methods == {"POST", "OPTIONS"}
    assert endpoints.index("api.character_advanced_editor_update") < endpoints.index(READ_ENDPOINT)
    assert endpoints.index(READ_ENDPOINT) < endpoints.index(SUBMIT_ENDPOINT)
    assert endpoints.index(SUBMIT_ENDPOINT) < endpoints.index("api.character_level_up_read")
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


@pytest.mark.parametrize("method", ("GET", "HEAD"))
def test_read_preserves_query_availability_and_response_order(
    app, monkeypatch, tmp_path, method
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    _install_dependencies(app, READ_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(
        f"{ROUTE_PATH}?choice=first&choice=second&blank=", method=method
    ):
        response = _raw_view(app, READ_ENDPOINT)("linden-pass", "arden-march")
    assert response[1] == 200
    assert [event[0] for event in events] == [
        "target",
        "normalize",
        "availability",
        "serialize",
    ]
    normalize_payload = events[1][1][0]
    assert normalize_payload == {"choice": "first", "blank": ""}
    assert events[2][2] == {"form_values": {"choice": "replacement"}}


def test_access_error_prevents_query_readiness_and_response_work(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    fixture["dependencies"]["load_character_retraining_target"] = lambda *args: (
        events.append(("target", args, {}))
        or (fixture["campaign"], fixture["record"], ({"error": "forbidden"}, 403))
    )

    def forbidden(*args, **kwargs):
        pytest.fail("denied request performed eager Retraining work")

    fixture["dependencies"].update(
        normalize_character_retraining_values=forbidden,
        character_retraining_availability=forbidden,
        serialize_character_retraining_response=forbidden,
    )
    _install_dependencies(app, READ_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH):
        response = _raw_view(app, READ_ENDPOINT)("linden-pass", "arden-march")
    assert response[1] == 403
    assert [event[0] for event in events] == ["target"]


def test_submit_preserves_full_state_yaml_reload_and_response_order(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    original_store = app.extensions["character_state_store"]
    app.extensions["character_state_store"] = fixture["state_store"]
    try:
        _install_dependencies(
            app, SUBMIT_ENDPOINT, monkeypatch, **fixture["dependencies"]
        )
        with app.test_request_context(ROUTE_PATH, method="POST", json={}):
            response = _raw_view(app, SUBMIT_ENDPOINT)("linden-pass", "arden-march")
        assert response[1] == 200
    finally:
        app.extensions["character_state_store"] = original_store

    assert [event[0] for event in events] == [
        "target",
        "availability",
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
        "availability",
        "serialize",
    ]
    assert [event[1][0] for event in events if event[0] == "write"] == [
        "definition.yaml",
        "import.yaml",
    ]
    merge_event = next(event for event in events if event[0] == "merge")
    assert merge_event[2] == {
        "inventory_quantity_overrides": {"item": 2},
        "removed_resource_ids": {"old"},
    }
    state_event = next(event for event in events if event[0] == "state")
    assert state_event[2] == {"expected_revision": 7, "updated_by_user_id": 41}


def test_unsupported_submit_excludes_user_json_and_mutation_work(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    fixture["dependencies"]["character_retraining_is_supported"] = (
        lambda readiness: events.append(("supported", (readiness,), {})) or False
    )

    def forbidden(*args, **kwargs):
        pytest.fail("unsupported request performed eager work")

    fixture["dependencies"].update(
        get_current_user=forbidden,
        load_json_object=forbidden,
        build_character_retraining_context_parts=forbidden,
        apply_native_character_retraining=forbidden,
    )
    _install_dependencies(app, SUBMIT_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH, method="POST", json={}):
        response, status = _raw_view(app, SUBMIT_ENDPOINT)(
            "linden-pass", "arden-march"
        )
    assert status == 400
    assert response["error"]["code"] == "unsupported_campaign_system"
    assert [event[0] for event in events] == [
        "target",
        "availability",
        "supported",
    ]


@pytest.mark.parametrize(
    ("error", "status", "code"),
    (
        (CharacterStateConflictError(), 409, "state_conflict"),
        (ValueError("invalid retraining"), 400, "validation_error"),
        (TypeError("invalid type"), 400, "validation_error"),
    ),
)
def test_submit_preserves_caught_error_taxonomy(
    app, monkeypatch, tmp_path, error, status, code
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)

    def fail(*args, **kwargs):
        raise error

    fixture["dependencies"]["apply_native_character_retraining"] = fail
    _install_dependencies(app, SUBMIT_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH, method="POST", json={}):
        response, actual_status = _raw_view(app, SUBMIT_ENDPOINT)(
            "linden-pass", "arden-march"
        )
    assert actual_status == status
    assert response["error"]["code"] == code
    assert "state" not in [event[0] for event in events]


def test_post_state_yaml_fault_preserves_prior_effects(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    original_store = app.extensions["character_state_store"]
    app.extensions["character_state_store"] = fixture["state_store"]

    def write(path, payload):
        events.append(("write", (path.name, payload), {}))
        if path.name == "import.yaml":
            raise RuntimeError("import write fault")

    fixture["dependencies"]["write_yaml"] = write
    try:
        _install_dependencies(
            app, SUBMIT_ENDPOINT, monkeypatch, **fixture["dependencies"]
        )
        with app.test_request_context(ROUTE_PATH, method="POST", json={}):
            with pytest.raises(RuntimeError, match="import write fault"):
                _raw_view(app, SUBMIT_ENDPOINT)("linden-pass", "arden-march")
    finally:
        app.extensions["character_state_store"] = original_store
    names = [event[0] for event in events]
    assert names.index("state") < names.index("write")
    assert [event[1][0] for event in events if event[0] == "write"] == [
        "definition.yaml",
        "import.yaml",
    ]
    assert "reload" not in names


def test_helpers_and_cross_callers_remain_inline_and_unchanged() -> None:
    tree = ast.parse((PROJECT_ROOT / "player_wiki" / "api.py").read_text(encoding="utf-8"))
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    helper_names = {
        "normalize_character_retraining_values",
        "character_retraining_base_readiness",
        "character_retraining_catalog_parts",
        "build_character_retraining_context_parts",
        "character_retraining_availability",
        "character_retraining_is_supported",
        "serialize_character_retraining_context",
        "character_retraining_links",
        "serialize_character_retraining_response",
        "load_character_retraining_target",
    }
    assert helper_names <= set(functions)
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "character_retraining_availability"
        for node in ast.walk(functions["serialize_character_links"])
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "character_advanced_editor_is_supported"
        for node in ast.walk(functions["character_retraining_links"])
    )
