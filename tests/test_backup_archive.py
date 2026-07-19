from __future__ import annotations

import json
import hashlib
import os
import sqlite3
import stat
import struct
import subprocess
import sys
import zipfile
from contextlib import closing
from pathlib import Path

import pytest

import player_wiki.backup_archive as backup_archive_module
import player_wiki.restore_transaction as restore_transaction_module
from player_wiki.backup_archive import (
    DATABASE_MEMBER,
    MANIFEST_MEMBER,
    BackupArchiveError,
    BackupArchiveHooks,
    BackupArchiveLimits,
    CampaignFileEvidence,
    canonical_json_bytes,
    create_backup_archive_v2,
    inspect_backup_archive,
    stage_backup_archive,
)
from player_wiki.db import init_database
from player_wiki.migrations import (
    BASELINE_SCHEMA_SQL,
    MIGRATIONS,
    SCHEMA_V2_SQL,
    SCHEMA_V3_SQL,
    run_migrations,
)
from player_wiki.operations import restore_backup_archive


def make_database(
    path: Path,
    *,
    current: bool = False,
    current_v2: bool = False,
    current_v3: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if current:
        init_database(path)
        return
    if current_v2:
        with sqlite3.connect(path) as connection:
            run_migrations(
                connection,
                database_path=path,
                schema_sql=SCHEMA_V2_SQL,
                registry=MIGRATIONS[:2],
            )
        return
    if current_v3:
        with sqlite3.connect(path) as connection:
            run_migrations(
                connection,
                database_path=path,
                schema_sql=SCHEMA_V3_SQL,
                registry=MIGRATIONS[:3],
            )
        return
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sample_state (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample_state VALUES ('safe fixture')")


def create_v2(
    tmp_path: Path,
    *,
    current: bool = False,
    current_v2: bool = False,
    current_v3: bool = False,
    hooks: BackupArchiveHooks | None = None,
):
    database = tmp_path / "source" / "wiki.sqlite3"
    campaigns = tmp_path / "campaigns"
    backups = tmp_path / "backups"
    make_database(
        database,
        current=current,
        current_v2=current_v2,
        current_v3=current_v3,
    )
    (campaigns / "alpha" / "content").mkdir(parents=True)
    (campaigns / "alpha" / "content" / "index.md").write_text("# Alpha\n", encoding="utf-8")
    evidence = create_backup_archive_v2(
        db_path=database,
        campaigns_dir=campaigns,
        backup_root=backups,
        archive_basename="player-wiki-backup-fixed",
        created_at="2026-07-11T12:00:00Z",
        hooks=hooks,
    )
    return evidence, database, campaigns, backups


def read_members(path: Path) -> tuple[list[str], dict[str, bytes], list[zipfile.ZipInfo]]:
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        return archive.namelist(), {info.filename: archive.read(info) for info in infos}, infos


def write_raw_archive(path: Path, members: list[tuple[str, bytes]], *, mode: int | None = None) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members:
            if mode is None:
                archive.writestr(name, payload)
            else:
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = mode << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, payload)


def write_v1(path: Path, database: Path, campaign_name: str = "campaigns/alpha/page.md") -> None:
    manifest = {
        "format_version": 1,
        "created_at": "2026-07-10T12:00:00+00:00",
        "database_filename": "player_wiki.sqlite3",
        "campaigns_dir_name": "campaigns",
    }
    stored_name = campaign_name.replace("\\", "/")
    write_raw_archive(
        path,
        [
            (MANIFEST_MEMBER, json.dumps(manifest).encode()),
            (DATABASE_MEMBER, database.read_bytes()),
            (stored_name, b"legacy page\n"),
        ],
    )
    if "\\" in campaign_name:
        raw = path.read_bytes()
        raw = raw.replace(stored_name.encode(), campaign_name.encode())
        path.write_bytes(raw)


def rewrite_v2_manifest(source: Path, destination: Path, mutate) -> None:
    names, members, _ = read_members(source)
    manifest = json.loads(members[MANIFEST_MEMBER])
    mutate(manifest)
    write_raw_archive(destination, [
        (name, canonical_json_bytes(manifest) if name == MANIFEST_MEMBER else members[name])
        for name in names
    ])


def test_v2_creation_is_canonical_streamed_and_reinspectable(tmp_path):
    evidence, _, _, _ = create_v2(tmp_path, current=True)
    names, members, infos = read_members(evidence.archive_path)

    assert names == [MANIFEST_MEMBER, DATABASE_MEMBER, "campaigns/alpha/content/index.md"]
    assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in infos)
    assert all(stat.S_IFMT(info.external_attr >> 16) == stat.S_IFREG for info in infos)
    manifest = json.loads(members[MANIFEST_MEMBER])
    assert members[MANIFEST_MEMBER] == canonical_json_bytes(manifest)
    assert set(manifest) == {"format", "format_version", "created_at", "producer", "database", "campaigns", "totals"}
    assert evidence.format_version == 2
    assert evidence.manifest_hashes_verified is True
    assert evidence.migration.is_current is True
    assert inspect_backup_archive(evidence.archive_path) == evidence


def test_ledgerless_database_is_truthfully_recorded_as_version_zero(tmp_path):
    evidence, _, _, _ = create_v2(tmp_path)
    assert evidence.migration.ledger_exists is False
    assert evidence.migration.applied_version == 0
    assert evidence.migration.current_version == 5
    assert evidence.migration.applied_name is None
    assert evidence.migration.applied_checksum is None
    assert evidence.migration.is_current is False


def test_v2_old_producer_current_archive_stages_and_restores_under_newer_registry(
    tmp_path,
):
    evidence, _, _, _ = create_v2(tmp_path, current_v2=True)

    with stage_backup_archive(evidence.archive_path) as staged:
        assert staged.evidence.verification_level == "verified_v2"
        assert staged.evidence.migration.ledger_exists is True
        assert staged.evidence.migration.applied_version == 2
        assert staged.evidence.migration.current_version == 5
        assert staged.evidence.migration.is_current is False

    restored = restore_backup_archive(
        archive_path=evidence.archive_path,
        db_path=tmp_path / "restored" / "wiki.sqlite3",
        campaigns_dir=tmp_path / "restored" / "campaigns",
    )
    assert restored.evidence.verification_level == "verified_v2"
    assert restored.evidence.migration.ledger_exists is True
    assert restored.evidence.migration.applied_version == 2
    assert restored.evidence.migration.current_version == 5
    assert restored.evidence.migration.is_current is False
    assert restored.database_verification.migration == restored.evidence.migration
    assert restored.migration_required is True
    migrated = init_database(restored.database_path)
    assert migrated.from_version == 2
    assert migrated.to_version == 5
    assert migrated.applied_versions == (3, 4, 5)


def test_v3_producer_archive_restores_then_applies_migrations_four_and_five(tmp_path):
    evidence, _, _, _ = create_v2(tmp_path, current_v3=True)

    with stage_backup_archive(evidence.archive_path) as staged:
        assert staged.evidence.verification_level == "verified_v2"
        assert staged.evidence.migration.applied_version == 3
        assert staged.evidence.migration.current_version == 5
        assert staged.evidence.migration.is_current is False

    restored = restore_backup_archive(
        archive_path=evidence.archive_path,
        db_path=tmp_path / "restored-v3" / "wiki.sqlite3",
        campaigns_dir=tmp_path / "restored-v3" / "campaigns",
    )
    assert restored.evidence.migration.applied_version == 3
    assert restored.evidence.migration.current_version == 5
    assert restored.migration_required is True
    migrated = init_database(restored.database_path)
    assert migrated.from_version == 3
    assert migrated.to_version == 5
    assert migrated.applied_versions == (4, 5)


def test_v2_ledgerless_archive_stages_under_current_registry(tmp_path):
    evidence, _, _, _ = create_v2(tmp_path)

    with stage_backup_archive(evidence.archive_path) as staged:
        assert staged.evidence.migration.ledger_exists is False
        assert staged.evidence.migration.applied_version == 0
        assert staged.evidence.migration.current_version == 5
        assert staged.evidence.migration.is_current is False


def test_v2_empty_existing_migration_ledger_is_valid_version_zero(tmp_path):
    database = tmp_path / "source" / "wiki.sqlite3"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL)"""
        )
    campaigns = tmp_path / "campaigns"
    campaigns.mkdir()
    evidence = create_backup_archive_v2(
        db_path=database,
        campaigns_dir=campaigns,
        backup_root=tmp_path / "backups",
        archive_basename="empty-ledger",
        created_at="2026-07-11T12:00:00Z",
    )

    assert evidence.migration.ledger_exists is True
    assert evidence.migration.applied_version == 0
    assert evidence.migration.applied_name is None
    assert evidence.migration.applied_checksum is None
    assert evidence.migration.is_current is False
    assert inspect_backup_archive(evidence.archive_path) == evidence


@pytest.mark.parametrize(
    "mutation",
    [
        lambda migration: migration.__setitem__("is_current", False),
        lambda migration: migration.__setitem__("current_version", 0),
        lambda migration: migration.__setitem__("applied_name", None),
        lambda migration: migration.__setitem__("applied_checksum", None),
        lambda migration: migration.__setitem__("ledger_exists", False),
        lambda migration: migration.update(applied_version=0, is_current=False),
    ],
)
def test_v2_rejects_internally_inconsistent_producer_migration_evidence(
    tmp_path,
    mutation,
):
    evidence, _, _, _ = create_v2(tmp_path, current=True)
    forged = tmp_path / "inconsistent.zip"
    rewrite_v2_manifest(
        evidence.archive_path,
        forged,
        lambda manifest: mutation(manifest["database"]["migrations"]),
    )

    with pytest.raises(BackupArchiveError, match="internally inconsistent"):
        inspect_backup_archive(forged)


def test_v2_rejects_producer_registry_newer_than_current_application(tmp_path):
    evidence, _, _, _ = create_v2(tmp_path, current=True)
    forged = tmp_path / "newer-producer.zip"

    def claim_newer_registry(manifest):
        migration = manifest["database"]["migrations"]
        migration["current_version"] = 6
        migration["is_current"] = False

    rewrite_v2_manifest(evidence.archive_path, forged, claim_newer_registry)

    with pytest.raises(BackupArchiveError, match="newer migration registry"):
        inspect_backup_archive(forged)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda migration: migration.update(
            applied_version=0,
            applied_name=None,
            applied_checksum=None,
            is_current=False,
        ),
        lambda migration: migration.__setitem__("applied_name", "0001_forged"),
        lambda migration: migration.__setitem__("applied_checksum", "0" * 64),
        lambda migration: migration.update(
            ledger_exists=False,
            applied_version=0,
            applied_name=None,
            applied_checksum=None,
            is_current=False,
        ),
    ],
)
def test_v2_rejects_migration_ledger_identity_tampering(tmp_path, mutation):
    evidence, _, _, _ = create_v2(tmp_path, current=True)
    forged = tmp_path / "ledger-tamper.zip"
    rewrite_v2_manifest(
        evidence.archive_path,
        forged,
        lambda manifest: mutation(manifest["database"]["migrations"]),
    )

    with pytest.raises(BackupArchiveError, match="ledger does not match"):
        inspect_backup_archive(forged)


def test_v2_snapshot_includes_committed_wal_rows(tmp_path):
    database = tmp_path / "source.sqlite3"
    campaigns = tmp_path / "campaigns"
    backups = tmp_path / "backups"
    campaigns.mkdir()
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        connection.execute("CREATE TABLE wal_state (value TEXT NOT NULL)")
        connection.commit()
        connection.execute("INSERT INTO wal_state VALUES ('committed-in-wal')")
        connection.commit()
        evidence = create_backup_archive_v2(
            db_path=database, campaigns_dir=campaigns, backup_root=backups,
            archive_basename="wal", created_at="2026-07-11T12:00:00Z",
        )
    with stage_backup_archive(evidence.archive_path) as staged:
        with closing(sqlite3.connect(staged.database_path)) as connection:
            assert connection.execute("SELECT value FROM wal_state").fetchone() == ("committed-in-wal",)


def test_same_inputs_and_timestamp_produce_byte_identical_v2_archives(tmp_path):
    database = tmp_path / "source.sqlite3"
    campaigns = tmp_path / "campaigns"
    backups = tmp_path / "backups"
    make_database(database, current=True)
    (campaigns / "alpha").mkdir(parents=True)
    (campaigns / "alpha" / "page.md").write_text("same\n")
    kwargs = dict(
        db_path=database, campaigns_dir=campaigns, backup_root=backups,
        created_at="2026-07-11T12:00:00Z",
    )
    first = create_backup_archive_v2(archive_basename="first", **kwargs)
    second = create_backup_archive_v2(archive_basename="second", **kwargs)
    assert first.archive_path.read_bytes() == second.archive_path.read_bytes()


def test_same_name_publication_never_overwrites_existing_archive(tmp_path):
    first, _, _, backups = create_v2(tmp_path / "one")
    original = first.archive_path.read_bytes()

    database = tmp_path / "two" / "source" / "wiki.sqlite3"
    campaigns = tmp_path / "two" / "campaigns"
    make_database(database)
    campaigns.mkdir(parents=True)
    second = create_backup_archive_v2(
        db_path=database, campaigns_dir=campaigns, backup_root=backups,
        archive_basename="player-wiki-backup-fixed", created_at="2026-07-11T12:00:00Z",
    )
    assert first.archive_path.read_bytes() == original
    assert second.archive_path.name == "player-wiki-backup-fixed-1.zip"


def test_historical_v1_inspects_and_stages_with_explicitly_weaker_evidence(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    make_database(database)
    archive = tmp_path / "legacy.zip"
    write_v1(archive, database)

    evidence = inspect_backup_archive(archive)
    assert evidence.format_version == 1
    assert evidence.verification_level == "legacy_v1"
    assert evidence.manifest_hashes_verified is False
    with stage_backup_archive(archive) as staged:
        assert staged.database_path.exists()
        assert (staged.campaigns_dir / "alpha" / "page.md").read_text() == "legacy page\n"
        assert [(item.relative_path, item.byte_count, item.sha256) for item in staged.campaign_files] == [
            ("alpha/page.md", len(b"legacy page\n"), hashlib.sha256(b"legacy page\n").hexdigest())
        ]
    target_db = tmp_path / "active" / "wiki.sqlite3"
    target_campaigns = tmp_path / "active" / "campaigns"
    result = restore_backup_archive(
        archive_path=archive,
        db_path=target_db,
        campaigns_dir=target_campaigns,
    )
    assert result.evidence.verification_level == "legacy_v1"
    assert (target_campaigns / "alpha" / "page.md").read_text() == "legacy page\n"


def test_v2_staging_exposes_manifest_backed_campaign_inventory(tmp_path):
    evidence, _, campaigns, _ = create_v2(tmp_path)
    payload = (campaigns / "alpha" / "content" / "index.md").read_bytes()

    with stage_backup_archive(evidence.archive_path) as staged:
        assert staged.campaign_files == (
            CampaignFileEvidence(
                relative_path="alpha/content/index.md",
                byte_count=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
            ),
        )


@pytest.mark.parametrize(
    "unsafe",
    [
        "campaigns/../escape.md", "/campaigns/escape.md", "C:/escape.md",
        "campaigns\\escape.md", "campaigns/CON.txt", "campaigns/trailing. ",
        "campaigns/nul\x00tail.md", "campaigns/control\x01.md", "campaigns/e\u0301.md",
    ],
)
def test_legacy_archive_rejects_cross_platform_unsafe_paths(tmp_path, unsafe):
    database = tmp_path / "legacy.sqlite3"
    make_database(database)
    archive = tmp_path / "unsafe.zip"
    write_v1(archive, database, unsafe)
    with pytest.raises(BackupArchiveError):
        inspect_backup_archive(archive)


@pytest.mark.parametrize("character", list('<>:"|?*'))
def test_windows_special_component_characters_are_rejected(tmp_path, character):
    database = tmp_path / "legacy.sqlite3"
    make_database(database)
    archive = tmp_path / "unsafe-special.zip"
    write_v1(archive, database, f"campaigns/bad{character}name.md")
    with pytest.raises(BackupArchiveError, match="Windows-invalid"):
        inspect_backup_archive(archive)


def test_linux_style_colon_source_enumeration_fails_and_cleans_all_staging(tmp_path, monkeypatch):
    database = tmp_path / "source.sqlite3"
    campaigns = tmp_path / "campaigns"
    backups = tmp_path / "backups"
    make_database(database)
    campaigns.mkdir()
    real_walk = os.walk

    def simulated_linux_walk(root, *args, **kwargs):
        if Path(root) == campaigns:
            return iter([(str(campaigns), [], ["linux:colon.md"])])
        return real_walk(root, *args, **kwargs)

    monkeypatch.setattr("player_wiki.backup_archive.os.walk", simulated_linux_walk)
    with pytest.raises(BackupArchiveError, match="Windows-invalid"):
        create_backup_archive_v2(
            db_path=database, campaigns_dir=campaigns, backup_root=backups,
            archive_basename="backup", created_at="2026-07-11T12:00:00Z",
        )
    assert not list(backups.glob("*.zip"))
    assert not list(backups.glob(".player-wiki-backup-*"))


def test_v2_colon_component_fails_structurally_before_payload_extraction(tmp_path, monkeypatch):
    evidence, _, _, _ = create_v2(tmp_path / "source")
    names, payloads, _ = read_members(evidence.archive_path)
    manifest = json.loads(payloads[MANIFEST_MEMBER])
    manifest["campaigns"]["files"][0]["path"] = "bad:name.md"
    archive = tmp_path / "v2-colon.zip"
    rewritten = []
    for name in names:
        if name == MANIFEST_MEMBER:
            rewritten.append((name, canonical_json_bytes(manifest)))
        elif name.startswith("campaigns/"):
            rewritten.append(("campaigns/bad:name.md", payloads[name]))
        else:
            rewritten.append((name, payloads[name]))
    write_raw_archive(archive, rewritten)
    calls = []
    monkeypatch.setattr(
        "player_wiki.backup_archive._extract_and_hash",
        lambda *_args, **_kwargs: calls.append(True),
    )
    with pytest.raises(BackupArchiveError, match="Windows-invalid"):
        inspect_backup_archive(archive)
    assert calls == []


@pytest.mark.parametrize(
    "members",
    [
        [("campaigns/a", b"file"), ("campaigns/a/b.md", b"child")],
        [("campaigns/a/b.md", b"child"), ("campaigns/a", b"file")],
        [("campaigns/Folder/item.md", b"child"), ("campaigns/folder", b"file")],
        [("campaigns/\u00e9/item.md", b"child"), ("campaigns/e\u0301", b"file")],
    ],
)
def test_v1_file_directory_prefix_collisions_fail_before_extraction(tmp_path, monkeypatch, members):
    database = tmp_path / "legacy.sqlite3"
    make_database(database)
    manifest = json.dumps({
        "format_version": 1, "created_at": "2026-07-10T12:00:00Z",
        "database_filename": "player_wiki.sqlite3", "campaigns_dir_name": "campaigns",
    }).encode()
    archive = tmp_path / "prefix.zip"
    write_raw_archive(
        archive,
        [(MANIFEST_MEMBER, manifest), (DATABASE_MEMBER, database.read_bytes()), *members],
    )
    calls = []
    monkeypatch.setattr(
        "player_wiki.backup_archive._extract_and_hash",
        lambda *_args, **_kwargs: calls.append(True),
    )
    with pytest.raises(BackupArchiveError):
        inspect_backup_archive(archive)
    assert calls == []


def test_v2_file_directory_prefix_collision_fails_before_extraction(tmp_path, monkeypatch):
    evidence, _, _, _ = create_v2(tmp_path / "source")
    _, payloads, _ = read_members(evidence.archive_path)
    manifest = json.loads(payloads[MANIFEST_MEMBER])
    files = [("A/child.md", b"child"), ("a", b"file")]
    manifest["campaigns"] = {
        "file_count": 2,
        "total_bytes": sum(len(payload) for _, payload in files),
        "files": [
            {"path": name, "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
            for name, payload in files
        ],
    }
    manifest["totals"] = {
        "member_count": 4,
        "payload_bytes": manifest["database"]["size"] + manifest["campaigns"]["total_bytes"],
    }
    archive = tmp_path / "v2-prefix.zip"
    write_raw_archive(
        archive,
        [
            (MANIFEST_MEMBER, canonical_json_bytes(manifest)),
            (DATABASE_MEMBER, payloads[DATABASE_MEMBER]),
            *[(f"campaigns/{name}", payload) for name, payload in files],
        ],
    )
    calls = []
    monkeypatch.setattr(
        "player_wiki.backup_archive._extract_and_hash",
        lambda *_args, **_kwargs: calls.append(True),
    )
    with pytest.raises(BackupArchiveError, match="file/directory"):
        inspect_backup_archive(archive)
    assert calls == []


@pytest.mark.parametrize("target", ["database", "campaign"])
def test_v2_central_size_mismatch_fails_before_any_payload_extraction(tmp_path, monkeypatch, target):
    evidence, _, _, _ = create_v2(tmp_path / target)
    names, payloads, _ = read_members(evidence.archive_path)
    manifest = json.loads(payloads[MANIFEST_MEMBER])
    if target == "database":
        manifest["database"]["size"] += 1
    else:
        manifest["campaigns"]["files"][0]["size"] += 1
        manifest["campaigns"]["total_bytes"] += 1
    manifest["totals"]["payload_bytes"] += 1
    archive = tmp_path / f"{target}-size.zip"
    write_raw_archive(
        archive,
        [(name, canonical_json_bytes(manifest) if name == MANIFEST_MEMBER else payloads[name]) for name in names],
    )
    calls = []
    monkeypatch.setattr(
        "player_wiki.backup_archive._extract_and_hash",
        lambda *_args, **_kwargs: calls.append(True),
    )
    with pytest.raises(BackupArchiveError, match="central-directory size"):
        inspect_backup_archive(archive)
    assert calls == []


def test_exact_and_casefold_duplicate_members_are_rejected(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    make_database(database)
    manifest = json.dumps({
        "format_version": 1, "created_at": "2026-07-10T12:00:00Z",
        "database_filename": "player_wiki.sqlite3", "campaigns_dir_name": "campaigns",
    }).encode()
    for suffix, duplicate in (("exact", "campaigns/Foo.md"), ("case", "campaigns/foo.md")):
        archive = tmp_path / f"duplicate-{suffix}.zip"
        members = [
            (MANIFEST_MEMBER, manifest), (DATABASE_MEMBER, database.read_bytes()),
            ("campaigns/Foo.md", b"a"), (duplicate, b"b"),
        ]
        if suffix == "exact":
            with pytest.warns(UserWarning, match="Duplicate name"):
                write_raw_archive(archive, members)
        else:
            write_raw_archive(archive, members)
        with pytest.raises(BackupArchiveError, match="collide"):
            inspect_backup_archive(archive)


def test_duplicate_json_keys_and_extra_members_fail_closed(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    make_database(database)
    duplicate_json = b'{"format_version":1,"format_version":1}'
    archive = tmp_path / "duplicate-json.zip"
    write_raw_archive(archive, [(MANIFEST_MEMBER, duplicate_json), (DATABASE_MEMBER, database.read_bytes())])
    with pytest.raises(BackupArchiveError, match="duplicate JSON"):
        inspect_backup_archive(archive)

    valid = tmp_path / "extra.zip"
    write_v1(valid, database)
    names, members, _ = read_members(valid)
    write_raw_archive(valid, [(name, members[name]) for name in names] + [("unexpected.txt", b"no")])
    with pytest.raises(BackupArchiveError, match="unexpected"):
        inspect_backup_archive(valid)


def test_special_member_and_unsupported_compression_are_rejected(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    make_database(database)
    manifest = json.dumps({
        "format_version": 1, "created_at": "2026-07-10T12:00:00Z",
        "database_filename": "player_wiki.sqlite3", "campaigns_dir_name": "campaigns",
    }).encode()
    archive = tmp_path / "symlink.zip"
    write_raw_archive(archive, [(MANIFEST_MEMBER, manifest), (DATABASE_MEMBER, database.read_bytes())], mode=stat.S_IFLNK | 0o777)
    with pytest.raises(BackupArchiveError, match="Special"):
        inspect_backup_archive(archive)

    archive = tmp_path / "bzip2.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_BZIP2) as output:
        output.writestr(MANIFEST_MEMBER, manifest)
        output.writestr(DATABASE_MEMBER, database.read_bytes())
    with pytest.raises(BackupArchiveError, match="unsupported compression"):
        inspect_backup_archive(archive)


def test_injectable_limits_reject_booleans_and_bound_archive_work(tmp_path):
    with pytest.raises(ValueError):
        BackupArchiveLimits(member_count=True)  # type: ignore[arg-type]

    evidence, _, _, _ = create_v2(tmp_path)
    with pytest.raises(BackupArchiveError, match="compressed size"):
        inspect_backup_archive(
            evidence.archive_path,
            limits=BackupArchiveLimits(compressed_archive_bytes=1),
        )
    with pytest.raises(BackupArchiveError, match="too many members"):
        inspect_backup_archive(
            evidence.archive_path,
            limits=BackupArchiveLimits(member_count=2),
        )


def test_manifest_hash_tamper_and_corrupt_database_are_rejected(tmp_path):
    evidence, _, _, _ = create_v2(tmp_path)
    names, members, _ = read_members(evidence.archive_path)
    manifest = json.loads(members[MANIFEST_MEMBER])
    manifest["database"]["sha256"] = "0" * 64
    tampered = tmp_path / "tampered.zip"
    write_raw_archive(tampered, [
        (name, canonical_json_bytes(manifest) if name == MANIFEST_MEMBER else members[name])
        for name in names
    ])
    with pytest.raises(BackupArchiveError, match="hash or size"):
        inspect_backup_archive(tampered)

    corrupt = tmp_path / "corrupt.zip"
    write_raw_archive(corrupt, [
        (name, b"not sqlite" if name == DATABASE_MEMBER else members[name]) for name in names
    ])
    with pytest.raises(BackupArchiveError):
        inspect_backup_archive(corrupt)


def test_legacy_database_with_foreign_key_violation_is_rejected(tmp_path):
    database = tmp_path / "foreign-key.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))")
        connection.execute("INSERT INTO child VALUES (999)")
    archive = tmp_path / "foreign-key.zip"
    write_v1(archive, database)
    with pytest.raises(BackupArchiveError, match="integrity validation"):
        inspect_backup_archive(archive)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda manifest: manifest["totals"].__setitem__("member_count", True),
        lambda manifest: manifest["campaigns"].__setitem__("total_bytes", -1),
        lambda manifest: manifest.__setitem__("created_at", "not-a-time"),
        lambda manifest: manifest["database"]["migrations"].__setitem__("applied_version", 1),
        lambda manifest: manifest["campaigns"]["files"][0].__setitem__("size", 999),
    ],
)
def test_v2_forged_types_totals_timestamp_ledger_and_sizes_fail(tmp_path, mutation):
    evidence, _, _, _ = create_v2(tmp_path)
    forged = tmp_path / "forged.zip"
    rewrite_v2_manifest(evidence.archive_path, forged, mutation)
    with pytest.raises(BackupArchiveError):
        inspect_backup_archive(forged)


def test_v2_noncanonical_json_is_rejected(tmp_path):
    evidence, _, _, _ = create_v2(tmp_path)
    names, members, _ = read_members(evidence.archive_path)
    manifest = json.loads(members[MANIFEST_MEMBER])
    noncanonical = json.dumps(manifest, indent=2, sort_keys=False).encode()
    archive = tmp_path / "noncanonical.zip"
    write_raw_archive(archive, [
        (name, noncanonical if name == MANIFEST_MEMBER else members[name]) for name in names
    ])
    with pytest.raises(BackupArchiveError, match="canonically"):
        inspect_backup_archive(archive)


def test_encrypted_flag_and_crc_damage_fail_before_staging(tmp_path):
    evidence, _, _, _ = create_v2(tmp_path)
    encrypted = tmp_path / "encrypted.zip"
    encrypted.write_bytes(evidence.archive_path.read_bytes())
    raw = bytearray(encrypted.read_bytes())
    cursor = 0
    while True:
        cursor = raw.find(b"PK\x03\x04", cursor)
        if cursor < 0:
            break
        flags = struct.unpack_from("<H", raw, cursor + 6)[0]
        struct.pack_into("<H", raw, cursor + 6, flags | 1)
        cursor += 4
    cursor = 0
    while True:
        cursor = raw.find(b"PK\x01\x02", cursor)
        if cursor < 0:
            break
        flags = struct.unpack_from("<H", raw, cursor + 8)[0]
        struct.pack_into("<H", raw, cursor + 8, flags | 1)
        cursor += 4
    encrypted.write_bytes(raw)
    with pytest.raises(BackupArchiveError, match="Encrypted"):
        inspect_backup_archive(encrypted)

    damaged = tmp_path / "damaged.zip"
    damaged.write_bytes(evidence.archive_path.read_bytes())
    with zipfile.ZipFile(damaged) as archive:
        info = archive.getinfo("campaigns/alpha/content/index.md")
        raw = bytearray(damaged.read_bytes())
        name_length, extra_length = struct.unpack_from("<HH", raw, info.header_offset + 26)
        data_offset = info.header_offset + 30 + name_length + extra_length
    raw[data_offset + max(0, info.compress_size // 2)] ^= 0xFF
    damaged.write_bytes(raw)
    with pytest.raises(BackupArchiveError):
        inspect_backup_archive(damaged)


def test_malformed_and_future_migration_ledgers_fail_creation(tmp_path):
    for kind in ("malformed", "future"):
        root = tmp_path / kind
        database = root / "source.sqlite3"
        campaigns = root / "campaigns"
        backups = root / "backups"
        make_database(database)
        with sqlite3.connect(database) as connection:
            if kind == "malformed":
                connection.execute("CREATE TABLE schema_migrations (version INTEGER)")
            else:
                connection.execute(
                    "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
                )
                connection.execute("INSERT INTO schema_migrations VALUES (2, '0002_future', ?, 'now')", ("0" * 64,))
        with pytest.raises(BackupArchiveError, match="ledger"):
            create_backup_archive_v2(
                db_path=database, campaigns_dir=campaigns, backup_root=backups,
                archive_basename="backup", created_at="2026-07-11T12:00:00Z",
            )
        assert not list(backups.glob("*.zip"))
        assert not list(backups.glob(".player-wiki-backup-*"))


@pytest.mark.parametrize(
    "hook_name",
    [
        "after_snapshot", "after_campaign_scan", "after_manifest_write",
        "after_database_write", "after_campaign_member_write", "before_archive_fsync",
        "after_archive_write", "after_reinspection", "before_publication", "after_publication",
    ],
)
def test_faults_cleanup_all_staging_and_preserve_existing_archive(tmp_path, hook_name):
    database = tmp_path / "source.sqlite3"
    campaigns = tmp_path / "campaigns"
    backups = tmp_path / "backups"
    make_database(database)
    campaigns.mkdir()
    (campaigns / "page.md").write_text("campaign fixture")
    backups.mkdir()
    existing = backups / "backup.zip"
    existing.write_bytes(b"existing")

    def fail(*_args):
        raise RuntimeError("injected")

    hooks = BackupArchiveHooks(**{hook_name: fail})
    with pytest.raises(RuntimeError, match="injected"):
        create_backup_archive_v2(
            db_path=database, campaigns_dir=campaigns, backup_root=backups,
            archive_basename="backup", created_at="2026-07-11T12:00:00Z", hooks=hooks,
        )
    assert existing.read_bytes() == b"existing"
    assert list(backups.iterdir()) == [existing]


def test_source_symlink_is_rejected_without_publishing(tmp_path, monkeypatch):
    database = tmp_path / "source.sqlite3"
    campaigns = tmp_path / "campaigns"
    backups = tmp_path / "backups"
    make_database(database)
    campaigns.mkdir()
    target = tmp_path / "secret.txt"
    target.write_text("secret")
    link = campaigns / "linked.txt"
    try:
        link.symlink_to(target)
    except OSError:
        link.write_text("simulated reparse entry")
        monkeypatch.setattr(
            "player_wiki.backup_archive._is_reparse_point",
            lambda path: Path(path) == link,
        )
    with pytest.raises(BackupArchiveError, match="Symlink"):
        create_backup_archive_v2(
            db_path=database, campaigns_dir=campaigns, backup_root=backups,
            archive_basename="backup", created_at="2026-07-11T12:00:00Z",
        )
    assert not list(backups.glob("*.zip"))


def test_source_mutation_and_storage_overlap_fail_without_publication(tmp_path):
    database = tmp_path / "source.sqlite3"
    campaigns = tmp_path / "campaigns"
    backups = tmp_path / "backups"
    make_database(database)
    campaigns.mkdir()
    campaign_file = campaigns / "page.md"
    campaign_file.write_text("before")

    def replace_source() -> None:
        replacement = campaigns / "replacement.tmp"
        replacement.write_text("after")
        os.replace(replacement, campaign_file)

    hooks = BackupArchiveHooks(after_campaign_scan=replace_source)
    with pytest.raises(BackupArchiveError, match="changed"):
        create_backup_archive_v2(
            db_path=database, campaigns_dir=campaigns, backup_root=backups,
            archive_basename="backup", created_at="2026-07-11T12:00:00Z", hooks=hooks,
        )
    assert not list(backups.glob("*.zip"))
    assert not list(backups.glob(".player-wiki-backup-*"))

    with pytest.raises(BackupArchiveError, match="overlap"):
        create_backup_archive_v2(
            db_path=database, campaigns_dir=campaigns, backup_root=campaigns / "backups",
            archive_basename="backup", created_at="2026-07-11T12:00:00Z",
        )


def test_invalid_archive_causes_zero_restore_target_mutation(tmp_path):
    evidence, _, _, _ = create_v2(tmp_path / "source")
    invalid = tmp_path / "invalid.zip"
    rewrite_v2_manifest(
        evidence.archive_path,
        invalid,
        lambda manifest: manifest["database"].__setitem__("sha256", "0" * 64),
    )
    target_db = tmp_path / "active" / "wiki.sqlite3"
    target_campaigns = tmp_path / "active" / "campaigns"
    make_database(target_db)
    target_campaigns.mkdir(parents=True)
    marker = target_campaigns / "keep.md"
    marker.write_text("keep")
    before_db = target_db.read_bytes()
    with pytest.raises(BackupArchiveError):
        restore_backup_archive(archive_path=invalid, db_path=target_db, campaigns_dir=target_campaigns)
    assert target_db.read_bytes() == before_db
    assert marker.read_text() == "keep"


def test_ops_inspect_is_read_only_and_invalid_restore_inspects_before_prebackup(tmp_path):
    evidence, _, _, _ = create_v2(tmp_path / "source")
    project_root = Path(__file__).resolve().parents[1]
    inspect_run = subprocess.run(
        [sys.executable, str(project_root / "ops.py"), "inspect", str(evidence.archive_path)],
        check=True, capture_output=True, text=True,
    )
    assert "Inspected backup archive:" in inspect_run.stdout
    assert "Backup format: v2 (verified_v2)" in inspect_run.stdout
    assert "Manifest hashes verified: true" in inspect_run.stdout

    invalid = tmp_path / "invalid.zip"
    invalid.write_bytes(b"not a zip")
    active_db = tmp_path / "active" / "wiki.sqlite3"
    active_campaigns = tmp_path / "active" / "campaigns"
    backup_root = tmp_path / "prebackups"
    make_database(active_db)
    active_campaigns.mkdir(parents=True)
    env = os.environ.copy()
    env["PLAYER_WIKI_DB_PATH"] = str(active_db)
    env["PLAYER_WIKI_CAMPAIGNS_DIR"] = str(active_campaigns)
    run = subprocess.run(
        [sys.executable, str(project_root / "ops.py"), "restore", str(invalid), "--output-dir", str(backup_root), "--yes"],
        capture_output=True, text=True, env=env,
    )
    assert run.returncode != 0
    assert "Created pre-restore safety backup:" not in run.stdout
    assert not list(backup_root.glob("*.zip")) if backup_root.exists() else True
