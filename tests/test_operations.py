from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tarfile
import zipfile
from contextlib import closing
from pathlib import Path

import pytest

from player_wiki.operations import (
    FlyDatabasePullResult,
    build_flyctl_environment,
    create_backup_archive,
    resolve_fly_machine_id,
    rehearse_restore_archive,
    restore_backup_archive,
    run_flyctl_command,
    snapshot_database,
    sync_local_state_from_fly,
)
from player_wiki.backup_archive import DATABASE_MEMBER, BackupArchiveError
from player_wiki.db import init_database
from player_wiki.runtime_lease import acquire_exclusive_state_lease


def write_manage_campaign_fixture(
    campaigns_dir: Path,
    *,
    campaign_slug: str,
    pages: tuple[tuple[str, bool], ...],
) -> None:
    campaign_dir = campaigns_dir / campaign_slug
    source_config = (campaigns_dir / "linden-pass" / "campaign.yaml").read_text(
        encoding="utf-8"
    )
    campaign_dir.mkdir(parents=True, exist_ok=True)
    (campaign_dir / "campaign.yaml").write_text(
        source_config.replace(
            "title: Echoes of the Alloy Coast",
            f"title: {campaign_slug.replace('-', ' ').title()}",
        ).replace("slug: linden-pass", f"slug: {campaign_slug}"),
        encoding="utf-8",
    )
    (campaign_dir / "assets").mkdir(exist_ok=True)
    (campaign_dir / "characters").mkdir(exist_ok=True)
    for page_ref, published in pages:
        page_path = campaign_dir / "content" / f"{page_ref}.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            "\n".join(
                [
                    "---",
                    f"title: {page_ref.rsplit('/', 1)[-1].replace('-', ' ').title()}",
                    "section: Items",
                    "page_type: item",
                    "source_ref: manage.py publication policy test",
                    f"published: {'true' if published else 'false'}",
                    "---",
                    "",
                    "*Wondrous item, uncommon*",
                    "",
                    "A campaign item mechanics CLI test page.",
                    "",
                ]
            ),
            encoding="utf-8",
        )


def run_manage_for_app(app, *arguments: str) -> subprocess.CompletedProcess[str]:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update(
        {
            "PLAYER_WIKI_DB_PATH": str(app.config["DB_PATH"]),
            "PLAYER_WIKI_CAMPAIGNS_DIR": str(app.config["TEST_CAMPAIGNS_DIR"]),
            "PLAYER_WIKI_ENV": "development",
            "PLAYER_WIKI_SECRET_KEY": "item-mechanics-cli-test-secret",
        }
    )
    return subprocess.run(
        [sys.executable, str(project_root / "manage.py"), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=project_root,
    )


def run_ops(*arguments: str) -> subprocess.CompletedProcess[str]:
    project_root = Path(__file__).resolve().parents[1]
    return subprocess.run(
        [sys.executable, str(project_root / "ops.py"), *arguments],
        check=False,
        capture_output=True,
        text=True,
        cwd=project_root,
    )


def write_database(db_path: Path, value: str) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute("CREATE TABLE sample_state (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample_state (value) VALUES (?)", (value,))
        connection.commit()


def read_database_value(db_path: Path) -> str:
    with closing(sqlite3.connect(db_path)) as connection:
        row = connection.execute("SELECT value FROM sample_state").fetchone()
    assert row is not None
    return str(row[0])


def update_database_value(db_path: Path, value: str) -> None:
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute("UPDATE sample_state SET value = ?", (value,))
        connection.commit()


def create_campaigns_archive(archive_path: Path, campaigns_dir: Path) -> None:
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(campaigns_dir, arcname="campaigns")


def create_legacy_backup_archive(
    archive_path: Path, database: Path, *, campaign_payload: bytes
) -> None:
    manifest = {
        "format_version": 1,
        "created_at": "2026-07-11T12:00:00+00:00",
        "database_filename": "player_wiki.sqlite3",
        "campaigns_dir_name": "campaigns",
    }
    with zipfile.ZipFile(
        archive_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        archive.writestr("manifest.json", json.dumps(manifest).encode("utf-8"))
        archive.write(database, "database/player_wiki.sqlite3")
        archive.writestr("campaigns/alpha/page.md", campaign_payload)


def test_create_backup_archive_includes_database_and_campaign_files(tmp_path):
    db_path = tmp_path / "player_wiki.sqlite3"
    campaigns_dir = tmp_path / "campaigns"
    backup_root = tmp_path / "backups"

    write_database(db_path, "original-state")
    (campaigns_dir / "linden-pass" / "content").mkdir(parents=True)
    (campaigns_dir / "linden-pass" / "content" / "index.md").write_text("# Linden Pass\n", encoding="utf-8")

    result = create_backup_archive(
        db_path=db_path,
        campaigns_dir=campaigns_dir,
        backup_root=backup_root,
        label="smoke-check",
    )

    assert result.archive_path.exists()
    assert result.campaign_file_count == 1

    with zipfile.ZipFile(result.archive_path) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "database/player_wiki.sqlite3" in names
        assert "campaigns/linden-pass/content/index.md" in names


def test_snapshot_database_delegates_to_safe_sqlite_primitive(tmp_path, monkeypatch):
    db_path = tmp_path / "source.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"
    expected_evidence = object()
    captured = {}

    def fake_snapshot_sqlite_database(*, source_path, destination_path):
        captured["source_path"] = source_path
        captured["destination_path"] = destination_path
        return expected_evidence

    monkeypatch.setattr("player_wiki.operations.snapshot_sqlite_database", fake_snapshot_sqlite_database)

    result = snapshot_database(db_path=db_path, destination_path=destination_path)

    assert result is expected_evidence
    assert captured == {"source_path": db_path, "destination_path": destination_path}


def test_snapshot_database_missing_source_fails_without_creating_database(tmp_path):
    db_path = tmp_path / "missing.sqlite3"
    destination_path = tmp_path / "snapshot.sqlite3"

    with pytest.raises(FileNotFoundError, match="source does not exist"):
        snapshot_database(db_path=db_path, destination_path=destination_path)

    assert not db_path.exists()
    assert not destination_path.exists()


def test_restore_backup_archive_replaces_database_and_campaigns(tmp_path):
    source_db = tmp_path / "source.sqlite3"
    source_campaigns = tmp_path / "source-campaigns"
    backup_root = tmp_path / "backups"

    write_database(source_db, "restored-state")
    (source_campaigns / "linden-pass" / "content").mkdir(parents=True)
    (source_campaigns / "linden-pass" / "content" / "page.md").write_text("restored page", encoding="utf-8")

    backup = create_backup_archive(
        db_path=source_db,
        campaigns_dir=source_campaigns,
        backup_root=backup_root,
        label="restore-target",
    )

    target_root = tmp_path / "active"
    target_db = target_root / "player_wiki.sqlite3"
    target_campaigns = target_root / "campaigns"
    write_database(target_db, "stale-state")
    (target_campaigns / "stale").mkdir(parents=True)
    (target_campaigns / "stale" / "old.md").write_text("old page", encoding="utf-8")

    result = restore_backup_archive(
        archive_path=backup.archive_path,
        db_path=target_db,
        campaigns_dir=target_campaigns,
    )

    assert result.database_path == target_db.resolve()
    assert read_database_value(target_db) == "restored-state"
    assert (target_campaigns / "linden-pass" / "content" / "page.md").read_text(encoding="utf-8") == "restored page"
    assert not (target_campaigns / "stale" / "old.md").exists()


def test_ops_cli_backup_and_restore_round_trip_in_isolated_environment(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    ops_path = project_root / "ops.py"
    active_db = tmp_path / "active" / "player_wiki.sqlite3"
    campaigns_dir = tmp_path / "active" / "campaigns"
    backup_root = tmp_path / "backups"

    write_database(active_db, "initial-state")
    (campaigns_dir / "linden-pass" / "content").mkdir(parents=True)
    (campaigns_dir / "linden-pass" / "content" / "page.md").write_text("original page", encoding="utf-8")

    env = os.environ.copy()
    env["PLAYER_WIKI_DB_PATH"] = str(active_db)
    env["PLAYER_WIKI_CAMPAIGNS_DIR"] = str(campaigns_dir)

    backup_run = subprocess.run(
        [sys.executable, str(ops_path), "backup", "--output-dir", str(backup_root), "--label", "cli-roundtrip"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert "Created backup archive:" in backup_run.stdout

    archive_path = next(backup_root.glob("player-wiki-backup-*-cli-roundtrip.zip"))
    update_database_value(active_db, "mutated-state")
    (campaigns_dir / "linden-pass" / "content" / "page.md").write_text("mutated page", encoding="utf-8")

    restore_run = subprocess.run(
        [sys.executable, str(ops_path), "restore", str(archive_path), "--output-dir", str(backup_root), "--yes"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert "Created pre-restore safety backup:" in restore_run.stdout
    assert "Restored backup archive:" in restore_run.stdout

    assert read_database_value(active_db) == "initial-state"
    assert (campaigns_dir / "linden-pass" / "content" / "page.md").read_text(encoding="utf-8") == "original page"
    archives = list(backup_root.glob("*.zip"))
    assert len(archives) == 2
    assert len([path for path in archives if "pre-restore-" in path.name]) == 1
    with acquire_exclusive_state_lease(active_db):
        pass


@pytest.mark.parametrize("format_version", [1, 2])
@pytest.mark.parametrize("current", [False, True])
def test_restore_rehearsal_is_isolated_complete_and_cleanup_verified(
    tmp_path, monkeypatch, format_version, current
):
    source_db = tmp_path / "source" / "wiki.sqlite3"
    source_db.parent.mkdir(parents=True)
    if current:
        init_database(source_db)
        with closing(sqlite3.connect(source_db)) as connection:
            connection.execute("CREATE TABLE rehearsal_source (value TEXT NOT NULL)")
            connection.execute("INSERT INTO rehearsal_source VALUES ('archive-state')")
    else:
        write_database(source_db, "archive-state")
    source_campaigns = tmp_path / "source-campaigns"
    (source_campaigns / "alpha").mkdir(parents=True)
    campaign_payload = b"archive campaign\n"
    (source_campaigns / "alpha" / "page.md").write_bytes(campaign_payload)
    archive_root = tmp_path / "archives"
    archive_root.mkdir()
    if format_version == 2:
        archive = create_backup_archive(
            db_path=source_db,
            campaigns_dir=source_campaigns,
            backup_root=archive_root,
            label="rehearsal-source",
        ).archive_path
    else:
        archive = archive_root / "legacy.zip"
        create_legacy_backup_archive(
            archive, source_db, campaign_payload=campaign_payload
        )

    active_db = tmp_path / "active-sentinel" / "wiki.sqlite3"
    active_campaigns = tmp_path / "active-sentinel" / "campaigns"
    write_database(active_db, "must-not-change")
    active_campaigns.mkdir()
    active_campaign = active_campaigns / "private-marker.txt"
    active_campaign.write_bytes(b"must-not-change\n")
    database_before = active_db.read_bytes()
    campaign_before = active_campaign.read_bytes()
    temp_root = (
        Path(os.environ["TEMP"])
        / f"cpw-rh-{os.getpid()}-{format_version}-{int(current)}"
    )
    monkeypatch.setenv("PLAYER_WIKI_TEMP_DIR", str(temp_root))
    monkeypatch.setenv("PLAYER_WIKI_DB_PATH", str(active_db))
    monkeypatch.setenv("PLAYER_WIKI_CAMPAIGNS_DIR", str(active_campaigns))

    result = rehearse_restore_archive(archive_path=archive)

    assert result.source_format_version == format_version
    assert result.source_verification_level == (
        "verified_v2" if format_version == 2 else "legacy_v1"
    )
    assert result.source_manifest_hashes_verified is (format_version == 2)
    assert result.migration_applied_version == (
        result.migration_current_version if current else 0
    )
    assert result.migration_current_version >= 1
    assert result.migration_required is (not current)
    assert result.database_integrity_check == ("ok",)
    assert result.database_foreign_key_violation_count == 0
    assert result.campaign_file_count == 1
    assert result.campaign_hashes_verified is True
    assert result.prebackup_format_version == 2
    assert result.prebackup_verification_level == "verified_v2"
    assert result.prebackup_manifest_hashes_verified is True
    assert result.transaction_outcome == "committed"
    assert result.recovery_state == "clean"
    assert result.cleanup_verified is True
    assert active_db.read_bytes() == database_before
    assert active_campaign.read_bytes() == campaign_before
    assert list(temp_root.iterdir()) == []


def test_restore_rehearsal_rejects_invalid_archive_and_removes_workspace(
    tmp_path, monkeypatch
):
    archive = tmp_path / "invalid.zip"
    archive.write_bytes(b"not a zip")
    temp_root = tmp_path / "rehearsal-temp"
    monkeypatch.setenv("PLAYER_WIKI_TEMP_DIR", str(temp_root))

    with pytest.raises(BackupArchiveError):
        rehearse_restore_archive(archive_path=archive)

    assert not temp_root.exists() or list(temp_root.iterdir()) == []


def test_restore_rehearsal_rejects_tampered_archive_before_mutation(
    tmp_path, monkeypatch
):
    source_db = tmp_path / "source" / "wiki.sqlite3"
    campaigns = tmp_path / "campaigns"
    write_database(source_db, "archive-state")
    campaigns.mkdir()
    source = create_backup_archive(
        db_path=source_db,
        campaigns_dir=campaigns,
        backup_root=tmp_path / "archives",
        label="tamper-source",
    ).archive_path
    with zipfile.ZipFile(source) as archive:
        members = [(item, archive.read(item)) for item in archive.namelist()]
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(
        tampered, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for name, payload in members:
            if name == DATABASE_MEMBER:
                payload += b"tamper"
            archive.writestr(name, payload)
    temp_root = Path(os.environ["TEMP"]) / f"cpw-tamper-rh-{os.getpid()}"
    monkeypatch.setenv("PLAYER_WIKI_TEMP_DIR", str(temp_root))

    with pytest.raises(BackupArchiveError):
        rehearse_restore_archive(archive_path=tampered)

    assert not temp_root.exists()


def test_ops_parser_exposes_recovery_commands_and_rejects_legacy_or_retention_flags(
    tmp_path,
):
    project_root = Path(__file__).resolve().parents[1]
    ops_path = project_root / "ops.py"

    help_run = subprocess.run(
        [sys.executable, str(ops_path), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    for command in (
        "restore-status",
        "restore-resume",
        "restore-rollback",
        "restore-rehearsal",
    ):
        assert command in help_run.stdout

    archive = tmp_path / "unused.zip"
    rejected = (
        ("restore", str(archive), "--skip-pre-restore-backup"),
        ("restore", str(archive), "--pre-restore-label", "custom"),
        ("restore-rehearsal", str(archive), "--keep"),
        ("restore-rehearsal", str(archive), "--target", str(tmp_path)),
        ("restore-rehearsal", str(archive), "--output-dir", str(tmp_path)),
    )
    for arguments in rejected:
        completed = subprocess.run(
            [sys.executable, str(ops_path), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode != 0
        assert "unrecognized arguments" in completed.stderr


def test_ops_recovery_cli_is_pre_app_confirmed_idempotent_and_path_private(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    ops_path = project_root / "ops.py"
    active_db = tmp_path / "private-active-root" / "wiki.sqlite3"
    active_campaigns = tmp_path / "private-active-root" / "campaigns"
    write_database(active_db, "unchanged")
    active_campaigns.mkdir()
    before = active_db.read_bytes()
    env = os.environ.copy()
    env.update(
        {
            "PLAYER_WIKI_DB_PATH": str(active_db),
            "PLAYER_WIKI_CAMPAIGNS_DIR": str(active_campaigns),
            "PLAYER_WIKI_ENV": "production",
            "PLAYER_WIKI_SECRET_KEY": "",
        }
    )

    status = subprocess.run(
        [sys.executable, str(ops_path), "restore-status"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert status.stdout.splitlines() == [
        "Recovery state: clean",
        "Transaction: none",
        "Phase: none",
        "Recommended action: none",
    ]
    assert str(active_db) not in status.stdout

    for command in ("restore-resume", "restore-rollback"):
        refused = subprocess.run(
            [sys.executable, str(ops_path), command],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        assert refused.returncode != 0
        assert "Re-run with --yes" in refused.stderr
        assert active_db.read_bytes() == before

        clean = subprocess.run(
            [sys.executable, str(ops_path), command, "--yes"],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        assert "Transaction: none" in clean.stdout
        assert "Outcome: no_active_transaction" in clean.stdout
        assert "Recovery state: clean" in clean.stdout
        assert active_db.read_bytes() == before


def test_ops_restore_rehearsal_cli_is_pre_app_isolated_and_path_private(
    tmp_path,
):
    project_root = Path(__file__).resolve().parents[1]
    ops_path = project_root / "ops.py"
    source_db = tmp_path / "source" / "wiki.sqlite3"
    source_campaigns = tmp_path / "source-campaigns"
    write_database(source_db, "archive-state")
    source_campaigns.mkdir()
    (source_campaigns / "page.md").write_text("archive page\n", encoding="utf-8")
    archive = create_backup_archive(
        db_path=source_db,
        campaigns_dir=source_campaigns,
        backup_root=tmp_path / "archives",
        label="cli-rehearsal",
    ).archive_path
    active_db = tmp_path / "private-active" / "wiki.sqlite3"
    active_campaigns = tmp_path / "private-active" / "campaigns"
    write_database(active_db, "must-not-change")
    active_campaigns.mkdir()
    active_marker = active_campaigns / "marker.md"
    active_marker.write_text("must-not-change\n", encoding="utf-8")
    database_before = active_db.read_bytes()
    campaign_before = active_marker.read_bytes()
    temp_root = Path(os.environ["TEMP"]) / f"cpw-cli-rh-{os.getpid()}"
    env = os.environ.copy()
    env.update(
        {
            "PLAYER_WIKI_DB_PATH": str(active_db),
            "PLAYER_WIKI_CAMPAIGNS_DIR": str(active_campaigns),
            "PLAYER_WIKI_TEMP_DIR": str(temp_root),
            "PLAYER_WIKI_ENV": "production",
            "PLAYER_WIKI_SECRET_KEY": "",
        }
    )

    completed = subprocess.run(
        [sys.executable, str(ops_path), "restore-rehearsal", str(archive)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert "Restore rehearsal: pass" in completed.stdout
    assert "Mandatory prebackup: v2 (verified_v2)" in completed.stdout
    assert "Migration applied version: 0" in completed.stdout
    assert "Migration current version:" in completed.stdout
    assert "Mandatory prebackup manifest hashes verified: true" in completed.stdout
    assert "Disposable cleanup: true" in completed.stdout
    assert str(archive) not in completed.stdout
    assert str(active_db) not in completed.stdout
    assert active_db.read_bytes() == database_before
    assert active_marker.read_bytes() == campaign_before
    assert list(temp_root.iterdir()) == []

def test_local_ps1_restore_recovery_contract_and_status_smoke(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    wrapper = project_root / "local.ps1"
    content = wrapper.read_text(encoding="utf-8")
    assert "SkipPreRestoreBackup" not in content
    assert "--skip-pre-restore-backup" not in content
    assert "--pre-restore-label" not in content
    assert "mandatory prebackup names are transaction-correlated" in content
    assert content.count('"restore-status"') >= 3
    assert content.count('"restore-resume"') >= 3
    assert content.count('"restore-rollback"') >= 3
    assert content.count('"restore-rehearsal"') >= 3
    assert "--skip-pre-sync-backup" in content
    assert "--pre-sync-label" in content

    active_db = tmp_path / "active" / "wiki.sqlite3"
    write_database(active_db, "unchanged")
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(wrapper),
            "-Action",
            "restore-status",
            "-PythonPath",
            sys.executable,
            "-DbPath",
            str(active_db),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Recovery state: clean" in completed.stdout

    rejected_label = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(wrapper),
            "-Action",
            "restore",
            "-PythonPath",
            sys.executable,
            "-BackupArchive",
            str(tmp_path / "unused.zip"),
            "-BackupLabel",
            "custom",
            "-ForceRestore",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected_label.returncode != 0
    assert "mandatory prebackup names are transaction-correlated" in (
        rejected_label.stdout + rejected_label.stderr
    )


def test_manage_cli_intentionally_prints_one_time_invite_reset_and_api_tokens(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    manage_path = project_root / "manage.py"
    db_path = tmp_path / "player_wiki.sqlite3"
    campaigns_dir = tmp_path / "campaigns"
    campaigns_dir.mkdir()
    base_url = "http://127.0.0.1:5999"
    env = os.environ.copy()
    env.update(
        {
            "PLAYER_WIKI_DB_PATH": str(db_path),
            "PLAYER_WIKI_CAMPAIGNS_DIR": str(campaigns_dir),
            "PLAYER_WIKI_BASE_URL": base_url,
            "PLAYER_WIKI_RELOAD_CONTENT": "false",
        }
    )

    def run_manage(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(manage_path), *arguments],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

    invite_run = run_manage(
        "invite-user",
        "cli-invite@example.com",
        "CLI Invite",
    )
    invite_match = re.search(rf"{re.escape(base_url)}/invite/([A-Za-z0-9_-]+)", invite_run.stdout)
    assert invite_match is not None
    assert len(invite_match.group(1)) >= 32

    run_manage(
        "create-admin",
        "cli-active@example.com",
        "CLI Active",
        "--password",
        "safe-cli-password-123",
    )
    reset_run = run_manage("issue-password-reset", "cli-active@example.com")
    reset_match = re.search(rf"{re.escape(base_url)}/reset/([A-Za-z0-9_-]+)", reset_run.stdout)
    assert reset_match is not None
    assert len(reset_match.group(1)) >= 32

    api_token_run = run_manage(
        "issue-api-token",
        "cli-active@example.com",
        "cli-regression",
    )
    api_token = api_token_run.stdout.strip().splitlines()[-1]
    assert re.fullmatch(r"[A-Za-z0-9_-]{32,}", api_token)

    assert "[REDACTED]" not in invite_run.stdout
    assert "[REDACTED]" not in reset_run.stdout
    assert "[REDACTED]" not in api_token_run.stdout
    assert len({invite_match.group(1), reset_match.group(1), api_token}) == 3


def test_manage_campaign_item_mechanics_filters_unpublished_pages_and_rejects_explicit_refresh(
    app,
    users,
):
    campaign_slug = "cli-item-policy"
    published_ref = "items/cli-published-item"
    unpublished_ref = "items/cli-unpublished-item"
    write_manage_campaign_fixture(
        Path(app.config["TEST_CAMPAIGNS_DIR"]),
        campaign_slug=campaign_slug,
        pages=((published_ref, True), (unpublished_ref, False)),
    )
    with app.app_context():
        app.extensions["repository_store"].refresh()
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        auth_store = app.extensions["auth_store"]
        library_slug = service.get_campaign_library_slug(campaign_slug)
        source_id = service.get_campaign_custom_source_id(campaign_slug)

        def systems_state():
            source = store.get_source(library_slug, source_id)
            return (
                source,
                store.get_campaign_policy(campaign_slug),
                store.get_campaign_enabled_source(campaign_slug, source_id),
                tuple(
                    store.list_entries_for_source(
                        library_slug,
                        source_id,
                        limit=None,
                    )
                )
                if source is not None
                else (),
                tuple(store.list_campaign_entry_overrides(campaign_slug, library_slug)),
                tuple(
                    auth_store.list_recent_audit_events(
                        event_type="campaign_systems_item_mechanics_imported",
                        campaign_slug=campaign_slug,
                    )
                ),
            )

        before = systems_state()

    rejected = run_manage_for_app(
        app,
        "import-campaign-item-mechanics",
        campaign_slug,
        unpublished_ref,
        "--review-status",
        "approved",
        "--actor-email",
        users["dm"]["email"],
    )
    assert rejected.returncode != 0
    assert rejected.stdout == ""
    assert (
        "Choose a valid published item page before importing item mechanics."
        in rejected.stderr
    )
    with app.app_context():
        assert systems_state() == before

    imported = run_manage_for_app(
        app,
        "import-campaign-item-mechanics",
        campaign_slug,
        "--review-status",
        "approved",
        "--actor-email",
        users["dm"]["email"],
    )
    assert imported.returncode == 0, imported.stderr
    assert published_ref in imported.stdout
    assert unpublished_ref not in imported.stdout
    with app.app_context():
        assert service.get_campaign_item_entry_by_page_ref(
            campaign_slug,
            published_ref,
        ) is not None
        assert (
            service.get_campaign_item_entry_by_page_ref(
                campaign_slug,
                unpublished_ref,
            )
            is None
        )
        audits = auth_store.list_recent_audit_events(
            event_type="campaign_systems_item_mechanics_imported",
            campaign_slug=campaign_slug,
        )
        assert {str(event.metadata["page_ref"]) for event in audits} == {
            published_ref
        }


def test_manage_campaign_item_mechanics_implicit_empty_list_keeps_message(app, users):
    campaign_slug = "cli-unpublished-items"
    unpublished_ref = "items/cli-only-unpublished-item"
    write_manage_campaign_fixture(
        Path(app.config["TEST_CAMPAIGNS_DIR"]),
        campaign_slug=campaign_slug,
        pages=((unpublished_ref, False),),
    )

    result = run_manage_for_app(
        app,
        "import-campaign-item-mechanics",
        campaign_slug,
        "--review-status",
        "approved",
        "--actor-email",
        users["dm"]["email"],
    )
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr.strip().endswith(
        f"No published item pages found for {campaign_slug}."
    )
    with app.app_context():
        app.extensions["repository_store"].refresh()
        service = app.extensions["systems_service"]
        auth_store = app.extensions["auth_store"]
        assert service.list_campaign_item_page_rows(campaign_slug) == []
        assert (
            service.get_campaign_item_entry_by_page_ref(
                campaign_slug,
                unpublished_ref,
            )
            is None
        )
        assert auth_store.list_recent_audit_events(
            event_type="campaign_systems_item_mechanics_imported",
            campaign_slug=campaign_slug,
        ) == []


def test_resolve_fly_machine_id_prefers_started_machine(monkeypatch):
    def fake_run_flyctl_command(flyctl_path, arguments, *, capture_output=True):
        assert flyctl_path == "flyctl"
        assert arguments == ["machine", "list", "-a", "example-app", "--json"]
        return subprocess.CompletedProcess(
            [flyctl_path, *arguments],
            0,
            stdout=(
                '[{"id":"stopped-id","state":"stopped"},'
                '{"id":"started-id","state":"started"}]'
            ),
            stderr="",
        )

    monkeypatch.setattr("player_wiki.operations.run_flyctl_command", fake_run_flyctl_command)

    assert resolve_fly_machine_id(flyctl_path="flyctl", app_name="example-app") == "started-id"


def test_build_flyctl_environment_loads_saved_token_from_local_fly_config(tmp_path):
    fly_dir = tmp_path / ".fly"
    fly_dir.mkdir()
    (fly_dir / "config.yml").write_text('access_token: "saved-token"\n', encoding="utf-8")

    env = {
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
    }

    resolved_env = build_flyctl_environment(env)

    assert resolved_env["FLY_ACCESS_TOKEN"] == "saved-token"


def test_build_flyctl_environment_keeps_existing_shell_token(tmp_path):
    fly_dir = tmp_path / ".fly"
    fly_dir.mkdir()
    (fly_dir / "config.yml").write_text('access_token: "saved-token"\n', encoding="utf-8")

    env = {
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "FLY_ACCESS_TOKEN": "shell-token",
    }

    resolved_env = build_flyctl_environment(env)

    assert resolved_env["FLY_ACCESS_TOKEN"] == "shell-token"


def test_run_flyctl_command_passes_resolved_environment(monkeypatch, tmp_path):
    fly_dir = tmp_path / ".fly"
    fly_dir.mkdir()
    (fly_dir / "config.yml").write_text("access_token: saved-token\n", encoding="utf-8")

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("FLY_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FLYCTL_ACCESS_TOKEN", raising=False)

    captured = {}

    def fake_run(command, *, check, capture_output, text, env):
        captured["command"] = command
        captured["check"] = check
        captured["capture_output"] = capture_output
        captured["text"] = text
        captured["env"] = env
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    run_flyctl_command("flyctl", ["status", "-a", "example-app"])

    assert captured["command"] == ["flyctl", "status", "-a", "example-app"]
    assert captured["check"] is True
    assert captured["capture_output"] is True
    assert captured["text"] is True
    assert captured["env"]["FLY_ACCESS_TOKEN"] == "saved-token"


def test_sync_local_state_from_fly_restores_db_and_campaigns(tmp_path, monkeypatch):
    active_db = tmp_path / "active" / "player_wiki.sqlite3"
    active_campaigns = tmp_path / "active" / "campaigns"
    backup_root = tmp_path / "backups"
    remote_db = tmp_path / "remote" / "player_wiki.sqlite3"
    remote_campaigns = tmp_path / "remote" / "campaigns"
    remote_archive = tmp_path / "remote" / "campaigns.tar.gz"

    write_database(active_db, "local-state")
    (active_campaigns / "linden-pass" / "content").mkdir(parents=True)
    (active_campaigns / "linden-pass" / "content" / "page.md").write_text("local page", encoding="utf-8")
    (active_campaigns / "README.md").write_text("local placeholder", encoding="utf-8")
    (active_campaigns / ".gitkeep").write_text("", encoding="utf-8")

    write_database(remote_db, "fly-state")
    (remote_campaigns / "linden-pass" / "content").mkdir(parents=True)
    (remote_campaigns / "linden-pass" / "content" / "page.md").write_text("fly page", encoding="utf-8")
    create_campaigns_archive(remote_archive, remote_campaigns)

    monkeypatch.setattr("player_wiki.operations.resolve_fly_machine_id", lambda **kwargs: "machine-123")

    def fake_pull_fly_database(*, flyctl_path, app_name, remote_db_path, output_path, machine_id=None):
        assert flyctl_path == "flyctl"
        assert app_name == "example-app"
        assert remote_db_path == "/data/player_wiki.sqlite3"
        assert machine_id == "machine-123"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(remote_db.read_bytes())
        return FlyDatabasePullResult(
            app_name=app_name,
            machine_id=machine_id,
            output_path=output_path,
            remote_db_path=remote_db_path,
        )

    monkeypatch.setattr("player_wiki.operations.pull_fly_database", fake_pull_fly_database)

    def fake_run_flyctl_command(flyctl_path, arguments, *, capture_output=True):
        assert flyctl_path == "flyctl"
        if arguments[:3] == ["machine", "exec", "-a"]:
            return subprocess.CompletedProcess([flyctl_path, *arguments], 0, stdout="", stderr="")
        if arguments[:4] == ["ssh", "sftp", "get", "/data/player_wiki.campaigns-sync.tar.gz"]:
            output_path = Path(arguments[4])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(remote_archive.read_bytes())
            return subprocess.CompletedProcess([flyctl_path, *arguments], 0, stdout="", stderr="")
        raise AssertionError(f"Unexpected flyctl arguments: {arguments}")

    monkeypatch.setattr("player_wiki.operations.run_flyctl_command", fake_run_flyctl_command)

    result = sync_local_state_from_fly(
        flyctl_path="flyctl",
        app_name="example-app",
        remote_db_path="/data/player_wiki.sqlite3",
        remote_campaigns_dir="/data/campaigns",
        db_path=active_db,
        campaigns_dir=active_campaigns,
        backup_root=backup_root,
    )

    assert result.app_name == "example-app"
    assert result.machine_id == "machine-123"
    assert result.pre_sync_backup_path is not None
    assert result.pre_sync_backup_path.exists()
    assert read_database_value(active_db) == "fly-state"
    assert (active_campaigns / "linden-pass" / "content" / "page.md").read_text(encoding="utf-8") == "fly page"
    assert (active_campaigns / "README.md").read_text(encoding="utf-8") == "local placeholder"
    assert (active_campaigns / ".gitkeep").exists()


def test_artifact_inventory_cli_is_explicit_redacted_and_zero_write(tmp_path):
    root = tmp_path / "private-root-slug"
    artifact = root / "secret-name-deadbeef.bin"
    root.mkdir()
    artifact.write_bytes(b"private-content")
    before = (
        artifact.stat().st_size,
        artifact.stat().st_mtime_ns,
        artifact.read_bytes(),
    )

    result = run_ops(
        "artifact-inventory",
        "--scratch-root",
        str(root),
        "--as-of-epoch",
        "2000000000",
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["mode"] == "inventory"
    assert report["classes"]["local_scratch"]["count"] == 1
    assert "advisory_alerts" not in report
    rendered = result.stdout + result.stderr
    for private_value in (
        str(root),
        root.name,
        artifact.name,
        "secret-name",
        "deadbeef",
        "private-content",
    ):
        assert private_value not in rendered
    assert (
        artifact.stat().st_size,
        artifact.stat().st_mtime_ns,
        artifact.read_bytes(),
    ) == before


def test_artifact_retention_cli_reports_only_nonactionable_advice(tmp_path):
    root = tmp_path / "scratch"
    root.mkdir()
    artifact = root / "one.bin"
    artifact.write_bytes(b"sample")
    old = 2_000_000_000 - 8 * 24 * 60 * 60
    os.utime(artifact, (old, old))

    result = run_ops(
        "artifact-retention-assess",
        "--scratch-root",
        str(root),
        "--as-of-epoch",
        "2000000000",
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["mode"] == "retention_assessment"
    assert all(row["advisory"] for row in report["advisory_alerts"])
    assert not any(row["actionable"] for row in report["advisory_alerts"])


def test_artifact_inventory_cli_requires_a_root_with_sanitized_error():
    result = run_ops("artifact-inventory")

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr.strip() == (
        "Artifact inventory could not inspect the requested roots safely."
    )
    assert "Traceback" not in result.stderr


def test_local_script_exposes_zero_write_artifact_actions_from_arbitrary_cwd(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "local.ps1"
    root = tmp_path / "private-root"
    root.mkdir()
    artifact = root / "private-file.bin"
    artifact.write_bytes(b"sample")
    invocation_cwd = tmp_path / "unrelated-cwd"
    invocation_cwd.mkdir()

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Action",
            "artifact-inventory",
            "-PythonPath",
            sys.executable,
            "-ArtifactScratchRoot",
            str(root),
            "-ArtifactAsOfEpoch",
            "2000000000",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=invocation_cwd,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["classes"]["local_scratch"]["count"] == 1
    assert list(invocation_cwd.iterdir()) == []
    rendered = result.stdout + result.stderr
    assert str(root) not in rendered
    assert artifact.name not in rendered


def test_local_artifact_action_missing_root_has_sanitized_error(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(project_root / "local.ps1"),
            "-Action",
            "artifact-retention-assess",
            "-PythonPath",
            sys.executable,
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.strip() == "At least one explicit artifact root is required."
    assert str(project_root) not in result.stderr


def test_local_reconciliation_dry_run_is_zero_temp_from_arbitrary_cwd(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    database = tmp_path / "state" / "wiki.sqlite3"
    campaigns = tmp_path / "campaigns"
    campaign = campaigns / "test-campaign"
    content = campaign / "content"
    content.mkdir(parents=True)
    (campaign / "assets").mkdir()
    (campaign / "campaign.yaml").write_text(
        "title: Test Campaign\nslug: test-campaign\nplayer_content_dir: content\nasset_dir: assets\n",
        encoding="utf-8",
    )
    desired = b"desired"
    (content / "page.md").write_bytes(desired)
    init_database(database)
    digest = hashlib.sha256(desired).hexdigest()
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
                "a" * 32,
                "test-campaign",
                "page",
                "update",
                "markdown",
                "page.md",
                "",
                digest,
                "",
                digest,
                sqlite3.Binary(desired),
                None,
                None,
                None,
                "prepared",
                "",
                "2026-07-18T12:00:00+00:00",
                "2026-07-18T12:00:00+00:00",
            ),
        )
        connection.commit()
    invocation_cwd = tmp_path / "unrelated-cwd"
    invocation_cwd.mkdir()
    env = os.environ.copy()
    env["PLAYER_WIKI_DB_PATH"] = str(database)
    env["PLAYER_WIKI_CAMPAIGNS_DIR"] = str(campaigns)

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(project_root / "local.ps1"),
            "-Action",
            "player-wiki-reconciliation-dry-run",
            "-PythonPath",
            sys.executable,
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=invocation_cwd,
        env=env,
    )

    assert result.returncode == 1, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout)["consistency"] == "stable"
    assert list(invocation_cwd.iterdir()) == []
    assert not Path(f"{database}.runtime.lock").exists()
    assert not Path(f"{database}-wal").exists()
    assert not Path(f"{database}-shm").exists()


def test_local_reconciliation_dry_run_propagates_sanitized_exit_without_writes(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    missing_parent = tmp_path / "missing-state"
    database = missing_parent / "wiki.sqlite3"
    campaigns = tmp_path / "campaigns"
    campaigns.mkdir()
    invocation_cwd = tmp_path / "unrelated-cwd"
    invocation_cwd.mkdir()
    env = os.environ.copy()
    env["PLAYER_WIKI_DB_PATH"] = str(database)
    env["PLAYER_WIKI_CAMPAIGNS_DIR"] = str(campaigns)

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(project_root / "local.ps1"),
            "-Action",
            "player-wiki-reconciliation-dry-run",
            "-PythonPath",
            sys.executable,
            "-ReconciliationPageRef",
            "private/page",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=invocation_cwd,
        env=env,
    )

    assert result.returncode == 2
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report["error"]["reason_code"] == "page_ref_requires_campaign_filter"
    assert "private/page" not in result.stdout
    assert not missing_parent.exists()
    assert list(invocation_cwd.iterdir()) == []


def test_reconciliation_apply_parse_errors_are_redacted_json():
    secret = "private-unsupported-action"
    result = run_ops(
        "player-wiki-reconciliation-apply",
        "--kind",
        "publication",
        "--operation-id",
        "a" * 32,
        "--action",
        secret,
        "--yes",
    )

    assert result.returncode == 2
    assert result.stderr == ""
    assert json.loads(result.stdout)["error"]["reason_code"] == "invalid_arguments"
    assert secret not in result.stdout


def test_local_reconciliation_apply_requires_explicit_confirmation_with_redacted_output(
    tmp_path,
):
    project_root = Path(__file__).resolve().parents[1]
    invocation_cwd = tmp_path / "unrelated-cwd"
    invocation_cwd.mkdir()
    private_db = tmp_path / "private-state" / "wiki.sqlite3"
    private_campaigns = tmp_path / "private-campaigns"
    env = os.environ.copy()
    env["PLAYER_WIKI_DB_PATH"] = str(private_db)
    env["PLAYER_WIKI_CAMPAIGNS_DIR"] = str(private_campaigns)

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(project_root / "local.ps1"),
            "-Action",
            "player-wiki-reconciliation-apply",
            "-PythonPath",
            sys.executable,
            "-ReconciliationKind",
            "publication",
            "-ReconciliationOperationId",
            "a" * 32,
            "-ReconciliationApplyAction",
            "resume-forward",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=invocation_cwd,
        env=env,
    )

    assert result.returncode == 2
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report["error"]["reason_code"] == "confirmation_required"
    rendered = result.stdout + result.stderr
    assert str(private_db) not in rendered
    assert str(private_campaigns) not in rendered
    assert not private_db.parent.exists()
    assert not private_campaigns.exists()
    assert list(invocation_cwd.iterdir()) == []
