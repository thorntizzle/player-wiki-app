from __future__ import annotations

import ast
from dataclasses import fields
from io import BytesIO
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from PIL import Image

import player_wiki.app as app_module
import player_wiki.character_portrait_mutation_routes as portrait_routes
from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.character_repository import CharacterRepository
from tests.helpers.api_test_helpers import api_headers, issue_api_token


UPLOAD_ENDPOINT = "character_personal_portrait"
REMOVE_ENDPOINT = "character_personal_portrait_remove"
UPLOAD_PATH = "/campaigns/linden-pass/characters/arden-march/personal/portrait"
REMOVE_PATH = f"{UPLOAD_PATH}/remove"

# Small valid images used to keep the characterization independent of fixtures in
# the broader character lifecycle suite.
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDAT\x08\xd7c\xf8"
    b"\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_portrait_mutation_transport_has_exact_dependency_and_composition_shape() -> None:
    assert [
        field.name
        for field in fields(portrait_routes.CharacterPortraitMutationRouteDependencies)
    ] == [
        "load_character_context",
        "parse_expected_revision",
        "validate_character_portrait_upload",
        "finalize_character_definition_for_write",
        "redirect_to_character_mode",
        "has_session_mode_access",
        "get_current_user",
        "validate_character_portrait_text",
        "build_character_portrait_asset_ref",
        "update_character_portrait_profile",
        "build_managed_character_import_metadata",
        "merge_state_with_definition",
        "load_campaign_character_config",
        "write_yaml",
        "write_campaign_asset_file",
        "delete_campaign_asset_file",
    ]

    source_root = Path(__file__).resolve().parents[1] / "player_wiki"
    route_tree = ast.parse(
        (source_root / "character_portrait_mutation_routes.py").read_text(encoding="utf-8")
    )
    app_tree = ast.parse((source_root / "app.py").read_text(encoding="utf-8"))
    registrar = next(
        node
        for node in ast.walk(route_tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_character_portrait_mutation_routes"
    )
    assert {
        node.name for node in registrar.body if isinstance(node, ast.FunctionDef)
    } == {UPLOAD_ENDPOINT, REMOVE_ENDPOINT}
    assert all(
        next(
            node
            for node in ast.walk(route_tree)
            if isinstance(node, ast.FunctionDef) and node.name == endpoint
        ).decorator_list
        == []
        for endpoint in (UPLOAD_ENDPOINT, REMOVE_ENDPOINT)
    )
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name in {UPLOAD_ENDPOINT, REMOVE_ENDPOINT}
        for node in ast.walk(app_tree)
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
        for node in ast.walk(app_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "register_character_portrait_mutation_routes"
    )
    keyword_values = {keyword.arg: keyword.value for keyword in registrar_call.keywords}
    for name in (
        "load_character_context",
        "parse_expected_revision",
        "validate_character_portrait_upload",
        "finalize_character_definition_for_write",
        "redirect_to_character_mode",
    ):
        assert isinstance(keyword_values[name], ast.Name)
        assert keyword_values[name].id == name
    for name in set(keyword_values) - {
        "load_character_context",
        "parse_expected_revision",
        "validate_character_portrait_upload",
        "finalize_character_definition_for_write",
        "redirect_to_character_mode",
    }:
        assert isinstance(keyword_values[name], ast.Lambda)


def _revision(app) -> int:
    with app.app_context():
        record = app.extensions["character_repository"].get_character(
            "linden-pass", "arden-march"
        )
        assert record is not None
        return record.state_record.revision


def _raw_handler(app, endpoint: str):
    return inspect.unwrap(app.view_functions[endpoint])


def _upload(client, revision: int, **overrides):
    data = {
        "expected_revision": revision,
        "mode": "read",
        "page": "portrait",
        "portrait_alt": "Arden portrait",
        "portrait_caption": "At the harbor.",
        "portrait_file": (BytesIO(PNG_BYTES), "arden.png"),
    }
    data.update(overrides)
    return client.post(
        UPLOAD_PATH,
        data=data,
        content_type="multipart/form-data",
        follow_redirects=False,
    )


def _image_bytes(image_format: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), (41, 82, 123)).save(output, format=image_format)
    return output.getvalue()


def _set_stored_portrait_ref(app, asset_ref: str) -> None:
    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / "arden-march"
        / "definition.yaml"
    )
    payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    profile = dict(payload.get("profile") or {})
    profile["portrait_asset_ref"] = asset_ref
    payload["profile"] = profile
    definition_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    app.extensions["character_repository"]._character_payload_cache.clear()


def test_portrait_mutation_route_identity_methods_and_order(app, client):
    rules = list(app.url_map.iter_rules())
    endpoints = [rule.endpoint for rule in rules]
    upload_rule = next(rule for rule in rules if rule.endpoint == UPLOAD_ENDPOINT)
    remove_rule = next(rule for rule in rules if rule.endpoint == REMOVE_ENDPOINT)

    assert upload_rule.rule.endswith("/personal/portrait")
    assert remove_rule.rule.endswith("/personal/portrait/remove")
    assert upload_rule.methods == {"POST", "OPTIONS"}
    assert remove_rule.methods == {"POST", "OPTIONS"}
    assert inspect.unwrap(app.view_functions[UPLOAD_ENDPOINT]).__name__ == UPLOAD_ENDPOINT
    assert inspect.unwrap(app.view_functions[REMOVE_ENDPOINT]).__name__ == REMOVE_ENDPOINT
    assert endpoints.index("character_portrait_asset") < endpoints.index(UPLOAD_ENDPOINT)
    assert endpoints.index(UPLOAD_ENDPOINT) < endpoints.index(REMOVE_ENDPOINT)
    assert endpoints.index(REMOVE_ENDPOINT) < endpoints.index("character_session_vitals")

    for path in (UPLOAD_PATH, REMOVE_PATH):
        assert client.options(path).status_code == 200
        for method in ("get", "head", "put", "patch", "delete"):
            assert getattr(client, method)(path).status_code == 405


def test_portrait_mutation_scope_assignment_view_as_csrf_and_bearer_order(
    app, client, sign_in, users, set_campaign_visibility
):
    anonymous = client.post(f"{UPLOAD_PATH}?mode=session", follow_redirects=False)
    assert anonymous.status_code == 302
    assert anonymous.headers["Location"].endswith(
        "/sign-in?next=/campaigns/linden-pass/characters/arden-march/personal/portrait?mode%3Dsession"
    )

    set_campaign_visibility("linden-pass", characters="private")
    sign_in(users["owner"]["email"], users["owner"]["password"])
    # Assignment does not bypass Characters-scope admission.
    assert _upload(client, _revision(app)).status_code == 404

    client.post("/sign-out", follow_redirects=False)
    set_campaign_visibility("linden-pass", characters="public")
    sign_in(users["admin"]["email"], users["admin"]["password"])
    app.config["CSRF_ENABLED"] = True
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    assert client.post(REMOVE_PATH).status_code == 403

    with client.session_transaction() as browser_session:
        browser_session.pop(VIEW_AS_SESSION_KEY, None)
    csrf = client.post(REMOVE_PATH)
    assert csrf.status_code == 400
    assert "Refresh the page and try again." in csrf.get_data(as_text=True)

    token = issue_api_token(app, users["admin"]["email"], label="p36-browser-bearer")
    bearer = app.test_client().post(
        REMOVE_PATH,
        data={"expected_revision": "not-an-int"},
        headers=api_headers(token),
        follow_redirects=False,
    )
    # Bearer browser mutations retain the shipped bypass of browser-session
    # View-As/CSRF processing and reach the ordinary empty-portrait redirect.
    assert bearer.status_code == 302
    assert bearer.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/arden-march?page=quick#character-portrait-manager"
    )


@pytest.mark.parametrize("endpoint", (UPLOAD_PATH, REMOVE_PATH))
def test_portrait_mutation_invalid_slug_stops_before_state_and_body_work(
    app, client, sign_in, users, monkeypatch, endpoint
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    state_store = app.extensions["character_state_store"]
    monkeypatch.setattr(
        state_store,
        "get_state",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("state accessed")),
    )
    monkeypatch.setattr(
        state_store,
        "initialize_state_if_missing",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("state initialized")),
    )
    monkeypatch.setattr(
        app_module,
        "write_campaign_asset_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("asset written")),
    )
    monkeypatch.setattr(
        app_module,
        "delete_campaign_asset_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("asset deleted")),
    )

    response = client.post(endpoint.replace("arden-march", "..%5coutside"))
    assert response.status_code == 404


def test_portrait_upload_validation_and_partial_commit_order(
    app, client, sign_in, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])
    events: list[str] = []
    state_store = app.extensions["character_state_store"]
    original_replace = state_store.replace_state
    original_write_yaml = app_module.write_yaml
    original_write_asset = app_module.write_campaign_asset_file

    def replace(*args, **kwargs):
        events.append("state")
        return original_replace(*args, **kwargs)

    def write_yaml(*args, **kwargs):
        events.append("yaml")
        return original_write_yaml(*args, **kwargs)

    def write_asset(*args, **kwargs):
        events.append("asset")
        return original_write_asset(*args, **kwargs)

    monkeypatch.setattr(state_store, "replace_state", replace)
    monkeypatch.setattr(app_module, "write_yaml", write_yaml)
    monkeypatch.setattr(app_module, "write_campaign_asset_file", write_asset)

    response = _upload(client, _revision(app))
    assert response.status_code == 302
    assert events == ["state", "yaml", "yaml", "asset"]
    assert response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/arden-march?page=portrait#character-portrait-manager"
    )


def test_portrait_remove_empty_short_circuits_revision_and_writes(
    app, client, sign_in, users, set_campaign_visibility, monkeypatch
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])
    state_store = app.extensions["character_state_store"]
    monkeypatch.setattr(
        state_store,
        "replace_state",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("state replaced")),
    )
    monkeypatch.setattr(
        app_module,
        "write_yaml",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("yaml written")),
    )

    response = client.post(REMOVE_PATH, data={"expected_revision": "not-an-int"})
    assert response.status_code == 302
    with client.session_transaction() as browser_session:
        assert browser_session["_flashes"][-1] == (
            "error",
            "That character does not currently have a portrait.",
        )


@pytest.mark.parametrize(
    ("image_format", "filename", "expected_suffix"),
    (
        ("PNG", "../../unsafe-name.PNG", ".webp"),
        ("JPEG", "portrait.JpG", ".webp"),
        ("GIF", "portrait.GIF", ".gif"),
        ("WEBP", "portrait.WEBP", ".webp"),
    ),
)
def test_portrait_upload_preserves_image_conversion_and_filename_contract(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    image_format,
    filename,
    expected_suffix,
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])
    response = _upload(
        client,
        _revision(app),
        portrait_file=(BytesIO(_image_bytes(image_format)), filename),
    )
    assert response.status_code == 302

    with app.app_context():
        record = app.extensions["character_repository"].get_character(
            "linden-pass", "arden-march"
        )
        assert record is not None
        asset_ref = str(record.definition.profile["portrait_asset_ref"])
    assert asset_ref == f"characters/arden-march/portrait{expected_suffix}"
    asset_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "assets" / Path(asset_ref)
    assert asset_path.is_file()


@pytest.mark.parametrize(
    ("case", "message"),
    (
        ("missing", "Choose an image file"),
        ("extension", "PNG, JPG, GIF, or WEBP"),
        ("empty", "cannot be empty"),
        ("content", "valid image"),
        ("oversize", "under 8 MB"),
        ("revision", "invalid literal for int() with base 10"),
        ("alt", "alt text must stay under 200"),
        ("caption", "captions must stay under 300"),
    ),
)
def test_portrait_upload_preserves_validation_taxonomy_before_state_write(
    app, client, sign_in, users, set_campaign_visibility, case, message
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])
    revision = _revision(app)
    overrides: dict[str, object] = {}
    if case == "missing":
        overrides["portrait_file"] = (BytesIO(b""), "")
    elif case == "extension":
        overrides["portrait_file"] = (BytesIO(b"text"), "portrait.txt")
    elif case == "empty":
        overrides["portrait_file"] = (BytesIO(b""), "portrait.png")
    elif case == "content":
        overrides["portrait_file"] = (BytesIO(b"not-an-image"), "portrait.png")
    elif case == "oversize":
        overrides["portrait_file"] = (BytesIO(b"x" * (8 * 1024 * 1024 + 1)), "portrait.gif")
    elif case == "revision":
        overrides["expected_revision"] = "not-an-integer"
    elif case == "alt":
        overrides["portrait_alt"] = "a" * 201
    elif case == "caption":
        overrides["portrait_caption"] = "c" * 301

    response = _upload(client, revision, **overrides)
    assert response.status_code == 302
    with client.session_transaction() as browser_session:
        assert browser_session["_flashes"][-1][0] == "error"
        assert message.lower() in browser_session["_flashes"][-1][1].lower()
    assert _revision(app) == revision


@pytest.mark.parametrize(
    "asset_ref",
    (
        "../outside.txt",
        "characters/arden-march/..\\..\\outside.txt",
        "/outside.txt",
        "C:\\outside.txt",
        "C:\\absolute\\outside.txt",
        "\\\\server\\share\\outside.txt",
        "\\\\?\\C:\\outside.txt",
    ),
)
@pytest.mark.parametrize("route_kind", ("upload", "remove"))
def test_portrait_mutations_do_not_touch_external_sentinel_for_unsafe_stored_refs(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    tmp_path,
    asset_ref,
    route_kind,
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])
    sentinel = tmp_path / "outside.txt"
    sentinel.write_text("outside-sentinel", encoding="utf-8")
    _set_stored_portrait_ref(app, asset_ref)
    revision = _revision(app)

    if route_kind == "upload":
        response = _upload(client, revision)
    else:
        response = client.post(
            REMOVE_PATH,
            data={"expected_revision": revision},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert sentinel.read_text(encoding="utf-8") == "outside-sentinel"
    with app.app_context():
        record = app.extensions["character_repository"].get_character(
            "linden-pass", "arden-march"
        )
        assert record is not None
        resulting_ref = str(
            (record.definition.profile or {}).get("portrait_asset_ref") or ""
        )
    if route_kind == "upload":
        assert resulting_ref == "characters/arden-march/portrait.webp"
    else:
        assert resulting_ref == ""


@pytest.mark.parametrize("route_kind", ("upload", "remove"))
def test_portrait_mutations_reject_outside_symlink_without_external_effect(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    tmp_path,
    route_kind,
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])
    assets_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    sentinel = tmp_path / "outside-symlink-target.gif"
    sentinel.write_bytes(b"outside-sentinel")
    symlink = assets_dir / "outside-link.gif"
    try:
        symlink.symlink_to(sentinel)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Windows symlink capability unavailable: {exc.__class__.__name__}")
    _set_stored_portrait_ref(app, "outside-link.gif")
    revision = _revision(app)

    response = (
        _upload(client, revision)
        if route_kind == "upload"
        else client.post(
            REMOVE_PATH,
            data={"expected_revision": revision},
            follow_redirects=False,
        )
    )
    assert response.status_code == 302
    assert sentinel.read_bytes() == b"outside-sentinel"
    assert symlink.is_symlink()


def _synthetic_dependencies(
    events: list[str], *, fault_stage: str | None = None, system: str = "DND-5E"
):
    definition = SimpleNamespace(
        character_slug="arden-march",
        system=system,
        profile={"portrait_asset_ref": "characters/arden-march/old.gif"},
        to_dict=lambda: {"character_slug": "arden-march"},
    )
    import_metadata = SimpleNamespace(to_dict=lambda: {"source": "managed"})
    campaign = SimpleNamespace(slug="linden-pass")
    record = SimpleNamespace(
        definition=definition,
        import_metadata=SimpleNamespace(),
        state_record=SimpleNamespace(state={"vitals": {}}),
    )

    def called(stage, result=None):
        events.append(stage)
        if fault_stage == stage:
            raise RuntimeError(f"{stage} fault")
        return result

    yaml_calls = iter(("definition_yaml", "import_yaml"))
    return portrait_routes.CharacterPortraitMutationRouteDependencies(
        load_character_context=lambda *args: called("load", (campaign, record)),
        parse_expected_revision=lambda: called("revision", 7),
        validate_character_portrait_upload=lambda upload: called(
            "upload", ("portrait.webp", b"webp")
        ),
        finalize_character_definition_for_write=lambda *args, **kwargs: called(
            "finalize", definition
        ),
        redirect_to_character_mode=lambda *args, **kwargs: called(
            "redirect", "redirected"
        ),
        has_session_mode_access=lambda *args: called("access", True),
        get_current_user=lambda: called("user", SimpleNamespace(id=19)),
        validate_character_portrait_text=lambda *args: called(
            "text", ("alt", "caption")
        ),
        build_character_portrait_asset_ref=lambda *args: called(
            "asset_ref", "characters/arden-march/portrait.webp"
        ),
        update_character_portrait_profile=lambda *args, **kwargs: called(
            "profile", definition
        ),
        build_managed_character_import_metadata=lambda *args: called(
            "import_metadata", import_metadata
        ),
        merge_state_with_definition=lambda *args: called("merge", {"vitals": {}}),
        load_campaign_character_config=lambda *args: called(
            "config", SimpleNamespace(characters_dir=Path("characters"))
        ),
        write_yaml=lambda *args: called(next(yaml_calls)),
        write_campaign_asset_file=lambda *args, **kwargs: called("asset_write"),
        delete_campaign_asset_file=lambda *args: called("asset_delete"),
    )


@pytest.mark.parametrize(
    "fault_stage",
    ("state", "definition_yaml", "import_yaml", "asset_write", "asset_delete", "flash", "redirect"),
)
def test_portrait_upload_preserves_fault_and_partial_commit_boundaries(
    app, monkeypatch, fault_stage
):
    events: list[str] = []
    dependencies = _synthetic_dependencies(events, fault_stage=fault_stage)
    monkeypatch.setitem(
        app.extensions, "character_portrait_mutation_route_dependencies", dependencies
    )

    class StateStore:
        def replace_state(self, *args, **kwargs):
            events.append("state")
            if fault_stage == "state":
                raise RuntimeError("state fault")

    monkeypatch.setitem(app.extensions, "character_state_store", StateStore())
    original_flash = portrait_routes.flash

    def flash(message, category):
        events.append("flash")
        if fault_stage == "flash":
            raise RuntimeError("flash fault")
        return original_flash(message, category)

    monkeypatch.setattr(portrait_routes, "flash", flash)
    with app.test_request_context(
        UPLOAD_PATH,
        method="POST",
        data={"portrait_file": (BytesIO(PNG_BYTES), "portrait.png")},
        content_type="multipart/form-data",
    ):
        with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
            _raw_handler(app, UPLOAD_ENDPOINT)("linden-pass", "arden-march")

    expected = [
        "load", "access", "user", "revision", "upload", "text", "asset_ref",
        "profile", "finalize", "import_metadata", "merge", "state",
        "config", "definition_yaml", "import_yaml", "asset_write", "asset_delete",
        "flash", "redirect",
    ]
    assert events == expected[: expected.index(fault_stage) + 1]


def test_portrait_remove_preserves_exact_effect_order(app, monkeypatch):
    events: list[str] = []
    dependencies = _synthetic_dependencies(events)
    monkeypatch.setitem(
        app.extensions, "character_portrait_mutation_route_dependencies", dependencies
    )

    class StateStore:
        def replace_state(self, *args, **kwargs):
            events.append("state")

    monkeypatch.setitem(app.extensions, "character_state_store", StateStore())
    monkeypatch.setattr(portrait_routes, "flash", lambda *args: events.append("flash"))
    with app.test_request_context(REMOVE_PATH, method="POST"):
        assert (
            _raw_handler(app, REMOVE_ENDPOINT)("linden-pass", "arden-march")
            == "redirected"
        )

    assert events == [
        "load", "access", "user", "revision", "profile", "finalize",
        "import_metadata", "merge", "state", "config", "definition_yaml",
        "import_yaml", "asset_delete", "flash", "redirect",
    ]


@pytest.mark.parametrize("system", ("DND-5E", "Xianxia", "unsupported-fallback"))
def test_portrait_mutation_pair_has_no_system_gate(app, monkeypatch, system):
    events: list[str] = []
    dependencies = _synthetic_dependencies(events, system=system)
    monkeypatch.setitem(
        app.extensions, "character_portrait_mutation_route_dependencies", dependencies
    )

    class StateStore:
        def replace_state(self, *args, **kwargs):
            events.append("state")

    monkeypatch.setitem(app.extensions, "character_state_store", StateStore())
    monkeypatch.setattr(portrait_routes, "flash", lambda *args: events.append("flash"))
    with app.test_request_context(
        UPLOAD_PATH,
        method="POST",
        data={"portrait_file": (BytesIO(PNG_BYTES), "portrait.png")},
        content_type="multipart/form-data",
    ):
        assert (
            _raw_handler(app, UPLOAD_ENDPOINT)("linden-pass", "arden-march")
            == "redirected"
        )
    assert events[0:3] == ["load", "access", "user"]
    assert events[-3:] == ["asset_delete", "flash", "redirect"]
