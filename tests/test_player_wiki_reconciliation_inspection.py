from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys

import pytest

import player_wiki.player_wiki_reconciliation_inspection as inspection
from player_wiki.migrations import MIGRATIONS
from player_wiki.player_wiki_reconciliation_inspection import (
    InspectionFilters,
    inspect_player_wiki_reconciliation,
)


NOW = "2026-07-18T12:00:00+00:00"


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fixture(tmp_path: Path, *, version: int = 9) -> tuple[Path, Path, Path, Path]:
    database = tmp_path / "state" / "wiki.sqlite3"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.executescript(MIGRATIONS[version - 1].payload.schema_sql)
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
        connection.executemany(
            "INSERT INTO schema_migrations(version,name,checksum,applied_at) VALUES(?,?,?,?)",
            [
                (migration.version, migration.name, migration.checksum, NOW)
                for migration in MIGRATIONS[:version]
            ],
        )
        connection.commit()
    campaigns = tmp_path / "campaigns"
    campaign = campaigns / "test-campaign"
    content = campaign / "content"
    assets = campaign / "assets"
    content.mkdir(parents=True)
    assets.mkdir()
    (campaign / "campaign.yaml").write_text(
        "title: Test Campaign\nslug: test-campaign\nplayer_content_dir: content\nasset_dir: assets\n",
        encoding="utf-8",
    )
    return database, campaigns, content, assets


def _insert_publication(
    database: Path,
    *,
    operation_id: str,
    page_ref: str,
    state: str,
    desired: bytes,
    previous_markdown: str = "",
    primary_authority: str = "markdown",
    desired_primary_ref: str | None = None,
    previous_primary: str | None = None,
    desired_primary: str | None = None,
) -> None:
    desired_markdown = _digest(desired)
    primary_ref = desired_primary_ref or f"{page_ref}.md"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO player_wiki_reconciliation_operations (
                operation_id,campaign_slug,page_ref,operation_kind,primary_authority,
                desired_primary_ref,previous_primary_digest,desired_primary_digest,
                previous_markdown_digest,desired_markdown_digest,desired_markdown,
                audit_event_type,audit_actor_user_id,audit_metadata_json,state,error_code,
                created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                operation_id,
                "test-campaign",
                page_ref,
                "update",
                primary_authority,
                primary_ref,
                previous_primary if previous_primary is not None else previous_markdown,
                desired_primary if desired_primary is not None else desired_markdown,
                previous_markdown,
                desired_markdown,
                desired if state in {"prepared", "conflict"} else None,
                None,
                None,
                None,
                state,
                "",
                NOW,
                NOW,
            ),
        )
        connection.commit()


def _insert_deletion(
    database: Path,
    *,
    operation_id: str,
    page_ref: str,
    state: str,
    source: bytes,
) -> str:
    tombstone_ref = (
        f".{operation_id}.del"
        if "/" not in page_ref
        else f"{page_ref.rsplit('/', 1)[0]}/.{operation_id}.del"
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO player_wiki_deletion_operations (
                operation_id,campaign_slug,page_ref,source_ref,tombstone_ref,
                source_sha256,source_size,operation_kind,audit_event_type,
                audit_actor_user_id,audit_metadata_json,state,error_code,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                operation_id,
                "test-campaign",
                page_ref,
                f"{page_ref}.md",
                tombstone_ref,
                _digest(source),
                len(source),
                "api_delete",
                None,
                None,
                None,
                state,
                "",
                NOW,
                NOW,
            ),
        )
        connection.commit()
    return tombstone_ref


def _inspect(database: Path, campaigns: Path, **kwargs):
    return inspect_player_wiki_reconciliation(
        database_path=database,
        campaigns_dir=campaigns,
        filters=InspectionFilters(**kwargs),
    )


@pytest.mark.parametrize(
    ("arrangement", "classification"),
    [
        ("previous", "precommit_abortable"),
        ("desired", "forward_recoverable"),
        ("third", "manual_conflict"),
    ],
)
@pytest.mark.parametrize("schema_version", [4, 5, 6, 7, 8, 9])
def test_publication_prepared_markdown_classifications(
    tmp_path, arrangement, classification, schema_version
):
    database, campaigns, content, _assets = _fixture(tmp_path, version=schema_version)
    previous = b"previous"
    desired = b"desired"
    page_ref = "notes/page"
    target = content / "notes" / "page.md"
    target.parent.mkdir()
    payload = {"previous": previous, "desired": desired, "third": b"third"}[arrangement]
    target.write_bytes(payload)
    _insert_publication(
        database,
        operation_id="1" * 32,
        page_ref=page_ref,
        state="prepared",
        desired=desired,
        previous_markdown=_digest(previous),
    )

    report, exit_code = _inspect(database, campaigns)

    assert exit_code == 1
    assert report["operations"][0]["classification"] == classification


@pytest.mark.parametrize("schema_version", [4, 5, 6, 7, 8, 9])
def test_publication_desired_equals_previous_uses_forward_equivalence(
    tmp_path, schema_version
):
    database, campaigns, content, _assets = _fixture(tmp_path, version=schema_version)
    desired = b"same"
    target = content / "same.md"
    target.write_bytes(desired)
    digest = _digest(desired)
    _insert_publication(
        database,
        operation_id="2" * 32,
        page_ref="same",
        state="prepared",
        desired=desired,
        previous_markdown=digest,
    )

    report, _ = _inspect(database, campaigns)

    assert report["operations"][0]["classification"] == "forward_recoverable"


@pytest.mark.parametrize(
    ("markdown_payload", "classification"),
    [
        (b"previous markdown", "forward_recoverable_requires_markdown_publish"),
        (b"desired markdown", "forward_recoverable"),
        (b"third markdown", "manual_conflict"),
    ],
)
@pytest.mark.parametrize("schema_version", [4, 5, 6, 7, 8, 9])
def test_publication_image_primary_classifications(
    tmp_path, markdown_payload, classification, schema_version
):
    database, campaigns, content, assets = _fixture(tmp_path, version=schema_version)
    previous_markdown = b"previous markdown"
    desired_markdown = b"desired markdown"
    desired_image = b"desired image"
    markdown = content / "image-page.md"
    markdown.write_bytes(markdown_payload)
    image = assets / "page.webp"
    image.write_bytes(desired_image)
    _insert_publication(
        database,
        operation_id="3" * 32,
        page_ref="image-page",
        state="prepared",
        desired=desired_markdown,
        previous_markdown=_digest(previous_markdown),
        primary_authority="image",
        desired_primary_ref="page.webp",
        previous_primary=_digest(b"previous image"),
        desired_primary=_digest(desired_image),
    )

    report, _ = _inspect(database, campaigns)

    assert report["operations"][0]["classification"] == classification


@pytest.mark.parametrize(
    ("markdown_payload", "classification", "reason_code"),
    [
        (b"previous markdown", "precommit_abortable", "primary_matches_previous"),
        (
            b"desired markdown",
            "manual_conflict",
            "image_previous_markdown_changed",
        ),
        (
            b"third markdown",
            "manual_conflict",
            "image_previous_markdown_changed",
        ),
    ],
)
def test_image_previous_requires_markdown_previous_for_precommit_abandonment(
    tmp_path, markdown_payload, classification, reason_code
):
    database, campaigns, content, assets = _fixture(tmp_path)
    previous_markdown = b"previous markdown"
    desired_markdown = b"desired markdown"
    previous_image = b"previous image"
    (content / "image-previous.md").write_bytes(markdown_payload)
    (assets / "image-previous.webp").write_bytes(previous_image)
    _insert_publication(
        database,
        operation_id="8" * 32,
        page_ref="image-previous",
        state="prepared",
        desired=desired_markdown,
        previous_markdown=_digest(previous_markdown),
        primary_authority="image",
        desired_primary_ref="image-previous.webp",
        previous_primary=_digest(previous_image),
        desired_primary=_digest(b"desired image"),
    )

    report, _ = _inspect(database, campaigns)

    operation = report["operations"][0]
    assert operation["classification"] == classification
    assert operation["reason_code"] == reason_code


@pytest.mark.parametrize(
    ("state", "file_payload", "classification"),
    [
        ("repository_pending", b"desired", "refresh_cleanup_retryable"),
        ("repository_pending", b"changed", "manual_attention"),
        ("conflict", b"changed", "manual_repair_or_abandon"),
    ],
)
@pytest.mark.parametrize("schema_version", [4, 5, 6, 7, 8, 9])
def test_publication_pending_and_conflict_classifications(
    tmp_path, state, file_payload, classification, schema_version
):
    database, campaigns, content, _assets = _fixture(tmp_path, version=schema_version)
    desired = b"desired"
    (content / "page.md").write_bytes(file_payload)
    _insert_publication(
        database,
        operation_id="4" * 32,
        page_ref="page",
        state=state,
        desired=desired,
        previous_markdown=_digest(b"previous"),
    )

    report, _ = _inspect(database, campaigns)

    assert report["operations"][0]["classification"] == classification


@pytest.mark.parametrize(
    ("state", "arrangement", "classification"),
    [
        ("prepared", "source", "precommit_abortable"),
        ("prepared", "tombstone", "forward_recoverable"),
        ("prepared", "third", "manual_conflict"),
        ("repository_pending", "tombstone", "refresh_cleanup_retryable"),
        ("repository_pending", "absent", "refresh_cleanup_retryable"),
        ("repository_pending", "source", "manual_attention"),
        ("conflict", "third", "manual_repair_or_abandon"),
    ],
)
@pytest.mark.parametrize("schema_version", [4, 5, 6, 7, 8, 9])
def test_deletion_classifications(
    tmp_path, state, arrangement, classification, schema_version
):
    database, campaigns, content, _assets = _fixture(tmp_path, version=schema_version)
    source = b"delete me"
    operation_id = "5" * 32
    tombstone_ref = _insert_deletion(
        database,
        operation_id=operation_id,
        page_ref="notes/delete",
        state=state,
        source=source,
    )
    source_path = content / "notes" / "delete.md"
    tombstone_path = content.joinpath(*tombstone_ref.split("/"))
    source_path.parent.mkdir()
    if arrangement == "source":
        source_path.write_bytes(source)
    elif arrangement == "tombstone":
        tombstone_path.write_bytes(source)
    elif arrangement == "third":
        source_path.write_bytes(b"third")

    report, _ = _inspect(database, campaigns)

    assert report["operations"][0]["classification"] == classification


@pytest.mark.parametrize("schema_version", [4, 5, 6, 7, 8, 9])
def test_filters_order_and_output_are_redacted(tmp_path, schema_version):
    database, campaigns, content, _assets = _fixture(tmp_path, version=schema_version)
    for operation_id, page_ref in (("b" * 32, "private/beta"), ("a" * 32, "private/alpha")):
        desired = f"desired-{page_ref}".encode()
        target = content / f"{page_ref}.md"
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(desired)
        _insert_publication(
            database,
            operation_id=operation_id,
            page_ref=page_ref,
            state="prepared",
            desired=desired,
        )

    report, exit_code = _inspect(
        database,
        campaigns,
        kind="publication",
        campaign_slug="test-campaign",
        page_ref="private/alpha",
        state="prepared",
        operation_id="a" * 32,
    )
    rendered = json.dumps(report, sort_keys=True)

    assert exit_code == 1
    assert [item["operation_id"] for item in report["operations"]] == ["a" * 32]
    assert report["scope"] == {
        "campaign_filter_present": True,
        "kind": "publication",
        "operation_id_filter_present": True,
        "page_ref_filter_present": True,
        "state_filter_present": True,
    }
    for private in ("test-campaign", "private/alpha", "private/beta", str(content)):
        assert private not in rendered
    assert set(report["operations"][0]) == {
        "backup_required",
        "classification",
        "kind",
        "operation_id",
        "operation_kind",
        "reason_code",
        "recommended_action",
        "state",
    }


def test_current_empty_and_legacy_v2_exit_semantics(tmp_path):
    database, campaigns, _content, _assets = _fixture(tmp_path / "current")
    current, current_exit = _inspect(database, campaigns)
    legacy_database, legacy_campaigns, _legacy_content, _legacy_assets = _fixture(
        tmp_path / "legacy", version=2
    )
    legacy, legacy_exit = _inspect(legacy_database, legacy_campaigns)
    unsupported, unsupported_exit = _inspect(
        legacy_database,
        legacy_campaigns,
        kind="deletion",
    )

    assert current_exit == 0
    assert current["migration"] == {
        "applied_version": 9,
        "compatibility": "current",
        "current_version": 9,
        "evidence_status": "verified",
        "migration_required": False,
    }
    assert legacy_exit == 1
    assert legacy["migration"] == {
        "applied_version": 2,
        "compatibility": "legacy_supported",
        "current_version": 9,
        "evidence_status": "verified",
        "migration_required": True,
    }
    assert unsupported_exit == 2
    assert unsupported["error"]["reason_code"] == "deletion_inspection_requires_current_schema"


def test_v3_under_current_v9_supports_publication_and_deletion(tmp_path):
    database, campaigns, content, _assets = _fixture(tmp_path, version=3)
    desired = b"legacy publication"
    (content / "legacy-publication.md").write_bytes(desired)
    _insert_publication(
        database,
        operation_id="a" * 32,
        page_ref="legacy-publication",
        state="prepared",
        desired=desired,
    )
    source = b"legacy deletion"
    (content / "legacy-deletion.md").write_bytes(source)
    _insert_deletion(
        database,
        operation_id="b" * 32,
        page_ref="legacy-deletion",
        state="prepared",
        source=source,
    )

    report, exit_code = _inspect(database, campaigns)

    assert exit_code == 1
    assert report["migration"] == {
        "applied_version": 3,
        "compatibility": "legacy_supported",
        "current_version": 9,
        "evidence_status": "verified",
        "migration_required": True,
    }
    assert {operation["kind"] for operation in report["operations"]} == {
        "publication",
        "deletion",
    }


def test_v4_under_current_v9_supports_player_wiki_inventory_only(tmp_path):
    database, campaigns, content, _assets = _fixture(tmp_path, version=4)
    desired = b"v4 publication"
    (content / "v4-publication.md").write_bytes(desired)
    _insert_publication(
        database,
        operation_id="f" * 32,
        page_ref="v4-publication",
        state="prepared",
        desired=desired,
    )
    source = b"v4 deletion"
    (content / "v4-deletion.md").write_bytes(source)
    _insert_deletion(
        database,
        operation_id="1" * 32,
        page_ref="v4-deletion",
        state="prepared",
        source=source,
    )

    report, exit_code = _inspect(database, campaigns)

    assert exit_code == 1
    assert report["migration"] == {
        "applied_version": 4,
        "compatibility": "legacy_supported",
        "current_version": 9,
        "evidence_status": "verified",
        "migration_required": True,
    }
    assert {operation["kind"] for operation in report["operations"]} == {
        "publication",
        "deletion",
    }
    rendered = json.dumps(report, sort_keys=True)
    assert "character_reconciliation_operations" not in rendered
    assert "desired_definition_yaml" not in rendered


@pytest.mark.parametrize("schema_version", [5, 6, 7, 8, 9])
def test_v5_through_v9_inspect_only_active_player_wiki_journals(
    tmp_path, schema_version
):
    database, campaigns, content, _assets = _fixture(
        tmp_path, version=schema_version
    )
    desired = b"current publication"
    (content / "current-publication.md").write_bytes(desired)
    publication_id = "c" * 32
    deletion_id = "d" * 32
    _insert_publication(
        database,
        operation_id=publication_id,
        page_ref="current-publication",
        state="prepared",
        desired=desired,
    )
    source = b"current deletion"
    (content / "current-deletion.md").write_bytes(source)
    _insert_deletion(
        database,
        operation_id=deletion_id,
        page_ref="current-deletion",
        state="prepared",
        source=source,
    )
    private_character_operation = "e" * 32
    private_character_payload = b"private character recovery payload"
    private_portrait_operation = "9" * 32
    private_portrait_payload = b"private portrait recovery image"
    private_deletion_operation = "7" * 32
    digest = _digest(private_character_payload)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO character_reconciliation_operations (
                operation_id,campaign_slug,character_slug,operation_kind,
                previous_definition_digest,desired_definition_digest,
                previous_import_digest,desired_import_digest,
                previous_state_digest,desired_state_digest,
                previous_state_revision,desired_state_revision,
                desired_definition_yaml,desired_import_yaml,state,error_code,
                created_at,updated_at
            ) VALUES (?,?,?,'native_create','',?,'',?,'',?,0,1,?,?,?,?,?,?)
            """,
            (
                private_character_operation,
                "test-campaign",
                "private-character",
                digest,
                digest,
                digest,
                sqlite3.Binary(private_character_payload),
                sqlite3.Binary(private_character_payload),
                "conflict",
                "private_conflict",
                NOW,
                NOW,
            ),
        )
        if schema_version >= 8:
            connection.execute(
                """
                INSERT INTO character_reconciliation_operations (
                    operation_id,campaign_slug,character_slug,operation_kind,
                    previous_definition_digest,desired_definition_digest,
                    previous_import_digest,desired_import_digest,
                    previous_state_digest,desired_state_digest,
                    previous_state_revision,desired_state_revision,
                    desired_definition_yaml,desired_import_yaml,
                    previous_asset_ref,desired_asset_ref,
                    previous_asset_digest,desired_asset_digest,desired_asset_bytes,
                    state,error_code,created_at,updated_at
                ) VALUES (?,?,?,'portrait_upsert',?,?,?,?,?,?,7,8,?,?,?,?,?,?,?,
                    'conflict','private_conflict',?,?)
                """,
                (
                    private_portrait_operation,
                    "test-campaign",
                    "private-portrait-character",
                    "b" * 64,
                    "c" * 64,
                    "d" * 64,
                    "e" * 64,
                    "f" * 64,
                    "a" * 64,
                    sqlite3.Binary(private_character_payload),
                    sqlite3.Binary(private_character_payload),
                    "",
                    "characters/private-portrait-character/portrait.webp",
                    "",
                    _digest(private_portrait_payload),
                    sqlite3.Binary(private_portrait_payload),
                    NOW,
                    NOW,
                ),
            )
        if schema_version == 9:
            connection.execute(
                """
                INSERT INTO character_deletion_operations (
                    operation_id,campaign_slug,character_slug,operation_kind,
                    definition_present,definition_digest,definition_size,
                    definition_tombstone_name,import_present,import_digest,
                    import_size,import_tombstone_name,asset_present,asset_ref,
                    asset_digest,asset_size,asset_tombstone_name,
                    previous_state_present,previous_state_revision,
                    previous_state_digest,previous_assignment_present,
                    previous_assignment_digest,deleted_files,deleted_state,
                    deleted_assignment,deleted_assets,audit_event_type,
                    audit_actor_user_id,audit_target_user_id,audit_metadata_json,
                    state,error_code,created_at,updated_at
                ) VALUES (?,?,?,'content_api',0,'',0,'',0,'',0,'',0,'','',0,'',
                    1,1,?,0,'',0,1,0,0,NULL,NULL,NULL,NULL,
                    'conflict','private_conflict',?,?)
                """,
                (
                    private_deletion_operation,
                    "test-campaign",
                    "private-deleted-character",
                    "a" * 64,
                    NOW,
                    NOW,
                ),
            )
        connection.commit()

    report, exit_code = _inspect(database, campaigns)
    rendered = json.dumps(report, sort_keys=True)

    assert exit_code == 1
    assert report["migration"] == {
        "applied_version": schema_version,
        "compatibility": "current" if schema_version == 9 else "legacy_supported",
        "current_version": 9,
        "evidence_status": "verified",
        "migration_required": schema_version != 9,
    }
    assert {operation["operation_id"] for operation in report["operations"]} == {
        publication_id,
        deletion_id,
    }
    assert private_character_operation not in rendered
    assert "private-character" not in rendered
    assert private_character_payload.decode() not in rendered
    assert private_portrait_operation not in rendered
    assert "private-portrait-character" not in rendered
    assert private_portrait_payload.decode() not in rendered
    assert private_deletion_operation not in rendered
    assert "private-deleted-character" not in rendered


@pytest.mark.parametrize("kind", ["all", "publication"])
def test_v2_rejects_unledgered_v3_deletion_inventory_before_filters(tmp_path, kind):
    database, campaigns, content, _assets = _fixture(tmp_path, version=2)
    source = b"unledgered deletion"
    (content / "page.md").write_bytes(source)
    with sqlite3.connect(database) as connection:
        connection.executescript(MIGRATIONS[2].payload.schema_sql)
        connection.commit()
    _insert_deletion(
        database,
        operation_id="f" * 32,
        page_ref="page",
        state="prepared",
        source=source,
    )

    report, exit_code = _inspect(database, campaigns, kind=kind)

    assert exit_code == 2
    assert report["error"]["reason_code"] == "reconciliation_inventory_inconsistent"
    assert report["operations"] == []


def test_v3_publication_filter_rejects_missing_deletion_inventory(tmp_path):
    database, campaigns, _content, _assets = _fixture(tmp_path, version=3)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE player_wiki_deletion_operations")
        connection.commit()

    report, exit_code = _inspect(database, campaigns, kind="publication")

    assert exit_code == 2
    assert report["operations"] == []


def test_v3_deletion_filter_rejects_missing_publication_inventory(tmp_path):
    database, campaigns, _content, _assets = _fixture(tmp_path, version=3)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE player_wiki_reconciliation_operations")
        connection.commit()

    report, exit_code = _inspect(database, campaigns, kind="deletion")

    assert exit_code == 2
    assert report["operations"] == []


@pytest.mark.parametrize("version", [1])
def test_old_migration_versions_fail_closed(tmp_path, version):
    database, campaigns, _content, _assets = _fixture(tmp_path, version=version)

    report, exit_code = _inspect(database, campaigns)

    assert exit_code == 2
    assert report["consistency"] == "invalid"


@pytest.mark.parametrize("schema_version", [4, 5, 6, 7, 8, 9])
def test_future_tampered_and_table_shape_evidence_fail_closed(tmp_path, schema_version):
    for case in ("future", "tampered", "table", "table_sql", "index_predicate"):
        database, campaigns, _content, _assets = _fixture(
            tmp_path / case, version=schema_version
        )
        with sqlite3.connect(database) as connection:
            if case == "future":
                connection.execute("PRAGMA ignore_check_constraints=ON")
                connection.execute(
                    "INSERT INTO schema_migrations VALUES(10,'0010_future',?,?)",
                    ("0" * 64, NOW),
                )
            elif case == "tampered":
                connection.execute(
                    "UPDATE schema_migrations SET checksum=? WHERE version=4",
                    ("0" * 64,),
                )
            else:
                if case == "table":
                    connection.execute("DROP INDEX idx_player_wiki_reconciliation_active_page")
                elif case == "table_sql":
                    connection.execute("PRAGMA writable_schema=ON")
                    connection.execute(
                        """
                        UPDATE sqlite_master
                        SET sql = replace(sql, 'length(operation_id) = 32', 'length(operation_id) = 31')
                        WHERE type='table' AND name='player_wiki_reconciliation_operations'
                        """
                    )
                    connection.execute("PRAGMA writable_schema=OFF")
                else:
                    connection.execute("DROP INDEX idx_player_wiki_reconciliation_active_page")
                    connection.execute(
                        """
                        CREATE UNIQUE INDEX idx_player_wiki_reconciliation_active_page
                        ON player_wiki_reconciliation_operations(campaign_slug,page_ref)
                        WHERE state='prepared'
                        """
                    )
            connection.commit()

        report, exit_code = _inspect(database, campaigns)

        assert exit_code == 2
        assert report["operations"] == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("page_ref", "private//page"),
        ("desired_primary_ref", "assets/./image.webp"),
    ],
)
@pytest.mark.parametrize("schema_version", [4, 5, 6, 7, 8, 9])
def test_raw_malformed_refs_fail_closed_before_path_normalization(
    tmp_path, field, value, schema_version
):
    database, campaigns, content, _assets = _fixture(tmp_path, version=schema_version)
    desired = b"desired"
    (content / "page.md").write_bytes(desired)
    _insert_publication(
        database,
        operation_id="d" * 32,
        page_ref="page",
        state="prepared",
        desired=desired,
    )
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(
            f"UPDATE player_wiki_reconciliation_operations SET {field}=?",
            (value,),
        )
        connection.commit()

    report, exit_code = _inspect(database, campaigns)

    assert exit_code == 2
    assert value not in json.dumps(report, sort_keys=True)


@pytest.mark.parametrize("schema_version", [4, 5, 6, 7, 8, 9])
def test_cross_journal_active_page_conflict_fails_closed(tmp_path, schema_version):
    database, campaigns, content, _assets = _fixture(tmp_path, version=schema_version)
    desired = b"desired"
    source = content / "page.md"
    source.write_bytes(desired)
    _insert_publication(
        database,
        operation_id="1" * 32,
        page_ref="page",
        state="prepared",
        desired=desired,
    )
    _insert_deletion(
        database,
        operation_id="2" * 32,
        page_ref="page",
        state="prepared",
        source=desired,
    )

    report, exit_code = _inspect(database, campaigns)

    assert exit_code == 2
    assert report["error"]["reason_code"] == "cross_journal_active_page_conflict"
    assert report["operations"] == []


def test_missing_paths_restore_journal_and_invalid_filter_fail_closed(tmp_path):
    database, campaigns, _content, _assets = _fixture(tmp_path)
    missing_db, missing_db_exit = _inspect(tmp_path / "missing.sqlite3", campaigns)
    missing_root, missing_root_exit = _inspect(database, tmp_path / "missing-campaigns")
    restore_journal = Path(f"{database.resolve()}.restore-journal.json")
    restore_journal.write_text("private", encoding="utf-8")
    restore, restore_exit = _inspect(database, campaigns)
    invalid_filter, invalid_filter_exit = _inspect(database, campaigns, page_ref="secret/page")

    assert missing_db_exit == missing_root_exit == restore_exit == invalid_filter_exit == 2
    assert missing_db["error"]["reason_code"] == "database_missing"
    assert missing_root["error"]["reason_code"] == "campaigns_root_unavailable"
    assert restore["error"]["reason_code"] == "restore_recovery_active"
    assert invalid_filter["error"]["reason_code"] == "page_ref_requires_campaign_filter"


@pytest.mark.parametrize("schema_version", [4, 5, 6, 7, 8, 9])
def test_malformed_payload_and_unsafe_file_fail_closed(tmp_path, schema_version):
    database, campaigns, content, _assets = _fixture(tmp_path, version=schema_version)
    desired = b"desired"
    target = content / "page.md"
    target.write_bytes(desired)
    _insert_publication(
        database,
        operation_id="6" * 32,
        page_ref="page",
        state="prepared",
        desired=desired,
    )
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(
            "UPDATE player_wiki_reconciliation_operations SET desired_markdown=?",
            (sqlite3.Binary(b"\xff"),),
        )
        connection.commit()

    malformed, malformed_exit = _inspect(database, campaigns)

    assert malformed_exit == 2
    assert malformed["error"]["reason_code"] == "publication_recovery_payload_invalid"

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE player_wiki_reconciliation_operations SET desired_markdown=?, desired_markdown_digest=?",
            (sqlite3.Binary(desired), _digest(desired)),
        )
        connection.commit()
    outside = tmp_path / "outside.md"
    outside.write_bytes(desired)
    target.unlink()
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    unsafe, unsafe_exit = _inspect(database, campaigns)
    assert unsafe_exit == 2
    assert unsafe["error"]["reason_code"] == "publication_markdown_file_unsafe"


@pytest.mark.parametrize("case", ["malformed_config", "missing_content_root", "special_markdown"])
@pytest.mark.parametrize("schema_version", [4, 5, 6, 7, 8, 9])
def test_config_root_and_special_file_evidence_fail_closed(
    tmp_path, case, schema_version
):
    database, campaigns, content, _assets = _fixture(tmp_path, version=schema_version)
    desired = b"desired"
    _insert_publication(
        database,
        operation_id="e" * 32,
        page_ref="page",
        state="prepared",
        desired=desired,
    )
    config = campaigns / "test-campaign" / "campaign.yaml"
    if case == "malformed_config":
        config.write_text("not: [valid", encoding="utf-8")
    elif case == "missing_content_root":
        config.write_text(
            "title: Test Campaign\nslug: test-campaign\nplayer_content_dir: missing\nasset_dir: assets\n",
            encoding="utf-8",
        )
    else:
        (content / "page.md").mkdir()

    report, exit_code = _inspect(database, campaigns)

    assert exit_code == 2
    assert report["consistency"] == "invalid"
    assert report["operations"] == []


@pytest.mark.parametrize("schema_version", [4, 5, 6, 7, 8, 9])
def test_concurrent_row_and_file_change_are_indeterminate(tmp_path, schema_version):
    database, campaigns, content, _assets = _fixture(
        tmp_path / "row", version=schema_version
    )
    desired = b"desired"
    target = content / "page.md"
    target.write_bytes(desired)
    _insert_publication(
        database,
        operation_id="7" * 32,
        page_ref="page",
        state="prepared",
        desired=desired,
    )

    def change_row():
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE player_wiki_reconciliation_operations SET error_code='retry'"
            )
            connection.commit()

    row_report, row_exit = inspect_player_wiki_reconciliation(
        database_path=database,
        campaigns_dir=campaigns,
        between_scans=change_row,
    )

    file_database, file_campaigns, file_content, _file_assets = _fixture(
        tmp_path / "file", version=schema_version
    )
    file_target = file_content / "page.md"
    file_target.write_bytes(desired)
    _insert_publication(
        file_database,
        operation_id="8" * 32,
        page_ref="page",
        state="prepared",
        desired=desired,
    )
    file_report, file_exit = inspect_player_wiki_reconciliation(
        database_path=file_database,
        campaigns_dir=file_campaigns,
        between_scans=lambda: file_target.write_bytes(b"changed"),
    )

    assert row_exit == file_exit == 3
    assert row_report["consistency"] == file_report["consistency"] == "indeterminate"


@pytest.mark.parametrize("schema_version", [4, 5, 6, 7, 8, 9])
def test_concurrent_restore_journal_appearance_is_indeterminate_and_redacted(
    tmp_path, schema_version
):
    database, campaigns, _content, _assets = _fixture(
        tmp_path, version=schema_version
    )
    journal = Path(f"{database.resolve()}.restore-journal.json")
    private_payload = "private-restore-transaction"

    report, exit_code = inspect_player_wiki_reconciliation(
        database_path=database,
        campaigns_dir=campaigns,
        between_scans=lambda: journal.write_text(private_payload, encoding="utf-8"),
    )
    rendered = json.dumps(report, sort_keys=True)

    assert exit_code == 3
    assert report["consistency"] == "indeterminate"
    assert report["error"]["reason_code"] == "restore_recovery_appeared_during_inspection"
    assert str(journal) not in rendered
    assert private_payload not in rendered


@pytest.mark.parametrize("schema_version", [4, 5, 6, 7, 8, 9])
def test_busy_database_is_indeterminate(tmp_path, schema_version):
    database, campaigns, _content, _assets = _fixture(tmp_path, version=schema_version)
    blocker = sqlite3.connect(database, timeout=0)
    try:
        blocker.execute("BEGIN EXCLUSIVE")
        report, exit_code = _inspect(database, campaigns)
    finally:
        blocker.rollback()
        blocker.close()

    assert exit_code == 3
    assert report["consistency"] == "indeterminate"


def _path_identity(root: Path) -> dict[str, tuple[int, int, bytes]]:
    result: dict[str, tuple[int, int, bytes]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            details = path.stat()
            result[path.relative_to(root).as_posix()] = (
                details.st_size,
                details.st_mtime_ns,
                path.read_bytes(),
            )
    return result


@pytest.mark.parametrize("schema_version", [4, 5, 6, 7, 8, 9])
def test_cli_is_json_only_and_preserves_filesystem_database_and_sidecars(
    tmp_path, schema_version
):
    database, campaigns, content, _assets = _fixture(tmp_path, version=schema_version)
    desired = b"private desired markdown"
    (content / "private-page.md").write_bytes(desired)
    _insert_publication(
        database,
        operation_id="9" * 32,
        page_ref="private-page",
        state="prepared",
        desired=desired,
    )
    runtime_lock = Path(f"{database.resolve()}.runtime.lock")
    runtime_lock.write_bytes(b"preexisting-runtime-lock")
    project_root = Path(__file__).resolve().parents[1]
    before = _path_identity(tmp_path)
    env = os.environ.copy()
    env["PLAYER_WIKI_DB_PATH"] = str(database)
    env["PLAYER_WIKI_CAMPAIGNS_DIR"] = str(campaigns)

    result = subprocess.run(
        [sys.executable, str(project_root / "ops.py"), "player-wiki-reconciliation-dry-run"],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
    )

    assert result.returncode == 1
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report["consistency"] == "stable"
    assert _path_identity(tmp_path) == before
    rendered = result.stdout + result.stderr
    for private in (str(database), str(campaigns), "test-campaign", "private-page", desired.decode()):
        assert private not in rendered
    for suffix in ("-wal", "-shm", ".runtime.lock"):
        if suffix == ".runtime.lock":
            assert Path(f"{database}{suffix}").read_bytes() == b"preexisting-runtime-lock"
        else:
            assert not Path(f"{database}{suffix}").exists()


def test_cli_does_not_create_missing_database_parent(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    missing_parent = tmp_path / "missing-private-parent"
    database = missing_parent / "wiki.sqlite3"
    campaigns = tmp_path / "campaigns"
    campaigns.mkdir()
    env = os.environ.copy()
    env["PLAYER_WIKI_DB_PATH"] = str(database)
    env["PLAYER_WIKI_CAMPAIGNS_DIR"] = str(campaigns)

    result = subprocess.run(
        [sys.executable, str(project_root / "ops.py"), "player-wiki-reconciliation-dry-run"],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
    )

    assert result.returncode == 2
    assert result.stderr == ""
    assert not missing_parent.exists()
    assert str(missing_parent) not in result.stdout


def test_cli_parse_errors_are_redacted_json(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    secret = "private-invalid-value"
    result = subprocess.run(
        [
            sys.executable,
            str(project_root / "ops.py"),
            "player-wiki-reconciliation-dry-run",
            "--kind",
            secret,
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert result.stderr == ""
    assert json.loads(result.stdout)["error"]["reason_code"] == "invalid_arguments"
    assert secret not in result.stdout


def test_normally_closed_wal_database_uses_immutable_inspection_without_sidecars(
    tmp_path,
):
    database, campaigns, content, _assets = _fixture(tmp_path)
    desired = b"closed wal desired"
    (content / "closed-wal.md").write_bytes(desired)
    writer = sqlite3.connect(database)
    try:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
        writer.execute(
            "PRAGMA wal_autocheckpoint=0"
        )
        writer.execute(
            """
            INSERT INTO player_wiki_reconciliation_operations (
                operation_id,campaign_slug,page_ref,operation_kind,primary_authority,
                desired_primary_ref,previous_primary_digest,desired_primary_digest,
                previous_markdown_digest,desired_markdown_digest,desired_markdown,
                audit_event_type,audit_actor_user_id,audit_metadata_json,state,error_code,
                created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "4" * 32, "test-campaign", "closed-wal", "update", "markdown",
                "closed-wal.md", "", _digest(desired), "", _digest(desired),
                sqlite3.Binary(desired), None, None, None, "prepared", "", NOW, NOW,
            ),
        )
        writer.commit()
    finally:
        writer.close()
    wal = Path(f"{database}-wal")
    assert not wal.exists() or wal.stat().st_size == 0
    before = _path_identity(database.parent)

    report, exit_code = _inspect(database, campaigns)

    assert exit_code == 1, report
    assert report["operations"][0]["operation_id"] == "4" * 32
    assert _path_identity(database.parent) == before


def test_zero_length_wal_with_stable_shm_is_inspected_without_sidecar_change(tmp_path):
    database, campaigns, _content, _assets = _fixture(tmp_path)
    writer = sqlite3.connect(database)
    try:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
    finally:
        writer.close()
    wal = Path(f"{database}-wal")
    shm = Path(f"{database}-shm")
    wal.write_bytes(b"")
    shm.write_bytes(b"\0" * 32768)
    before = _path_identity(database.parent)

    report, exit_code = _inspect(database, campaigns)

    assert exit_code == 0, report
    assert report["consistency"] == "stable"
    assert _path_identity(database.parent) == before


def test_nonempty_wal_without_shared_memory_fails_closed_without_writes(tmp_path):
    database, campaigns, _content, _assets = _fixture(tmp_path)
    wal = Path(f"{database}-wal")
    shm = Path(f"{database}-shm")
    writer = sqlite3.connect(database)
    try:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE committed_only_in_wal (value TEXT NOT NULL)")
        writer.execute("INSERT INTO committed_only_in_wal VALUES ('committed')")
        writer.commit()
        wal_payload = wal.read_bytes()
        assert wal_payload
    finally:
        writer.close()
    wal.write_bytes(wal_payload)
    if shm.exists():
        shm.unlink()
    before = _path_identity(database.parent)

    report, exit_code = _inspect(database, campaigns)

    assert exit_code == 2
    assert report["error"]["reason_code"] == "wal_shared_memory_missing"
    assert _path_identity(database.parent) == before


@pytest.mark.parametrize("schema_version", [4, 5, 6, 7, 8, 9])
def test_committed_wal_rows_are_visible_without_sidecar_mutation(
    tmp_path, schema_version
):
    database, campaigns, content, _assets = _fixture(tmp_path, version=schema_version)
    desired = b"wal desired"
    (content / "wal.md").write_bytes(desired)
    writer = sqlite3.connect(database)
    try:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute(
            """
            INSERT INTO player_wiki_reconciliation_operations (
                operation_id,campaign_slug,page_ref,operation_kind,primary_authority,
                desired_primary_ref,previous_primary_digest,desired_primary_digest,
                previous_markdown_digest,desired_markdown_digest,desired_markdown,
                audit_event_type,audit_actor_user_id,audit_metadata_json,state,error_code,
                created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "c" * 32, "test-campaign", "wal", "update", "markdown", "wal.md", "",
                _digest(desired), "", _digest(desired), sqlite3.Binary(desired), None, None,
                None, "prepared", "", NOW, NOW,
            ),
        )
        writer.commit()
        warm_reader = sqlite3.connect(
            f"file:{database.absolute().as_posix()}?mode=ro",
            uri=True,
            timeout=0,
            isolation_level=None,
        )
        warm_reader.execute("SELECT COUNT(*) FROM player_wiki_reconciliation_operations").fetchone()
        warm_reader.close()
        before = _path_identity(database.parent)

        report, exit_code = _inspect(database, campaigns)

        assert exit_code == 1, report
        assert report["operations"][0]["operation_id"] == "c" * 32
        assert _path_identity(database.parent) == before
    finally:
        writer.close()


@pytest.mark.parametrize("schema_version", [4, 5, 6, 7, 8, 9])
def test_unbounded_sidecar_identity_uses_streaming_digest(
    tmp_path, monkeypatch, schema_version
):
    database, _campaigns, _content, _assets = _fixture(
        tmp_path, version=schema_version
    )
    runtime_lock = Path(f"{database.resolve()}.runtime.lock")
    payload = b"bounded-chunk" * 100_000
    runtime_lock.write_bytes(payload)

    def forbidden_materialization(*_args, **_kwargs):
        raise AssertionError("state sidecars must not use bounded whole-file materialization")

    monkeypatch.setattr(inspection, "_read_regular_file", forbidden_materialization)
    identity = inspection._state_identity(database)

    lock_row = next(row for row in identity if row[0] == "runtime_lock")
    assert lock_row[1] is True
    assert lock_row[3] == _digest(payload)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission control")
@pytest.mark.parametrize("schema_version", [4, 5, 6, 7, 8, 9])
def test_read_only_parent_remains_read_only_and_unmodified(tmp_path, schema_version):
    database, campaigns, _content, _assets = _fixture(tmp_path, version=schema_version)
    before = _path_identity(tmp_path)
    database.parent.chmod(stat.S_IREAD | stat.S_IEXEC)
    try:
        report, exit_code = _inspect(database, campaigns)
    finally:
        database.parent.chmod(stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)

    assert exit_code == 0
    assert report["consistency"] == "stable"
    assert _path_identity(tmp_path) == before
