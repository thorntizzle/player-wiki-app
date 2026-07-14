from __future__ import annotations

import ast
from dataclasses import replace
import importlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import player_wiki.api as api_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from tests.helpers.api_test_helpers import api_headers, issue_api_token
from tests.helpers.xianxia_character_helpers import (
    _configure_xianxia_campaign,
    _valid_xianxia_create_data,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "api.character_detail"
ROUTE_PATH = "/api/v1/campaigns/linden-pass/characters/arden-march"
DEPENDENCY_KEY = "character_detail_api_dependencies"


def _install_dependencies(app, monkeypatch, **replacements) -> None:
    dependencies = app.extensions.get(DEPENDENCY_KEY)
    if dependencies is not None:
        monkeypatch.setitem(
            app.extensions,
            DEPENDENCY_KEY,
            replace(dependencies, **replacements),
        )
        return

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
    closure_names = {
        "json_error",
        "load_character_record",
        "serialize_character_record",
        "serialize_character_links",
    }
    for name, value in replacements.items():
        if name in closure_names:
            index = raw_view.__code__.co_freevars.index(name)
            monkeypatch.setattr(raw_view.__closure__[index], "cell_contents", value)
        else:
            monkeypatch.setattr(api_module, name, value)


def _source_functions(name: str) -> list[tuple[str, ast.FunctionDef]]:
    matches: list[tuple[str, ast.FunctionDef]] = []
    for filename in ("api.py", "character_api_routes.py"):
        path = PROJECT_ROOT / "player_wiki" / filename
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        matches.extend(
            (filename, node)
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == name
        )
    return matches


@pytest.mark.parametrize(
    ("visibility", "actor", "expected_status"),
    (
        (None, None, 401),
        (None, "owner", 200),
        (None, "party", 403),
        (None, "observer", 403),
        (None, "outsider", 403),
        (None, "dm", 200),
        (None, "admin", 200),
        ("players", "owner", 200),
        ("players", "party", 200),
        ("players", "observer", 403),
        ("players", "outsider", 403),
        ("public", None, 200),
        ("public", "outsider", 200),
    ),
)
def test_character_detail_actor_visibility_and_assignment_matrix(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    visibility,
    actor,
    expected_status,
):
    if visibility is not None:
        set_campaign_visibility("linden-pass", characters=visibility)
    if actor is not None:
        sign_in(users[actor]["email"], users[actor]["password"])

    response = client.get(ROUTE_PATH)

    assert response.status_code == expected_status
    assert response.content_type.startswith("application/json")
    if expected_status == 401:
        assert response.get_json() == {
            "ok": False,
            "error": {
                "code": "auth_required",
                "message": "Authentication required.",
            },
        }
    elif expected_status == 403:
        assert response.get_json() == {
            "ok": False,
            "error": {
                "code": "forbidden",
                "message": "You do not have access to this character.",
            },
        }
    else:
        payload = response.get_json()
        assert payload["ok"] is True
        assert payload["character"]["definition"]["character_slug"] == "arden-march"


def test_character_detail_session_and_combat_assignment_override_is_bounded(
    client,
    sign_in,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility(
        "linden-pass",
        characters="dm",
        session="players",
        combat="players",
    )
    sign_in(users["owner"]["email"], users["owner"]["password"])
    assert client.get(ROUTE_PATH).status_code == 200

    sign_in(users["party"]["email"], users["party"]["password"])
    denied = client.get(ROUTE_PATH)
    assert denied.status_code == 403
    assert denied.get_json()["error"]["code"] == "forbidden"

    set_campaign_visibility("linden-pass", characters="players", session="dm", combat="dm")
    assert client.get(ROUTE_PATH).status_code == 200


def test_character_detail_view_as_uses_effective_actor_for_scope_and_assignment(
    client,
    sign_in,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility(
        "linden-pass",
        characters="dm",
        session="players",
        combat="players",
    )
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["owner"]["id"]
    assert client.get(ROUTE_PATH).status_code == 200

    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    denied = client.get(ROUTE_PATH)
    assert denied.status_code == 403
    assert denied.get_json()["error"]["code"] == "forbidden"

    set_campaign_visibility("linden-pass", characters="players")
    assert client.get(ROUTE_PATH).status_code == 200


@pytest.mark.parametrize("identity", ("browser", "bearer"))
def test_character_detail_browser_session_and_bearer_identity_match(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    identity,
):
    set_campaign_visibility("linden-pass", characters="players")
    headers = None
    if identity == "browser":
        sign_in(users["owner"]["email"], users["owner"]["password"])
    else:
        token = issue_api_token(app, users["owner"]["email"], label="p28-character-detail")
        headers = api_headers(token)

    response = client.get(ROUTE_PATH, headers=headers)

    assert response.status_code == 200
    assert response.get_json()["character"]["definition"]["character_slug"] == "arden-march"


@pytest.mark.parametrize(
    ("actor", "expected_status"),
    ((None, 401), ("dm", 403)),
)
def test_character_detail_missing_campaign_keeps_actor_specific_helper_order(
    client,
    sign_in,
    users,
    actor,
    expected_status,
):
    if actor is not None:
        sign_in(users[actor]["email"], users[actor]["password"])
    response = client.get("/api/v1/campaigns/missing-campaign/characters/arden-march")
    assert response.status_code == expected_status


def test_character_detail_missing_campaign_admin_reaches_record_loader_fault(
    client,
    sign_in,
    users,
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    with pytest.raises(FileNotFoundError, match="Campaign config not found"):
        client.get("/api/v1/campaigns/missing-campaign/characters/arden-march")


def test_character_detail_missing_record_precedes_explicit_campaign_lookup(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    events: list[str] = []

    def missing_record(campaign_slug, character_slug):
        events.append("record")
        from flask import abort

        abort(404)

    def forbidden_repository():
        events.append("repository")
        raise AssertionError("campaign lookup must follow the record load")

    _install_dependencies(
        app,
        monkeypatch,
        load_character_record=missing_record,
        get_repository=forbidden_repository,
    )

    response = client.get("/api/v1/campaigns/linden-pass/characters/missing")

    assert response.status_code == 404
    assert events == ["record"]


def test_character_detail_exact_dependency_order_counts_and_payload(
    app,
    client,
    monkeypatch,
):
    events: list[object] = []
    actor = SimpleNamespace(id=7)
    record = SimpleNamespace(slug="arden-march")
    campaign = SimpleNamespace(slug="linden-pass")

    def scope(campaign_slug, scope_name):
        events.append(("scope", campaign_slug, scope_name))
        return False

    def session(campaign_slug, character_slug):
        events.append(("session", campaign_slug, character_slug))
        return True

    def current_user():
        events.append("user")
        return actor

    def load(campaign_slug, character_slug):
        events.append(("record", campaign_slug, character_slug))
        return record

    class Repository:
        def get_campaign(self, campaign_slug):
            events.append(("campaign", campaign_slug))
            return campaign

    def repository():
        events.append("repository")
        return Repository()

    def serialize_record(campaign_slug, current_record):
        events.append(("serialize_record", campaign_slug, current_record))
        return {"slug": current_record.slug}

    def serialize_links(campaign_slug, current_campaign, current_record):
        events.append(("serialize_links", campaign_slug, current_campaign, current_record))
        return {"self": "/character"}

    _install_dependencies(
        app,
        monkeypatch,
        can_access_campaign_scope=scope,
        has_session_mode_access=session,
        get_current_user=current_user,
        load_character_record=load,
        get_repository=repository,
        serialize_character_record=serialize_record,
        serialize_character_links=serialize_links,
    )

    response = client.get(ROUTE_PATH)

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "character": {"slug": "arden-march"},
        "links": {"self": "/character"},
    }
    assert events == [
        ("scope", "linden-pass", "characters"),
        ("session", "linden-pass", "arden-march"),
        ("record", "linden-pass", "arden-march"),
        "repository",
        ("campaign", "linden-pass"),
        ("serialize_record", "linden-pass", record),
        ("serialize_links", "linden-pass", campaign, record),
    ]


@pytest.mark.parametrize(
    ("actor", "expected_status", "expected_code"),
    ((None, 401, "auth_required"), (SimpleNamespace(id=4), 403, "forbidden")),
)
def test_character_detail_denial_has_no_eager_record_campaign_or_serialization_work(
    app,
    client,
    monkeypatch,
    actor,
    expected_status,
    expected_code,
):
    events: list[str] = []

    def scope(*args):
        events.append("scope")
        return False

    def session(*args):
        events.append("session")
        return False

    def current_user():
        events.append("user")
        return actor

    def eager(*args):
        events.append("eager")
        raise AssertionError("denial performed eager work")

    _install_dependencies(
        app,
        monkeypatch,
        can_access_campaign_scope=scope,
        has_session_mode_access=session,
        get_current_user=current_user,
        load_character_record=eager,
        get_repository=eager,
        serialize_character_record=eager,
        serialize_character_links=eager,
    )

    response = client.get(ROUTE_PATH)

    assert response.status_code == expected_status
    assert response.get_json()["error"]["code"] == expected_code
    assert events == ["scope", "session", "user"]


def test_character_detail_scope_success_short_circuits_assignment_and_user_checks(
    app,
    client,
    monkeypatch,
):
    events: list[str] = []
    record = SimpleNamespace(slug="arden-march")
    campaign = SimpleNamespace(slug="linden-pass")

    def scope(*args):
        events.append("scope")
        return True

    def forbidden(*args):
        events.append("forbidden")
        raise AssertionError("short-circuited dependency ran")

    _install_dependencies(
        app,
        monkeypatch,
        can_access_campaign_scope=scope,
        has_session_mode_access=forbidden,
        get_current_user=forbidden,
        load_character_record=lambda *args: record,
        get_repository=lambda: SimpleNamespace(get_campaign=lambda slug: campaign),
        serialize_character_record=lambda *args: {"slug": "arden-march"},
        serialize_character_links=lambda *args: {},
    )

    response = client.get(ROUTE_PATH)

    assert response.status_code == 200
    assert events == ["scope"]


def test_character_detail_explicit_missing_campaign_precedes_serializers(
    app,
    client,
    monkeypatch,
):
    events: list[str] = []

    def record(*args):
        events.append("record")
        return SimpleNamespace(slug="arden-march")

    class Repository:
        def get_campaign(self, slug):
            events.append("campaign")
            return None

    def forbidden(*args):
        events.append("serialize")
        raise AssertionError("serializer ran after missing campaign")

    _install_dependencies(
        app,
        monkeypatch,
        can_access_campaign_scope=lambda *args: True,
        load_character_record=record,
        get_repository=lambda: Repository(),
        serialize_character_record=forbidden,
        serialize_character_links=forbidden,
    )

    response = client.get(ROUTE_PATH)

    assert response.status_code == 404
    assert events == ["record", "campaign"]


def test_character_detail_get_head_options_and_disallowed_methods(
    app,
    client,
    monkeypatch,
):
    calls: list[str] = []
    record = SimpleNamespace(slug="arden-march")
    campaign = SimpleNamespace(slug="linden-pass")

    def load(*args):
        calls.append("load")
        return record

    _install_dependencies(
        app,
        monkeypatch,
        can_access_campaign_scope=lambda *args: True,
        load_character_record=load,
        get_repository=lambda: SimpleNamespace(get_campaign=lambda slug: campaign),
        serialize_character_record=lambda *args: {"slug": "arden-march"},
        serialize_character_links=lambda *args: {},
    )

    get_response = client.get(ROUTE_PATH)
    head_response = client.head(ROUTE_PATH)
    options_response = client.options(ROUTE_PATH)
    post_response = client.post(ROUTE_PATH)

    assert get_response.status_code == 200
    assert get_response.content_type.startswith("application/json")
    assert head_response.status_code == 200
    assert head_response.data == b""
    assert options_response.status_code == 200
    assert set(options_response.headers["Allow"].replace(" ", "").split(",")) == {
        "GET",
        "HEAD",
        "OPTIONS",
    }
    assert post_response.status_code == 405
    assert calls == ["load", "load"]


@pytest.mark.parametrize(
    "fault_name",
    (
        "can_access_campaign_scope",
        "has_session_mode_access",
        "get_current_user",
        "load_character_record",
        "get_repository",
        "serialize_character_record",
        "serialize_character_links",
    ),
)
def test_character_detail_dependency_faults_propagate_without_retry(
    app,
    client,
    monkeypatch,
    fault_name,
):
    calls: list[str] = []
    record = SimpleNamespace(slug="arden-march")
    campaign = SimpleNamespace(slug="linden-pass")

    def fault(*args):
        calls.append(fault_name)
        raise RuntimeError(f"{fault_name} fault")

    replacements = {
        "can_access_campaign_scope": lambda *args: False,
        "has_session_mode_access": lambda *args: False,
        "get_current_user": lambda: SimpleNamespace(id=1),
        "load_character_record": lambda *args: record,
        "get_repository": lambda: SimpleNamespace(get_campaign=lambda slug: campaign),
        "serialize_character_record": lambda *args: {"slug": "arden-march"},
        "serialize_character_links": lambda *args: {},
    }
    replacements[fault_name] = fault
    if fault_name in {
        "load_character_record",
        "get_repository",
        "serialize_character_record",
        "serialize_character_links",
    }:
        replacements["has_session_mode_access"] = lambda *args: True
    _install_dependencies(app, monkeypatch, **replacements)

    with pytest.raises(RuntimeError, match=f"{fault_name} fault"):
        client.get(ROUTE_PATH)

    assert calls == [fault_name]


def test_character_detail_dnd_and_xianxia_serializers_remain_system_driven(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    dnd = client.get(ROUTE_PATH)
    assert dnd.status_code == 200
    dnd_character = dnd.get_json()["character"]
    assert dnd_character["definition"]["character_slug"] == "arden-march"
    assert "presented_xianxia" not in dnd_character or not dnd_character["presented_xianxia"]

    _configure_xianxia_campaign(app)
    created = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("P28 API Crane"),
        follow_redirects=False,
    )
    assert created.status_code == 302
    xianxia = client.get("/api/v1/campaigns/linden-pass/characters/p28-api-crane")
    assert xianxia.status_code == 200
    xianxia_character = xianxia.get_json()["character"]
    assert xianxia_character["definition"]["character_slug"] == "p28-api-crane"
    assert xianxia_character["presented_xianxia"]["system_label"] == "Xianxia"


def test_character_detail_endpoint_order_manifest_and_policy_contract(app):
    rules = [rule for rule in app.url_map.iter_rules() if rule.endpoint == ENDPOINT]
    assert len(rules) == 1
    rule = rules[0]
    assert rule.rule == "/api/v1/campaigns/<campaign_slug>/characters/<character_slug>"
    assert rule.methods == {"GET", "HEAD", "OPTIONS"}
    assert app.view_functions[ENDPOINT].__name__ == "character_detail"

    endpoints = [registered.endpoint for registered in app.url_map.iter_rules()]
    assert endpoints.index("api.character_xianxia_manual_import_submit") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index("api.character_controls_assignment_update")

    manifest = json.loads(
        (PROJECT_ROOT / "docs/contracts/route-api-role-visibility-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    entries = [
        entry
        for entry in manifest["entries"]
        if entry["endpoint"] == ENDPOINT and entry["method"] == "GET"
    ]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["owning_domain"] == "characters"
    assert entry["authentication_policy"] == "optional_identity"
    assert entry["access_policy"] == "character_read_api"
    assert entry["visibility_policy"] == "character_scope_with_assignment_override"
    assert entry["object_relationship_requirement"] == "visible_character_or_assignment"
    assert entry["system_restriction"] == "none"
    assert entry["view_as_policy"] == "campaign_safe_reads_use_effective_actor"

    policies = json.loads(
        (PROJECT_ROOT / "docs/contracts/route-access-policies.json").read_text(encoding="utf-8")
    )
    assert policies["endpoints"][ENDPOINT] == {
        "profile": "character_read_api",
        "owning_domain": "characters",
    }


def test_character_detail_has_one_source_handler():
    matches = _source_functions("character_detail")
    assert len(matches) == 1


def test_character_detail_module_globals_remain_post_registration_monkeypatchable(
    app,
    client,
    monkeypatch,
):
    events: list[str] = []
    record = SimpleNamespace(slug="arden-march")
    campaign = SimpleNamespace(slug="linden-pass")

    monkeypatch.setattr(api_module, "can_access_campaign_scope", lambda *args: True)
    monkeypatch.setattr(
        api_module,
        "has_session_mode_access",
        lambda *args: events.append("unexpected-session") or False,
    )
    monkeypatch.setattr(
        api_module,
        "get_current_user",
        lambda: events.append("unexpected-user") or None,
    )
    monkeypatch.setattr(
        api_module,
        "get_repository",
        lambda: SimpleNamespace(get_campaign=lambda slug: campaign),
    )
    _install_dependencies(
        app,
        monkeypatch,
        load_character_record=lambda *args: record,
        serialize_character_record=lambda *args: {"slug": "arden-march"},
        serialize_character_links=lambda *args: {},
    )

    response = client.get(ROUTE_PATH)

    assert response.status_code == 200
    assert events == []


def test_character_detail_is_explicitly_registered_after_extraction():
    path = PROJECT_ROOT / "player_wiki" / "character_api_routes.py"
    if not path.exists():
        pytest.skip("explicit registration applies after extraction")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    registrations = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_url_rule"
    ]
    assert len(registrations) == 1
    assert _source_functions("character_detail")[0][0] == "character_api_routes.py"
