from __future__ import annotations

import argparse
import os
from pathlib import Path

from player_wiki import create_app
from player_wiki.operations import (
    bootstrap_fly_campaigns_volume,
    create_backup_archive,
    default_fly_sync_root,
    default_flyctl_path,
    default_backup_root,
    pull_fly_database,
    restore_backup_archive,
    sync_local_state_from_fly,
)


DEFAULT_FLY_APP = os.getenv("PLAYER_WIKI_FLY_APP", "campaign-player-wiki-example")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create or restore local Campaign Player Wiki backups.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="Create a timestamped local backup archive.")
    backup.add_argument("--output-dir", help="Directory where the backup archive should be written.")
    backup.add_argument("--label", help="Optional label to include in the archive filename.")

    restore = subparsers.add_parser("restore", help="Restore a local backup archive into the active app paths.")
    restore.add_argument("archive_path", help="Path to a backup archive created by this tool.")
    restore.add_argument("--output-dir", help="Directory for the automatic pre-restore backup archive.")
    restore.add_argument("--pre-restore-label", default="pre-restore", help="Label for the automatic pre-restore backup.")
    restore.add_argument(
        "--skip-pre-restore-backup",
        action="store_true",
        help="Skip the automatic safety backup before overwriting local state.",
    )
    restore.add_argument(
        "--yes",
        action="store_true",
        help="Confirm that you want to overwrite the current local database and campaign content.",
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
    app = create_app()
    project_root = Path(__file__).resolve().parent

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

        if args.command == "restore":
            if not args.yes:
                raise SystemExit("Restore overwrites the current local database and campaign content. Re-run with --yes.")

            if not args.skip_pre_restore_backup:
                pre_restore_backup = create_backup_archive(
                    db_path=db_path,
                    campaigns_dir=campaigns_dir,
                    backup_root=backup_root,
                    label=args.pre_restore_label,
                )
                print(f"Created pre-restore safety backup: {pre_restore_backup.archive_path}")

            result = restore_backup_archive(
                archive_path=Path(args.archive_path),
                db_path=db_path,
                campaigns_dir=campaigns_dir,
            )
            print(f"Restored backup archive: {result.archive_path}")
            print(f"Database restored to: {result.database_path}")
            print(f"Campaign files restored: {result.restored_campaign_files}")
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
