from __future__ import annotations

import argparse
import os
from pathlib import Path

from player_wiki import create_app
from player_wiki.config import Config
from player_wiki.operations import (
    bootstrap_fly_campaigns_volume,
    create_backup_archive,
    default_fly_sync_root,
    default_flyctl_path,
    default_backup_root,
    inspect_backup_archive,
    pull_fly_database,
    rehearse_restore_archive,
    restore_backup_archive,
    sync_local_state_from_fly,
)
from player_wiki.restore_transaction import (
    inspect_restore_recovery,
    resume_restore,
    rollback_restore,
)


DEFAULT_FLY_APP = os.getenv("PLAYER_WIKI_FLY_APP", "campaign-player-wiki-example")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create or restore local Campaign Player Wiki backups.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="Create a timestamped local backup archive.")
    backup.add_argument("--output-dir", help="Directory where the backup archive should be written.")
    backup.add_argument("--label", help="Optional label to include in the archive filename.")

    inspect = subparsers.add_parser("inspect", help="Validate a backup archive without restoring it.")
    inspect.add_argument("archive_path", help="Path to the backup archive to inspect.")

    restore = subparsers.add_parser("restore", help="Restore a local backup archive into the active app paths.")
    restore.add_argument("archive_path", help="Path to a backup archive created by this tool.")
    restore.add_argument("--output-dir", help="Directory for the automatic pre-restore backup archive.")
    restore.add_argument(
        "--yes",
        action="store_true",
        help="Confirm that you want to overwrite the current local database and campaign content.",
    )

    subparsers.add_parser(
        "restore-status",
        help="Inspect whether an interrupted restore needs explicit recovery.",
    )

    restore_resume = subparsers.add_parser(
        "restore-resume",
        help="Resume and finish an interrupted restore transaction.",
    )
    restore_resume.add_argument(
        "--yes",
        action="store_true",
        help="Confirm mutation of the interrupted restore transaction.",
    )

    restore_rollback = subparsers.add_parser(
        "restore-rollback",
        help="Roll back an interrupted restore transaction when evidence permits.",
    )
    restore_rollback.add_argument(
        "--yes",
        action="store_true",
        help="Confirm mutation of the interrupted restore transaction.",
    )

    restore_rehearsal = subparsers.add_parser(
        "restore-rehearsal",
        help="Rehearse a restore entirely inside a disposable workspace.",
    )
    restore_rehearsal.add_argument(
        "archive_path",
        help="Path to the backup archive to rehearse.",
    )

    pull_fly_db = subparsers.add_parser(
        "pull-fly-db",
        help="Download the live Fly SQLite database without overwriting the active local state.",
    )
    pull_fly_db.add_argument("--app", default=DEFAULT_FLY_APP, help="Fly app name.")
    pull_fly_db.add_argument("--machine-id", help="Optional Fly machine id. Defaults to the first started machine.")
    pull_fly_db.add_argument("--remote-db-path", default="/data/player_wiki.sqlite3", help="Remote SQLite path on Fly.")
    pull_fly_db.add_argument("--output-path", help="Local output path for the downloaded database snapshot.")
    pull_fly_db.add_argument("--flyctl-path", default=default_flyctl_path(), help="Path to flyctl.")

    prepare_fly_campaigns = subparsers.add_parser(
        "prepare-fly-campaigns",
        help="Seed /data campaign content on Fly from the current image content if the volume is still empty.",
    )
    prepare_fly_campaigns.add_argument("--app", default=DEFAULT_FLY_APP, help="Fly app name.")
    prepare_fly_campaigns.add_argument(
        "--machine-id",
        help="Optional Fly machine id. Defaults to the first started machine.",
    )
    prepare_fly_campaigns.add_argument(
        "--remote-source-dir",
        default="/app/campaigns",
        help="Current image-backed campaigns directory on Fly.",
    )
    prepare_fly_campaigns.add_argument(
        "--remote-target-dir",
        default="/data/campaigns",
        help="Volume-backed campaigns directory on Fly.",
    )
    prepare_fly_campaigns.add_argument("--flyctl-path", default=default_flyctl_path(), help="Path to flyctl.")

    sync_from_fly = subparsers.add_parser(
        "sync-from-fly",
        help="Mirror the live Fly database and campaign content into the active local app paths.",
    )
    sync_from_fly.add_argument("--app", default=DEFAULT_FLY_APP, help="Fly app name.")
    sync_from_fly.add_argument("--machine-id", help="Optional Fly machine id. Defaults to the first started machine.")
    sync_from_fly.add_argument("--remote-db-path", default="/data/player_wiki.sqlite3", help="Remote SQLite path on Fly.")
    sync_from_fly.add_argument(
        "--remote-campaigns-dir",
        default="/data/campaigns",
        help="Remote campaigns directory on Fly.",
    )
    sync_from_fly.add_argument(
        "--output-dir",
        help="Directory for the automatic pre-sync backup archive. Defaults to the standard local backup root.",
    )
    sync_from_fly.add_argument(
        "--pre-sync-label",
        default="pre-fly-sync",
        help="Label for the automatic safety backup created before overwriting local state.",
    )
    sync_from_fly.add_argument(
        "--skip-pre-sync-backup",
        action="store_true",
        help="Skip the automatic safety backup before overwriting local state.",
    )
    sync_from_fly.add_argument(
        "--yes",
        action="store_true",
        help="Confirm that you want to overwrite the active local database and campaign content.",
    )
    sync_from_fly.add_argument("--flyctl-path", default=default_flyctl_path(), help="Path to flyctl.")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parent

    if args.command == "inspect":
        evidence = inspect_backup_archive(Path(args.archive_path))
        print(f"Inspected backup archive: {evidence.archive_path}")
        print(f"Backup format: v{evidence.format_version} ({evidence.verification_level})")
        print(f"Manifest hashes verified: {str(evidence.manifest_hashes_verified).lower()}")
        print(f"Database integrity: {','.join(evidence.database_integrity_check)}")
        print(f"Campaign files: {evidence.campaign_file_count}")
        return

    if args.command == "restore":
        if not args.yes:
            raise SystemExit("Restore overwrites the current local database and campaign content. Re-run with --yes.")

        db_path = Path(Config.DB_PATH)
        campaigns_dir = Path(Config.CAMPAIGNS_DIR)
        backup_root = Path(args.output_dir).resolve() if args.output_dir else default_backup_root(project_root)

        # Validate before the transaction takes its mandatory pre-restore
        # backup; restore validates again before any target mutation.
        inspect_backup_archive(Path(args.archive_path))
        result = restore_backup_archive(
            archive_path=Path(args.archive_path),
            db_path=db_path,
            campaigns_dir=campaigns_dir,
            backup_root=backup_root,
        )
        if result.prebackup_evidence is not None:
            print(f"Created pre-restore safety backup: {result.prebackup_evidence.archive_path}")
        print(f"Restored backup archive: {result.archive_path}")
        print(f"Database restored to: {result.database_path}")
        print(f"Campaign files restored: {result.restored_campaign_files}")
        return

    if args.command == "restore-status":
        try:
            status = inspect_restore_recovery(db_path=Path(Config.DB_PATH))
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from None
        print(f"Recovery state: {status.recovery_state}")
        print(f"Transaction: {status.transaction_id or 'none'}")
        print(f"Phase: {status.phase or 'none'}")
        if status.recovery_origin is not None:
            print(f"Recovery origin: {status.recovery_origin}")
        print(f"Recommended action: {status.recommended_action}")
        return

    if args.command in ("restore-resume", "restore-rollback"):
        if not args.yes:
            raise SystemExit(
                "Restore recovery mutates transaction state. Re-run with --yes."
            )
        try:
            recovery = (
                resume_restore(db_path=Path(Config.DB_PATH))
                if args.command == "restore-resume"
                else rollback_restore(db_path=Path(Config.DB_PATH))
            )
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from None
        print(f"Transaction: {recovery.transaction_id or 'none'}")
        print(f"Action: {recovery.action}")
        print(f"Outcome: {recovery.outcome}")
        print(f"Recovery state: {recovery.recovery_state}")
        return

    if args.command == "restore-rehearsal":
        try:
            rehearsal = rehearse_restore_archive(
                archive_path=Path(args.archive_path)
            )
        except (OSError, RuntimeError) as exc:
            raise SystemExit(str(exc)) from None
        print("Restore rehearsal: pass")
        print(
            "Archive evidence: "
            f"v{rehearsal.source_format_version} "
            f"({rehearsal.source_verification_level})"
        )
        print(
            "Manifest hashes verified: "
            f"{str(rehearsal.source_manifest_hashes_verified).lower()}"
        )
        print(f"Migration applied version: {rehearsal.migration_applied_version}")
        print(f"Migration current version: {rehearsal.migration_current_version}")
        print(f"Migration required: {str(rehearsal.migration_required).lower()}")
        print(
            "Database integrity: "
            f"{','.join(rehearsal.database_integrity_check)}"
        )
        print(
            "Foreign key violations: "
            f"{rehearsal.database_foreign_key_violation_count}"
        )
        print(f"Campaign files: {rehearsal.campaign_file_count}")
        print(
            "Campaign hashes verified: "
            f"{str(rehearsal.campaign_hashes_verified).lower()}"
        )
        print(
            "Mandatory prebackup: "
            f"v{rehearsal.prebackup_format_version} "
            f"({rehearsal.prebackup_verification_level})"
        )
        print(
            "Mandatory prebackup manifest hashes verified: "
            f"{str(rehearsal.prebackup_manifest_hashes_verified).lower()}"
        )
        print(f"Transaction outcome: {rehearsal.transaction_outcome}")
        print(f"Recovery state: {rehearsal.recovery_state}")
        print(f"Disposable cleanup: {str(rehearsal.cleanup_verified).lower()}")
        return

    app = create_app()

    with app.app_context():
        db_path = Path(app.config["DB_PATH"])
        campaigns_dir = Path(app.config["CAMPAIGNS_DIR"])
        backup_root = Path(args.output_dir).resolve() if getattr(args, "output_dir", None) else default_backup_root(project_root)

        if args.command == "backup":
            result = create_backup_archive(
                db_path=db_path,
                campaigns_dir=campaigns_dir,
                backup_root=backup_root,
                label=args.label,
            )
            print(f"Created backup archive: {result.archive_path}")
            print(f"Campaign files included: {result.campaign_file_count}")
            print(f"Database snapshot: {result.database_filename}")
            return

        if args.command == "pull-fly-db":
            output_path = (
                Path(args.output_path).resolve()
                if args.output_path
                else default_fly_sync_root(project_root) / "player_wiki.fly.sqlite3"
            )
            result = pull_fly_database(
                flyctl_path=args.flyctl_path,
                app_name=args.app,
                remote_db_path=args.remote_db_path,
                output_path=output_path,
                machine_id=args.machine_id,
            )
            print(f"Downloaded Fly database from {result.app_name} ({result.machine_id})")
            print(f"Remote path: {result.remote_db_path}")
            print(f"Local path: {result.output_path}")
            return

        if args.command == "prepare-fly-campaigns":
            result = bootstrap_fly_campaigns_volume(
                flyctl_path=args.flyctl_path,
                app_name=args.app,
                remote_source_dir=args.remote_source_dir,
                remote_target_dir=args.remote_target_dir,
                machine_id=args.machine_id,
            )
            print(f"Prepared Fly campaigns directory for {result.app_name} ({result.machine_id})")
            print(f"Source: {result.remote_source_dir}")
            print(f"Target: {result.remote_target_dir}")
            print(f"Status: {result.status}")
            return

        if args.command == "sync-from-fly":
            if not args.yes:
                raise SystemExit(
                    "Sync overwrites the current local database and campaign content. Re-run with --yes."
                )

            result = sync_local_state_from_fly(
                flyctl_path=args.flyctl_path,
                app_name=args.app,
                remote_db_path=args.remote_db_path,
                remote_campaigns_dir=args.remote_campaigns_dir,
                db_path=db_path,
                campaigns_dir=campaigns_dir,
                backup_root=backup_root,
                machine_id=args.machine_id,
                pre_sync_label=args.pre_sync_label,
                create_pre_sync_backup=not args.skip_pre_sync_backup,
            )
            if result.pre_sync_backup_path is not None:
                print(f"Created pre-sync safety backup: {result.pre_sync_backup_path}")
            print(f"Mirrored Fly state from {result.app_name} ({result.machine_id})")
            print(f"Database restored to: {result.database_path}")
            print(f"Campaigns restored to: {result.campaigns_dir}")
            return

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
