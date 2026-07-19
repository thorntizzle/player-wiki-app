from __future__ import annotations

import ast
from dataclasses import fields, replace
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import player_wiki.api as api_module
from player_wiki.character_builder import CharacterBuildError
from player_wiki.character_store import CharacterStateConflictError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = "/api/v1/campaigns/linden-pass/characters/arden-march/level-up"
READ_ENDPOINT = "api.character_level_up_read"
SUBMIT_ENDPOINT = "api.character_level_up_submit"


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
        "load_character_level_up_target",
        "character_level_up_readiness",
        "character_level_up_is_supported",
        "serialize_character_level_up_response",
        "normalize_character_level_up_values",
        "build_character_level_up_context_parts",
        "json_error",
        "load_json_object",
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
        name="Arden March",
        to_dict=lambda: {"character_slug": "arden-march"},
    )
    updated_definition = SimpleNamespace(
        name="Arden March",
        to_dict=lambda: {"character_slug": "arden-march", "level": 2},
    )
    import_metadata = SimpleNamespace(to_dict=lambda: {"source": "native"})
    record = SimpleNamespace(
        definition=definition,
        import_metadata=import_metadata,
        state_record=SimpleNamespace(revision=7, state={"vitals": {"current_hp": 8}}),
    )
    refreshed = SimpleNamespace(
        definition=updated_definition,
        import_metadata=import_metadata,
        state_record=SimpleNamespace(revision=8, state={"vitals": {"current_hp": 13}}),
    )
    campaign = SimpleNamespace(system="DND-5E", current_session=3)
    user = SimpleNamespace(id=41)
    character_dir = tmp_path / "characters" / "arden-march"

    def event(name, result=None):
        def invoke(*args, **kwargs):
            events.append((name, args, kwargs))
            return result

        return invoke

    def readiness(campaign_slug, campaign_value, record_value):
        events.append(("readiness", (campaign_slug, campaign_value, record_value), {}))
        return {"status": "ready", "message": ""}

    def context(*args, **kwargs):
        events.append(("context", args, kwargs))
        return {"next_level": 2, "state_revision": 7}

    def build(*args, **kwargs):
        events.append(("build", args, kwargs))
        return updated_definition, import_metadata, 5

    def merge(*args, **kwargs):
        events.append(("merge", args, kwargs))
        return {"vitals": {"current_hp": 13}}

    class Coordinator:
        def update(self, *args, **kwargs):
            events.append(("publish", args, kwargs))

    return {
        "campaign": campaign,
        "record": record,
        "refreshed": refreshed,
        "updated_definition": updated_definition,
        "import_metadata": import_metadata,
        "dependencies": {
            "load_character_level_up_target": event("target", (campaign, record, None)),
            "character_level_up_readiness": readiness,
            "character_level_up_is_supported": event("supported", True),
            "serialize_character_level_up_response": event(
                "serialize", ({"ok": True}, 200)
            ),
            "normalize_character_level_up_values": event(
                "normalize", {"choice": "second"}
            ),
            "build_character_level_up_context_parts": context,
            "json_error": lambda message, status, *, code: (
                {"ok": False, "error": {"code": code, "message": message}},
                status,
            ),
            "load_json_object": event(
                "json", {"expected_revision": "7", "values": {"choice": "second"}}
            ),
            "load_character_record": event("reload", refreshed),
            "finalize_character_definition_for_write": event(
                "finalize", updated_definition
            ),
            "get_current_user": event("user", user),
            "build_native_level_up_character_definition": build,
            "merge_state_with_definition": merge,
            "character_publication_coordinator": Coordinator(),
        },
    }


def test_transport_has_exact_dependency_and_composition_shape() -> None:
    expected_order = [
        "api_login_required",
        "load_character_level_up_target",
        "character_level_up_readiness",
        "character_level_up_is_supported",
        "serialize_character_level_up_response",
        "normalize_character_level_up_values",
        "build_character_level_up_context_parts",
        "json_error",
        "load_json_object",
        "load_character_record",
        "finalize_character_definition_for_write",
        "get_current_user",
        "build_native_level_up_character_definition",
        "merge_state_with_definition",
        "character_publication_coordinator",
    ]
    source_root = PROJECT_ROOT / "player_wiki"
    route_path = source_root / "character_level_up_api_routes.py"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    if not route_path.exists():
        inline = {
            node.name
            for node in ast.walk(api_tree)
            if isinstance(node, ast.FunctionDef)
            and node.name in {"character_level_up_read", "character_level_up_submit"}
        }
        assert inline == {"character_level_up_read", "character_level_up_submit"}
        return

    route_module = importlib.import_module("player_wiki.character_level_up_api_routes")
    assert [field.name for field in fields(route_module.CharacterLevelUpApiDependencies)] == expected_order
    route_tree = ast.parse(route_path.read_text(encoding="utf-8"))
    handlers = {
        node.name: node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name in {"character_level_up_read", "character_level_up_submit"}
    }
    assert set(handlers) == {"character_level_up_read", "character_level_up_submit"}
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
        and node.func.id == "CharacterLevelUpApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    direct = set(expected_order[:9])
    assert all(isinstance(by_name[name], ast.Name) for name in direct)
    assert all(
        isinstance(by_name[name], ast.Lambda)
        for name in set(by_name) - direct - {"character_publication_coordinator"}
    )
    assert isinstance(by_name["character_publication_coordinator"], ast.Subscript)


def test_route_identity_methods_and_neighbor_order(app, client) -> None:
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    read = next(rule for rule in rules if rule.endpoint == READ_ENDPOINT)
    submit = next(rule for rule in rules if rule.endpoint == SUBMIT_ENDPOINT)
    assert read.rule == "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/level-up"
    assert submit.rule == read.rule
    assert read.methods == {"GET", "HEAD", "OPTIONS"}
    assert submit.methods == {"POST", "OPTIONS"}
    assert endpoints.index("api.character_retraining_submit") < endpoints.index(READ_ENDPOINT)
    assert endpoints.index(READ_ENDPOINT) < endpoints.index(SUBMIT_ENDPOINT)
    assert endpoints.index(SUBMIT_ENDPOINT) < endpoints.index("api.character_progression_repair_read")
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


@pytest.mark.parametrize("method", ("GET", "HEAD"))
def test_read_preserves_query_context_and_response_order(app, monkeypatch, tmp_path, method) -> None:
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
        "readiness",
        "supported",
        "normalize",
        "context",
        "serialize",
    ]
    assert events[3][1][0] == {"choice": "first", "blank": ""}
    assert events[4][2] == {"form_values": {"choice": "second"}}


def test_access_error_prevents_readiness_query_context_and_response_work(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    fixture["dependencies"]["load_character_level_up_target"] = lambda *args: (
        events.append(("target", args, {}))
        or (fixture["campaign"], None, ({"error": "forbidden"}, 403))
    )

    def forbidden(*args, **kwargs):
        pytest.fail("denied request performed eager Level Up work")

    fixture["dependencies"].update(
        character_level_up_readiness=forbidden,
        normalize_character_level_up_values=forbidden,
        build_character_level_up_context_parts=forbidden,
        serialize_character_level_up_response=forbidden,
    )
    _install_dependencies(app, READ_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH):
        response = _raw_view(app, READ_ENDPOINT)("linden-pass", "arden-march")
    assert response[1] == 403
    assert [event[0] for event in events] == ["target"]


def test_read_build_error_becomes_unsupported_success_response(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)

    def fail(*args, **kwargs):
        events.append(("context", args, kwargs))
        raise CharacterBuildError("builder unavailable")

    fixture["dependencies"]["build_character_level_up_context_parts"] = fail
    _install_dependencies(app, READ_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH):
        response = _raw_view(app, READ_ENDPOINT)("linden-pass", "arden-march")
    assert response[1] == 200
    serialize_event = events[-1]
    assert serialize_event[0] == "serialize"
    assert serialize_event[2]["readiness"] == {
        "status": "unsupported",
        "message": "builder unavailable",
    }


def test_submit_preserves_state_yaml_reload_readiness_context_response_order(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    _install_dependencies(app, SUBMIT_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH, method="POST", json={}):
        response = _raw_view(app, SUBMIT_ENDPOINT)("linden-pass", "arden-march")
    assert response[1] == 200

    assert [event[0] for event in events] == [
        "target",
        "readiness",
        "supported",
        "user",
        "json",
        "normalize",
        "context",
        "build",
        "finalize",
        "merge",
        "publish",
        "reload",
        "readiness",
        "supported",
        "context",
        "serialize",
    ]
    merge_event = next(event for event in events if event[0] == "merge")
    assert merge_event[2] == {"hp_delta": 5}
    publish_event = next(event for event in events if event[0] == "publish")
    assert publish_event[1] == (
        fixture["record"],
        fixture["updated_definition"],
        fixture["import_metadata"],
        {"vitals": {"current_hp": 13}},
    )
    assert publish_event[2] == {"expected_revision": 7, "updated_by_user_id": 41}
    serialize_event = events[-1]
    assert serialize_event[2]["message"] == "Arden March advanced to level 2."


def test_unsupported_submit_excludes_user_json_context_and_mutation_work(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    fixture["dependencies"]["character_level_up_is_supported"] = (
        lambda readiness: events.append(("supported", (readiness,), {})) or False
    )

    def forbidden(*args, **kwargs):
        pytest.fail("unsupported request performed eager work")

    fixture["dependencies"].update(
        get_current_user=forbidden,
        load_json_object=forbidden,
        build_character_level_up_context_parts=forbidden,
        build_native_level_up_character_definition=forbidden,
    )
    _install_dependencies(app, SUBMIT_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH, method="POST", json={}):
        response, status = _raw_view(app, SUBMIT_ENDPOINT)("linden-pass", "arden-march")
    assert status == 400
    assert response["error"]["code"] == "unsupported_campaign_system"
    assert [event[0] for event in events] == ["target", "readiness", "supported"]


@pytest.mark.parametrize(
    ("error", "status", "code"),
    (
        (CharacterStateConflictError(), 409, "state_conflict"),
        (ValueError("invalid level up"), 400, "validation_error"),
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

    fixture["dependencies"]["build_native_level_up_character_definition"] = fail
    _install_dependencies(app, SUBMIT_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH, method="POST", json={}):
        response, actual_status = _raw_view(app, SUBMIT_ENDPOINT)(
            "linden-pass", "arden-march"
        )
    assert actual_status == status
    assert response["error"]["code"] == code
    assert "publish" not in [event[0] for event in events]


def test_publication_fault_prevents_reload_and_response(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    class FaultCoordinator:
        def update(self, *args, **kwargs):
            events.append(("publish", args, kwargs))
            raise RuntimeError("publication fault")

    fixture["dependencies"]["character_publication_coordinator"] = FaultCoordinator()
    _install_dependencies(app, SUBMIT_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH, method="POST", json={}):
        with pytest.raises(RuntimeError, match="publication fault"):
            _raw_view(app, SUBMIT_ENDPOINT)("linden-pass", "arden-march")

    names = [event[0] for event in events]
    assert names[-1] == "publish"
    assert "reload" not in names
    assert "serialize" not in names
