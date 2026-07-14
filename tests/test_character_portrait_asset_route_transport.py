from __future__ import annotations

import ast
from dataclasses import replace
import importlib
import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import request

from player_wiki.auth import VIEW_AS_SESSION_KEY


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "character_portrait_asset"
ROUTE_PATH = "/campaigns/linden-pass/characters/arden-march/portrait"


def _install_dependencies(
    app,
    monkeypatch,
    *,
    load_character_context=None,
    build_character_portrait_context=None,
    get_campaign_asset_file=None,
) -> None:
    raw_view = inspect.unwrap(app.view_functions[ENDPOINT])
    dependencies = app.extensions.get("character_portrait_asset_route_dependencies")
    replacements = {
        "load_character_context": load_character_context,
        "build_character_portrait_context": build_character_portrait_context,
        "get_campaign_asset_file": get_campaign_asset_file,
    }
    if dependencies is not None:
        monkeypatch.setitem(
            app.extensions,
            "character_portrait_asset_route_dependencies",
            replace(
                dependencies,
                **{
                    name: value
                    for name, value in replacements.items()
                    if value is not None
                },
            ),
        )
        return

    for name, value in replacements.items():
        if value is None:
            continue
        closure_index = raw_view.__code__.co_freevars.index(name)
        monkeypatch.setattr(raw_view.__closure__[closure_index], "cell_contents", value)


def _source_function(name: str) -> tuple[str, ast.FunctionDef]:
    matches: list[tuple[str, ast.FunctionDef]] = []
    for filename in ("app.py", "character_routes.py"):
        tree = ast.parse((PROJECT_ROOT / "player_wiki" / filename).read_text(encoding="utf-8"))
        matches.extend(
            (filename, node)
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == name
        )
    assert len(matches) == 1
    return matches[0]


def _asset_dependencies(app):
    dependencies = app.extensions.get("character_portrait_asset_route_dependencies")
    if dependencies is not None:
        return dependencies
    raw_view = inspect.unwrap(app.view_functions[ENDPOINT])
    return SimpleNamespace(
        **{
            name: raw_view.__closure__[raw_view.__code__.co_freevars.index(name)].cell_contents
            for name in (
                "load_character_context",
                "build_character_portrait_context",
                "get_campaign_asset_file",
            )
        }
    )


def _portrait_context(asset_ref: str = "characters/arden-march/portrait.png") -> dict[str, str]:
    return {
        "asset_ref": asset_ref,
        "url": ROUTE_PATH,
        "alt": "Arden",
        "caption": "Portrait",
    }


def _install_served_asset(app, monkeypatch, tmp_path, *, payload=b"portrait-bytes"):
    campaign = SimpleNamespace(slug="linden-pass", assets_dir=tmp_path / "assets")
    definition = SimpleNamespace(character_slug="arden-march", system="DND-5E")
    asset_file = tmp_path / "served" / "arden-final.png"
    asset_file.parent.mkdir(parents=True)
    asset_file.write_bytes(payload)
    calls: list[tuple[object, ...]] = []

    def load(campaign_slug, character_slug):
        calls.append(("load", campaign_slug, character_slug))
        return campaign, SimpleNamespace(definition=definition)

    def resolve(current_campaign, asset_ref):
        calls.append(("resolve", current_campaign, asset_ref))
        return asset_file

    def build(current_campaign, current_definition):
        calls.append(("build", current_campaign, current_definition))
        # Preserve the shipped first validation resolution inside the context builder.
        assert resolve(current_campaign, "characters/arden-march/portrait.png") is asset_file
        return _portrait_context()

    _install_dependencies(
        app,
        monkeypatch,
        load_character_context=load,
        build_character_portrait_context=build,
        get_campaign_asset_file=resolve,
    )
    return asset_file, calls


@pytest.mark.parametrize(
    ("visibility", "actor", "expected_status", "expected_loads"),
    (
        (None, "owner", 404, 0),
        (None, "party", 404, 0),
        (None, "observer", 404, 0),
        (None, "outsider", 404, 0),
        (None, "dm", 200, 1),
        (None, "admin", 200, 1),
        ("players", "owner", 200, 1),
        ("players", "party", 200, 1),
        ("players", "observer", 404, 0),
        ("players", "outsider", 404, 0),
        ("public", "observer", 200, 1),
        ("public", "outsider", 200, 1),
        ("public", None, 200, 1),
    ),
)
def test_portrait_asset_actor_visibility_and_assignment_non_bypass(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    monkeypatch,
    tmp_path,
    visibility,
    actor,
    expected_status,
    expected_loads,
):
    if visibility is not None:
        set_campaign_visibility("linden-pass", characters=visibility)
    if actor is not None:
        sign_in(users[actor]["email"], users[actor]["password"])
    _, calls = _install_served_asset(app, monkeypatch, tmp_path)

    response = client.get(ROUTE_PATH)

    assert response.status_code == expected_status
    assert sum(call[0] == "load" for call in calls) == expected_loads
    if expected_loads:
        assert response.data == b"portrait-bytes"
        assert [call[0] for call in calls] == ["load", "build", "resolve", "resolve"]


def test_portrait_asset_optional_identity_view_as_and_missing_order(
    app, client, sign_in, users, set_campaign_visibility, monkeypatch, tmp_path
):
    _, calls = _install_served_asset(app, monkeypatch, tmp_path)

    anonymous = client.get(f"{ROUTE_PATH}?download=visible", follow_redirects=False)
    assert anonymous.status_code == 302
    assert anonymous.headers["Location"].endswith(
        "/sign-in?next=/campaigns/linden-pass/characters/arden-march/portrait?download%3Dvisible"
    )
    missing_campaign = client.get(
        "/campaigns/missing-campaign/characters/arden-march/portrait",
        follow_redirects=False,
    )
    assert missing_campaign.status_code == 404
    assert calls == []

    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    calls.clear()
    denied = client.get(ROUTE_PATH)
    assert denied.status_code == 404
    assert all(call[0] not in {"load", "build"} for call in calls)

    set_campaign_visibility("linden-pass", characters="players")
    calls.clear()
    allowed = client.get(ROUTE_PATH)
    assert allowed.status_code == 200
    assert sum(call[0] == "load" for call in calls) == 1


def test_portrait_asset_missing_character_is_after_scope_authorization(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    calls: list[tuple[str, str]] = []

    def load(campaign_slug, character_slug):
        calls.append((campaign_slug, character_slug))
        from flask import abort

        abort(404)

    _install_dependencies(app, monkeypatch, load_character_context=load)
    response = client.get("/campaigns/linden-pass/characters/missing-character/portrait")
    assert response.status_code == 404
    assert calls == [("linden-pass", "missing-character")]


@pytest.mark.parametrize("system", ("DND-5E", "Xianxia"))
def test_portrait_asset_has_no_system_gate_and_preserves_two_resolutions(
    app, client, sign_in, users, monkeypatch, tmp_path, system
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    campaign = SimpleNamespace(slug="linden-pass")
    record = SimpleNamespace(definition=SimpleNamespace(character_slug="arden-march", system=system))
    first = tmp_path / "first.png"
    second = tmp_path / "second.webp"
    first.write_bytes(b"first")
    second.write_bytes(b"second-wins")
    events: list[tuple[object, ...]] = []

    def load(campaign_slug, character_slug):
        events.append(("load", campaign_slug, character_slug))
        return campaign, record

    def resolve(current_campaign, asset_ref):
        events.append(("resolve", current_campaign, asset_ref))
        return first if sum(event[0] == "resolve" for event in events) == 1 else second

    def build(current_campaign, definition):
        events.append(("build", current_campaign, definition))
        assert resolve(current_campaign, "characters/arden-march/portrait.png") is first
        return _portrait_context()

    _install_dependencies(
        app,
        monkeypatch,
        load_character_context=load,
        build_character_portrait_context=build,
        get_campaign_asset_file=resolve,
    )
    response = client.get(ROUTE_PATH)

    assert response.status_code == 200
    assert response.data == b"second-wins"
    assert response.mimetype == "image/webp"
    assert [event[0] for event in events] == ["load", "build", "resolve", "resolve"]


@pytest.mark.parametrize("missing_stage", ("context", "second_resolution"))
def test_portrait_asset_missing_context_or_second_resolution_is_404(
    app, client, sign_in, users, monkeypatch, missing_stage
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    campaign = SimpleNamespace(slug="linden-pass")
    record = SimpleNamespace(definition=SimpleNamespace(character_slug="arden-march"))
    events: list[str] = []

    def load(campaign_slug, character_slug):
        events.append("load")
        return campaign, record

    def build(current_campaign, definition):
        events.append("build")
        return None if missing_stage == "context" else _portrait_context()

    def resolve(current_campaign, asset_ref):
        if current_campaign is not campaign:
            return None
        events.append("resolve")
        return None

    _install_dependencies(
        app,
        monkeypatch,
        load_character_context=load,
        build_character_portrait_context=build,
        get_campaign_asset_file=resolve,
    )
    response = client.get(ROUTE_PATH)
    assert response.status_code == 404
    assert events == (["load", "build"] if missing_stage == "context" else ["load", "build", "resolve"])


def test_portrait_asset_resolver_rejects_unsafe_refs_and_missing_files(app, tmp_path):
    dependencies = _asset_dependencies(app)
    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign is not None
        assets_root = Path(campaign.assets_dir)
        inside = assets_root / "characters" / "arden-march" / "portrait.png"
        inside.parent.mkdir(parents=True, exist_ok=True)
        inside.write_bytes(b"inside")
        outside = tmp_path / "outside.png"
        outside.write_bytes(b"outside")

        assert dependencies.get_campaign_asset_file(campaign, "characters/arden-march/portrait.png") == inside
        for asset_ref in (
            "",
            "missing.png",
            "../outside.png",
            "characters/../../outside.png",
            str(outside),
        ):
            assert dependencies.get_campaign_asset_file(campaign, asset_ref) is None


def test_portrait_asset_resolver_symlink_boundaries_are_capability_classified(app, tmp_path):
    dependencies = _asset_dependencies(app)
    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign is not None
        assets_root = Path(campaign.assets_dir)
        assets_root.mkdir(parents=True, exist_ok=True)
        inside_target = assets_root / "inside.png"
        inside_target.write_bytes(b"inside")
        outside_target = tmp_path / "outside.png"
        outside_target.write_bytes(b"outside")
        inside_link = assets_root / "inside-link.png"
        outside_link = assets_root / "outside-link.png"
        try:
            inside_link.symlink_to(inside_target)
            outside_link.symlink_to(outside_target)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"Windows symlink capability unavailable: {exc.__class__.__name__}")

        assert dependencies.get_campaign_asset_file(campaign, "inside-link.png") == inside_target
        assert dependencies.get_campaign_asset_file(campaign, "outside-link.png") is None


def test_portrait_asset_get_head_options_and_http_file_contract(
    app, client, sign_in, users, monkeypatch, tmp_path
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    asset_file, calls = _install_served_asset(
        app,
        monkeypatch,
        tmp_path,
        payload=b"0123456789abcdef",
    )
    os.utime(asset_file, (1_700_000_000, 1_700_000_000))

    get_response = client.get(f"{ROUTE_PATH}?visible=query")
    head_response = client.head(ROUTE_PATH)
    options_response = client.options(ROUTE_PATH)
    range_response = client.get(ROUTE_PATH, headers={"Range": "bytes=2-5"})
    invalid_range = client.get(ROUTE_PATH, headers={"Range": "bytes=99-100"})
    conditional = client.get(ROUTE_PATH, headers={"If-None-Match": get_response.headers["ETag"]})

    assert get_response.status_code == 200
    assert get_response.data == b"0123456789abcdef"
    assert get_response.mimetype == "image/png"
    assert get_response.headers["Content-Disposition"] == "inline; filename=arden-final.png"
    assert get_response.headers["Content-Length"] == "16"
    assert get_response.headers["ETag"]
    assert get_response.headers["Last-Modified"] == "Tue, 14 Nov 2023 22:13:20 GMT"
    assert get_response.headers["Cache-Control"] == "no-cache"
    assert head_response.status_code == 200
    assert head_response.data == b""
    assert head_response.headers["Content-Length"] == "16"
    assert options_response.status_code == 200
    assert set(options_response.headers["Allow"].replace(" ", "").split(",")) == {
        "GET", "HEAD", "OPTIONS"
    }
    assert range_response.status_code == 206
    assert range_response.data == b"2345"
    assert range_response.headers["Content-Range"] == "bytes 2-5/16"
    assert invalid_range.status_code == 416
    assert invalid_range.headers["Content-Range"] == "bytes */16"
    assert conditional.status_code == 304
    assert conditional.data == b""
    assert sum(call[0] == "load" for call in calls) == 5


def test_portrait_asset_guess_precedes_send_file_and_faults_propagate_without_retry(
    app, client, sign_in, users, monkeypatch, tmp_path
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    asset_file, dependency_calls = _install_served_asset(app, monkeypatch, tmp_path)
    raw_view = inspect.unwrap(app.view_functions[ENDPOINT])
    source_module = importlib.import_module(raw_view.__module__)
    events: list[tuple[object, ...]] = []

    def guess(file_path):
        events.append(("guess", file_path))
        return "image/p27"

    def send(file_path, **kwargs):
        events.append(("send", file_path, kwargs))
        raise RuntimeError("send file fault")

    monkeypatch.setattr(source_module, "guess_campaign_asset_media_type", guess)
    monkeypatch.setattr(source_module, "send_file", send)
    with pytest.raises(RuntimeError, match="send file fault"):
        client.get(ROUTE_PATH)

    assert [event[0] for event in events] == ["guess", "send"]
    assert events[0][1] == asset_file
    assert events[1][1] == asset_file
    assert events[1][2] == {"mimetype": "image/p27", "download_name": "arden-final.png"}
    assert [call[0] for call in dependency_calls] == ["load", "build", "resolve", "resolve"]


@pytest.mark.parametrize("fault_stage", ("load", "build", "first_resolve", "second_resolve", "guess"))
def test_portrait_asset_stage_faults_propagate_in_order_without_retry(
    app, client, sign_in, users, monkeypatch, tmp_path, fault_stage
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    campaign = SimpleNamespace(slug="linden-pass")
    record = SimpleNamespace(definition=SimpleNamespace(character_slug="arden-march"))
    asset_file = tmp_path / "portrait.png"
    asset_file.write_bytes(b"portrait")
    events: list[str] = []

    def fail(stage):
        events.append(stage)
        if fault_stage == stage:
            raise RuntimeError(f"{stage} fault")

    def load(campaign_slug, character_slug):
        fail("load")
        return campaign, record

    def resolve(current_campaign, asset_ref):
        stage = "first_resolve" if "first_resolve" not in events else "second_resolve"
        fail(stage)
        return asset_file

    def build(current_campaign, definition):
        fail("build")
        resolve(current_campaign, "characters/arden-march/portrait.png")
        return _portrait_context()

    _install_dependencies(
        app,
        monkeypatch,
        load_character_context=load,
        build_character_portrait_context=build,
        get_campaign_asset_file=resolve,
    )
    raw_view = inspect.unwrap(app.view_functions[ENDPOINT])
    source_module = importlib.import_module(raw_view.__module__)

    def guess(file_path):
        fail("guess")
        return "image/png"

    monkeypatch.setattr(source_module, "guess_campaign_asset_media_type", guess)
    with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
        client.get(ROUTE_PATH)
    assert events.count(fault_stage) == 1


def test_portrait_asset_endpoint_decorator_order_manifest_and_policy_are_exact(app):
    rules = list(app.url_map.iter_rules())
    matching_rules = [rule for rule in rules if rule.endpoint == ENDPOINT]
    assert len(matching_rules) == 1
    rule = matching_rules[0]
    assert rule.rule == "/campaigns/<campaign_slug>/characters/<character_slug>/portrait"
    assert rule.methods == {"GET", "HEAD", "OPTIONS"}
    assert app.view_functions[ENDPOINT].__name__ == ENDPOINT
    assert inspect.unwrap(app.view_functions[ENDPOINT]).__name__ == ENDPOINT
    endpoints = [registered.endpoint for registered in rules]
    assert endpoints.index("character_xianxia_dao_immolating_use_record") < endpoints.index(ENDPOINT)
    assert endpoints.index(ENDPOINT) < endpoints.index("character_personal_portrait")

    _, source_function = _source_function(ENDPOINT)
    decorators = [
        decorator
        for decorator in source_function.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Name)
        and decorator.func.id == "campaign_scope_access_required"
    ]
    assert len(decorators) == 1
    assert isinstance(decorators[0].args[0], ast.Constant)
    assert decorators[0].args[0].value == "characters"

    manifest = json.loads(
        (PROJECT_ROOT / "docs/contracts/route-api-role-visibility-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    entries = [
        entry for entry in manifest["entries"]
        if entry["endpoint"] == ENDPOINT and entry["method"] == "GET"
    ]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["owning_domain"] == "characters"
    assert entry["authentication_policy"] == "optional_identity"
    assert entry["access_policy"] == "character_read_browser"
    assert entry["campaign_scope"] == "characters"
    assert entry["visibility_policy"] == "campaign_scope"
    assert entry["object_relationship_requirement"] == "visible_character_in_characters_scope"
    assert entry["view_as_policy"] == "campaign_safe_reads_use_effective_actor"
