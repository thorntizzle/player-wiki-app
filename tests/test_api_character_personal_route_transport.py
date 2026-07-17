from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
import yaml

import player_wiki.character_personal_api_routes as route_module
import player_wiki.character_rest_api_routes as rest_route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.character_store import CharacterStateStore
from player_wiki.route_contracts import build_manifest
from tests.helpers.api_test_helpers import api_headers, issue_api_token
from tests.helpers.xianxia_character_helpers import (
    _configure_xianxia_campaign,
    _valid_xianxia_create_data,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "fbd9b299fdc4e0428d23b5fb785f0c4c27723172"
ROUTE_PATH = "/api/v1/campaigns/linden-pass/characters/arden-march/session/personal"
ENDPOINT = "api.character_personal_update"
DEPENDENCY_ORDER = [
    "api_campaign_scope_access_required",
    "api_login_required",
    "run_character_mutation",
    "get_character_state_service",
]


def _handler(app):
    return inspect.unwrap(app.view_functions[ENDPOINT])


def _dependencies_cell(app):
    raw_view = _handler(app)
    freevars = dict(zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ()))
    return freevars["dependencies"]


def _install_dependencies(app, monkeypatch, **replacements) -> None:
    cell = _dependencies_cell(app)
    monkeypatch.setattr(
        cell,
        "cell_contents",
        replace(cell.cell_contents, **replacements),
    )


class _DependencyQualifier(ast.NodeTransformer):
    def visit_Attribute(self, node: ast.Attribute):
        node = self.generic_visit(node)
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "dependencies"
        ):
            return ast.copy_location(ast.Name(id=node.attr, ctx=node.ctx), node)
        return node


def _canonical_handler(node: ast.FunctionDef) -> str:
    node = _DependencyQualifier().visit(ast.fix_missing_locations(node))
    node.decorator_list = []
    return ast.dump(node, include_attributes=False)


class RecordingPayload:
    def __init__(self, values, events):
        self.values = values
        self.events = events

    def get(self, key):
        self.events.append(("payload_get", key))
        return self.values.get(key)


def _dependencies(events: list[tuple], *, payload_values=None, system="dnd5e"):
    record = SimpleNamespace(
        definition=SimpleNamespace(system=system),
        state_record=SimpleNamespace(state={}),
    )
    payload = RecordingPayload(
        {
            "expected_revision": 17,
            "physical_description_markdown": "Broad-shouldered and steady-eyed.",
            "background_markdown": "Ran messages along the harbor roads.",
        }
        if payload_values is None
        else payload_values,
        events,
    )

    def update(*args, **kwargs):
        events.append(("update", args, kwargs))
        return "updated-state"

    service = SimpleNamespace(update_personal_details=update)

    def get_service(*args, **kwargs):
        events.append(("service", args, kwargs))
        return service

    def runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        result = args[2](record, payload, 42)
        events.append(("action_result", (result,), {}))
        return "mutation-result"

    return {
        "run_character_mutation": runner,
        "get_character_state_service": get_service,
    }


def test_transport_has_exact_dependencies_registration_wrappers_and_source_shape() -> None:
    assert [field.name for field in fields(route_module.CharacterPersonalApiDependencies)] == (
        DEPENDENCY_ORDER
    )

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_personal_api_routes.py").read_text(encoding="utf-8")
    )
    api_tree = ast.parse((source_root / "api.py").read_text(encoding="utf-8"))
    handler = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_personal_update"
    )
    assert handler.decorator_list == []
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "character_personal_update"
        for node in ast.walk(api_tree)
    )

    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_character_personal_api_route"
    )
    registrations = [
        node
        for node in ast.walk(registrar)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1
    view_func = next(
        keyword.value
        for keyword in registrations[0].keywords
        if keyword.arg == "view_func"
    )
    assert isinstance(view_func, ast.Call)
    assert isinstance(view_func.func, ast.Call)
    assert isinstance(view_func.func.func, ast.Attribute)
    assert view_func.func.func.attr == "api_campaign_scope_access_required"
    assert len(view_func.func.args) == 1
    assert isinstance(view_func.func.args[0], ast.Constant)
    assert view_func.func.args[0].value == "characters"
    assert len(view_func.args) == 1
    inner = view_func.args[0]
    assert isinstance(inner, ast.Call)
    assert isinstance(inner.func, ast.Attribute)
    assert inner.func.attr == "api_login_required"
    assert isinstance(inner.args[0], ast.Name)
    assert inner.args[0].id == "character_personal_update"
    assert not any(
        isinstance(node, ast.Name)
        and node.id in {"current_app", "request", "is_xianxia_system"}
        for node in ast.walk(route_tree)
    )

    register_api = next(
        node
        for node in api_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_api"
    )
    assert len(register_api.body) == 268
    assert sum(isinstance(node, ast.FunctionDef) for node in register_api.body) == 221
    assert sum(isinstance(node, ast.FunctionDef) for node in ast.walk(register_api)) == 231
    api_route_decorators = [
        decorator
        for node in ast.walk(register_api)
        if isinstance(node, ast.FunctionDef)
        for decorator in node.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and isinstance(decorator.func.value, ast.Name)
        and decorator.func.value.id == "api"
    ]
    assert len(api_route_decorators) == 53

    assert isinstance(register_api.body[264], ast.Expr)
    assert register_api.body[264].value.func.id == "register_character_notes_api_route"
    assert isinstance(register_api.body[265], ast.Expr)
    assert register_api.body[265].value.func.id == "register_character_personal_api_route"
    assert isinstance(register_api.body[266], ast.Expr)
    assert register_api.body[266].value.func.id == "register_character_rest_api_route"
    rest_source = inspect.getsource(rest_route_module)
    rest_tree = ast.parse(rest_source)
    rest_handler = next(
        node
        for node in ast.walk(rest_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_rest_apply"
    )
    assert rest_handler.decorator_list == []

    dependency_call = next(
        node
        for node in ast.walk(register_api.body[265])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterPersonalApiDependencies"
    )
    by_name = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    assert list(by_name) == DEPENDENCY_ORDER
    assert all(isinstance(by_name[name], ast.Name) for name in DEPENDENCY_ORDER)


def test_moved_handler_keeps_canonical_ast_and_all_unrelated_statement_parity() -> None:
    route_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "character_personal_api_routes.py").read_text(
            encoding="utf-8"
        )
    )
    moved = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "character_personal_update"
    )
    old_tree = ast.parse(
        subprocess.check_output(
            ["git", "show", f"{BASE_COMMIT}:player_wiki/api.py"], text=True
        )
    )
    new_tree = ast.parse(
        (PROJECT_ROOT / "player_wiki" / "api.py").read_text(encoding="utf-8")
    )
    old_register = next(
        node
        for node in old_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_api"
    )
    new_register = next(
        node
        for node in new_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_api"
    )
    original = old_register.body[265]
    assert isinstance(original, ast.FunctionDef)
    assert original.name == "character_personal_update"
    assert _canonical_handler(moved) == _canonical_handler(original)
    assert len(old_register.body) == len(new_register.body) == 268
    for index, (before, after) in enumerate(zip(old_register.body, new_register.body)):
        if index in {162, 253, 254, 255, 265, 266}:
            continue
        assert ast.dump(before, include_attributes=False) == ast.dump(
            after, include_attributes=False
        )


def test_route_preserves_endpoint_methods_wrappers_and_registration_order(app, client):
    endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
    assert endpoints.index("api.character_notes_update") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index("api.character_rest_apply")
    rule = next(rule for rule in app.url_map.iter_rules() if rule.endpoint == ENDPOINT)
    assert rule.rule == (
        "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>/session/personal"
    )
    assert rule.methods == {"PATCH", "OPTIONS"}
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("get", "head", "post", "put", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405
    assert client.patch(ROUTE_PATH).status_code == 401
    assert inspect.unwrap(app.view_functions[ENDPOINT]).__name__ == (
        "character_personal_update"
    )


def test_handler_preserves_service_revision_fields_and_actor_evaluation_order(
    app,
    monkeypatch,
):
    events: list[tuple] = []
    _install_dependencies(app, monkeypatch, **_dependencies(events))
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        assert _handler(app)("linden-pass", "arden-march") == "mutation-result"

    assert [event[0] for event in events] == [
        "runner",
        "service",
        "payload_get",
        "payload_get",
        "payload_get",
        "update",
        "action_result",
    ]
    assert [event[1] for event in events if event[0] == "payload_get"] == [
        "expected_revision",
        "physical_description_markdown",
        "background_markdown",
    ]
    update = next(event for event in events if event[0] == "update")
    assert update[2] == {
        "expected_revision": 17,
        "physical_description_markdown": "Broad-shouldered and steady-eyed.",
        "background_markdown": "Ran messages along the harbor roads.",
        "updated_by_user_id": 42,
    }


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    (
        (None, ""),
        ("", ""),
        (0, ""),
        (False, ""),
        (17, "17"),
        (["detail"], "['detail']"),
    ),
)
@pytest.mark.parametrize(
    "field",
    ("physical_description_markdown", "background_markdown"),
)
def test_personal_fields_preserve_falsey_clear_and_truthy_string_coercion(
    app,
    monkeypatch,
    field,
    raw_value,
    expected,
):
    events: list[tuple] = []
    values = {
        "expected_revision": 17,
        "physical_description_markdown": "physical",
        "background_markdown": "background",
    }
    values[field] = raw_value
    _install_dependencies(
        app,
        monkeypatch,
        **_dependencies(events, payload_values=values),
    )
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        assert _handler(app)("linden-pass", "arden-march") == "mutation-result"
    update = next(event for event in events if event[0] == "update")
    assert update[2][field] == expected


def test_service_is_acquired_before_invalid_revision_stops_personal_field_reads(
    app,
    monkeypatch,
):
    events: list[tuple] = []
    _install_dependencies(
        app,
        monkeypatch,
        **_dependencies(
            events,
            payload_values={
                "expected_revision": "not-an-int",
                "physical_description_markdown": "must not be read",
                "background_markdown": "must not be read",
            },
        ),
    )
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        with pytest.raises(ValueError):
            _handler(app)("linden-pass", "arden-march")
    assert [event[0] for event in events] == ["runner", "service", "payload_get"]
    assert events[-1][1] == "expected_revision"


@pytest.mark.parametrize("fault_stage", ("runner", "service", "update"))
def test_unrelated_transport_faults_propagate_at_exact_stage(
    app,
    monkeypatch,
    fault_stage,
):
    events: list[tuple] = []
    replacements = _dependencies(events)

    def fault(*args, **kwargs):
        raise RuntimeError(f"{fault_stage} fault")

    if fault_stage == "runner":
        replacements["run_character_mutation"] = fault
    elif fault_stage == "service":
        replacements["get_character_state_service"] = fault
    else:
        replacements["get_character_state_service"] = lambda: SimpleNamespace(
            update_personal_details=fault
        )
    _install_dependencies(app, monkeypatch, **replacements)
    with app.test_request_context(ROUTE_PATH, method="PATCH"):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _handler(app)("linden-pass", "arden-march")


def test_view_as_denial_precedes_handler_but_bearer_identity_wins(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    events: list[tuple] = []

    def runner(*args, **kwargs):
        events.append(("runner", args, kwargs))
        return {"ok": True}

    _install_dependencies(app, monkeypatch, run_character_mutation=runner)
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    assert client.patch(ROUTE_PATH).status_code == 403
    assert events == []

    token = issue_api_token(app, users["admin"]["email"], label="p89-bearer")
    response = client.patch(ROUTE_PATH, headers=api_headers(token), json={})
    assert response.status_code == 200
    assert [event[0] for event in events] == ["runner"]


def test_runner_preserves_access_json_validation_conflict_and_precommit_atomicity(
    client,
    app,
    users,
    set_campaign_visibility,
    monkeypatch,
):
    set_campaign_visibility("linden-pass", characters="players")
    owner_token = issue_api_token(app, users["owner"]["email"], label="p89-owner")
    party_token = issue_api_token(app, users["party"]["email"], label="p89-party")
    repository = app.extensions["character_repository"]
    with app.app_context():
        before = repository.get_visible_character("linden-pass", "arden-march")
    assert before is not None
    starting_revision = before.state_record.revision

    def unexpected_save(*args, **kwargs):
        raise AssertionError("denied or malformed request reached personal persistence")

    service = app.extensions["character_state_service"]
    original_update = service.update_personal_details
    monkeypatch.setattr(service, "update_personal_details", unexpected_save)
    denied = client.patch(
        ROUTE_PATH,
        headers=api_headers(party_token),
        json={
            "expected_revision": starting_revision,
            "physical_description_markdown": "no",
        },
    )
    assert denied.status_code == 403
    assert denied.get_json()["error"]["code"] == "forbidden"

    malformed = client.patch(
        ROUTE_PATH,
        headers={**api_headers(owner_token), "Content-Type": "application/json"},
        data="{",
    )
    assert malformed.status_code == 400
    assert malformed.get_json()["error"]["code"] == "invalid_json"

    invalid_revision = client.patch(
        ROUTE_PATH,
        headers=api_headers(owner_token),
        json={
            "expected_revision": "not-an-int",
            "physical_description_markdown": "no",
        },
    )
    assert invalid_revision.status_code == 400
    assert invalid_revision.get_json()["error"]["code"] == "validation_error"
    monkeypatch.setattr(service, "update_personal_details", original_update)

    stale = client.patch(
        ROUTE_PATH,
        headers=api_headers(owner_token),
        json={
            "expected_revision": starting_revision + 99,
            "physical_description_markdown": "stale",
            "background_markdown": "stale",
        },
    )
    assert stale.status_code == 409
    assert stale.get_json()["error"]["code"] == "state_conflict"

    with app.app_context():
        after = repository.get_visible_character("linden-pass", "arden-march")
    assert after is not None
    assert after.state_record.revision == starting_revision


def test_real_service_sanitizes_personal_fields_and_missing_fields_clear(
    client,
    app,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="players")
    token = issue_api_token(app, users["owner"]["email"], label="p89-sanitize")
    repository = app.extensions["character_repository"]
    with app.app_context():
        before = repository.get_visible_character("linden-pass", "arden-march")
    assert before is not None

    response = client.patch(
        ROUTE_PATH,
        headers=api_headers(token),
        json={
            "expected_revision": before.state_record.revision,
            "physical_description_markdown": (
                '<p onclick="alert(1)">Steady-eyed.</p><script>alert(1)</script>'
            ),
            "background_markdown": (
                '<a href="javascript:alert(1)">Harbor runner.</a>'
            ),
        },
    )
    assert response.status_code == 200
    notes = response.get_json()["character"]["state_record"]["state"]["notes"]
    assert notes["physical_description_markdown"] == (
        "<p>Steady-eyed.</p>alert(1)"
    )
    assert notes["background_markdown"] == "<a>Harbor runner.</a>"

    cleared = client.patch(
        ROUTE_PATH,
        headers=api_headers(token),
        json={"expected_revision": response.get_json()["character"]["state_record"]["revision"]},
    )
    assert cleared.status_code == 200
    cleared_notes = cleared.get_json()["character"]["state_record"]["state"]["notes"]
    assert cleared_notes["physical_description_markdown"] == ""
    assert cleared_notes["background_markdown"] == ""


def test_xianxia_personal_update_keeps_shared_fields_without_player_note_sync(
    app,
    client,
    sign_in,
    users,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    created = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data(
            "P89 Personal Crane",
            slug="p89-personal-crane",
        ),
        follow_redirects=False,
    )
    assert created.status_code == 302

    token = issue_api_token(app, users["dm"]["email"], label="p89-xianxia")
    repository = app.extensions["character_repository"]
    with app.app_context():
        before = repository.get_visible_character("linden-pass", "p89-personal-crane")
    assert before is not None
    prior_xianxia_notes = dict(before.state_record.state["xianxia"].get("notes") or {})
    response = client.patch(
        ROUTE_PATH.replace("arden-march", "p89-personal-crane"),
        headers=api_headers(token),
        json={
            "expected_revision": before.state_record.revision,
            "physical_description_markdown": "Jade-eyed.",
            "background_markdown": "Raised beneath the crane banners.",
        },
    )
    assert response.status_code == 200
    state = response.get_json()["character"]["state_record"]["state"]
    assert state["notes"]["physical_description_markdown"] == "Jade-eyed."
    assert state["notes"]["background_markdown"] == (
        "Raised beneath the crane banners."
    )
    assert dict(state["xianxia"].get("notes") or {}) == prior_xianxia_notes


def test_p34_identity_mismatch_stops_before_state_or_personal_service(
    client,
    app,
    users,
    set_campaign_visibility,
    monkeypatch,
):
    set_campaign_visibility("linden-pass", characters="players")
    token = issue_api_token(app, users["owner"]["email"], label="p89-p34")
    definition_path = (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / "linden-pass"
        / "characters"
        / "arden-march"
        / "definition.yaml"
    )
    definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    definition["character_slug"] = "another-character"
    definition_path.write_text(
        yaml.safe_dump(definition, sort_keys=False), encoding="utf-8"
    )

    def unexpected(*args, **kwargs):
        raise AssertionError("identity mismatch reached personal work")

    monkeypatch.setattr(CharacterStateStore, "get_state", unexpected)
    monkeypatch.setattr(
        app.extensions["character_state_service"],
        "update_personal_details",
        unexpected,
    )
    response = client.patch(
        ROUTE_PATH,
        headers=api_headers(token),
        json={
            "expected_revision": 0,
            "physical_description_markdown": "no",
            "background_markdown": "no",
        },
    )
    assert response.status_code == 404


def test_committed_personal_details_survive_refresh_serialization_fault(
    client,
    app,
    users,
    set_campaign_visibility,
    monkeypatch,
):
    set_campaign_visibility("linden-pass", characters="players")
    token = issue_api_token(app, users["owner"]["email"], label="p89-postcommit")
    repository = app.extensions["character_repository"]
    original_load = repository.get_visible_character
    with app.app_context():
        before = original_load("linden-pass", "arden-march")
    assert before is not None
    starting_revision = before.state_record.revision
    calls = 0

    def fail_refresh(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("refresh serialization fault")
        return original_load(*args, **kwargs)

    monkeypatch.setattr(repository, "get_visible_character", fail_refresh)
    with pytest.raises(RuntimeError, match="refresh serialization fault"):
        client.patch(
            ROUTE_PATH,
            headers=api_headers(token),
            json={
                "expected_revision": starting_revision,
                "physical_description_markdown": "Persists through refresh failure.",
                "background_markdown": "Also persists.",
            },
        )

    with app.app_context():
        persisted = original_load("linden-pass", "arden-march")
    assert persisted is not None
    assert persisted.state_record.revision == starting_revision + 1
    assert persisted.state_record.state["notes"]["physical_description_markdown"] == (
        "Persists through refresh failure."
    )
    assert persisted.state_record.state["notes"]["background_markdown"] == (
        "Also persists."
    )


def test_browser_personal_keeps_form_block_render_redirect_distinction_and_service_inline():
    api_source = (
        PROJECT_ROOT / "player_wiki" / "character_personal_api_routes.py"
    ).read_text(encoding="utf-8")
    browser_source = (
        PROJECT_ROOT / "player_wiki" / "character_session_personal_routes.py"
    ).read_text(encoding="utf-8")
    assert 'payload.get("physical_description_markdown")' in api_source
    assert 'request.form.get("physical_description_markdown", "")' in browser_source
    assert "run_character_mutation" in api_source
    assert "ensure_active_session_for_session_character_mutation" in browser_source
    assert "session_character_advanced_personal_edit_block_message" in browser_source


def test_manifest_metadata_remains_characters_scope_without_system_gate():
    entries = [
        entry
        for entry in build_manifest()["entries"]
        if entry["endpoint"] == ENDPOINT and entry["method"] == "PATCH"
    ]
    assert len(entries) == 1
    assert entries[0]["campaign_scope"] == "characters"
    assert entries[0]["system_restriction"] == "none"
    assert entries[0]["authentication_policy"] == "api_identity_required"
    assert entries[0]["access_policy"] == "character_owner_or_manager_api"
