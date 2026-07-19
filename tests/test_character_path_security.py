from __future__ import annotations

from pathlib import Path
import shutil
from urllib.parse import quote

import pytest
import yaml

import player_wiki.api as api_module
import player_wiki.app as app_module
import player_wiki.character_reconciliation as character_reconciliation_module
from player_wiki.auth_store import AuthStore
from player_wiki.campaign_content_service import (
    CampaignContentError,
    delete_campaign_character_file,
    get_campaign_character_file,
    write_campaign_character_file,
)
from player_wiki.character_importer import CharacterImportError, parse_character_sheet_text
from player_wiki.character_path_safety import (
    CharacterPathSafetyError,
    resolve_character_path,
    validate_character_slug,
)
from player_wiki.character_repository import CharacterRepository
from player_wiki.character_store import CharacterStateStore
from tests.helpers.api_test_helpers import api_headers, issue_api_token
from tests.helpers.character_builder_fakes import (
    _builder_context_fixture,
    _minimal_character_definition,
    _minimal_import_metadata,
)
from tests.helpers.xianxia_character_helpers import (
    _configure_xianxia_campaign,
    _valid_xianxia_create_data,
    _valid_xianxia_manual_import_data,
)


def _copy_external_character(app, tmp_path: Path) -> tuple[str, Path]:
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    source_dir = campaigns_dir / "linden-pass" / "characters" / "arden-march"
    external_dir = tmp_path / "outside-character"
    external_dir.mkdir()
    requested_slug = str(external_dir.resolve())

    definition = yaml.safe_load((source_dir / "definition.yaml").read_text(encoding="utf-8"))
    definition["campaign_slug"] = "linden-pass"
    definition["character_slug"] = requested_slug
    (external_dir / "definition.yaml").write_text(
        yaml.safe_dump(definition, sort_keys=False), encoding="utf-8"
    )
    import_payload = yaml.safe_load((source_dir / "import.yaml").read_text(encoding="utf-8"))
    import_payload["campaign_slug"] = "linden-pass"
    import_payload["character_slug"] = requested_slug
    (external_dir / "import.yaml").write_text(
        yaml.safe_dump(import_payload, sort_keys=False), encoding="utf-8"
    )
    return requested_slug, external_dir


def test_repository_rejects_absolute_character_slug_before_state_access(
    app, tmp_path, monkeypatch
):
    requested_slug, external_dir = _copy_external_character(app, tmp_path)

    def unexpected_state_access(*args, **kwargs):
        raise AssertionError("unsafe slug reached Character state")

    monkeypatch.setattr(CharacterStateStore, "get_state", unexpected_state_access)
    repository = CharacterRepository(
        Path(app.config["TEST_CAMPAIGNS_DIR"]),
        app.extensions["character_state_store"],
    )

    assert repository.get_character("linden-pass", requested_slug) is None
    assert (external_dir / "definition.yaml").exists()
    assert (external_dir / "import.yaml").exists()


def test_destructive_helper_rejects_absolute_slug_before_any_effect(app, tmp_path):
    requested_slug, external_dir = _copy_external_character(app, tmp_path)

    class StateStore:
        def delete_state(self, *args, **kwargs):
            raise AssertionError("unsafe slug reached state deletion")

    class Store:
        def delete_character_assignment(self, *args, **kwargs):
            raise AssertionError("unsafe slug reached assignment deletion")

    deleted = delete_campaign_character_file(
        Path(app.config["TEST_CAMPAIGNS_DIR"]),
        "linden-pass",
        requested_slug,
        state_store=StateStore(),
        auth_store=Store(),
    )

    assert deleted is None
    assert (external_dir / "definition.yaml").exists()
    assert (external_dir / "import.yaml").exists()


@pytest.mark.parametrize("surface", ("browser", "api"))
def test_delete_routes_reject_absolute_slug_before_state_assignment_audit_or_files(
    app, client, users, sign_in, tmp_path, monkeypatch, surface
):
    requested_slug, external_dir = _copy_external_character(app, tmp_path)
    encoded_slug = quote(requested_slug, safe="")

    def unexpected_state_access(*args, **kwargs):
        raise AssertionError("unsafe route slug reached Character state")

    monkeypatch.setattr(CharacterStateStore, "get_state", unexpected_state_access)
    if surface == "browser":
        sign_in(users["admin"]["email"], users["admin"]["password"])
        response = client.post(
            f"/campaigns/linden-pass/characters/{encoded_slug}/controls/delete",
            data={"confirm_character_slug": requested_slug},
        )
    else:
        token = issue_api_token(app, users["admin"]["email"], label="path-security")
        response = client.delete(
            f"/api/v1/campaigns/linden-pass/characters/{encoded_slug}/controls",
            headers=api_headers(token),
            json={"confirm_character_slug": requested_slug},
        )

    assert response.status_code == 404
    assert (external_dir / "definition.yaml").exists()
    assert (external_dir / "import.yaml").exists()


def test_repository_rejects_definition_identity_mismatch_before_state_access(
    app, monkeypatch
):
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    definition_path = (
        campaigns_dir / "linden-pass" / "characters" / "arden-march" / "definition.yaml"
    )
    definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    definition["campaign_slug"] = "another-campaign"
    definition_path.write_text(yaml.safe_dump(definition, sort_keys=False), encoding="utf-8")

    def unexpected_state_access(*args, **kwargs):
        raise AssertionError("mismatched definition reached Character state")

    monkeypatch.setattr(CharacterStateStore, "get_state", unexpected_state_access)
    repository = CharacterRepository(campaigns_dir, app.extensions["character_state_store"])
    assert repository.get_character("linden-pass", "arden-march") is None


@pytest.mark.parametrize(
    "slug",
    (
        "",
        ".",
        "..",
        "../victim",
        "..\\victim",
        "mixed/..\\victim",
        "/rooted",
        "\\rooted",
        "C:relative",
        "C:\\absolute",
        "\\\\server\\share",
        "\\\\?\\C:\\device",
        "name\x00suffix",
        "name\x1fsuffix",
        'bad<name',
        'bad>name',
        'bad:name',
        'bad"name',
        'bad|name',
        'bad?name',
        'bad*name',
        "trailing.",
        "trailing ",
        "CON",
        "CONIN$",
        "CONOUT$",
        "nul.txt",
        "COM1",
        "COM\u00b9",
        "lpt9.log",
        "LPT\u00b3.txt",
    ),
)
def test_validator_rejects_cross_platform_unsafe_slugs(slug):
    with pytest.raises(CharacterPathSafetyError):
        validate_character_slug(slug)


@pytest.mark.parametrize(
    "slug",
    (
        "arden-march",
        "arden_march",
        "Arden.March-v2",
        "lǐng-yún_二",
        "name+tag",
        "name!tag",
        "name@tag",
        "name#tag",
        "name$tag",
        "name%tag",
        "name&tag",
        "name'tag",
        "name(tag)",
        "name,tag",
        "name;tag",
        "name=tag",
        "name[tag]",
        "name^tag",
        "name`tag",
        "name{tag}",
        "name~tag",
    ),
)
def test_validator_preserves_legitimate_exact_slugs(slug):
    assert validate_character_slug(slug) == slug


def test_resolver_rejects_character_directory_and_child_symlink_escapes(tmp_path):
    root = tmp_path / "characters"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "definition.yaml").write_text("sentinel", encoding="utf-8")
    try:
        (root / "escaped").symlink_to(outside, target_is_directory=True)
        with pytest.raises(CharacterPathSafetyError):
            resolve_character_path(root, "escaped", "definition.yaml")

        safe_dir = root / "safe"
        safe_dir.mkdir()
        (safe_dir / "definition.yaml").symlink_to(outside / "definition.yaml")
        with pytest.raises(CharacterPathSafetyError):
            resolve_character_path(root, "safe", "definition.yaml")

        sibling = root / "sibling"
        sibling.mkdir()
        (sibling / "definition.yaml").write_text("sentinel", encoding="utf-8")
        (root / "alias").symlink_to(sibling, target_is_directory=True)
        with pytest.raises(CharacterPathSafetyError):
            resolve_character_path(root, "alias", "definition.yaml")
    except OSError as exc:
        pytest.skip(f"symlinks unavailable on this Windows host: {exc}")


def test_delete_preflights_portrait_escape_before_definition_unlink(app, tmp_path):
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    character_dir = campaigns_dir / "linden-pass" / "characters" / "arden-march"
    definition_path = character_dir / "definition.yaml"
    import_path = character_dir / "import.yaml"
    portrait_root = campaigns_dir / "linden-pass" / "assets" / "characters"
    portrait_root.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside-portraits"
    outside.mkdir()
    (outside / "sentinel.webp").write_bytes(b"sentinel")
    portrait_dir = portrait_root / "arden-march"
    try:
        portrait_dir.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable on this Windows host: {exc}")

    with app.app_context():
        deleted = delete_campaign_character_file(
            campaigns_dir,
            "linden-pass",
            "arden-march",
            state_store=app.extensions["character_state_store"],
            auth_store=AuthStore(),
        )

    assert deleted is None
    assert definition_path.exists()
    assert import_path.exists()
    assert (outside / "sentinel.webp").exists()


def test_content_service_preserves_invalid_slug_error_taxonomy(app):
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    invalid_slug = "..\\outside"
    assert get_campaign_character_file(campaigns_dir, "linden-pass", invalid_slug) is None
    with app.app_context():
        with pytest.raises(CampaignContentError):
            write_campaign_character_file(
                campaigns_dir,
                "linden-pass",
                invalid_slug,
                definition_payload={},
                import_metadata_payload=None,
                state_store=app.extensions["character_state_store"],
            )


def test_explicit_import_slug_is_rejected_before_definition_creation():
    with pytest.raises(CharacterImportError):
        parse_character_sheet_text(
            "linden-pass",
            "",
            source_path="sheet.md",
            source_type="markdown_character_sheet",
            imported_from="Sheet",
            character_slug="../outside",
        )


@pytest.mark.parametrize("surface", ("browser", "api"))
def test_dnd_native_create_rejects_builder_output_before_files_or_state(
    app, client, users, sign_in, monkeypatch, surface
):
    unsafe_slug = "..\\outside-dnd"
    definition = _minimal_character_definition(unsafe_slug, "Unsafe DND")
    import_metadata = _minimal_import_metadata(unsafe_slug)
    target = Path(app.config["TEST_CAMPAIGNS_DIR"]) / "linden-pass" / "outside-dnd"

    monkeypatch.setattr(
        app_module,
        "build_level_one_builder_context",
        lambda *args, **kwargs: _builder_context_fixture(),
    )
    monkeypatch.setattr(
        api_module,
        "build_level_one_builder_context",
        lambda *args, **kwargs: _builder_context_fixture(),
    )
    monkeypatch.setattr(
        app_module,
        "build_level_one_character_definition",
        lambda *args, **kwargs: (definition, import_metadata),
    )
    monkeypatch.setattr(
        api_module,
        "build_level_one_character_definition",
        lambda *args, **kwargs: (definition, import_metadata),
    )

    if surface == "browser":
        sign_in(users["dm"]["email"], users["dm"]["password"])
        response = client.post(
            "/campaigns/linden-pass/characters/new",
            data={"name": "Unsafe DND", "character_slug": unsafe_slug},
        )
        assert response.status_code == 400
    else:
        token = issue_api_token(app, users["dm"]["email"], label="unsafe-dnd-create")
        response = client.post(
            "/api/v1/campaigns/linden-pass/characters/create",
            headers=api_headers(token),
            json={"values": {"name": "Unsafe DND", "character_slug": unsafe_slug}},
        )
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "validation_error"
    assert not target.exists()


@pytest.mark.parametrize("surface", ("browser", "api"))
def test_native_create_maps_containment_failure_to_existing_400(
    app, client, users, sign_in, monkeypatch, surface
):
    definition = _minimal_character_definition("safe-output", "Safe Output")
    import_metadata = _minimal_import_metadata("safe-output")
    target_module = app_module if surface == "browser" else api_module
    monkeypatch.setattr(
        target_module,
        "build_level_one_builder_context",
        lambda *args, **kwargs: _builder_context_fixture(),
    )
    monkeypatch.setattr(
        target_module,
        "build_level_one_character_definition",
        lambda *args, **kwargs: (definition, import_metadata),
    )
    monkeypatch.setattr(
        character_reconciliation_module,
        "resolve_character_path",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            CharacterPathSafetyError("contained-path test failure")
        ),
    )

    if surface == "browser":
        sign_in(users["dm"]["email"], users["dm"]["password"])
        response = client.post(
            "/campaigns/linden-pass/characters/new",
            data={"name": "Safe Output", "character_slug": "safe-output"},
        )
        assert response.status_code == 400
        assert "contained-path test failure" in response.get_data(as_text=True)
    else:
        token = issue_api_token(app, users["dm"]["email"], label="containment-create")
        response = client.post(
            "/api/v1/campaigns/linden-pass/characters/create",
            headers=api_headers(token),
            json={"values": {"name": "Safe Output", "character_slug": "safe-output"}},
        )
        assert response.status_code == 400
        assert response.get_json()["error"] == {
            "code": "validation_error",
            "message": "contained-path test failure",
        }


def _build_deletion_fixture(app, tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    character_dir = campaigns_dir / "linden-pass" / "characters" / "delete-order"
    character_dir.mkdir()
    definition_path = character_dir / "definition.yaml"
    import_path = character_dir / "import.yaml"
    definition_path.write_text("definition", encoding="utf-8")
    import_path.write_text("import", encoding="utf-8")
    portrait_dir = campaigns_dir / "linden-pass" / "assets" / "characters" / "delete-order"
    portrait_dir.mkdir(parents=True)
    (portrait_dir / "portrait.webp").write_bytes(b"portrait")
    return campaigns_dir, character_dir, definition_path, import_path


def test_valid_delete_preserves_files_portraits_state_assignment_order(
    app, tmp_path, monkeypatch
):
    campaigns_dir, character_dir, definition_path, import_path = _build_deletion_fixture(
        app, tmp_path
    )
    portrait_dir = campaigns_dir / "linden-pass" / "assets" / "characters" / "delete-order"
    events: list[str] = []
    original_unlink = Path.unlink
    original_rmdir = Path.rmdir
    original_rmtree = shutil.rmtree

    monkeypatch.setattr(
        Path,
        "unlink",
        lambda path, *args, **kwargs: events.append(f"unlink:{path.name}")
        or original_unlink(path, *args, **kwargs),
    )
    monkeypatch.setattr(
        Path,
        "rmdir",
        lambda path, *args, **kwargs: events.append("rmdir")
        or original_rmdir(path, *args, **kwargs),
    )
    monkeypatch.setattr(
        shutil,
        "rmtree",
        lambda path, *args, **kwargs: events.append("portraits")
        or original_rmtree(path, *args, **kwargs),
    )

    class StateStore:
        def delete_state(self, *args):
            events.append("state")
            return object()

    class Store:
        def delete_character_assignment(self, *args):
            events.append("assignment")
            return object()

    deleted = delete_campaign_character_file(
        campaigns_dir,
        "linden-pass",
        "delete-order",
        state_store=StateStore(),
        auth_store=Store(),
    )

    assert events == [
        "unlink:definition.yaml",
        "unlink:import.yaml",
        "rmdir",
        "portraits",
        "state",
        "assignment",
    ]
    assert deleted is not None
    assert not definition_path.exists()
    assert not import_path.exists()
    assert not character_dir.exists()
    assert not portrait_dir.exists()


@pytest.mark.parametrize(
    ("fault_stage", "expected_events"),
    (
        ("definition", ["unlink:definition.yaml"]),
        ("import", ["unlink:definition.yaml", "unlink:import.yaml"]),
        ("rmdir", ["unlink:definition.yaml", "unlink:import.yaml", "rmdir"]),
        (
            "portraits",
            ["unlink:definition.yaml", "unlink:import.yaml", "rmdir", "portraits"],
        ),
        (
            "state",
            ["unlink:definition.yaml", "unlink:import.yaml", "rmdir", "portraits", "state"],
        ),
        (
            "assignment",
            [
                "unlink:definition.yaml",
                "unlink:import.yaml",
                "rmdir",
                "portraits",
                "state",
                "assignment",
            ],
        ),
    ),
)
def test_valid_delete_faults_preserve_prior_partial_effects(
    app, tmp_path, monkeypatch, fault_stage, expected_events
):
    campaigns_dir, _, _, _ = _build_deletion_fixture(app, tmp_path)
    events: list[str] = []
    original_unlink = Path.unlink
    original_rmdir = Path.rmdir
    original_rmtree = shutil.rmtree

    def unlink(path, *args, **kwargs):
        stage = "definition" if path.name == "definition.yaml" else "import"
        events.append(f"unlink:{path.name}")
        if fault_stage == stage:
            raise RuntimeError(f"{stage} fault")
        return original_unlink(path, *args, **kwargs)

    def rmdir(path, *args, **kwargs):
        events.append("rmdir")
        if fault_stage == "rmdir":
            raise RuntimeError("rmdir fault")
        return original_rmdir(path, *args, **kwargs)

    def rmtree(path, *args, **kwargs):
        events.append("portraits")
        if fault_stage == "portraits":
            raise RuntimeError("portraits fault")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    monkeypatch.setattr(Path, "rmdir", rmdir)
    monkeypatch.setattr(shutil, "rmtree", rmtree)

    class StateStore:
        def delete_state(self, *args):
            events.append("state")
            if fault_stage == "state":
                raise RuntimeError("state fault")
            return object()

    class Store:
        def delete_character_assignment(self, *args):
            events.append("assignment")
            if fault_stage == "assignment":
                raise RuntimeError("assignment fault")
            return object()

    with pytest.raises(RuntimeError, match=f"{fault_stage} fault"):
        delete_campaign_character_file(
            campaigns_dir,
            "linden-pass",
            "delete-order",
            state_store=StateStore(),
            auth_store=Store(),
        )
    assert events == expected_events


@pytest.mark.parametrize("surface", ("browser-create", "api-create", "browser-import", "api-import"))
def test_xianxia_create_and_manual_import_reject_unsafe_slug_before_write(
    app, client, users, sign_in, monkeypatch, surface
):
    _configure_xianxia_campaign(app)
    unsafe_slug = "..\\outside-xianxia"
    target = Path(app.config["TEST_CAMPAIGNS_DIR"]) / "linden-pass" / "outside-xianxia"
    sign_in(users["dm"]["email"], users["dm"]["password"])
    if surface.endswith("create"):
        definition = _minimal_character_definition(unsafe_slug, "Unsafe Xianxia")
        import_metadata = _minimal_import_metadata(unsafe_slug)
        monkeypatch.setattr(
            app_module,
            "build_xianxia_character_definition",
            lambda *args, **kwargs: (definition, import_metadata),
        )
        monkeypatch.setattr(
            api_module,
            "build_xianxia_character_definition",
            lambda *args, **kwargs: (definition, import_metadata),
        )
        monkeypatch.setattr(
            app_module,
            "build_xianxia_character_initial_state",
            lambda *args, **kwargs: {},
        )
        monkeypatch.setattr(
            api_module,
            "build_xianxia_character_initial_state",
            lambda *args, **kwargs: {},
        )

    if surface == "browser-create":
        response = client.post(
            "/campaigns/linden-pass/characters/new",
            data=_valid_xianxia_create_data("Unsafe Xianxia", slug=unsafe_slug),
        )
        assert response.status_code == 400
    elif surface == "browser-import":
        response = client.post(
            "/campaigns/linden-pass/characters/import/xianxia-manual",
            data={
                **_valid_xianxia_manual_import_data("Unsafe Import", slug=unsafe_slug),
                "confirm_import": "1",
            },
        )
        assert response.status_code == 400
    else:
        token = issue_api_token(app, users["dm"]["email"], label=f"unsafe-{surface}")
        if surface == "api-create":
            response = client.post(
                "/api/v1/campaigns/linden-pass/characters/create",
                headers=api_headers(token),
                json={"values": _valid_xianxia_create_data("Unsafe Xianxia", slug=unsafe_slug)},
            )
        else:
            response = client.post(
                "/api/v1/campaigns/linden-pass/characters/import/xianxia-manual",
                headers=api_headers(token),
                json={
                    "values": _valid_xianxia_manual_import_data("Unsafe Import", slug=unsafe_slug),
                    "confirm_import": True,
                },
            )
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "validation_error"
    assert not target.exists()


def test_confirmed_xianxia_api_import_maps_containment_failure_to_existing_400(
    app, client, users, monkeypatch
):
    _configure_xianxia_campaign(app)
    slug = "safe-import-containment"
    token = issue_api_token(app, users["dm"]["email"], label="containment-manual-import")
    character_dir = (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / "linden-pass"
        / "characters"
        / slug
    )
    monkeypatch.setattr(
        character_reconciliation_module,
        "resolve_character_path",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            CharacterPathSafetyError("contained import path is unavailable")
        ),
    )

    response = client.post(
        "/api/v1/campaigns/linden-pass/characters/import/xianxia-manual",
        headers=api_headers(token),
        json={
            "values": _valid_xianxia_manual_import_data(
                "Contained Import",
                slug=slug,
            ),
            "confirm_import": True,
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "validation_error",
        "message": "contained import path is unavailable",
    }
    assert not character_dir.exists()
    with app.app_context():
        assert app.extensions["character_state_store"].get_state("linden-pass", slug) is None


def test_confirmed_xianxia_api_import_does_not_broaden_unrelated_value_error_catch(
    app, client, users, monkeypatch
):
    _configure_xianxia_campaign(app)
    token = issue_api_token(app, users["dm"]["email"], label="unrelated-manual-import-fault")
    monkeypatch.setattr(
        character_reconciliation_module,
        "resolve_character_path",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("unrelated write fault")
        ),
    )

    with pytest.raises(ValueError, match="unrelated write fault"):
        client.post(
            "/api/v1/campaigns/linden-pass/characters/import/xianxia-manual",
            headers=api_headers(token),
            json={
                "values": _valid_xianxia_manual_import_data(
                    "Unrelated Fault",
                    slug="unrelated-fault",
                ),
                "confirm_import": True,
            },
        )
