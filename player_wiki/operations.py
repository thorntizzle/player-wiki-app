from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import zipfile
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .db import SCHEMA

BACKUP_FORMAT_VERSION = 1


@dataclass(slots=True)
class BackupResult:
    archive_path: Path
    created_at: str
    database_filename: str
    campaign_file_count: int


@dataclass(slots=True)
class RestoreResult:
    archive_path: Path
    restored_campaign_files: int
    database_path: Path


@dataclass(slots=True)
class FlyDatabasePullResult:
    app_name: str
    machine_id: str
    output_path: Path
    remote_db_path: str


@dataclass(slots=True)
class FlyCampaignBootstrapResult:
    app_name: str
    machine_id: str
    remote_source_dir: str
    remote_target_dir: str
    status: str


@dataclass(slots=True)
class FlyLocalSyncResult:
    app_name: str
    machine_id: str
    database_path: Path
    campaigns_dir: Path
    pre_sync_backup_path: Path | None
    remote_db_path: str
    remote_campaigns_dir: str


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_backup_root(project_root: Path) -> Path:
    return project_root / ".local" / "backups"


def default_fly_sync_root(project_root: Path) -> Path:
    return project_root / ".local" / "fly-sync"


def default_flyctl_path() -> str:
    override = os.getenv("PLAYER_WIKI_FLYCTL_PATH", "").strip()
    if override:
        return override

    home_flyctl = Path.home() / ".fly" / "bin" / "flyctl.exe"
    if home_flyctl.exists():
        return str(home_flyctl)
    return "flyctl"


def sanitize_backup_label(label: str | None) -> str:
    if not label:
        return ""
    sanitized = re.sub(r"[^a-z0-9_-]+", "-", label.strip().lower())
    return sanitized.strip("-_")


def create_backup_archive(
    *,
    db_path: Path,
    campaigns_dir: Path,
    backup_root: Path,
    label: str | None = None,
) -> BackupResult:
    current_time = datetime.now(timezone.utc).replace(microsecond=0)
    created_at = current_time.isoformat()
    timestamp = current_time.strftime("%Y%m%dT%H%M%SZ")
    safe_label = sanitize_backup_label(label)
    archive_name = f"player-wiki-backup-{timestamp}"
    if safe_label:
        archive_name = f"{archive_name}-{safe_label}"

    backup_root.mkdir(parents=True, exist_ok=True)
    archive_path = backup_root / f"{archive_name}.zip"
    campaigns_dir = campaigns_dir.resolve()
    database_filename = db_path.name or "player_wiki.sqlite3"

    with tempfile.TemporaryDirectory() as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        database_snapshot = temp_dir / database_filename
        snapshot_database(db_path=db_path, destination_path=database_snapshot)
        manifest = {
            "format_version": BACKUP_FORMAT_VERSION,
            "created_at": created_at,
            "database_filename": database_filename,
            "campaigns_dir_name": campaigns_dir.name,
        }

        campaign_file_count = 0
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
            archive.write(database_snapshot, arcname=f"database/{database_filename}")

            if campaigns_dir.exists():
                for file_path in sorted(path for path in campaigns_dir.rglob("*") if path.is_file()):
                    relative_path = file_path.relative_to(campaigns_dir)
                    archive.write(file_path, arcname=(PurePosixPath("campaigns") / relative_path.as_posix()).as_posix())
                    campaign_file_count += 1

    return BackupResult(
        archive_path=archive_path,
        created_at=created_at,
        database_filename=database_filename,
        campaign_file_count=campaign_file_count,
    )


def restore_backup_archive(
    *,
    archive_path: Path,
    db_path: Path,
    campaigns_dir: Path,
) -> RestoreResult:
    archive_path = archive_path.resolve()
    if not archive_path.exists():
        raise FileNotFoundError(f"Backup archive not found: {archive_path}")

    with tempfile.TemporaryDirectory() as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        with zipfile.ZipFile(archive_path, "r") as archive:
            extract_archive(archive, temp_dir)

        manifest = load_manifest(temp_dir / "manifest.json")
        if int(manifest.get("format_version", 0)) != BACKUP_FORMAT_VERSION:
            raise RuntimeError("Unsupported backup archive format.")

        extracted_campaigns_dir = temp_dir / "campaigns"
        extracted_database_path = temp_dir / "database" / str(manifest["database_filename"])

        if not extracted_database_path.exists():
            raise RuntimeError("Backup archive is missing the database snapshot.")

        campaigns_dir = campaigns_dir.resolve()
        db_path = db_path.resolve()
        restore_campaigns_directory(extracted_campaigns_dir, campaigns_dir)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(extracted_database_path, db_path)

        restored_campaign_files = sum(1 for path in campaigns_dir.rglob("*") if path.is_file()) if campaigns_dir.exists() else 0
        return RestoreResult(
            archive_path=archive_path,
            restored_campaign_files=restored_campaign_files,
            database_path=db_path,
        )


def run_flyctl_command(
    flyctl_path: str,
    arguments: list[str],
    *,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [flyctl_path, *arguments],
        check=True,
        capture_output=capture_output,
        text=True,
    )


def normalize_shell_script(script: str) -> str:
    return script.strip().replace("\r\n", "\n")


def resolve_fly_machine_id(
    *,
    flyctl_path: str,
    app_name: str,
    machine_id: str | None = None,
) -> str:
    if machine_id:
        return machine_id

    result = run_flyctl_command(
        flyctl_path,
        ["machine", "list", "-a", app_name, "--json"],
    )
    payload = json.loads(result.stdout)
    if not isinstance(payload, list) or not payload:
        raise RuntimeError(f"No Fly machines found for app '{app_name}'.")

    started_machines = [item for item in payload if str(item.get("state", "")).lower() == "started"]
    selected = started_machines[0] if started_machines else payload[0]
    selected_id = str(selected.get("id") or "").strip()
    if not selected_id:
        raise RuntimeError(f"Could not determine a Fly machine id for app '{app_name}'.")
    return selected_id


def pull_fly_database(
    *,
    flyctl_path: str,
    app_name: str,
    remote_db_path: str,
    output_path: Path,
    machine_id: str | None = None,
) -> FlyDatabasePullResult:
    resolved_machine_id = resolve_fly_machine_id(
        flyctl_path=flyctl_path,
        app_name=app_name,
        machine_id=machine_id,
    )
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    run_flyctl_command(
        flyctl_path,
        [
            "ssh",
            "sftp",
            "get",
            remote_db_path,
            str(output_path),
            "--app",
            app_name,
            "--machine",
            resolved_machine_id,
        ],
        capture_output=False,
    )
    return FlyDatabasePullResult(
        app_name=app_name,
        machine_id=resolved_machine_id,
        output_path=output_path,
        remote_db_path=remote_db_path,
    )


def bootstrap_fly_campaigns_volume(
    *,
    flyctl_path: str,
    app_name: str,
    remote_source_dir: str,
    remote_target_dir: str,
    machine_id: str | None = None,
) -> FlyCampaignBootstrapResult:
    resolved_machine_id = resolve_fly_machine_id(
        flyctl_path=flyctl_path,
        app_name=app_name,
        machine_id=machine_id,
    )
    script = (
        "set -eu\n"
        f'source_dir="{remote_source_dir}"\n'
        f'target_dir="{remote_target_dir}"\n'
        'if [ -d "$source_dir" ]; then\n'
        '  mkdir -p "$target_dir"\n'
        '  cp -R "$source_dir"/. "$target_dir"/\n'
        '  printf "ready"\n'
        'else\n'
        '  printf "missing-source"\n'
        "fi\n"
    )
    result = run_flyctl_command(
        flyctl_path,
        [
            "machine",
            "exec",
            "-a",
            app_name,
            "--timeout",
            "120",
            resolved_machine_id,
            "--",
            f"sh -lc '{normalize_shell_script(script)}'",
        ],
    )
    status = result.stdout.strip() or "unknown"
    return FlyCampaignBootstrapResult(
        app_name=app_name,
        machine_id=resolved_machine_id,
        remote_source_dir=remote_source_dir,
        remote_target_dir=remote_target_dir,
        status=status,
    )


def sync_local_state_from_fly(
    *,
    flyctl_path: str,
    app_name: str,
    remote_db_path: str,
    remote_campaigns_dir: str,
    db_path: Path,
    campaigns_dir: Path,
    backup_root: Path,
    machine_id: str | None = None,
    pre_sync_label: str = "pre-fly-sync",
    create_pre_sync_backup: bool = True,
) -> FlyLocalSyncResult:
    resolved_machine_id = resolve_fly_machine_id(
        flyctl_path=flyctl_path,
        app_name=app_name,
        machine_id=machine_id,
    )
    pre_sync_backup_path: Path | None = None

    with tempfile.TemporaryDirectory() as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        downloaded_db_path = temp_dir / (Path(remote_db_path).name or "player_wiki.fly.sqlite3")
        downloaded_campaigns_archive = temp_dir / "fly-campaigns.tar.gz"
        extracted_root = temp_dir / "campaigns-extract"
        remote_archive_path = "/data/player_wiki.campaigns-sync.tar.gz"
        preserved_campaign_root_files: dict[str, bytes] = {}

        pull_fly_database(
            flyctl_path=flyctl_path,
            app_name=app_name,
            remote_db_path=remote_db_path,
            output_path=downloaded_db_path,
            machine_id=resolved_machine_id,
        )

        archive_script = (
            "set -eu\n"
            f'remote_campaigns_dir="{remote_campaigns_dir}"\n'
            f'remote_archive_path="{remote_archive_path}"\n'
            'rm -f "$remote_archive_path"\n'
            'mkdir -p "$(dirname "$remote_archive_path")"\n'
            'mkdir -p "$remote_campaigns_dir"\n'
            'tar -C "$(dirname "$remote_campaigns_dir")" -czf "$remote_archive_path" "$(basename "$remote_campaigns_dir")"\n'
        )
        run_flyctl_command(
            flyctl_path,
            [
                "machine",
                "exec",
                "-a",
                app_name,
                "--timeout",
                "120",
                resolved_machine_id,
                "--",
                f"sh -lc '{normalize_shell_script(archive_script)}'",
            ],
        )

        try:
            run_flyctl_command(
                flyctl_path,
                [
                    "ssh",
                    "sftp",
                    "get",
                    remote_archive_path,
                    str(downloaded_campaigns_archive),
                    "--app",
                    app_name,
                    "--machine",
                    resolved_machine_id,
                ],
                capture_output=False,
            )
        finally:
            run_flyctl_command(
                flyctl_path,
                [
                    "machine",
                    "exec",
                    "-a",
                    app_name,
                    "--timeout",
                    "30",
                    resolved_machine_id,
                    "--",
                    f'sh -lc \'rm -f "{remote_archive_path}"\'',
                ],
            )

        extract_tar_archive(downloaded_campaigns_archive, extracted_root)
        extracted_campaigns_dir = extracted_root / Path(remote_campaigns_dir).name

        if create_pre_sync_backup:
            pre_sync_backup = create_backup_archive(
                db_path=db_path,
                campaigns_dir=campaigns_dir,
                backup_root=backup_root,
                label=pre_sync_label,
            )
            pre_sync_backup_path = pre_sync_backup.archive_path

        db_path = db_path.resolve()
        campaigns_dir = campaigns_dir.resolve()
        for placeholder_name in (".gitkeep", "README.md"):
            placeholder_path = campaigns_dir / placeholder_name
            if placeholder_path.exists() and placeholder_path.is_file():
                preserved_campaign_root_files[placeholder_name] = placeholder_path.read_bytes()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(downloaded_db_path, db_path)
        restore_campaigns_directory(extracted_campaigns_dir, campaigns_dir)
        for placeholder_name, data in preserved_campaign_root_files.items():
            placeholder_path = campaigns_dir / placeholder_name
            if not placeholder_path.exists():
                placeholder_path.write_bytes(data)

    return FlyLocalSyncResult(
        app_name=app_name,
        machine_id=resolved_machine_id,
        database_path=db_path,
        campaigns_dir=campaigns_dir,
        pre_sync_backup_path=pre_sync_backup_path,
        remote_db_path=remote_db_path,
        remote_campaigns_dir=remote_campaigns_dir,
    )


def snapshot_database(*, db_path: Path, destination_path: Path) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if destination_path.exists():
        destination_path.unlink()

    with closing(sqlite3.connect(destination_path)) as destination_connection:
        if db_path.exists():
            with closing(sqlite3.connect(db_path)) as source_connection:
                source_connection.backup(destination_connection)
        else:
            destination_connection.executescript(SCHEMA)
        destination_connection.commit()


def extract_archive(archive: zipfile.ZipFile, destination_dir: Path) -> None:
    for member_name in archive.namelist():
        pure_path = PurePosixPath(member_name)
        if pure_path.is_absolute() or ".." in pure_path.parts:
            raise RuntimeError(f"Unsafe backup archive member: {member_name}")
        if member_name.endswith("/"):
            continue

        destination_path = destination_dir.joinpath(*pure_path.parts)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member_name, "r") as source, destination_path.open("wb") as destination:
            shutil.copyfileobj(source, destination)


def extract_tar_archive(archive_path: Path, destination_dir: Path) -> None:
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            pure_path = PurePosixPath(member.name)
            if pure_path.is_absolute() or ".." in pure_path.parts:
                raise RuntimeError(f"Unsafe tar archive member: {member.name}")

        archive.extractall(destination_dir)


def load_manifest(manifest_path: Path) -> dict[str, object]:
    if not manifest_path.exists():
        raise RuntimeError("Backup archive is missing manifest.json.")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def restore_campaigns_directory(source_dir: Path, destination_dir: Path) -> None:
    if destination_dir.exists():
        if destination_dir.is_dir():
            shutil.rmtree(destination_dir)
        else:
            destination_dir.unlink()

    if source_dir.exists():
        shutil.copytree(source_dir, destination_dir)
    else:
        destination_dir.mkdir(parents=True, exist_ok=True)
