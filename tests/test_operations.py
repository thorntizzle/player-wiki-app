from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

from player_wiki.operations import (
    FlyDatabasePullResult,
    create_backup_archive,
    resolve_fly_machine_id,
    restore_backup_archive,
    sync_local_state_from_fly,
)


def write_database(db_path: Path, value: str) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE sample_state (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample_state (value) VALUES (?)", (value,))
        connection.commit()


def read_database_value(db_path: Path) -> str:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute("SELECT value FROM sample_state").fetchone()
    assert row is not None
    return str(row[0])


def update_database_value(db_path: Path, value: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE sample_state SET value = ?", (value,))
        connection.commit()


def create_campaigns_archive(archive_path: Path, campaigns_dir: Path) -> None:
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(campaigns_dir, arcname="campaigns")


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
    assert len(list(backup_root.glob("*.zip"))) == 2


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
