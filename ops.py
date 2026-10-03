from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from player_wiki import create_app
from player_wiki.artifact_retention import ArtifactRoot, build_artifact_report
from player_wiki.config import Config
from player_wiki.player_wiki_reconciliation_inspection import (
    InspectionFilters,
    inspect_player_wiki_reconciliation,
)
from player_wiki.player_wiki_reconciliation_operations import (
    PlayerWikiReconciliationOperationError,
    apply_player_wiki_reconciliation_operation,
)
from player_wiki.operations import (
    bootstrap_fly_campaigns_volume,
    create_backup_archive,
    create_fly_sync_capture_archive,
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
from player_wiki.committed_activation import ActivationRefused, ActivationUncertain, activate, inspect_activation


DEFAULT_FLY_APP = os.getenv("PLAYER_WIKI_FLY_APP", "campaign-player-wiki-example")


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        if len(sys.argv) > 1 and sys.argv[1] == "player-wiki-reconciliation-apply":
            print(
                json.dumps(
                    {
                        "error": {"reason_code": "invalid_arguments"},
                        "outcome": "refused",
                        "schema_version": 1,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            raise SystemExit(2)
        if len(sys.argv) > 1 and sys.argv[1] == "player-wiki-reconciliation-dry-run":
            report = {
                "consistency": "invalid",
                "counts": {
                    "by_classification": {},
                    "by_kind": {},
                    "by_state": {},
                    "total": 0,
                },
                "error": {"reason_code": "invalid_arguments"},
                "migration": {
                    "compatibility": "untrusted",
                    "evidence_status": "failed",
                    "migration_required": False,
                },
                "operations": [],
                "schema_version": 1,
                "scope": {
                    "campaign_filter_present": False,
                    "kind": "all",
                    "operation_id_filter_present": False,
                    "page_ref_filter_present": False,
                    "state_filter_present": False,
                },
            }
            print(json.dumps(report, sort_keys=True, separators=(",", ":")))
            raise SystemExit(2)
        super().error(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(description="Create or restore local Campaign Player Wiki backups.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("committed-activation-inspect", "committed-activation-apply"):
        activation = subparsers.add_parser(command, help="Inspect or apply private committed-source activation.")
        activation.add_argument("--db-path", required=True)
        activation.add_argument("--campaigns-dir", required=True)
        if command.endswith("apply"):
            activation.add_argument("--backup-root", required=True)
            activation.add_argument("--confirm-target", required=True)
            activation.add_argument("--readiness-sha256", required=True)

    for command, help_text in (
        ("artifact-inventory", "Inventory local operational artifacts without writing."),
        ("artifact-retention-assess", "Assess advisory local artifact-retention thresholds."),
    ):
        artifact_parser = subparsers.add_parser(command, help=help_text)
        artifact_parser.add_argument("--data-root", action="append", default=[])
        artifact_parser.add_argument("--archive-root", action="append", default=[])
        artifact_parser.add_argument("--scratch-root", action="append", default=[])
        artifact_parser.add_argument("--as-of-epoch", type=float)

    reconciliation = subparsers.add_parser(
        "player-wiki-reconciliation-dry-run",
        help="Inspect active Player Wiki reconciliation state without writing.",
    )
    reconciliation.add_argument(
        "--kind",
        choices=("all", "publication", "deletion"),
        default="all",
    )
    reconciliation.add_argument("--campaign-slug")
    reconciliation.add_argument("--page-ref")
    reconciliation.add_argument(
        "--state",
        choices=("prepared", "repository_pending", "conflict"),
    )
    reconciliation.add_argument("--operation-id")

    reconciliation_apply = subparsers.add_parser(
        "player-wiki-reconciliation-apply",
        help="Apply one backup-gated deterministic Player Wiki reconciliation action.",
    )
    reconciliation_apply.add_argument(
        "--kind",
        choices=("publication", "deletion"),
        required=True,
    )
    reconciliation_apply.add_argument("--operation-id", required=True)
    reconciliation_apply.add_argument(
        "--action",
        choices=(
            "abandon-precommit",
            "resume-forward",
            "retry-refresh-cleanup",
        ),
        required=True,
    )
    reconciliation_apply.add_argument(
        "--output-dir",
        help="Directory for the mandatory verified safety backup.",
    )
    reconciliation_apply.add_argument(
        "--yes",
        action="store_true",
        help="Confirm execution of the selected deterministic action.",
    )

    backup = subparsers.add_parser("backup", help="Create a timestamped local backup archive.")
    backup.add_argument("--output-dir", help="Directory where the backup archive should be written.")
    backup.add_argument("--label", help="Optional label to include in the archive filename.")

    fly_capture = subparsers.add_parser(
        "fly-sync-capture", help="Capture Fly state under an exclusive request gate."
    )
    fly_capture.add_argument("--db-path", required=True)
    fly_capture.add_argument("--campaigns-dir", required=True)
    fly_capture.add_argument("--output-dir", required=True)

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
        required=True,
        help="Private backup/recovery directory outside the repository.",
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

    if args.command in ("committed-activation-inspect", "committed-activation-apply"):
        try:
            if args.command.endswith("inspect"):
                result = inspect_activation(db_path=Path(args.db_path), campaigns_dir=Path(args.campaigns_dir))
            else:
                result = activate(db_path=Path(args.db_path), campaigns_dir=Path(args.campaigns_dir),
                                  backup_root=Path(args.backup_root), confirmed_target=args.confirm_target,
                                  readiness_sha256=args.readiness_sha256)
        except (ActivationRefused, OSError, ValueError) as exc:
            print(json.dumps({"outcome":"uncertain" if isinstance(exc,ActivationUncertain) else "refused",
                              "reason_code":type(exc).__name__},sort_keys=True))
            raise SystemExit(2) from None
        print(json.dumps(result,sort_keys=True,separators=(",",":")))
        return

    if args.command == "player-wiki-reconciliation-dry-run":
        report, exit_code = inspect_player_wiki_reconciliation(
            database_path=Path(Config.DB_PATH),
            campaigns_dir=Path(Config.CAMPAIGNS_DIR),
            filters=InspectionFilters(
                kind=args.kind,
                campaign_slug=args.campaign_slug,
                page_ref=args.page_ref,
                state=args.state,
                operation_id=args.operation_id,
            ),
        )
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        if exit_code:
            raise SystemExit(exit_code)
        return

    if args.command == "fly-sync-capture":
        if (Path(args.db_path).resolve(strict=False) != Path(Config.DB_PATH).resolve(strict=False)
                or Path(args.campaigns_dir).resolve(strict=False)
                != Path(Config.CAMPAIGNS_DIR).resolve(strict=False)):
            raise SystemExit(
                "Fly capture paths must match the running app database and campaigns paths."
            )
        result = create_fly_sync_capture_archive(
            db_path=Path(args.db_path),
            campaigns_dir=Path(args.campaigns_dir),
            output_dir=Path(args.output_dir),
        )
        with result.archive_path.open("rb") as archive_stream:
            sha256 = hashlib.file_digest(archive_stream, "sha256").hexdigest()
        print(json.dumps({
            "archive_path": str(result.archive_path),
            "byte_count": result.archive_path.stat().st_size,
            "created_at": result.created_at,
            "sha256": sha256,
            "schema_version": 1,
        }, sort_keys=True))
        return

    if args.command == "player-wiki-reconciliation-apply":
        backup_root = (
            Path(args.output_dir).resolve()
            if args.output_dir
            else default_backup_root(project_root)
        )
        try:
            result = apply_player_wiki_reconciliation_operation(
                database_path=Path(Config.DB_PATH),
                campaigns_dir=Path(Config.CAMPAIGNS_DIR),
                backup_root=backup_root,
                kind=args.kind,
                operation_id=args.operation_id,
                action=args.action,
                confirmed=args.yes,
                app_factory=create_app,
            )
        except PlayerWikiReconciliationOperationError as exc:
            print(
                json.dumps(
                    {
                        "error": {"reason_code": exc.reason_code},
                        "outcome": "refused",
                        "schema_version": 1,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            raise SystemExit(exc.exit_code) from None
        print(
            json.dumps(
                {
                    "action": result.action,
                    "backup": {
                        "archive_path": str(result.backup_path),
                        "format_version": result.backup_evidence.format_version,
                        "manifest_hashes_verified": (
                            result.backup_evidence.manifest_hashes_verified
                        ),
                        "verification_level": (
                            result.backup_evidence.verification_level
                        ),
                    },
                    "kind": result.kind,
                    "operation_id": result.operation_id,
                    "outcome": result.outcome,
                    "schema_version": 1,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return

    if args.command in ("artifact-inventory", "artifact-retention-assess"):
        roots = tuple(
            ArtifactRoot(kind, Path(value))
            for kind, values in (
                ("data", args.data_root),
                ("archive", args.archive_root),
                ("scratch", args.scratch_root),
            )
            for value in values
        )
        try:
            report = build_artifact_report(
                roots,
                as_of_seconds=(
                    float(args.as_of_epoch)
                    if args.as_of_epoch is not None
                    else time.time()
                ),
                include_assessment=args.command == "artifact-retention-assess",
            )
        except Exception:
            raise SystemExit(
                "Artifact inventory could not inspect the requested roots safely."
            ) from None
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return

    if args.command == "inspect":
        evidence = inspect_backup_archive(Path(args.archive_path))
        print(f"Inspected backup archive: {evidence.archive_path}")
        print(f"Backup format: v{evidence.format_version} ({evidence.verification_level})")
        print(f"Manifest hashes verified: {str(evidence.manifest_hashes_verified).lower()}")
        print(f"Database integrity: {','.join(evidence.database_integrity_check)}")
        print(f"Campaign files: {evidence.campaign_file_count}")
        if evidence.format_version < 3:
            print("Direct upgraded restore: unavailable; validate in a separate compatible old-app copy and use reviewed import.")
        else:
            print("Direct upgraded restore: eligible for target compatibility and later-edit checks.")
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
            )
            if result.pre_sync_backup_path is not None:
                print(f"Created pre-sync safety backup: {result.pre_sync_backup_path}")
            print(f"Mirrored Fly state from {result.app_name} ({result.machine_id})")
            print(f"Database restored to: {result.database_path}")
            print(f"Campaigns restored to: {result.campaigns_dir}")
            print(f"Verified source archive: {result.source_archive_path}")
            print(f"Source SHA-256: {result.source_archive_sha256}")
            print(f"Capture provenance: {result.provenance_path}")
            print(f"Restore transaction: {result.restore_transaction_id}")
            return

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
