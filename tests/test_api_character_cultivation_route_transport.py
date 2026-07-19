from __future__ import annotations

import ast
from dataclasses import fields, replace
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from player_wiki.character_store import CharacterStateConflictError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = "/api/v1/campaigns/linden-pass/characters/cultivation-crane/cultivation"
READ_ENDPOINT = "api.character_cultivation_read"
ACTION_ENDPOINT = "api.character_cultivation_action"


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
        name="Cultivation Crane",
        character_slug="cultivation-crane",
        to_dict=lambda: {"character_slug": "cultivation-crane"},
    )
    updated_definition = SimpleNamespace(
        name="Cultivation Crane",
        character_slug="cultivation-crane",
        to_dict=lambda: {"character_slug": "cultivation-crane", "cultivated": True},
    )
    import_metadata = SimpleNamespace(to_dict=lambda: {"source": "managed"})
    record = SimpleNamespace(
        definition=definition,
        import_metadata=import_metadata,
        state_record=SimpleNamespace(revision=7, state={"xianxia": {"insight": 2}}),
    )
    refreshed = SimpleNamespace(
        definition=updated_definition,
        import_metadata=import_metadata,
        state_record=SimpleNamespace(revision=8, state={"xianxia": {"insight": 1}}),
    )
    campaign = SimpleNamespace(system="Xianxia", current_session=3)
    user = SimpleNamespace(id=41)
    character_dir = tmp_path / "characters" / "cultivation-crane"

    def event(name, result=None):
        def invoke(*args, **kwargs):
            events.append((name, args, kwargs))
            return result

        return invoke

    def merge(*args, **kwargs):
        events.append(("merge", args, kwargs))
        return {"xianxia": {"insight": 1}}

    class Coordinator:
        def __init__(self):
            self.expected_args = (
                record,
                updated_definition,
                import_metadata,
                {"xianxia": {"insight": 1}},
            )

        def update(self, *args, **kwargs):
            events.append(("publish", args, kwargs))

    return {
        "campaign": campaign,
        "record": record,
        "refreshed": refreshed,
        "dependencies": {
            "load_character_cultivation_target": event(
                "target", (campaign, record, None)
            ),
            "serialize_character_cultivation_response": event(
                "serialize", ({"ok": True}, 200)
            ),
            "character_cultivation_is_supported": event("supported", True),
            "json_error": lambda message, status, *, code: (
                {"ok": False, "error": {"code": code, "message": message}},
                status,
            ),
            "load_json_object": event(
                "json",
                {
                    "expected_revision": "7",
                    "action": "save_insight",
                    "values": {"insight_available": "3", "insight_spent": "1"},
                },
            ),
            "apply_xianxia_cultivation_action": event(
                "action",
                (updated_definition, "Insight counters saved.", "xianxia-cultivation-insight"),
            ),
            "load_character_record": event("reload", refreshed),
            "finalize_character_definition_for_write": event(
                "finalize", updated_definition
            ),
            "get_current_user": event("user", user),
            "build_managed_character_import_metadata": event(
                "metadata", import_metadata
            ),
            "merge_state_with_definition": merge,
            "character_publication_coordinator": Coordinator(),
        },
    }


def test_transport_has_exact_dependency_wrapper_and_helper_ownership_shape() -> None:
    expected_order = [
        "api_campaign_scope_access_required",
        "api_login_required",
        "load_character_cultivation_target",
        "serialize_character_cultivation_response",
        "character_cultivation_is_supported",
        "json_error",
        "load_json_object",
        "apply_xianxia_cultivation_action",
        "load_character_record",
        "finalize_character_definition_for_write",
        "get_current_user",
        "build_managed_character_import_metadata",
        "merge_state_with_definition",
        "character_publication_coordinator",
    ]
    source_root = PROJECT_ROOT / "player_wiki"
    route_path = source_root / "character_cultivation_api_routes.py"
    route_module = importlib.import_module(
        "player_wiki.character_cultivation_api_routes"
    )
    assert [
        field.name for field in fields(route_module.CharacterCultivationApiDependencies)
    ] == expected_order

    route_tree = ast.parse(route_path.read_text(encoding="utf-8"))
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    handler_names = {"character_cultivation_read", "character_cultivation_action"}
    helper_names = {
        "normalize_cultivation_values",
        "normalize_cultivation_int",
        "character_cultivation_is_supported",
        "build_xianxia_cultivation_parts",
        "serialize_character_cultivation_response",
        "load_character_cultivation_target",
        "apply_xianxia_cultivation_action",
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
    assert helper_names <= {
        node.name for node in ast.walk(api_tree) if isinstance(node, ast.FunctionDef)
    }
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in helper_names
        for node in ast.walk(route_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_character_cultivation_api_routes"
    )
    assignments = {
        target.id: statement.value
        for statement in registrar.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance((target := statement.targets[0]), ast.Name)
    }
    for view_name, handler_name in (
        ("character_cultivation_read_view", "character_cultivation_read"),
        ("character_cultivation_action_view", "character_cultivation_action"),
    ):
        outer = assignments[view_name]
        assert isinstance(outer, ast.Call)
        assert isinstance(outer.func, ast.Call)
        assert isinstance(outer.func.func, ast.Attribute)
        assert outer.func.func.attr == "api_campaign_scope_access_required"
        assert outer.func.args[0].value == "characters"
        inner = outer.args[0]
        assert isinstance(inner, ast.Call)
        assert isinstance(inner.func, ast.Attribute)
        assert inner.func.attr == "api_login_required"
        assert inner.args[0].id == handler_name

    dependency_call = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterCultivationApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == expected_order
    assert all(isinstance(by_name[name], ast.Name) for name in expected_order[:8])
    assert all(
        isinstance(by_name[name], ast.Lambda) for name in expected_order[8:-1]
    )
    assert isinstance(by_name["character_publication_coordinator"], ast.Subscript)


def test_module_global_dependencies_remain_forwarded_after_registration(
    app, monkeypatch
) -> None:
    import player_wiki.api as api_module

    raw_view = _raw_view(app, ACTION_ENDPOINT)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    dependencies = freevars["dependencies"].cell_contents
    marker = object()

    monkeypatch.setattr(api_module, "get_current_user", lambda: marker)
    monkeypatch.setattr(
        api_module,
        "build_managed_character_import_metadata",
        lambda *args, **kwargs: (marker, args, kwargs),
    )
    monkeypatch.setattr(
        api_module,
        "merge_state_with_definition",
        lambda *args, **kwargs: (marker, args, kwargs),
    )
    assert dependencies.get_current_user() is marker
    assert dependencies.build_managed_character_import_metadata("a", key="b")[0] is marker
    assert dependencies.merge_state_with_definition("a", key="b")[0] is marker
    assert (
        dependencies.character_publication_coordinator
        is app.extensions["character_publication_coordinator"]
    )


def test_route_identity_methods_and_neighbor_order(app, client) -> None:
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    read = next(rule for rule in rules if rule.endpoint == READ_ENDPOINT)
    action = next(rule for rule in rules if rule.endpoint == ACTION_ENDPOINT)
    expected_path = (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/cultivation"
    )
    assert read.rule == expected_path
    assert action.rule == expected_path
    assert read.methods == {"GET", "HEAD", "OPTIONS"}
    assert action.methods == {"POST", "OPTIONS"}
    assert endpoints.index("api.character_progression_repair_submit") < endpoints.index(
        READ_ENDPOINT
    )
    assert endpoints.index(READ_ENDPOINT) < endpoints.index(ACTION_ENDPOINT)
    assert endpoints.index(ACTION_ENDPOINT) < endpoints.index("api.character_controls_assignment_update")
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405


@pytest.mark.parametrize("method", ("GET", "HEAD"))
def test_read_preserves_full_target_then_response_order(
    app, monkeypatch, tmp_path, method
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    _install_dependencies(app, READ_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(
        f"{ROUTE_PATH}?ignored=first&ignored=second", method=method
    ):
        response = _raw_view(app, READ_ENDPOINT)("linden-pass", "cultivation-crane")
    assert response[1] == 200
    assert [event[0] for event in events] == ["target", "serialize"]


@pytest.mark.parametrize("endpoint", (READ_ENDPOINT, ACTION_ENDPOINT))
def test_access_error_prevents_response_or_mutation_work(
    app, monkeypatch, tmp_path, endpoint
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    fixture["dependencies"]["load_character_cultivation_target"] = (
        lambda *args: events.append(("target", args, {}))
        or (fixture["campaign"], None, ({"error": "forbidden"}, 403))
    )

    def forbidden(*args, **kwargs):
        pytest.fail("denied request performed eager Cultivation work")

    fixture["dependencies"].update(
        serialize_character_cultivation_response=forbidden,
        character_cultivation_is_supported=forbidden,
        get_current_user=forbidden,
        load_json_object=forbidden,
        apply_xianxia_cultivation_action=forbidden,
    )
    _install_dependencies(app, endpoint, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(
        ROUTE_PATH, method="POST" if endpoint == ACTION_ENDPOINT else "GET", json={}
    ):
        response = _raw_view(app, endpoint)("linden-pass", "cultivation-crane")
    assert response[1] == 403
    assert [event[0] for event in events] == ["target"]


def test_action_preserves_state_yaml_reload_response_order(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    _install_dependencies(app, ACTION_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH, method="POST", json={}):
        response = _raw_view(app, ACTION_ENDPOINT)(
            "linden-pass", "cultivation-crane"
        )
    assert response[1] == 200

    assert [event[0] for event in events] == [
        "target",
        "supported",
        "user",
        "json",
        "action",
        "finalize",
        "metadata",
        "merge",
        "publish",
        "reload",
        "serialize",
    ]
    publish_event = next(event for event in events if event[0] == "publish")
    assert publish_event[1] == fixture[
        "dependencies"
    ]["character_publication_coordinator"].expected_args
    assert publish_event[2] == {"expected_revision": 7, "updated_by_user_id": 41}
    serialize_event = events[-1]
    assert serialize_event[2] == {
        "message": "Insight counters saved.",
        "anchor": "xianxia-cultivation-insight",
    }


def test_unsupported_action_excludes_actor_json_and_mutation_work(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    fixture["dependencies"]["character_cultivation_is_supported"] = (
        lambda *args: events.append(("supported", args, {})) or False
    )

    def forbidden(*args, **kwargs):
        pytest.fail("unsupported action performed eager work")

    fixture["dependencies"].update(
        get_current_user=forbidden,
        load_json_object=forbidden,
        apply_xianxia_cultivation_action=forbidden,
    )
    _install_dependencies(app, ACTION_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH, method="POST", json={}):
        response, status = _raw_view(app, ACTION_ENDPOINT)(
            "linden-pass", "cultivation-crane"
        )
    assert status == 400
    assert response["error"]["code"] == "unsupported_campaign_system"
    assert [event[0] for event in events] == ["target", "supported"]


def test_missing_actor_prevents_json_and_mutation_work(
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
        apply_xianxia_cultivation_action=forbidden,
    )
    _install_dependencies(app, ACTION_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH, method="POST", json={}):
        response, status = _raw_view(app, ACTION_ENDPOINT)(
            "linden-pass", "cultivation-crane"
        )
    assert status == 401
    assert response["error"]["code"] == "auth_required"
    assert [event[0] for event in events] == ["target", "supported", "user"]


@pytest.mark.parametrize(
    ("error", "status", "code"),
    (
        (CharacterStateConflictError(), 409, "state_conflict"),
        (ValueError("invalid cultivation"), 400, "validation_error"),
        (TypeError("invalid type"), 400, "validation_error"),
    ),
)
def test_action_preserves_caught_error_taxonomy(
    app, monkeypatch, tmp_path, error, status, code
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)

    def fail(*args, **kwargs):
        raise error

    fixture["dependencies"]["apply_xianxia_cultivation_action"] = fail
    _install_dependencies(app, ACTION_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH, method="POST", json={}):
        response, actual_status = _raw_view(app, ACTION_ENDPOINT)(
            "linden-pass", "cultivation-crane"
        )
    assert actual_status == status
    assert response["error"]["code"] == code
    assert "publish" not in [event[0] for event in events]


def test_publication_conflict_prevents_reload(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    class ConflictCoordinator:
        def update(self, *args, **kwargs):
            events.append(("publish", args, kwargs))
            raise CharacterStateConflictError()

    fixture["dependencies"]["character_publication_coordinator"] = ConflictCoordinator()
    _install_dependencies(app, ACTION_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH, method="POST", json={}):
        response, status = _raw_view(app, ACTION_ENDPOINT)(
            "linden-pass", "cultivation-crane"
        )
    assert status == 409
    assert response["error"]["code"] == "state_conflict"
    names = [event[0] for event in events]
    assert names[-1] == "publish"
    assert "reload" not in names


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
    _install_dependencies(app, ACTION_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH, method="POST", json={}):
        with pytest.raises(RuntimeError, match="publication fault"):
            _raw_view(app, ACTION_ENDPOINT)("linden-pass", "cultivation-crane")
    names = [event[0] for event in events]
    assert names[-1] == "publish"
    assert "reload" not in names
    assert "serialize" not in names


def test_response_fault_occurs_after_state_yaml_and_reload(
    app, monkeypatch, tmp_path
) -> None:
    events: list[tuple] = []
    fixture = _fixtures(tmp_path, events)
    def fail_response(*args, **kwargs):
        events.append(("serialize", args, kwargs))
        raise RuntimeError("response fault")

    fixture["dependencies"]["serialize_character_cultivation_response"] = fail_response
    _install_dependencies(app, ACTION_ENDPOINT, monkeypatch, **fixture["dependencies"])
    with app.test_request_context(ROUTE_PATH, method="POST", json={}):
        with pytest.raises(RuntimeError, match="response fault"):
            _raw_view(app, ACTION_ENDPOINT)("linden-pass", "cultivation-crane")
    names = [event[0] for event in events]
    assert names.index("publish") < names.index("reload")
    assert names[-1] == "serialize"
