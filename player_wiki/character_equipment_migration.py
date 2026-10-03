"""Version 1 controlled-copy migration for DND equipment activation.

The planner is pure.  The command reports per-row provenance by default and
requires an explicitly marked controlled copy before any SQLite update.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from .character_equipment_activation import ACTIVATION_FIELDS, activation_marker, analyze_activation
from .character_models import CharacterDefinition, CharacterImportMetadata
from .character_path_safety import resolve_character_path, validate_character_slug
from .character_repository import load_campaign_character_config
from .character_service import validate_state
from .migrations import inspect_migration_ledger
from .system_policy import is_dnd_5e_system


MIGRATION_ID = "character-equipment-activation-v1"


def _bounded_report_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep private definition and inventory bodies out of CLI output."""
    def bounded_field(field: str, detail: Any) -> dict[str, Any]:
        payload = detail if isinstance(detail, dict) else {}
        value = payload.get("value")
        safe_value = (
            value if isinstance(value, bool)
            else value[:128] if field == "weapon_wield_mode" and isinstance(value, str)
            else "malformed_value"
        )
        return {"provenance": str(payload.get("provenance") or "")[:40],
                "value": safe_value}

    report_rows: list[dict[str, Any]] = []
    for row in rows:
        state = row.get("state") if isinstance(row.get("state"), dict) else {}
        fields = row.get("fields") if isinstance(row.get("fields"), dict) else {
            field: {"provenance": "sqlite_explicit", "value": state[field]}
            for field in ACTIVATION_FIELDS if field in state
        }
        report_rows.append({
            "source": str(row.get("source") or ""),
            "index": row.get("index"),
            "id": str(row.get("id") or "")[:128],
            "status": str(row.get("status") or ""),
            "reason": str(row.get("reason") or ""),
            "fields": {field: bounded_field(field, fields[field])
                       for field in ACTIVATION_FIELDS if field in fields},
        })
    return report_rows


def _assert_activation_only_delta(before: dict[str, Any], after: dict[str, Any]) -> None:
    changed_top = {key for key in set(before) | set(after) if before.get(key) != after.get(key)}
    if changed_top - {"inventory", "attunement", "equipment_activation"}:
        raise ValueError("Migration would alter unrelated Character state.")
    old_rows = list(before.get("inventory") or [])
    new_rows = list(after.get("inventory") or [])
    if len(old_rows) != len(new_rows):
        raise ValueError("Migration would change inventory row count without explicit repair.")
    for old, new in zip(old_rows, new_rows):
        if not isinstance(old, dict) or not isinstance(new, dict):
            raise ValueError("Migration inventory row is malformed.")
        changed = {key for key in set(old) | set(new) if old.get(key) != new.get(key)}
        if changed - set(ACTIVATION_FIELDS):
            raise ValueError("Migration would alter unrelated inventory fields.")
    old_attunement = dict(before.get("attunement") or {})
    new_attunement = dict(after.get("attunement") or {})
    if {key for key in set(old_attunement) | set(new_attunement)
        if old_attunement.get(key) != new_attunement.get(key)} - {"attuned_item_refs"}:
        raise ValueError("Migration would alter unrelated attunement fields.")


def plan_equipment_activation_migration(
    definition: CharacterDefinition, state: dict[str, Any], *, allow_partial: bool = False
) -> dict[str, Any]:
    if not is_dnd_5e_system(definition.system):
        return {"status": "skipped_system", "state": deepcopy(state), "rows": [], "warnings": []}
    existing_marker = dict(state.get("equipment_activation") or {})
    if existing_marker.get("schema_version") == 1:
        analysis = analyze_activation(definition, state)
        return {"status": "already_migrated" if not analysis["blocked"] else "quarantined",
                "state": deepcopy(state), "rows": analysis["rows"],
                "warnings": analysis["warnings"]}
    definition_rows = [dict(item) for item in list(definition.equipment_catalog or [])
                       if isinstance(item, dict) and not item.get("is_currency_only")]
    raw_state_rows = list(state.get("inventory") or [])
    if any(not isinstance(item, dict) for item in raw_state_rows):
        return {"status": "quarantined", "state": deepcopy(state), "rows": [],
                "warnings": [{"code": "malformed_inventory_row",
                              "message": "A non-object inventory row needs manager review."}]}
    state_rows = [dict(item) for item in raw_state_rows]
    definition_ids = [str(item.get("id") or "").strip() for item in definition_rows]
    state_ids = [str(item.get("catalog_ref") or item.get("id") or "").strip() for item in state_rows]
    def_counts, state_counts = Counter(definition_ids), Counter(state_ids)
    by_id = {str(item.get("id") or "").strip(): item for item in definition_rows}
    candidate = deepcopy(state)
    provenance: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    unsafe = False
    for index, row in enumerate(state_rows):
        item_id = state_ids[index]
        reason = ""
        if row.get("unlinked_activation_discarded"):
            provenance.append({"source": "sqlite", "index": index, "id": item_id,
                               "status": "explicit_discard_preserved", "fields": {}})
            continue
        if not item_id or (row.get("id") and row.get("catalog_ref")
                           and str(row["id"]).strip() != str(row["catalog_ref"]).strip()):
            reason = "missing_or_conflicting_state_id"
        elif state_counts[item_id] != 1 or def_counts[item_id] != 1:
            reason = "duplicate_or_orphan_id"
        elif any(field in row and not isinstance(row[field], bool)
                 for field in ACTIVATION_FIELDS[:2]):
            reason = "malformed_activation_boolean"
        elif "weapon_wield_mode" in row and not isinstance(row["weapon_wield_mode"], str):
            reason = "malformed_wield_mode"
        if reason:
            unsafe = True
            warnings.append({"code": reason, "message": f"Row {index} ({item_id or 'no ID'}) needs manager repair."})
            provenance.append({"source": "sqlite", "index": index, "id": item_id,
                               "status": "quarantined", "reason": reason,
                               "fields": {field: {"provenance": "sqlite_explicit", "value": row.get(field)}
                                          for field in ACTIVATION_FIELDS if field in row}})
            continue
        target = by_id[item_id]
        fields: dict[str, dict[str, Any]] = {}
        for field in ACTIVATION_FIELDS:
            if field in row:
                value = row[field]
                origin = "sqlite_explicit"
            else:
                value = target.get(field, "" if field == "weapon_wield_mode" else False)
                origin = "yaml_seed_missing"
            if field == "weapon_wield_mode":
                value = str(value or "").strip()
            else:
                value = bool(value)
            candidate["inventory"][index][field] = value
            fields[field] = {"provenance": origin, "value": value}
        provenance.append({"source": "sqlite", "index": index, "id": item_id,
                           "status": "exact", "fields": fields})
    for index, item in enumerate(definition_rows):
        item_id = definition_ids[index]
        if not item_id or def_counts[item_id] != 1:
            unsafe = True
            warnings.append({"code": "definition_identity_ambiguous",
                             "message": f"Definition row {index} needs manager repair."})
            provenance.append({"source": "definition", "index": index, "id": item_id,
                               "status": "quarantined"})
        elif state_counts[item_id] == 0:
            unsafe = True
            warnings.append({"code": "missing_state_row_unproven",
                             "message": f"Definition row {index} has no proven state row; manager repair is required."})
            provenance.append({"source": "definition", "index": index, "id": item_id,
                               "status": "quarantined_missing_state"})
    if unsafe:
        # The preview reports safe field provenance; ambiguous characters are
        # left byte-for-byte unchanged until explicit manager repair.
        return {"status": "quarantined", "state": candidate if allow_partial else deepcopy(state),
                "rows": provenance, "warnings": warnings}
    candidate["equipment_activation"] = activation_marker(definition)
    candidate["attunement"] = dict(candidate.get("attunement") or {})
    candidate["attunement"]["attuned_item_refs"] = [
        str(item.get("catalog_ref") or item.get("id") or "").strip()
        for item in candidate.get("inventory") or [] if bool(item.get("is_attuned"))
    ]
    validate_state(definition, candidate)
    _assert_activation_only_delta(state, candidate)
    if analyze_activation(definition, candidate)["blocked"]:
        raise ValueError("Post-migration activation invariants failed.")
    return {"status": "ready", "state": candidate, "rows": provenance,
            "warnings": []}


def migrate_controlled_copy(campaigns_dir: Path, database_path: Path, *, apply: bool) -> dict[str, Any]:
    campaigns_dir = campaigns_dir.resolve(strict=True)
    database_path = database_path.resolve(strict=True)
    if apply and not (campaigns_dir / ".cpw-activation-controlled-copy").is_file():
        raise ValueError("Apply requires a marked controlled copy of the campaign root.")
    if apply and not (database_path.parent / ".cpw-activation-controlled-copy").is_file():
        raise ValueError("Apply requires a marked controlled copy of the database directory.")
    uri = f"file:{database_path.as_posix()}?mode={'rw' if apply else 'ro'}"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        ledger = inspect_migration_ledger(connection)
        if not ledger.is_current:
            raise ValueError("Database schema migration ledger is not current.")
        if apply:
            from .committed_publication import active
            if active(connection):
                raise ValueError("Activated Character state requires committed definition authority.")
        rows = connection.execute(
            "SELECT campaign_slug, character_slug, revision, state_json FROM character_state "
            "ORDER BY campaign_slug, character_slug"
        ).fetchall()
        report: list[dict[str, Any]] = []
        counts: Counter[str] = Counter()
        seen_keys: set[tuple[str, str]] = set()
        for db_row in rows:
            campaign_slug = str(db_row["campaign_slug"])
            character_slug = str(db_row["character_slug"])
            seen_keys.add((campaign_slug, character_slug))
            validate_character_slug(character_slug)
            protected = connection.execute(
                "SELECT 1 FROM character_reconciliation_operations WHERE campaign_slug=? AND character_slug=? "
                "AND state IN ('prepared','repository_pending','conflict') UNION ALL "
                "SELECT 1 FROM character_deletion_operations WHERE campaign_slug=? AND character_slug=? "
                "AND state IN ('prepared','repository_pending','conflict') LIMIT 1",
                (campaign_slug, character_slug, campaign_slug, character_slug),
            ).fetchone()
            if protected:
                counts["journal_protected"] += 1
                report.append({"campaign_slug": campaign_slug, "character_slug": character_slug,
                               "revision": int(db_row["revision"]),
                               "status": "journal_protected", "rows": [],
                               "warnings": [{"code": "journal_protected",
                                             "message": "Character publication or deletion recovery is pending."}]})
                continue
            config = load_campaign_character_config(campaigns_dir, campaign_slug)
            if config.campaign_slug != campaign_slug:
                raise ValueError("Campaign source identity differs from SQLite.")
            if not config.characters_dir.resolve().is_relative_to(campaigns_dir):
                raise ValueError("Configured character directory escapes the controlled copy.")
            definition_path = resolve_character_path(config.characters_dir, character_slug, "definition.yaml")
            import_path = resolve_character_path(config.characters_dir, character_slug, "import.yaml")
            if not definition_path.is_file():
                raise ValueError("Character definition is missing for a SQLite row.")
            if not import_path.is_file():
                raise ValueError("Character import metadata is missing for a SQLite row.")
            definition_bytes = definition_path.read_bytes()
            import_bytes = import_path.read_bytes()
            payload = yaml.safe_load(definition_bytes.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Character definition must be a mapping.")
            definition = CharacterDefinition.from_dict(payload)
            import_payload = yaml.safe_load(import_bytes.decode("utf-8"))
            if not isinstance(import_payload, dict):
                raise ValueError("Character import metadata must be a mapping.")
            import_metadata = CharacterImportMetadata.from_dict(import_payload)
            if definition.campaign_slug != campaign_slug or definition.character_slug != character_slug:
                raise ValueError("Character source identity differs from SQLite.")
            if (import_metadata.campaign_slug != campaign_slug
                    or import_metadata.character_slug != character_slug):
                raise ValueError("Character import identity differs from SQLite.")
            state = json.loads(db_row["state_json"])
            if not isinstance(state, dict):
                raise ValueError("Character state must be a mapping.")
            plan = plan_equipment_activation_migration(definition, state)
            counts[plan["status"]] += 1
            report.append({"campaign_slug": campaign_slug, "character_slug": character_slug,
                           "revision": int(db_row["revision"]),
                           "definition_sha256": hashlib.sha256(definition_bytes).hexdigest(),
                           "import_sha256": hashlib.sha256(import_bytes).hexdigest(),
                           "status": plan["status"], "rows": _bounded_report_rows(plan["rows"]),
                           "warnings": plan["warnings"]})
            if not apply or plan["status"] != "ready" or plan["state"] == state:
                continue
            # One character per transaction makes interruption restartable.
            connection.execute("BEGIN IMMEDIATE")
            try:
                protected = connection.execute(
                    "SELECT 1 FROM character_reconciliation_operations WHERE campaign_slug=? AND character_slug=? "
                    "AND state IN ('prepared','repository_pending','conflict') UNION ALL "
                    "SELECT 1 FROM character_deletion_operations WHERE campaign_slug=? AND character_slug=? "
                    "AND state IN ('prepared','repository_pending','conflict') LIMIT 1",
                    (campaign_slug, character_slug, campaign_slug, character_slug),
                ).fetchone()
                if (protected
                        or definition_path.read_bytes() != definition_bytes
                        or import_path.read_bytes() != import_bytes):
                    raise ValueError("Character source or journal changed during migration.")
                cursor = connection.execute(
                    "UPDATE character_state SET revision=revision+1, state_json=? "
                    "WHERE campaign_slug=? AND character_slug=? AND revision=? AND state_json=?",
                    (json.dumps(plan["state"], sort_keys=True), campaign_slug, character_slug,
                     int(db_row["revision"]), str(db_row["state_json"])),
                )
                if cursor.rowcount != 1:
                    raise ValueError("Character state changed during migration.")
                connection.commit()
                confirmed = connection.execute(
                    "SELECT revision, state_json FROM character_state "
                    "WHERE campaign_slug=? AND character_slug=?",
                    (campaign_slug, character_slug),
                ).fetchone()
                if (confirmed is None
                        or int(confirmed["revision"]) != int(db_row["revision"]) + 1
                        or analyze_activation(definition, json.loads(confirmed["state_json"]))["blocked"]):
                    raise ValueError("Post-migration SQLite invariants failed; stop the controlled copy.")
            except Exception:
                connection.rollback()
                raise
        for campaign_config in sorted(campaigns_dir.glob("*/campaign.yaml")):
            campaign_slug = campaign_config.parent.name
            config = load_campaign_character_config(campaigns_dir, campaign_slug)
            if config.campaign_slug != campaign_slug or not config.characters_dir.resolve().is_relative_to(campaigns_dir):
                raise ValueError("Campaign source identity or character directory is invalid.")
            for definition_path in sorted(config.characters_dir.glob("*/definition.yaml")):
                character_slug = definition_path.parent.name
                validate_character_slug(character_slug)
                if (campaign_slug, character_slug) in seen_keys:
                    continue
                counts["source_without_state"] += 1
                report.append({"campaign_slug": campaign_slug,
                               "character_slug": character_slug,
                               "status": "source_without_state", "rows": [],
                               "warnings": [{"code": "source_without_state",
                                             "message": "Definition has no SQLite state row; no automatic seed is authorized."}]})
        return {"migration_id": MIGRATION_ID, "mode": "apply" if apply else "dry_run",
                "counts": dict(counts), "characters": report}
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaigns-dir", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--apply-controlled-copy", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate_controlled_copy(args.campaigns_dir, args.database,
                                             apply=args.apply_controlled_copy),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
