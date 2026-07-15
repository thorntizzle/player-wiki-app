from __future__ import annotations

import ast
from dataclasses import fields, replace
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from player_wiki.character_builder import CharacterBuildError
from player_wiki.character_store import CharacterStateConflictError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = (
    "/api/v1/campaigns/linden-pass/characters/arden-march/progression-repair"
)
READ_ENDPOINT = "api.character_progression_repair_read"
SUBMIT_ENDPOINT = "api.character_progression_repair_submit"


def _raw_view(app, endpoint: str):
    return inspect.unwrap(app.view_functions[endpoint])


def _install_dependencies(app, endpoint: str, monkeypatch, **replacements) -> None:
    raw_view = _raw_view(app, endpoint)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    current = freevars["dependencies"].cell_contents
    monkeypatch.setattr(
        freevars["dependencies"],
        "cell_contents",
        replace(current, **replacements),
    )


def _fixtures(tmp_path: Path, events: list[tuple]):
    definition = SimpleNamespace(
        name="Arden March",
        to_dict=lambda: {"character_slug": "arden-march"},
    )
    updated_definition = SimpleNamespace(
        name="Arden March",
        to_dict=lambda: {"character_slug": "arden-march", "repaired": True},
    )
    import_metadata = SimpleNamespace(to_dict=lambda: {"source": "import"})
    record = SimpleNamespace(
        definition=definition,
        import_metadata=import_metadata,
        state_record=SimpleNamespace(revision=7, state={"vitals": {"current_hp": 8}}),
    )
    refreshed = SimpleNamespace(
        definition=updated_definition,
        import_metadata=import_metadata,
        state_record=SimpleNamespace(revision=8, state={"vitals": {"current_hp": 8}}),
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
        return {"status": "repairable", "message": "Repair imported progression."}

    def context(*args, **kwargs):
        events.append(("context", args, kwargs))
        return {"state_revision": 7, "values": {"class_ref": "wizard-phb"}}

    def apply(*args, **kwargs):
        events.append(("apply", args, kwargs))
        return updated_definition, import_metadata

    def merge(*args, **kwargs):
        events.append(("merge", args, kwargs))
        return {"vitals": {"current_hp": 8}}

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
            "load_character_progression_repair_target": event(
                "target", (campaign, record, None)
            ),
            "character_progression_repair_readiness": readiness,
            "character_progression_repair_is_supported": event("supported", True),
            "serialize_character_progression_repair_response": event(
                "serialize", ({"ok": True}, 200)
            ),
            "normalize_character_progression_repair_values": event(
                "normalize", {"class_ref": "wizard-phb"}
            ),
            "build_character_progression_repair_context_parts": context,
            "json_error": lambda message, status, *, code: (
                {"ok": False, "error": {"code": code, "message": message}},
                status,
            ),
            "load_json_object": event(
                "json",
                {
                    "expected_revision": "7",
                    "values": {"class_ref": "wizard-phb"},
                },
            ),
            "load_character_record": event("reload", refreshed),
            "finalize_character_definition_for_write": event(
                "finalize", updated_definition
            ),
            "get_current_user": event("user", user),
            "apply_imported_progression_repairs": apply,
            "merge_state_with_definition": merge,
            "load_campaign_character_config": config,
            "write_yaml": write,
        },
    }


def test_transport_has_exact_dependency_and_wrapper_composition_shape() -> None:
    expected_order = [
        "api_campaign_scope_access_required",
        "api_login_required",
        "load_character_progression_repair_target",
        "character_progression_repair_readiness",
        "character_progression_repair_is_supported",
        "serialize_character_progression_repair_response",
        "normalize_character_progression_repair_values",
        "build_character_progression_repair_context_parts",
        "json_error",
        "load_json_object",
        "load_character_record",
        "finalize_character_definition_for_write",
        "get_current_user",
        "apply_imported_progression_repairs",
        "merge_state_with_definition",
        "load_campaign_character_config",
        "write_yaml",
    ]
    source_root = PROJECT_ROOT / "player_wiki"
    route_path = source_root / "character_progression_repair_api_routes.py"
    route_module = importlib.import_module(
        "player_wiki.character_progression_repair_api_routes"
    )
    assert [
        field.name
        for field in fields(route_module.CharacterProgressionRepairApiDependencies)
    ] == expected_order

    route_tree = ast.parse(route_path.read_text(encoding="utf-8"))
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    handler_names = {
        "character_progression_repair_read",
        "character_progression_repair_submit",
    }
    handlers = {
        node.name: node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name in handler_names
    }
    assert set(handlers) == handler_names
    assert all(handler.decorator_list == [] for handler in handlers.values())
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in handler_names
        for node in ast.walk(api_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_character_progression_repair_api_routes"
    )
    assignments = {
        target.id: statement.value
        for statement in registrar.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance((target := statement.targets[0]), ast.Name)
    }
    for view_name, handler_name in (
        ("character_progression_repair_read_view", "character_progression_repair_read"),
        ("character_progression_repair_submit_view", "character_progression_repair_submit"),
    ):
        outer = assignments[view_name]
        assert isinstance(outer, ast.Call)
        assert isinstance(outer.func, ast.Call)
        assert isinstance(outer.func.func, ast.Attribute)
        assert outer.func.func.attr == "api_campaign_scope_access_required"
        assert isinstance(outer.func.args[0], ast.Constant)
        assert outer.func.args[0].value == "characters"
        inner = outer.args[0]
        assert isinstance(inner, ast.Call)
        assert isinstance(inner.func, ast.Attribute)
        assert inner.func.attr == "api_login_required"
        assert isinstance(inner.args[0], ast.Name)
        assert inner.args[0].id == handler_name

    dependency_call = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterProgressionRepairApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == expected_order
    assert all(isinstance(by_name[name], ast.Name) for name in expected_order[:10])
    assert all(isinstance(by_name[name], ast.Lambda) for name in expected_order[10:])


def test_route_identity_methods_and_neighbor_order(app, client) -> None:
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    read = next(rule for rule in rules if rule.endpoint == READ_ENDPOINT)
    submit = next(rule for rule in rules if rule.endpoint == SUBMIT_ENDPOINT)
    assert read.rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/progression-repair"
    )
    assert submit.rule == read.rule
    assert read.methods == {"GET", "HEAD", "OPTIONS"}
    assert submit.methods == {"POST", "OPTIONS"}
    assert endpoints.index("api.character_level_up_submit") < endpoints.index(READ_ENDPOINT)
    assert endpoints.index(READ_ENDPOINT) < endpoints.index(SUBMIT_ENDPOINT)
    assert endpoints.index(SUBMIT_ENDPOINT) < endpoints.index("api.character_cultivation_read")
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


@pytest.mark.parametrize("method", ("GET", "HEAD"))
def test_read_preserves_query_context_and_response_order(
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
        "readiness",
        "supported",
        "normalize",
        "context",
        "serialize",
    ]
    assert events[3][1][0] == {"choice": "first", "blank": ""}
    assert events[4][2] == {"form_values": {"class_ref": "wizard-phb"}}


def test_access_error_prevents_readiness_query_context_and_response_work(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    fixture["dependencies"]["load_character_progression_repair_target"] = (
        lambda *args: events.append(("target", args, {}))
        or (fixture["campaign"], None, ({"error": "forbidden"}, 403))
    )

    def forbidden(*args, **kwargs):
        pytest.fail("denied request performed eager Progression Repair work")

    fixture["dependencies"].update(
        character_progression_repair_readiness=forbidden,
        normalize_character_progression_repair_values=forbidden,
        build_character_progression_repair_context_parts=forbidden,
        serialize_character_progression_repair_response=forbidden,
    )
    _install_dependencies(app, READ_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH):
        response = _raw_view(app, READ_ENDPOINT)("linden-pass", "arden-march")
    assert response[1] == 403
    assert [event[0] for event in events] == ["target"]


def test_unsupported_read_serializes_without_query_or_context_work(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    fixture["dependencies"]["character_progression_repair_is_supported"] = (
        lambda readiness: events.append(("supported", (readiness,), {})) or False
    )

    def forbidden(*args, **kwargs):
        pytest.fail("unsupported read performed query or context work")

    fixture["dependencies"].update(
        normalize_character_progression_repair_values=forbidden,
        build_character_progression_repair_context_parts=forbidden,
    )
    _install_dependencies(app, READ_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH):
        response = _raw_view(app, READ_ENDPOINT)("linden-pass", "arden-march")
    assert response[1] == 200
    assert [event[0] for event in events] == [
        "target",
        "readiness",
        "supported",
        "serialize",
    ]


def test_read_build_error_becomes_unsupported_success_response(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)

    def fail(*args, **kwargs):
        events.append(("context", args, kwargs))
        raise CharacterBuildError("builder unavailable")

    fixture["dependencies"]["build_character_progression_repair_context_parts"] = fail
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
    original_store = app.extensions["character_state_store"]
    app.extensions["character_state_store"] = fixture["state_store"]
    try:
        _install_dependencies(app, SUBMIT_ENDPOINT, monkeypatch, **fixture["dependencies"])
        with app.test_request_context(ROUTE_PATH, method="POST", json={}):
            response = _raw_view(app, SUBMIT_ENDPOINT)("linden-pass", "arden-march")
        assert response[1] == 200
    finally:
        app.extensions["character_state_store"] = original_store

    assert [event[0] for event in events] == [
        "target",
        "readiness",
        "supported",
        "user",
        "json",
        "normalize",
        "context",
        "apply",
        "finalize",
        "merge",
        "state",
        "config",
        "write",
        "write",
        "reload",
        "readiness",
        "supported",
        "context",
        "serialize",
    ]
    assert [event[1][0] for event in events if event[0] == "write"] == [
        "definition.yaml",
        "import.yaml",
    ]
    state_event = next(event for event in events if event[0] == "state")
    assert state_event[2] == {"expected_revision": 7, "updated_by_user_id": 41}
    serialize_event = events[-1]
    assert serialize_event[2]["message"] == (
        "Progression repair saved, but this character still needs a few more linked "
        "details before native level-up."
    )


def test_unsupported_submit_excludes_actor_json_context_and_mutation_work(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    fixture["dependencies"]["character_progression_repair_is_supported"] = (
        lambda readiness: events.append(("supported", (readiness,), {})) or False
    )

    def forbidden(*args, **kwargs):
        pytest.fail("unsupported request performed eager work")

    fixture["dependencies"].update(
        get_current_user=forbidden,
        load_json_object=forbidden,
        build_character_progression_repair_context_parts=forbidden,
        apply_imported_progression_repairs=forbidden,
    )
    _install_dependencies(app, SUBMIT_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH, method="POST", json={}):
        response, status = _raw_view(app, SUBMIT_ENDPOINT)(
            "linden-pass", "arden-march"
        )
    assert status == 400
    assert response["error"]["code"] == "unsupported_campaign_system"
    assert [event[0] for event in events] == ["target", "readiness", "supported"]


def test_missing_actor_prevents_json_context_and_mutation_work(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    fixture["dependencies"]["get_current_user"] = (
        lambda: events.append(("user", (), {})) or None
    )

    def forbidden(*args, **kwargs):
        pytest.fail("missing actor performed payload or mutation work")

    fixture["dependencies"].update(
        load_json_object=forbidden,
        build_character_progression_repair_context_parts=forbidden,
        apply_imported_progression_repairs=forbidden,
    )
    _install_dependencies(app, SUBMIT_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH, method="POST", json={}):
        response, status = _raw_view(app, SUBMIT_ENDPOINT)(
            "linden-pass", "arden-march"
        )
    assert status == 401
    assert response["error"]["code"] == "auth_required"
    assert [event[0] for event in events] == [
        "target",
        "readiness",
        "supported",
        "user",
    ]


@pytest.mark.parametrize(
    ("error", "status", "code"),
    (
        (CharacterStateConflictError(), 409, "state_conflict"),
        (ValueError("invalid repair"), 400, "validation_error"),
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

    fixture["dependencies"]["apply_imported_progression_repairs"] = fail
    _install_dependencies(app, SUBMIT_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH, method="POST", json={}):
        response, actual_status = _raw_view(app, SUBMIT_ENDPOINT)(
            "linden-pass", "arden-march"
        )
    assert actual_status == status
    assert response["error"]["code"] == code
    assert "state" not in [event[0] for event in events]


def test_import_yaml_fault_preserves_state_and_definition_write(
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
        _install_dependencies(app, SUBMIT_ENDPOINT, monkeypatch, **fixture["dependencies"])
        with app.test_request_context(ROUTE_PATH, method="POST", json={}):
            with pytest.raises(RuntimeError, match="import write fault"):
                _raw_view(app, SUBMIT_ENDPOINT)("linden-pass", "arden-march")
    finally:
        app.extensions["character_state_store"] = original_store

    names = [event[0] for event in events]
    assert names.index("state") < names.index("config") < names.index("write")
    assert [event[1][0] for event in events if event[0] == "write"] == [
        "definition.yaml",
        "import.yaml",
    ]
    assert "reload" not in names
    assert "serialize" not in names


def test_config_fault_occurs_after_dynamic_state_replace(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    original_store = app.extensions["character_state_store"]
    app.extensions["character_state_store"] = fixture["state_store"]

    def fail_config(*args, **kwargs):
        events.append(("config", args, kwargs))
        raise RuntimeError("config fault")

    fixture["dependencies"]["load_campaign_character_config"] = fail_config
    try:
        _install_dependencies(app, SUBMIT_ENDPOINT, monkeypatch, **fixture["dependencies"])
        with app.test_request_context(ROUTE_PATH, method="POST", json={}):
            with pytest.raises(RuntimeError, match="config fault"):
                _raw_view(app, SUBMIT_ENDPOINT)("linden-pass", "arden-march")
    finally:
        app.extensions["character_state_store"] = original_store
    names = [event[0] for event in events]
    assert names.index("state") < names.index("config")
    assert "write" not in names
    assert "reload" not in names


def test_response_fault_after_writes_does_not_hide_committed_order(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    original_store = app.extensions["character_state_store"]
    app.extensions["character_state_store"] = fixture["state_store"]

    def fail_serialize(*args, **kwargs):
        events.append(("serialize", args, kwargs))
        raise RuntimeError("response fault")

    fixture["dependencies"]["serialize_character_progression_repair_response"] = (
        fail_serialize
    )
    try:
        _install_dependencies(app, SUBMIT_ENDPOINT, monkeypatch, **fixture["dependencies"])
        with app.test_request_context(ROUTE_PATH, method="POST", json={}):
            with pytest.raises(RuntimeError, match="response fault"):
                _raw_view(app, SUBMIT_ENDPOINT)("linden-pass", "arden-march")
    finally:
        app.extensions["character_state_store"] = original_store
    names = [event[0] for event in events]
    assert names.index("state") < names.index("write") < names.index("reload")
    assert [event[1][0] for event in events if event[0] == "write"] == [
        "definition.yaml",
        "import.yaml",
    ]
    assert names[-1] == "serialize"
