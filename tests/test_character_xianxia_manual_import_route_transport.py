from __future__ import annotations

import ast
from dataclasses import fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import player_wiki.app as app_module
import player_wiki.character_xianxia_manual_import_routes as route_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.character_path_safety import CharacterPathSafetyError
from tests.helpers.api_test_helpers import api_headers, issue_api_token
from tests.helpers.xianxia_character_helpers import _configure_xianxia_campaign


ENDPOINT = "character_import_xianxia_manual_view"
ROUTE_PATH = "/campaigns/linden-pass/characters/import/xianxia-manual"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _handler(app):
    return inspect.unwrap(app.view_functions[ENDPOINT])


def _install_dependencies(app, monkeypatch, **replacements) -> None:
    raw_view = _handler(app)
    assert "dependencies" in raw_view.__code__.co_freevars
    index = raw_view.__code__.co_freevars.index("dependencies")
    current = raw_view.__closure__[index].cell_contents
    monkeypatch.setattr(
        raw_view.__closure__[index],
        "cell_contents",
        replace(current, **replacements),
    )


def _definition(slug: str = "imported-lotus"):
    return SimpleNamespace(
        name="Imported Lotus",
        character_slug=slug,
        to_dict=lambda: {"name": "Imported Lotus", "character_slug": slug},
    )


def _import_metadata():
    return SimpleNamespace(
        to_dict=lambda: {"source_path": "importer://xianxia-manual"}
    )


def _dependencies(tmp_path: Path, events: list[object]) -> dict[str, object]:
    campaign = SimpleNamespace(slug="linden-pass", system="Xianxia")
    systems_service = object()
    definition = _definition()
    metadata = _import_metadata()
    initial_state = {"revision": 0}
    characters_dir = tmp_path / "characters"
    characters_dir.mkdir(parents=True, exist_ok=True)

    def manage(campaign_slug):
        events.append(("manage", campaign_slug))
        return True

    def load(campaign_slug):
        events.append(("load", campaign_slug))
        return campaign

    def lane(system):
        events.append(("lane", system))
        return "xianxia"

    def get_systems():
        events.append("systems")
        return systems_service

    def context(*, systems_service, campaign_slug, values, preview=None):
        events.append(
            ("context", systems_service, campaign_slug, values, preview)
        )
        return {"martial_art_options": ["art-option"], "preview": preview}

    def render(campaign_slug, import_context, *, status_code=200):
        events.append(("render", campaign_slug, import_context, status_code))
        return f"render:{status_code}", status_code

    def payload(values):
        events.append(("payload", values))
        return {"name": values.get("name", "")}

    def build(current_payload, *, campaign_slug, martial_art_options):
        events.append(
            ("build", current_payload, campaign_slug, martial_art_options)
        )
        return definition, metadata, initial_state

    def validate(character_slug):
        events.append(("validate", character_slug))

    def preview(current_definition, state):
        events.append(("preview", current_definition, state))
        return {"name": current_definition.name}

    def load_config(campaigns_dir, campaign_slug):
        events.append(("config", campaigns_dir, campaign_slug))
        return SimpleNamespace(characters_dir=characters_dir)

    def resolve(root, *parts):
        events.append(("resolve", root, parts))
        return root.joinpath(*parts)

    def write(path, payload):
        events.append(("write", path, payload))

    return {
        "load_campaign_context": load,
        "get_systems_service": get_systems,
        "render_xianxia_manual_import_page": render,
        "can_manage_campaign_session": manage,
        "native_character_create_lane": lane,
        "build_xianxia_manual_import_context": context,
        "build_xianxia_manual_import_payload": payload,
        "build_xianxia_manual_import_character": build,
        "validate_character_slug": validate,
        "build_xianxia_manual_import_preview": preview,
        "load_campaign_character_config": load_config,
        "resolve_character_path": resolve,
        "write_yaml": write,
    }


def test_transport_has_exact_dependency_and_composition_shape() -> None:
    assert [
        field.name
        for field in fields(
            route_module.CharacterXianxiaManualImportRouteDependencies
        )
    ] == [
        "load_campaign_context",
        "get_systems_service",
        "render_xianxia_manual_import_page",
        "can_manage_campaign_session",
        "native_character_create_lane",
        "build_xianxia_manual_import_context",
        "build_xianxia_manual_import_payload",
        "build_xianxia_manual_import_character",
        "validate_character_slug",
        "build_xianxia_manual_import_preview",
        "load_campaign_character_config",
        "resolve_character_path",
        "write_yaml",
    ]

    source_root = PROJECT_ROOT / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_xianxia_manual_import_routes.py").read_text(
            encoding="utf-8"
        )
    )
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
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
        and node.func.id == "register_character_xianxia_manual_import_route"
    )
    dependency_call = next(
        node
        for node in ast.walk(registrar_call)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "CharacterXianxiaManualImportRouteDependencies"
    )
    keyword_values = {keyword.arg: keyword.value for keyword in dependency_call.keywords}
    for name in (
        "load_campaign_context",
        "get_systems_service",
        "render_xianxia_manual_import_page",
    ):
        assert isinstance(keyword_values[name], ast.Name)
        assert keyword_values[name].id == name
    assert all(
        isinstance(keyword_values[name], ast.Lambda)
        for name in set(keyword_values)
        - {
            "load_campaign_context",
            "get_systems_service",
            "render_xianxia_manual_import_page",
        }
    )


def test_dependency_forwarders_remain_post_registration_monkeypatchable(
    app, monkeypatch
):
    raw_view = _handler(app)
    index = raw_view.__code__.co_freevars.index("dependencies")
    dependencies = raw_view.__closure__[index].cell_contents
    forwarded = (
        "can_manage_campaign_session",
        "native_character_create_lane",
        "build_xianxia_manual_import_context",
        "build_xianxia_manual_import_payload",
        "build_xianxia_manual_import_character",
        "validate_character_slug",
        "build_xianxia_manual_import_preview",
        "load_campaign_character_config",
        "resolve_character_path",
        "write_yaml",
    )
    invocations = {
        "can_manage_campaign_session": (("linden-pass",), {}),
        "native_character_create_lane": (("Xianxia",), {}),
        "build_xianxia_manual_import_context": (
            (),
            {
                "systems_service": object(),
                "campaign_slug": "linden-pass",
                "values": {},
            },
        ),
        "build_xianxia_manual_import_payload": (({},), {}),
        "build_xianxia_manual_import_character": (
            ({},),
            {"campaign_slug": "linden-pass", "martial_art_options": []},
        ),
        "validate_character_slug": (("imported-lotus",), {}),
        "build_xianxia_manual_import_preview": ((object(), {}), {}),
        "load_campaign_character_config": ((Path("root"), "linden-pass"), {}),
        "resolve_character_path": ((Path("root"), "imported-lotus"), {}),
        "write_yaml": ((Path("definition.yaml"), {}), {}),
    }
    for name in forwarded:
        marker = object()
        monkeypatch.setattr(
            app_module, name, lambda *args, result=marker, **kwargs: result
        )
        args, kwargs = invocations[name]
        assert getattr(dependencies, name)(*args, **kwargs) is marker


def test_route_identity_methods_registration_manifest_and_policy(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    rule = next(rule for rule in rules if rule.endpoint == ENDPOINT)
    assert rule.rule == "/campaigns/<campaign_slug>/characters/import/xianxia-manual"
    assert rule.methods == {"GET", "HEAD", "POST", "OPTIONS"}
    assert _handler(app).__name__ == ENDPOINT
    assert endpoints.index("character_create_view") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index("character_level_up_view")
    assert client.options(ROUTE_PATH).status_code == 200
    for method in ("put", "patch", "delete"):
        assert getattr(client, method)(ROUTE_PATH).status_code == 405

    manifest_bytes = (
        PROJECT_ROOT / "docs/contracts/route-api-role-visibility-manifest.json"
    ).read_bytes()
    policy_bytes = (
        PROJECT_ROOT / "docs/contracts/route-access-policies.json"
    ).read_bytes()
    assert b'"endpoint": "character_import_xianxia_manual_view"' in manifest_bytes
    assert b'"character_import_xianxia_manual_view"' in policy_bytes


def test_scope_assignment_manager_and_missing_order(
    app, client, sign_in, users, set_campaign_visibility, monkeypatch
):
    _configure_xianxia_campaign(app)
    set_campaign_visibility("linden-pass", characters="private")
    anonymous = client.get(f"{ROUTE_PATH}?repeat=first&repeat=second")
    assert anonymous.status_code == 302
    assert anonymous.headers["Location"].endswith(
        "/sign-in?next=/campaigns/linden-pass/characters/import/xianxia-manual?repeat%3Dfirst%26repeat%3Dsecond"
    )
    assert client.get(
        "/campaigns/missing/characters/import/xianxia-manual"
    ).status_code == 404

    sign_in(users["owner"]["email"], users["owner"]["password"])
    # Assignment does not bypass Characters visibility.
    assert client.get(ROUTE_PATH).status_code == 404

    set_campaign_visibility("linden-pass", characters="public")
    calls: list[str] = []
    _install_dependencies(
        app,
        monkeypatch,
        can_manage_campaign_session=lambda slug: calls.append("manage") or False,
        load_campaign_context=lambda slug: pytest.fail("denial loaded campaign"),
    )
    assert client.get(ROUTE_PATH).status_code == 403
    assert calls == ["manage"]


def test_view_as_csrf_bearer_head_and_options_order(
    app, client, sign_in, users, monkeypatch
):
    _configure_xianxia_campaign(app)
    sign_in(users["admin"]["email"], users["admin"]["password"])
    app.config["CSRF_ENABLED"] = True
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    assert client.post(ROUTE_PATH, data={}).status_code == 403

    with client.session_transaction() as browser_session:
        browser_session.pop(VIEW_AS_SESSION_KEY, None)
    csrf = client.post(ROUTE_PATH, data={})
    assert csrf.status_code == 400
    assert "Refresh the page and try again." in csrf.get_data(as_text=True)

    token = issue_api_token(app, users["admin"]["email"], label="p41-browser-bearer")
    bearer = app.test_client().post(
        ROUTE_PATH,
        data={},
        headers=api_headers(token),
        follow_redirects=False,
    )
    assert bearer.status_code == 400
    assert "Refresh the page and try again." not in bearer.get_data(as_text=True)

    events: list[object] = []
    dependencies = _dependencies(app.config["TEST_CAMPAIGNS_DIR"], events)
    _install_dependencies(app, monkeypatch, **dependencies)
    app.config["CSRF_ENABLED"] = False
    assert client.head(f"{ROUTE_PATH}?blank=&repeat=first&repeat=second").status_code == 200
    assert events
    events.clear()
    assert client.options(ROUTE_PATH).status_code == 200
    assert events == []


def test_get_and_unsupported_system_preserve_order(
    app, client, sign_in, users, monkeypatch, tmp_path
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    events: list[object] = []
    dependencies = _dependencies(tmp_path, events)
    _install_dependencies(app, monkeypatch, **dependencies)
    response = client.get(f"{ROUTE_PATH}?blank=&repeat=first&repeat=second")
    assert response.status_code == 200
    assert [event[0] if isinstance(event, tuple) else event for event in events] == [
        "manage",
        "load",
        "lane",
        "systems",
        "context",
        "render",
    ]
    assert events[4][3] == {"blank": "", "repeat": "first"}

    events.clear()
    dependencies["native_character_create_lane"] = (
        lambda system: events.append(("lane", system)) or "dnd5e"
    )
    for name in (
        "get_systems_service",
        "build_xianxia_manual_import_context",
        "render_xianxia_manual_import_page",
    ):
        dependencies[name] = lambda *args, **kwargs: pytest.fail(
            "unsupported system entered form/context work"
        )
    _install_dependencies(app, monkeypatch, **dependencies)
    response = client.get(ROUTE_PATH, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters"
    )
    assert [event[0] for event in events] == ["manage", "load", "lane"]


@pytest.mark.parametrize("confirm", (None, ""))
def test_post_preview_builds_two_contexts_and_never_persists(
    app, client, sign_in, users, monkeypatch, tmp_path, confirm
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    events: list[object] = []
    dependencies = _dependencies(tmp_path, events)
    dependencies["load_campaign_character_config"] = lambda *args: pytest.fail(
        "preview loaded persistence config"
    )
    _install_dependencies(app, monkeypatch, **dependencies)
    data = {"name": "Imported Lotus", "repeat": ["first", "second"]}
    if confirm is not None:
        data["confirm_import"] = confirm
    response = client.post(ROUTE_PATH, data=data)
    assert response.status_code == 200
    names = [event[0] if isinstance(event, tuple) else event for event in events]
    assert names == [
        "manage",
        "load",
        "lane",
        "systems",
        "context",
        "payload",
        "build",
        "validate",
        "preview",
        "systems",
        "context",
        "render",
    ]
    assert [event for event in events if isinstance(event, tuple) and event[0] == "context"][0][3]["repeat"] == "first"
    assert [event for event in events if isinstance(event, tuple) and event[0] == "context"][1][4] == {"name": "Imported Lotus"}


def test_nonempty_zero_confirmation_preserves_write_state_and_redirect_order(
    app, client, sign_in, users, monkeypatch, tmp_path
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    events: list[object] = []
    dependencies = _dependencies(tmp_path, events)
    _install_dependencies(app, monkeypatch, **dependencies)

    state_store = app.extensions["character_state_store"]
    monkeypatch.setattr(
        state_store,
        "initialize_state_if_missing",
        lambda definition, state: events.append(("state", definition, state)),
    )
    original_flash = route_module.flash
    original_url_for = route_module.url_for
    original_redirect = route_module.redirect
    monkeypatch.setattr(
        route_module,
        "flash",
        lambda message, category: events.append(("flash", message, category))
        or original_flash(message, category),
    )
    monkeypatch.setattr(
        route_module,
        "url_for",
        lambda endpoint, **values: events.append(("url_for", endpoint, values))
        or original_url_for(endpoint, **values),
    )
    monkeypatch.setattr(
        route_module,
        "redirect",
        lambda location: events.append(("redirect", location))
        or original_redirect(location),
    )

    response = client.post(
        ROUTE_PATH,
        data={"name": "Imported Lotus", "confirm_import": "0"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    names = [event[0] if isinstance(event, tuple) else event for event in events]
    assert names == [
        "manage",
        "load",
        "lane",
        "systems",
        "context",
        "payload",
        "build",
        "validate",
        "preview",
        "systems",
        "context",
        "config",
        "resolve",
        "resolve",
        "resolve",
        "write",
        "write",
        "state",
        "flash",
        "url_for",
        "redirect",
    ]
    resolve_events = [event for event in events if event[0] == "resolve"]
    assert [event[2] for event in resolve_events] == [
        ("imported-lotus",),
        ("imported-lotus", "definition.yaml"),
        ("imported-lotus", "import.yaml"),
    ]


def test_caught_error_taxonomy_and_duplicate_order(
    app, client, sign_in, users, monkeypatch, tmp_path
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    events: list[object] = []
    dependencies = _dependencies(tmp_path, events)
    dependencies["validate_character_slug"] = lambda slug: (_ for _ in ()).throw(
        ValueError("unsafe slug")
    )
    _install_dependencies(app, monkeypatch, **dependencies)
    invalid = client.post(ROUTE_PATH, data={"name": "bad"})
    assert invalid.status_code == 400
    with client.session_transaction() as browser_session:
        assert browser_session["_flashes"][-1] == ("error", "unsafe slug")

    events.clear()
    dependencies = _dependencies(tmp_path, events)
    dependencies["resolve_character_path"] = lambda *args: (_ for _ in ()).throw(
        CharacterPathSafetyError("outside root")
    )
    _install_dependencies(app, monkeypatch, **dependencies)
    containment = client.post(
        ROUTE_PATH, data={"name": "bad", "confirm_import": "1"}
    )
    assert containment.status_code == 400
    with client.session_transaction() as browser_session:
        assert browser_session["_flashes"][-1] == ("error", "outside root")

    events.clear()
    dependencies = _dependencies(tmp_path, events)
    character_dir = tmp_path / "characters" / "imported-lotus"
    character_dir.mkdir(parents=True, exist_ok=True)
    (character_dir / "definition.yaml").write_text("existing", encoding="utf-8")
    _install_dependencies(app, monkeypatch, **dependencies)
    duplicate = client.post(
        ROUTE_PATH, data={"name": "duplicate", "confirm_import": "1"}
    )
    assert duplicate.status_code == 409
    names = [event[0] if isinstance(event, tuple) else event for event in events]
    assert names[-1] == "render"
    assert "write" not in names
    assert "state" not in names


@pytest.mark.parametrize(
    ("fault_stage", "expected_completed"),
    (("definition", 0), ("import", 1), ("state", 2)),
)
def test_persistence_faults_preserve_no_rollback_partial_commit_order(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    tmp_path,
    fault_stage,
    expected_completed,
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    events: list[object] = []
    dependencies = _dependencies(tmp_path, events)
    completed: list[str] = []

    def write(path, payload):
        stage = "definition" if path.name == "definition.yaml" else "import"
        events.append(("write", stage))
        if stage == fault_stage:
            raise RuntimeError(stage)
        completed.append(stage)

    dependencies["write_yaml"] = write
    _install_dependencies(app, monkeypatch, **dependencies)
    monkeypatch.setattr(
        app.extensions["character_state_store"],
        "initialize_state_if_missing",
        lambda *args: (_ for _ in ()).throw(RuntimeError("state"))
        if fault_stage == "state"
        else completed.append("state"),
    )

    with pytest.raises(RuntimeError, match=fault_stage):
        client.post(
            ROUTE_PATH,
            data={"name": "Imported Lotus", "confirm_import": "1"},
        )
    assert len(completed) == expected_completed


@pytest.mark.parametrize("fault_stage", ("flash", "url_for", "redirect"))
def test_post_state_response_faults_do_not_undo_persistence(
    app, client, sign_in, users, monkeypatch, tmp_path, fault_stage
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    events: list[object] = []
    dependencies = _dependencies(tmp_path, events)
    _install_dependencies(app, monkeypatch, **dependencies)
    completed: list[str] = []
    monkeypatch.setattr(
        app.extensions["character_state_store"],
        "initialize_state_if_missing",
        lambda *args: completed.append("state"),
    )

    original_flash = route_module.flash
    original_url_for = route_module.url_for

    def flash(message, category):
        if category == "success" and fault_stage == "flash":
            raise RuntimeError("flash")
        return original_flash(message, category)

    def url_for(endpoint, **values):
        if fault_stage == "url_for":
            raise RuntimeError("url_for")
        return original_url_for(endpoint, **values)

    monkeypatch.setattr(route_module, "flash", flash)
    monkeypatch.setattr(route_module, "url_for", url_for)
    if fault_stage == "redirect":
        monkeypatch.setattr(
            route_module,
            "redirect",
            lambda *args: (_ for _ in ()).throw(RuntimeError("redirect")),
        )

    with pytest.raises(RuntimeError, match=fault_stage):
        client.post(
            ROUTE_PATH,
            data={"name": "Imported Lotus", "confirm_import": "1"},
        )
    assert completed == ["state"]
