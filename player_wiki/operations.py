from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import tarfile
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .backup_archive import (
    DEFAULT_LIMITS,
    BackupArchiveEvidence,
    BackupArchiveLimits,
    create_backup_archive_v2,
    inspect_backup_archive,
)
from .local_temp import temporary_directory
from .restore_transaction import (
    RecoveryStatus,
    RestoreHooks,
    RestoreResult,
    RestoreTransactionError,
    inspect_restore_recovery,
    restore_backup_archive_atomic,
)
from .sqlite_safety import SQLiteSnapshotEvidence, snapshot_sqlite_database

BACKUP_FORMAT_VERSION = 2


@dataclass(slots=True)
class BackupResult:
    archive_path: Path
    created_at: str
    database_filename: str
    campaign_file_count: int
    evidence: BackupArchiveEvidence


@dataclass(frozen=True, slots=True)
class RestoreRehearsalResult:
    source_format_version: int
    source_verification_level: str
    source_manifest_hashes_verified: bool
    migration_applied_version: int
    migration_current_version: int
    migration_required: bool
    database_integrity_check: tuple[str, ...]
    database_foreign_key_violation_count: int
    campaign_file_count: int
    campaign_hashes_verified: bool
    prebackup_format_version: int
    prebackup_verification_level: str
    prebackup_manifest_hashes_verified: bool
    transaction_outcome: str
    recovery_state: str
    cleanup_verified: bool


class RestoreRehearsalError(RuntimeError):
    """Raised when an isolated restore rehearsal cannot prove its result."""


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


def load_saved_fly_access_token(env: dict[str, str] | None = None) -> str | None:
    effective_env = dict(os.environ if env is None else env)
    if str(effective_env.get("FLY_ACCESS_TOKEN", "")).strip():
        return None
    if str(effective_env.get("FLYCTL_ACCESS_TOKEN", "")).strip():
        return None

    home_dir = str(effective_env.get("HOME") or effective_env.get("USERPROFILE") or Path.home()).strip()
    if not home_dir:
        return None

    config_path = Path(home_dir) / ".fly" / "config.yml"
    if not config_path.exists():
        return None

    try:
        config_content = config_path.read_text(encoding="utf-8")
    except OSError:
        return None

    match = re.search(r"(?m)^access_token:\s*(.+?)\s*$", config_content)
    if match is None:
        return None

    token = match.group(1).strip().strip("'\"")
    return token or None


def build_flyctl_environment(env: dict[str, str] | None = None) -> dict[str, str]:
    resolved_env = dict(os.environ if env is None else env)
    if str(resolved_env.get("FLY_ACCESS_TOKEN", "")).strip():
        return resolved_env
    if str(resolved_env.get("FLYCTL_ACCESS_TOKEN", "")).strip():
        return resolved_env

    saved_token = load_saved_fly_access_token(env=resolved_env)
    if saved_token:
        resolved_env["FLY_ACCESS_TOKEN"] = saved_token
    return resolved_env


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
    limits: BackupArchiveLimits = DEFAULT_LIMITS,
) -> BackupResult:
    current_time = datetime.now(timezone.utc).replace(microsecond=0)
    created_at = current_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    timestamp = current_time.strftime("%Y%m%dT%H%M%SZ")
    safe_label = sanitize_backup_label(label)
    archive_name = f"player-wiki-backup-{timestamp}"
    if safe_label:
        archive_name = f"{archive_name}-{safe_label}"

    evidence = create_backup_archive_v2(
        db_path=db_path,
        campaigns_dir=campaigns_dir,
        backup_root=backup_root,
        archive_basename=archive_name,
        created_at=created_at,
        limits=limits,
        snapshotter=lambda *, source_path, destination_path: snapshot_database(
            db_path=source_path,
            destination_path=destination_path,
        ),
    )

    return BackupResult(
        archive_path=evidence.archive_path,
        created_at=created_at,
        database_filename=evidence.database_filename,
        campaign_file_count=evidence.campaign_file_count,
        evidence=evidence,
    )


def restore_backup_archive(
    *,
    archive_path: Path,
    db_path: Path,
    campaigns_dir: Path,
    backup_root: Path | None = None,
    limits: BackupArchiveLimits = DEFAULT_LIMITS,
    hooks: RestoreHooks | None = None,
) -> RestoreResult:
    return restore_backup_archive_atomic(
        archive_path=archive_path,
        db_path=db_path,
        campaigns_dir=campaigns_dir,
        backup_root=backup_root,
        limits=limits,
        hooks=hooks,
    )


def rehearse_restore_archive(
    *,
    archive_path: Path,
    limits: BackupArchiveLimits = DEFAULT_LIMITS,
) -> RestoreRehearsalResult:
    """Exercise a named archive against synthetic state in a disposable root."""

    source = inspect_backup_archive(Path(archive_path), limits=limits)
    workspace_path: Path | None = None
    result: RestoreRehearsalResult | None = None
    try:
        with temporary_directory(prefix="rr-") as temp_dir_name:
            workspace_path = Path(temp_dir_name)
            target_root = workspace_path
            target_db = target_root / "d"
            target_campaigns = target_root / "c"
            backup_root = workspace_path / "b"
            target_campaigns.mkdir()

            with closing(sqlite3.connect(target_db)) as connection:
                connection.execute(
                    "CREATE TABLE rehearsal_marker (value TEXT NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO rehearsal_marker VALUES ('synthetic-pre-restore-state')"
                )
                connection.commit()
            (target_campaigns / "synthetic-marker.txt").write_text(
                "synthetic-pre-restore-state\n",
                encoding="utf-8",
            )

            restore_events: list[str] = []
            try:
                restored = restore_backup_archive_atomic(
                    archive_path=Path(archive_path),
                    db_path=target_db,
                    campaigns_dir=target_campaigns,
                    backup_root=backup_root,
                    limits=limits,
                    hooks=RestoreHooks(restore_events.append),
                )
            except RestoreTransactionError as exc:
                last_event = restore_events[-1] if restore_events else "validation"
                raise RestoreRehearsalError(
                    f"The restore rehearsal transaction failed after {last_event}."
                ) from exc
            if restored.evidence != source:
                raise RestoreRehearsalError(
                    "The restored archive evidence changed during rehearsal."
                )
            if restored.prebackup_evidence is None:
                raise RestoreRehearsalError(
                    "The rehearsal did not create its mandatory pre-restore backup."
                )
            prebackup = inspect_backup_archive(
                restored.prebackup_evidence.archive_path,
                limits=limits,
            )
            if prebackup != restored.prebackup_evidence:
                raise RestoreRehearsalError(
                    "The mandatory pre-restore backup failed reinspection."
                )
            if (
                prebackup.format_version != 2
                or prebackup.verification_level != "verified_v2"
                or not prebackup.manifest_hashes_verified
            ):
                raise RestoreRehearsalError(
                    "The mandatory pre-restore backup evidence is insufficient."
                )

            database = restored.database_verification
            campaigns = restored.campaign_verification
            if database.integrity_check != ("ok",) or database.foreign_key_violations:
                raise RestoreRehearsalError(
                    "The rehearsal database verification failed."
                )
            if database.migration != source.migration:
                raise RestoreRehearsalError(
                    "The rehearsal migration evidence does not match the archive."
                )
            if restored.migration_required != (not source.migration.is_current):
                raise RestoreRehearsalError(
                    "The rehearsal migration requirement is inconsistent."
                )
            if (
                restored.restored_campaign_files != source.campaign_file_count
                or campaigns.file_count != source.campaign_file_count
                or campaigns.total_bytes != source.campaign_total_bytes
                or not campaigns.hashes_verified
            ):
                raise RestoreRehearsalError(
                    "The rehearsal campaign evidence does not match the archive."
                )

            recovery: RecoveryStatus = inspect_restore_recovery(db_path=target_db)
            if recovery.recovery_state != "clean" or recovery.recommended_action != "none":
                raise RestoreRehearsalError(
                    "The rehearsal left restore recovery state behind."
                )
            restore_artifacts = (
                list(target_root.glob(".*.restore-*.new"))
                + list(target_root.glob(".*.restore-*.old"))
                + list(target_root.glob("*.restore-journal.json"))
            )
            if restore_artifacts:
                raise RestoreRehearsalError(
                    "The rehearsal left restore transaction artifacts behind."
                )

            result = RestoreRehearsalResult(
                source_format_version=source.format_version,
                source_verification_level=source.verification_level,
                source_manifest_hashes_verified=source.manifest_hashes_verified,
                migration_applied_version=database.migration.applied_version,
                migration_current_version=database.migration.current_version,
                migration_required=restored.migration_required,
                database_integrity_check=database.integrity_check,
                database_foreign_key_violation_count=len(
                    database.foreign_key_violations
                ),
                campaign_file_count=campaigns.file_count,
                campaign_hashes_verified=campaigns.hashes_verified,
                prebackup_format_version=prebackup.format_version,
                prebackup_verification_level=prebackup.verification_level,
                prebackup_manifest_hashes_verified=(
                    prebackup.manifest_hashes_verified
                ),
                transaction_outcome=restored.outcome,
                recovery_state=recovery.recovery_state,
                cleanup_verified=True,
            )
    finally:
        if workspace_path is not None and os.path.lexists(workspace_path):
            raise RestoreRehearsalError(
                "The disposable restore rehearsal workspace was not removed."
            )

    if result is None:
        raise RestoreRehearsalError("The restore rehearsal did not complete.")
    return result


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
        env=build_flyctl_environment(),
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

    with temporary_directory(prefix="player-wiki-fly-sync-") as temp_dir_name:
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


def snapshot_database(*, db_path: Path, destination_path: Path) -> SQLiteSnapshotEvidence:
    return snapshot_sqlite_database(
        source_path=db_path,
        destination_path=destination_path,
    )


def extract_tar_archive(archive_path: Path, destination_dir: Path) -> None:
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            pure_path = PurePosixPath(member.name)
            if pure_path.is_absolute() or ".." in pure_path.parts:
                raise RuntimeError(f"Unsafe tar archive member: {member.name}")

        archive.extractall(destination_dir)


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
