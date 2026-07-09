from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import sqlite3
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from player_wiki.operations import (  # noqa: E402
    default_flyctl_path,
    pull_fly_database,
    resolve_fly_machine_id,
    run_flyctl_command,
)

REMOTE_DB_PATH = "/data/player_wiki.sqlite3"

CORE_TABLES = {
    "users",
    "user_preferences",
    "campaign_memberships",
    "campaign_visibility_settings",
    "character_assignments",
    "invite_tokens",
    "password_reset_tokens",
    "sessions",
    "api_tokens",
    "auth_audit_log",
}
SECRET_EXACT_KEYS = {"password_hash", "token_hash", "ip_address"}
SENSITIVE_KEY_MARKERS = (
    "password",
    "token",
    "secret",
    "credential",
    "hash",
    "session_cookie",
    "set_cookie",
    "invite_link",
    "reset_link",
    "invite_url",
    "reset_url",
    "url",
    "link",
    "ip_address",
)
COMPACT_REFERENCE_COLUMNS = [
    "id",
    "campaign_slug",
    "library_slug",
    "page_ref",
    "route_slug",
    "entry_key",
    "character_slug",
    "slug",
    "session_id",
    "article_id",
    "message_type",
    "recipient_scope",
    "recipient_user_id",
    "author_user_id",
    "author_display_name",
    "created_by_user_id",
    "updated_by_user_id",
    "revealed_by_user_id",
    "proprietary_acknowledged_by_user_id",
    "started_by_user_id",
    "ended_by_user_id",
    "actor_user_id",
    "target_user_id",
    "user_id",
    "title",
    "name",
    "label",
    "status",
    "visibility",
    "scope",
    "role",
    "assignment_type",
    "revision",
    "created_at",
    "updated_at",
    "started_at",
    "ended_at",
    "revealed_at",
    "last_used_at",
    "last_seen_at",
    "expires_at",
    "revoked_at",
    "used_at",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export sanitized Campaign Player Wiki account data.")
    parser.add_argument("--db-path", help="Local SQLite DB path. Ignored when --from-fly is used.")
    parser.add_argument(
        "--output-dir",
        help="Output directory. Defaults to .local/account-exports/account-data-<source>-<timestamp>.",
    )
    parser.add_argument("--from-fly", action="store_true", help="Export from a live Fly app DB snapshot.")
    parser.add_argument(
        "--fly-app",
        default=os.environ.get("PLAYER_WIKI_FLY_APP", "linden-pass-player-wiki"),
        help="Fly app name used with --from-fly.",
    )
    parser.add_argument(
        "--flyctl-path",
        default=os.environ.get("PLAYER_WIKI_FLYCTL_PATH") or default_flyctl_path(),
        help="Path to flyctl.",
    )
    parser.add_argument(
        "--remote-db-path",
        default=os.environ.get("PLAYER_WIKI_FLY_DB_PATH", REMOTE_DB_PATH),
        help="Remote SQLite DB path used with --from-fly.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    exported_at = datetime.now(timezone.utc).replace(microsecond=0)
    timestamp_utc = exported_at.strftime("%Y%m%dT%H%M%SZ")
    timestamp_local = datetime.now().strftime("%Y%m%d-%H%M%S")
    source_label = "live" if args.from_fly else "local"
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else REPO_ROOT / ".local" / "account-exports" / f"account-data-{source_label}-{timestamp_local}"
    )

    if args.from_fly:
        with tempfile.TemporaryDirectory(prefix="campaign-player-wiki-account-export-") as temp_dir_name:
            local_db_path, source = _pull_live_database_snapshot(
                app_name=args.fly_app,
                flyctl_path=args.flyctl_path,
                remote_db_path=args.remote_db_path,
                timestamp_utc=timestamp_utc,
                temp_dir=Path(temp_dir_name),
            )
            result = export_account_data(
                db_path=local_db_path,
                output_dir=output_dir,
                exported_at=exported_at,
                source=source,
            )
    else:
        db_path = Path(args.db_path).resolve() if args.db_path else REPO_ROOT / ".local" / "player_wiki.sqlite3"
        source = {
            "kind": "local",
            "db_path": str(db_path),
        }
        result = export_account_data(
            db_path=db_path,
            output_dir=output_dir,
            exported_at=exported_at,
            source=source,
        )

    print(f"Wrote {result['output_dir']}")
    print(
        "Exported "
        f"{result['counts']['users']} users, "
        f"{result['counts']['campaign_memberships']} memberships, "
        f"{result['counts']['character_assignments']} character assignments, "
        f"{result['counts']['auth_audit_log']} audit events."
    )
    print(f"Validation passed: {str(result['validation_passed']).lower()}")
    return 0 if result["validation_passed"] else 1


def _pull_live_database_snapshot(
    *,
    app_name: str,
    flyctl_path: str,
    remote_db_path: str,
    timestamp_utc: str,
    temp_dir: Path,
) -> tuple[Path, dict[str, Any]]:
    machine_id = resolve_fly_machine_id(flyctl_path=flyctl_path, app_name=app_name)
    remote_snapshot_path = f"/data/player_wiki.account-export-{timestamp_utc}.sqlite3"
    remote_backup_code = (
        "import json, os, sqlite3; "
        f"src_path={remote_db_path!r}; dst_path={remote_snapshot_path!r}; "
        "os.path.exists(dst_path) and os.remove(dst_path); "
        "src=sqlite3.connect(src_path, timeout=30.0); dst=sqlite3.connect(dst_path); "
        "src.backup(dst); dst.commit(); "
        "integrity=dst.execute('PRAGMA integrity_check').fetchone()[0]; "
        "src.close(); dst.close(); "
        "print(json.dumps({'path': dst_path, 'bytes': os.path.getsize(dst_path), 'integrity': integrity}))"
    )
    remote_result = run_flyctl_command(
        flyctl_path,
        [
            "machine",
            "exec",
            "-a",
            app_name,
            "--timeout",
            "120",
            machine_id,
            "--",
            f"python -c {shlex.quote(remote_backup_code)}",
        ],
    )
    snapshot_info = json.loads(remote_result.stdout.strip().splitlines()[-1])
    local_db_path = temp_dir / "player_wiki.live.sqlite3"
    try:
        pull_fly_database(
            flyctl_path=flyctl_path,
            app_name=app_name,
            remote_db_path=remote_snapshot_path,
            output_path=local_db_path,
            machine_id=machine_id,
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
                machine_id,
                "--",
                f"sh -lc {shlex.quote(f'rm -f {remote_snapshot_path}')}",
            ],
        )

    return local_db_path, {
        "kind": "fly",
        "fly_app": app_name,
        "machine_id": machine_id,
        "remote_db_path": remote_db_path,
        "remote_snapshot_path": remote_snapshot_path,
        "remote_snapshot_removed": True,
        "remote_snapshot_bytes": snapshot_info.get("bytes"),
        "remote_snapshot_integrity": snapshot_info.get("integrity"),
    }


def export_account_data(
    *,
    db_path: Path,
    output_dir: Path,
    exported_at: datetime,
    source: dict[str, Any],
) -> dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {db_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        local_integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        users_raw = read_table(conn, "users", "lower(email) ASC, id ASC")
        users = [sanitize_user(row) for row in users_raw]
        users_by_id = {int(user["id"]): user for user in users if user.get("id") is not None}

        preferences = [sanitize_with_user(row, users_by_id) for row in read_table(conn, "user_preferences", "user_id ASC")]
        memberships = [
            sanitize_with_user(row, users_by_id)
            for row in read_table(conn, "campaign_memberships", "campaign_slug ASC, user_id ASC, id ASC")
        ]
        visibility_settings = [
            sanitize_with_user(row, users_by_id, user_key="updated_by_user_id")
            for row in read_table(conn, "campaign_visibility_settings", "campaign_slug ASC, scope ASC")
        ]
        assignments = [
            sanitize_with_user(row, users_by_id)
            for row in read_table(conn, "character_assignments", "campaign_slug ASC, character_slug ASC, id ASC")
        ]
        invite_tokens = [sanitize_token_row(row, users_by_id) for row in read_table(conn, "invite_tokens", "id ASC")]
        password_reset_tokens = [
            sanitize_token_row(row, users_by_id) for row in read_table(conn, "password_reset_tokens", "id ASC")
        ]
        sessions = [sanitize_session(row, users_by_id) for row in read_table(conn, "sessions", "user_id ASC, created_at DESC, id DESC")]
        api_tokens = [
            sanitize_token_row(row, users_by_id, include_label=True)
            for row in read_table(conn, "api_tokens", "user_id ASC, created_at DESC, id DESC")
        ]
        audit_log = [sanitize_audit_log(row, users_by_id) for row in read_table(conn, "auth_audit_log", "id ASC")]

        table_payloads = {
            "users": users,
            "user_preferences": preferences,
            "campaign_memberships": memberships,
            "campaign_visibility_settings": visibility_settings,
            "character_assignments": assignments,
            "invite_tokens": invite_tokens,
            "password_reset_tokens": password_reset_tokens,
            "sessions": sessions,
            "api_tokens": api_tokens,
            "auth_audit_log": audit_log,
        }
        for table, rows in table_payloads.items():
            write_jsonl(output_dir / "tables" / f"{table}.jsonl", rows)

        account_aggregates = build_account_aggregates(
            users=users,
            preferences=preferences,
            memberships=memberships,
            assignments=assignments,
            sessions=sessions,
            api_tokens=api_tokens,
            invite_tokens=invite_tokens,
            password_reset_tokens=password_reset_tokens,
            audit_log=audit_log,
        )
        json_dump(output_dir / "accounts" / "accounts.json", account_aggregates)

        all_tables = table_names(conn)
        table_counts = {table: count_table(conn, table) for table in all_tables}
        json_dump(output_dir / "schema" / "database-table-counts.json", table_counts)
        schema_tables = {
            table: {
                "columns": [col["name"] for col in table_columns(conn, table)],
                "secret_columns_omitted_from_account_payloads": [
                    col["name"] for col in table_columns(conn, table) if col["name"] in SECRET_EXACT_KEYS
                ],
            }
            for table in all_tables
        }
        json_dump(output_dir / "schema" / "tables.json", schema_tables)

        reference_rows, reference_summary = build_account_linked_references(conn, users_by_id, all_tables)
        write_jsonl(output_dir / "references" / "account-linked-records.jsonl", reference_rows)
        json_dump(output_dir / "references" / "user-reference-summary.json", reference_summary)

        summary = build_summary(
            output_dir=output_dir,
            exported_at=exported_at,
            source=source,
            local_integrity=local_integrity,
            users=users,
            preferences=preferences,
            memberships=memberships,
            visibility_settings=visibility_settings,
            assignments=assignments,
            invite_tokens=invite_tokens,
            password_reset_tokens=password_reset_tokens,
            sessions=sessions,
            api_tokens=api_tokens,
            audit_log=audit_log,
            reference_rows=reference_rows,
        )
        json_dump(output_dir / "summary.json", summary)
        write_readme(output_dir, summary)

        validation = validate_export(output_dir, source, local_integrity)
        json_dump(output_dir / "validation.json", validation)
        write_manifest(output_dir, exported_at, summary["source"], summary["sanitization"])

        return {
            "output_dir": str(output_dir),
            "counts": summary["counts"],
            "validation_passed": validation["passed"],
        }
    finally:
        conn.close()


def build_account_aggregates(
    *,
    users: list[dict[str, Any]],
    preferences: list[dict[str, Any]],
    memberships: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    api_tokens: list[dict[str, Any]],
    invite_tokens: list[dict[str, Any]],
    password_reset_tokens: list[dict[str, Any]],
    audit_log: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    preferences_by_user = {row["user_id"]: strip_user_fields(row) for row in preferences}
    memberships_by_user: dict[int, list[dict[str, Any]]] = defaultdict(list)
    assignments_by_user: dict[int, list[dict[str, Any]]] = defaultdict(list)
    sessions_by_user: dict[int, list[dict[str, Any]]] = defaultdict(list)
    api_tokens_by_user: dict[int, list[dict[str, Any]]] = defaultdict(list)
    invite_tokens_by_user: dict[int, list[dict[str, Any]]] = defaultdict(list)
    reset_tokens_by_user: dict[int, list[dict[str, Any]]] = defaultdict(list)
    audit_counts_by_user: dict[int, Counter[str]] = defaultdict(Counter)

    for row in memberships:
        memberships_by_user[int(row["user_id"])].append(strip_user_fields(row))
    for row in assignments:
        assignments_by_user[int(row["user_id"])].append(strip_user_fields(row))
    for row in sessions:
        sessions_by_user[int(row["user_id"])].append(strip_user_fields(row))
    for row in api_tokens:
        api_tokens_by_user[int(row["user_id"])].append(strip_user_fields(row))
    for row in invite_tokens:
        invite_tokens_by_user[int(row["user_id"])].append(strip_user_fields(row))
    for row in password_reset_tokens:
        reset_tokens_by_user[int(row["user_id"])].append(strip_user_fields(row))
    for row in audit_log:
        for key in ("actor_user_id", "target_user_id"):
            user_id = row.get(key)
            if user_id is not None:
                audit_counts_by_user[int(user_id)][str(row.get("event_type") or "unknown")] += 1

    account_aggregates = []
    for user in users:
        user_id = int(user["id"])
        user_sessions = sessions_by_user.get(user_id, [])
        user_api_tokens = api_tokens_by_user.get(user_id, [])
        account_aggregates.append(
            {
                **user,
                "preferences": preferences_by_user.get(user_id),
                "memberships": memberships_by_user.get(user_id, []),
                "character_assignments": assignments_by_user.get(user_id, []),
                "session_summary": {
                    "total": len(user_sessions),
                    "not_revoked": sum(1 for row in user_sessions if not row.get("revoked_at")),
                    "with_ip_address_recorded": sum(1 for row in user_sessions if row.get("ip_address_recorded")),
                },
                "api_token_summary": {
                    "total": len(user_api_tokens),
                    "not_revoked": sum(1 for row in user_api_tokens if not row.get("revoked_at")),
                },
                "api_tokens": user_api_tokens,
                "invite_tokens": invite_tokens_by_user.get(user_id, []),
                "password_reset_tokens": reset_tokens_by_user.get(user_id, []),
                "auth_audit_event_counts": dict(sorted(audit_counts_by_user.get(user_id, Counter()).items())),
            }
        )
    return account_aggregates


def build_account_linked_references(
    conn: sqlite3.Connection,
    users_by_id: dict[int, dict[str, Any]],
    all_tables: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    reference_summary: dict[str, Any] = {}
    reference_rows: list[dict[str, Any]] = []
    for table in all_tables:
        columns = [col["name"] for col in table_columns(conn, table)]
        user_columns = [col for col in columns if col == "user_id" or col.endswith("_user_id")]
        if not user_columns or table in CORE_TABLES:
            continue
        where_clause = " OR ".join(f"{qid(col)} IS NOT NULL" for col in user_columns)
        matching_count = int(conn.execute(f"SELECT COUNT(*) FROM {qid(table)} WHERE {where_clause}").fetchone()[0])
        selected_columns = [col for col in COMPACT_REFERENCE_COLUMNS if col in columns and col not in SECRET_EXACT_KEYS]
        for col in user_columns:
            if col not in selected_columns:
                selected_columns.append(col)
        if not selected_columns:
            selected_columns = list(user_columns)
        query = f"SELECT {', '.join(qid(col) for col in selected_columns)} FROM {qid(table)} WHERE {where_clause}"
        if "updated_at" in columns:
            query += " ORDER BY updated_at ASC"
        elif "created_at" in columns:
            query += " ORDER BY created_at ASC"
        elif "id" in columns:
            query += " ORDER BY id ASC"
        rows = [row_to_dict(row) for row in conn.execute(query).fetchall()]
        reference_summary[table] = {
            "user_id_columns": user_columns,
            "matching_row_count": matching_count,
            "exported_compact_columns": selected_columns,
        }
        for row in rows:
            user_refs = {col: user_ref(users_by_id, row.get(col)) for col in user_columns if row.get(col) is not None}
            reference_rows.append(
                {
                    "table": table,
                    "user_id_columns": user_columns,
                    "user_refs": user_refs,
                    "row": row,
                }
            )
    return reference_rows, reference_summary


def build_summary(
    *,
    output_dir: Path,
    exported_at: datetime,
    source: dict[str, Any],
    local_integrity: str,
    users: list[dict[str, Any]],
    preferences: list[dict[str, Any]],
    memberships: list[dict[str, Any]],
    visibility_settings: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    invite_tokens: list[dict[str, Any]],
    password_reset_tokens: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    api_tokens: list[dict[str, Any]],
    audit_log: list[dict[str, Any]],
    reference_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    campaign_slugs = sorted(
        {
            row.get("campaign_slug")
            for row in memberships + assignments + visibility_settings + audit_log
            if row.get("campaign_slug")
        }
    )
    return {
        "export_type": "campaign_player_wiki_account_data",
        "exported_at": exported_at.isoformat(),
        "output_dir": str(output_dir),
        "source": {
            **source,
            "local_integrity": local_integrity,
        },
        "sanitization": {
            "raw_sqlite_database_included": False,
            "password_hashes_included": False,
            "token_hashes_included": False,
            "raw_session_tokens_included": False,
            "raw_api_tokens_included": False,
            "raw_invite_or_reset_tokens_included": False,
            "raw_ip_addresses_included": False,
            "emails_included": True,
            "user_agents_included": True,
        },
        "counts": {
            "users": len(users),
            "user_preferences": len(preferences),
            "campaign_memberships": len(memberships),
            "campaign_visibility_settings": len(visibility_settings),
            "character_assignments": len(assignments),
            "invite_tokens": len(invite_tokens),
            "password_reset_tokens": len(password_reset_tokens),
            "sessions": len(sessions),
            "api_tokens": len(api_tokens),
            "auth_audit_log": len(audit_log),
            "account_linked_reference_rows": len(reference_rows),
        },
        "campaign_slugs_seen": campaign_slugs,
        "user_status_counts": dict(sorted(Counter(str(user.get("status") or "unknown") for user in users).items())),
        "membership_role_counts": dict(sorted(Counter(str(row.get("role") or "unknown") for row in memberships).items())),
        "campaign_membership_counts": dict(
            sorted(Counter(str(row.get("campaign_slug") or "unknown") for row in memberships).items())
        ),
        "audit_event_counts": dict(sorted(Counter(str(row.get("event_type") or "unknown") for row in audit_log).items())),
    }


def validate_export(output_dir: Path, source: dict[str, Any], local_integrity: str) -> dict[str, Any]:
    payload_paths = list((output_dir / "tables").glob("*.jsonl")) + [
        output_dir / "accounts" / "accounts.json",
        output_dir / "references" / "account-linked-records.jsonl",
        output_dir / "references" / "user-reference-summary.json",
    ]
    forbidden_payload_keys: list[dict[str, str]] = []
    for path in payload_paths:
        for finding in find_forbidden_payload_keys(path):
            forbidden_payload_keys.append({"file": str(path.relative_to(output_dir)), "path": finding})
    sqlite_files = [
        str(path.relative_to(output_dir))
        for path in output_dir.rglob("*")
        if path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}
    ]
    remote_integrity = source.get("remote_snapshot_integrity", "ok")
    return {
        "remote_snapshot_integrity": remote_integrity,
        "local_integrity": local_integrity,
        "forbidden_raw_secret_keys_in_payloads": forbidden_payload_keys,
        "sqlite_or_db_files_in_export": sqlite_files,
        "payload_files_scanned": [str(path.relative_to(output_dir)) for path in payload_paths],
        "passed": local_integrity == "ok" and remote_integrity == "ok" and not forbidden_payload_keys and not sqlite_files,
    }


def write_manifest(output_dir: Path, exported_at: datetime, source: dict[str, Any], sanitization: dict[str, Any]) -> None:
    files = []
    for path in sorted(file_path for file_path in output_dir.rglob("*") if file_path.is_file() and file_path.name != "manifest.json"):
        files.append(
            {
                "path": path.relative_to(output_dir).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_path(path),
            }
        )
    json_dump(
        output_dir / "manifest.json",
        {
            "format_version": 1,
            "export_type": "campaign_player_wiki_account_data",
            "exported_at": exported_at.isoformat(),
            "source": source,
            "sanitization": sanitization,
            "files": files,
        },
    )


def write_readme(output_dir: Path, summary: dict[str, Any]) -> None:
    source = summary["source"]
    lines = [
        "# Campaign Player Wiki Account Export",
        "",
        f"- Exported at: {summary['exported_at']}",
        f"- Source: `{source.get('kind')}`",
        f"- Source Fly app: `{source.get('fly_app', '')}`",
        f"- Source machine: `{source.get('machine_id', '')}`",
        f"- Source DB: `{source.get('remote_db_path') or source.get('db_path')}`",
        "- Secret material omitted: password hashes, token hashes, raw session tokens, raw API/invite/reset tokens, raw IP addresses, and the raw SQLite database.",
        "- Account scope: all live Campaign Player Wiki accounts and all campaign memberships/assignments found in the database.",
        "",
        "## Files",
        "",
        "- `accounts/accounts.json`: per-account aggregate with preferences, memberships, assignments, token summaries, and audit counts.",
        "- `tables/*.jsonl`: sanitized core account/auth tables.",
        "- `references/account-linked-records.jsonl`: compact references from other app tables that point at user IDs.",
        "- `references/user-reference-summary.json`: counts of non-core app records that refer to users.",
        "- `schema/database-table-counts.json`: full database table counts for orientation.",
        "- `validation.json`: integrity and sanitization checks.",
        "",
    ]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def qid(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_table(conn: sqlite3.Connection, table: str, order_by: str = "id ASC") -> list[dict[str, Any]]:
    if not table_exists(conn, table):
        return []
    query = f"SELECT * FROM {qid(table)}"
    if order_by:
        query += f" ORDER BY {order_by}"
    return [row_to_dict(row) for row in conn.execute(query).fetchall()]


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone() is not None


def table_columns(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    if not table_exists(conn, table):
        return []
    return [row_to_dict(row) for row in conn.execute(f"PRAGMA table_info({qid(table)})").fetchall()]


def table_names(conn: sqlite3.Connection) -> list[str]:
    return [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name ASC"
        ).fetchall()
    ]


def count_table(conn: sqlite3.Connection, table: str) -> int:
    if not table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) FROM {qid(table)}").fetchone()[0])


def user_ref(users_by_id: dict[int, dict[str, Any]], user_id: Any) -> dict[str, Any] | None:
    if user_id is None:
        return None
    try:
        normalized = int(user_id)
    except (TypeError, ValueError):
        return {"id": user_id, "email": None, "display_name": None, "status": None}
    user = users_by_id.get(normalized)
    if not user:
        return {"id": normalized, "email": None, "display_name": None, "status": None}
    return {
        "id": normalized,
        "email": user.get("email"),
        "display_name": user.get("display_name"),
        "status": user.get("status"),
    }


def should_redact_key(key: str) -> bool:
    lower_key = key.lower()
    return lower_key in SECRET_EXACT_KEYS or any(marker in lower_key for marker in SENSITIVE_KEY_MARKERS)


def redact_metadata(value: Any, key_hint: str = "") -> Any:
    if should_redact_key(key_hint):
        return {"redacted": True, "present": value not in (None, "", [], {})}
    if isinstance(value, dict):
        return {str(key): redact_metadata(item, str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_metadata(item, key_hint) for item in value]
    return value


def parse_metadata(raw: str) -> tuple[Any, str | None]:
    try:
        return redact_metadata(json.loads(raw or "{}")), None
    except json.JSONDecodeError as exc:
        return {}, str(exc)


def bool_int(value: Any) -> bool:
    return bool(int(value or 0))


def sanitize_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "email": row.get("email"),
        "display_name": row.get("display_name"),
        "is_admin": bool_int(row.get("is_admin")),
        "status": row.get("status"),
        "password_configured": bool(row.get("password_hash")),
        "auth_version": row.get("auth_version"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def sanitize_with_user(
    row: dict[str, Any],
    users_by_id: dict[int, dict[str, Any]],
    *,
    user_key: str = "user_id",
) -> dict[str, Any]:
    sanitized = {key: value for key, value in row.items() if key not in SECRET_EXACT_KEYS}
    ref = user_ref(users_by_id, row.get(user_key))
    if ref:
        sanitized["user"] = ref
    for key in (
        "created_by_user_id",
        "updated_by_user_id",
        "actor_user_id",
        "target_user_id",
        "started_by_user_id",
        "ended_by_user_id",
        "revealed_by_user_id",
        "recipient_user_id",
        "author_user_id",
    ):
        if key in row:
            sanitized[key.replace("_user_id", "_user")] = user_ref(users_by_id, row.get(key))
    return sanitized


def sanitize_token_row(
    row: dict[str, Any],
    users_by_id: dict[int, dict[str, Any]],
    *,
    include_label: bool = False,
) -> dict[str, Any]:
    keys = ["id", "user_id", "created_at", "expires_at", "used_at", "last_used_at", "revoked_at", "created_by_user_id"]
    if include_label:
        keys.insert(2, "label")
    sanitized = {key: row.get(key) for key in keys if key in row}
    sanitized["token_configured"] = bool(row.get("token_hash"))
    sanitized["user"] = user_ref(users_by_id, row.get("user_id"))
    if "created_by_user_id" in row:
        sanitized["created_by_user"] = user_ref(users_by_id, row.get("created_by_user_id"))
    return sanitized


def sanitize_session(row: dict[str, Any], users_by_id: dict[int, dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "user_id": row.get("user_id"),
        "user": user_ref(users_by_id, row.get("user_id")),
        "created_at": row.get("created_at"),
        "last_seen_at": row.get("last_seen_at"),
        "expires_at": row.get("expires_at"),
        "revoked_at": row.get("revoked_at"),
        "user_agent": row.get("user_agent"),
        "session_token_configured": bool(row.get("token_hash")),
        "ip_address_recorded": bool(row.get("ip_address")),
    }


def sanitize_audit_log(row: dict[str, Any], users_by_id: dict[int, dict[str, Any]]) -> dict[str, Any]:
    metadata, metadata_error = parse_metadata(str(row.get("metadata_json") or "{}"))
    sanitized = {
        "id": row.get("id"),
        "actor_user_id": row.get("actor_user_id"),
        "actor_user": user_ref(users_by_id, row.get("actor_user_id")),
        "target_user_id": row.get("target_user_id"),
        "target_user": user_ref(users_by_id, row.get("target_user_id")),
        "campaign_slug": row.get("campaign_slug"),
        "character_slug": row.get("character_slug"),
        "event_type": row.get("event_type"),
        "metadata": metadata,
        "created_at": row.get("created_at"),
    }
    if metadata_error:
        sanitized["metadata_parse_error"] = metadata_error
    return sanitized


def strip_user_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if key not in {"user", "created_by_user", "updated_by_user", "actor_user", "target_user"}
    }


def find_forbidden_payload_keys(path: Path) -> list[str]:
    findings: list[str] = []

    def walk(obj: Any, key_path: str) -> None:
        if isinstance(obj, dict):
            for key, item in obj.items():
                child_path = f"{key_path}.{key}" if key_path else key
                if key in SECRET_EXACT_KEYS:
                    findings.append(child_path)
                walk(item, child_path)
        elif isinstance(obj, list):
            for index, item in enumerate(obj):
                walk(item, f"{key_path}[{index}]")

    if path.suffix == ".jsonl":
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if line.strip():
                    walk(json.loads(line), f"{path.name}:{line_number}")
    elif path.suffix == ".json":
        walk(json.loads(path.read_text(encoding="utf-8")), path.name)
    return findings


if __name__ == "__main__":
    raise SystemExit(main())
