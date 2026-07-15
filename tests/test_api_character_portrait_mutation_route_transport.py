from __future__ import annotations

import ast
import base64
from dataclasses import fields
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Blueprint, Flask, jsonify

import player_wiki.api as api_module
import player_wiki.character_portrait_mutation_api_routes as portrait_api_routes
from tests.helpers.api_test_helpers import api_headers, issue_api_token


ROUTE_PATH = "/api/v1/campaigns/linden-pass/characters/arden-march/portrait"
UPSERT_ENDPOINT = "api.character_portrait_upsert"
DELETE_ENDPOINT = "api.character_portrait_delete"
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _revision(app) -> int:
    with app.app_context():
        record = app.extensions["character_repository"].get_visible_character(
            "linden-pass", "arden-march"
        )
        assert record is not None
        return record.state_record.revision


def _payload(revision: int, *, filename: str = "portrait.png") -> dict[str, object]:
    return {
        "expected_revision": revision,
        "portrait_file": {
            "filename": filename,
            "media_type": "image/png",
            "data_base64": base64.b64encode(TINY_PNG).decode("ascii"),
        },
        "alt_text": "Arden portrait",
        "caption": "At the harbor.",
    }


def test_portrait_api_transport_has_exact_dependency_and_composition_shape() -> None:
    assert [
        field.name
        for field in fields(
            portrait_api_routes.CharacterPortraitMutationApiDependencies
        )
    ] == [
        "load_character_record",
        "json_error",
        "load_json_object",
        "validate_character_portrait_payload",
        "serialize_updated_character",
        "finalize_character_definition_for_write",
        "has_session_mode_access",
        "get_current_user",
        "get_repository",
        "build_character_portrait_asset_ref",
        "update_character_portrait_profile",
        "build_managed_character_import_metadata",
        "merge_state_with_definition",
        "load_campaign_character_config",
        "write_yaml",
        "write_campaign_asset_file",
        "delete_campaign_asset_file",
    ]

    source_root = Path(api_module.__file__).resolve().parent
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    route_tree = ast.parse(
        (source_root / "character_portrait_mutation_api_routes.py").read_text(
            encoding="utf-8"
        )
    )
    handlers = {
        node.name: node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name in {"character_portrait_upsert", "character_portrait_delete"}
    }
    assert set(handlers) == {"character_portrait_upsert", "character_portrait_delete"}
    assert all(handler.decorator_list == [] for handler in handlers.values())
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

    registrar_call = next(
        node
        for node in ast.walk(api_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "register_character_portrait_mutation_api_routes"
    )
    dependencies_call = next(
        keyword.value
        for keyword in registrar_call.keywords
        if keyword.arg == "dependencies"
    )
    assert isinstance(dependencies_call, ast.Call)
    keyword_values = {
        keyword.arg: keyword.value for keyword in dependencies_call.keywords
    }
    for name in (
        "load_character_record",
        "json_error",
        "load_json_object",
        "validate_character_portrait_payload",
        "serialize_updated_character",
    ):
        assert isinstance(keyword_values[name], ast.Name)
        assert keyword_values[name].id == name
    for name in set(keyword_values) - {
        "load_character_record",
        "json_error",
        "load_json_object",
        "validate_character_portrait_payload",
        "serialize_updated_character",
    }:
        assert isinstance(keyword_values[name], ast.Lambda)


def test_portrait_api_route_identity_methods_order_and_late_bound_finalizer(
    app, client, users, set_campaign_visibility
) -> None:
    set_campaign_visibility("linden-pass", characters="players")
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    upsert = next(rule for rule in rules if rule.endpoint == UPSERT_ENDPOINT)
    delete = next(rule for rule in rules if rule.endpoint == DELETE_ENDPOINT)

    assert upsert.methods == {"PUT", "OPTIONS"}
    assert delete.methods == {"DELETE", "OPTIONS"}
    assert inspect.unwrap(app.view_functions[UPSERT_ENDPOINT]).__name__ == "character_portrait_upsert"
    assert inspect.unwrap(app.view_functions[DELETE_ENDPOINT]).__name__ == "character_portrait_delete"
    assert endpoints.index("api.character_controls_delete") < endpoints.index(UPSERT_ENDPOINT)
    assert endpoints.index(UPSERT_ENDPOINT) < endpoints.index(DELETE_ENDPOINT)
    assert endpoints.index(DELETE_ENDPOINT) < endpoints.index("api.character_rest_preview")

    assert client.options(ROUTE_PATH).status_code == 200
    assert client.get(ROUTE_PATH).status_code == 405
    assert client.patch(ROUTE_PATH).status_code == 405
    assert client.post(ROUTE_PATH).status_code == 405

    token = issue_api_token(app, users["dm"]["email"], label="p37-late-finalizer")
    response = client.put(
        ROUTE_PATH,
        headers=api_headers(token),
        json=_payload(_revision(app)),
    )
    assert response.status_code == 200
    assert response.get_json()["character"]["portrait"]["asset_ref"].endswith(
        "/portrait.webp"
    )


def test_portrait_api_preserves_no_login_decorator_and_access_order(
    app, client, users, set_campaign_visibility, monkeypatch
) -> None:
    set_campaign_visibility("linden-pass", characters="players")
    assert client.put(ROUTE_PATH, json=_payload(_revision(app))).status_code == 403

    party_token = issue_api_token(app, users["party"]["email"], label="p37-denied")
    before_revision = _revision(app)
    denied = client.put(
        ROUTE_PATH,
        headers=api_headers(party_token),
        json=_payload(before_revision),
    )
    assert denied.status_code == 403
    assert denied.get_json()["error"] == {
        "code": "forbidden",
        "message": "You do not have permission to update this character from this view.",
    }
    assert _revision(app) == before_revision

    state_store = app.extensions["character_state_store"]
    monkeypatch.setattr(
        state_store,
        "get_state",
        lambda *args, **kwargs: pytest.fail("malicious slug reached state lookup"),
    )
    monkeypatch.setattr(
        state_store,
        "replace_state",
        lambda *args, **kwargs: pytest.fail("malicious slug reached state write"),
    )
    malicious = client.put(
        "/api/v1/campaigns/linden-pass/characters/%5C..%5Coutside/portrait",
        headers=api_headers(party_token),
        json={"unexpected": "payload"},
    )
    assert malicious.status_code == 404


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({}, "validation_error"),
        ({"expected_revision": "not-an-int"}, "validation_error"),
        ([], "validation_error"),
    ],
)
def test_portrait_api_preserves_json_revision_and_validation_taxonomy(
    app, client, users, set_campaign_visibility, payload, code
) -> None:
    set_campaign_visibility("linden-pass", characters="players")
    token = issue_api_token(app, users["dm"]["email"], label=f"p37-json-{payload!r}")
    response = client.put(ROUTE_PATH, headers=api_headers(token), json=payload)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == code


def test_portrait_api_empty_delete_short_circuits_body_and_state(
    app, client, users, set_campaign_visibility, monkeypatch
) -> None:
    set_campaign_visibility("linden-pass", characters="players")
    token = issue_api_token(app, users["dm"]["email"], label="p37-empty-delete")
    state_store = app.extensions["character_state_store"]
    monkeypatch.setattr(
        state_store,
        "replace_state",
        lambda *args, **kwargs: pytest.fail("empty delete reached state write"),
    )
    response = client.delete(
        ROUTE_PATH,
        headers={**api_headers(token), "Content-Type": "application/json"},
        data="not-json",
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "validation_error",
        "message": "That character does not currently have a portrait.",
    }


def test_portrait_api_state_write_remains_committed_when_later_yaml_faults(
    app, client, users, set_campaign_visibility, monkeypatch
) -> None:
    set_campaign_visibility("linden-pass", characters="players")
    token = issue_api_token(app, users["dm"]["email"], label="p37-partial-commit")
    starting_revision = _revision(app)
    calls = []

    def fail_yaml(*args, **kwargs):
        calls.append(args[0].name)
        raise RuntimeError("yaml fault")

    monkeypatch.setattr(api_module, "write_yaml", fail_yaml)
    with pytest.raises(RuntimeError, match="yaml fault"):
        client.put(
            ROUTE_PATH,
            headers=api_headers(token),
            json=_payload(starting_revision),
        )
    assert calls == ["definition.yaml"]
    assert _revision(app) == starting_revision + 1


def _fault_app(method: str, fault_stage: str):
    events: list[str] = []

    def event(name: str, value=None):
        events.append(name)
        if name == fault_stage:
            raise RuntimeError(f"{name} fault")
        return value

    definition = SimpleNamespace(
        profile={"portrait_asset_ref": "characters/arden-march/old.gif"},
        character_slug="arden-march",
        to_dict=lambda: {"character_slug": "arden-march"},
    )
    import_metadata = SimpleNamespace(to_dict=lambda: {"managed": True})
    record = SimpleNamespace(
        definition=definition,
        import_metadata=import_metadata,
        state_record=SimpleNamespace(state={"vitals": {}}),
    )
    campaign = SimpleNamespace(slug="linden-pass")
    repository = SimpleNamespace(
        get_campaign=lambda campaign_slug: event("campaign", campaign)
    )
    state_store = SimpleNamespace(
        replace_state=lambda *args, **kwargs: event("state")
    )

    dependencies = portrait_api_routes.CharacterPortraitMutationApiDependencies(
        load_character_record=lambda *args: event("load", record),
        json_error=lambda message, status, **kwargs: (
            jsonify({"error": {"code": kwargs["code"], "message": message}}),
            status,
        ),
        load_json_object=lambda: event("json", {"expected_revision": 7}),
        validate_character_portrait_payload=lambda payload: event(
            "validate",
            {
                "filename": "portrait.webp",
                "data_blob": b"portrait",
                "alt_text": "Arden",
                "caption": "Harbor",
            },
        ),
        serialize_updated_character=lambda *args: event(
            "serialize", jsonify({"ok": True})
        ),
        finalize_character_definition_for_write=lambda *args: event(
            "finalize", definition
        ),
        has_session_mode_access=lambda *args: event("access", True),
        get_current_user=lambda: event("user", SimpleNamespace(id=42)),
        get_repository=lambda: repository,
        build_character_portrait_asset_ref=lambda *args: event(
            "asset_ref", "characters/arden-march/portrait.webp"
        ),
        update_character_portrait_profile=lambda *args, **kwargs: event(
            "profile", definition
        ),
        build_managed_character_import_metadata=lambda *args: event(
            "import_metadata", import_metadata
        ),
        merge_state_with_definition=lambda *args: event("merge", {"vitals": {}}),
        load_campaign_character_config=lambda *args: event(
            "config", SimpleNamespace(characters_dir=Path("characters"))
        ),
        write_yaml=lambda path, payload: event(f"yaml:{path.name}"),
        write_campaign_asset_file=lambda *args, **kwargs: event("asset_write"),
        delete_campaign_asset_file=lambda *args, **kwargs: event("asset_delete"),
    )
    api = Blueprint("api", __name__, url_prefix="/api/v1")
    portrait_api_routes.register_character_portrait_mutation_api_routes(
        api, dependencies=dependencies
    )
    test_app = Flask(__name__)
    test_app.config.update(TESTING=True, CAMPAIGNS_DIR=Path("campaigns"))
    test_app.extensions["character_state_store"] = state_store
    test_app.register_blueprint(api)
    return test_app, events


@pytest.mark.parametrize(
    "fault_stage",
    [
        "state",
        "config",
        "yaml:definition.yaml",
        "yaml:import.yaml",
        "asset_write",
        "asset_delete",
        "serialize",
    ],
)
def test_portrait_api_upsert_preserves_each_partial_commit_fault_boundary(
    fault_stage
) -> None:
    app, events = _fault_app("PUT", fault_stage)
    expected = [
        "load",
        "access",
        "user",
        "campaign",
        "json",
        "validate",
        "asset_ref",
        "profile",
        "finalize",
        "import_metadata",
        "merge",
        "state",
        "config",
        "yaml:definition.yaml",
        "yaml:import.yaml",
        "asset_write",
        "asset_delete",
        "serialize",
    ]
    with app.test_client() as client, pytest.raises(
        RuntimeError, match=f"{fault_stage} fault"
    ):
        client.put(
            "/api/v1/campaigns/linden-pass/characters/arden-march/portrait",
            json={"expected_revision": 7},
        )
    assert events == expected[: expected.index(fault_stage) + 1]


@pytest.mark.parametrize(
    "fault_stage",
    [
        "state",
        "config",
        "yaml:definition.yaml",
        "yaml:import.yaml",
        "asset_delete",
        "serialize",
    ],
)
def test_portrait_api_delete_preserves_each_partial_commit_fault_boundary(
    fault_stage,
) -> None:
    app, events = _fault_app("DELETE", fault_stage)
    expected = [
        "load",
        "access",
        "user",
        "campaign",
        "json",
        "profile",
        "finalize",
        "import_metadata",
        "merge",
        "state",
        "config",
        "yaml:definition.yaml",
        "yaml:import.yaml",
        "asset_delete",
        "serialize",
    ]
    with app.test_client() as client, pytest.raises(
        RuntimeError, match=f"{fault_stage} fault"
    ):
        client.delete(
            "/api/v1/campaigns/linden-pass/characters/arden-march/portrait",
            json={"expected_revision": 7},
        )
    assert events == expected[: expected.index(fault_stage) + 1]
