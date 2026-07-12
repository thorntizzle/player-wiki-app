from __future__ import annotations

import os
import json
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
