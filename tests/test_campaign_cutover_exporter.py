from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

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
QUARANTINE_SENTINEL = "[cpw-cutover-v2:quarantined-external-machine-path]"


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


def _insert_campaign_page(
    database: Path,
    *,
    campaign_slug: str,
    image_path: str = "",
    source_ref: str = "",
    metadata: dict | None = None,
    summary: str = "",
) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO campaign_pages (
                campaign_slug, page_ref, route_slug, title, section, page_type,
                image_path, source_ref, metadata_json, raw_link_targets_json,
                summary, body_markdown, created_at, updated_at
            ) VALUES (?, 'path-probe', 'path-probe', 'Path Probe', 'Wiki', 'wiki',
                      ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                campaign_slug,
                image_path,
                source_ref,
                json.dumps(metadata or {}, separators=(",", ":")),
                json.dumps(["/campaigns/path-probe", "Rules/Paths"]),
                summary,
                "Ordinary text: drive C:; ratio 3:1; https://example.test/home/help.",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )
        connection.commit()


def _insert_session_articles(
    database: Path,
    *,
    campaign_slug: str,
    rows: list[tuple[int, str, str]],
    reverse: bool = False,
) -> None:
    ordered = list(reversed(rows)) if reverse else rows
    with sqlite3.connect(database) as connection:
        connection.executemany(
            """
            INSERT INTO campaign_session_articles (
                id, campaign_slug, title, body_markdown, status, created_at
            ) VALUES (?, ?, ?, ?, 'staged', '2026-01-01T00:00:00Z')
            """,
            [
                (row_id, campaign_slug, title, body_markdown)
                for row_id, title, body_markdown in ordered
            ],
        )
        connection.commit()


_LEGACY_CHECK_REPLACEMENTS = (
    (
        "status TEXT NOT NULL CHECK (status IN ('invited', 'active', 'disabled'))",
        "status TEXT NOT NULL",
    ),
    (
        "session_chat_order TEXT NOT NULL DEFAULT 'newest_first' "
        "CHECK (session_chat_order IN ('newest_first', 'oldest_first'))",
        "session_chat_order TEXT NOT NULL DEFAULT 'newest_first'",
    ),
    (
        "frontend_mode TEXT NOT NULL DEFAULT 'flask' "
        "CHECK (frontend_mode IN ('flask', 'gen2'))",
        "frontend_mode TEXT NOT NULL DEFAULT 'flask'",
    ),
)

_LEGACY_MISSING_CHECKS = {
    "user_preferences": {
        "frontend_mode in ('flask','gen2')",
        "session_chat_order in ('newest_first','oldest_first')",
    },
    "users": {"status in ('invited','active','disabled')"},
}


def _create_legacy_missing_check_database(path: Path) -> None:
    schema_sql = CURRENT_SCHEMA_SQL
    for present, absent in _LEGACY_CHECK_REPLACEMENTS:
        assert schema_sql.count(present) == 1
        schema_sql = schema_sql.replace(present, absent, 1)
    with sqlite3.connect(path) as connection:
        connection.executescript(schema_sql)
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


def _create_reordered_schema_migrations_database(path: Path) -> None:
    """Create the same supported schema with physical column order changed."""

    with sqlite3.connect(path) as connection:
        connection.executescript(CURRENT_SCHEMA_SQL)
        connection.execute("DROP TABLE character_state")
        connection.execute(
            """
            CREATE TABLE character_state (
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                character_slug TEXT NOT NULL,
                revision INTEGER NOT NULL,
                updated_by_user_id INTEGER,
                campaign_slug TEXT NOT NULL,
                PRIMARY KEY (campaign_slug, character_slug),
                FOREIGN KEY (updated_by_user_id) REFERENCES users(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                name TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL,
                version INTEGER PRIMARY KEY,
                checksum TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO schema_migrations (version, name, checksum, applied_at)
            VALUES (1, '0001_sanitized', ?, '2026-01-01T00:00:00Z')
            """,
            ("a" * 64,),
        )
        connection.commit()


def _insert_equivalent_character_rows(
    path: Path, *, reverse_rows: bool, reverse_json_keys: bool
) -> None:
    rows = [
        (
            "sparse-dnd",
            "alpha",
            2,
            '{"traits":{"brave":true,"rank":2},"tags":["frontline","scout"]}',
            "2026-01-02T00:00:00Z",
        ),
        (
            "sparse-dnd",
            "zeta",
            1,
            '{"traits":{"brave":false,"rank":1},"tags":["support"]}',
            "2026-01-01T00:00:00Z",
        ),
    ]
    if reverse_json_keys:
        rows = [
            (
                campaign_slug,
                character_slug,
                revision,
                json.dumps(
                    {
                        "tags": json.loads(state_json)["tags"],
                        "traits": {
                            "rank": json.loads(state_json)["traits"]["rank"],
                            "brave": json.loads(state_json)["traits"]["brave"],
                        },
                    },
                    separators=(",", ":"),
                ),
                updated_at,
            )
            for campaign_slug, character_slug, revision, state_json, updated_at in rows
        ]
    if reverse_rows:
        rows.reverse()
    with sqlite3.connect(path) as connection:
        connection.executemany(
            """
            INSERT INTO character_state (
                campaign_slug, character_slug, revision, state_json, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            rows,
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
    schema = json.loads((output / "inventory" / "schema.json").read_text(encoding="utf-8"))
    users = next(item for item in schema["tables"] if item["name"] == "users")
    assert users["check_constraints"] == [
        {
            "declaration_state": "present",
            "predicate": "status in ('invited','active','disabled')",
            "validation": "physical_declaration",
        }
    ]
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
    typed_blobs = [item for item in blobs if "sha256" in item]
    sealed_blobs = [item for item in blobs if "sha256" not in item]
    assert len(typed_blobs) == len(sealed_blobs) == 1
    assert typed_blobs[0]["byte_count"] == len(b"sanitized-blob")
    assert set(sealed_blobs[0]) == {"column", "custody", "primary_key", "table"}
    assert hashlib.sha256(b"preserved-blob").hexdigest() not in json.dumps(
        [blobs, dispositions]
    )
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
    assert {item["table"] for item in dispositions["zero_tables"]} == {
        item["table"] for item in tables if item["row_count"] == 0
    }
    assert all("disposition" not in item for item in dispositions["zero_tables"])


def test_reordered_physical_columns_are_name_bound_and_emitted_canonically(tmp_path):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_reordered_schema_migrations_database(database)
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    output = tmp_path / "out"

    _export(database=database, campaigns_parent=parent, fixture=fixture, output=output)

    schema = json.loads((output / "inventory" / "schema.json").read_text(encoding="utf-8"))
    table = next(item for item in schema["tables"] if item["name"] == "schema_migrations")
    assert [item["name"] for item in table["columns"]] == [
        "version",
        "name",
        "checksum",
        "applied_at",
    ]
    assert schema["migration_ledger"] == [
        {
            "applied_at": "2026-01-01T00:00:00Z",
            "checksum": "a" * 64,
            "name": "0001_sanitized",
            "version": 1,
        }
    ]
    tables = json.loads((output / "inventory" / "tables.json").read_text(encoding="utf-8"))
    inventory = next(item for item in tables if item["table"] == "schema_migrations")
    assert inventory["columns"] == ["version", "name", "checksum", "applied_at"]
    dispositions = json.loads(
        (output / "inventory" / "dispositions.json").read_text(encoding="utf-8")
    )
    assert [
        item["column"]
        for item in dispositions["columns"]
        if item["table"] == "schema_migrations"
    ] == ["version", "name", "checksum", "applied_at"]


def test_reordered_physical_columns_preserve_canonical_derived_bytes(tmp_path):
    fixture = _fixture("sparse")
    canonical_database = tmp_path / "canonical.sqlite3"
    reordered_database = tmp_path / "reordered.sqlite3"
    _create_full_schema_database(canonical_database)
    _create_reordered_schema_migrations_database(reordered_database)
    _insert_equivalent_character_rows(
        canonical_database, reverse_rows=False, reverse_json_keys=False
    )
    _insert_equivalent_character_rows(
        reordered_database, reverse_rows=True, reverse_json_keys=True
    )
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    canonical_output = tmp_path / "canonical"
    reordered_output = tmp_path / "reordered"
    reordered_repeat_output = tmp_path / "reordered-repeat"

    _export(
        database=canonical_database,
        campaigns_parent=parent,
        fixture=fixture,
        output=canonical_output,
    )
    _export(
        database=reordered_database,
        campaigns_parent=parent,
        fixture=fixture,
        output=reordered_output,
    )
    _export(
        database=reordered_database,
        campaigns_parent=parent,
        fixture=fixture,
        output=reordered_repeat_output,
    )

    canonical_schema = json.loads(
        (canonical_output / "inventory" / "schema.json").read_text(encoding="utf-8")
    )
    reordered_schema = json.loads(
        (reordered_output / "inventory" / "schema.json").read_text(encoding="utf-8")
    )
    # sqlite_schema.sql and the captured source database intentionally retain
    # physical-source evidence; all canonical projections are order independent.
    canonical_schema.pop("objects")
    reordered_schema.pop("objects")
    canonical_schema.pop("schema_digest_basis")
    reordered_schema.pop("schema_digest_basis")
    assert canonical_schema == reordered_schema
    for relative in (f"families/{name}.json" for name in FAMILY_NAMES):
        assert (canonical_output / relative).read_bytes() == (reordered_output / relative).read_bytes()
    canonical_manifest = json.loads(
        (canonical_output / "manifest.json").read_text(encoding="utf-8")
    )
    reordered_manifest = json.loads(
        (reordered_output / "manifest.json").read_text(encoding="utf-8")
    )
    assert canonical_manifest["snapshot"]["sha256"] != reordered_manifest["snapshot"]["sha256"]
    assert canonical_manifest["content_root_digest"] != reordered_manifest["content_root_digest"]
    assert (canonical_output / "source" / "database.sqlite3").read_bytes() != (
        reordered_output / "source" / "database.sqlite3"
    ).read_bytes()
    assert _package_digests(reordered_output) == _package_digests(reordered_repeat_output)


@pytest.mark.parametrize(
    "definition",
    [
        "version TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, checksum TEXT NOT NULL, applied_at TEXT NOT NULL",
        "version INTEGER PRIMARY KEY, name TEXT UNIQUE, checksum TEXT NOT NULL, applied_at TEXT NOT NULL",
        "version INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, checksum TEXT NOT NULL DEFAULT '', applied_at TEXT NOT NULL",
        "version INTEGER NOT NULL UNIQUE, name TEXT NOT NULL UNIQUE, checksum TEXT PRIMARY KEY, applied_at TEXT NOT NULL",
        "version INTEGER PRIMARY KEY REFERENCES users(id), name TEXT NOT NULL UNIQUE, checksum TEXT NOT NULL, applied_at TEXT NOT NULL",
        "version INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, checksum TEXT NOT NULL, applied_at TEXT NOT NULL CHECK (applied_at <> '')",
    ],
    ids=["type", "nullability", "default", "primary-key", "foreign-key", "check"],
)
def test_non_order_schema_contract_drift_still_fails_closed(tmp_path, definition):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE schema_migrations")
        connection.execute(f"CREATE TABLE schema_migrations ({definition})")
        connection.commit()
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    output = tmp_path / "out"

    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(database=database, campaigns_parent=parent, fixture=fixture, output=output)

    assert caught.value.code in {
        "schema_column_contract_mismatch",
        "schema_constraint_mismatch",
    }
    assert not output.exists()
    assert not list(tmp_path.glob(".out.cutover-stage-*"))


def test_legacy_missing_checks_are_row_validated_evidenced_and_deterministic(tmp_path):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_legacy_missing_check_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO users (
                email, display_name, status, created_at, updated_at
            ) VALUES ('player@example.invalid', 'Player', 'active', '2026-01-01', '2026-01-01')
            """
        )
        connection.execute(
            """
            INSERT INTO user_preferences (
                user_id, theme_key, session_chat_order, frontend_mode, updated_at
            ) VALUES (1, 'parchment', 'newest_first', 'flask', '2026-01-01')
            """
        )
        connection.commit()
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    first = tmp_path / "out-a"
    second = tmp_path / "out-b"

    _export(database=database, campaigns_parent=parent, fixture=fixture, output=first)
    _export(database=database, campaigns_parent=parent, fixture=fixture, output=second)

    schema = json.loads((first / "inventory" / "schema.json").read_text(encoding="utf-8"))
    missing_schema = {
        table["name"]: {
            item["predicate"]
            for item in table["check_constraints"]
            if item["declaration_state"] == "missing_row_validated"
        }
        for table in schema["tables"]
        if any(
            item["declaration_state"] == "missing_row_validated"
            for item in table["check_constraints"]
        )
    }
    assert missing_schema == _LEGACY_MISSING_CHECKS
    dispositions = json.loads(
        (first / "inventory" / "dispositions.json").read_text(encoding="utf-8")
    )
    missing_dispositions = {
        table: {
            item["predicate"]
            for item in dispositions["check_constraints"]
            if item["table"] == table
            and item["declaration_state"] == "missing_row_validated"
        }
        for table in _LEGACY_MISSING_CHECKS
    }
    assert missing_dispositions == _LEGACY_MISSING_CHECKS
    assert all(
        item["disposition"] == "typed_projection"
        and item["owner"] == "inventory"
        and item["validation"] == "all_rows_satisfy_frozen_predicate"
        for item in dispositions["check_constraints"]
        if item["declaration_state"] == "missing_row_validated"
    )
    assert _package_digests(first) == _package_digests(second)


def test_missing_frozen_check_uses_sqlite_null_and_false_semantics():
    predicate = "status in ('invited','active','disabled')"
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE users (status TEXT)")
        connection.execute("INSERT INTO users VALUES (NULL)")
        exporter_module._validate_missing_check_predicate(
            connection=connection,
            table_name="users",
            predicate=predicate,
        )
        connection.execute("INSERT INTO users VALUES ('retired')")
        with pytest.raises(CampaignCutoverExportError) as caught:
            exporter_module._validate_missing_check_predicate(
                connection=connection,
                table_name="users",
                predicate=predicate,
            )
    assert caught.value.code == "schema_constraint_row_violation"
    assert "retired" not in caught.value.safe_message


def test_legacy_missing_check_with_violating_row_fails_closed(tmp_path):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_legacy_missing_check_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO users (
                email, display_name, status, created_at, updated_at
            ) VALUES ('player@example.invalid', 'Player', 'retired', '2026-01-01', '2026-01-01')
            """
        )
        connection.commit()
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    output = tmp_path / "out"

    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(database=database, campaigns_parent=parent, fixture=fixture, output=output)

    assert caught.value.code == "schema_constraint_row_violation"
    assert "retired" not in caught.value.safe_message
    assert not output.exists()
    assert not list(tmp_path.glob(".out.cutover-stage-*"))


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE TABLE users (status TEXT CHECK (status IN ('invited', 'active', 'disabled')) "
        "CHECK ( status in ('invited','active','disabled') ))",
        "CREATE TABLE users (status TEXT CHECK (status IN ('invited', 'active', 'disabled')",
    ],
    ids=["duplicate-normalized-ambiguous", "unparsable"],
)
def test_ambiguous_or_unparsable_check_declarations_fail_closed(sql):
    with pytest.raises(CampaignCutoverExportError) as caught:
        exporter_module._extract_check_constraints(sql)
    assert caught.value.code == "schema_constraint_mismatch"


@pytest.mark.parametrize(
    "mutation",
    [
        "schema_omission",
        "disposition_omission",
        "disposition_duplication",
        "disposition_mismatch",
    ],
)
def test_missing_check_evidence_tamper_fails_self_verification(tmp_path, monkeypatch, mutation):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_legacy_missing_check_database(database)
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    original_write = exporter_module._write_canonical_json

    def tampering_write(path, value):
        value = json.loads(json.dumps(value))
        if path.as_posix().endswith("inventory/schema.json") and mutation == "schema_omission":
            table = next(item for item in value["tables"] if item["name"] == "users")
            table["check_constraints"] = []
        elif path.as_posix().endswith("inventory/dispositions.json"):
            missing = [
                item
                for item in value["check_constraints"]
                if item["declaration_state"] == "missing_row_validated"
            ]
            if mutation == "disposition_omission":
                value["check_constraints"].remove(missing[0])
            elif mutation == "disposition_duplication":
                value["check_constraints"].append(dict(missing[0]))
            elif mutation == "disposition_mismatch":
                missing[0]["declaration_state"] = "present"
        original_write(path, value)

    monkeypatch.setattr(exporter_module, "_write_canonical_json", tampering_write)
    output = tmp_path / "out"
    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(database=database, campaigns_parent=parent, fixture=fixture, output=output)

    assert caught.value.code == "self_verification_failed"
    assert not output.exists()
    assert not list(tmp_path.glob(".out.cutover-stage-*"))


@pytest.mark.parametrize(
    "actual_names",
    [
        ("first",),
        ("first", "second", "extra"),
        ("first", "first"),
    ],
)
def test_missing_extra_and_duplicate_column_names_still_fail_closed(actual_names):
    columns = [{"name": name} for name in actual_names]

    with pytest.raises(CampaignCutoverExportError) as caught:
        exporter_module._canonical_schema_columns(columns, ("first", "second"))

    assert caught.value.code == "schema_column_mismatch"


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


def test_exhaustive_safe_file_custody_has_exact_typed_and_sealed_dispositions(tmp_path):
    fixture = _fixture("dense")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    root = _materialize_campaign(parent, fixture)
    additions = {
        "outside.txt": b"root-level-safe",
        "content/handouts/map.pdf": b"sanitized-pdf",
        "characters/hero/portrait.webp": b"sanitized-portrait",
        "characters/hero/notes.txt": b"character-notes",
        "unknown/nested/data.bin": b"same-preserved-bytes",
        "unknown/nested/data-copy.bin": b"same-preserved-bytes",
    }
    for relative, content in additions.items():
        path = root / Path(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    output = tmp_path / "out"
    summary = _export(
        database=database,
        campaigns_parent=parent,
        fixture=fixture,
        output=output,
    )

    files = json.loads((output / "inventory" / "files.json").read_text(encoding="utf-8"))
    dispositions = json.loads(
        (output / "inventory" / "dispositions.json").read_text(encoding="utf-8")
    )["files"]
    by_path = {item["logical_path"]: item for item in files}
    disposition_by_path = {item["logical_path"]: item for item in dispositions}
    typed = {
        "campaign.yaml",
        "characters/hero/definition.yaml",
        "characters/hero/import.yaml",
        "content/overview/index.md",
        "content/sessions/one.md",
    }
    assert {
        path
        for path, item in by_path.items()
        if item["disposition"] == "typed_projection"
    } == typed
    assert set(by_path) - typed == {
        "assets/shared/crest-copy.bin",
        "assets/shared/crest.bin",
        *additions,
    }
    assert all(
        item["disposition"] == "sealed_preservation"
        for path, item in by_path.items()
        if path not in typed
    )
    assert by_path["outside.txt"]["owner"] == "campaign_files"
    assert by_path["outside.txt"]["audience"] == "operator"
    assert by_path["content/handouts/map.pdf"]["owner"] == "campaign_pages"
    assert by_path["content/handouts/map.pdf"]["audience"] == "player"
    assert by_path["characters/hero/portrait.webp"]["owner"] == "characters"
    assert by_path["assets/shared/crest.bin"]["owner"] == "assets"
    assert len(files) == len(dispositions) == summary.file_count
    assert set(disposition_by_path) == set(by_path)
    for path, item in by_path.items():
        disposition = disposition_by_path[path]
        for key in (
            "audience",
            "byte_count",
            "campaign_stable_id",
            "disposition",
            "logical_path",
            "object_path",
            "owner",
            "sha256",
        ):
            assert disposition[key] == item[key]
    object_files = [
        path
        for path in (output / "source" / "objects" / "sha256").rglob("*")
        if path.is_file()
    ]
    assert len(object_files) == len({item["sha256"] for item in files})
    duplicates = [
        by_path[name]
        for name in (
            "unknown/nested/data.bin",
            "unknown/nested/data-copy.bin",
        )
    ]
    assert len({item["sha256"] for item in duplicates}) == 1
    assert len({item["object_path"] for item in duplicates}) == 1


@pytest.mark.parametrize("mutation", ["disposition", "byte_count"])
def test_file_disposition_tamper_fails_self_verification_without_publication(
    tmp_path, monkeypatch, mutation
):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    original_write = exporter_module._write_canonical_json

    def tampering_write(path, value):
        if path.as_posix().endswith("inventory/dispositions.json"):
            value = json.loads(json.dumps(value))
            if mutation == "disposition":
                value["files"][0]["disposition"] = "sealed_preservation"
            else:
                value["files"][0]["byte_count"] += 1
        original_write(path, value)

    monkeypatch.setattr(exporter_module, "_write_canonical_json", tampering_write)
    output = tmp_path / "out"
    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(
            database=database,
            campaigns_parent=parent,
            fixture=fixture,
            output=output,
        )
    assert caught.value.code == "self_verification_failed"
    assert not output.exists()


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


def _draft_2020_12_manifest(tmp_path: Path) -> tuple[Draft202012Validator, dict]:
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    campaigns_parent = tmp_path / "campaigns"
    _materialize_campaign(campaigns_parent, fixture)
    output = tmp_path / "cutover"
    _export(
        database=database,
        campaigns_parent=campaigns_parent,
        fixture=fixture,
        output=output,
    )
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(contract)
    return Draft202012Validator(contract), json.loads(
        (output / "manifest.json").read_text(encoding="utf-8")
    )


def _runtime_verification_manifest(tmp_path: Path, monkeypatch):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    campaigns_parent = tmp_path / "campaigns"
    _materialize_campaign(campaigns_parent, fixture)
    output = tmp_path / "cutover"
    original_verify = exporter_module._self_verify_package
    runtime_kwargs = {}

    def capture_verification(stage, **kwargs):
        runtime_kwargs.update(kwargs)
        return original_verify(stage, **kwargs)

    monkeypatch.setattr(exporter_module, "_self_verify_package", capture_verification)
    _export(
        database=database,
        campaigns_parent=campaigns_parent,
        fixture=fixture,
        output=output,
    )
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(contract)
    return (
        Draft202012Validator(contract),
        original_verify,
        output,
        runtime_kwargs,
        json.loads((output / "manifest.json").read_text(encoding="utf-8")),
    )


def test_exported_manifest_validates_as_draft_2020_12(tmp_path):
    validator, manifest = _draft_2020_12_manifest(tmp_path)

    validator.validate(manifest)


def test_exported_manifest_passes_mandatory_schema_and_runtime_layers(
    tmp_path, monkeypatch
):
    validator, runtime_verify, output, runtime_kwargs, manifest = (
        _runtime_verification_manifest(tmp_path, monkeypatch)
    )

    validator.validate(manifest)
    runtime_verify(output, **runtime_kwargs)


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "families/%2e%2e/accounts.json",
        "families/%2E%2e/accounts.json",
        "families/%252e%252e/accounts.json",
        "families/%2faccounts.json",
        "families/%5Caccounts.json",
        "families/%00accounts.json",
        "families/%43%3A/accounts.json",
        "families/%3F/device.json",
    ],
)
def test_schema_percent_encoded_traversal_and_precursors_are_rejected(
    tmp_path, unsafe_path
):
    validator, manifest = _draft_2020_12_manifest(tmp_path)
    manifest["artifacts"][0]["path"] = unsafe_path

    with pytest.raises(ValidationError):
        validator.validate(manifest)


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "families/%2e%2e/accounts.json",
        "families/%2E%2e/accounts.json",
        "families/%252e%252e/accounts.json",
        "families/%2faccounts.json",
        "families/%5Caccounts.json",
        "families/%00accounts.json",
        "families/%43%3A/accounts.json",
        "families/%3F/device.json",
    ],
)
def test_runtime_percent_encoded_traversal_and_precursors_are_rejected(unsafe_path):
    assert not exporter_module._is_safe_relative_package_path(unsafe_path)


def test_generated_package_paths_are_safe_schema_and_runtime_controls(tmp_path):
    validator, manifest = _draft_2020_12_manifest(tmp_path)
    validator.validate(manifest)
    generated_paths = [item["path"] for item in manifest["artifacts"]]
    generated_paths.extend(item["path"] for item in manifest["families"])
    generated_paths.append(manifest["snapshot"]["path"])

    assert generated_paths
    assert all("%" not in path for path in generated_paths)
    assert all(
        exporter_module._is_safe_relative_package_path(path)
        for path in generated_paths
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_artifact_path",
        "duplicate_campaign_slug",
        "duplicate_campaign_stable_id",
        "campaign_mapping_mismatch",
        "missing_campaign_mapping",
        "extra_campaign_mapping",
        "equal_count_campaign_substitution",
        "wrong_campaign_association",
        "wrong_artifact_path_association",
    ],
)
def test_runtime_relational_verification_rejects_mutations_after_schema_layer(
    tmp_path, monkeypatch, mutation
):
    validator, runtime_verify, output, runtime_kwargs, manifest = (
        _runtime_verification_manifest(tmp_path, monkeypatch)
    )
    mutated = copy.deepcopy(manifest)
    if mutation == "duplicate_artifact_path":
        mutated["artifacts"][1]["path"] = mutated["artifacts"][0]["path"]
    elif mutation == "duplicate_campaign_slug":
        duplicate = copy.deepcopy(mutated["campaigns"][0])
        duplicate["campaign_stable_id"] = "campaign-distinct-stable-id"
        mutated["campaigns"].append(duplicate)
    elif mutation == "duplicate_campaign_stable_id":
        duplicate = copy.deepcopy(mutated["campaigns"][0])
        duplicate["campaign_slug"] = "distinct-campaign-slug"
        mutated["campaigns"].append(duplicate)
    elif mutation == "campaign_mapping_mismatch":
        slug = next(iter(mutated["campaign_stable_ids"]))
        mutated["campaign_stable_ids"][slug] = "campaign-mismatched-stable-id"
    elif mutation == "missing_campaign_mapping":
        slug = next(iter(mutated["campaign_stable_ids"]))
        del mutated["campaign_stable_ids"][slug]
    elif mutation == "extra_campaign_mapping":
        mutated["campaign_stable_ids"]["extra-campaign"] = "campaign-extra"
    elif mutation == "equal_count_campaign_substitution":
        descriptor = mutated["campaigns"][0]
        original_slug = descriptor["campaign_slug"]
        stable_id = mutated["campaign_stable_ids"].pop(original_slug)
        descriptor["campaign_slug"] = "substituted-campaign"
        mutated["campaign_stable_ids"]["substituted-campaign"] = stable_id
    elif mutation == "wrong_campaign_association":
        mutated["campaigns"][0][
            "campaign_stable_id"
        ] = "campaign-wrong-association"
    elif mutation == "wrong_artifact_path_association":
        first_path = mutated["artifacts"][0]["path"]
        mutated["artifacts"][0]["path"] = mutated["artifacts"][1]["path"]
        mutated["artifacts"][1]["path"] = first_path
    else:  # pragma: no cover - the parameter table is exhaustive
        raise AssertionError(mutation)

    schema_errors = list(validator.iter_errors(mutated))
    if mutation == "missing_campaign_mapping":
        # The one-campaign control becomes empty and is also rejected by the
        # structural layer. Runtime must still reject it independently.
        assert schema_errors
    else:
        # Generic unique-by-property and cross-object relations are outside
        # core JSON Schema; the mandatory runtime layer closes that boundary.
        assert not schema_errors
    mutated_bytes = exporter_module._canonical_json_bytes(mutated)
    (output / "manifest.json").write_bytes(mutated_bytes)
    runtime_kwargs["expected_manifest_bytes"] = mutated_bytes

    with pytest.raises(CampaignCutoverExportError) as caught:
        runtime_verify(output, **runtime_kwargs)

    assert caught.value.code == "self_verification_failed"


@pytest.mark.parametrize(
    ("mutation", "unsafe_path"),
    [
        ("duplicate_family", None),
        ("missing_family", None),
        ("wrong_family_path", None),
        ("duplicate_artifact", None),
        ("duplicate_campaign", None),
        ("additional_property", None),
        ("unsafe_artifact_path", "families\\..\\accounts.json"),
        ("unsafe_artifact_path", "families/./accounts.json"),
        ("unsafe_artifact_path", "families/../accounts.json"),
        ("unsafe_artifact_path", "/families/accounts.json"),
        ("unsafe_artifact_path", "C:families/accounts.json"),
        ("unsafe_artifact_path", "families/accounts.json\x00suffix"),
    ],
)
def test_draft_2020_12_contract_rejects_manifest_mutations(
    tmp_path, mutation, unsafe_path
):
    validator, manifest = _draft_2020_12_manifest(tmp_path)
    if mutation == "duplicate_family":
        manifest["families"][1] = dict(manifest["families"][0])
    elif mutation == "missing_family":
        manifest["families"].pop()
    elif mutation == "wrong_family_path":
        manifest["families"][0]["path"] = "families/characters.json"
    elif mutation == "duplicate_artifact":
        manifest["artifacts"].append(dict(manifest["artifacts"][0]))
    elif mutation == "duplicate_campaign":
        manifest["campaigns"].append(dict(manifest["campaigns"][0]))
    elif mutation == "additional_property":
        manifest["unexpected"] = True
    elif mutation == "unsafe_artifact_path":
        manifest["artifacts"][0]["path"] = unsafe_path
    else:  # pragma: no cover - the parameter table is exhaustive
        raise AssertionError(mutation)

    with pytest.raises(ValidationError):
        validator.validate(manifest)


def _synthetic_path_contract():
    posix_root = ("posix", "/workspace/campaigns/alpha")
    posix_file = ("posix", "/workspace/campaigns/alpha/content/session.md")
    windows_root = ("windows", r"c:\campaigns\alpha")
    windows_file = ("windows", r"c:\campaigns\alpha\content\session.md")
    binding = {
        "binding": "campaign_file",
        "campaign_slug": "alpha",
        "logical_path": "content/session.md",
        "object_path": "source/objects/sha256/aa/" + "a" * 64,
        "sha256": "a" * 64,
    }
    return {
        "approved_roots": frozenset({posix_root, windows_root}),
        "binding": binding,
        "bindings": {posix_file: binding, windows_file: binding},
    }


@pytest.mark.parametrize(
    "approved_path",
    [
        "/workspace/campaigns/alpha/content/session.md",
        "file:///workspace/campaigns/alpha/content/session.md",
    ],
)
def test_platform_neutral_posix_approved_paths_bind_without_host_parser(
    approved_path,
):
    contract = _synthetic_path_contract()

    assert exporter_module._rewrite_projected_paths(
        approved_path,
        host_path_bindings=contract["bindings"],
        approved_campaign_root_keys=contract["approved_roots"],
    ) == contract["binding"]


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "/workspace/campaigns/alpha/content/Session.md",
        "/workspace/campaigns/alpha/content/missing.md",
        "/home/outside/alpha/session.md",
        "/workspace/campaigns/alpha/content/../session.md",
        "/workspace/campaigns/alpha-escape/content/session.md",
    ],
)
def test_platform_neutral_posix_adversaries_fail_closed_and_redacted(
    unsafe_path,
):
    contract = _synthetic_path_contract()

    with pytest.raises(CampaignCutoverExportError) as caught:
        exporter_module._rewrite_projected_paths(
            unsafe_path,
            host_path_bindings=contract["bindings"],
            approved_campaign_root_keys=contract["approved_roots"],
        )

    assert caught.value.code == "machine_path_leak"
    assert unsafe_path.casefold() not in caught.value.safe_message.casefold()


@pytest.mark.parametrize(
    "logical_reference",
    [
        "/app/campaigns/alpha/session/current",
        "https://example.test/app/campaigns/alpha/session/current",
        "//cdn.example.test/assets/session.md",
    ],
)
def test_logical_application_and_web_references_remain_non_path_content(
    logical_reference,
):
    contract = _synthetic_path_contract()

    assert exporter_module._rewrite_projected_paths(
        logical_reference,
        host_path_bindings=contract["bindings"],
        approved_campaign_root_keys=contract["approved_roots"],
        path_context=True,
    ) == logical_reference


def test_platform_neutral_windows_binding_and_rf6_quarantine_regression():
    contract = _synthetic_path_contract()
    approved = r"c:\campaigns\alpha\content\session.md"
    external = r"Q:\rf7-external\missing.md"

    assert exporter_module._rewrite_projected_paths(
        approved,
        host_path_bindings=contract["bindings"],
        approved_campaign_root_keys=contract["approved_roots"],
    ) == contract["binding"]
    assert exporter_module._is_quarantinable_external_machine_path(
        family="session_history",
        column="body_markdown",
        value=external,
        host_path_bindings=contract["bindings"],
        approved_campaign_root_keys=contract["approved_roots"],
    )
    with pytest.raises(CampaignCutoverExportError) as mismatched_case:
        exporter_module._rewrite_projected_paths(
            approved.swapcase(),
            host_path_bindings=contract["bindings"],
            approved_campaign_root_keys=contract["approved_roots"],
        )
    assert mismatched_case.value.code == "machine_path_leak"


def test_approved_absolute_paths_rebind_to_custodied_package_objects_and_are_deterministic(
    tmp_path,
):
    fixture = _fixture("sparse")
    fixture["files"]["content/path probe.md"] = "# Approved path target\n"
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    root = _materialize_campaign(parent, fixture)
    approved = (root / "content" / "path probe.md").resolve()
    native = str(approved)
    slash_variant = native.replace("\\", "/")
    file_uri = approved.as_uri()
    ordinary = (
        "drive C:; ratio 3:1; /campaigns/path-probe; "
        "https://example.test/home/help"
    )
    _insert_campaign_page(
        database,
        campaign_slug=fixture["campaign_slug"],
        image_path=native,
        source_ref=file_uri,
        metadata={
            "nested": [
                {"file_path": slash_variant},
                {"source_path": native},
            ],
            "ordinary": ordinary,
        },
        summary=ordinary,
    )

    output_a = tmp_path / "out-a"
    output_b = tmp_path / "out-b"
    first = _export(
        database=database,
        campaigns_parent=parent,
        fixture=fixture,
        output=output_a,
    )
    second = _export(
        database=database,
        campaigns_parent=parent,
        fixture=fixture,
        output=output_b,
    )

    assert _package_digests(output_a) == _package_digests(output_b)
    assert first.content_root_sha256 == second.content_root_sha256
    family = json.loads(
        (output_a / "families" / "campaign_pages.json").read_text(encoding="utf-8")
    )
    page_table = next(item for item in family["tables"] if item["table"] == "campaign_pages")
    row = page_table["rows"][0]
    inventory = json.loads(
        (output_a / "inventory" / "files.json").read_text(encoding="utf-8")
    )
    file_record = next(
        item for item in inventory if item["logical_path"] == "content/path probe.md"
    )
    expected_binding = {
        "binding": "campaign_file",
        "campaign_slug": fixture["campaign_slug"],
        "logical_path": file_record["logical_path"],
        "object_path": file_record["object_path"],
        "sha256": file_record["sha256"],
    }
    assert row["image_path"] == expected_binding
    assert row["source_ref"] == expected_binding
    assert row["metadata_json"]["nested"] == [
        {"file_path": expected_binding},
        {"source_path": expected_binding},
    ]
    assert row["metadata_json"]["ordinary"] == ordinary
    assert row["summary"] == ordinary

    private_forms = {native, slash_variant, file_uri}
    for artifact in output_a.rglob("*.json"):
        text = artifact.read_text(encoding="utf-8")
        for private_form in private_forms:
            assert private_form not in text
            assert json.dumps(private_form)[1:-1] not in text


def test_session_history_external_drive_paths_are_quarantined_exactly_once_without_leakage(
    tmp_path, caplog
):
    fixture = _fixture("sparse")
    fixture["files"]["content/approved-session.md"] = "# Approved session\n"
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    root = _materialize_campaign(parent, fixture)
    approved = str((root / "content" / "approved-session.md").resolve())
    private_paths = [
        r"Q:\rf6-alpha\absent-one.md",
        r"R:\rf6-bravo\absent-two.md",
        "S:/rf6-charlie/absent-three.md",
    ]
    ordinary = (
        "# Session notes\n"
        "See /campaigns/linden-pass/session/current, Rules/Travel, and "
        "https://example.test/reference."
    )
    _insert_session_articles(
        database,
        campaign_slug=fixture["campaign_slug"],
        rows=[
            (101, "First retained title", private_paths[0]),
            (102, "Second retained title", private_paths[1]),
            (103, "Third retained title", private_paths[2]),
            (110, "Ordinary retained title", ordinary),
            (111, "Approved retained title", approved),
        ],
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO campaign_dm_statblocks (
                id, campaign_slug, title, body_markdown, source_filename,
                created_at, updated_at
            ) VALUES (201, ?, 'Retained statblock', ?, 'sanitized-source.md', ?, ?)
            """,
            (
                fixture["campaign_slug"],
                r"T:\rf6-delta\absent-four.md",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )
        connection.commit()
    private_paths.append(r"T:\rf6-delta\absent-four.md")

    output = tmp_path / "out"
    _export(database=database, campaigns_parent=parent, fixture=fixture, output=output)

    family = json.loads(
        (output / "families" / "session_history.json").read_text(encoding="utf-8")
    )
    article_table = next(
        item for item in family["tables"] if item["table"] == "campaign_session_articles"
    )
    articles = {item["id"]: item for item in article_table["rows"]}
    assert all(
        articles[row_id]["body_markdown"] == QUARANTINE_SENTINEL
        for row_id in (101, 102, 103)
    )
    assert articles[101]["title"] == "First retained title"
    assert articles[102]["status"] == "staged"
    assert articles[110]["body_markdown"] == ordinary
    file_inventory = json.loads(
        (output / "inventory" / "files.json").read_text(encoding="utf-8")
    )
    approved_file = next(
        item
        for item in file_inventory
        if item["logical_path"] == "content/approved-session.md"
    )
    assert articles[111]["body_markdown"] == {
        "binding": "campaign_file",
        "campaign_slug": fixture["campaign_slug"],
        "logical_path": approved_file["logical_path"],
        "object_path": approved_file["object_path"],
        "sha256": approved_file["sha256"],
    }
    statblock_table = next(
        item for item in family["tables"] if item["table"] == "campaign_dm_statblocks"
    )
    assert statblock_table["rows"][0]["body_markdown"] == QUARANTINE_SENTINEL
    assert statblock_table["rows"][0]["source_filename"] == "sanitized-source.md"

    dispositions = json.loads(
        (output / "inventory" / "dispositions.json").read_text(encoding="utf-8")
    )
    expected = [
        {
            "custody": "source/database.sqlite3",
            "disposition": "unsupported_quarantined",
            "family": "session_history",
            "field": "body_markdown",
            "locator": {"id": row_id},
            "original_value_emitted": False,
            "raw_snapshot_preserved": True,
            "reason": "external_machine_path",
            "table": table,
        }
        for table, row_id in (
            ("campaign_dm_statblocks", 201),
            ("campaign_session_articles", 101),
            ("campaign_session_articles", 102),
            ("campaign_session_articles", 103),
        )
    ]
    assert dispositions["field_quarantines"] == expected
    unsupported_records = sum(
        1
        for collection in (
            "blobs",
            "check_constraints",
            "columns",
            "field_quarantines",
            "files",
            "rows",
            "schema_objects",
            "tables",
        )
        for item in dispositions[collection]
        if item["disposition"] == "unsupported_quarantined"
    )
    assert dispositions["totals"]["unsupported_quarantined"] == unsupported_records
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads(
        (output / "evidence" / "safe-summary.json").read_text(encoding="utf-8")
    )
    assert manifest["disposition_totals"] == dispositions["totals"]
    assert summary["disposition_totals"] == dispositions["totals"]
    tables = json.loads(
        (output / "inventory" / "tables.json").read_text(encoding="utf-8")
    )
    table_counts = {item["table"]: item["quarantined_field_count"] for item in tables}
    assert table_counts["campaign_session_articles"] == 3
    assert table_counts["campaign_dm_statblocks"] == 1
    assert sum(table_counts.values()) == len(expected)
    with sqlite3.connect(output / "source" / "database.sqlite3") as snapshot:
        preserved_articles = [
            row[0]
            for row in snapshot.execute(
                "SELECT body_markdown FROM campaign_session_articles "
                "WHERE id IN (101, 102, 103) ORDER BY id"
            ).fetchall()
        ]
        preserved_statblock = snapshot.execute(
            "SELECT body_markdown FROM campaign_dm_statblocks WHERE id = 201"
        ).fetchone()[0]
    assert preserved_articles == private_paths[:3]
    assert preserved_statblock == private_paths[3]

    non_snapshot_bytes = b"\n".join(
        path.read_bytes()
        for path in output.rglob("*")
        if path.is_file()
        and path.relative_to(output).as_posix() != "source/database.sqlite3"
    )
    for private_path in private_paths:
        assert private_path.encode("utf-8") not in non_snapshot_bytes
        assert json.dumps(private_path)[1:-1].encode("utf-8") not in non_snapshot_bytes
        private_hash = hashlib.sha256(private_path.encode("utf-8")).hexdigest()
        assert private_hash.encode("ascii") not in non_snapshot_bytes
        for component in ("rf6-alpha", "rf6-bravo", "rf6-charlie", "rf6-delta"):
            assert component.encode("ascii") not in non_snapshot_bytes
    assert all(
        private_path.casefold() not in caplog.text.casefold()
        for private_path in private_paths
    )


def test_external_drive_path_quarantine_is_deterministic_across_row_order_and_private_values(
    tmp_path
):
    fixture = _fixture("sparse")
    rows_a = [
        (301, "First", r"Q:\rf6-one\missing.md"),
        (302, "Second", r"R:\rf6-two\missing.md"),
        (303, "Third", r"S:\rf6-tri\missing.md"),
    ]
    rows_b = [
        (301, "First", r"V:\alt-one\missing.md"),
        (302, "Second", r"W:\alt-two\missing.md"),
        (303, "Third", r"X:\alt-tri\missing.md"),
    ]
    outputs = []
    for name, rows, reverse in (("a", rows_a, False), ("b", rows_b, True)):
        case = tmp_path / name
        case.mkdir()
        database = case / "source.sqlite3"
        _create_full_schema_database(database)
        parent = case / "campaigns"
        _materialize_campaign(parent, fixture, reverse=reverse)
        _insert_session_articles(
            database,
            campaign_slug=fixture["campaign_slug"],
            rows=rows,
            reverse=reverse,
        )
        output = case / "out"
        _export(database=database, campaigns_parent=parent, fixture=fixture, output=output)
        outputs.append(output)

    first, second = outputs
    comparable = {
        path.relative_to(first).as_posix()
        for path in first.rglob("*")
        if path.is_file()
    } - {"manifest.json", "source/database.sqlite3"}
    assert comparable == {
        path.relative_to(second).as_posix()
        for path in second.rglob("*")
        if path.is_file()
    } - {"manifest.json", "source/database.sqlite3"}
    assert all(
        (first / relative).read_bytes() == (second / relative).read_bytes()
        for relative in comparable
    )

    manifests = [
        json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        for output in outputs
    ]
    assert manifests[0]["snapshot"]["sha256"] != manifests[1]["snapshot"]["sha256"]
    for manifest in manifests:
        manifest.pop("content_root_digest")
        manifest["snapshot"] = {"path": manifest["snapshot"]["path"]}
        manifest["artifacts"] = [
            {"path": item["path"]}
            if item["path"] == "source/database.sqlite3"
            else item
            for item in manifest["artifacts"]
        ]
    assert manifests[0] == manifests[1]


@pytest.mark.parametrize(
    "unsafe_body",
    [
        r"prefix C:\rf6-embedded\missing.md suffix",
        r"\\server\rf6-share\missing.md",
        r"\\?\C:\rf6-device\missing.md",
        "file:///C:/rf6-uri/missing.md",
        "/home/rf6-posix/missing.md",
        r"Q:\rf6-invalid\bad<name>.md",
        "Q:\\rf6-multiline\\missing.md\n# trailing markdown",
    ],
)
def test_other_session_body_machine_path_forms_remain_fail_closed_without_echo(
    tmp_path, unsafe_body
):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    _insert_session_articles(
        database,
        campaign_slug=fixture["campaign_slug"],
        rows=[(401, "Unsafe", unsafe_body)],
    )

    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(
            database=database,
            campaigns_parent=parent,
            fixture=fixture,
            output=tmp_path / "out",
        )

    assert caught.value.code == "machine_path_leak"
    assert unsafe_body.casefold() not in caught.value.safe_message.casefold()
    assert not (tmp_path / "out").exists()


def test_uninventoried_path_inside_approved_campaign_root_remains_fail_closed(tmp_path):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    root = _materialize_campaign(parent, fixture)
    missing = str((root / "content" / "not-in-inventory.md").resolve())
    _insert_session_articles(
        database,
        campaign_slug=fixture["campaign_slug"],
        rows=[(402, "Missing approved-root file", missing)],
    )

    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(
            database=database,
            campaigns_parent=parent,
            fixture=fixture,
            output=tmp_path / "out",
        )

    assert caught.value.code == "machine_path_leak"
    assert missing.casefold() not in caught.value.safe_message.casefold()


def test_reserved_field_quarantine_sentinel_cannot_be_supplied_as_source_text(tmp_path):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    _insert_session_articles(
        database,
        campaign_slug=fixture["campaign_slug"],
        rows=[(403, "Reserved sentinel", QUARANTINE_SENTINEL)],
    )

    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(
            database=database,
            campaigns_parent=parent,
            fixture=fixture,
            output=tmp_path / "out",
        )

    assert caught.value.code == "reserved_quarantine_sentinel"
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "mutation",
    ["sentinel", "reason", "row_binding", "count", "original_value_emitted", "table_count"],
)
def test_field_quarantine_tamper_fails_self_verification_without_publication(
    tmp_path, monkeypatch, mutation
):
    fixture = _fixture("sparse")
    private_path = r"Q:\rf6-tamper\missing.md"
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    _insert_session_articles(
        database,
        campaign_slug=fixture["campaign_slug"],
        rows=[(501, "Tamper target", private_path)],
    )
    original_write = exporter_module._write_canonical_json

    def tampering_write(path, value):
        altered = json.loads(json.dumps(value))
        relative = path.as_posix()
        if mutation == "sentinel" and relative.endswith("families/session_history.json"):
            table = next(
                item for item in altered["tables"] if item["table"] == "campaign_session_articles"
            )
            table["rows"][0]["body_markdown"] = "[substituted]"
        elif relative.endswith("inventory/dispositions.json"):
            item = altered["field_quarantines"][0]
            if mutation == "reason":
                item["reason"] = "substituted"
            elif mutation == "row_binding":
                item["locator"]["id"] += 1
            elif mutation == "count":
                altered["totals"]["unsupported_quarantined"] += 1
            elif mutation == "original_value_emitted":
                item["original_value_emitted"] = True
        elif mutation == "table_count" and relative.endswith("inventory/tables.json"):
            table = next(
                item for item in altered if item["table"] == "campaign_session_articles"
            )
            table["quarantined_field_count"] += 1
        original_write(path, altered)

    monkeypatch.setattr(exporter_module, "_write_canonical_json", tampering_write)
    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(
            database=database,
            campaigns_parent=parent,
            fixture=fixture,
            output=tmp_path / "out",
        )

    assert caught.value.code == "self_verification_failed"
    assert private_path.casefold() not in caught.value.safe_message.casefold()
    assert not (tmp_path / "out").exists()
    assert not list(tmp_path.glob(".out.cutover-stage-*"))


@pytest.mark.parametrize(
    "private_path",
    [
        r"C:\PrivateRoot\nested\source.txt",
        "c:/privateroot/NESTED/source.txt",
        r"\\server\private-share\source.txt",
        "//server/private-share/source.txt",
        r"\\?\C:\PrivateRoot\source.txt",
        r"\\.\C:\PrivateRoot\source.txt",
        "//?/C:/PrivateRoot/source.txt",
        "/home/private-user/source.txt",
        "/opt/private-root/source.txt",
        "/custom/private-root/source.txt",
        "file:///C:/PrivateRoot/source.txt",
        "file:///C:/PrivateRoot/source.txt?unsafe=1",
        "FILE://server/private-share/source.txt",
        r"prefix C:\PrivateRoot\source.txt suffix",
    ],
)
def test_nonbindable_host_path_forms_fail_closed_without_echo(
    tmp_path, private_path
):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO character_state VALUES (?, 'hero', 1, ?, ?, NULL)",
            (
                fixture["campaign_slug"],
                json.dumps({"nested": [{"source_path": private_path}]}),
                "2026-01-01T00:00:00Z",
            ),
        )
        connection.commit()
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    output = tmp_path / "out"

    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(
            database=database,
            campaigns_parent=parent,
            fixture=fixture,
            output=output,
        )

    assert caught.value.code == "machine_path_leak"
    assert private_path.casefold() not in caught.value.safe_message.casefold()
    assert "privateroot" not in caught.value.safe_message.casefold()
    assert not output.exists()
    assert not list(tmp_path.glob(".out.cutover-stage-*"))


def test_projected_path_binding_tamper_fails_self_verification_without_publication(
    tmp_path, monkeypatch
):
    fixture = _fixture("sparse")
    fixture["files"]["content/path probe.md"] = "# Approved path target\n"
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    root = _materialize_campaign(parent, fixture)
    approved = (root / "content" / "path probe.md").resolve()
    _insert_campaign_page(
        database,
        campaign_slug=fixture["campaign_slug"],
        image_path=str(approved),
    )
    original_write = exporter_module._write_canonical_json

    def tampering_write(path, value):
        if path.as_posix().endswith("families/campaign_pages.json"):
            page_table = next(
                item for item in value["tables"] if item["table"] == "campaign_pages"
            )
            page_table["rows"][0]["image_path"]["object_path"] = (
                "source/objects/sha256/00/" + "0" * 64
            )
        original_write(path, value)

    monkeypatch.setattr(exporter_module, "_write_canonical_json", tampering_write)
    output = tmp_path / "out"
    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(
            database=database,
            campaigns_parent=parent,
            fixture=fixture,
            output=output,
        )

    assert caught.value.code == "self_verification_failed"
    assert str(approved).casefold() not in caught.value.safe_message.casefold()
    assert not output.exists()
    assert not list(tmp_path.glob(".out.cutover-stage-*"))


@pytest.mark.skipif(os.name != "posix", reason="native POSIX mode contract")
def test_posix_package_modes_are_private_and_umask_independent(tmp_path):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    output = tmp_path / "out"
    previous_umask = os.umask(0)
    try:
        _export(
            database=database,
            campaigns_parent=parent,
            fixture=fixture,
            output=output,
        )
    finally:
        os.umask(previous_umask)

    paths = [output, *output.rglob("*")]
    assert all(
        stat.S_IMODE(path.lstat().st_mode) == (0o700 if path.is_dir() else 0o600)
        for path in paths
    )
    assert stat.S_IMODE((output / "source").lstat().st_mode) == 0o700
    assert stat.S_IMODE((output / "source" / "objects").lstat().st_mode) == 0o700


@pytest.mark.skipif(os.name != "posix", reason="native POSIX mode contract")
def test_posix_stage_is_private_before_atomic_publication(tmp_path, monkeypatch):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    original_publish = exporter_module._publish_stage
    inspected = False

    def inspect_then_publish(stage, output):
        nonlocal inspected
        inspected = True
        for path in [stage, *stage.rglob("*")]:
            details = path.lstat()
            assert not stat.S_ISLNK(details.st_mode)
            expected = 0o700 if stat.S_ISDIR(details.st_mode) else 0o600
            assert stat.S_IMODE(details.st_mode) == expected
        original_publish(stage, output)

    monkeypatch.setattr(exporter_module, "_publish_stage", inspect_then_publish)
    _export(
        database=database,
        campaigns_parent=parent,
        fixture=fixture,
        output=tmp_path / "out",
    )
    assert inspected


@pytest.mark.skipif(os.name != "posix", reason="native POSIX mode contract")
def test_posix_private_mode_application_never_follows_links(tmp_path):
    target = tmp_path / "target"
    target.write_text("target", encoding="utf-8")
    os.chmod(target, 0o644)
    link = tmp_path / "link"
    link.symlink_to(target)

    with pytest.raises(CampaignCutoverExportError) as caught:
        exporter_module._make_private(link)

    assert caught.value.code == "private_storage_unavailable"
    assert stat.S_IMODE(target.lstat().st_mode) == 0o644


@pytest.mark.skipif(os.name != "posix", reason="native POSIX mode contract")
def test_posix_injected_fchmod_failure_refuses_capture(tmp_path, monkeypatch):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)

    def refuse_fchmod(*_):
        raise OSError("injected chmod refusal")

    monkeypatch.setattr(exporter_module.os, "fchmod", refuse_fchmod)
    output = tmp_path / "out"
    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(
            database=database,
            campaigns_parent=parent,
            fixture=fixture,
            output=output,
        )

    assert caught.value.code == "private_storage_unavailable"
    assert not output.exists()
    assert not list(tmp_path.glob(".out.cutover-stage-*"))


@pytest.mark.skipif(os.name != "posix", reason="native POSIX mode contract")
def test_posix_mode_drift_fails_self_verification_without_publication(
    tmp_path, monkeypatch
):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    parent = tmp_path / "campaigns"
    _materialize_campaign(parent, fixture)
    original_verify = exporter_module._self_verify_package

    def drift_then_verify(stage, **kwargs):
        os.chmod(stage / "source", 0o755)
        original_verify(stage, **kwargs)

    monkeypatch.setattr(exporter_module, "_self_verify_package", drift_then_verify)
    output = tmp_path / "out"
    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(
            database=database,
            campaigns_parent=parent,
            fixture=fixture,
            output=output,
        )

    assert caught.value.code == "self_verification_failed"
    assert not output.exists()
    assert not list(tmp_path.glob(".out.cutover-stage-*"))


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


def test_rf8_dependency_union_includes_all_policy_sources_and_referenced_users(tmp_path):
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    now = "2026-01-01T00:00:00Z"
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        connection.executemany(
            "INSERT INTO users (id, email, display_name, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'active', ?, ?)",
            [
                (user_id, f"sanitized-{user_id}@example.invalid", f"Sanitized {user_id}", now, now)
                for user_id in range(101, 106)
            ],
        )
        connection.execute(
            "INSERT INTO campaign_system_policies "
            "(campaign_slug, library_slug, status, proprietary_acknowledged_by_user_id, "
            "created_at, updated_at, updated_by_user_id) "
            "VALUES ('selected', 'library-policy', 'active', 101, ?, ?, 102)",
            (now, now),
        )
        connection.execute(
            "INSERT INTO campaign_enabled_sources "
            "(campaign_slug, library_slug, source_id, default_visibility, updated_at, updated_by_user_id) "
            "VALUES ('selected', 'library-enabled', 'SRC', 'players', ?, 103)",
            (now,),
        )
        connection.execute(
            "INSERT INTO campaign_entry_overrides "
            "(campaign_slug, library_slug, entry_key, updated_at, updated_by_user_id) "
            "VALUES ('selected', 'library-override', 'entry', ?, 104)",
            (now,),
        )
        connection.execute(
            "INSERT INTO systems_shared_entry_edit_events "
            "(campaign_slug, library_slug, source_id, entry_key, entry_slug, actor_user_id, "
            "audit_event_type, created_at) "
            "VALUES ('selected', 'library-shared-edit', 'SRC', 'entry', 'entry', 105, 'edit', ?)",
            (now,),
        )
        connection.commit()
        dependencies = exporter_module._collect_scope_dependencies(
            connection, {"selected"}
        )

    assert dependencies["libraries"] == {
        "library-policy",
        "library-enabled",
        "library-override",
        "library-shared-edit",
    }
    assert dependencies["users"] == {101, 102, 103, 104, 105}


def test_rf8_secret_and_custody_only_rows_emit_no_value_derived_hash(tmp_path):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    now = "2026-01-01T00:00:00Z"
    password = "sanitized-password-material.invalid"
    token = "sanitized-token-material.invalid"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO users (id, email, display_name, status, password_hash, created_at, updated_at) "
            "VALUES (501, 'sanitized-501@example.invalid', 'Sanitized 501', 'active', ?, ?, ?)",
            (password, now, now),
        )
        connection.execute(
            "INSERT INTO campaign_memberships "
            "(user_id, campaign_slug, role, status, created_at, updated_at) "
            "VALUES (501, ?, 'player', 'active', ?, ?)",
            (fixture["campaign_slug"], now, now),
        )
        connection.execute(
            "INSERT INTO invite_tokens "
            "(id, user_id, token_hash, expires_at, created_at) VALUES (601, 501, ?, ?, ?)",
            (token, now, now),
        )
        connection.commit()
    campaigns_parent = tmp_path / "campaigns"
    _materialize_campaign(campaigns_parent, fixture)
    output = tmp_path / "out"
    _export(
        database=database,
        campaigns_parent=campaigns_parent,
        fixture=fixture,
        output=output,
    )
    json_text = "\n".join(
        path.read_text(encoding="utf-8") for path in output.rglob("*.json")
    )
    for private_value in (password, token):
        assert private_value not in json_text
        assert hashlib.sha256(private_value.encode()).hexdigest() not in json_text
    dispositions = json.loads(
        (output / "inventory" / "dispositions.json").read_text(encoding="utf-8")
    )
    invite = next(item for item in dispositions["rows"] if item["table"] == "invite_tokens")
    assert set(invite) == {"disposition", "family", "locator", "reason", "table"}


def test_rf8_projected_foreign_key_may_not_point_only_to_sealed_row(tmp_path):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    now = "2026-01-01T00:00:00Z"
    with sqlite3.connect(database) as connection:
        session = connection.execute(
            "INSERT INTO campaign_sessions (campaign_slug, status, started_at) "
            "VALUES (?, 'active', ?)",
            (fixture["campaign_slug"], now),
        )
        sealed_article = connection.execute(
            "INSERT INTO campaign_session_articles "
            "(campaign_slug, title, body_markdown, status, created_at) "
            "VALUES ('sealed-campaign', 'Sealed', 'Sanitized', 'staged', ?)",
            (now,),
        )
        connection.execute(
            "INSERT INTO campaign_session_messages "
            "(session_id, campaign_slug, message_type, body_text, recipient_scope, "
            "author_display_name, article_id, created_at) "
            "VALUES (?, ?, 'article_reveal', 'Sanitized', 'global', "
            "'Sanitized Author', ?, ?)",
            (
                session.lastrowid,
                fixture["campaign_slug"],
                sealed_article.lastrowid,
                now,
            ),
        )
        connection.commit()
    campaigns_parent = tmp_path / "campaigns"
    _materialize_campaign(campaigns_parent, fixture)
    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(
            database=database,
            campaigns_parent=campaigns_parent,
            fixture=fixture,
            output=tmp_path / "out",
        )
    assert caught.value.code == "dependency_closure_failure"
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "secret_key",
    [
        "password",
        "TOKEN-HASH",
        "session secret",
        "api.key",
        "APIKey",
        "ACCESS TOKEN",
        "accessToken",
        "refresh_token",
        "client-secret",
        "Authorization",
        "COOKIE",
        "private key",
        "secret",
    ],
)
def test_rf8_normalized_nested_secret_keys_are_denied(secret_key):
    with pytest.raises(CampaignCutoverExportError) as caught:
        exporter_module._reject_secret_keys(
            {"outer": [{"inner": {secret_key: "sanitized-secret.invalid"}}]}
        )
    assert caught.value.code == "secret_leak"


@pytest.mark.parametrize(
    "safe_key",
    [
        "password_policy",
        "token_hash_algorithm",
        "session_secretary",
        "api_key_label",
        "access_token_expiry",
        "cookie_policy",
        "private_keyboard",
        "secretary",
    ],
)
def test_rf8_secret_key_near_misses_are_not_substring_rejected(safe_key):
    exporter_module._reject_secret_keys({safe_key: "sanitized-safe-control"})


@pytest.mark.parametrize(
    "unsafe_path",
    [
        r"C:relative\\host.txt",
        r"\\rooted\\host.txt",
        r"\\server\\share\\host.txt",
        r"\\?\\C:\\extended\\host.txt",
        r"\\.\\C:\\device\\host.txt",
        "../../escape.txt",
        r"safe\\..\\escape.txt",
        "safe/./escape.txt",
        "safe//ambiguous.txt",
        r"safe\\ambiguous.txt",
        "safe/trailing/",
        "/workspace//campaigns/alpha/content/session.md",
        r"C:\campaigns\alpha\content\..\content\session.md",
        "/custom-host-root/private.txt",
        "safe/%2e%2e/escape.txt",
        "safe\x00name.txt",
    ],
)
def test_rf8_cross_platform_path_grammar_refuses_redacted(unsafe_path):
    contract = _synthetic_path_contract()
    with pytest.raises(CampaignCutoverExportError) as caught:
        exporter_module._rewrite_projected_paths(
            unsafe_path,
            host_path_bindings=contract["bindings"],
            approved_campaign_root_keys=contract["approved_roots"],
            path_context=True,
        )
    assert caught.value.code == "machine_path_leak"
    assert unsafe_path not in caught.value.safe_message


def test_rf8_unapproved_missing_check_refuses_even_when_table_is_empty(tmp_path):
    database = tmp_path / "source.sqlite3"
    frozen = (
        "role TEXT NOT NULL CHECK (role IN ('dm', 'player', 'observer'))"
    )
    schema_sql = CURRENT_SCHEMA_SQL.replace(frozen, "role TEXT NOT NULL", 1)
    assert schema_sql != CURRENT_SCHEMA_SQL
    with sqlite3.connect(database) as connection:
        connection.executescript(schema_sql)
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, "
            "checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO schema_migrations VALUES (1, '0001_sanitized', ?, ?)",
            ("a" * 64, "2026-01-01T00:00:00Z"),
        )
        connection.row_factory = sqlite3.Row
        with pytest.raises(CampaignCutoverExportError) as caught:
            exporter_module._inspect_schema(connection)
    assert caught.value.code == "schema_constraint_mismatch"


def test_rf8_refusal_does_not_create_missing_output_parent(tmp_path):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    campaigns_parent = tmp_path / "campaigns"
    _materialize_campaign(campaigns_parent, fixture)
    missing_parent = tmp_path / "missing-parent"
    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(
            database=database,
            campaigns_parent=campaigns_parent,
            fixture=fixture,
            output=missing_parent / "out",
        )
    assert caught.value.code == "output_parent_missing"
    assert not missing_parent.exists()


def test_rf8_cleanup_failure_is_structured_and_retains_private_evidence(
    tmp_path, monkeypatch
):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    campaigns_parent = tmp_path / "campaigns"
    _materialize_campaign(campaigns_parent, fixture)
    original_rmtree = exporter_module.shutil.rmtree

    def deny_stage_cleanup(path, *args, **kwargs):
        if Path(path).name.startswith(".out.cutover-stage-"):
            raise PermissionError("sanitized-cleanup-denial")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(exporter_module.shutil, "rmtree", deny_stage_cleanup)
    monkeypatch.setattr(
        exporter_module,
        "_project_snapshot",
        lambda **_: (_ for _ in ()).throw(ValueError("sanitized-projection-fault")),
    )
    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(
            database=database,
            campaigns_parent=campaigns_parent,
            fixture=fixture,
            output=tmp_path / "out",
        )
    assert caught.value.code == "private_residue_retained"
    assert len(list(tmp_path.glob(".out.cutover-stage-*"))) == 1


def test_rf8_source_directory_metadata_drift_refuses_without_publication(
    tmp_path, monkeypatch
):
    fixture = _fixture("sparse")
    database = tmp_path / "source.sqlite3"
    _create_full_schema_database(database)
    campaigns_parent = tmp_path / "campaigns"
    campaign_root = _materialize_campaign(campaigns_parent, fixture)
    original_project = exporter_module._project_snapshot

    def drift_directory_after_projection(**kwargs):
        projected = original_project(**kwargs)
        details = campaign_root.stat()
        os.utime(
            campaign_root,
            ns=(details.st_atime_ns, details.st_mtime_ns + 1_000_000_000),
        )
        return projected

    monkeypatch.setattr(
        exporter_module, "_project_snapshot", drift_directory_after_projection
    )
    with pytest.raises(CampaignCutoverExportError) as caught:
        _export(
            database=database,
            campaigns_parent=campaigns_parent,
            fixture=fixture,
            output=tmp_path / "out",
        )
    assert caught.value.code == "source_drift"
    assert not (tmp_path / "out").exists()
    assert not list(tmp_path.glob(".out.cutover-stage-*"))


@pytest.mark.parametrize(
    "sddl",
    [
        "O:SYD:PAI(A;ID;FW;;;S-1-1-0)",
        "O:SYD:P(A;;0x1301bf;;;S-1-5-11)",
        "O:SYD:P(A;;FA;;;S-1-5-32-545)",
    ],
)
def test_rf8_windows_acl_parser_detects_inherited_explicit_and_compound_broad_writes(
    monkeypatch, sddl
):
    sid = "S-1-5-21-1"
    monkeypatch.setattr(
        exporter_module,
        "_windows_acl_sddl",
        lambda _: f"{sddl}(A;;FA;;;{sid})",
    )
    with pytest.raises(CampaignCutoverExportError) as caught:
        exporter_module._verify_windows_private_acl(Path("sanitized.invalid"), sid)
    assert caught.value.code == "private_storage_unavailable"


def test_rf8_windows_acl_private_sid_and_drift_semantics(monkeypatch):
    sid = "S-1-5-21-1-2-3-1001"
    monkeypatch.setattr(
        exporter_module,
        "_windows_acl_sddl",
        lambda _: f"O:{sid}D:P(A;;FA;;;{sid})",
    )
    exporter_module._verify_windows_private_acl(Path("sanitized.invalid"), sid)
    monkeypatch.setattr(
        exporter_module,
        "_windows_acl_sddl",
        lambda _: f"O:{sid}D:P(A;;FA;;;{sid})(A;;FW;;;S-1-5-21-9-8-7-1002)",
    )
    with pytest.raises(CampaignCutoverExportError) as other_principal:
        exporter_module._verify_windows_private_acl(Path("sanitized.invalid"), sid)
    assert other_principal.value.code == "private_storage_unavailable"
    monkeypatch.setattr(
        exporter_module,
        "_windows_acl_sddl",
        lambda _: f"O:{sid}D:P(D;;FW;;;AU)(A;;FA;;;{sid})",
    )
    with pytest.raises(CampaignCutoverExportError) as denied_effective_rights:
        exporter_module._verify_windows_private_acl(Path("sanitized.invalid"), sid)
    assert denied_effective_rights.value.code == "private_storage_unavailable"
    monkeypatch.setattr(
        exporter_module,
        "_windows_acl_sddl",
        lambda _: f"O:{sid}D:AI(A;ID;FA;;;{sid})",
    )
    with pytest.raises(CampaignCutoverExportError) as drift:
        exporter_module._verify_windows_private_acl(Path("sanitized.invalid"), sid)
    assert drift.value.code == "private_storage_unavailable"
