from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
from types import SimpleNamespace

import pytest

import player_wiki.campaign_cutover_exporter as exporter_module

from player_wiki.campaign_cutover_exporter import (
    CampaignCutoverExportError,
    CampaignRoot,
    FAMILY_NAMES,
    assert_final_cutover_eligible,
    export_campaign_cutover_package,
)
from player_wiki.migrations import CURRENT_SCHEMA_SQL


FIXTURES = Path(__file__).parent / "fixtures" / "cutover_package_v2"
CONTRACT = (
    Path(__file__).parents[1]
    / "docs"
    / "contracts"
    / "campaign-player-wiki-cutover-package-v2.schema.json"
)
COMMIT = "1" * 40
TREE = "2" * 40


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name / "fixture.json").read_text(encoding="utf-8"))


def _materialize_campaign(parent: Path, fixture: dict, *, reverse: bool = False) -> Path:
    root = parent / fixture["campaign_slug"]
    entries = list(fixture["files"].items())
    if reverse:
        entries.reverse()
    for relative, text in entries:
        path = root / Path(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    return root


def _create_full_schema_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(CURRENT_SCHEMA_SQL)
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO schema_migrations VALUES (1, '0001_sanitized', ?, '2026-01-01T00:00:00Z')",
            ("a" * 64,),
        )
        connection.commit()


def _export(
    *, database: Path, campaigns_parent: Path, fixture: dict, output: Path
):
    _make_fixture_sources_private(database, campaigns_parent)
    return export_campaign_cutover_package(
        database_path=database,
        campaigns_parent=campaigns_parent,
        campaigns=[
            CampaignRoot(
                fixture["campaign_slug"],
                fixture["campaign_stable_id"],
                campaigns_parent / fixture["campaign_slug"],
            )
        ],
        output_dir=output,
        source_stable_id=fixture["source_stable_id"],
        exporter_commit=COMMIT,
        exporter_tree=TREE,
    )


def _make_fixture_sources_private(database: Path, campaigns_parent: Path) -> None:
    database_bundle = [
        path
        for path in (
            database,
            Path(f"{database}-wal"),
            Path(f"{database}-shm"),
        )
        if path.exists()
    ]
    paths = [*database_bundle, campaigns_parent, *campaigns_parent.rglob("*")]
    for path in paths:
        os.chmod(path, 0o700 if path.is_dir() else 0o600)
    if os.name != "nt":
        return
    user = os.environ["USERNAME"]
    for path in paths:
        grant = f"{user}:(OI)(CI)F" if path.is_dir() else f"{user}:F"
        result = subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", grant],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


def _package_digests(root: Path) -> dict[str, str]:
    import hashlib

    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _tamper_manifest(payload: dict, mutation: str) -> None:
    families = payload["families"]
    if mutation == "top_level_additional":
        payload["unexpected"] = "field"
    elif mutation == "version_constant":
        payload["format_version"] = 3
    elif mutation == "certification_additional":
        payload["certification"]["unexpected"] = True
    elif mutation == "certification_missing":
        del payload["certification"]["verification_level"]
    elif mutation == "source_stable_id":
        payload["source_stable_id"] = "substituted-source"
    elif mutation == "exporter_tree":
        payload["exporter"]["tree"] = "3" * 40
    elif mutation == "artifact_hash":
        payload["artifacts"][0]["sha256"] = payload["artifacts"][1]["sha256"]
    elif mutation == "content_root":
        payload["content_root_digest"] = payload["schema_digest"]
    elif mutation == "schema_digest":
        payload["schema_digest"] = families[0]["sha256"]
    elif mutation == "snapshot_identity":
        payload["snapshot"]["sha256"] = families[0]["sha256"]
    elif mutation == "snapshot_missing":
        del payload["snapshot"]["byte_count"]
    elif mutation == "family_same_count_hash_substitution":
        target = families[0]
        replacement = next(
            item
            for item in families[1:]
            if item["record_count"] == target["record_count"]
        )
        target["path"] = replacement["path"]
        target["sha256"] = replacement["sha256"]
    elif mutation == "family_missing":
        del families[0]["record_count"]
    elif mutation == "disposition_totals":
        payload["disposition_totals"]["typed_projection"] += 1
    elif mutation == "campaign_stable_ids":
        slug = next(iter(payload["campaign_stable_ids"]))
        payload["campaign_stable_ids"][slug] = "substituted-campaign"
    elif mutation == "campaign_same_count_hash_substitution":
        payload["campaigns"][0]["content_sha256"] = families[0]["sha256"]
    elif mutation == "campaign_additional":
        payload["campaigns"][0]["unexpected"] = "field"
    else:  # pragma: no cover - the parameter table is exhaustive
        raise AssertionError(mutation)


def test_sparse_full_schema_export_has_exact_topology_and_contract(tmp_path):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    campaigns_parent = tmp_path / "campaigns"
    _materialize_campaign(campaigns_parent, fixture)
    output = tmp_path / "cutover"

    summary = _export(
        database=database,
        campaigns_parent=campaigns_parent,
        fixture=fixture,
        output=output,
    )

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert set(manifest) == set(contract["required"])
    assert manifest["certification"] == {
        "format_version": 2,
        "manifest_hashes_verified": True,
        "verification_level": "verified_v2",
    }
    assert [item["name"] for item in manifest["families"]] == list(FAMILY_NAMES)
    assert summary.table_count == len(
        json.loads((output / "inventory" / "tables.json").read_text(encoding="utf-8"))
    )
    expected_static = {
        "manifest.json",
        "source/database.sqlite3",
        "inventory/schema.json",
        "inventory/tables.json",
        "inventory/files.json",
        "inventory/blobs.json",
        "inventory/dispositions.json",
        "evidence/safe-summary.json",
        *(f"families/{name}.json" for name in FAMILY_NAMES),
    }
    actual = {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()}
    assert expected_static <= actual
    assert all("C:\\" not in path.read_text(encoding="utf-8") for path in output.rglob("*.json"))
    for path in output.rglob("*.json"):
        raw = path.read_bytes()
        assert raw.endswith(b"\n") and not raw.endswith(b"\n\n") and not raw.startswith(b"\xef\xbb\xbf")


@pytest.mark.parametrize("fixture_name", ["dense", "sparse"])
def test_same_source_and_logical_files_are_byte_identical_across_roots_and_creation_order(
    tmp_path, fixture_name
):
    fixture = _fixture(fixture_name)
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent_a = tmp_path / "a" / "campaigns"
    parent_b = tmp_path / "b" / "campaigns"
    _materialize_campaign(parent_a, fixture)
    _materialize_campaign(parent_b, fixture, reverse=True)

    _export(database=database, campaigns_parent=parent_a, fixture=fixture, output=tmp_path / "out-a")
    _export(database=database, campaigns_parent=parent_b, fixture=fixture, output=tmp_path / "out-b")

    assert _package_digests(tmp_path / "out-a") == _package_digests(tmp_path / "out-b")
    objects = [path for path in (tmp_path / "out-a" / "source" / "objects").rglob("*") if path.is_file()]
    assert len(objects) == len({path.name for path in objects})
    files = json.loads((tmp_path / "out-a" / "inventory" / "files.json").read_text(encoding="utf-8"))
    duplicate_bindings = [item for item in files if item["logical_path"].startswith("assets/shared/crest")]
    if fixture_name == "dense":
        assert len(duplicate_bindings) == 2
        assert len({item["sha256"] for item in duplicate_bindings}) == 1
    else:
        assert not duplicate_bindings


def test_dense_full_schema_fixture_binds_blob_and_preserves_xianxia(app, tmp_path):
    fixture = _fixture("dense")
    database = Path(app.config["DB_PATH"])
    with sqlite3.connect(database) as connection:
        cursor = connection.execute(
            """
            INSERT INTO campaign_session_articles (
                campaign_slug, title, body_markdown, status, created_at
            ) VALUES ('linden-pass', 'Sanitized Article', '# Article', 'staged', ?)
            """,
            ("2026-01-01T00:00:00Z",),
        )
        connection.execute(
            """
            INSERT INTO campaign_session_article_images (
                article_id, filename, media_type, alt_text, caption, data_blob, updated_at
            ) VALUES (?, 'crest.bin', 'application/octet-stream', 'Crest', '', ?, ?)
            """,
            (cursor.lastrowid, b"sanitized-blob", "2026-01-01T00:00:00Z"),
        )
        xianxia_article = connection.execute(
            """
            INSERT INTO campaign_session_articles (
                campaign_slug, title, body_markdown, status, created_at
            ) VALUES ('xianxia-preserved', 'Preserved Article', '# Preserved', 'staged', ?)
            """,
            ("2026-01-01T00:00:00Z",),
        )
        connection.execute(
            """
            INSERT INTO campaign_session_article_images (
                article_id, filename, media_type, alt_text, caption, data_blob, updated_at
            ) VALUES (?, 'preserved.bin', 'application/octet-stream', '', '', ?, ?)
            """,
            (xianxia_article.lastrowid, b"preserved-blob", "2026-01-01T00:00:00Z"),
        )
        connection.execute(
            """
            INSERT INTO character_state (
                campaign_slug, character_slug, revision, state_json, updated_at
            ) VALUES ('xianxia-preserved', 'cultivator', 1, '{}', ?)
            """,
            ("2026-01-01T00:00:00Z",),
        )
        connection.commit()
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    output = tmp_path / "out"

    summary = _export(database=database, campaigns_parent=parent, fixture=fixture, output=output)

    blobs = json.loads((output / "inventory" / "blobs.json").read_text(encoding="utf-8"))
    dispositions = json.loads((output / "inventory" / "dispositions.json").read_text(encoding="utf-8"))
    assert summary.blob_count == 2
    assert {item["table"] for item in blobs} == {"campaign_session_article_images"}
    assert {item["column"] for item in blobs} == {"data_blob"}
    assert {item["byte_count"] for item in blobs} == {
        len(b"sanitized-blob"),
        len(b"preserved-blob"),
    }
    blob_dispositions = dispositions["blobs"]
    assert {item["disposition"] for item in blob_dispositions} == {
        "typed_projection",
        "sealed_preservation",
    }
    assets_family = json.loads(
        (output / "families" / "assets.json").read_text(encoding="utf-8")
    )
    assert len(assets_family["blob_bindings"]) == 1
    xianxia = [
        item
        for item in dispositions["rows"]
        if item["table"] == "character_state"
        and item["locator"].get("campaign_slug") == "xianxia-preserved"
    ]
    assert xianxia and xianxia[0]["disposition"] == "sealed_preservation"
    family_tables = {
        name: {
            item["table"]
            for item in json.loads((output / "families" / f"{name}.json").read_text(encoding="utf-8"))["tables"]
        }
        for name in FAMILY_NAMES
    }
    assert family_tables["assets"] == {"campaign_session_article_images"}
    assert family_tables["campaign_system_policies"] == {"campaign_system_policies"}


def test_full_schema_registry_and_zero_closure_are_source_derived(tmp_path):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    output = tmp_path / "out"
    _export(database=database, campaigns_parent=parent, fixture=fixture, output=output)

    tables = json.loads((output / "inventory" / "tables.json").read_text(encoding="utf-8"))
    dispositions = json.loads((output / "inventory" / "dispositions.json").read_text(encoding="utf-8"))
    assert {item["table"] for item in tables} == {item["table"] for item in dispositions["tables"]}
    assert sum(item["row_count"] for item in tables) == len(dispositions["rows"])
    assert sum(len(item["columns"]) for item in tables) == len(dispositions["columns"])
    assert all(item["verified_source_zero"] for item in tables if item["table"] != "schema_migrations")


@pytest.mark.parametrize("mutation", ["unknown_table", "extra_column", "missing_table"])
def test_schema_drift_fails_closed_without_publication(tmp_path, mutation):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    with sqlite3.connect(database) as connection:
        if mutation == "unknown_table":
            connection.execute("CREATE TABLE unexpected_table (id INTEGER PRIMARY KEY)")
        elif mutation == "extra_column":
            connection.execute("ALTER TABLE character_state ADD COLUMN surprise TEXT")
        else:
            connection.execute("DROP TABLE character_state")
        connection.commit()
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    output = tmp_path / "out"

    with pytest.raises(CampaignCutoverExportError):
        _export(database=database, campaigns_parent=parent, fixture=fixture, output=output)

    assert not output.exists()
    assert not list(tmp_path.glob(".out.cutover-stage-*"))


def test_nonterminal_journal_is_product_escalation_and_source_is_unchanged(tmp_path):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO player_wiki_reconciliation_operations (
                operation_id, campaign_slug, page_ref, operation_kind, primary_authority,
                desired_primary_ref, previous_primary_digest, desired_primary_digest,
                previous_markdown_digest, desired_markdown_digest, desired_markdown,
                state, error_code, created_at, updated_at
            ) VALUES (?, ?, ?, 'update', 'markdown', ?, '', ?, '', ?, ?, 'prepared', '', ?, ?)
            """,
            (
                "1" * 32,
                fixture["campaign_slug"],
                "overview/index",
                "overview/index.md",
                "2" * 64,
                "3" * 64,
                b"# pending",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )
        connection.commit()
    before = database.read_bytes()
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)

    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(database=database, campaigns_parent=parent, fixture=fixture, output=tmp_path / "out")

    assert caught.value.code == "nonterminal_operational_journal"
    assert database.read_bytes() == before


def test_additional_supported_dnd_campaign_is_product_escalation(tmp_path):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    extra = parent / "second-dnd"
    extra.mkdir(parents=True)
    (extra / "campaign.yaml").write_text("slug: second-dnd\nsystem: DND-5E\n", encoding="utf-8")

    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(database=database, campaigns_parent=parent, fixture=fixture, output=tmp_path / "out")

    assert caught.value.code == "additional_supported_dnd_campaign"


def test_unapproved_campaign_directory_link_is_refused_when_supported(tmp_path):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    linked_source = tmp_path / "linked-campaign"
    linked_source.mkdir()
    (linked_source / "campaign.yaml").write_text(
        "slug: linked-campaign\nsystem: XIANXIA\n", encoding="utf-8"
    )
    try:
        (parent / "linked-campaign").symlink_to(linked_source, target_is_directory=True)
    except OSError:
        pytest.skip("directory links are unavailable")

    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(
            database=database,
            campaigns_parent=parent,
            fixture=fixture,
            output=tmp_path / "out",
        )

    assert caught.value.code == "unsafe_source_topology"


def test_unapproved_file_shape_fails_as_required_file_escalation(tmp_path):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    root = _materialize_campaign(parent, fixture)
    (root / "outside.txt").write_text("required", encoding="utf-8")

    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(database=database, campaigns_parent=parent, fixture=fixture, output=tmp_path / "out")

    assert caught.value.code == "required_file_outside_approved_roots"


def test_symlink_or_hardlink_source_is_refused_when_supported(tmp_path):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    root = _materialize_campaign(parent, fixture)
    source = root / "assets" / "one.bin"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"one")
    linked = root / "assets" / "two.bin"
    try:
        os.link(source, linked)
    except OSError:
        pytest.skip("hardlinks are unavailable")

    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(database=database, campaigns_parent=parent, fixture=fixture, output=tmp_path / "out")

    assert caught.value.code in {"unsafe_source_topology", "unsafe_hardlink"}


def test_output_no_clobber_and_legacy_final_certification_refusal(tmp_path):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    output = tmp_path / "out"
    output.mkdir()
    marker = output / "keep"
    marker.write_text("unchanged", encoding="utf-8")

    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(database=database, campaigns_parent=parent, fixture=fixture, output=output)
    assert caught.value.code == "output_exists"
    assert marker.read_text(encoding="utf-8") == "unchanged"

    with pytest.raises(CampaignCutoverExportError) as legacy:
        assert_final_cutover_eligible(
            format_identity="campaign-player-wiki-campaign-package",
            format_version=1,
            verification_level="legacy_v1",
            manifest_hashes_verified=False,
        )
    assert legacy.value.code == "final_certification_ineligible"
    assert_final_cutover_eligible(
        format_identity="campaign-player-wiki-cutover-package",
        format_version=2,
        verification_level="verified_v2",
        manifest_hashes_verified=True,
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "top_level_additional",
        "version_constant",
        "certification_additional",
        "certification_missing",
        "source_stable_id",
        "exporter_tree",
        "artifact_hash",
        "content_root",
        "schema_digest",
        "snapshot_identity",
        "snapshot_missing",
        "family_same_count_hash_substitution",
        "family_missing",
        "disposition_totals",
        "campaign_stable_ids",
        "campaign_same_count_hash_substitution",
        "campaign_additional",
    ],
)
def test_canonical_manifest_tamper_fails_self_verification_without_side_effects(
    tmp_path, monkeypatch, mutation
):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    output = tmp_path / "out"
    database_before = database.read_bytes()
    campaigns_before = _package_digests(parent)
    original_write = exporter_module._write_canonical_json

    def tampering_write(path, value):
        original_write(path, value)
        if path.name != "manifest.json":
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        _tamper_manifest(payload, mutation)
        path.write_bytes(exporter_module._canonical_json_bytes(payload))

    monkeypatch.setattr(exporter_module, "_write_canonical_json", tampering_write)
    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(
            database=database,
            campaigns_parent=parent,
            fixture=fixture,
            output=output,
        )

    assert caught.value.code == "self_verification_failed"
    assert database.read_bytes() == database_before
    assert _package_digests(parent) == campaigns_before
    assert not output.exists()
    assert not list(tmp_path.glob(".out.cutover-stage-*"))


def test_atomic_publication_race_never_replaces_competing_destination(
    tmp_path, monkeypatch
):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    output = tmp_path / "out"
    database_before = database.read_bytes()
    campaigns_before = _package_digests(parent)
    original_publish = exporter_module._publish_stage
    competing_bytes = b"concurrent destination\n"

    def claim_destination_then_publish(stage, destination):
        destination.mkdir()
        (destination / "competitor.bin").write_bytes(competing_bytes)
        original_publish(stage, destination)

    monkeypatch.setattr(
        exporter_module,
        "_publish_stage",
        claim_destination_then_publish,
    )
    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(
            database=database,
            campaigns_parent=parent,
            fixture=fixture,
            output=output,
        )

    assert caught.value.code == "output_collision"
    assert (output / "competitor.bin").read_bytes() == competing_bytes
    assert {path.name for path in output.iterdir()} == {"competitor.bin"}
    assert database.read_bytes() == database_before
    assert _package_digests(parent) == campaigns_before
    assert not list(tmp_path.glob(".out.cutover-stage-*"))


def test_contract_rejects_additional_manifest_properties():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["additionalProperties"] is False
    assert contract["properties"]["certification"]["additionalProperties"] is False


@pytest.mark.parametrize(
    ("state_json", "expected_code"),
    [
        ('{"a":1,"a":2}', "duplicate_json_key"),
        ('{"note":"C:\\\\private\\\\source.txt"}', "machine_path_leak"),
    ],
)
def test_invalid_structured_or_machine_path_values_fail_redacted(
    tmp_path, state_json, expected_code
):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO character_state VALUES (?, 'hero', 1, ?, ?, NULL)",
            (fixture["campaign_slug"], state_json, "2026-01-01T00:00:00Z"),
        )
        connection.commit()
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)

    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(database=database, campaigns_parent=parent, fixture=fixture, output=tmp_path / "out")

    assert caught.value.code == expected_code
    assert "private" not in caught.value.safe_message.casefold()
    assert not (tmp_path / "out").exists()


def test_non_blob_media_and_active_rollback_journal_fail_closed(tmp_path):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    with sqlite3.connect(database) as connection:
        cursor = connection.execute(
            """
            INSERT INTO campaign_session_articles (
                campaign_slug, title, body_markdown, status, created_at
            ) VALUES (?, 'Article', '# Body', 'staged', ?)
            """,
            (fixture["campaign_slug"], "2026-01-01T00:00:00Z"),
        )
        connection.execute(
            """
            INSERT INTO campaign_session_article_images
            VALUES (?, 'bad.bin', 'application/octet-stream', '', '', 'not-a-blob', ?)
            """,
            (cursor.lastrowid, "2026-01-01T00:00:00Z"),
        )
        connection.commit()
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)

    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(database=database, campaigns_parent=parent, fixture=fixture, output=tmp_path / "out")
    assert caught.value.code == "invalid_blob"

    Path(f"{database}-journal").write_bytes(b"unsafe")
    with pytest.raises(CampaignCutoverExportError) as journal:
        _export(database=database, campaigns_parent=parent, fixture=fixture, output=tmp_path / "out-2")
    assert journal.value.code == "unsafe_sqlite_journal"


def test_capacity_interruption_and_atomic_failure_leave_no_unpublished_residue(
    tmp_path, monkeypatch
):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)

    monkeypatch.setattr(
        exporter_module.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(total=1, used=1, free=0),
    )
    with pytest.raises(CampaignCutoverExportError) as capacity:
        _export(database=database, campaigns_parent=parent, fixture=fixture, output=tmp_path / "capacity")
    assert capacity.value.code == "insufficient_capacity"
    assert not list(tmp_path.glob(".capacity.cutover-stage-*"))

    monkeypatch.undo()
    monkeypatch.setattr(
        exporter_module,
        "_project_snapshot",
        lambda **_: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    with pytest.raises(KeyboardInterrupt):
        _export(database=database, campaigns_parent=parent, fixture=fixture, output=tmp_path / "interrupt")
    assert not list(tmp_path.glob(".interrupt.cutover-stage-*"))

    monkeypatch.undo()
    monkeypatch.setattr(
        exporter_module,
        "_publish_stage",
        lambda *_: (_ for _ in ()).throw(OSError("atomic failure at private path")),
    )
    with pytest.raises(CampaignCutoverExportError) as atomic:
        _export(database=database, campaigns_parent=parent, fixture=fixture, output=tmp_path / "atomic")
    assert atomic.value.code == "capture_refused"
    assert not (tmp_path / "atomic").exists()
    assert not list(tmp_path.glob(".atomic.cutover-stage-*"))


def test_same_count_substitution_changes_family_and_content_digests(tmp_path):
    fixture = _fixture("sparse")
    database_a = tmp_path / "a.sqlite3"
    database_b = tmp_path / "b.sqlite3"
    _create_full_schema_database(database_a)
    _create_full_schema_database(database_b)
    for database, marker in ((database_a, "one"), (database_b, "two")):
        with sqlite3.connect(database) as connection:
            connection.execute(
                "INSERT INTO character_state VALUES (?, 'hero', 1, ?, ?, NULL)",
                (
                    fixture["campaign_slug"],
                    json.dumps({"marker": marker}),
                    "2026-01-01T00:00:00Z",
                ),
            )
            connection.commit()
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    first = _export(database=database_a, campaigns_parent=parent, fixture=fixture, output=tmp_path / "out-a")
    second = _export(database=database_b, campaigns_parent=parent, fixture=fixture, output=tmp_path / "out-b")
    manifest_a = json.loads((tmp_path / "out-a" / "manifest.json").read_text(encoding="utf-8"))
    manifest_b = json.loads((tmp_path / "out-b" / "manifest.json").read_text(encoding="utf-8"))
    family_a = next(item for item in manifest_a["families"] if item["name"] == "characters")
    family_b = next(item for item in manifest_b["families"] if item["name"] == "characters")
    assert family_a["record_count"] == family_b["record_count"] == 1
    assert family_a["sha256"] != family_b["sha256"]
    assert first.content_root_sha256 != second.content_root_sha256


def test_source_output_overlap_refuses_before_staging(tmp_path):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    root = _materialize_campaign(parent, fixture)
    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(database=database, campaigns_parent=parent, fixture=fixture, output=root / "out")
    assert caught.value.code == "source_output_overlap"


def test_cli_refusal_is_structured_and_redacted(capsys):
    from scripts.export_campaign_cutover_package import main

    assert main([]) == 2
    payload = json.loads(capsys.readouterr().err)
    assert payload == {
        "code": "invalid_cli",
        "message": "The cutover export invocation is invalid.",
        "status": "refused",
    }
