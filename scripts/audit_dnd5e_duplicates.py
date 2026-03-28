from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from player_wiki.systems_importer import CLASS_DATASET_KEYS, DATASETS, Dnd5eSystemsImporter

DEFAULT_DND5E_EXPORT_ROOT = Path.home() / "Documents" / "dnd5e-source-export"
DEFAULT_LOCAL_DB_PATH = REPO_ROOT / ".local" / "player_wiki.sqlite3"


@dataclass(slots=True)
class AuditRow:
    source_id: str
    entry_type: str
    title: str
    source_path: str
    page: str
    class_name: str
    class_source: str
    subclass_name: str
    subclass_source: str
    level: str
    payload_hash: str
    identity_seed: str
    has_content: bool

    @property
    def is_stub(self) -> bool:
        return not self.page and not self.has_content

    @property
    def context_key(self) -> tuple[str, str, str, str, str]:
        return (
            self.class_name,
            self.class_source,
            self.subclass_name,
            self.subclass_source,
            self.level,
        )

    def describe(self) -> str:
        parts = [
            f"path={self.source_path}",
            f"page={self.page or '-'}",
        ]
        if self.class_name or self.class_source:
            parts.append(f"class={self.class_name or '-'}[{self.class_source or '-'}]")
        if self.subclass_name or self.subclass_source:
            parts.append(f"subclass={self.subclass_name or '-'}[{self.subclass_source or '-'}]")
        if self.level:
            parts.append(f"level={self.level}")
        parts.append(f"content={'yes' if self.has_content else 'no'}")
        return " | ".join(parts)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit DND 5E source materials and the local Systems DB for duplicate-looking entries."
    )
    parser.add_argument("source_ids", nargs="+", help="One or more source IDs, such as TCE or XGE.")
    parser.add_argument(
        "--data-root",
        default=str(DEFAULT_DND5E_EXPORT_ROOT),
        help="Path to the local DND 5E source export root.",
    )
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_LOCAL_DB_PATH),
        help="Path to the local Campaign Player Wiki SQLite database.",
    )
    parser.add_argument("--output", help="Optional path to write the markdown report.")
    return parser


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def value_has_content(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(value_has_content(item) for item in value)
    if isinstance(value, dict):
        return any(value_has_content(item) for item in value.values())
    return True


def raw_row_has_content(raw_entry: dict[str, Any]) -> bool:
    content_fields = (
        raw_entry.get("entries"),
        raw_entry.get("entriesHigherLevel"),
        raw_entry.get("classFeatures"),
        raw_entry.get("subclassFeatures"),
        raw_entry.get("optionalfeatureProgression"),
    )
    return any(value_has_content(value) for value in content_fields)


def db_row_has_content(body: dict[str, Any]) -> bool:
    return value_has_content(body)


def build_raw_row(
    importer: Dnd5eSystemsImporter,
    source_id: str,
    entry_type: str,
    raw_entry: dict[str, Any],
    source_path: str,
) -> AuditRow:
    return AuditRow(
        source_id=source_id,
        entry_type=entry_type,
        title=normalize_text(raw_entry.get("name")),
        source_path=source_path,
        page=normalize_text(raw_entry.get("page")),
        class_name=normalize_text(raw_entry.get("className")),
        class_source=normalize_text(raw_entry.get("classSource")).upper(),
        subclass_name=normalize_text(raw_entry.get("subclassShortName")),
        subclass_source=normalize_text(raw_entry.get("subclassSource")).upper(),
        level=normalize_text(raw_entry.get("level")),
        payload_hash=stable_hash(raw_entry),
        identity_seed=importer._build_entry_identity_seed(entry_type, raw_entry),
        has_content=raw_row_has_content(raw_entry),
    )


def load_raw_rows(importer: Dnd5eSystemsImporter, source_id: str) -> list[AuditRow]:
    rows: list[AuditRow] = []
    normalized_source_id = source_id.upper()

    for dataset in DATASETS:
        path = dataset.resolve_path(importer.data_root, normalized_source_id)
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        raw_entries = importer._load_dataset_raw_entries(payload, dataset=dataset, source_id=normalized_source_id)
        if not isinstance(raw_entries, list):
            continue
        relative_path = str(path.relative_to(importer.data_root)).replace("\\", "/")
        for raw_entry in raw_entries:
            if not isinstance(raw_entry, dict):
                continue
            if normalize_text(raw_entry.get("source")).upper() != normalized_source_id:
                continue
            rows.append(build_raw_row(importer, normalized_source_id, dataset.entry_type, raw_entry, relative_path))

    class_dir = importer.data_root / "data/class"
    index_path = class_dir / "index.json"
    if index_path.exists():
        with index_path.open(encoding="utf-8") as handle:
            index_payload = json.load(handle)
        if isinstance(index_payload, dict):
            for relative_name in sorted(index_payload.values()):
                path = class_dir / str(relative_name)
                if not path.exists():
                    continue
                with path.open(encoding="utf-8") as handle:
                    payload = json.load(handle)
                if not isinstance(payload, dict):
                    continue
                relative_path = str(path.relative_to(importer.data_root)).replace("\\", "/")
                for entry_type, json_key in CLASS_DATASET_KEYS.items():
                    raw_entries = payload.get(json_key, [])
                    if not isinstance(raw_entries, list):
                        continue
                    for raw_entry in raw_entries:
                        if not isinstance(raw_entry, dict):
                            continue
                        if normalize_text(raw_entry.get("source")).upper() != normalized_source_id:
                            continue
                        rows.append(build_raw_row(importer, normalized_source_id, entry_type, raw_entry, relative_path))

    return rows


def load_db_rows(db_path: Path, source_id: str) -> list[AuditRow]:
    if not db_path.exists():
        return []

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        fetched_rows = connection.execute(
            """
            SELECT entry_type, title, source_path, source_page, metadata_json, body_json
            FROM systems_entries
            WHERE library_slug = 'DND-5E' AND source_id = ?
            ORDER BY entry_type, title, id
            """,
            (source_id.upper(),),
        ).fetchall()
    finally:
        connection.close()

    rows: list[AuditRow] = []
    for fetched in fetched_rows:
        metadata = json.loads(fetched["metadata_json"] or "{}")
        body = json.loads(fetched["body_json"] or "{}")
        rows.append(
            AuditRow(
                source_id=source_id.upper(),
                entry_type=normalize_text(fetched["entry_type"]),
                title=normalize_text(fetched["title"]),
                source_path=normalize_text(fetched["source_path"]),
                page=normalize_text(fetched["source_page"]),
                class_name=normalize_text(metadata.get("class_name")),
                class_source=normalize_text(metadata.get("class_source")).upper(),
                subclass_name=normalize_text(metadata.get("subclass_name")),
                subclass_source=normalize_text(metadata.get("subclass_source")).upper(),
                level=normalize_text(metadata.get("level")),
                payload_hash=stable_hash({"metadata": metadata, "body": body}),
                identity_seed="",
                has_content=db_row_has_content(body),
            )
        )
    return rows


def group_rows(rows: list[AuditRow], key_fn) -> list[tuple[Any, list[AuditRow]]]:
    grouped: dict[Any, list[AuditRow]] = defaultdict(list)
    for row in rows:
        grouped[key_fn(row)].append(row)
    return [(key, group) for key, group in grouped.items() if len(group) > 1]


def find_stub_mixed_groups(rows: list[AuditRow]) -> list[tuple[tuple[str, str], list[AuditRow]]]:
    suspicious_groups: list[tuple[tuple[str, str], list[AuditRow]]] = []
    for key, group in group_rows(rows, lambda row: (row.entry_type, row.title)):
        has_stub = any(row.is_stub for row in group)
        has_non_stub = any(not row.is_stub for row in group)
        has_context_variance = len({row.context_key for row in group}) > 1
        if has_stub and has_non_stub and has_context_variance:
            suspicious_groups.append((key, sorted(group, key=lambda row: (row.is_stub, row.page, row.source_path), reverse=True)))
    return sorted(suspicious_groups, key=lambda item: (item[0][0], item[0][1]))


def summarize_rows(rows: list[AuditRow]) -> dict[str, Any]:
    exact_groups = group_rows(rows, lambda row: (row.entry_type, row.payload_hash))
    identity_groups = [group for group in group_rows(rows, lambda row: (row.entry_type, row.identity_seed)) if group[0][1]]
    same_title_groups = group_rows(rows, lambda row: (row.entry_type, row.title))
    stub_mixed_groups = find_stub_mixed_groups(rows)
    return {
        "row_count": len(rows),
        "exact_groups": exact_groups,
        "identity_groups": identity_groups,
        "same_title_groups": same_title_groups,
        "stub_mixed_groups": stub_mixed_groups,
    }


def render_group_block(groups: list[tuple[tuple[str, str], list[AuditRow]]]) -> list[str]:
    if not groups:
        return ["None."]
    lines: list[str] = []
    for (entry_type, title), rows in groups:
        lines.append(f"- `{entry_type}` / `{title}` ({len(rows)} rows)")
        for row in rows:
            lines.append(f"  - {row.describe()}")
    return lines


def render_exact_group_block(groups: list[tuple[Any, list[AuditRow]]], *, limit: int = 10) -> list[str]:
    if not groups:
        return ["None."]
    sorted_groups = sorted(
        groups,
        key=lambda item: (-len(item[1]), item[1][0].entry_type, item[1][0].title),
    )
    lines: list[str] = []
    for index, (_, rows) in enumerate(sorted_groups):
        if index >= limit:
            remaining = len(sorted_groups) - limit
            if remaining > 0:
                lines.append(f"- `{remaining}` additional exact-content groups omitted for brevity.")
            break
        titles = ", ".join(sorted({row.title for row in rows}))
        lines.append(f"- `{rows[0].entry_type}` ({len(rows)} rows): {titles}")
        for row in rows:
            lines.append(f"  - {row.describe()}")
    return lines


def render_report(
    *,
    source_id: str,
    data_root: Path,
    db_path: Path,
    raw_summary: dict[str, Any],
    db_summary: dict[str, Any],
) -> str:
    lines = [
        f"# DND 5E Duplicate Audit - {source_id}",
        "",
        "## Scope",
        f"- Source ID: `{source_id}`",
        f"- Data root: `{data_root}`",
        f"- DB path: `{db_path}`",
        "",
        "## Method",
        "- Raw-source scan groups rows by exact payload hash, importer identity seed, and same-type same-title buckets.",
        "- The `stub mixed group` flag is the most useful signal for user-facing duplicates.",
        "- A stub mixed group means the same source/type/title appears both as a blank-or-near-blank row and as a populated row with a different context.",
        "- DB results use the current local `systems_entries` table to show what is actually visible in the app right now.",
        "",
        "## Raw Source Summary",
        f"- Rows scanned: `{raw_summary['row_count']}`",
        f"- Exact duplicate payload groups: `{len(raw_summary['exact_groups'])}`",
        f"- Importer identity-collision groups: `{len(raw_summary['identity_groups'])}`",
        f"- Same-type same-title groups: `{len(raw_summary['same_title_groups'])}`",
        f"- Stub mixed groups: `{len(raw_summary['stub_mixed_groups'])}`",
        "",
        "## DB Summary",
        f"- Rows scanned: `{db_summary['row_count']}`",
        f"- Exact duplicate payload groups: `{len(db_summary['exact_groups'])}`",
        f"- Same-type same-title groups: `{len(db_summary['same_title_groups'])}`",
        f"- Stub mixed groups: `{len(db_summary['stub_mixed_groups'])}`",
        "",
        "## DB Exact Duplicate Payload Groups",
        *render_exact_group_block(db_summary["exact_groups"]),
        "",
        "## Raw Stub Mixed Groups",
        *render_group_block(raw_summary["stub_mixed_groups"]),
        "",
        "## DB Stub Mixed Groups",
        *render_group_block(db_summary["stub_mixed_groups"]),
        "",
        "## Notes",
        "- Exact duplicate payload groups of `0` means there are no byte-for-byte duplicate rows within this source and entry type.",
        "- Identity-collision groups of `0` means the importer's current uniqueness seed does not collide inside this source.",
        "- Same-title groups can be legitimate, especially class features or subclass features reused across levels or parent classes.",
        "- Stub mixed groups are the strongest indicator that the source export contains compatibility aliases or legacy rows that can look like duplicates in the app.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    data_root = Path(args.data_root)
    db_path = Path(args.db_path)
    importer = Dnd5eSystemsImporter(store=None, systems_service=None, data_root=data_root)

    reports: list[str] = []
    for source_id in args.source_ids:
        normalized_source_id = source_id.strip().upper()
        raw_rows = load_raw_rows(importer, normalized_source_id)
        db_rows = load_db_rows(db_path, normalized_source_id)
        raw_summary = summarize_rows(raw_rows)
        db_summary = summarize_rows(db_rows)
        reports.append(
            render_report(
                source_id=normalized_source_id,
                data_root=data_root,
                db_path=db_path,
                raw_summary=raw_summary,
                db_summary=db_summary,
            )
        )

    report_text = "\n\n".join(reports)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report_text, encoding="utf-8")
    else:
        print(report_text)


if __name__ == "__main__":
    main()
