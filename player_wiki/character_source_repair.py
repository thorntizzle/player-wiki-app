"""Bounded manager source repair and independently witnessed manual grants.

Definition records are proposals.  A MANUAL record becomes authoritative only
when the journaled manager publication also produced its matching audit row.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

from .db import get_db
from .character_models import CharacterDefinition


MANUAL_METRICS = frozenset({"availability", "spell_attack_bonus", "spell_save_dc"})
MANUAL_TARGETS = frozenset({"spell", "source_row"})
NUMERIC_TARGETS = frozenset({"field", "proficiency", "resource", "spell_metric", "spell_choice"})
NUMERIC_METRICS = frozenset({"base", "final", "adjustment", "grant", "owner_reset", "formula", "selection"})
REPAIR_FAMILIES = frozenset({"item", "feature", "spell"})
SOURCE_KINDS = frozenset({"systems_entry", "campaign_page"})
MAX_ID = 512


class SourceRepairError(ValueError):
    """The proposed repair cannot be tied to one exact current identity."""


def _bounded(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise SourceRepairError(f"{label} must be text.")
    clean = value.strip()
    if not clean or len(clean.encode("utf-8")) > MAX_ID:
        raise SourceRepairError(f"{label} is invalid.")
    return clean


def _rows(definition: Mapping[str, Any], family: str) -> list[dict[str, Any]]:
    if family == "item":
        value = definition.get("equipment_catalog") or []
    elif family == "feature":
        value = definition.get("features") or []
    elif family == "spell":
        value = (definition.get("spellcasting") or {}).get("spells") or []
    else:
        raise SourceRepairError("Unsupported repair family.")
    if not isinstance(value, list) or any(not isinstance(row, Mapping) for row in value):
        raise SourceRepairError("Character source rows are malformed.")
    return [deepcopy(dict(row)) for row in value]


def _target_id(row: Mapping[str, Any], family: str) -> str:
    # A spell must already have a durable instance id; a title is never one.
    return str(row.get("id") or "").strip()


def eligible_repair_targets(definition: Mapping[str, Any]) -> tuple[dict[str, str], ...]:
    targets: list[dict[str, str]] = []
    for family in ("item", "feature", "spell"):
        rows = _rows(definition, family)
        counts: dict[str, int] = {}
        for row in rows:
            target = _target_id(row, family)
            if target:
                counts[target] = counts.get(target, 0) + 1
        for row in rows:
            target = _target_id(row, family)
            if not target or counts[target] != 1 or len(target.encode("utf-8")) > MAX_ID:
                continue
            targets.append({
                "family": family,
                "target_id": target,
                "label": str(row.get("name") or row.get("title") or target)[:160],
            })
    return tuple(targets)


def repair_definition(
    definition: Mapping[str, Any], *, family: str, target_id: str,
    source_kind: str, source_value: str, source_record: object,
    campaign_option: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Change only one exact link; retain row, selection, and ownership identity."""
    if family not in REPAIR_FAMILIES or source_kind not in SOURCE_KINDS:
        raise SourceRepairError("Unsupported repair source.")
    target_id = _bounded(target_id, "Target id")
    source_value = _bounded(source_value, "Source identity")
    result = deepcopy(dict(definition))
    rows = _rows(result, family)
    matches = [index for index, row in enumerate(rows) if _target_id(row, family) == target_id]
    if len(matches) != 1:
        raise SourceRepairError("The Character target has no unique instance identity.")
    row = rows[matches[0]]
    if source_kind == "campaign_page":
        if str(getattr(source_record, "page_ref", "") or "").strip() != source_value:
            raise SourceRepairError("The published page identity changed.")
        row["page_ref"] = source_value
        row.pop("systems_ref", None)
    else:
        if str(getattr(source_record, "entry_key", "") or "").strip() != source_value:
            raise SourceRepairError("The Systems entry identity changed.")
        entry_type = str(getattr(source_record, "entry_type", "") or "").strip()
        slug = str(getattr(source_record, "slug", "") or "").strip()
        if not entry_type or not slug:
            raise SourceRepairError("The Systems entry is incomplete.")
        row["systems_ref"] = {
            "entry_key": source_value,
            "entry_type": entry_type,
            "slug": slug,
            "title": str(getattr(source_record, "title", "") or "").strip(),
            "source_id": str(getattr(source_record, "source_id", "") or "").strip(),
        }
        row.pop("page_ref", None)
        # Preserve historical choices; SourceAuthority discards copied effects
        # and rehydrates only approved current mechanics during projection.
    rows[matches[0]] = row
    if family == "item":
        result["equipment_catalog"] = rows
    elif family == "feature":
        result["features"] = rows
    else:
        spellcasting = deepcopy(dict(result.get("spellcasting") or {}))
        spellcasting["spells"] = rows
        result["spellcasting"] = spellcasting
    return result


def manual_authorization_record(
    *, character_slug: str, target_kind: str, target_id: str,
    metric: str, action_id: str, definition: CharacterDefinition,
) -> dict[str, Any]:
    from .character_source_authority import manual_target_digest
    if target_kind not in MANUAL_TARGETS or metric not in MANUAL_METRICS:
        raise SourceRepairError("Unsupported manual authorization target or metric.")
    target_digest = manual_target_digest(definition, target_kind, target_id)
    if target_digest is None:
        raise SourceRepairError("Manual target content is ambiguous.")
    return {
        "schema_version": 2,
        "character_slug": _bounded(character_slug, "Character"),
        "target_kind": target_kind,
        "target_id": _bounded(target_id, "Target id"),
        "metric": metric,
        "action_id": _bounded(action_id, "Action id"),
        "provenance": "manager",
        "target_digest": target_digest,
    }


def add_manual_authorization(
    definition: Mapping[str, Any], authorization: Mapping[str, Any],
) -> dict[str, Any]:
    result = deepcopy(dict(definition))
    spellcasting = deepcopy(dict(result.get("spellcasting") or {}))
    rows = spellcasting.get("spells" if authorization["target_kind"] == "spell" else "source_rows") or []
    if not isinstance(rows, list) or sum(
        isinstance(row, Mapping)
        and str(row.get("id" if authorization["target_kind"] == "spell" else "source_row_id") or "").strip()
        == authorization["target_id"]
        for row in rows
    ) != 1:
        raise SourceRepairError("Manual authorization requires one exact current target.")
    existing = spellcasting.get("manual_authorizations") or []
    if not isinstance(existing, list) or any(not isinstance(row, Mapping) for row in existing):
        raise SourceRepairError("Existing manual authorizations are malformed.")
    if any(
        row.get("target_kind") == authorization["target_kind"]
        and row.get("target_id") == authorization["target_id"]
        and row.get("metric") == authorization["metric"]
        for row in existing
    ):
        raise SourceRepairError("This metric already has a manual authorization record.")
    spellcasting["manual_authorizations"] = [*deepcopy(existing), dict(authorization)]
    result["spellcasting"] = spellcasting
    return result


def numeric_authorization_record(
    *, character_slug: str, target_kind: str, target_id: str,
    metric: str, raw_value: Any, action_id: str, provenance: str,
    owner_digest: str | None = None,
) -> dict[str, Any]:
    from .character_source_authority import numeric_value_digest
    if target_kind not in NUMERIC_TARGETS or metric not in NUMERIC_METRICS:
        raise SourceRepairError("Unsupported numeric authorization target or metric.")
    if provenance not in {"manager", "native_creation", "native_level_up", "native_spell_choice"}:
        raise SourceRepairError("Unsupported numeric authorization provenance.")
    if provenance == "native_spell_choice" and target_kind != "spell_choice":
        raise SourceRepairError("Native spell selection can authorize only a spell choice.")
    if target_kind == "spell_metric" and (provenance == "manager" or metric != "formula"):
        raise SourceRepairError("Only native source-bound formula witnesses are supported.")
    if target_kind == "spell_choice" and (provenance == "manager" or metric != "selection"):
        raise SourceRepairError("Only native source-bound spell choices are supported.")
    if provenance == "manager" and not _sha256_hex(owner_digest):
        raise SourceRepairError("Manager target owner context is unavailable.")
    return {
        "schema_version": 3 if provenance == "manager" else 2,
        "character_slug": _bounded(character_slug, "Character"),
        "target_kind": target_kind,
        "target_id": _bounded(target_id, "Target id"),
        "metric": metric,
        "value_digest": numeric_value_digest(raw_value),
        "action_id": _bounded(action_id, "Action id"),
        "provenance": provenance,
        **({"owner_digest": owner_digest} if provenance == "manager" else {}),
    }


def add_numeric_authorization(
    definition: Mapping[str, Any], authorization: Mapping[str, Any],
) -> dict[str, Any]:
    """Replace only the named field owner; never infer a nearby target by title."""
    result = deepcopy(dict(definition))
    source = deepcopy(dict(result.get("source") or {}))
    existing = source.get("source_authorizations") or []
    if not isinstance(existing, list) or any(not isinstance(row, Mapping) for row in existing):
        raise SourceRepairError("Existing source authorizations are malformed.")
    filtered = [
        deepcopy(dict(row)) for row in existing
        if not (row.get("target_kind") == authorization["target_kind"]
                and row.get("target_id") == authorization["target_id"]
                and row.get("metric") == authorization["metric"])
    ]
    source["source_authorizations"] = [*filtered, dict(authorization)]
    result["source"] = source
    return result


def page_feature_authorization_record(
    *, definition: CharacterDefinition, state: dict[str, Any], template: dict[str, Any],
    feature_id: str, page_ref: str, page_revision: int, source_basis_digest: str,
    source_snapshot_digest: str, operation_digest: str, config_revision: int,
) -> dict[str, Any]:
    """Create a pending marker; only a separate confirmed audit can trust it."""
    from .character_source_authority import numeric_target_owner_digest, numeric_value_digest
    target_id = f"resource:{str(template.get('id') or '').strip()}"
    owner_digest = numeric_target_owner_digest(
        definition, state, "resource", target_id, "owner_reset",
    )
    if (not target_id.startswith("resource:campaign-option-tracker:")
            or not all(_sha256_hex(value) for value in (
                owner_digest, source_basis_digest, source_snapshot_digest, operation_digest,
            )) or type(page_revision) is not int or page_revision < 1
            or type(config_revision) is not int or config_revision < 1
            or type(template.get("initial_current")) is not int
            or template["initial_current"] != template.get("max")):
        raise SourceRepairError("Page feature resource proof is unavailable.")
    marker = {
        "schema_version": 4,
        "character_slug": definition.character_slug,
        "target_kind": "resource",
        "target_id": target_id,
        "metric": "owner_reset",
        "value_digest": numeric_value_digest(template),
        "action_id": operation_digest,
        "provenance": "page_feature_update",
        "owner_digest": owner_digest,
        "source_basis_digest": source_basis_digest,
        "source_snapshot_digest": source_snapshot_digest,
        "operation_digest": operation_digest,
        "config_revision": config_revision,
        "feature_id": _bounded(feature_id, "feature id"),
        "page_ref": _bounded(page_ref, "page ref"),
        "page_revision": page_revision,
        "initial_value": template["initial_current"],
    }
    if not _valid_numeric_witness_marker(marker, definition.character_slug,
                                         "page_feature_update"):
        raise SourceRepairError("Page feature resource proof is malformed.")
    return marker


def _valid_numeric_witness_marker(marker: Any, character_slug: str, provenance: str) -> bool:
    fields = {
        "schema_version", "character_slug", "target_kind", "target_id",
        "metric", "value_digest", "action_id", "provenance",
    }
    if provenance == "manager":
        fields.add("owner_digest")
    if provenance == "page_feature_update":
        fields.update({"owner_digest", "source_basis_digest", "page_ref", "page_revision",
                       "feature_id", "source_snapshot_digest", "operation_digest",
                       "config_revision", "initial_value"})
    if not isinstance(marker, dict) or set(marker) != fields:
        return False
    if (type(marker.get("schema_version")) is not int or marker["schema_version"] != (
            3 if provenance == "manager" else 4 if provenance == "page_feature_update" else 2)
            or marker.get("character_slug") != character_slug
            or marker.get("target_kind") not in NUMERIC_TARGETS
            or marker.get("metric") not in NUMERIC_METRICS
            or marker.get("provenance") != provenance):
        return False
    try:
        _bounded(marker["target_id"], "target_id")
        _bounded(marker["action_id"], "action_id")
    except (KeyError, SourceRepairError):
        return False
    digest = marker.get("value_digest")
    if provenance == "page_feature_update" and (
        marker.get("target_kind") != "resource" or marker.get("metric") != "owner_reset"
        or not str(marker.get("target_id") or "").startswith("resource:campaign-option-tracker:")
        or marker.get("target_id") != f"resource:campaign-option-tracker:{marker.get('feature_id')}"
        or marker.get("operation_digest") != marker.get("action_id")
        or type(marker.get("page_revision")) is not int or marker["page_revision"] < 1
        or type(marker.get("config_revision")) is not int or marker["config_revision"] < 1
        or type(marker.get("initial_value")) is not int or marker["initial_value"] < 0
        or not all(_sha256_hex(marker.get(key)) for key in (
            "owner_digest", "source_basis_digest", "source_snapshot_digest", "operation_digest"))
        or not isinstance(marker.get("page_ref"), str) or not marker["page_ref"]
        or not isinstance(marker.get("feature_id"), str) or not marker["feature_id"]
    ):
        return False
    return (_sha256_hex(digest) and (provenance not in {"manager", "page_feature_update"}
                                     or _sha256_hex(marker.get("owner_digest"))))


def load_verified_numeric_actions(campaign_slug: str, character_slug: str, *,
                                  connection: sqlite3.Connection | None = None,
                                  strict: bool = False,
                                  include_origin: bool = False) -> tuple[dict[str, Any], ...]:
    """Load only actor-bound manager/native audit records, never copied YAML labels."""
    try:
        db = connection if connection is not None else get_db()
        rows = db.execute(
            """SELECT id,actor_user_id, event_type, metadata_json FROM auth_audit_log
               WHERE campaign_slug = ? AND character_slug = ?
                 AND event_type IN ('character_update_applied', 'character_page_feature_grant_confirmed',
                                    'character_native_created', 'character_native_leveled', 'character_native_spell_selected')
               ORDER BY id ASC""",
            (campaign_slug, character_slug),
        ).fetchall()
    except Exception:
        if strict:
            raise SourceRepairError("Numeric audit proof is unavailable.")
        return ()
    witnesses: list[dict[str, Any]] = []
    origins: list[dict[str, Any]] = []
    confirmed_updates: set[tuple[int, str, str]] = set()
    for row in rows:
        if row["event_type"] != "character_update_applied":
            continue
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
            if (type(row["actor_user_id"]) is int and isinstance(metadata, dict)
                    and metadata.get("source") == "character_update_preview"
                    and _sha256_hex(metadata.get("review_digest"))
                    and _sha256_hex(metadata.get("candidate_digest"))):
                confirmed_updates.add((row["actor_user_id"], metadata["review_digest"],
                                       metadata["candidate_digest"]))
        except (TypeError, ValueError):
            continue
    for row in rows:
        start = len(witnesses)
        try:
            actor_id = row["actor_user_id"]
            if type(actor_id) is not int or actor_id < 1:
                continue
            metadata = json.loads(row["metadata_json"] or "{}")
            if not isinstance(metadata, dict) or metadata.get("numeric_actor_id") != actor_id:
                continue
            if row["event_type"] == "character_page_feature_grant_confirmed":
                marker = metadata.get("numeric_authorization")
                if (metadata.get("source") != "page_feature_update_confirmed"
                        or not _valid_numeric_witness_marker(marker, character_slug,
                                                             "page_feature_update")
                        or metadata.get("action_id") != marker["action_id"]
                        or metadata.get("source_basis_digest") != marker["source_basis_digest"]
                        or type(metadata.get("committed_revision")) is not int
                        or metadata["committed_revision"] < 1
                        or type(metadata.get("prior_state_revision")) is not int
                        or type(metadata.get("state_revision")) is not int
                        or metadata["state_revision"] != metadata["prior_state_revision"] + 1
                        or not _sha256_hex(metadata.get("review_digest"))
                        or not _sha256_hex(metadata.get("candidate_digest"))
                        or (actor_id, metadata["review_digest"], metadata["candidate_digest"])
                        not in confirmed_updates):
                    continue
                witnesses.append({"authorization": dict(marker),
                                  "source_basis_digest": marker["source_basis_digest"]})
                continue
            if row["event_type"] == "character_update_applied":
                if (metadata.get("manager_action") != "numeric_attest"
                        or not isinstance(metadata.get("review_digest"), str)
                        or len(metadata["review_digest"]) != 64):
                    continue
                marker = metadata.get("numeric_authorization")
                if (_valid_numeric_witness_marker(marker, character_slug, "manager")
                        and metadata.get("action_id") == marker["action_id"]):
                    witnesses.append(dict(marker))
            elif row["event_type"] == "character_native_created":
                if (metadata.get("source") != "native_create_confirmed"
                        or not _sha256_hex(metadata.get("definition_digest"))):
                    continue
                batch = metadata.get("numeric_authorizations")
                if not isinstance(batch, list) or not 1 <= len(batch) <= 128:
                    continue
                action_id = metadata.get("action_id")
                basis = metadata.get("source_basis_digests")
                if not isinstance(action_id, str) or not action_id or not isinstance(basis, dict):
                    continue
                bound_ids = [marker.get("target_id") for marker in batch
                             if isinstance(marker, dict) and _native_source_bound_marker(marker)]
                if all(_valid_numeric_witness_marker(marker, character_slug, "native_creation")
                       and marker["action_id"] == action_id
                       and (marker.get("target_kind") not in {"resource", "spell_metric", "spell_choice"}
                            or _native_source_bound_marker(marker)) for marker in batch) and (
                           len(bound_ids) == len(set(bound_ids))
                           and set(basis) == set(bound_ids)
                           and all(_sha256_hex(value) for value in basis.values())):
                    witnesses.extend(
                        {"authorization": dict(marker),
                         "source_basis_digest": basis[marker["target_id"]]}
                        if _native_source_bound_marker(marker) else dict(marker)
                        for marker in batch
                    )
            elif row["event_type"] in {"character_native_leveled", "character_native_spell_selected"}:
                spell_choice = row["event_type"] == "character_native_spell_selected"
                expected_provenance = "native_spell_choice" if spell_choice else "native_level_up"
                expected_source = "native_spell_choice_confirmed" if spell_choice else "native_level_up_confirmed"
                prior_revision = metadata.get("prior_state_revision")
                revision = metadata.get("state_revision")
                if (metadata.get("source") != expected_source
                        or type(prior_revision) is not int or prior_revision < 0
                        or type(revision) is not int or revision != prior_revision + 1
                        or not _sha256_hex(metadata.get("definition_digest"))
                        or not _sha256_hex(metadata.get("source_snapshot_digest"))):
                    continue
                batch = metadata.get("numeric_authorizations")
                action_id = metadata.get("action_id")
                basis = metadata.get("source_basis_digests")
                if (not isinstance(batch, list) or not 1 <= len(batch) <= 128
                        or not isinstance(action_id, str) or not action_id
                        or not isinstance(basis, dict)):
                    continue
                if all(_valid_numeric_witness_marker(marker, character_slug, expected_provenance)
                       and marker["action_id"] == action_id
                       and _native_source_bound_marker(marker)
                       and (not spell_choice or marker.get("target_kind") == "spell_choice")
                       and _sha256_hex(basis.get(marker["target_id"]))
                       for marker in batch):
                    if len(basis) == len(batch) and len({marker["target_id"] for marker in batch}) == len(batch):
                        witnesses.extend({"authorization": dict(marker),
                                          "source_basis_digest": basis[marker["target_id"]]}
                                         for marker in batch)
        except (KeyError, TypeError, ValueError):
            continue
        finally:
            if include_origin:
                origins.extend({"witness": witness, "audit_id": row["id"],
                                "actor_user_id": row["actor_user_id"],
                                "event_type": row["event_type"],
                                "source_snapshot_digest": json.loads(
                                    row["metadata_json"]).get("source_snapshot_digest"),
                                "metadata_sha256": hashlib.sha256(
                                    row["metadata_json"].encode("utf-8")).hexdigest()}
                               for witness in witnesses[start:])
    if include_origin:
        return tuple(origins)
    return (*witnesses, *_load_transition_actions(db, campaign_slug, character_slug,
                                                   strict=strict))


def _load_transition_actions(connection: sqlite3.Connection, campaign_slug: str,
                             character_slug: str, *, strict: bool = False) -> tuple[dict[str, Any], ...]:
    """Accept only activation-transaction proofs linked to one original audit row."""
    try:
        from .committed_publication import active
        if not active(connection):
            return ()
        marker = connection.execute("SELECT activated_at FROM committed_source_activation WHERE singleton=1").fetchone()
        rows = connection.execute(
            """SELECT actor_user_id,metadata_json FROM auth_audit_log
               WHERE campaign_slug=? AND character_slug=?
                 AND event_type='character_source_transition_confirmed' ORDER BY id""",
            (campaign_slug, character_slug),
        ).fetchall()
        if not rows:
            return ()
        originals = load_verified_numeric_actions(campaign_slug, character_slug,
                    connection=connection, strict=True, include_origin=True)
        current_identity = _current_transition_identity(connection, campaign_slug,
                                                        character_slug)
        candidates: list[dict[str, Any]] = []
        counts: dict[tuple[str, str, str, str], int] = {}
        proof_fields = {"schema_version", "campaign_slug", "character_slug",
            "target_kind", "target_id", "metric", "authorization",
            "origin_audit_id", "origin_actor_user_id", "origin_event_type",
            "origin_metadata_sha256", "old_basis", "new_basis",
            "old_snapshot", "new_snapshot", "value_digest", "owner_digest",
            "identity", "activated_at"}
        for row in rows:
            try:
                proof = json.loads(row["metadata_json"])
                if not isinstance(proof, dict):
                    continue
                key = (str(proof.get("target_kind")), str(proof.get("target_id")),
                       str(proof.get("metric")), str(proof.get("new_basis")))
                counts[key] = counts.get(key, 0) + 1
                if (row["actor_user_id"] is not None or set(proof) != proof_fields
                        or proof.get("schema_version") != 1
                        or proof.get("campaign_slug") != campaign_slug
                        or proof.get("character_slug") != character_slug
                        or marker is None or proof.get("activated_at") != marker[0]
                        or proof.get("target_kind") not in {"resource", "spell_metric", "spell_choice"}
                        or not all(_sha256_hex(proof.get(name)) for name in (
                            "old_basis", "new_basis", "old_snapshot", "new_snapshot",
                            "value_digest", "owner_digest", "origin_metadata_sha256"))
                        or type(proof.get("origin_audit_id")) is not int
                        or type(proof.get("origin_actor_user_id")) is not int
                        or not isinstance(proof.get("authorization"), dict)
                        or not isinstance(proof.get("identity"), dict)
                        or not current_identity
                        or set(proof["identity"]) != {
                            "generation", "state", "config", "systems", "pages",
                            "page_current", "audit"}
                        or not _sha256_hex(proof["identity"].get("audit"))
                        or any(proof["identity"].get(name) != value for name, value
                               in current_identity.items() if name != "state")):
                    continue
                authorization = proof["authorization"]
                if ((authorization.get("target_kind"), authorization.get("target_id"),
                     authorization.get("metric")) != key[:3]
                        or authorization.get("value_digest") != proof["value_digest"]
                        or (authorization.get("owner_digest") is not None
                            and authorization["owner_digest"] != proof["owner_digest"])):
                    continue
                matching = [original for original in originals
                    if original["audit_id"] == proof["origin_audit_id"]
                    and original["actor_user_id"] == proof["origin_actor_user_id"]
                    and original["event_type"] == proof.get("origin_event_type")
                    and original["metadata_sha256"] == proof["origin_metadata_sha256"]
                    and (original["source_snapshot_digest"] == proof["old_snapshot"]
                         if authorization.get("provenance") != "page_feature_update"
                         else authorization.get("source_snapshot_digest") == proof["old_snapshot"])
                    and isinstance(original["witness"], dict)
                    and original["witness"].get("authorization") == authorization
                    and original["witness"].get("source_basis_digest") == proof["old_basis"]]
                if len(matching) != 1:
                    continue
                candidates.append({"authorization": authorization,
                    "source_basis_digest": proof["new_basis"], "transition_proof": proof})
            except (TypeError, ValueError, KeyError):
                continue
        return tuple(candidate for candidate in candidates
                     if counts[(candidate["authorization"]["target_kind"],
                                candidate["authorization"]["target_id"],
                                candidate["authorization"]["metric"],
                                candidate["source_basis_digest"])] == 1)
    except Exception:
        if strict:
            raise SourceRepairError("Transition audit proof is unavailable.") from None
        return ()


def _current_transition_identity(connection: sqlite3.Connection, campaign_slug: str,
                                 character_slug: str) -> dict[str, object]:
    def digest(rows: object) -> str:
        return hashlib.sha256(json.dumps([tuple(row) for row in rows],sort_keys=True,
            default=str,separators=(",", ":")).encode()).hexdigest()
    character = connection.execute("""SELECT revision,primary_sha256 FROM
        committed_source_current JOIN committed_source_generations
        USING(campaign_slug,object_kind,object_ref,revision)
        WHERE campaign_slug=? AND object_kind='character' AND object_ref=?""",
        (campaign_slug, character_slug)).fetchone()
    config = connection.execute("""SELECT revision,primary_sha256 FROM
        committed_source_current JOIN committed_source_generations
        USING(campaign_slug,object_kind,object_ref,revision)
        WHERE campaign_slug=? AND object_kind='config' AND object_ref=''""",
        (campaign_slug,)).fetchone()
    state = connection.execute("""SELECT revision,state_json FROM character_state
        WHERE campaign_slug=? AND character_slug=?""",
        (campaign_slug, character_slug)).fetchone()
    systems = connection.execute("SELECT token FROM systems_revision WHERE singleton=1").fetchone()
    if any(row is None for row in (character,config,state,systems)):
        return {}
    return {"generation": [character[0],character[1]],
            "state": [state[0],hashlib.sha256(state[1].encode()).hexdigest()],
            "config": [config[0],config[1]], "systems": str(systems[0]),
            "pages": digest(connection.execute(
                "SELECT * FROM campaign_pages WHERE campaign_slug=? ORDER BY page_ref",
                (campaign_slug,)).fetchall()),
            "page_current": digest(connection.execute(
                """SELECT * FROM committed_source_current WHERE campaign_slug=?
                   AND object_kind='page' ORDER BY object_ref""",(campaign_slug,)).fetchall())}


def _sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _native_source_bound_marker(marker: Mapping[str, Any]) -> bool:
    return (
        marker.get("target_kind") == "resource"
        and marker.get("metric") == "owner_reset"
        and str(marker.get("target_id") or "").startswith(("resource:", "spell_slot:", "hit_die:"))
    ) or (
        marker.get("target_kind") == "field"
        and marker.get("target_id") == "stats.max_hp"
        and marker.get("metric") == "final"
    ) or (
        marker.get("target_kind") == "spell_metric"
        and marker.get("metric") == "formula"
        and str(marker.get("target_id") or "").startswith("spell_metric:")
    ) or (
        marker.get("target_kind") == "spell_choice"
        and marker.get("metric") == "selection"
        and str(marker.get("target_id") or "").startswith("spell_choice:")
    )


def record_confirmed_native_level_up_witness(
    *, expected_definition: CharacterDefinition, readback_record: object,
    markers: tuple[dict[str, Any], ...], prior_revision: int,
    source_snapshot_digest: str, source_basis_digests: dict[str, str],
    actor_id: int, auth_store: object, witness_kind: str = "native_level_up",
) -> bool:
    """Record one new owner batch only after a revisioned level-up readback."""
    from .character_source_authority import numeric_target_values, numeric_value_digest
    from .character_update_apply import canonical_digest
    if witness_kind not in {"native_level_up", "native_spell_choice"}:
        return False
    event_type = ("character_native_leveled" if witness_kind == "native_level_up"
                  else "character_native_spell_selected")
    source_label = ("native_level_up_confirmed" if witness_kind == "native_level_up"
                    else "native_spell_choice_confirmed")
    if (type(actor_id) is not int or actor_id < 1
            or type(prior_revision) is not int or prior_revision < 0
            or not _sha256_hex(source_snapshot_digest)
            or not isinstance(source_basis_digests, dict)
            or not isinstance(markers, tuple) or not 1 <= len(markers) <= 128):
        return False
    readback_definition = getattr(readback_record, "definition", None)
    readback_state_record = getattr(readback_record, "state_record", None)
    readback_state = getattr(readback_state_record, "state", None)
    revision = getattr(readback_state_record, "revision", None)
    if (not isinstance(readback_definition, CharacterDefinition)
            or not isinstance(readback_state, dict)
            or type(revision) is not int or revision != prior_revision + 1
            or readback_definition.to_dict() != expected_definition.to_dict()):
        return False
    character_slug = readback_definition.character_slug
    campaign_slug = readback_definition.campaign_slug
    action_id = markers[0].get("action_id") if isinstance(markers[0], dict) else None
    if not isinstance(action_id, str) or not action_id:
        return False
    persisted_markers = list(dict(readback_definition.source or {}).get("source_authorizations") or [])
    target_values = numeric_target_values(readback_definition, readback_state)
    identities: set[tuple[str, str, str]] = set()
    for marker in markers:
        if (not _valid_numeric_witness_marker(marker, character_slug, witness_kind)
                or marker["action_id"] != action_id
                or not _native_source_bound_marker(marker)
                or (witness_kind == "native_spell_choice" and marker["target_kind"] != "spell_choice")
                or marker not in persisted_markers):
            return False
        key = (marker["target_kind"], marker["target_id"], marker["metric"])
        if (key in identities or key not in target_values
                or numeric_value_digest(target_values[key]) != marker["value_digest"]):
            return False
        identities.add(key)
    if (set(source_basis_digests) != {marker["target_id"] for marker in markers}
            or not all(_sha256_hex(value) for value in source_basis_digests.values())):
        return False
    expected_witnesses = tuple(
        {"authorization": dict(marker),
         "source_basis_digest": source_basis_digests[marker["target_id"]]}
        for marker in markers
    )
    try:
        existing = get_db().execute(
            """SELECT metadata_json FROM auth_audit_log
               WHERE event_type = ?
                 AND campaign_slug = ? AND character_slug = ?""",
            (event_type, campaign_slug, character_slug),
        ).fetchall()
        for row in existing:
            metadata = json.loads(row["metadata_json"] or "{}")
            if metadata.get("action_id") == action_id:
                return all(witness in load_verified_numeric_actions(campaign_slug, character_slug)
                           for witness in expected_witnesses)
        auth_store.insert_audit_event(
            event_type=event_type, actor_user_id=actor_id,
            campaign_slug=campaign_slug, character_slug=character_slug,
            metadata={
                "source": source_label,
                "numeric_actor_id": actor_id,
                "numeric_authorizations": list(markers),
                "action_id": action_id,
                "definition_digest": canonical_digest(readback_definition.to_dict()),
                "prior_state_revision": prior_revision,
                "state_revision": revision,
                "source_snapshot_digest": source_snapshot_digest,
                "source_basis_digests": dict(source_basis_digests),
            },
            commit=True,
        )
        witnesses = load_verified_numeric_actions(campaign_slug, character_slug)
        return all(witness in witnesses for witness in expected_witnesses)
    except Exception:
        return False


def prepare_native_creation_authorizations(
    definition: CharacterDefinition, initial_state: Mapping[str, Any],
    *, systems_service: Any, campaign_page_records: list[Any] | None,
) -> tuple[CharacterDefinition, tuple[dict[str, Any], ...], dict[str, str], str]:
    """Pre-mark only a new native DND baseline; the later audit is authority."""
    from .character_source_authority import build_reconciled_source_authority, numeric_target_values
    from .system_policy import is_dnd_5e_system
    if not is_dnd_5e_system(definition.system):
        raise SourceRepairError("Native numeric attestation applies only to DND-5E.")
    payload = deepcopy(definition.to_dict())
    source = deepcopy(dict(payload.get("source") or {}))
    if source.get("source_authorizations"):
        raise SourceRepairError("A new native Character cannot import source authorizations.")
    authority = build_reconciled_source_authority(
        definition=definition, state=dict(initial_state), state_revision=0,
        systems_service=systems_service,
        campaign_page_records=campaign_page_records,
    )
    values = numeric_target_values(definition, dict(initial_state))
    keys: list[tuple[str, str, str]] = []
    for ability in ("str", "dex", "con", "int", "wis", "cha"):
        keys.append(("field", f"stats.ability_scores.{ability}.score", "base"))
    keys.append(("field", "stats.proficiency_bonus", "final"))
    numeric_basis = getattr(authority, "numeric_basis_digest", lambda _target_id: None)
    if numeric_basis("stats.max_hp") is not None:
        keys.append(("field", "stats.max_hp", "final"))
    keys.extend(key for key in values if key[0] == "resource"
                and authority.resource_basis_digest(key[1]) is not None)
    keys.extend(key for key in values if key[0] == "spell_metric"
                and authority.numeric_basis_digest(key[1]) is not None)
    keys.extend(key for key in values if key[0] == "spell_choice"
                and authority.numeric_basis_digest(key[1]) is not None)
    if len(keys) != len(set(keys)) or len(keys) > 128:
        raise SourceRepairError("Native owner identities are ambiguous or too many.")
    # The target map cannot expose duplicates, so inspect raw owners too.
    resource_ids = [str(row.get("id") or "").strip() for row in definition.resource_templates if isinstance(row, Mapping)]
    if any(not value for value in resource_ids) or len(resource_ids) != len(set(resource_ids)):
        raise SourceRepairError("Native resource template identity is ambiguous.")
    slot_ids = [
        (str(row.get("slot_lane_id") or "").strip(), row.get("level"))
        for row in list(initial_state.get("spell_slots") or []) if isinstance(row, Mapping)
    ]
    if any(not lane or type(level) is not int or level < 1 for lane, level in slot_ids) or len(slot_ids) != len(set(slot_ids)):
        raise SourceRepairError("Native spell-slot identity is ambiguous.")
    pools = [row.get("faces") for row in list(dict(initial_state.get("hit_dice") or {}).get("pools") or []) if isinstance(row, Mapping)]
    if any(type(faces) is not int or faces < 1 for faces in pools) or len(pools) != len(set(pools)):
        raise SourceRepairError("Native Hit Die identity is ambiguous.")
    action_id = uuid4().hex
    markers = []
    numeric_basis_digests: dict[str, str] = {}
    for kind, target_id, metric in keys:
        if (kind, target_id, metric) not in values or values[(kind, target_id, metric)] is None:
            raise SourceRepairError("Native baseline input is incomplete.")
        markers.append(numeric_authorization_record(
            character_slug=definition.character_slug, target_kind=kind,
            target_id=target_id, metric=metric,
            raw_value=values[(kind, target_id, metric)],
            action_id=action_id, provenance="native_creation",
        ))
        if _native_source_bound_marker(markers[-1]):
            basis = (authority.resource_basis_digest(target_id) if kind == "resource"
                     else numeric_basis(target_id))
            if not _sha256_hex(basis):
                raise SourceRepairError("Native numeric source basis is unavailable.")
            numeric_basis_digests[target_id] = basis
    source["source_authorizations"] = deepcopy(markers)
    payload["source"] = source
    if not _sha256_hex(authority.source_snapshot_digest):
        raise SourceRepairError("Native source snapshot is unavailable.")
    return (CharacterDefinition.from_dict(payload), tuple(markers),
            numeric_basis_digests, authority.source_snapshot_digest)


def record_confirmed_native_creation_witness(
    *, expected_definition: CharacterDefinition, initial_state: Mapping[str, Any],
    readback_record: object, markers: tuple[dict[str, Any], ...],
    source_basis_digests: dict[str, str], source_snapshot_digest: str,
    load_current_source_context: Callable[[], tuple[Any, list[Any] | None]],
    actor_id: int, auth_store: object,
) -> bool:
    """Audit only after durable create/readback; failure leaves UNKNOWN."""
    from .character_source_authority import (build_reconciled_source_authority,
                                             numeric_target_values, numeric_value_digest)
    from .character_update_apply import canonical_digest
    if (type(actor_id) is not int or actor_id < 1
            or not isinstance(markers, tuple) or not 1 <= len(markers) <= 128
            or not isinstance(source_basis_digests, dict)
            or not _sha256_hex(source_snapshot_digest)
            or not callable(load_current_source_context)):
        return False
    readback_definition = getattr(readback_record, "definition", None)
    readback_state = getattr(getattr(readback_record, "state_record", None), "state", None)
    if not isinstance(readback_definition, CharacterDefinition) or not isinstance(readback_state, dict):
        return False
    if readback_definition.to_dict() != expected_definition.to_dict():
        return False
    expected_action = markers[0].get("action_id") if isinstance(markers[0], dict) else None
    if not isinstance(expected_action, str) or not expected_action:
        return False
    character_slug = readback_definition.character_slug
    persisted_markers = list(dict(readback_definition.source or {}).get("source_authorizations") or [])
    if any(not _valid_numeric_witness_marker(marker, character_slug, "native_creation")
           or marker["action_id"] != expected_action or marker not in persisted_markers
           or (marker["target_kind"] in {"resource", "spell_metric", "spell_choice"}
               and not _native_source_bound_marker(marker))
           for marker in markers):
        return False
    bound_ids = [marker["target_id"] for marker in markers if _native_source_bound_marker(marker)]
    if (len(bound_ids) != len(set(bound_ids))
            or set(source_basis_digests) != set(bound_ids)
            or not all(_sha256_hex(value) for value in source_basis_digests.values())):
        return False
    try:
        systems_service, campaign_page_records = load_current_source_context()
        readback_authority = build_reconciled_source_authority(
            definition=readback_definition, state=readback_state,
            state_revision=readback_record.state_record.revision,
            systems_service=systems_service,
            campaign_page_records=campaign_page_records,
        )
        if readback_authority.source_snapshot_digest != source_snapshot_digest:
            return False
        for marker in markers:
            if not _native_source_bound_marker(marker):
                continue
            target_id = marker["target_id"]
            current_basis = (
                readback_authority.resource_basis_digest(target_id)
                if marker["target_kind"] == "resource"
                else readback_authority.numeric_basis_digest(target_id)
            )
            if current_basis != source_basis_digests[target_id]:
                return False
    except Exception:
        return False
    values = numeric_target_values(readback_definition, readback_state)
    for marker in markers:
        key = (marker["target_kind"], marker["target_id"], marker["metric"])
        if key not in values or numeric_value_digest(values[key]) != marker["value_digest"]:
            return False
    campaign_slug = readback_definition.campaign_slug
    expected_witnesses = tuple(
        {"authorization": dict(marker),
         "source_basis_digest": source_basis_digests[marker["target_id"]]}
        if _native_source_bound_marker(marker) else dict(marker)
        for marker in markers
    )
    try:
        existing = get_db().execute(
            """SELECT metadata_json FROM auth_audit_log
               WHERE event_type = 'character_native_created'
                 AND campaign_slug = ? AND character_slug = ?""",
            (campaign_slug, character_slug),
        ).fetchall()
        for row in existing:
            metadata = json.loads(row["metadata_json"] or "{}")
            if metadata.get("action_id") == expected_action:
                witnesses = load_verified_numeric_actions(campaign_slug, character_slug)
                return all(witness in witnesses for witness in expected_witnesses)
        auth_store.insert_audit_event(
            event_type="character_native_created",
            actor_user_id=actor_id,
            campaign_slug=campaign_slug,
            character_slug=character_slug,
            metadata={
                "source": "native_create_confirmed",
                "numeric_actor_id": actor_id,
                "numeric_authorizations": list(markers),
                "action_id": expected_action,
                "definition_digest": canonical_digest(readback_definition.to_dict()),
                "source_basis_digests": dict(source_basis_digests),
                "source_snapshot_digest": source_snapshot_digest,
            },
            commit=True,
        )
        witnesses = load_verified_numeric_actions(campaign_slug, character_slug)
        return all(witness in witnesses for witness in expected_witnesses)
    except Exception:
        return False


def load_verified_manual_actions(campaign_slug: str, character_slug: str, *,
                                 connection: sqlite3.Connection | None = None,
                                 strict: bool = False) -> tuple[dict[str, Any], ...]:
    """Read only journal-produced, actor-bound audit witnesses for this Character."""
    try:
        rows = (connection if connection is not None else get_db()).execute(
            """SELECT actor_user_id, metadata_json FROM auth_audit_log
               WHERE event_type = 'character_update_applied'
                 AND campaign_slug = ? AND character_slug = ?
               ORDER BY id ASC""",
            (campaign_slug, character_slug),
        ).fetchall()
    except Exception:
        if strict:
            raise SourceRepairError("Manual audit proof is unavailable.")
        return ()  # Projection fails closed outside an available DB context.
    witnesses: list[dict[str, Any]] = []
    for row in rows:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
            authorization = metadata.get("manual_authorization")
            if not isinstance(authorization, dict) or set(authorization) != {
                "schema_version", "character_slug", "target_kind", "target_id",
                "metric", "action_id", "provenance", "target_digest",
            }:
                continue
            if (
                metadata.get("manager_action") != "manual_authorize"
                or metadata.get("action_id") != authorization["action_id"]
                or not isinstance(metadata.get("review_digest"), str)
                or len(metadata["review_digest"]) != 64
                or authorization["schema_version"] != 2
                or not _sha256_hex(authorization.get("target_digest"))
                or authorization["character_slug"] != character_slug
                or authorization["target_kind"] not in MANUAL_TARGETS
                or authorization["metric"] not in MANUAL_METRICS
                or authorization["provenance"] != "manager"
                or isinstance(row["actor_user_id"], bool)
                or not isinstance(row["actor_user_id"], int)
                or row["actor_user_id"] < 1
                or metadata.get("manual_actor_id") != row["actor_user_id"]
                or not isinstance(metadata.get("manual_authorized_at"), str)
            ):
                continue
            for field in ("target_id", "action_id"):
                _bounded(authorization[field], field)
            _bounded(metadata["manual_authorized_at"], "authorized_at")
            witnesses.append(dict(authorization))
        except (KeyError, TypeError, ValueError, SourceRepairError):
            continue
    return tuple(witnesses)
