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


class NativeAggregateWitness(dict):
    """Trusted request-local automatic-output origin; never a stored marker."""

    def __init__(self, witness: Mapping[str, Any], *, origin: tuple[Any, ...]):
        super().__init__(deepcopy(dict(witness)))
        self.origin = origin


class NativeSpellChoiceDecision(dict):
    """Request-local historical decision, issued only by the durable reader."""

    def __init__(self, *, target_id, row_digest, state, authorization, origin,
                 source_snapshot_digest=None):
        super().__init__(target_id=target_id, row_digest=row_digest, state=state,
            authorization=deepcopy(authorization))
        if source_snapshot_digest is not None:
            if not _sha256_hex(source_snapshot_digest):
                raise SourceRepairError("The historical choice source snapshot is malformed.")
            self["source_snapshot_digest"] = source_snapshot_digest
        self.origin = origin

    def matches(self, row, authorization=None):
        from .character_source_authority import numeric_value_digest
        from .character_spell_grants import native_class_choice_state
        try:
            return (isinstance(row, dict) and self.get("target_id") == f"spell_choice:{row.get('id')}"
                and self.get("row_digest") == numeric_value_digest(row)
                and self.get("state") == native_class_choice_state(row)
                and self.get("state") in {"active", "retired"}
                and (authorization is None or self.get("authorization") == authorization)
                and isinstance(self.origin, tuple) and len(self.origin) == 5)
        except (TypeError, ValueError):
            return False


def action_witness_comparison(witnesses):
    """Detached equality data, never a witness, cache value or source authority.

    Audit readers return plain mappings or these three exact private wrappers.
    Their complete origin is part of freshness, including migration receipts.
    Keep generic source freeze/thaw strict; no trusted object is reconstructed.
    """
    from .character_source_reads import freeze, SourceReadConflict
    from .character_spell_grants import NativeGrantCustody
    from .character_spell_reconstruction import NativeSpellReconstructionFact
    from .character_language_electives import NativeElectiveDecision, PendingElectiveOutcome

    if type(witnesses) is not tuple:
        raise SourceReadConflict("Action witness sequence has an unsupported type.")
    compared = []
    for witness in witnesses:
        kind = type(witness)
        if kind is dict:
            compared.append(("plain", freeze(witness)))
        elif kind in (NativeAggregateWitness, NativeSpellChoiceDecision, NativeGrantCustody, NativeSpellReconstructionFact, NativeElectiveDecision, PendingElectiveOutcome):
            if set(vars(witness)) != {"origin"}:
                raise SourceReadConflict("Action witness provenance envelope is unavailable.")
            compared.append(("trusted", kind, freeze(dict.copy(witness)), freeze(witness.origin)))
        else:
            raise SourceReadConflict("Action witness has an unsupported type.")
    return tuple(compared)


def require_confirmed_native_grant_custody(prior_record, *, connection=None):
    """Authenticate the original committed model, independently of its benefits."""
    from .character_spell_grants import (has_native_grants, validate_native_grant_model,
        is_confirmed_native_grant_custody, canonical_digest)
    if not has_native_grants(prior_record.definition):
        return ()
    validate_native_grant_model(prior_record.definition)
    db = connection if connection is not None else get_db()
    from .committed_publication import current
    from .committed_source_store import _decode_mapping
    actual = current(prior_record.definition.campaign_slug, "character",
        prior_record.definition.character_slug, connection=db)
    if (actual is None or type(prior_record.committed_revision) is not int
            or actual["revision"] != prior_record.committed_revision
            or canonical_digest(CharacterDefinition.from_dict(_decode_mapping(actual["primary_bytes"])).to_dict())
               != canonical_digest(prior_record.definition.to_dict())):
        raise SourceRepairError("The original native grant generation changed.")
    witnesses = load_verified_numeric_actions(prior_record.definition.campaign_slug,
        prior_record.definition.character_slug, connection=db, strict=True)
    if not any(is_confirmed_native_grant_custody(w, prior_record.definition) for w in witnesses):
        raise SourceRepairError("The original native grant model needs independently confirmed custody.")
    return witnesses


def _decision_generation(connection, campaign, character, revision, digest, actor=None):
    from .character_native_requalification import _generation
    if type(revision) is not int or revision < 1 or not _sha256_hex(digest):
        raise SourceRepairError("The class choice generation is unavailable.")
    row = connection.execute("SELECT actor_user_id FROM committed_source_generations "
        "WHERE campaign_slug=? AND object_kind='character' AND object_ref=? AND revision=?",
        (campaign, character, revision)).fetchone()
    if (row is None or type(row["actor_user_id"]) is not int or row["actor_user_id"] < 1
            or actor is not None and row["actor_user_id"] != actor):
        raise SourceRepairError("The class choice generation actor changed.")
    return _generation(connection, campaign, character, digest, row["actor_user_id"], revision=revision)


def _verified_native_spell_choice_decisions(connection, campaign, character, audit_row,
        metadata, prior_witnesses):
    """Join real selected/leveled events; old numeric batches are not decisions."""
    from .character_spell_grants import (native_class_choice_rows, native_class_choice_state,
        CLASS_CHOICE_STATE_FIELD, grant_model_digest)
    from .character_source_authority import (numeric_value_digest, numeric_target_owner_digest,
        native_spell_choice_birth_is_absent, ordinary_native_spell_choice_state)
    proof = metadata.get("spell_choice_decisions")
    if proof is None:
        return ()
    required = {"schema_version", "event_type", "actor_id", "prior_generation", "generation",
        "prior_definition_digest", "definition_digest", "prior_state_revision", "state_revision",
        "prior_state_digest", "state_digest", "prior_model_digest", "model_digest", "decisions"}
    if (not isinstance(proof, dict) or set(proof) != required or type(proof["schema_version"]) is not int
            or proof["schema_version"] != 1 or proof["event_type"] != audit_row["event_type"]
            or audit_row["event_type"] not in {"character_native_spell_selected", "character_native_leveled"}
            or type(proof["actor_id"]) is not int or proof["actor_id"] != audit_row["actor_user_id"]
            or proof["actor_id"] != metadata.get("numeric_actor_id")
            or proof["definition_digest"] != metadata.get("definition_digest")
            or type(proof["prior_state_revision"]) is not int or proof["prior_state_revision"] < 0
            or type(proof["state_revision"]) is not int
            or proof["state_revision"] not in {proof["prior_state_revision"], proof["prior_state_revision"] + 1}
            or proof["prior_state_revision"] != metadata.get("prior_state_revision")
            or proof["state_revision"] != metadata.get("state_revision")
            or any(not _sha256_hex(proof[key]) for key in ("prior_state_digest", "state_digest"))
            or type(proof["decisions"]) is not list or len(proof["decisions"]) > 128):
        raise SourceRepairError("The class choice decision audit is malformed.")
    before_payload, before_generation = _decision_generation(connection, campaign, character,
        proof["prior_generation"], proof["prior_definition_digest"])
    after_payload, after_generation = _decision_generation(connection, campaign, character,
        proof["generation"], proof["definition_digest"], proof["actor_id"])
    if after_generation["revision"] != before_generation["revision"] + 1:
        raise SourceRepairError("The class choice decision skipped its actual generation.")
    before, after = CharacterDefinition.from_dict(before_payload), CharacterDefinition.from_dict(after_payload)
    if (grant_model_digest(before) != proof["prior_model_digest"]
            or grant_model_digest(after) != proof["model_digest"]):
        raise SourceRepairError("The class choice grant frame changed.")
    old_rows, new_rows = native_class_choice_rows(before), native_class_choice_rows(after)
    from .character_spell_grants import is_confirmed_native_grant_custody
    batch = metadata.get("numeric_authorizations", [])
    seen, result = set(), []
    fields = {"spell_id", "operation", "before_state", "after_state", "before_row_digest", "after_row_digest",
        "prior_authorization", "prior_owner_digest", "prior_source_basis_digest"}
    for decision in proof["decisions"]:
        if not isinstance(decision, dict) or set(decision) != fields:
            raise SourceRepairError("The class choice decision target is malformed.")
        spell_id = decision["spell_id"]
        old, new = old_rows.get(spell_id), new_rows.get(spell_id)
        if spell_id in seen or new is None:
            raise SourceRepairError("The class choice decision target is ambiguous.")
        seen.add(spell_id)
        birth = old is None
        if birth and (decision["operation"] != "select"
                or not native_spell_choice_birth_is_absent(before, new, candidate_definition=after)):
            raise SourceRepairError("The class choice birth has unresolved original observations.")
        if birth and (not any(is_confirmed_native_grant_custody(w, before) for w in prior_witnesses)
                or audit_row["event_type"] == "character_native_leveled"
                    and not isinstance(metadata.get("native_grant_confirmation"), dict)
                or audit_row["event_type"] == "character_native_spell_selected"
                    and grant_model_digest(before) != grant_model_digest(after)):
            raise SourceRepairError("The class choice birth lacks its actual native acquisition custody.")
        old_state = native_class_choice_state(old) if old is not None else None
        new_state = native_class_choice_state(new)
        left, right = deepcopy(old) if old is not None else {}, deepcopy(new)
        left.pop(CLASS_CHOICE_STATE_FIELD, None)
        right.pop(CLASS_CHOICE_STATE_FIELD, None)
        from .character_spell_reconstruction import NativeSpellReconstructionFact, _marks as checkpoint_marks
        available_facts = [fact for fact in prior_witnesses if type(fact) is NativeSpellReconstructionFact
            and fact.matches(old) and fact.origin[:2] == (campaign, character)
            and fact.get("role") == "available" and fact.get("spell_level", 0) > 0]
        available_preparation = bool(decision["operation"] == "prepare_available" and old is not None
            and old_state is None and new_state == "active" and available_facts
            and left != right and {key for key in set(left) | set(right) if (key in left) != (key in right) or left.get(key) != right.get(key)} <= {"mark", "prepared", "is_prepared"}
            and checkpoint_marks(old)[1] is False and checkpoint_marks(new)[1] is True)
        preparation = bool(decision["operation"] == "prepare" and old_state == new_state and new_state is not None
            and left != right and {key for key in set(left) | set(right) if (key in left) != (key in right) or left.get(key) != right.get(key)} <= {"mark", "prepared", "is_prepared"})
        continuing = bool(decision["operation"] == "continue" and old_state == new_state and new_state is not None and old == new)
        if ((left != right and not preparation and not available_preparation and not birth) or old_state != decision["before_state"] or new_state != decision["after_state"]
                or new_state not in {"active", "retired"} or new_state == old_state and not (preparation or continuing)
                or numeric_value_digest(old) != decision["before_row_digest"]
                or numeric_value_digest(new) != decision["after_row_digest"]):
            raise SourceRepairError("The class choice decision changed historical observations.")
        target = f"spell_choice:{spell_id}"
        old_markers = [m for m in before.source.get("source_authorizations", []) if isinstance(m, dict)
            and (m.get("target_kind"), m.get("target_id"), m.get("metric")) == ("spell_choice", target, "selection")]
        prior_marker = decision["prior_authorization"]
        if available_preparation:
            before_classes = {row.get("row_id"): row for row in before.profile.get("classes", []) if isinstance(row, dict)}
            after_classes = {row.get("row_id"): row for row in after.profile.get("classes", []) if isinstance(row, dict)}
            owner = old.get("class_row_id")
            if (owner != new.get("class_row_id") or owner not in before_classes or owner not in after_classes
                    or before_classes[owner].get("systems_ref") != after_classes[owner].get("systems_ref")
                    or len(old_markers) > 1 or prior_marker != (old_markers[0] if old_markers else None)
                    or decision["prior_owner_digest"] != (numeric_target_owner_digest(before, {}, "spell_choice", target, "selection") if old_markers else None)):
                raise SourceRepairError("The prepared-list continuation changed its confirmed owner or observation.")
        elif decision["operation"] in {"retire", "reactivate", "prepare", "continue"}:
            trusted = [w for w in prior_witnesses if isinstance(w, dict)
                and w.get("authorization", w) == prior_marker]
            if (len(old_markers) != 1 or old_markers[0] != prior_marker or not trusted
                    or prior_marker.get("value_digest") != numeric_value_digest(old)
                    or numeric_target_owner_digest(before, {}, "spell_choice", target, "selection") != decision["prior_owner_digest"]):
                raise SourceRepairError("The class choice decision lacks independent prior choice custody.")
            if old_state is not None and ordinary_native_spell_choice_state(old, prior_marker,
                    verified_numeric_actions=prior_witnesses) != old_state:
                raise SourceRepairError("The prior typed class choice decision is unconfirmed.")
            if (decision["operation"] == "retire" and (old_state == "retired" or new_state != "retired")
                    or decision["operation"] == "reactivate" and (old_state != "retired" or new_state != "active")):
                raise SourceRepairError("The class choice decision operation changed.")
            if decision["operation"] == "retire" and not any(
                    isinstance(w, dict) and w.get("authorization", w) == prior_marker
                    and w.get("source_basis_digest") == decision["prior_source_basis_digest"] for w in trusted):
                raise SourceRepairError("The retiring class choice lacks its actual current-source witness.")
        elif (decision["operation"] != "select" or old_state is not None or new_state != "active"
                or prior_marker is not None or old_markers
                or decision["prior_owner_digest"] is not None or decision["prior_source_basis_digest"] is not None):
            raise SourceRepairError("The fresh class choice has unsupported prior history.")
        current = [m for m in after.source.get("source_authorizations", []) if isinstance(m, dict)
            and (m.get("target_kind"), m.get("target_id"), m.get("metric")) == ("spell_choice", target, "selection")]
        provenance = "native_spell_choice" if audit_row["event_type"] == "character_native_spell_selected" else "native_level_up"
        if (len(current) != 1 or current[0] not in batch
                or not _valid_numeric_witness_marker(current[0], character, provenance)
                or current[0].get("value_digest") != numeric_value_digest(new)
                or current[0].get("action_id") != metadata.get("action_id")
                or not _sha256_hex(dict(metadata.get("source_basis_digests") or {}).get(target))):
            raise SourceRepairError("The published class choice decision marker differs from its event.")
        result.append(NativeSpellChoiceDecision(target_id=target, row_digest=numeric_value_digest(new),
            state=new_state, authorization=current[0],
            origin=(campaign, character, audit_row["id"], proof["actor_id"], proof["generation"]),
            source_snapshot_digest=(metadata.get("source_snapshot_digest")
                if _sha256_hex(metadata.get("source_snapshot_digest")) else None)))
        from .character_spell_reconstruction import carry_preparation_role
        role_fact = carry_preparation_role(before, after, spell_id, prior_witnesses,
            origin=(campaign, character, audit_row["id"], proof["actor_id"], proof["generation"]))
        if role_fact is not None:
            result.append(role_fact)
    def markers_for(model, spell_id):
        return [m for m in model.source.get("source_authorizations", []) if isinstance(m, dict)
            and (m.get("target_kind"), m.get("target_id"), m.get("metric")) == ("spell_choice", f"spell_choice:{spell_id}", "selection")]
    changed = {spell_id for spell_id in set(old_rows) | set(new_rows)
        if (spell_id in old_rows and CLASS_CHOICE_STATE_FIELD in old_rows[spell_id]
            or spell_id in new_rows and CLASS_CHOICE_STATE_FIELD in new_rows[spell_id])
        and (old_rows.get(spell_id) != new_rows.get(spell_id)
            or markers_for(before, spell_id) != markers_for(after, spell_id))}
    if changed != seen:
        raise SourceRepairError("The class choice decision audit omitted a changed target.")
    return tuple(result)


def _verified_native_creation_spell_choices(connection, campaign, character, audit_row,
        metadata, current_custody):
    """Derive birth decisions from the actual initial receipt, never generation zero."""
    from .character_spell_grants import (native_class_choice_rows, native_class_choice_state,
        CLASS_CHOICE_STATE_FIELD, is_confirmed_native_grant_custody)
    from .character_source_authority import numeric_value_digest
    receipt = metadata.get("native_grant_confirmation")
    if receipt is None:
        return ()  # Older generic numeric events do not prove ordinary acquisition.
    payload, generation = _decision_generation(connection, campaign, character,
        receipt.get("generation"), metadata.get("definition_digest"), audit_row["actor_user_id"])
    definition = CharacterDefinition.from_dict(payload)
    if (generation["revision"] != 1 or receipt.get("event_type") != "character_native_created"
            or not any(is_confirmed_native_grant_custody(w, definition) for w in current_custody)):
        raise SourceRepairError("The ordinary creation birth lacks its actual initial receipt.")
    rows = native_class_choice_rows(definition)
    batch = metadata["numeric_authorizations"]
    result = []
    for spell_id, raw in rows.items():
        if CLASS_CHOICE_STATE_FIELD not in raw:
            continue
        target = f"spell_choice:{spell_id}"
        current = [m for m in definition.source.get("source_authorizations", []) if isinstance(m, dict)
            and (m.get("target_kind"), m.get("target_id"), m.get("metric")) == ("spell_choice", target, "selection")]
        if (native_class_choice_state(raw) != "active" or len(current) != 1 or current[0] not in batch
                or current[0].get("schema_version") != 2
                or not _valid_numeric_witness_marker(current[0], character, "native_creation")
                or current[0].get("value_digest") != numeric_value_digest(raw)
                or current[0].get("action_id") != metadata.get("action_id")
                or not _sha256_hex(metadata["source_basis_digests"].get(target))):
            raise SourceRepairError("The ordinary creation birth differs from its exact initial marker.")
        result.append(NativeSpellChoiceDecision(target_id=target, row_digest=numeric_value_digest(raw),
            state="active", authorization=current[0],
            origin=(campaign, character, audit_row["id"], audit_row["actor_user_id"], 1),
            source_snapshot_digest=(metadata.get("source_snapshot_digest")
                if _sha256_hex(metadata.get("source_snapshot_digest")) else None)))
    return tuple(result)


def _native_aggregate_origins(db, campaign_slug, character_slug, row, metadata, witnesses, *, prior_witnesses=(), require_complete=False):
    """Keep exact historical producer custody separate from current arithmetic."""
    from .character_source_authority import NATIVE_BASELINE_FIELDS, numeric_target_values, numeric_value_digest
    from .character_native_requalification import _generation
    automatic = (row["event_type"] in {"character_native_created", "character_native_leveled"}
                 or row["event_type"] == "character_update_applied" and metadata.get("manager_action") in {"native_requalify", "native_reconstruct"})
    if not automatic:
        return witnesses
    digest = (metadata.get("published_definition_digest") if row["event_type"] == "character_update_applied"
              else metadata.get("definition_digest"))
    try:
        if row["event_type"] == "character_update_applied":
            revision = metadata.get("published_revision")
            if type(revision) is not int or revision < 1:
                raise ValueError("Native currentness publication revision is unavailable.")
            payload, generation = _generation(
                db, campaign_slug, character_slug, digest, row["actor_user_id"], revision=revision,
            )
            aliases = ((generation["revision"], generation["primary_sha256"]),)
        else:
            # These historical audit formats have no publication revision. An
            # identical later publication must not erase their exact content
            # custody or pretend to identify one original generation.
            candidates = [dict(candidate) for candidate in db.execute(
                "SELECT revision,primary_bytes,primary_sha256,actor_user_id,tombstone "
                "FROM committed_source_generations WHERE campaign_slug=? "
                "AND object_kind='character' AND object_ref=? AND actor_user_id=? "
                "AND tombstone=0 ORDER BY revision LIMIT 513",
                (campaign_slug, character_slug, row["actor_user_id"]),
            ).fetchall()]
            if len(candidates) > 512:
                raise ValueError("Native generation aliases need a separately bounded review.")
            matches = []
            for candidate in candidates:
                if type(candidate.get("revision")) is not int or candidate["revision"] < 1:
                    continue
                try:
                    current_payload, receipt = _generation(
                        db, campaign_slug, character_slug, digest, row["actor_user_id"], index=[candidate],
                    )
                except (TypeError, ValueError, KeyError):
                    continue
                matches.append((current_payload, receipt))
            contents = {json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
                        for value, _receipt in matches}
            if len(contents) != 1:
                raise ValueError("Native generation alias content is ambiguous.")
            # Every receipt binds the same complete content, marker/value and
            # class/native-history frame checked below. No first/latest claim.
            payload = json.loads(contents.pop())
            aliases = tuple(sorted((receipt["revision"], receipt["primary_sha256"])
                                   for _value, receipt in matches))
            generation = {"aliases": aliases}
        historical = CharacterDefinition.from_dict(payload)
        values = numeric_target_values(historical, {})
        stored = list(dict(historical.source or {}).get("source_authorizations") or [])
    except (TypeError, ValueError, KeyError):
        values, stored, generation = {}, [], None
    result = []
    for witness in witnesses:
        marker = witness.get("authorization", witness)
        key = (marker.get("target_kind"), marker.get("target_id"), marker.get("metric"))
        recipe_hp = (key == ("field", "stats.max_hp", "final") and generation is not None
                     and isinstance(dict(historical.source.get("native_progression") or {}).get("hp_recipe"), dict))
        if key[0] != "field" or (key[1] not in NATIVE_BASELINE_FIELDS and not recipe_hp) or key[2] != "final":
            result.append(witness)
        elif (generation is not None and marker in stored and key in values
              and numeric_value_digest(values[key]) == marker.get("value_digest")):
            envelope = witness if "authorization" in witness else {"authorization": witness}
            result.append(NativeAggregateWitness(envelope, origin=(
                metadata.get("manager_action") if row["event_type"] == "character_update_applied" else marker["provenance"],
                row["id"], row["actor_user_id"], hashlib.sha256(row["metadata_json"].encode()).hexdigest(),
                aliases, digest,
                hashlib.sha256(json.dumps({"classes": historical.profile.get("classes"),
                    "native_progression": dict(historical.source or {}).get("native_progression")},
                    sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest(),
            )))
    # Finalizing the original batch is one-for-one. Check that invariant before
    # extending it with independently recovered acquisition custody, so added
    # custody cannot hide a lost original witness or reject a complete event.
    if require_complete and len(result) != len(witnesses):
        raise SourceRepairError("The complete class choice event could not be finalized.")
    if generation is not None:
        from .character_feature_proficiency_grants import recovered_native_custody
        result.extend(recovered_native_custody(db, historical, aliases, row, metadata, prior_witnesses))
    return result


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
    connection: Any | None = None,
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
        if family == "feature":
            from .character_feature_composition import CLAIM_FIELD
            row.pop(CLAIM_FIELD, None)
    else:
        if str(getattr(source_record, "entry_key", "") or "").strip() != source_value:
            raise SourceRepairError("The Systems entry identity changed.")
        entry_type = str(getattr(source_record, "entry_type", "") or "").strip()
        slug = str(getattr(source_record, "slug", "") or "").strip()
        if not entry_type or not slug:
            raise SourceRepairError("The Systems entry is incomplete.")
        prior_systems = bool(row.get("systems_ref"))
        prior_page = deepcopy(row.get("page_ref"))
        row["systems_ref"] = {
            "entry_key": source_value,
            "entry_type": entry_type,
            "slug": slug,
            "title": str(getattr(source_record, "title", "") or "").strip(),
            "source_id": str(getattr(source_record, "source_id", "") or "").strip(),
        }
        row.pop("page_ref", None)
        if family == "feature":
            from .character_feature_composition import selected_replacement_claim, CLAIM_FIELD
            claim = selected_replacement_claim(source_record,
                class_row_id=str(row.get("class_row_id") or ""))
            if claim is None:
                row.pop(CLAIM_FIELD, None)
            else:
                row[CLAIM_FIELD] = claim
        if family == "item" and prior_systems and prior_page and connection is not None:
            from .committed_character_publication import (
                _create_source_proof, _exact_page_link, _exact_systems_link,
            )
            from .committed_publication import CommittedSourceConflict

            owner = f"definition.equipment_catalog[{matches[0]}]"
            try:
                page_link = _exact_page_link(prior_page, owner + ".page_ref", "item_context")
                systems_link = _exact_systems_link(row["systems_ref"], owner + ".systems_ref", "item")
                _create_source_proof(
                    str(definition.get("campaign_slug") or ""), (page_link,), (systems_link,),
                    connection=connection,
                )
            except (CommittedSourceConflict, TypeError, ValueError):
                pass
            else:
                row["page_ref"] = prior_page
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
    if provenance not in {"manager", "native_creation", "native_level_up", "native_spell_choice", "native_reconstruction", "native_requalification", "native_elective_decision"}:
        raise SourceRepairError("Unsupported numeric authorization provenance.")
    if provenance == "native_elective_decision" and not (target_kind == "proficiency"
            and metric == "grant" and type(target_id) is str and target_id.startswith("proficiencies.languages.")):
        raise SourceRepairError("An elective decision can authorize only its current language grants.")
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


def _grant_receipt_error(message):
    raise SourceRepairError(message)


def _strict_grant_audit_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _grant_receipt_error("Duplicate audit metadata key.")
            result[key] = value
        return result
    def constant(_value):
        _grant_receipt_error("Nonfinite audit metadata value.")
    if not isinstance(raw, str):
        _grant_receipt_error("Audit metadata is unavailable.")
    parsed = json.loads(raw, object_pairs_hook=unique, parse_constant=constant)
    if not isinstance(parsed, dict):
        _grant_receipt_error("Audit metadata must be an object.")
    return parsed


def _grant_context_from_receipt(intent):
    from .character_spell_grants import AcquisitionContext
    keys = {"schema_version", "intent_id", "campaign_slug", "system", "actor_id",
            "mode", "prior_revision", "prior_state_revision", "prior_definition_digest"}
    if (not isinstance(intent, dict) or set(intent) != keys
            or type(intent.get("schema_version")) is not int or intent["schema_version"] != 1
            or intent.get("system") != "DND-5E"
            or not _sha256_hex(intent.get("intent_id"))
            or type(intent.get("actor_id")) is not int or intent["actor_id"] < 1
            or not isinstance(intent.get("campaign_slug"), str) or not intent["campaign_slug"]
            or intent.get("mode") not in {"create", "progression"}):
        _grant_receipt_error("Confirmed acquisition intent is malformed.")
    if intent["mode"] == "create":
        if any(intent[key] is not None for key in (
                "prior_revision", "prior_state_revision", "prior_definition_digest")):
            _grant_receipt_error("Creation borrowed progression custody.")
    elif (type(intent["prior_revision"]) is not int or intent["prior_revision"] < 1
            or type(intent["prior_state_revision"]) is not int or intent["prior_state_revision"] < 1
            or not _sha256_hex(intent["prior_definition_digest"])):
        _grant_receipt_error("Progression prior custody is malformed.")
    # Historical reconstruction deliberately has no live token. It is NOT an
    # authorization to submit, refresh or replay the original acquisition.
    return AcquisitionContext(intent["intent_id"], intent["campaign_slug"],
        intent["actor_id"], intent["mode"], intent["prior_revision"],
        intent["prior_state_revision"], intent["prior_definition_digest"])


def _recheck_same_submitted_grant_intent(context):
    from flask import current_app
    from itsdangerous import URLSafeTimedSerializer
    from .character_spell_grants import (AcquisitionContext, ACQUISITION_SALT,
                                         ACQUISITION_MAX_AGE)
    if not isinstance(context, AcquisitionContext):
        _grant_receipt_error("The authenticated submitted intent is unavailable.")
    _grant_context_from_receipt(context.to_dict())
    if (context.admission_validated is not True
            or type(context.signed_issued_at) is not int
            or type(context.admitted_at) is not int
            or not 0 <= context.admitted_at - context.signed_issued_at <= ACQUISITION_MAX_AGE):
        _grant_receipt_error("Request-local timely acquisition admission is unavailable.")
    token = getattr(context, "validated_token", "")
    if not isinstance(token, str) or not token or len(token.encode("utf-8")) > 8192:
        _grant_receipt_error("The same submitted acquisition token is unavailable.")
    signer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=ACQUISITION_SALT)
    payload, signed_at = signer.loads(token, max_age=None, return_timestamp=True)
    if (not isinstance(payload, dict) or set(payload) != set(context.to_dict())
            or int(signed_at.timestamp()) != context.signed_issued_at
            or json.dumps(payload, sort_keys=True, allow_nan=False)
            != json.dumps(context.to_dict(), sort_keys=True, allow_nan=False)):
        _grant_receipt_error("Submitted acquisition intent changed.")


def _receipt_prior_generation(connection, campaign, character, context):
    from .character_native_requalification import _generation
    if context.mode == "create":
        return None
    row = connection.execute(
        "SELECT actor_user_id FROM committed_source_generations "
        "WHERE campaign_slug=? AND object_kind='character' AND object_ref=? AND revision=?",
        (campaign, character, context.prior_revision)).fetchone()
    if row is None or type(row["actor_user_id"]) is not int:
        _grant_receipt_error("Actual prior generation is unavailable.")
    payload, _receipt = _generation(connection, campaign, character,
        context.prior_definition_digest, row["actor_user_id"], revision=context.prior_revision)
    return CharacterDefinition.from_dict(payload)


def _native_grant_confirmation_receipt(expected_definition, readback_record,
        acquisition_context, actor_id, systems_service, *, prior_definition=None,
        prior_custody=(), expected_event):
    from .character_native_requalification import _generation
    from .character_reconstruction_authority import capacity_frame
    from .character_spell_grants import (has_native_grants, canonical_digest,
        grant_model_digest, inspect_native_grant_proposal, is_confirmed_native_grant_custody)
    if not has_native_grants(expected_definition):
        # Both containers are genuinely absent. Routes may carry a new context
        # for ordinary nonmigrated progression; its existing numeric audit and
        # default metadata remain unchanged. Presence of EITHER container makes
        # has_native_grants True and therefore enters strict model validation.
        return None
    if expected_event not in {"character_native_created", "character_native_leveled"}:
        _grant_receipt_error("This event cannot confirm a native acquisition.")
    _recheck_same_submitted_grant_intent(acquisition_context)
    if (type(actor_id) is not int or actor_id < 1
            or type(acquisition_context.actor_id) is not int
            or acquisition_context.actor_id != actor_id
            or acquisition_context.campaign_slug != expected_definition.campaign_slug
            or acquisition_context.mode != (
                "create" if expected_event == "character_native_created" else "progression")):
        _grant_receipt_error("Acquisition actor or event changed.")
    persisted = getattr(readback_record, "definition", None)
    state_record = getattr(readback_record, "state_record", None)
    state = getattr(state_record, "state", None)
    state_revision = getattr(state_record, "revision", None)
    generation = getattr(readback_record, "committed_revision", None)
    if (not isinstance(persisted, CharacterDefinition) or not isinstance(state, dict)
            or type(state_revision) is not int or state_revision < 1
            or type(generation) is not int or generation < 1
            or canonical_digest(persisted.to_dict()) != canonical_digest(expected_definition.to_dict())):
        _grant_receipt_error("Actual committed readback is unavailable or changed.")
    if acquisition_context.mode == "create" and generation != 1:
        _grant_receipt_error("Native creation must confirm its actual initial generation.")
    digest = canonical_digest(persisted.to_dict())
    db = get_db()
    payload, receipt = _generation(db, persisted.campaign_slug, persisted.character_slug,
        digest, actor_id, revision=generation)
    if type(receipt["revision"]) is not int or receipt["revision"] != generation:
        _grant_receipt_error("Actual generation identity changed type or value.")
    actual = CharacterDefinition.from_dict(payload)
    if canonical_digest(actual.to_dict()) != canonical_digest(persisted.to_dict()):
        _grant_receipt_error("Readback differs from the actual committed generation.")
    if (canonical_digest(actual.source.get("native_acquisitions", {}).get("intent"))
            != canonical_digest(acquisition_context.to_dict())):
        _grant_receipt_error("Committed model differs from the same submitted intent.")
    actual_prior = _receipt_prior_generation(db, actual.campaign_slug,
        actual.character_slug, acquisition_context)
    if acquisition_context.mode == "progression":
        if (prior_definition is None
                or canonical_digest(actual_prior.to_dict()) != canonical_digest(prior_definition.to_dict())
                or type(acquisition_context.prior_revision) is not int
                or type(acquisition_context.prior_state_revision) is not int
                or generation != acquisition_context.prior_revision + 1
                or state_revision != acquisition_context.prior_state_revision + 1
                or not any(is_confirmed_native_grant_custody(witness, actual_prior)
                           for witness in prior_custody)):
            _grant_receipt_error("Progression did not retain authenticated actual prior custody.")
    # This replays the source/acquisition compiler independently after durable
    # readback. It gives no pending witness to active SourceAuthority.
    draft = inspect_native_grant_proposal(actual, systems_service,
        acquisition_context=acquisition_context, actor_id=actor_id,
        prior_definition=actual_prior, prior_custody=prior_custody)
    return {"schema_version": 1, "event_type": expected_event,
        "actor_id": actor_id, "generation": receipt["revision"],
        "definition_digest": digest, "state_revision": state_revision,
        "model_digest": grant_model_digest(actual),
        "intent": acquisition_context.to_dict(),
        "source_facts_digest": draft.source_digest,
        "capacity_frame": capacity_frame(state)}


def _native_grant_audit_metadata(metadata, grant_receipt):
    from .runtime_security import sanitize_audit_metadata
    from .character_spell_grants import canonical_digest
    if grant_receipt is None and "spell_choice_decisions" not in metadata:
        return metadata  # historical/nonmigrated path unchanged
    payload = deepcopy(metadata)
    if grant_receipt is not None:
        payload["native_grant_confirmation"] = deepcopy(grant_receipt)
    sanitized = sanitize_audit_metadata(payload)
    encoded = json.dumps(sanitized, sort_keys=True, allow_nan=False).encode("utf-8")
    if canonical_digest(sanitized) != canonical_digest(payload) or len(encoded) > 65536:
        _grant_receipt_error("Complete native grant audit cannot be stored losslessly.")
    return payload


def prepare_native_spell_choice_audit_metadata(prior_record, definition, state, *, actor_id,
        markers, source_snapshot_digest, source_basis_digests, event_type, systems_service,
        campaign_page_records=None, acquisition_context=None, advancement_intent=None,
        state_revision=None, generation=None):
    """Build the complete existing-event payload for admission and actual readback.

    Before publication the generation/state arguments are prospective, never a
    custody witness. The recorder and durable reader separately join actual bytes.
    """
    from .character_source_authority import (build_reconciled_source_authority,
        validate_native_spell_choice_decision_transition, numeric_value_digest)
    from .character_spell_grants import (canonical_digest, grant_model_digest,
        has_native_grants, inspect_native_grant_proposal, is_confirmed_native_grant_custody)
    from .character_reconstruction_authority import capacity_frame
    if event_type not in {"character_native_spell_selected", "character_native_leveled"}:
        raise SourceRepairError("The class choice decision event is unsupported.")
    if type(actor_id) is not int or actor_id < 1 or prior_record is None:
        raise SourceRepairError("The actual class choice actor and prior record are required.")
    campaign, character = definition.campaign_slug, definition.character_slug
    if (prior_record.definition.campaign_slug, prior_record.definition.character_slug) != (campaign, character):
        raise SourceRepairError("The class choice decision target changed.")
    numeric = load_verified_numeric_actions(campaign, character, strict=True)
    manual = load_verified_manual_actions(campaign, character, strict=True)
    prior_authority = build_reconciled_source_authority(definition=prior_record.definition,
        state=prior_record.state_record.state, state_revision=prior_record.state_record.revision,
        systems_service=systems_service, campaign_page_records=campaign_page_records,
        verified_numeric_actions=numeric, verified_manual_actions=manual)
    leveled = event_type == "character_native_leveled"
    if leveled and advancement_intent is not None and not advancement_intent.matches_resource_readback(prior_record.definition, definition):
        raise SourceRepairError("The actual validated level-up decision changed.")
    decisions = validate_native_spell_choice_decision_transition(prior_record, definition, state,
        prior_authority=prior_authority, actor_id=actor_id, operation_kind="interactive_update",
        allow_management=not leveled, allow_progression=leveled, systems_service=systems_service,
        campaign_page_records=campaign_page_records)
    if not markers or not isinstance(markers, tuple) or len(markers) > 128:
        raise SourceRepairError("The native selection marker batch is unavailable.")
    action_ids = {m.get("action_id") for m in markers if isinstance(m, dict)}
    if len(action_ids) != 1 or None in action_ids:
        raise SourceRepairError("The native selection action is ambiguous.")
    state_revision = (prior_record.state_record.revision + int(state != prior_record.state_record.state)
        if state_revision is None else state_revision)
    generation = prior_record.committed_revision + 1 if generation is None else generation
    metadata = {"source": "native_level_up_confirmed" if leveled else "native_spell_choice_confirmed",
        "numeric_actor_id": actor_id, "numeric_authorizations": list(markers),
        "action_id": next(iter(action_ids)), "definition_digest": canonical_digest(definition.to_dict()),
        "prior_state_revision": prior_record.state_record.revision, "state_revision": state_revision,
        "source_snapshot_digest": source_snapshot_digest, "source_basis_digests": dict(source_basis_digests)}
    from .character_spell_grants import CLASS_CHOICE_STATE_FIELD
    if decisions or any(CLASS_CHOICE_STATE_FIELD in row for model in (prior_record.definition, definition)
            for row in model.spellcasting.get("spells", []) if isinstance(row, dict)):
        metadata["spell_choice_decisions"] = {"schema_version": 1, "event_type": event_type,
            "actor_id": actor_id, "prior_generation": prior_record.committed_revision, "generation": generation,
            "prior_definition_digest": canonical_digest(prior_record.definition.to_dict()),
            "definition_digest": canonical_digest(definition.to_dict()),
            "prior_state_revision": prior_record.state_record.revision, "state_revision": state_revision,
            "prior_state_digest": numeric_value_digest(prior_record.state_record.state),
            "state_digest": numeric_value_digest(state), "prior_model_digest": grant_model_digest(prior_record.definition),
            "model_digest": grant_model_digest(definition), "decisions": list(decisions)}
    receipt = None
    if leveled and has_native_grants(definition):
        if not any(is_confirmed_native_grant_custody(w, prior_record.definition) for w in numeric):
            raise SourceRepairError("The actual prior native grant custody is unavailable.")
        draft = inspect_native_grant_proposal(definition, systems_service,
            acquisition_context=acquisition_context, actor_id=actor_id,
            prior_definition=prior_record.definition, prior_custody=numeric)
        receipt = {"schema_version": 1, "event_type": event_type, "actor_id": actor_id,
            "generation": generation, "definition_digest": canonical_digest(definition.to_dict()),
            "state_revision": state_revision, "model_digest": grant_model_digest(definition),
            "intent": acquisition_context.to_dict(), "source_facts_digest": draft.source_digest,
            "capacity_frame": capacity_frame(state)}
    return _native_grant_audit_metadata(metadata, receipt)


def _verified_native_grant_custody(connection, campaign, character, audit_row,
        *, row_local_numeric_witnesses, prior_confirmed_custody):
    from .character_native_requalification import _generation
    from .character_source_authority import numeric_target_values, numeric_value_digest
    from .character_spell_grants import (NativeGrantCustody, canonical_digest,
        grant_model_digest, validate_native_grant_model, validate_acquisition_context,
        is_confirmed_native_grant_custody)
    metadata = _strict_grant_audit_json(audit_row["metadata_json"])
    if "native_grant_confirmation" not in metadata:
        return ()
    event = audit_row["event_type"]
    expected = {"character_native_created": ("native_create_confirmed", "native_creation", "create"),
                "character_native_leveled": ("native_level_up_confirmed", "native_level_up", "progression")}
    if event not in expected:
        _grant_receipt_error("Unsupported event cannot acquire grant custody.")
    source, provenance, mode = expected[event]
    actor = audit_row["actor_user_id"]
    receipt = metadata["native_grant_confirmation"]
    fields = {"schema_version", "event_type", "actor_id", "generation", "definition_digest",
              "state_revision", "model_digest", "intent", "source_facts_digest", "capacity_frame"}
    if (type(actor) is not int or actor < 1
            or type(metadata.get("numeric_actor_id")) is not int
            or metadata["numeric_actor_id"] != actor
            or metadata.get("source") != source or not isinstance(receipt, dict)
            or set(receipt) != fields or type(receipt["schema_version"]) is not int
            or receipt["schema_version"] != 1 or receipt["event_type"] != event
            or type(receipt["actor_id"]) is not int or receipt["actor_id"] != actor
            or type(receipt["generation"]) is not int or receipt["generation"] < 1
            or type(receipt["state_revision"]) is not int or receipt["state_revision"] < 1
            or not all(_sha256_hex(receipt[key]) for key in (
                "definition_digest", "model_digest", "source_facts_digest"))
            or receipt["definition_digest"] != metadata.get("definition_digest")
            or not _sha256_hex(metadata.get("source_snapshot_digest"))):
        _grant_receipt_error("Confirmed grant receipt is malformed or mismatched.")
    _native_grant_audit_metadata(
        {key: value for key, value in metadata.items() if key != "native_grant_confirmation"}, receipt)
    context = _grant_context_from_receipt(receipt["intent"])
    if context.mode != mode or context.actor_id != actor or context.campaign_slug != campaign:
        _grant_receipt_error("Confirmed receipt borrowed another submitted intent.")
    payload, generation = _generation(connection, campaign, character,
        receipt["definition_digest"], actor, revision=receipt["generation"])
    if type(generation["revision"]) is not int:
        _grant_receipt_error("Committed generation identity is not an integer.")
    if mode == "create" and (receipt["generation"] != 1 or generation["revision"] != 1):
        _grant_receipt_error("Creation receipt is not bound to the actual initial generation.")
    definition = CharacterDefinition.from_dict(payload)
    validate_native_grant_model(definition)
    if (grant_model_digest(definition) != receipt["model_digest"]
            or canonical_digest(definition.source["native_acquisitions"]["intent"])
            != canonical_digest(context.to_dict())):
        _grant_receipt_error("Audit model differs from its actual committed generation.")
    actual_prior = _receipt_prior_generation(connection, campaign, character, context)
    if mode == "progression":
        if (type(context.prior_revision) is not int
                or type(context.prior_state_revision) is not int
                or type(metadata.get("prior_state_revision")) is not int
                or type(metadata.get("state_revision")) is not int
                or generation["revision"] != context.prior_revision + 1
                or receipt["state_revision"] != context.prior_state_revision + 1
                or metadata.get("prior_state_revision") != context.prior_state_revision
                or metadata.get("state_revision") != receipt["state_revision"]
                or not any(is_confirmed_native_grant_custody(witness, actual_prior)
                           for witness in prior_confirmed_custody)):
            _grant_receipt_error("Progression receipt has no authenticated prior model.")
    validate_acquisition_context(definition, context, actor_id=actor,
        prior_definition=actual_prior, prior_custody=prior_confirmed_custody)
    batch = metadata.get("numeric_authorizations")
    if not isinstance(batch, list) or not 1 <= len(batch) <= 128:
        _grant_receipt_error("Current event has no complete native numeric batch.")
    local = [witness.get("authorization", witness) for witness in row_local_numeric_witnesses
             if isinstance(witness, dict) and not isinstance(witness, NativeGrantCustody)]
    if canonical_digest(local) != canonical_digest(batch):
        _grant_receipt_error("Earlier witnesses cannot authenticate the current native event.")
    stored = definition.source.get("source_authorizations", [])
    frame = receipt["capacity_frame"]
    if (not isinstance(frame, dict) or set(frame) != {"spell_slots", "hit_dice"}
            or type(frame["spell_slots"]) is not list
            or not isinstance(frame["hit_dice"], dict)
            or set(frame["hit_dice"]) != {"pools"} or type(frame["hit_dice"]["pools"]) is not list):
        _grant_receipt_error("Historical capacity frame is malformed.")
    slot_ids, dice_ids = set(), set()
    for slot in frame["spell_slots"]:
        if (not isinstance(slot, dict) or set(slot) != {"slot_lane_id", "level", "max"}
                or not isinstance(slot["slot_lane_id"], str) or not slot["slot_lane_id"]
                or type(slot["level"]) is not int or not 1 <= slot["level"] <= 9
                or type(slot["max"]) is not int or slot["max"] < 0
                or (slot["slot_lane_id"], slot["level"]) in slot_ids):
            _grant_receipt_error("Historical slot capacities are ambiguous.")
        slot_ids.add((slot["slot_lane_id"], slot["level"]))
    for die in frame["hit_dice"]["pools"]:
        if (not isinstance(die, dict) or set(die) != {"faces", "max"}
                or type(die["faces"]) is not int or die["faces"] not in {6, 8, 10, 12}
                or type(die["max"]) is not int or die["max"] < 0 or die["faces"] in dice_ids):
            _grant_receipt_error("Historical Hit Die capacities are ambiguous.")
        dice_ids.add(die["faces"])
    values, targets = numeric_target_values(definition, frame), set()
    for marker in batch:
        if (not _valid_numeric_witness_marker(marker, character, provenance)
                or marker.get("action_id") != metadata.get("action_id")
                or stored.count(marker) != 1):
            _grant_receipt_error("Current audit marker differs from committed native creation/progression.")
        key = (marker["target_kind"], marker["target_id"], marker["metric"])
        if key in targets or key not in values or numeric_value_digest(values[key]) != marker["value_digest"]:
            _grant_receipt_error("Current audit value or target is ambiguous.")
        targets.add(key)
    return (NativeGrantCustody(definition, origin=(
        "confirmed_native_creation" if mode == "create" else "confirmed_native_progression",
        campaign, character, audit_row["id"], actor, generation["revision"],
        hashlib.sha256(audit_row["metadata_json"].encode("utf-8")).hexdigest())),)


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
    requalification_history: dict[str, Any] = {}
    confirmed_updates: set[tuple[int, str, str]] = set()
    for row in rows:
        if row["event_type"] != "character_update_applied":
            continue
        try:
            update_metadata = json.loads(row["metadata_json"] or "{}")
            if (type(row["actor_user_id"]) is int and isinstance(update_metadata, dict)
                    and update_metadata.get("source") == "character_update_preview"
                    and _sha256_hex(update_metadata.get("review_digest"))
                    and _sha256_hex(update_metadata.get("candidate_digest"))):
                confirmed_updates.add((row["actor_user_id"], update_metadata["review_digest"],
                                       update_metadata["candidate_digest"]))
        except (TypeError, ValueError):
            continue
    for row in rows:
        metadata = None
        raw_metadata = None
        decision_event = False
        numeric_admitted = False
        decisions_admitted = False
        row_witnesses = []
        row_history = dict(requalification_history)
        # The validator replaces entries in this mapping before it can refuse.
        # Shared history and already accepted witness objects remain read-only.
        if "accepted_batches" in row_history:
            row_history["accepted_batches"] = dict(row_history["accepted_batches"])
        requalification_accepted = False
        try:
            actor_id = row["actor_user_id"]
            if type(actor_id) is not int or actor_id < 1:
                continue
            raw_metadata = row["metadata_json"]
            parsed_metadata = json.loads(raw_metadata or "{}")
            if not isinstance(parsed_metadata, dict):
                continue
            metadata = parsed_metadata
            requalification = metadata.get("native_requalification")
            if isinstance(requalification, dict) and requalification.get("schema_version") in {5, 6}:
                if type(raw_metadata) is not str or len(raw_metadata.encode("utf-8")) > 65536:
                    continue
                metadata = _strict_grant_audit_json(raw_metadata)
            decision_event = metadata.get("spell_choice_decisions") is not None
            if decision_event and row["event_type"] not in {"character_native_leveled", "character_native_spell_selected"}:
                continue
            if type(metadata.get("numeric_actor_id")) is not int or metadata["numeric_actor_id"] != actor_id:
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
                row_witnesses.append({"authorization": dict(marker),
                                      "source_basis_digest": marker["source_basis_digest"]})
                continue
            if row["event_type"] == "character_update_applied":
                if metadata.get("manager_action") == "native_language_elective_decision":
                    from .character_language_electives import verified_decision_batch
                    row_witnesses.extend(verified_decision_batch(db, campaign_slug,
                        character_slug, row, metadata, tuple(witnesses)))
                    continue
                if metadata.get("manager_action") == "native_reconstruct":
                    from .character_reconstruction_authority import verified_reconstruction_batch
                    row_witnesses.extend(verified_reconstruction_batch(
                        db, campaign_slug, character_slug, row, metadata, prior_witnesses=tuple(witnesses)))
                    continue
                if metadata.get("manager_action") == "native_requalify":
                    from .character_native_requalification import verified_requalification_batch
                    row_history["prior_numeric_witnesses"] = tuple(witnesses)
                    batch = verified_requalification_batch(
                        db, campaign_slug, character_slug, row, metadata,
                        history_cache=row_history)
                    requalification_accepted = bool(batch)
                    row_witnesses.extend(batch)
                    continue
                if (metadata.get("manager_action") != "numeric_attest"
                        or not isinstance(metadata.get("review_digest"), str)
                        or len(metadata["review_digest"]) != 64):
                    continue
                marker = metadata.get("numeric_authorization")
                batch = metadata.get("numeric_authorizations")
                if batch is not None:
                    # A skill correction has one owned skill and at most its
                    # directly dependent passive, published by the same review.
                    from .character_builder_constants import SKILL_LABELS
                    from .repository import normalize_lookup
                    skill_path = marker.get("target_id") if isinstance(marker, dict) else None
                    skill_name = skill_path.removeprefix("skills.") if isinstance(skill_path, str) else ""
                    passive = {"investigation": "passive_investigation", "insight": "passive_insight",
                               "perception": "passive_perception"}.get(normalize_lookup(skill_name))
                    expected = [("proficiency", skill_path, "grant")]
                    if passive is not None:
                        expected.append(("field", f"stats.{passive}", "final"))
                    if (not isinstance(batch, list) or len(batch) != len(expected)
                            or normalize_lookup(skill_name) not in SKILL_LABELS
                            or skill_path != f"skills.{SKILL_LABELS[normalize_lookup(skill_name)].casefold()}"
                            or metadata.get("source") != "character_source_repair"
                            or metadata.get("review_action") != "numeric_attest"
                            or metadata.get("review_target_id") != skill_path
                            or metadata.get("confirmed_skill_level") not in {"none", "half_proficient", "proficient", "expertise"}
                            or not _sha256_hex(metadata.get("review_digest"))
                            or not _sha256_hex(metadata.get("candidate_digest"))
                            or not _sha256_hex(metadata.get("published_definition_digest"))
                            or metadata.get("published_definition_digest") != metadata.get("candidate_digest")
                            or type(metadata.get("published_revision")) is not int or metadata["published_revision"] < 1
                            or type(metadata.get("published_state_revision")) is not int or metadata["published_state_revision"] < 1
                            or marker not in batch
                            or any(not _valid_numeric_witness_marker(item, character_slug, "manager")
                                   or item["action_id"] != metadata.get("action_id") for item in batch)
                            or [(item["target_kind"], item["target_id"], item["metric"]) for item in batch] != expected):
                        continue
                    row_witnesses.extend(dict(item) for item in batch)
                    continue
                if (_valid_numeric_witness_marker(marker, character_slug, "manager")
                        and metadata.get("action_id") == marker["action_id"]):
                    row_witnesses.append(dict(marker))
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
                    row_witnesses.extend(
                        {"authorization": dict(marker),
                         "source_basis_digest": basis[marker["target_id"]]}
                        if _native_source_bound_marker(marker) else dict(marker)
                        for marker in batch
                    )
                    custody = _verified_native_grant_custody(
                        db, campaign_slug, character_slug, row,
                        row_local_numeric_witnesses=tuple(row_witnesses),
                        prior_confirmed_custody=tuple(witnesses))
                    row_witnesses.extend(custody)
                    row_witnesses.extend(_verified_native_creation_spell_choices(
                        db, campaign_slug, character_slug, row, metadata, custody))
            elif row["event_type"] in {"character_native_leveled", "character_native_spell_selected"}:
                spell_choice = row["event_type"] == "character_native_spell_selected"
                expected_provenance = "native_spell_choice" if spell_choice else "native_level_up"
                expected_source = "native_spell_choice_confirmed" if spell_choice else "native_level_up_confirmed"
                prior_revision = metadata.get("prior_state_revision")
                revision = metadata.get("state_revision")
                if (metadata.get("source") != expected_source
                        or type(prior_revision) is not int or prior_revision < 0
                        or type(revision) is not int
                        or (revision not in {prior_revision, prior_revision + 1} if decision_event else revision != prior_revision + 1)
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
                if not all(_valid_numeric_witness_marker(marker, character_slug, expected_provenance)
                       and marker["action_id"] == action_id
                       and _native_source_bound_marker(marker)
                       and (not spell_choice or marker.get("target_kind") == "spell_choice")
                       and _sha256_hex(basis.get(marker["target_id"]))
                       for marker in batch):
                    continue
                if (len(basis) != len(batch)
                        or len({marker["target_id"] for marker in batch}) != len(batch)
                        or set(basis) != {marker["target_id"] for marker in batch}):
                    continue
                numeric_admitted = True
                row_witnesses.extend({"authorization": dict(marker),
                                      "source_basis_digest": basis[marker["target_id"]]}
                                     for marker in batch)
                if not spell_choice:
                    row_witnesses.extend(_verified_native_grant_custody(
                        db, campaign_slug, character_slug, row,
                        row_local_numeric_witnesses=tuple(row_witnesses),
                        prior_confirmed_custody=tuple(witnesses)))
            if decision_event:
                if not numeric_admitted:
                    continue
                row_witnesses.extend(_verified_native_spell_choice_decisions(db, campaign_slug,
                    character_slug, row, metadata, tuple(witnesses)))
                decisions_admitted = True
        except (KeyError, TypeError, ValueError):
            if decision_event:
                row_witnesses.clear()
            # Legacy numeric proof can survive a separate grant-custody refusal.
            continue
        finally:
            if row_witnesses and (not decision_event or numeric_admitted and decisions_admitted):
                try:
                    finalized = _native_aggregate_origins(
                        db, campaign_slug, character_slug, row, metadata, row_witnesses,
                        prior_witnesses=tuple(witnesses), require_complete=decision_event)
                    row_origins = []
                    if include_origin and finalized:
                        metadata_sha256 = hashlib.sha256(raw_metadata.encode("utf-8")).hexdigest()
                        row_origins = [{"witness": witness, "audit_id": row["id"],
                                        "actor_user_id": row["actor_user_id"],
                                        "event_type": row["event_type"],
                                        "source_snapshot_digest": metadata.get("source_snapshot_digest"),
                                        "metadata_sha256": metadata_sha256}
                                       for witness in finalized]
                except (KeyError, TypeError, ValueError):
                    pass  # An incomplete current-row origin contributes no witnesses.
                else:
                    witnesses.extend(finalized)
                    origins.extend(row_origins)
                    if requalification_accepted:
                        requalification_history = row_history
    if include_origin:
        return tuple(origins)
    return (*witnesses, *_load_transition_actions(db, campaign_slug, character_slug,
                                                   strict=strict))


def _load_transition_actions(connection: sqlite3.Connection, campaign_slug: str,
                             character_slug: str, *, strict: bool = False) -> tuple[dict[str, Any], ...]:
    """Load current-generation proofs only after validating their entire audit chain."""
    try:
        return tuple({"authorization": row["proof"]["authorization"],
                      "source_basis_digest": row["proof"]["new_basis"],
                      "transition_proof": row["proof"]}
                     for row in _current_transition_proof_rows(
                         connection, campaign_slug, character_slug))
    except Exception:
        if strict:
            raise SourceRepairError("Transition audit proof is unavailable.") from None
        return ()


_TRANSITION_V1_FIELDS = frozenset({
    "schema_version", "campaign_slug", "character_slug", "target_kind", "target_id",
    "metric", "authorization", "origin_audit_id", "origin_actor_user_id",
    "origin_event_type", "origin_metadata_sha256", "old_basis", "new_basis",
    "old_snapshot", "new_snapshot", "value_digest", "owner_digest", "identity",
    "activated_at",
})
_TRANSITION_V2_FIELDS = _TRANSITION_V1_FIELDS | frozenset({
    "prior_generation", "prior_transition_audit_id", "prior_transition_metadata_sha256",
})
_TRANSITION_IDENTITY_FIELDS = frozenset({
    "generation", "state", "config", "systems", "pages", "page_current", "audit",
})


def _current_transition_proof_rows(connection: sqlite3.Connection, campaign_slug: str,
                                   character_slug: str) -> tuple[dict[str, Any], ...]:
    """Return unique current proofs; older rows are validated links, never claims."""
    from .committed_publication import active
    if not active(connection):
        return ()
    marker = connection.execute(
        "SELECT activated_at FROM committed_source_activation WHERE singleton=1"
    ).fetchone()
    identity = _current_transition_identity(connection, campaign_slug, character_slug)
    if marker is None or not identity:
        return ()
    rows = connection.execute(
        """SELECT id,actor_user_id,metadata_json FROM auth_audit_log
           WHERE campaign_slug=? AND character_slug=?
             AND event_type='character_source_transition_confirmed' ORDER BY id""",
        (campaign_slug, character_slug),
    ).fetchall()
    if not rows:
        return ()
    prefix_digests = _transition_audit_prefix_digests(
        connection, campaign_slug, character_slug, {row["id"] for row in rows},
    )
    activation_audit_digest = prefix_digests[rows[0]["id"]]
    originals = load_verified_numeric_actions(campaign_slug, character_slug,
        connection=connection, strict=True, include_origin=True)
    by_id: dict[int, dict[str, Any]] = {}
    current: list[dict[str, Any]] = []
    counts: dict[tuple[str, str, str, str], int] = {}
    current_claim_ids: set[int] = set()
    valid_claim_ids: set[int] = set()
    for row in rows:
        try:
            proof = json.loads(row["metadata_json"])
            if not isinstance(proof, dict):
                continue
            if (isinstance(proof.get("identity"), dict)
                    and proof["identity"].get("generation") == identity["generation"]):
                current_claim_ids.add(row["id"])
            version = proof.get("schema_version")
            fields = _TRANSITION_V1_FIELDS if version == 1 else _TRANSITION_V2_FIELDS
            if (version not in {1, 2} or set(proof) != fields
                    or row["actor_user_id"] is not None
                    or proof.get("campaign_slug") != campaign_slug
                    or proof.get("character_slug") != character_slug
                    or proof.get("activated_at") != marker[0]
                    or proof.get("target_kind") not in {"resource", "spell_metric", "spell_choice"}
                    or not isinstance(proof.get("target_id"), str) or not proof["target_id"]
                    or not isinstance(proof.get("metric"), str) or not proof["metric"]
                    or not all(_sha256_hex(proof.get(name)) for name in (
                        "old_basis", "new_basis", "old_snapshot", "new_snapshot",
                        "value_digest", "owner_digest", "origin_metadata_sha256"))
                    or type(proof.get("origin_audit_id")) is not int
                    or type(proof.get("origin_actor_user_id")) is not int
                    or not isinstance(proof.get("authorization"), dict)
                    or not isinstance(proof.get("identity"), dict)
                    or set(proof["identity"]) != _TRANSITION_IDENTITY_FIELDS
                    or not _sha256_hex(proof["identity"].get("audit"))
                    or not _valid_transition_generation(proof["identity"].get("generation"))):
                continue
            generation = proof["identity"]["generation"]
            committed = connection.execute(
                """SELECT primary_sha256 FROM committed_source_generations
                   WHERE campaign_slug=? AND object_kind='character' AND object_ref=?
                     AND revision=? AND tombstone=0""",
                (campaign_slug, character_slug, generation[0]),
            ).fetchone()
            if committed is None or committed[0] != generation[1]:
                continue
            config_generation = proof["identity"].get("config")
            if not _valid_transition_generation(config_generation):
                continue
            committed_config = connection.execute(
                """SELECT primary_sha256 FROM committed_source_generations
                   WHERE campaign_slug=? AND object_kind='config' AND object_ref=''
                     AND revision=? AND tombstone=0""",
                (campaign_slug, config_generation[0]),
            ).fetchone()
            if committed_config is None or committed_config[0] != config_generation[1]:
                continue
            key = (proof["target_kind"], proof["target_id"], proof["metric"],
                   proof["new_basis"])
            is_current = proof["identity"]["generation"] == identity["generation"]
            if is_current:
                counts[key] = counts.get(key, 0) + 1
            authorization = proof["authorization"]
            if ((authorization.get("target_kind"), authorization.get("target_id"),
                 authorization.get("metric")) != key[:3]
                    or authorization.get("value_digest") != proof["value_digest"]
                    or (authorization.get("owner_digest") is not None
                        and authorization["owner_digest"] != proof["owner_digest"])):
                continue
            if version == 1:
                if proof["identity"]["audit"] != activation_audit_digest:
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
            else:
                prior_id = proof.get("prior_transition_audit_id")
                prior = by_id.get(prior_id) if type(prior_id) is int else None
                prior_proof = prior["proof"] if prior else None
                if (prior is None or prior_id >= row["id"]
                        or proof.get("prior_transition_metadata_sha256") != prior["metadata_sha256"]
                        or proof.get("prior_generation") != prior_proof["identity"]["generation"]
                        or proof["identity"]["generation"][0] != proof["prior_generation"][0] + 1
                        or (proof["target_kind"], proof["target_id"], proof["metric"])
                            != (prior_proof["target_kind"], prior_proof["target_id"], prior_proof["metric"])
                        or any(proof[name] != prior_proof[name] for name in (
                            "authorization", "origin_audit_id", "origin_actor_user_id",
                            "origin_event_type", "origin_metadata_sha256", "activated_at",
                            "value_digest", "owner_digest"))
                        or proof["old_basis"] != prior_proof["new_basis"]
                        or proof["old_snapshot"] != prior_proof["new_snapshot"]):
                    continue
                if proof["identity"]["audit"] != prefix_digests[row["id"]]:
                    continue
            record = {"audit_id": row["id"], "metadata_sha256": hashlib.sha256(
                row["metadata_json"].encode("utf-8")).hexdigest(), "proof": proof}
            by_id[row["id"]] = record
            if is_current:
                valid_claim_ids.add(row["id"])
            if is_current and all(proof["identity"].get(name) == value
                                  for name, value in identity.items() if name != "state"):
                current.append(record)
        except (TypeError, ValueError, KeyError):
            continue
    if current_claim_ids != valid_claim_ids:
        raise SourceRepairError("Current Character transition proof is malformed.")
    if any(count != 1 for count in counts.values()):
        raise SourceRepairError("Current Character transition target is duplicated.")
    return tuple(row for row in current if counts[(row["proof"]["target_kind"],
        row["proof"]["target_id"], row["proof"]["metric"],
        row["proof"]["new_basis"])] == 1)


def _valid_transition_generation(value: Any) -> bool:
    return (isinstance(value, list) and len(value) == 2
            and type(value[0]) is int and value[0] >= 1 and _sha256_hex(value[1]))


def _transition_audit_prefix_digests(connection: sqlite3.Connection,
                                     campaign_slug: str, character_slug: str,
                                     target_ids: set[int]) -> dict[int, str]:
    """Hash canonical audit prefixes once in ID order, including nonproof rows."""
    digest = hashlib.sha256(b"[")
    first = True
    result: dict[int, str] = {}
    for row in connection.execute(
        """SELECT id,actor_user_id,event_type,metadata_json FROM auth_audit_log
           WHERE campaign_slug=? AND character_slug=? ORDER BY id""",
        (campaign_slug, character_slug),
    ).fetchall():
        if row["id"] in target_ids:
            ending = digest.copy()
            ending.update(b"]")
            result[row["id"]] = ending.hexdigest()
        if not first:
            digest.update(b",")
        digest.update(json.dumps(tuple(row), sort_keys=True, default=str,
                                 separators=(",", ":")).encode())
        first = False
    if len(result) != len(target_ids):
        raise SourceRepairError("Transition audit prefix is incomplete.")
    return result


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
    from .character_source_authority import native_baseline_target, native_advancement_input_target
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
    ) or native_baseline_target(marker.get("target_kind"), marker.get("target_id", ""), marker.get("metric")) or (
        marker.get("provenance") in {"native_level_up", "native_reconstruction", "native_requalification"}
        and native_advancement_input_target(marker.get("target_kind"), marker.get("target_id", ""), marker.get("metric"))
    )


def record_confirmed_native_level_up_witness(
    *, expected_definition: CharacterDefinition, readback_record: object,
    markers: tuple[dict[str, Any], ...], prior_revision: int,
    source_snapshot_digest: str, source_basis_digests: dict[str, str],
    actor_id: int, auth_store: object, witness_kind: str = "native_level_up",
    prior_definition: CharacterDefinition | None = None, systems_service: Any = None,
    campaign_page_records: list[Any] | None = None,
    verified_manual_actions: tuple[Any, ...] = (), verified_numeric_actions: tuple[Any, ...] = (),
    advancement_intent: Any = None,
    acquisition_context: Any = None,
    prior_record: Any = None,
) -> bool:
    """Record one new owner batch only after a revisioned level-up readback."""
    from .character_source_authority import numeric_target_values, numeric_value_digest
    from .character_update_apply import canonical_digest
    from .character_spell_grants import has_native_grants, is_confirmed_native_grant_custody
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
    from .character_spell_grants import CLASS_CHOICE_STATE_FIELD
    typed_decision = any(CLASS_CHOICE_STATE_FIELD in row for model in (
        expected_definition, getattr(prior_record, "definition", expected_definition))
        for row in model.spellcasting.get("spells", []) if isinstance(row, dict))
    if (not isinstance(readback_definition, CharacterDefinition)
            or not isinstance(readback_state, dict)
            or type(revision) is not int
            or (revision not in {prior_revision, prior_revision + 1} if typed_decision else revision != prior_revision + 1)
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
    if any(marker.get("target_kind") == "resource" and marker.get("target_id", "").startswith("resource:")
           and not marker.get("target_id", "").startswith("resource:campaign-option-tracker:") for marker in markers):
        from .character_source_authority import NativeAdvancementIntent
        if (systems_service is None or prior_definition is None
                or not isinstance(advancement_intent, NativeAdvancementIntent)
                or not advancement_intent.matches_resource_readback(prior_definition, readback_definition)):
            return False
        try:
            from .character_source_authority import build_reconciled_source_authority, validate_native_managed_resource_templates
            authority = build_reconciled_source_authority(
                definition=readback_definition, state=readback_state, state_revision=revision,
                systems_service=systems_service, campaign_page_records=campaign_page_records,
                verified_manual_actions=verified_manual_actions, verified_numeric_actions=verified_numeric_actions,
            )
            prior_authority = build_reconciled_source_authority(
                definition=prior_definition, state=readback_state, state_revision=prior_revision,
                systems_service=systems_service, campaign_page_records=campaign_page_records,
                verified_manual_actions=verified_manual_actions, verified_numeric_actions=verified_numeric_actions,
            )
            for marker in markers:
                target = marker.get("target_id", "")
                if marker.get("target_kind") != "resource" or not target.startswith("resource:"):
                    continue
                tracker_id = target.removeprefix("resource:")
                if (any(row.get("id") == tracker_id for row in prior_definition.resource_templates)
                        and not prior_authority.resource_status("resource", tracker_id).is_effective):
                    return False
            validate_native_managed_resource_templates(
                readback_definition, readback_state, authority=authority, systems_service=systems_service,
                campaign_page_records=campaign_page_records, prior_definition=prior_definition,
                restored_resource_currents=advancement_intent.restored_resource_currents,
                prior_authority=prior_authority,
            )
        except (TypeError, ValueError):
            return False
    grant_receipt = None
    if witness_kind == "native_level_up":
        try:
            grant_receipt = _native_grant_confirmation_receipt(
                expected_definition, readback_record, acquisition_context, actor_id,
                systems_service, prior_definition=prior_definition,
                prior_custody=verified_numeric_actions,
                expected_event="character_native_leveled")
        except (AttributeError, KeyError, TypeError, ValueError):
            return False
    complete_metadata = None
    if typed_decision:
        try:
            if (prior_record is None or prior_record.state_record.revision != prior_revision
                    or prior_definition is not None and prior_record.definition.to_dict() != prior_definition.to_dict()):
                return False
            actual_state = get_db().execute("SELECT revision,state_json FROM character_state "
                "WHERE campaign_slug=? AND character_slug=?", (campaign_slug, character_slug)).fetchone()
            if (actual_state is None or actual_state["revision"] != revision
                    or json.loads(actual_state["state_json"]) != readback_state):
                return False
            _decision_generation(get_db(), campaign_slug, character_slug,
                readback_record.committed_revision, canonical_digest(readback_definition.to_dict()), actor_id)
            complete_metadata = prepare_native_spell_choice_audit_metadata(prior_record,
                readback_definition, readback_state, actor_id=actor_id, markers=markers,
                source_snapshot_digest=source_snapshot_digest, source_basis_digests=source_basis_digests,
                event_type=event_type, systems_service=systems_service,
                campaign_page_records=campaign_page_records, acquisition_context=acquisition_context,
                advancement_intent=advancement_intent, state_revision=revision,
                generation=readback_record.committed_revision)
            if complete_metadata.get("native_grant_confirmation") != grant_receipt:
                return False
        except (AttributeError, KeyError, TypeError, ValueError):
            return False
    expected_witnesses = tuple(
        {"authorization": dict(marker),
         "source_basis_digest": source_basis_digests[marker["target_id"]]}
        for marker in markers
    )
    def decisions_confirmed(witnesses):
        from .character_source_authority import ordinary_native_spell_choice_state
        if complete_metadata is None:
            return True
        expected = complete_metadata.get("spell_choice_decisions", {}).get("decisions", [])
        rows = {row.get("id"): row for row in readback_definition.spellcasting.get("spells", []) if isinstance(row, dict)}
        for decision in expected:
            spell_id = decision["spell_id"]
            matching = [m for m in persisted_markers if isinstance(m, dict)
                and (m.get("target_kind"), m.get("target_id"), m.get("metric")) == ("spell_choice", f"spell_choice:{spell_id}", "selection")]
            if (len(matching) != 1 or ordinary_native_spell_choice_state(rows.get(spell_id), matching[0],
                    verified_numeric_actions=witnesses) != decision["after_state"]):
                return False
        return True
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
                witnesses = load_verified_numeric_actions(campaign_slug, character_slug)
                return (all(witness in witnesses for witness in expected_witnesses) and decisions_confirmed(witnesses)
                        and (not has_native_grants(readback_definition) or any(
                            is_confirmed_native_grant_custody(witness, readback_definition)
                            for witness in witnesses)))
        auth_store.insert_audit_event(
            event_type=event_type, actor_user_id=actor_id,
            campaign_slug=campaign_slug, character_slug=character_slug,
            metadata=complete_metadata if complete_metadata is not None else _native_grant_audit_metadata({
                "source": source_label,
                "numeric_actor_id": actor_id,
                "numeric_authorizations": list(markers),
                "action_id": action_id,
                "definition_digest": canonical_digest(readback_definition.to_dict()),
                "prior_state_revision": prior_revision,
                "state_revision": revision,
                "source_snapshot_digest": source_snapshot_digest,
                "source_basis_digests": dict(source_basis_digests),
            }, grant_receipt),
            commit=True,
        )
        witnesses = load_verified_numeric_actions(campaign_slug, character_slug)
        return (all(witness in witnesses for witness in expected_witnesses) and decisions_confirmed(witnesses)
                and (not has_native_grants(readback_definition) or any(
                    is_confirmed_native_grant_custody(witness, readback_definition)
                    for witness in witnesses)))
    except Exception:
        return False


def prepare_native_creation_authorizations(
    definition: CharacterDefinition, initial_state: Mapping[str, Any],
    *, systems_service: Any, campaign_page_records: list[Any] | None,
    acquisition_context: Any = None,
) -> tuple[CharacterDefinition, tuple[dict[str, Any], ...], dict[str, str], str]:
    """Pre-mark only a new native DND baseline; the later audit is authority."""
    from .character_source_authority import (build_reconciled_source_authority, numeric_target_values,
                                            validate_native_managed_resource_templates)
    from .system_policy import is_dnd_5e_system
    if not is_dnd_5e_system(definition.system):
        raise SourceRepairError("Native numeric attestation applies only to DND-5E.")
    from .character_spell_grants import has_native_grants, inspect_native_grant_proposal
    if has_native_grants(definition):
        # Source/acquisition proposal validation is deliberately disjoint from
        # numeric/confirmed authority. No draft enters verified_numeric_actions.
        try:
            inspect_native_grant_proposal(definition, systems_service,
                acquisition_context=acquisition_context)
        except ValueError as exc:
            raise SourceRepairError("Native grant acquisition or source proposal changed.") from exc
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
    action_id = uuid4().hex
    input_markers = {}
    input_witnesses = []
    provisional = deepcopy(payload)
    for kind, target_id, metric in keys:
        raw_value = values.get((kind, target_id, metric))
        basis = authority.numeric_basis_digest(target_id)
        if raw_value is None or not _sha256_hex(basis):
            raise SourceRepairError("Native baseline input is incomplete.")
        marker = numeric_authorization_record(
            character_slug=definition.character_slug, target_kind=kind, target_id=target_id,
            metric=metric, raw_value=raw_value, action_id=action_id, provenance="native_creation",
        )
        input_markers[(kind, target_id, metric)] = marker
        provisional = add_numeric_authorization(provisional, marker)
        # Creation base/PB inputs retain their existing exact bare-marker contract.
        input_witnesses.append(marker)
    input_definition = CharacterDefinition.from_dict(provisional)
    authority = build_reconciled_source_authority(
        definition=input_definition, state=dict(initial_state), state_revision=0,
        systems_service=systems_service, campaign_page_records=campaign_page_records,
        verified_numeric_actions=tuple(input_witnesses),
    )
    validate_native_managed_resource_templates(
        input_definition, dict(initial_state), authority=authority, systems_service=systems_service,
        campaign_page_records=campaign_page_records,
    )
    numeric_basis = getattr(authority, "numeric_basis_digest", lambda _target_id: None)
    if numeric_basis("stats.max_hp") is not None:
        keys.append(("field", "stats.max_hp", "final"))
    from .character_source_authority import native_baseline_target
    keys.extend(key for key in values if native_baseline_target(*key)
                and numeric_basis(key[1]) is not None)
    keys.extend(key for key in values if key[0] == "resource"
                and authority.resource_basis_digest(key[1]) is not None)
    keys.extend(key for key in values if key[0] == "spell_metric"
                and authority.numeric_basis_digest(key[1]) is not None)
    keys.extend(key for key in values if key[0] == "spell_choice"
                and authority.numeric_basis_digest(key[1]) is not None)
    if len(keys) != len(set(keys)) or len(keys) > 128:
        raise SourceRepairError("Native owner identities are ambiguous or too many.")
    from .character_spell_grants import native_class_choice_rows, native_class_choice_state, CLASS_CHOICE_STATE_FIELD
    typed = {spell_id: row for spell_id, row in native_class_choice_rows(definition).items()
             if CLASS_CHOICE_STATE_FIELD in row}
    if any(native_class_choice_state(row) != "active"
            or ("spell_choice", f"spell_choice:{spell_id}", "selection") not in keys
            for spell_id, row in typed.items()):
        raise SourceRepairError("Every ordinary creation choice needs its complete current source target.")
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
    markers = []
    numeric_basis_digests: dict[str, str] = {}
    for kind, target_id, metric in keys:
        if (kind, target_id, metric) not in values or values[(kind, target_id, metric)] is None:
            raise SourceRepairError("Native baseline input is incomplete.")
        markers.append(input_markers.get((kind, target_id, metric)) or numeric_authorization_record(
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
    acquisition_context: Any = None,
) -> bool:
    """Audit only after durable create/readback; failure leaves UNKNOWN."""
    from .character_source_authority import (build_reconciled_source_authority,
                                             numeric_target_values, numeric_value_digest)
    from .character_update_apply import canonical_digest
    from .character_spell_grants import has_native_grants, is_confirmed_native_grant_custody
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
        grant_receipt = _native_grant_confirmation_receipt(
            expected_definition, readback_record, acquisition_context, actor_id,
            systems_service, expected_event="character_native_created")
        from .character_source_authority import native_advancement_input_target, validate_native_managed_resource_templates
        provisional_inputs = tuple(
            marker
            for marker in markers if native_advancement_input_target(
                marker.get("target_kind"), marker.get("target_id", ""), marker.get("metric"))
        )
        readback_authority = build_reconciled_source_authority(
            definition=readback_definition, state=readback_state,
            state_revision=readback_record.state_record.revision,
            systems_service=systems_service,
            campaign_page_records=campaign_page_records,
            verified_numeric_actions=provisional_inputs,
        )
        validate_native_managed_resource_templates(
            readback_definition, readback_state, authority=readback_authority,
            systems_service=systems_service, campaign_page_records=campaign_page_records,
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
    from .character_spell_grants import native_class_choice_rows, native_class_choice_state, CLASS_CHOICE_STATE_FIELD
    try:
        typed = {spell_id: row for spell_id, row in native_class_choice_rows(readback_definition).items()
                 if CLASS_CHOICE_STATE_FIELD in row}
        if any(native_class_choice_state(row) != "active" or sum(
                (marker.get("target_kind"), marker.get("target_id"), marker.get("metric"))
                    == ("spell_choice", f"spell_choice:{spell_id}", "selection")
                for marker in markers) != 1 for spell_id, row in typed.items()):
            return False
    except (TypeError, ValueError):
        return False
    campaign_slug = readback_definition.campaign_slug
    expected_witnesses = tuple(
        {"authorization": dict(marker),
         "source_basis_digest": source_basis_digests[marker["target_id"]]}
        if _native_source_bound_marker(marker) else dict(marker)
        for marker in markers
    )
    def confirmed_creation(witnesses):
        from .character_source_authority import ordinary_native_spell_choice_state
        return (all(witness in witnesses for witness in expected_witnesses)
            and (not has_native_grants(readback_definition) or any(
                is_confirmed_native_grant_custody(witness, readback_definition) for witness in witnesses))
            and all(ordinary_native_spell_choice_state(raw, next(marker for marker in markers
                if marker.get("target_kind") == "spell_choice"
                and marker.get("target_id") == f"spell_choice:{spell_id}"),
                verified_numeric_actions=witnesses) == "active" for spell_id, raw in typed.items()))
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
                return confirmed_creation(witnesses)
        auth_store.insert_audit_event(
            event_type="character_native_created",
            actor_user_id=actor_id,
            campaign_slug=campaign_slug,
            character_slug=character_slug,
            metadata=_native_grant_audit_metadata({
                "source": "native_create_confirmed",
                "numeric_actor_id": actor_id,
                "numeric_authorizations": list(markers),
                "action_id": expected_action,
                "definition_digest": canonical_digest(readback_definition.to_dict()),
                "source_basis_digests": dict(source_basis_digests),
                "source_snapshot_digest": source_snapshot_digest,
            }, grant_receipt),
            commit=True,
        )
        witnesses = load_verified_numeric_actions(campaign_slug, character_slug)
        return confirmed_creation(witnesses)
    except Exception:
        return False


def load_verified_manual_actions(campaign_slug: str, character_slug: str, *,
                                 connection: sqlite3.Connection | None = None,
                                 strict: bool = False) -> tuple[dict[str, Any], ...]:
    from .character_reconstruction_inputs import current_input_scope, audit_input_witness
    scope = current_input_scope()
    if scope is None:
        return _load_verified_manual_actions(campaign_slug, character_slug,
            connection=connection, strict=strict)
    db = connection if connection is not None else get_db()
    return scope.resolve(("manual_actions", campaign_slug, character_slug, strict),
        lambda: audit_input_witness(db, campaign_slug, character_slug),
        lambda _witness: _load_verified_manual_actions(campaign_slug, character_slug,
            connection=db, strict=strict))


def _load_verified_manual_actions(campaign_slug: str, character_slug: str, *,
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
