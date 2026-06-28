"""Guarded scaffolding for TypeScript staging rehearsal evidence.

The helper creates disposable transcript folders and captures deterministic
file/SQLite snapshots for copied-data rehearsal targets. It intentionally does
not mutate, restore, deploy, or sync data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


FAMILY_TABLES: dict[str, tuple[str, ...]] = {
    "content-character": (
        "character_state",
        "character_assignments",
        "audit_events",
    ),
    "combat": (
        "campaign_combat_trackers",
        "campaign_combatants",
        "campaign_combat_conditions",
        "campaign_combatant_resource_counters",
        "campaign_combatant_resource_notes",
        "character_state",
    ),
    "session": (
        "campaign_sessions",
        "campaign_session_states",
        "campaign_session_messages",
        "campaign_session_articles",
        "campaign_session_article_images",
    ),
    "systems": (
        "systems_libraries",
        "systems_sources",
        "systems_entries",
        "systems_import_runs",
        "systems_shared_entry_edit_events",
        "systems_entry_links",
        "campaign_system_policies",
        "campaign_enabled_sources",
        "campaign_entry_overrides",
    ),
    "dm-content": (
        "campaign_dm_statblocks",
        "campaign_dm_condition_definitions",
    ),
    "publishing": (
        "campaign_pages",
        "campaign_page_sync_state",
    ),
}


REHEARSAL_DIRS = ("input", "backup", "pre", "mutation", "post", "restore", "logs")


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def assert_disposable_root(root: Path) -> Path:
    resolved = resolve_path(root)
    if ".task-temp" not in resolved.parts:
        raise ValueError(
            f"Rehearsal root must be inside a .task-temp directory: {resolved}"
        )
    return resolved


@dataclass(frozen=True)
class RehearsalPaths:
    root: str
    db_path: str | None = None
    campaigns_dir: str | None = None
    backup_archive: str | None = None


def validate_rehearsal_paths(
    *,
    root: Path,
    db_path: Path | None = None,
    campaigns_dir: Path | None = None,
    backup_archive: Path | None = None,
) -> RehearsalPaths:
    resolved_root = assert_disposable_root(root)
    resolved_db = resolve_path(db_path) if db_path else None
    resolved_campaigns = resolve_path(campaigns_dir) if campaigns_dir else None
    resolved_backup = resolve_path(backup_archive) if backup_archive else None

    for label, candidate in (
        ("database path", resolved_db),
        ("campaigns dir", resolved_campaigns),
        ("backup archive", resolved_backup),
    ):
        if candidate is not None and not is_relative_to(candidate, resolved_root):
            raise ValueError(
                f"{label} must resolve inside the rehearsal root {resolved_root}: {candidate}"
            )

    return RehearsalPaths(
        root=str(resolved_root),
        db_path=str(resolved_db) if resolved_db else None,
        campaigns_dir=str(resolved_campaigns) if resolved_campaigns else None,
        backup_archive=str(resolved_backup) if resolved_backup else None,
    )


def transcript_template(
    *,
    rehearsal_id: str,
    family: str,
    source_description: str,
    source_approval: str,
    root: Path,
) -> str:
    tables = "\n".join(f"- `{table}`" for table in FAMILY_TABLES[family])
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"""# Rehearsal Transcript: {rehearsal_id}

Generated: {created}

## Scope
- Write family: {family}
- Routes/actions:
- Readiness target:
- Source snapshot description: {source_description}
- Source snapshot approval: {source_approval}

## Safety Confirmation
- Rehearsal root: `{root}`
- Copied SQLite:
- Copied campaigns dir:
- Refused live paths:
- `.local` visibility:

## Baseline Evidence
- Flask authority commit:
- TypeScript commit:
- Route snapshot/check status:
- Pre-mutation file manifest: `pre/manifest.json`
- Pre-mutation SQL tables:
{tables}
- Baseline API samples:

## Backup
- Command:
- Archive path:
- Archive contents summary:
- Result:

## Mutation
- TypeScript runtime command:
- Environment:
- Request payloads:
- Response payloads:
- Expected changed files/tables:
- Observed changed files/tables:

## Restore
- Command:
- Target:
- Result:

## Equivalence
- File hash comparison:
- SQL row-count comparison:
- API response comparison:
- Known acceptable differences:
- Unexpected differences:

## Decision
- Result: pass | fail | blocked
- Label before:
- Label after:
- Follow-up required:
"""


def init_rehearsal(
    *,
    rehearsal_id: str,
    family: str,
    root: Path | None = None,
    source_description: str = "",
    source_approval: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    if family not in FAMILY_TABLES:
        raise ValueError(f"Unsupported write family: {family}")
    rehearsal_root = assert_disposable_root(root or repo_root() / ".task-temp" / rehearsal_id)
    paths = [rehearsal_root / name for name in REHEARSAL_DIRS]
    transcript_path = rehearsal_root / "transcript.md"

    if dry_run:
        return {
            "created": False,
            "root": str(rehearsal_root),
            "directories": [str(path) for path in paths],
            "transcript": str(transcript_path),
        }

    if rehearsal_root.exists() and any(rehearsal_root.iterdir()):
        raise ValueError(f"Rehearsal root already exists and is not empty: {rehearsal_root}")
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(
        transcript_template(
            rehearsal_id=rehearsal_id,
            family=family,
            source_description=source_description,
            source_approval=source_approval,
            root=rehearsal_root,
        ),
        encoding="utf-8",
    )
    return {
        "created": True,
        "root": str(rehearsal_root),
        "directories": [str(path) for path in paths],
        "transcript": str(transcript_path),
    }


def iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_manifest(campaigns_dir: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in iter_files(campaigns_dir):
        entries.append(
            {
                "path": path.relative_to(campaigns_dir).as_posix(),
                "size": path.stat().st_size,
                "sha256": hash_file(path),
            }
        )
    return entries


def sqlite_table_counts(db_path: Path, tables: Sequence[str]) -> dict[str, Any]:
    if not db_path.exists():
        return {"missing_database": True, "tables": {}, "missing_tables": list(tables)}
    counts: dict[str, int] = {}
    missing: list[str] = []
    with sqlite3.connect(db_path) as connection:
        existing = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        for table in tables:
            if table not in existing:
                missing.append(table)
                continue
            row = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
            counts[table] = int(row[0]) if row else 0
    return {"missing_database": False, "tables": counts, "missing_tables": missing}


def capture_snapshot(
    *,
    root: Path,
    label: str,
    family: str,
    db_path: Path,
    campaigns_dir: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    if family not in FAMILY_TABLES:
        raise ValueError(f"Unsupported write family: {family}")
    if label not in {"pre", "post", "restore"}:
        raise ValueError("Snapshot label must be one of: pre, post, restore")

    paths = validate_rehearsal_paths(
        root=root,
        db_path=db_path,
        campaigns_dir=campaigns_dir,
    )
    output_path = Path(paths.root) / label / "manifest.json"
    manifest = {
        "label": label,
        "family": family,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "paths": asdict(paths),
        "files": file_manifest(Path(paths.campaigns_dir)) if paths.campaigns_dir else [],
        "sqlite": sqlite_table_counts(Path(paths.db_path), FAMILY_TABLES[family])
        if paths.db_path
        else {},
    }
    if dry_run:
        return {"would_write": str(output_path), "manifest": manifest}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"wrote": str(output_path), "manifest": manifest}


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compare_manifests(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_files = {entry["path"]: entry for entry in before.get("files", [])}
    after_files = {entry["path"]: entry for entry in after.get("files", [])}
    all_files = sorted(set(before_files) | set(after_files))
    changed_files = [
        path for path in all_files if before_files.get(path) != after_files.get(path)
    ]

    before_sqlite = before.get("sqlite", {})
    after_sqlite = after.get("sqlite", {})
    sqlite_equal = before_sqlite == after_sqlite
    return {
        "equal": not changed_files and sqlite_equal,
        "changed_files": changed_files,
        "sqlite_equal": sqlite_equal,
        "before_sqlite": before_sqlite,
        "after_sqlite": after_sqlite,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scaffold and verify disposable TypeScript write-family rehearsals."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create rehearsal folders and transcript.")
    init_parser.add_argument("--rehearsal-id", required=True)
    init_parser.add_argument("--family", required=True, choices=sorted(FAMILY_TABLES))
    init_parser.add_argument("--root", type=Path)
    init_parser.add_argument("--source-description", default="")
    init_parser.add_argument("--source-approval", default="")
    init_parser.add_argument("--dry-run", action="store_true")

    check_parser = subparsers.add_parser("check-paths", help="Validate copied-data paths.")
    check_parser.add_argument("--root", required=True, type=Path)
    check_parser.add_argument("--db", type=Path)
    check_parser.add_argument("--campaigns-dir", type=Path)
    check_parser.add_argument("--backup-archive", type=Path)

    snapshot_parser = subparsers.add_parser("snapshot", help="Capture file and SQLite evidence.")
    snapshot_parser.add_argument("--root", required=True, type=Path)
    snapshot_parser.add_argument("--label", required=True, choices=["pre", "post", "restore"])
    snapshot_parser.add_argument("--family", required=True, choices=sorted(FAMILY_TABLES))
    snapshot_parser.add_argument("--db", required=True, type=Path)
    snapshot_parser.add_argument("--campaigns-dir", required=True, type=Path)
    snapshot_parser.add_argument("--dry-run", action="store_true")

    compare_parser = subparsers.add_parser("compare", help="Compare two captured manifests.")
    compare_parser.add_argument("--before", required=True, type=Path)
    compare_parser.add_argument("--after", required=True, type=Path)

    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "init":
            result = init_rehearsal(
                rehearsal_id=args.rehearsal_id,
                family=args.family,
                root=args.root,
                source_description=args.source_description,
                source_approval=args.source_approval,
                dry_run=args.dry_run,
            )
        elif args.command == "check-paths":
            result = asdict(
                validate_rehearsal_paths(
                    root=args.root,
                    db_path=args.db,
                    campaigns_dir=args.campaigns_dir,
                    backup_archive=args.backup_archive,
                )
            )
        elif args.command == "snapshot":
            result = capture_snapshot(
                root=args.root,
                label=args.label,
                family=args.family,
                db_path=args.db,
                campaigns_dir=args.campaigns_dir,
                dry_run=args.dry_run,
            )
        elif args.command == "compare":
            result = compare_manifests(load_manifest(args.before), load_manifest(args.after))
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result["equal"] else 1
        else:
            raise ValueError(f"Unsupported command: {args.command}")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except ValueError as exc:
        print(f"staging rehearsal harness refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
