from __future__ import annotations

import ast
from dataclasses import fields, replace
import importlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY

import pytest

import player_wiki.api as api_module
from player_wiki.character_builder import CharacterBuildError
from player_wiki.character_service import CharacterStateValidationError
from tests.helpers.api_test_helpers import api_headers, issue_api_token
from tests.helpers.character_state_helpers import _write_campaign_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "api.character_create_submit"
ROUTE_PATH = "/api/v1/campaigns/linden-pass/characters/create"


def _registered_dependencies(app):
    raw_view = inspect.unwrap(app.view_functions[ENDPOINT])
    index = raw_view.__code__.co_freevars.index("dependencies")
    return raw_view.__closure__[index].cell_contents


def _install_dependencies(app, monkeypatch, **replacements) -> None:
    raw_view = inspect.unwrap(app.view_functions[ENDPOINT])
    if "dependencies" in raw_view.__code__.co_freevars:
        index = raw_view.__code__.co_freevars.index("dependencies")
        dependencies = raw_view.__closure__[index].cell_contents
        monkeypatch.setattr(
            raw_view.__closure__[index],
            "cell_contents",
            replace(dependencies, **replacements),
        )
        return

    view_module = importlib.import_module(raw_view.__module__)
    for name, value in replacements.items():
        if name in raw_view.__code__.co_freevars:
            index = raw_view.__code__.co_freevars.index(name)
            monkeypatch.setattr(raw_view.__closure__[index], "cell_contents", value)
        else:
            monkeypatch.setattr(view_module, name, value)


def _view_module(app):
    raw_view = inspect.unwrap(app.view_functions[ENDPOINT])
    return importlib.import_module(raw_view.__module__)


def _record(slug: str = "transport-hero"):
    definition = SimpleNamespace(name="Transport Hero", character_slug=slug)
    return SimpleNamespace(definition=definition)


def _success_dependencies(events: list[object], *, lane: str = "dnd5e") -> dict[str, object]:
    campaign = SimpleNamespace(slug="linden-pass", system="DND-5E")
    definition = SimpleNamespace(name="Transport Hero", character_slug="transport-hero")
    import_metadata = {"source": "transport"}
    initial_state = {"revision": 0}
    record = _record()

    def access(slug):
        events.append(("access", slug))
        return campaign, None

    def load_json():
        events.append("load_json")
        return {"values": {"name": "Transport Hero"}}

    def normalize(payload):
        events.append(("normalize", payload))
        return {"name": "Transport Hero"}

    def create_lane(system):
        events.append(("lane", system))
        return lane

    def page_records(slug, current_campaign):
        events.append(("page_records", slug, current_campaign))
        return ["page-record"]

    def dnd_context(service, slug, values, *, campaign_page_records):
        events.append(
            ("dnd_context", service, slug, values, campaign_page_records)
        )
        return {
            "class_options": ["class"],
            "species_options": ["species"],
            "background_options": ["background"],
        }

    def dnd_definition(slug, context, values):
        events.append(("dnd_definition", slug, context, values))
        return definition, import_metadata

    def finalize(slug, current_definition):
        events.append(("finalize", slug, current_definition))
        return current_definition

    def dnd_state(current_definition):
        events.append(("dnd_state", current_definition))
        return initial_state

    def xianxia_context(values, *, systems_service, campaign_slug):
        events.append(("xianxia_context", values, systems_service, campaign_slug))
        return {"lane": "xianxia"}

    def xianxia_definition(slug, context, values):
        events.append(("xianxia_definition", slug, context, values))
        return definition, import_metadata

    def xianxia_state(current_definition, values):
        events.append(("xianxia_state", current_definition, values))
        return initial_state

    def write(slug, current_definition, metadata, state):
        events.append(("write", slug, current_definition, metadata, state))
        return record

    def serialize(slug, current_record):
        events.append(("serialize", slug, current_record))
        return {"character_slug": current_record.definition.character_slug}

    def links(slug, current_campaign):
        events.append(("links", slug, current_campaign))
        return {"create_url": "/create"}

    def campaign_href(slug, suffix):
        events.append(("campaign_href", slug, suffix))
        return f"/campaigns/{slug}/{suffix}"

    return {
        "ensure_character_authoring_access": access,
        "load_json_object": load_json,
        "json_error": lambda message, status, *, code: (
            {"ok": False, "error": {"code": code, "message": message}},
            status,
        ),
        "normalize_character_authoring_values": normalize,
        "list_builder_campaign_page_records": page_records,
        "write_new_character_record": write,
        "serialize_character_record": serialize,
        "serialize_character_authoring_links": links,
        "flask_campaign_href": campaign_href,
        "finalize_character_definition_for_write": finalize,
        "native_character_create_lane": create_lane,
        "build_xianxia_character_create_context": xianxia_context,
        "build_xianxia_character_definition": xianxia_definition,
        "build_xianxia_character_initial_state": xianxia_state,
        "build_level_one_builder_context": dnd_context,
        "build_level_one_character_definition": dnd_definition,
        "build_initial_state": dnd_state,
        "native_character_create_unsupported_message": lambda system: f"unsupported {system}",
    }


def test_create_submit_untouched_dnd_call_and_response_order(app, client, monkeypatch):
    events: list[object] = []
    dependencies = _success_dependencies(events)
    _install_dependencies(app, monkeypatch, **dependencies)
    view_module = _view_module(app)
    systems_service = app.extensions["systems_service"]
    original_jsonify = view_module.jsonify
    original_url_for = view_module.url_for

    def recording_url_for(endpoint, **values):
        events.append(("url_for", endpoint, values))
        return original_url_for(endpoint, **values)

    def recording_jsonify(payload):
        events.append(("jsonify", payload))
        return original_jsonify(payload)

    monkeypatch.setattr(view_module, "url_for", recording_url_for)
    monkeypatch.setattr(view_module, "jsonify", recording_jsonify)

    response = client.post(ROUTE_PATH, json={"ignored": True})

    assert response.status_code == 200
    assert response.content_type.startswith("application/json")
    assert response.get_json() == {
        "ok": True,
        "message": "Transport Hero created.",
        "character": {"character_slug": "transport-hero"},
        "links": {
            "create_url": "/create",
            "character_url": "/campaigns/linden-pass/characters/transport-hero",
            "flask_character_url": "/campaigns/linden-pass/characters/transport-hero",
        },
    }
    campaign = events[4][2]
    assert events == [
        ("access", "linden-pass"),
        "load_json",
        ("normalize", {"values": {"name": "Transport Hero"}}),
        ("lane", "DND-5E"),
        ("page_records", "linden-pass", campaign),
        (
            "dnd_context",
            systems_service,
            "linden-pass",
            {"name": "Transport Hero"},
            ["page-record"],
        ),
        (
            "dnd_definition",
            "linden-pass",
            {
                "class_options": ["class"],
                "species_options": ["species"],
                "background_options": ["background"],
            },
            {"name": "Transport Hero"},
        ),
        ("finalize", "linden-pass", ANY),
        ("dnd_state", ANY),
        ("write", "linden-pass", ANY, {"source": "transport"}, {"revision": 0}),
        ("serialize", "linden-pass", ANY),
        ("links", "linden-pass", campaign),
        ("campaign_href", "linden-pass", "characters/transport-hero"),
        (
            "url_for",
            "character_read_view",
            {"campaign_slug": "linden-pass", "character_slug": "transport-hero"},
        ),
        ("jsonify", response.get_json()),
    ]


def test_create_submit_untouched_xianxia_excludes_dnd_work(app, client, monkeypatch):
    events: list[object] = []
    dependencies = _success_dependencies(events, lane="xianxia")

    def forbidden(*args, **kwargs):
        pytest.fail("Xianxia create must not enter DND builder work")

    dependencies.update(
        list_builder_campaign_page_records=forbidden,
        build_level_one_builder_context=forbidden,
        build_level_one_character_definition=forbidden,
        finalize_character_definition_for_write=forbidden,
        build_initial_state=forbidden,
    )
    _install_dependencies(app, monkeypatch, **dependencies)

    response = client.post(ROUTE_PATH, json={"values": {"name": "Transport Hero"}})

    assert response.status_code == 200
    names = [event[0] if isinstance(event, tuple) else event for event in events]
    assert names == [
        "access",
        "load_json",
        "normalize",
        "lane",
        "xianxia_context",
        "xianxia_definition",
        "xianxia_state",
        "write",
        "serialize",
        "links",
        "campaign_href",
    ]


def test_create_submit_denial_performs_no_json_builder_or_write_work(app, client, monkeypatch):
    campaign = SimpleNamespace(slug="linden-pass", system="DND-5E")
    calls: list[str] = []

    def access(slug):
        calls.append("access")
        return campaign, ({"denied": True}, 403)

    def forbidden(*args, **kwargs):
        pytest.fail("denied create submit performed eager work")

    replacements = _success_dependencies([])
    replacements["ensure_character_authoring_access"] = access
    for name in replacements:
        if name not in {"ensure_character_authoring_access", "json_error"}:
            replacements[name] = forbidden
    _install_dependencies(app, monkeypatch, **replacements)

    response = client.post(ROUTE_PATH, json={"values": {"name": "Denied"}})

    assert response.status_code == 403
    assert response.get_json() == {"denied": True}
    assert calls == ["access"]


@pytest.mark.parametrize(
    ("error", "status", "code"),
    (
        (CharacterBuildError("builder invalid"), 400, "validation_error"),
        (FileExistsError("duplicate character"), 409, "character_exists"),
        (CharacterStateValidationError("state invalid"), 400, "validation_error"),
        (TypeError("type invalid"), 400, "validation_error"),
        (ValueError("value invalid"), 400, "validation_error"),
    ),
)
def test_create_submit_preserves_caught_error_taxonomy(
    app, client, monkeypatch, error, status, code
):
    dependencies = _success_dependencies([])

    def fail(*args, **kwargs):
        raise error

    dependencies["write_new_character_record"] = fail
    _install_dependencies(app, monkeypatch, **dependencies)

    response = client.post(ROUTE_PATH, json={"values": {"name": "Invalid"}})

    assert response.status_code == status
    assert response.get_json() == {
        "ok": False,
        "error": {"code": code, "message": str(error)},
    }


def test_create_submit_preserves_invalid_json_taxonomy(app, client, monkeypatch):
    dependencies = _success_dependencies([])

    def fail_json():
        raise ValueError("Request body must be a JSON object.")

    dependencies["load_json_object"] = fail_json
    dependencies["normalize_character_authoring_values"] = lambda *args: pytest.fail(
        "invalid JSON reached normalization"
    )
    _install_dependencies(app, monkeypatch, **dependencies)

    response = client.post(ROUTE_PATH, data="[]", content_type="application/json")

    assert response.status_code == 400
    assert response.get_json() == {
        "ok": False,
        "error": {
            "code": "invalid_json",
            "message": "Request body must be a JSON object.",
        },
    }


def test_create_submit_preserves_unsupported_and_builder_readiness_errors(
    app, client, monkeypatch
):
    dependencies = _success_dependencies([])
    dependencies["native_character_create_lane"] = lambda system: "unsupported"
    _install_dependencies(app, monkeypatch, **dependencies)
    unsupported = client.post(ROUTE_PATH, json={})
    assert unsupported.status_code == 400
    assert unsupported.get_json()["error"] == {
        "code": "unsupported_campaign_system",
        "message": "unsupported DND-5E",
    }

    dependencies = _success_dependencies([])
    dependencies["build_level_one_builder_context"] = lambda *args, **kwargs: {
        "class_options": [],
        "species_options": ["species"],
        "background_options": ["background"],
    }
    dependencies["build_level_one_character_definition"] = lambda *args: pytest.fail(
        "unready builder reached definition work"
    )
    _install_dependencies(app, monkeypatch, **dependencies)
    unready = client.post(ROUTE_PATH, json={})
    assert unready.status_code == 400
    assert unready.get_json()["error"] == {
        "code": "validation_error",
        "message": (
            "The native character builder needs a supported base class plus enabled "
            "Systems species and backgrounds first."
        ),
    }


@pytest.mark.parametrize("fault_name", ("access", "lane", "write", "serialize", "links"))
def test_create_submit_unexpected_faults_propagate_once(
    app, client, monkeypatch, fault_name
):
    events: list[object] = []
    dependencies = _success_dependencies(events)
    target = {
        "access": "ensure_character_authoring_access",
        "lane": "native_character_create_lane",
        "write": "write_new_character_record",
        "serialize": "serialize_character_record",
        "links": "serialize_character_authoring_links",
    }[fault_name]

    def fail(*args, **kwargs):
        events.append((f"{fault_name}_fault", args))
        raise RuntimeError(f"{fault_name} fault")

    dependencies[target] = fail
    _install_dependencies(app, monkeypatch, **dependencies)

    with pytest.raises(RuntimeError, match=f"{fault_name} fault"):
        client.post(ROUTE_PATH, json={})
    assert sum(
        isinstance(event, tuple) and event[0] == f"{fault_name}_fault"
        for event in events
    ) == 1


def test_create_submit_actor_identity_access_and_method_contract(
    app, client, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    anonymous = client.post(ROUTE_PATH, json={})
    assert anonymous.status_code == 401
    assert anonymous.get_json()["error"]["code"] == "auth_required"

    party_token = issue_api_token(app, users["party"]["email"], label="p39-party")
    denied = client.post(ROUTE_PATH, headers=api_headers(party_token), json={})
    assert denied.status_code == 403
    assert denied.get_json()["error"]["code"] == "forbidden"

    rule = next(rule for rule in app.url_map.iter_rules() if rule.endpoint == ENDPOINT)
    assert rule.rule == "/api/v1/campaigns/<campaign_slug>/characters/create"
    assert rule.methods == {"POST", "OPTIONS"}
    endpoints = [registered.endpoint for registered in app.url_map.iter_rules()]
    assert endpoints.index("api.character_create_context") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index(
        "api.character_xianxia_manual_import_context"
    )
    assert client.options(ROUTE_PATH).status_code == 200
    assert client.get(ROUTE_PATH).status_code != 405
    assert client.put(ROUTE_PATH).status_code == 405
    assert client.delete(ROUTE_PATH).status_code == 405


def test_create_submit_system_contract_and_manifest_identity(app):
    def unsupported(payload: dict) -> None:
        payload["system"] = "unsupported-test-system"
        payload["systems_library"] = "unsupported-test-system"

    _write_campaign_config(app, unsupported)
    manifest = json.loads(
        (PROJECT_ROOT / "docs/contracts/route-api-role-visibility-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    entry = next(
        item
        for item in manifest["entries"]
        if item["endpoint"] == ENDPOINT and item["method"] == "POST"
    )
    assert entry["owning_domain"] == "characters"
    assert entry["authentication_policy"] == "api_identity_required"
    assert entry["access_policy"] == "character_manager_api"
    assert entry["system_restriction"] == "campaign_character_authoring_capability"
    assert entry["campaign_scope"] == "none"


def test_create_submit_source_shape_supports_baseline_and_transport():
    source_root = PROJECT_ROOT / "player_wiki"
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    route_path = source_root / "character_create_submit_api_routes.py"
    inline = [
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_create_submit"
    ]
    if not route_path.exists():
        assert len(inline) == 1
        assert len(inline[0].decorator_list) == 1
        return

    assert inline == []
    route_tree = ast.parse(route_path.read_text(encoding="utf-8"))
    handlers = [
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_create_submit"
    ]
    assert len(handlers) == 1
    assert handlers[0].decorator_list == []
    registrations = [
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1

    module = importlib.import_module("player_wiki.character_create_submit_api_routes")
    assert [
        field.name for field in fields(module.CharacterCreateSubmitApiDependencies)
    ] == [
        "ensure_character_authoring_access",
        "load_json_object",
        "json_error",
            "normalize_character_authoring_values",
            "list_builder_campaign_page_records",
            "write_new_character_record",
            "serialize_character_record",
        "serialize_character_authoring_links",
        "flask_campaign_href",
        "finalize_character_definition_for_write",
        "native_character_create_lane",
        "build_xianxia_character_create_context",
        "build_xianxia_character_definition",
        "build_xianxia_character_initial_state",
        "build_level_one_builder_context",
        "build_level_one_character_definition",
        "build_initial_state",
        "native_character_create_unsupported_message",
    ]

    registrar_call = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "register_character_create_submit_api_route"
    )
    dependency_call = next(
        keyword.value
        for keyword in registrar_call.keywords
        if keyword.arg == "dependencies"
    )
    assert isinstance(dependency_call, ast.Call)
    dependency_values = {
        keyword.arg: keyword.value for keyword in dependency_call.keywords
    }
    direct = {
        "ensure_character_authoring_access",
        "load_json_object",
        "json_error",
        "normalize_character_authoring_values",
        "list_builder_campaign_page_records",
        "serialize_character_record",
        "serialize_character_authoring_links",
        "flask_campaign_href",
    }
    assert set(dependency_values) == {
        field.name for field in fields(module.CharacterCreateSubmitApiDependencies)
    }
    for name in direct:
        assert isinstance(dependency_values[name], ast.Name)
        assert dependency_values[name].id == name
    assert isinstance(dependency_values["write_new_character_record"], ast.Lambda)
    for name in set(dependency_values) - direct:
        assert isinstance(dependency_values[name], ast.Lambda)


def test_create_submit_preserves_forwarding_and_late_bound_composition(
    app, monkeypatch
):
    raw_view = inspect.unwrap(app.view_functions[ENDPOINT])
    assert "dependencies" in raw_view.__code__.co_freevars
    index = raw_view.__code__.co_freevars.index("dependencies")
    dependencies = raw_view.__closure__[index].cell_contents

    forwarding = {
        "native_character_create_lane": ("system",),
        "build_xianxia_character_create_context": (),
        "build_xianxia_character_definition": (),
        "build_xianxia_character_initial_state": (),
        "build_level_one_builder_context": (),
        "build_level_one_character_definition": (),
        "build_initial_state": (object(),),
        "native_character_create_unsupported_message": ("system",),
    }
    for name, args in forwarding.items():
        monkeypatch.setattr(api_module, name, lambda *unused, marker=name, **kwargs: marker)
        assert getattr(dependencies, name)(*args) == name

    finalizer = dependencies.finalize_character_definition_for_write
    assert finalizer.__closure__ is not None
    bound_names = {
        cell.cell_contents.__name__
        for cell in finalizer.__closure__
        if callable(cell.cell_contents) and hasattr(cell.cell_contents, "__name__")
    }
    assert "finalize_character_definition_for_write" in bound_names


def test_actual_app_api_create_binds_native_create_kind(app, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        app.extensions["character_publication_coordinator"],
        "create",
        lambda *args, **kwargs: calls.append((args, kwargs)) or "created",
    )
    dependencies = _registered_dependencies(app)
    definition = SimpleNamespace(character_slug="api-native-composition")
    import_metadata = object()
    initial_state = {"revision": 1}

    with app.app_context():
        assert dependencies.write_new_character_record(
            "linden-pass",
            definition,
            import_metadata,
            initial_state,
        ) == "created"
    assert calls == [
        (
            (definition, import_metadata, initial_state),
            {"operation_kind": "native_create"},
        )
    ]
