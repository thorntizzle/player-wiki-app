from __future__ import annotations

import ast
from dataclasses import fields, replace
import importlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import player_wiki.api as api_module
from player_wiki.character_path_safety import CharacterPathSafetyError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTEXT_ENDPOINT = "api.character_xianxia_manual_import_context"
SUBMIT_ENDPOINT = "api.character_xianxia_manual_import_submit"
ROUTE_PATH = "/api/v1/campaigns/linden-pass/characters/import/xianxia-manual"


def _registered_dependencies(app):
    raw_view = inspect.unwrap(app.view_functions[SUBMIT_ENDPOINT])
    index = raw_view.__code__.co_freevars.index("dependencies")
    return raw_view.__closure__[index].cell_contents


def _install_dependencies(app, monkeypatch, endpoint: str, **replacements) -> None:
    raw_view = inspect.unwrap(app.view_functions[endpoint])
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
        elif hasattr(view_module, name):
            monkeypatch.setattr(view_module, name, value)


def _view_module(app, endpoint: str):
    raw_view = inspect.unwrap(app.view_functions[endpoint])
    return importlib.import_module(raw_view.__module__)


def _record(slug: str = "imported-lotus"):
    definition = SimpleNamespace(name="Imported Lotus", character_slug=slug)
    return SimpleNamespace(definition=definition)


def test_actual_app_api_manual_import_binds_manual_import_kind(
    app,
    monkeypatch,
) -> None:
    calls = []
    monkeypatch.setattr(
        app.extensions["character_publication_coordinator"],
        "create",
        lambda *args, **kwargs: calls.append((args, kwargs)) or "imported",
    )
    dependencies = _registered_dependencies(app)
    definition = SimpleNamespace(character_slug="api-manual-composition")
    import_metadata = object()
    initial_state = {"revision": 1}

    with app.app_context():
        assert dependencies.write_new_character_record(
            "linden-pass",
            definition,
            import_metadata,
            initial_state,
        ) == "imported"
    assert calls == [
        (
            (definition, import_metadata, initial_state),
            {"operation_kind": "manual_import"},
        )
    ]


def _dependencies(events: list[object]) -> dict[str, object]:
    campaign = SimpleNamespace(slug="linden-pass", system="Xianxia")
    definition = SimpleNamespace(name="Imported Lotus", character_slug="imported-lotus")
    import_metadata = {"source_path": "importer://xianxia-manual"}
    initial_state = {"revision": 0}

    def access(slug):
        events.append(("access", slug))
        return campaign, None

    def lane(system):
        events.append(("lane", system))
        return "xianxia"

    def normalize(payload):
        events.append(("normalize", payload))
        raw = payload.get("values", payload)
        return {str(key): str(value or "") for key, value in raw.items()}

    def serialize_campaign(current_campaign):
        events.append(("campaign", current_campaign))
        return {"slug": current_campaign.slug}

    def links(slug, current_campaign):
        events.append(("links", slug, current_campaign))
        return {"import_url": "/import"}

    def json_safe(value):
        events.append(("json_safe", value))
        return value

    def context(*, systems_service, campaign_slug, values, preview=None, json_safe):
        events.append(
            (
                "context",
                systems_service,
                campaign_slug,
                values,
                preview,
                json_safe,
            )
        )
        result = {"martial_art_options": ["art-option"], "values": values}
        if preview is not None:
            result["preview"] = preview
        return result

    def load_json():
        events.append("load_json")
        return {"values": {"name": "Imported Lotus"}}

    def payload(values):
        events.append(("payload", values))
        return {"name": values["name"]}

    def build(current_payload, *, campaign_slug, martial_art_options):
        events.append(
            ("build", current_payload, campaign_slug, martial_art_options)
        )
        return definition, import_metadata, initial_state

    def validate(slug):
        events.append(("validate", slug))

    def preview(current_definition, state):
        events.append(("preview", current_definition, state))
        return {"name": current_definition.name}

    def write(slug, current_definition, metadata, state):
        events.append(("write", slug, current_definition, metadata, state))
        return _record()

    def serialize(slug, record):
        events.append(("serialize", slug, record))
        return {"character_slug": record.definition.character_slug}

    def campaign_href(slug, suffix):
        events.append(("campaign_href", slug, suffix))
        return f"/campaigns/{slug}/{suffix}"

    return {
        "ensure_character_authoring_access": access,
        "json_error": lambda message, status, *, code: (
            {"ok": False, "error": {"code": code, "message": message}},
            status,
        ),
        "normalize_character_authoring_values": normalize,
        "serialize_campaign": serialize_campaign,
        "serialize_character_authoring_links": links,
        "make_json_safe": json_safe,
        "load_json_object": load_json,
        "write_new_character_record": write,
        "serialize_character_record": serialize,
        "flask_campaign_href": campaign_href,
        "native_character_create_lane": lane,
        "build_xianxia_manual_import_context": context,
        "build_xianxia_manual_import_payload": payload,
        "build_xianxia_manual_import_character": build,
        "validate_character_slug": validate,
        "build_xianxia_manual_import_preview": preview,
    }


def _install_all(app, monkeypatch, events: list[object]) -> dict[str, object]:
    dependencies = _dependencies(events)
    _install_dependencies(app, monkeypatch, CONTEXT_ENDPOINT, **dependencies)
    _install_dependencies(app, monkeypatch, SUBMIT_ENDPOINT, **dependencies)
    return dependencies


def test_manual_import_context_preserves_query_and_response_order(
    app, client, monkeypatch
):
    events: list[object] = []
    dependencies = _install_all(app, monkeypatch, events)
    view_module = _view_module(app, CONTEXT_ENDPOINT)
    original_jsonify = view_module.jsonify

    def recording_jsonify(payload):
        events.append(("jsonify", payload))
        return original_jsonify(payload)

    monkeypatch.setattr(view_module, "jsonify", recording_jsonify)
    response = client.get(f"{ROUTE_PATH}?blank=&repeat=first&repeat=second")

    assert response.status_code == 200
    expected = {
        "ok": True,
        "campaign": {"slug": "linden-pass"},
        "lane": "xianxia",
        "links": {"import_url": "/import"},
        "import_context": {
            "martial_art_options": ["art-option"],
            "values": {"blank": "", "repeat": "first"},
        },
    }
    assert response.get_json() == expected
    campaign = events[3][1]
    assert events == [
        ("access", "linden-pass"),
        ("lane", "Xianxia"),
        ("normalize", {"values": {"blank": "", "repeat": "first"}}),
        ("campaign", campaign),
        ("links", "linden-pass", campaign),
        (
            "context",
            app.extensions["systems_service"],
            "linden-pass",
            {"blank": "", "repeat": "first"},
            None,
            dependencies["make_json_safe"],
        ),
        ("jsonify", expected),
    ]


def test_manual_import_context_head_invokes_and_options_does_not(
    app, client, monkeypatch
):
    events: list[object] = []
    _install_all(app, monkeypatch, events)
    assert client.head(ROUTE_PATH).status_code == 200
    assert events
    events.clear()
    assert client.options(ROUTE_PATH).status_code == 200
    assert events == []


@pytest.mark.parametrize("endpoint,method", ((CONTEXT_ENDPOINT, "get"), (SUBMIT_ENDPOINT, "post")))
def test_manual_import_denial_has_no_eager_work(
    app, client, monkeypatch, endpoint, method
):
    events: list[str] = []

    def access(slug):
        events.append("access")
        return SimpleNamespace(system="Xianxia"), ({"denied": True}, 403)

    replacements = _dependencies([])
    replacements["ensure_character_authoring_access"] = access

    def forbidden(*args, **kwargs):
        pytest.fail("denied request performed eager work")

    for name in replacements:
        if name not in {"ensure_character_authoring_access", "json_error"}:
            replacements[name] = forbidden
    _install_dependencies(app, monkeypatch, endpoint, **replacements)

    response = getattr(client, method)(ROUTE_PATH, json={} if method == "post" else None)
    assert response.status_code == 403
    assert response.get_json() == {"denied": True}
    assert events == ["access"]


@pytest.mark.parametrize("endpoint,method", ((CONTEXT_ENDPOINT, "get"), (SUBMIT_ENDPOINT, "post")))
def test_manual_import_xianxia_lane_check_precedes_route_work(
    app, client, monkeypatch, endpoint, method
):
    replacements = _dependencies([])
    replacements["native_character_create_lane"] = lambda system: "dnd5e"

    def forbidden(*args, **kwargs):
        pytest.fail("unsupported route entered import work")

    for name in (
        "normalize_character_authoring_values",
        "serialize_campaign",
        "serialize_character_authoring_links",
        "make_json_safe",
        "load_json_object",
        "build_xianxia_manual_import_context",
        "build_xianxia_manual_import_payload",
        "build_xianxia_manual_import_character",
        "validate_character_slug",
        "build_xianxia_manual_import_preview",
        "write_new_character_record",
        "serialize_character_record",
        "flask_campaign_href",
    ):
        replacements[name] = forbidden
    _install_dependencies(app, monkeypatch, endpoint, **replacements)

    response = getattr(client, method)(ROUTE_PATH, json={} if method == "post" else None)
    assert response.status_code == 400
    assert response.get_json() == {
        "ok": False,
        "error": {
            "code": "unsupported_campaign_system",
            "message": "Manual Xianxia character import is only available for Xianxia campaigns.",
        },
    }


def test_manual_import_submit_preview_builds_context_twice_and_does_not_write(
    app, client, monkeypatch
):
    events: list[object] = []
    dependencies = _install_all(app, monkeypatch, events)
    dependencies["write_new_character_record"] = lambda *args: pytest.fail(
        "preview persisted a character"
    )
    _install_dependencies(app, monkeypatch, SUBMIT_ENDPOINT, **dependencies)

    response = client.post(ROUTE_PATH, json={"values": {"name": "Imported Lotus"}})
    assert response.status_code == 200
    assert response.get_json()["message"] == (
        "Review the imported sheet summary, then confirm to create the character."
    )
    names = [event[0] if isinstance(event, tuple) else event for event in events]
    assert names == [
        "access",
        "lane",
        "load_json",
        "normalize",
        "context",
        "payload",
        "build",
        "validate",
        "preview",
        "campaign",
        "links",
        "context",
    ]
    context_events = [event for event in events if isinstance(event, tuple) and event[0] == "context"]
    assert context_events[0][4] is None
    assert context_events[1][4] == {"name": "Imported Lotus"}


def test_manual_import_submit_confirm_preserves_write_and_response_order(
    app, client, monkeypatch
):
    events: list[object] = []
    dependencies = _dependencies(events)
    dependencies["load_json_object"] = lambda: (
        events.append("load_json")
        or {"values": {"name": "Imported Lotus"}, "confirm_import": True}
    )
    _install_dependencies(app, monkeypatch, SUBMIT_ENDPOINT, **dependencies)
    view_module = _view_module(app, SUBMIT_ENDPOINT)
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
    assert response.get_json()["message"] == "Imported Lotus imported."
    names = [event[0] if isinstance(event, tuple) else event for event in events]
    assert names == [
        "access",
        "lane",
        "load_json",
        "normalize",
        "context",
        "payload",
        "build",
        "validate",
        "preview",
        "write",
        "serialize",
        "links",
        "campaign_href",
        "url_for",
        "jsonify",
    ]
    assert names.count("context") == 1


def test_manual_import_submit_invalid_json_and_caught_error_taxonomy(
    app, client, monkeypatch
):
    dependencies = _dependencies([])
    dependencies["load_json_object"] = lambda: (_ for _ in ()).throw(
        ValueError("Request body must be a JSON object.")
    )
    dependencies["normalize_character_authoring_values"] = lambda *args: pytest.fail(
        "invalid JSON reached normalization"
    )
    _install_dependencies(app, monkeypatch, SUBMIT_ENDPOINT, **dependencies)
    invalid = client.post(ROUTE_PATH, data="[]", content_type="application/json")
    assert invalid.status_code == 400
    assert invalid.get_json()["error"] == {
        "code": "invalid_json",
        "message": "Request body must be a JSON object.",
    }

    for error, status, code in (
        (ValueError("bad import"), 400, "validation_error"),
        (FileExistsError("duplicate"), 409, "character_exists"),
        (CharacterPathSafetyError("unsafe slug"), 400, "validation_error"),
    ):
        dependencies = _dependencies([])
        dependencies["load_json_object"] = lambda: {
            "values": {"name": "Imported Lotus"},
            "confirm_import": True,
        }
        if isinstance(error, ValueError) and not isinstance(error, CharacterPathSafetyError):
            dependencies["validate_character_slug"] = (
                lambda slug, current_error=error: (_ for _ in ()).throw(current_error)
            )
        else:
            dependencies["write_new_character_record"] = (
                lambda *args, current_error=error: (_ for _ in ()).throw(current_error)
            )
        _install_dependencies(app, monkeypatch, SUBMIT_ENDPOINT, **dependencies)
        response = client.post(ROUTE_PATH, json={})
        assert response.status_code == status
        assert response.get_json()["error"] == {"code": code, "message": str(error)}


def test_manual_import_endpoints_methods_order_manifest_and_policy(app, client):
    rules = {rule.endpoint: rule for rule in app.url_map.iter_rules()}
    context = rules[CONTEXT_ENDPOINT]
    submit = rules[SUBMIT_ENDPOINT]
    assert context.rule == "/api/v1/campaigns/<campaign_slug>/characters/import/xianxia-manual"
    assert context.methods == {"GET", "HEAD", "OPTIONS"}
    assert submit.rule == context.rule
    assert submit.methods == {"POST", "OPTIONS"}
    endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
    assert endpoints.index("api.character_create_submit") < endpoints.index(CONTEXT_ENDPOINT)
    assert endpoints.index(CONTEXT_ENDPOINT) < endpoints.index(SUBMIT_ENDPOINT)
    assert endpoints.index(SUBMIT_ENDPOINT) < endpoints.index("api.character_detail")
    assert client.options(ROUTE_PATH).status_code == 200
    assert client.put(ROUTE_PATH).status_code == 405
    assert client.delete(ROUTE_PATH).status_code == 405

    manifest = json.loads(
        (PROJECT_ROOT / "docs/contracts/route-api-role-visibility-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    for endpoint, method in ((CONTEXT_ENDPOINT, "GET"), (SUBMIT_ENDPOINT, "POST")):
        entries = [
            entry
            for entry in manifest["entries"]
            if entry["endpoint"] == endpoint and entry["method"] == method
        ]
        assert len(entries) == 1
        assert entries[0]["owning_domain"] == "characters"
        assert entries[0]["access_policy"] == "character_manager_api"
        assert entries[0]["system_restriction"] == "xianxia_only"

    policies = json.loads(
        (PROJECT_ROOT / "docs/contracts/route-access-policies.json").read_text(
            encoding="utf-8"
        )
    )
    for endpoint in (CONTEXT_ENDPOINT, SUBMIT_ENDPOINT):
        assert policies["endpoints"][endpoint] == {
            "profile": "character_manager_api",
            "owning_domain": "characters",
            "system_restriction": "xianxia_only",
        }


def test_manual_import_has_one_source_pair_and_transport_shape():
    source_root = PROJECT_ROOT / "player_wiki"
    matches: dict[str, list[tuple[str, ast.FunctionDef]]] = {
        "character_xianxia_manual_import_context": [],
        "character_xianxia_manual_import_submit": [],
    }
    for path in source_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in matches:
                matches[node.name].append((path.name, node))
    assert all(len(found) == 1 for found in matches.values())

    module_path = source_root / "character_xianxia_manual_import_api_routes.py"
    if not module_path.exists():
        assert {found[0][0] for found in matches.values()} == {"api.py"}
        assert all(len(found[0][1].decorator_list) == 1 for found in matches.values())
        return

    assert {found[0][0] for found in matches.values()} == {
        "character_xianxia_manual_import_api_routes.py"
    }
    assert all(found[0][1].decorator_list == [] for found in matches.values())
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    registrations = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 2


def test_manual_import_dependency_shape_and_forwarding_are_exact(
    app, monkeypatch
):
    raw_view = inspect.unwrap(app.view_functions[CONTEXT_ENDPOINT])
    assert "dependencies" in raw_view.__code__.co_freevars
    index = raw_view.__code__.co_freevars.index("dependencies")
    dependencies = raw_view.__closure__[index].cell_contents
    assert [field.name for field in fields(dependencies)] == [
        "ensure_character_authoring_access",
        "json_error",
        "normalize_character_authoring_values",
        "serialize_campaign",
        "serialize_character_authoring_links",
        "make_json_safe",
        "load_json_object",
        "write_new_character_record",
        "serialize_character_record",
        "flask_campaign_href",
        "native_character_create_lane",
        "build_xianxia_manual_import_context",
        "build_xianxia_manual_import_payload",
        "build_xianxia_manual_import_character",
        "validate_character_slug",
        "build_xianxia_manual_import_preview",
    ]

    forwarded = (
        "native_character_create_lane",
        "build_xianxia_manual_import_context",
        "build_xianxia_manual_import_payload",
        "build_xianxia_manual_import_character",
        "validate_character_slug",
        "build_xianxia_manual_import_preview",
    )
    for name in forwarded:
        marker = object()
        monkeypatch.setattr(api_module, name, lambda *args, result=marker, **kwargs: result)
        assert getattr(dependencies, name)("value") is marker
