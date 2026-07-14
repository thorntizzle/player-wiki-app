from __future__ import annotations

import ast
from dataclasses import replace
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import player_wiki.api as api_module
from player_wiki.auth import VIEW_AS_SESSION_KEY
from tests.helpers.api_test_helpers import api_headers, issue_api_token


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "api.character_list"
ROUTE_PATH = "/api/v1/campaigns/linden-pass/characters"


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

    closure_names = {
        "get_owned_character_slugs",
        "json_error",
        "get_character_repository",
        "serialize_character_summary",
        "serialize_campaign",
        "serialize_character_roster_tools",
        "serialize_character_roster_links",
    }
    for name, value in replacements.items():
        if name in closure_names:
            index = raw_view.__code__.co_freevars.index(name)
            monkeypatch.setattr(raw_view.__closure__[index], "cell_contents", value)
        else:
            monkeypatch.setattr(api_module, name, value)


def _source_functions(name: str) -> list[tuple[str, ast.FunctionDef]]:
    matches: list[tuple[str, ast.FunctionDef]] = []
    for filename in ("api.py", "character_list_api_routes.py"):
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
    ("visibility", "actor", "expected_status", "expected_slugs"),
    (
        (None, None, 401, None),
        (None, "owner", 200, ["arden-march"]),
        (None, "party", 403, None),
        (None, "observer", 403, None),
        (None, "outsider", 403, None),
        (None, "dm", 200, ["arden-march", "selene-brook", "tobin-slate"]),
        (None, "admin", 200, ["arden-march", "selene-brook", "tobin-slate"]),
        ("players", "owner", 200, ["arden-march", "selene-brook", "tobin-slate"]),
        ("players", "party", 200, ["arden-march", "selene-brook", "tobin-slate"]),
        ("players", "observer", 403, None),
        ("players", "outsider", 403, None),
        ("public", None, 200, ["arden-march", "selene-brook", "tobin-slate"]),
        ("public", "outsider", 200, ["arden-march", "selene-brook", "tobin-slate"]),
    ),
)
def test_character_list_actor_visibility_and_assignment_matrix(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    visibility,
    actor,
    expected_status,
    expected_slugs,
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
                "message": "You do not have access to campaign characters.",
            },
        }
    else:
        assert [card["slug"] for card in response.get_json()["characters"]] == expected_slugs


def test_character_list_view_as_uses_effective_actor_for_scope_and_assignment(
    client,
    sign_in,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility("linden-pass", characters="dm")
    sign_in(users["admin"]["email"], users["admin"]["password"])

    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["owner"]["id"]
    owner = client.get(ROUTE_PATH)
    assert owner.status_code == 200
    assert [card["slug"] for card in owner.get_json()["characters"]] == ["arden-march"]

    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    denied = client.get(ROUTE_PATH)
    assert denied.status_code == 403
    assert denied.get_json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("identity", ("browser", "bearer"))
def test_character_list_browser_and_bearer_assignment_projection_match(
    app,
    client,
    sign_in,
    users,
    identity,
):
    headers = None
    if identity == "browser":
        sign_in(users["owner"]["email"], users["owner"]["password"])
    else:
        token = issue_api_token(app, users["owner"]["email"], label="p30-character-list")
        headers = api_headers(token)

    response = client.get(ROUTE_PATH, headers=headers)

    assert response.status_code == 200
    assert [card["slug"] for card in response.get_json()["characters"]] == ["arden-march"]


def test_character_list_missing_or_inactive_owned_slug_authorizes_empty_projection(
    app,
    client,
    monkeypatch,
):
    record = SimpleNamespace(definition=SimpleNamespace(character_slug="active-character"))
    _install_dependencies(
        app,
        monkeypatch,
        can_access_campaign_scope=lambda *args: False,
        get_owned_character_slugs=lambda slug: {"missing-or-inactive"},
        get_character_repository=lambda: SimpleNamespace(
            list_visible_characters=lambda slug: [record]
        ),
        serialize_character_summary=lambda *args: pytest.fail(
            "a non-owned visible record must not be serialized"
        ),
        serialize_campaign=lambda campaign: {"slug": campaign.slug},
        serialize_character_roster_tools=lambda *args: {},
        serialize_character_roster_links=lambda *args: {},
    )

    response = client.get(ROUTE_PATH)

    assert response.status_code == 200
    assert response.get_json()["characters"] == []
    assert response.get_json()["result_count"] == 0


@pytest.mark.parametrize("system", ("dnd-5e", "xianxia", "unsupported-system"))
def test_character_list_exact_order_query_and_system_passthrough(
    app,
    client,
    monkeypatch,
    system,
):
    events: list[object] = []
    campaign = SimpleNamespace(slug="linden-pass", system=system)
    alpha = SimpleNamespace(definition=SimpleNamespace(character_slug="alpha"))
    bravo = SimpleNamespace(definition=SimpleNamespace(character_slug="bravo"))

    class Repository:
        def get_campaign(self, slug):
            events.append(("campaign", slug))
            return campaign

    class CharacterRepository:
        def list_visible_characters(self, slug):
            events.append(("records", slug))
            return [alpha, bravo]

    def tools(slug, current_campaign):
        events.append(("tools", slug, current_campaign.system))
        return {"system": current_campaign.system}

    def links(slug, current_campaign):
        nested_tools = tools(slug, current_campaign)
        events.append(("links", slug, current_campaign.system))
        return {"system": nested_tools["system"]}

    _install_dependencies(
        app,
        monkeypatch,
        get_repository=lambda: events.append("repository") or Repository(),
        can_access_campaign_scope=lambda slug, scope: events.append(
            ("scope", slug, scope)
        )
        or True,
        get_owned_character_slugs=lambda slug: events.append(("owned", slug)) or {"alpha"},
        get_current_user=lambda: pytest.fail("scope access must skip the denial user check"),
        get_character_repository=lambda: events.append("character_repository")
        or CharacterRepository(),
        serialize_character_summary=lambda current_campaign, record: events.append(
            ("summary", record.definition.character_slug, current_campaign.system)
        )
        or {
            "slug": record.definition.character_slug,
            "search_text": record.definition.character_slug,
        },
        serialize_campaign=lambda current_campaign: events.append(
            ("serialize_campaign", current_campaign.system)
        )
        or {"slug": current_campaign.slug, "system": current_campaign.system},
        serialize_character_roster_tools=tools,
        serialize_character_roster_links=links,
    )

    response = client.get(f"{ROUTE_PATH}?q=%20AlP%20")

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "campaign": {"slug": "linden-pass", "system": system},
        "characters": [{"slug": "alpha", "search_text": "alpha"}],
        "query": "AlP",
        "result_count": 1,
        "tools": {"system": system},
        "links": {"system": system},
    }
    assert events == [
        "repository",
        ("campaign", "linden-pass"),
        ("scope", "linden-pass", "characters"),
        ("owned", "linden-pass"),
        "character_repository",
        ("records", "linden-pass"),
        ("summary", "alpha", system),
        ("summary", "bravo", system),
        ("serialize_campaign", system),
        ("tools", "linden-pass", system),
        ("tools", "linden-pass", system),
        ("links", "linden-pass", system),
    ]


@pytest.mark.parametrize(
    ("actor", "expected_status", "expected_code"),
    ((None, 401, "auth_required"), (SimpleNamespace(id=4), 403, "forbidden")),
)
def test_character_list_denial_has_no_eager_record_or_payload_work(
    app,
    client,
    monkeypatch,
    actor,
    expected_status,
    expected_code,
):
    events: list[str] = []
    campaign = SimpleNamespace(slug="linden-pass")

    def eager(*args):
        events.append("eager")
        raise AssertionError("denial performed eager character or payload work")

    _install_dependencies(
        app,
        monkeypatch,
        get_repository=lambda: SimpleNamespace(get_campaign=lambda slug: campaign),
        can_access_campaign_scope=lambda *args: events.append("scope") or False,
        get_owned_character_slugs=lambda *args: events.append("owned") or set(),
        get_current_user=lambda: events.append("user") or actor,
        get_character_repository=eager,
        serialize_character_summary=eager,
        serialize_campaign=eager,
        serialize_character_roster_tools=eager,
        serialize_character_roster_links=eager,
    )

    response = client.get(ROUTE_PATH)

    assert response.status_code == expected_status
    assert response.get_json()["error"]["code"] == expected_code
    assert events == ["scope", "owned", "user"]


def test_character_list_missing_campaign_precedes_authorization_and_payload_work(
    app,
    client,
    monkeypatch,
):
    events: list[str] = []

    class Repository:
        def get_campaign(self, slug):
            events.append("campaign")
            return None

    def eager(*args):
        events.append("eager")
        raise AssertionError("missing campaign performed eager work")

    _install_dependencies(
        app,
        monkeypatch,
        get_repository=lambda: events.append("repository") or Repository(),
        can_access_campaign_scope=eager,
        get_owned_character_slugs=eager,
        get_current_user=eager,
        get_character_repository=eager,
        serialize_character_summary=eager,
        serialize_campaign=eager,
        serialize_character_roster_tools=eager,
        serialize_character_roster_links=eager,
    )

    response = client.get("/api/v1/campaigns/missing-campaign/characters")

    assert response.status_code == 404
    assert events == ["repository", "campaign"]


def test_character_list_get_head_options_and_disallowed_methods(app, client, monkeypatch):
    calls: list[str] = []
    campaign = SimpleNamespace(slug="linden-pass")
    _install_dependencies(
        app,
        monkeypatch,
        get_repository=lambda: SimpleNamespace(get_campaign=lambda slug: campaign),
        can_access_campaign_scope=lambda *args: True,
        get_owned_character_slugs=lambda slug: calls.append("owned") or set(),
        get_character_repository=lambda: SimpleNamespace(
            list_visible_characters=lambda slug: calls.append("records") or []
        ),
        serialize_campaign=lambda current_campaign: {},
        serialize_character_roster_tools=lambda *args: {},
        serialize_character_roster_links=lambda *args: {},
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
    assert calls == ["owned", "records", "owned", "records"]


@pytest.mark.parametrize(
    "fault_name",
    (
        "get_repository",
        "can_access_campaign_scope",
        "get_owned_character_slugs",
        "get_current_user",
        "json_error",
        "get_character_repository",
        "serialize_character_summary",
        "serialize_campaign",
        "serialize_character_roster_tools",
        "serialize_character_roster_links",
    ),
)
def test_character_list_dependency_faults_propagate_without_retry(
    app,
    client,
    monkeypatch,
    fault_name,
):
    calls: list[str] = []
    campaign = SimpleNamespace(slug="linden-pass")
    record = SimpleNamespace(definition=SimpleNamespace(character_slug="arden-march"))

    def fault(*args, **kwargs):
        calls.append(fault_name)
        raise RuntimeError(f"{fault_name} fault")

    denial_fault = fault_name in {"get_current_user", "json_error"}
    replacements = {
        "get_repository": lambda: SimpleNamespace(get_campaign=lambda slug: campaign),
        "can_access_campaign_scope": lambda *args: not denial_fault,
        "get_owned_character_slugs": lambda slug: set(),
        "get_current_user": lambda: None,
        "json_error": lambda *args, **kwargs: ({"ok": False}, 401),
        "get_character_repository": lambda: SimpleNamespace(
            list_visible_characters=lambda slug: [record]
        ),
        "serialize_character_summary": lambda *args: {
            "slug": "arden-march",
            "search_text": "arden",
        },
        "serialize_campaign": lambda *args: {},
        "serialize_character_roster_tools": lambda *args: {},
        "serialize_character_roster_links": lambda *args: {},
    }
    replacements[fault_name] = fault
    _install_dependencies(app, monkeypatch, **replacements)

    with pytest.raises(RuntimeError, match=f"{fault_name} fault"):
        client.get(ROUTE_PATH)

    assert calls == [fault_name]


def test_character_list_endpoint_order_manifest_and_policy_contract(app):
    rules = [rule for rule in app.url_map.iter_rules() if rule.endpoint == ENDPOINT]
    assert len(rules) == 1
    rule = rules[0]
    assert rule.rule == "/api/v1/campaigns/<campaign_slug>/characters"
    assert rule.methods == {"GET", "HEAD", "OPTIONS"}
    assert app.view_functions[ENDPOINT].__name__ == "character_list"

    endpoints = [registered.endpoint for registered in app.url_map.iter_rules()]
    assert endpoints.index("api.combat_combatant_delete") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index("api.character_create_context")

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


def test_character_list_has_one_source_handler():
    assert len(_source_functions("character_list")) == 1


def test_character_list_module_globals_remain_post_registration_monkeypatchable(
    app,
    client,
    monkeypatch,
):
    events: list[str] = []
    campaign = SimpleNamespace(slug="linden-pass")
    monkeypatch.setattr(
        api_module,
        "get_repository",
        lambda: events.append("repository")
        or SimpleNamespace(get_campaign=lambda slug: campaign),
    )
    monkeypatch.setattr(
        api_module,
        "can_access_campaign_scope",
        lambda *args: events.append("scope") or True,
    )
    monkeypatch.setattr(
        api_module,
        "get_current_user",
        lambda: pytest.fail("authorized request must not inspect current user directly"),
    )
    _install_dependencies(
        app,
        monkeypatch,
        get_owned_character_slugs=lambda slug: events.append("owned") or set(),
        get_character_repository=lambda: SimpleNamespace(list_visible_characters=lambda slug: []),
        serialize_campaign=lambda campaign: {},
        serialize_character_roster_tools=lambda *args: {},
        serialize_character_roster_links=lambda *args: {},
    )

    response = client.get(ROUTE_PATH)

    assert response.status_code == 200
    assert events == ["repository", "scope", "owned"]


def test_character_list_is_explicitly_registered_after_extraction():
    path = PROJECT_ROOT / "player_wiki" / "character_list_api_routes.py"
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
    assert _source_functions("character_list")[0][0] == "character_list_api_routes.py"
