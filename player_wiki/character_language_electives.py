"""Source-slot-bound manager decisions, not self-authorizing source flags.

Slot construction never loads an action witness. Audit admission never builds
SourceAuthority. The three steps are structural slots, authenticated outcomes,
then ordinary language numeric bases. Original reconstruction inputs are history.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Callable

from .character_models import CharacterDefinition
from .character_source_repair import SourceRepairError

FRAME_KEY = "language_elective_outcomes"
OPERATION = "native_language_elective_decision"
PROVENANCE = "native_elective_decision"
MAX_OUTCOMES = 128
_ISSUER = object()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _hex(value):
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _keys(value, maximum=32):
    return type(value) is dict and len(value) <= maximum and all(type(key) is str for key in value)


def _ref(value):
    return (_keys(value, 5) and set(value) == {"entry_key", "entry_type", "title", "slug", "source_id"}
        and all(type(item) is str and 1 <= len(item) <= 512 for item in value.values()))


def _adoption_allowed(slot, value, permission):
    """One reviewed retained-label permission, never a wider source domain."""
    from .character_builder_constants import STANDARD_LANGUAGE_OPTIONS, UNRESTRICTED_LANGUAGE_OPTIONS
    if type(value) is not str or value not in UNRESTRICTED_LANGUAGE_OPTIONS or type(permission) is not str:
        return False
    if permission == "source":
        return value in slot["options"]
    return (permission == "dm_exotic"
        and (slot["owner_id"], slot["systems_ref"]["entry_type"]) in {
            ("species", "race"), ("background", "background")}
        and slot["options"] == STANDARD_LANGUAGE_OPTIONS
        and value in UNRESTRICTED_LANGUAGE_OPTIONS and value not in STANDARD_LANGUAGE_OPTIONS)


def _retained_once(labels, value):
    from .repository import normalize_lookup
    return (type(value) is str and labels.count(value) == 1
        and sum(normalize_lookup(name) == normalize_lookup(value) for name in labels) == 1)


def _decision_languages(prior, submitted, contracts):
    """Adoption preserves the ordered observations; only a new selection appends."""
    retained = list(prior.proficiencies.get("languages", []))
    labels = list(retained)
    by_slot = {slot["slot_id"]: slot for slot in contracts}
    from .repository import normalize_lookup
    for intent in submitted["decisions"]:
        if intent["outcome"] == "adopted":
            slot = by_slot.get(intent["slot_id"])
            value = intent["selected_value"]
            if (slot is None or not _retained_once(retained, value)
                    or not _adoption_allowed(slot, value, intent["permission"])):
                raise SourceRepairError("Adoption needs one retained language and its exact source-slot permission.")
        elif intent["outcome"] == "selected":
            value = intent["selected_value"]
            if normalize_lookup(value) in {normalize_lookup(name) for name in labels}:
                raise SourceRepairError("A source slot cannot duplicate an existing retained language.")
            labels.append(value)
    return labels


def operation(value):
    combined = type(value) is dict and "external_acquisition" in value
    if (not _keys(value, 3) or set(value) != {"kind", "decisions"} | ({"external_acquisition"} if combined else set())
            or type(value["kind"]) is not str or value["kind"] != OPERATION or type(value["decisions"]) is not list
            or not 1 <= len(value["decisions"]) <= MAX_OUTCOMES):
        raise SourceRepairError("Language decisions need exact current optional slots.")
    rows, seen = [], set()
    for row in value["decisions"]:
        if not _keys(row, 4) or type(row.get("outcome")) is not str:
            raise SourceRepairError("A language decision has an invalid outcome.")
        expected = ({"slot_id", "outcome"}
            | ({"selected_value"} if row["outcome"] in {"selected", "adopted"} else set())
            | ({"permission"} if row["outcome"] == "adopted" else set()))
        if (set(row) != expected or row["outcome"] not in {"declined", "selected", "adopted"}
                or not _hex(row["slot_id"]) or row["slot_id"] in seen
                or row["outcome"] in {"selected", "adopted"} and (
                    type(row["selected_value"]) is not str or not 1 <= len(row["selected_value"]) <= 160)
                or row["outcome"] == "adopted" and (
                    type(row["permission"]) is not str or row["permission"] not in {"source", "dm_exotic"})):
            raise SourceRepairError("A language decision has a duplicate or unsupported slot.")
        seen.add(row["slot_id"])
        rows.append(deepcopy(row))
    result = {"kind": OPERATION, "decisions": rows}
    if combined:
        from .character_external_proficiencies import language_declaration
        if any(row["outcome"] != "declined" for row in rows):
            raise SourceRepairError("An external language confirmation may accompany only unused-slot declines.")
        result["external_acquisition"] = language_declaration(value["external_acquisition"])
    return result


def source_slots(definition, service, *, owners=None, slots=None):
    """Current structural input only; independent of all decision witnesses."""
    from .character_reconstruction_proficiencies import current_owners, grant_contract
    from .character_builder_equipment import _systems_ref_from_entry
    frame = definition.source.get("native_reconstruction_choices")
    if type(frame) is not dict or type(frame.get("choices")) is not dict:
        raise SourceRepairError("Language decisions require existing native choice history.")
    owners = current_owners(definition, service) if owners is None else owners
    if slots is None:
        _fixed, slots = grant_contract(definition, owners)
    refs = {identity: _systems_ref_from_entry(entry) for identity, entry in owners}
    grouped = {}
    for slot in slots:
        if slot["category"] == "languages":
            grouped.setdefault(slot["owner"], []).append(list(slot["options"]))
    positions, result = {}, []
    for global_index, slot in enumerate(slots):
        if slot["category"] != "languages":
            continue
        owner = slot["owner"]
        position = positions.get(owner, 0)
        positions[owner] = position + 1
        if slot.get("language_condition"):
            # This is a mandatory grant/replacement branch, not an elective
            # which may be declined or adopted without its prerequisite.
            continue
        group = f"reconstruction:{owner}:languages"
        observations = frame["choices"].get(group)
        if (type(observations) is not list or len(observations) != len(grouped[owner])
                or any(type(v) is not str for v in observations)):
            raise SourceRepairError("The retained language slot history changed shape.")
        basis = digest({"domain": "language-elective-slot-v1", "system": definition.system,
            "owner_id": owner, "systems_ref": refs[owner], "category": "languages",
            "ordered_domains": grouped[owner], "position": position})
        identity = {"campaign_slug": definition.campaign_slug, "character_slug": definition.character_slug,
            "owner_id": owner, "category": "languages", "position": position,
            "systems_ref": refs[owner], "slot_basis_digest": basis}
        result.append({**identity, "slot_id": digest(identity), "options": list(slot["options"]),
            "ordered_domains": deepcopy(grouped[owner]),
            "observation": observations[position], "unresolved_marker": f"__unresolved_{global_index}__"})
    if len(result) > MAX_OUTCOMES:
        raise SourceRepairError("The current optional language slots exceed their bounded decision contract.")
    return result


def outcome_rows(definition):
    frame = definition.source.get("native_reconstruction_choices")
    rows = frame.get(FRAME_KEY, []) if type(frame) is dict else []
    if type(rows) is not list or len(rows) > MAX_OUTCOMES:
        raise SourceRepairError("The language outcome frame is malformed.")
    result, seen = [], set()
    fields = {"schema_version", "owner_id", "category", "position", "systems_ref",
              "slot_basis_digest", "outcome", "decision_id"}
    for row in rows:
        if not _keys(row, 10) or type(row.get("outcome")) is not str:
            raise SourceRepairError("The language outcome row is malformed.")
        if (set(row) != (fields | ({"selected_value"} if row["outcome"] in {"selected", "adopted"} else set())
                | ({"permission"} if row["outcome"] == "adopted" else set()))
                or type(row["schema_version"]) is not int or row["schema_version"] != 1
                or type(row["owner_id"]) is not str or not 1 <= len(row["owner_id"]) <= 512
                or type(row["category"]) is not str or row["category"] != "languages" or type(row["position"]) is not int
                or not 0 <= row["position"] < MAX_OUTCOMES
                or not _ref(row["systems_ref"])
                or not _hex(row["slot_basis_digest"]) or not _hex(row["decision_id"])
                or row["outcome"] not in {"declined", "selected", "adopted"}
                or row["outcome"] in {"selected", "adopted"} and (
                    type(row["selected_value"]) is not str or not 1 <= len(row["selected_value"]) <= 160)
                or row["outcome"] == "adopted" and (
                    type(row["permission"]) is not str or row["permission"] not in {"source", "dm_exotic"})):
            raise SourceRepairError("The language outcome fields are unsupported.")
        key = row["owner_id"], row["position"]
        if key in seen:
            raise SourceRepairError("One optional language slot has conflicting decisions.")
        seen.add(key)
        result.append(deepcopy(row))
    return result


class NativeElectiveDecision(dict):
    """Exact private audit/pending witness; a JSON row is never this witness."""
    def __init__(self, outcomes, *, origin, _issuer=None):
        if _issuer is not _ISSUER:
            raise SourceRepairError("A language outcome requires authenticated decision custody.")
        super().__init__(outcomes=deepcopy(outcomes))
        self.origin = origin


class PendingElectiveOutcome(dict):
    """Ephemeral issuer input; never a durable decision or serialized proof."""
    def __init__(self, outcomes, *, origin, _issuer=None):
        if _issuer is not _ISSUER:
            raise SourceRepairError("Pending language outcomes require their genuine issuer.")
        super().__init__(outcomes=deepcopy(outcomes))
        self.origin = origin


def resolve_outcomes(definition, service, witnesses=(), *, owners=None, slots=None):
    rows = outcome_rows(definition)
    if not rows:
        return {}
    current = {(slot["owner_id"], slot["position"]): slot for slot in
               source_slots(definition, service, owners=owners, slots=slots)}
    latest = {}
    for witness in witnesses:
        if type(witness) not in (NativeElectiveDecision, PendingElectiveOutcome) or set(vars(witness)) != {"origin"}:
            continue
        if (type(witness.origin) is not tuple or len(witness.origin) != 7
                or witness.origin[1:3] != (definition.campaign_slug, definition.character_slug)
                or witness.origin[0] != ("confirmed_language_decision" if type(witness) is NativeElectiveDecision
                                         else "pending_language_decision")):
            continue
        for row in witness.get("outcomes", []):
            latest[(row["owner_id"], row["position"])] = row
    result = {}
    for row in rows:
        key = row["owner_id"], row["position"]
        slot = current.get(key)
        if (slot is None or latest.get(key) != row
                or row["systems_ref"] != slot["systems_ref"]
                or row["slot_basis_digest"] != slot["slot_basis_digest"]
                or row["outcome"] == "selected" and row["selected_value"] not in slot["options"]
                or row["outcome"] == "adopted" and (
                    not _adoption_allowed(slot, row["selected_value"], row["permission"])
                    or not _retained_once(list(definition.proficiencies.get("languages", [])), row["selected_value"]))
                or not slot["observation"].startswith("__unresolved_")):
            _observe_language_admission("slot", row=row, slot=slot, latest=latest.get(key))
            raise SourceRepairError("A language outcome has no current exact source-slot decision.")
        result[key] = row
    # Omitting a still-operative authenticated row is not permission to revive
    # its original unresolved observation or a superseded decision.
    if set(latest) != set(result):
        _observe_language_admission("vector", latest=latest, result=result)
        raise SourceRepairError("The current language decision vector lost authenticated custody.")
    return result


def language_basis(definition, service, witnesses=(), *, owners=None, slots=None):
    admitted = resolve_outcomes(definition, service, witnesses, owners=owners, slots=slots)
    return [deepcopy(admitted[key]) for key in sorted(admitted)]


def continuation_outcomes(prior, candidate, service, witnesses=()):
    """Validate, never issue or silently shift a carried slot decision."""
    if outcome_rows(prior) != outcome_rows(candidate):
        raise SourceRepairError("Language decisions need their explicit manager Update review.")
    resolve_outcomes(candidate, service, witnesses)
    return candidate


def decision_fields(definition, service):
    if type(definition.source.get("native_reconstruction_choices")) is not dict:
        return []
    from .character_source_repair import load_verified_numeric_actions
    from .character_reconstruction_proficiencies import current_owners, grant_contract
    from .repository import normalize_lookup
    from . import character_builder as builder
    witnesses = load_verified_numeric_actions(definition.campaign_slug, definition.character_slug, strict=True)
    owners = current_owners(definition, service)
    fixed, slots = grant_contract(definition, owners)
    current = source_slots(definition, service, owners=owners, slots=slots)
    admitted = resolve_outcomes(definition, service, witnesses, owners=owners, slots=slots)
    feat_languages = builder._extract_feat_language_proficiencies(
        [{"entry": entry, "instance_key": identity} for identity, entry in owners if entry.entry_type == "feat"],
        definition.source["native_reconstruction_choices"]["choices"])
    claimed = {normalize_lookup(value) for value in [*fixed["languages"], *feat_languages]}
    claimed.update(normalize_lookup(row["selected_value"]) for row in admitted.values()
        if row["outcome"] in {"selected", "adopted"})
    claimed.update(normalize_lookup(slot["observation"]) for slot in current
        if not slot["observation"].startswith("__unresolved_"))
    labels = list(definition.proficiencies.get("languages", []))
    fields = []
    for slot in current:
        key = slot["owner_id"], slot["position"]
        outcome = admitted.get(key)
        if not slot["observation"].startswith("__unresolved_"):
            continue  # A fixed/selected observation is not a declinable elective.
        adoption_options = []
        if outcome is None:
            for value in labels:
                if not _retained_once(labels, value) or normalize_lookup(value) in claimed:
                    continue
                permission = next((kind for kind in ("source", "dm_exotic")
                    if _adoption_allowed(slot, value, kind)), None)
                if permission is not None:
                    adoption_options.append({"value": f"adopted:{permission}:{value}", "label": value,
                        "requires_permission": permission == "dm_exotic"})
        if outcome is None:
            status = "Unresolved; no grant"
        elif outcome["outcome"] == "declined":
            status = "DM declined; no language grant"
        else:
            status = ("Adopted " if outcome["outcome"] == "adopted" else "Selected ") + outcome["selected_value"]
        fields.append({"slot_id": slot["slot_id"], "owner_id": slot["owner_id"],
            "position": slot["position"], "options": slot["options"],
            "status": status,
            "adoption_options": adoption_options,
            "can_decline": outcome is None or outcome["outcome"] == "declined",
            "can_select": outcome is not None and outcome["outcome"] == "declined"})
    return fields


def form_operation(values, fields):
    if type(values) is not dict or len(values) > MAX_OUTCOMES:
        raise SourceRepairError("Language decision inputs exceed their bounded form.")
    values = dict(values)
    declaration = None
    external_names = {"external_proficiency_" + key for key in (
        "name", "kind", "origin_status", "origin", "occurred_at", "evidence", "confirmed")}
    if "confirm_external_language" in values:
        confirmation = values.pop("confirm_external_language")
        if confirmation != "yes":
            raise SourceRepairError("Confirm the full existing external language explicitly.")
        from .character_external_proficiencies import acquisition_row, ADOPT_EXISTING
        raw = {key: values.pop(key) for key in external_names if key in values}
        raw["external_proficiency_category"] = "languages"
        raw.setdefault("external_proficiency_confirmed", "yes")
        row = acquisition_row(raw)
        declaration = {"operation": ADOPT_EXISTING, **{key: value for key, value in row.items() if key != "schema_version"}}
    elif external_names & set(values):
        raw = {key: values.pop(key) for key in external_names if key in values}
        if any(value not in ("", "external_grant" if key.endswith("_kind") else "unrecorded"
                             if key.endswith("_origin_status") else "") for key, value in raw.items()):
            raise SourceRepairError("External language fields require their explicit confirmation.")
    by_name = {"language_slot_" + row["slot_id"]: row for row in fields}
    decisions = []
    for key, value in values.items():
        if (type(key) is not str or len(key) > 160 or type(value) is not str
                or len(value) > 512 or "\x00" in value or key not in by_name):
            raise SourceRepairError("Only current displayed language slots may be submitted.")
        row = by_name[key]
        if value == "keep":
            continue
        if value == "declined" and row["can_decline"]:
            decisions.append({"slot_id": row["slot_id"], "outcome": "declined"})
        elif value.startswith("selected:") and row["can_select"] and value[9:] in row["options"]:
            decisions.append({"slot_id": row["slot_id"], "outcome": "selected", "selected_value": value[9:]})
        elif value in {choice["value"] for choice in row.get("adoption_options", [])}:
            _, permission, label = value.split(":", 2)
            decisions.append({"slot_id": row["slot_id"], "outcome": "adopted",
                "selected_value": label, "permission": permission})
        else:
            raise SourceRepairError("The selected language decision is unavailable for this slot.")
    return operation({"kind": OPERATION, "decisions": decisions,
                      **({"external_acquisition": declaration} if declaration is not None else {})})


@dataclass(frozen=True, slots=True)
class PendingElectiveDecision:
    candidate: CharacterDefinition
    prior_identity: dict[str, Any]
    operation: dict[str, Any]
    outcomes: tuple[dict[str, Any], ...]
    changed_slots: tuple[tuple[str, int], ...]
    slot_contracts: tuple[dict[str, Any], ...]
    decision_id: str
    markers: tuple[dict[str, Any], ...]
    bases: dict[str, str]
    authority: Any
    source_snapshot_digest: str
    refresh: Callable[[], Any] = field(repr=False, compare=False)
    external_adoption: dict[str, Any] | None = field(default=None, repr=False)
    _lineage: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if (type(self._lineage) is not dict or set(self._lineage) != {"issuer", "owner"}
                or self._lineage["issuer"] is not _ISSUER):
            raise SourceRepairError("A pending language decision requires its genuine issuer.")

    def _review_owner(self):
        if (type(self._lineage) is not dict or set(self._lineage) != {"issuer", "owner"}
                or self._lineage["issuer"] is not _ISSUER):
            raise SourceRepairError("The language decision lost its original custody.")
        return self._lineage["owner"]

    def bind_review_owner(self, owner):
        from .character_reconciliation import PendingReviewedSourceProof
        if self._review_owner() is not None or type(owner) is not PendingReviewedSourceProof:
            raise SourceRepairError("A language decision cannot acquire a second review owner.")
        owner.require_complete()
        if owner.native_elective_decision is not self:
            raise SourceRepairError("The language decision belongs to another reviewed proof.")
        self._lineage["owner"] = owner

    def __deepcopy__(self, memo):
        raise SourceRepairError("A pending language decision is not a cloneable authority.")

    def validate_binding(self, prior_record, definition, state, actor_id, *, published_generation=None):
        owner = self._review_owner()
        if owner is not None:
            owner.require_complete()
            if owner.native_elective_decision is not self:
                raise SourceRepairError("The language decision lost its original reviewed owner.")
        historical = published_generation is not None
        if historical:
            from .committed_character_publication import exact_character
            from .committed_source_store import _decode_mapping
            current = exact_character(definition.campaign_slug, definition.character_slug)
            if (type(published_generation) is not int or published_generation != prior_record.committed_revision + 1
                    or current is None or current["tombstone"] or current["revision"] != published_generation
                    or CharacterDefinition.from_dict(_decode_mapping(current["primary_bytes"])).to_dict() != definition.to_dict()
                    or type(current["secondary_bytes"]) is not bytes
                    or hashlib.sha256(current["secondary_bytes"]).hexdigest() != self.prior_identity["prior_import_raw_digest"]):
                raise SourceRepairError("The appended language generation does not match its exact decision.")
        if (type(actor_id) is not int or actor_id != self.prior_identity["actor_user_id"]
                or _record_identity(prior_record, actor_id, historical=historical) != self.prior_identity
                or definition.to_dict() != self.candidate.to_dict()
                or state != prior_record.state_record.state):
            raise SourceRepairError("The language decision target or preserved state changed.")

    def recheck(self, prior_record, definition, state, actor_id):
        self.validate_binding(prior_record, definition, state, actor_id)
        from .character_reconstruction_authority import current_target_tuple
        if current_target_tuple(definition.campaign_slug, definition.character_slug) != (
                self.prior_identity["prior_state_tuple_digest"], self.prior_identity["assignment_digest"]):
            raise SourceRepairError("The language decision state tuple or assignment changed.")
        fresh = self.refresh()
        if (type(fresh) is not PendingElectiveDecision or fresh.candidate.to_dict() != definition.to_dict()
                or fresh.prior_identity != self.prior_identity or fresh.operation != self.operation
                or fresh.outcomes != self.outcomes or fresh.changed_slots != self.changed_slots
                or fresh.slot_contracts != self.slot_contracts
                or fresh.decision_id != self.decision_id or fresh.markers != self.markers
                or fresh.bases != self.bases or fresh.authority.identity != self.authority.identity
                or fresh.external_adoption != self.external_adoption
                or fresh.source_snapshot_digest != self.source_snapshot_digest):
            raise SourceRepairError("The language decision, source or access changed.")
        return fresh.authority

    def validate_external_delta(self, prior_record, definition):
        if self.external_adoption is None:
            raise SourceRepairError("The language Review contains no acquisition.")
        expected = _combined_replay(prior_record.definition, self.operation, self.outcomes,
                                    self.markers, self.external_adoption)
        if expected.to_dict() != definition.to_dict():
            raise SourceRepairError("The combined language Review changed unrelated original fields.")


def _record_identity(record, actor_id, *, historical=False):
    from .character_reconstruction_authority import current_target_tuple
    from .committed_character_publication import exact_character
    definition = record.definition
    state_tuple, assignment, raw_state, logical_state, state_revision = current_target_tuple(
        definition.campaign_slug, definition.character_slug, include_state_identity=True)
    if historical:
        from .db import get_db
        source = get_db().execute("SELECT revision,primary_bytes,primary_sha256,secondary_bytes,tombstone "
            "FROM committed_source_generations WHERE campaign_slug=? AND object_kind='character' "
            "AND object_ref=? AND revision=?", (definition.campaign_slug, definition.character_slug,
                record.committed_revision)).fetchone()
        if source is not None and (type(source["primary_bytes"]) is not bytes
                or hashlib.sha256(source["primary_bytes"]).hexdigest() != source["primary_sha256"]):
            raise SourceRepairError("The prior committed language target bytes changed.")
    else:
        source = exact_character(definition.campaign_slug, definition.character_slug)
    if (source is None or source["tombstone"] or source["revision"] != record.committed_revision
            or type(source["primary_bytes"]) is not bytes or type(source["secondary_bytes"]) is not bytes
            or type(state_revision) is not int or state_revision != record.state_record.revision
            or logical_state != digest(record.state_record.state)):
        raise SourceRepairError("The physical and logical language-decision target changed.")
    return {"campaign_slug": definition.campaign_slug, "character_slug": definition.character_slug,
        "actor_user_id": actor_id, "prior_generation": record.committed_revision,
        "prior_definition_digest": digest(definition.to_dict()),
        "prior_primary_raw_digest": hashlib.sha256(source["primary_bytes"]).hexdigest(),
        "prior_import_digest": digest(record.import_metadata.to_dict()),
        "prior_import_raw_digest": hashlib.sha256(source["secondary_bytes"]).hexdigest(),
        "prior_state_revision": record.state_record.revision,
        "prior_state_digest": logical_state, "prior_state_raw_digest": raw_state,
        "prior_state_tuple_digest": state_tuple, "assignment_digest": assignment}


def _row(slot, intent, decision_id):
    row = {key: deepcopy(slot[key]) for key in
        ("owner_id", "category", "position", "systems_ref", "slot_basis_digest")}
    row.update(schema_version=1, outcome=intent["outcome"], decision_id=decision_id)
    if intent["outcome"] in {"selected", "adopted"}:
        row["selected_value"] = intent["selected_value"]
    if intent["outcome"] == "adopted":
        row["permission"] = intent["permission"]
    return row


def _language_values(definition, service, witnesses):
    """Same validator owns the retained set and the resulting no-grant outcome."""
    from .character_reconstruction_proficiencies import validate_current
    if "languages" in validate_current(definition, service, elective_witnesses=witnesses):
        raise SourceRepairError("Every retained language needs its current source and slot decision.")


def _language_projection(prior, submitted, outcomes):
    payload = deepcopy(prior.to_dict())
    payload["source"]["native_reconstruction_choices"][FRAME_KEY] = deepcopy(list(outcomes))
    # Combined operations contain only declines, so observations stay ordered.
    if "external_acquisition" in submitted:
        payload["proficiencies"]["languages"] = list(prior.proficiencies.get("languages", []))
    return CharacterDefinition.from_dict(payload)


def _combined_replay(prior, submitted, outcomes, markers, external):
    """Exact proposed/saved value replay, never prior custody or issuance."""
    from .character_external_proficiencies import _candidate, ADOPT_EXISTING
    from .character_source_repair import add_numeric_authorization
    if type(external) is not dict or set(external) != {"operation", "acquisition", "authorization", "basis_digest"}:
        raise SourceRepairError("The combined acquisition descriptor is malformed.")
    candidate = _language_projection(prior, submitted, outcomes)
    candidate = _candidate(candidate, external["acquisition"], external["authorization"], operation=ADOPT_EXISTING)
    payload = candidate.to_dict()
    frame = payload["source"]["native_reconstruction_choices"]
    frame["unresolved_proficiencies"] = [name for name in frame.get("unresolved_proficiencies", []) if name != "languages"]
    for marker in markers:
        payload = add_numeric_authorization(payload, marker)
    return CharacterDefinition.from_dict(payload)


def issue_decision(*, record, submitted, actor_id, systems_service, campaign_page_records, refresh):
    from .committed_publication import active
    from .character_source_repair import (load_verified_numeric_actions, load_verified_manual_actions,
        numeric_authorization_record, add_numeric_authorization)
    from .character_source_authority import build_reconciled_source_authority, numeric_target_values
    from .character_reconstruction_authority import retained_reconstruction_source_links
    if (not active() or record.definition.system != "DND-5E" or type(actor_id) is not int
            or actor_id < 1 or type(record.committed_revision) is not int or record.committed_revision < 1
            or not callable(refresh)):
        raise SourceRepairError("A language decision requires an admitted committed Character.")
    submitted = operation(submitted)
    definition = record.definition
    numeric = load_verified_numeric_actions(definition.campaign_slug, definition.character_slug, strict=True)
    manual = load_verified_manual_actions(definition.campaign_slug, definition.character_slug, strict=True)
    # Original reconstruction custody must already authenticate its base inputs.
    prior_authority = build_reconciled_source_authority(definition=definition,
        state=record.state_record.state, state_revision=record.state_record.revision,
        systems_service=systems_service, campaign_page_records=campaign_page_records,
        verified_numeric_actions=numeric, verified_manual_actions=manual)
    declaration = submitted.get("external_acquisition")
    if declaration is not None:
        from .character_read_foundation import read_item_catalog_for_definition
        prior_authority = prior_authority.bind_current_numbers(definition, record.state_record.state,
            systems_service=systems_service, campaign_page_records=campaign_page_records,
            item_catalog=read_item_catalog_for_definition(definition, systems_service=systems_service,
                                                        campaign_page_records=campaign_page_records))
        prior_authority.require_authoring_inputs()
    if any(prior_authority.field_status(f"stats.ability_scores.{ability}.score").status != "VERIFIED"
           or not _hex(prior_authority.numeric_basis_digest(f"stats.ability_scores.{ability}.score"))
           for ability in ("str", "dex", "con", "int", "wis", "cha")):
        raise SourceRepairError("Original reconstructed input custody is unavailable.")
    retained_reconstruction_source_links(definition, numeric)
    admitted = resolve_outcomes(definition, systems_service, numeric)
    slots = {slot["slot_id"]: slot for slot in source_slots(definition, systems_service)}
    prior = _record_identity(record, actor_id)
    decision_id = digest({"domain": "native-language-elective-decision-v1", "prior": prior,
        "operation": submitted, "slots": [slots.get(row["slot_id"]) for row in submitted["decisions"]]})
    changed, result = [], dict(admitted)
    for intent in submitted["decisions"]:
        slot = slots.get(intent["slot_id"])
        if slot is None or not slot["observation"].startswith("__unresolved_"):
            raise SourceRepairError("Only an exact unresolved optional language slot may be decided.")
        key = slot["owner_id"], slot["position"]
        previous = admitted.get(key)
        if declaration is not None and previous is not None:
            raise SourceRepairError("A combined confirmation requires previously undecided unused slots.")
        if intent["outcome"] == "selected":
            if previous is None or previous["outcome"] != "declined" or intent["selected_value"] not in slot["options"]:
                raise SourceRepairError("A later language selection must explicitly supersede its valid decline.")
        elif intent["outcome"] == "adopted":
            if previous is not None:
                raise SourceRepairError("Only an undecided source slot may adopt an observed language.")
        elif previous is not None:
            if previous["outcome"] != "declined":
                raise SourceRepairError("A selected language cannot be silently declined.")
            continue  # An authenticated, still-current exact decline is a no-op.
        result[key] = _row(slot, intent, decision_id)
        changed.append(key)
    if not changed:
        if declaration is not None:
            raise SourceRepairError("A combined confirmation requires an actual unused-slot decision.")
        _language_values(definition, systems_service, numeric)
        return None
    rows = [deepcopy(result[key]) for key in sorted(result)]
    payload = deepcopy(definition.to_dict())
    payload["source"]["native_reconstruction_choices"][FRAME_KEY] = rows
    payload["proficiencies"]["languages"] = _decision_languages(definition, submitted,
        [slots[row["slot_id"]] for row in submitted["decisions"]])
    candidate = CharacterDefinition.from_dict(payload)
    pending_witness = PendingElectiveOutcome(rows, origin=("pending_language_decision",
        definition.campaign_slug, definition.character_slug, decision_id, actor_id,
        record.committed_revision + 1, digest(rows)), _issuer=_ISSUER)
    actions = tuple(numeric) + (pending_witness,)
    external = None
    external_target = None
    if declaration is not None:
        from .character_external_proficiencies import (
            language_adoption_descriptor, _require_observation_attribution, _candidate, ADOPT_EXISTING,
            pending_language_adoption, resolve as external_acquisitions, target as external_target_for)
        external_acquisitions(definition, numeric)
        external = language_adoption_descriptor(definition, declaration, actor_id,
            record.committed_revision, record.state_record.revision, digest(record.state_record.state), check_future=True)
        _require_observation_attribution(candidate, external["acquisition"], prior_authority, systems_service, actions)
        candidate = _candidate(candidate, external["acquisition"], external["authorization"], operation=ADOPT_EXISTING)
        external_target = external_target_for(external["acquisition"])
        pending_acquisition = pending_language_adoption(candidate, external, actor_id=actor_id,
            state=record.state_record.state, decision_id=decision_id, prior_identity=prior)
        actions += (pending_acquisition, {"authorization": external["authorization"],
                                        "source_basis_digest": external["basis_digest"]})
    _language_values(candidate, systems_service, actions)
    frame = candidate.source["native_reconstruction_choices"]
    frame["unresolved_proficiencies"] = [name for name in frame.get("unresolved_proficiencies", []) if name != "languages"]
    def authority_for(value, witnesses):
        return build_reconciled_source_authority(definition=value, state=record.state_record.state,
            state_revision=record.state_record.revision, systems_service=systems_service,
            campaign_page_records=campaign_page_records, verified_numeric_actions=witnesses,
            verified_manual_actions=manual)
    authority = authority_for(candidate, actions)
    values = numeric_target_values(candidate, record.state_record.state)
    markers, bases = [], {}
    for (kind, path, metric), value in values.items():
        if kind != "proficiency" or not path.startswith("proficiencies.languages."):
            continue
        if path == external_target:
            continue  # Keep the independently owned external marker, never lend a source slot.
        basis = authority.numeric_basis_digest(path)
        if not _hex(basis):
            raise SourceRepairError("A current language has no closed native source basis.")
        marker = numeric_authorization_record(character_slug=definition.character_slug,
            target_kind=kind, target_id=path, metric=metric, raw_value=value,
            action_id=decision_id, provenance=PROVENANCE)
        payload = add_numeric_authorization(candidate.to_dict(), marker)
        candidate = CharacterDefinition.from_dict(payload)
        markers.append(marker)
        bases[path] = basis
    if (not markers and external is None) or len(markers) > MAX_OUTCOMES:
        raise SourceRepairError("The current retained language set has no bounded native witnesses.")
    actions += tuple({"authorization": marker, "source_basis_digest": bases[marker["target_id"]]} for marker in markers)
    authority = authority_for(candidate, actions)
    proof = PendingElectiveDecision(candidate, prior, submitted, tuple(rows), tuple(changed),
        tuple(deepcopy(slots[row["slot_id"]]) for row in submitted["decisions"]),
        decision_id, tuple(markers), bases, authority, authority.source_snapshot_digest, refresh,
        external_adoption=external,
        _lineage={"issuer": _ISSUER, "owner": None})
    if external is not None:
        proof.validate_external_delta(record, candidate)
    return proof


def validate_transition(prior, candidate, proof=None, *, actor_id=None, state=None):
    old, new = outcome_rows(prior.definition), outcome_rows(candidate)
    if old == new:
        return
    if type(proof) is not PendingElectiveDecision:
        raise SourceRepairError("Language outcome changes require the exact reviewed manager decision.")
    proof.validate_binding(prior, candidate, state, actor_id)
    if proof.external_adoption is not None:
        proof.validate_external_delta(prior, candidate)
        return
    if candidate.proficiencies.get("languages", []) != _decision_languages(
            prior.definition, proof.operation, proof.slot_contracts):
        raise SourceRepairError("The reviewed language observation order or declared grant changed.")
    # Only the additive vector, resolved language debt, explicit language set and
    # its new markers may differ; all original source observations are immutable.
    before, after = deepcopy(prior.definition.to_dict()), deepcopy(candidate.to_dict())
    for payload in (before, after):
        frame = payload["source"]["native_reconstruction_choices"]
        frame.pop(FRAME_KEY, None)
        frame["unresolved_proficiencies"] = [name for name in frame.get("unresolved_proficiencies", []) if name != "languages"]
        payload["proficiencies"].pop("languages", None)
        payload["source"]["source_authorizations"] = [row for row in payload["source"].get("source_authorizations", [])
            if not (row.get("target_kind") == "proficiency"
                and type(row.get("target_id")) is str and row["target_id"].startswith("proficiencies.languages."))]
    if before != after:
        raise SourceRepairError("A language decision changed an unrelated original input or observation.")


def historical_choices_equal(prior, candidate, *, exact=False):
    """Retained historical links cannot become new claims with this additive field."""
    left = deepcopy(prior.source.get("native_reconstruction_choices"))
    right = deepcopy(candidate.source.get("native_reconstruction_choices"))
    if type(left) is not dict or type(right) is not dict:
        return digest(left) == digest(right) if exact else left == right
    for frame in (left, right):
        frame.pop(FRAME_KEY, None)
        frame["unresolved_proficiencies"] = [name for name in frame.get("unresolved_proficiencies", []) if name != "languages"]
    return digest(left) == digest(right) if exact else left == right


def prepare_decision_state(prior_record, definition, state, proof, actor_id, *, exact_state_json=None):
    from .character_store import PreparedCharacterState
    validate_transition(prior_record, definition, proof, actor_id=actor_id, state=state)
    if state != prior_record.state_record.state:
        raise SourceRepairError("A language decision must preserve the complete play-state row.")
    raw = exact_state_json if exact_state_json is not None else json.dumps(state, ensure_ascii=False, sort_keys=True)
    if type(raw) is not str or json.loads(raw) != state:
        raise SourceRepairError("The exact current state serialization changed.")
    return PreparedCharacterState(deepcopy(state), raw)


def _decode_external_receipt(value, *, version, character_slug):
    """Decode only the closed numeric fragment, never credential-shaped data.

    Receipt2 retains its original spelling and digest. Receipt3 uses an explicit
    numeric marker field; the in-memory producer descriptor remains unchanged.
    Decoding supplies values for replay, never acquisition custody.
    """
    from .character_external_proficiencies import (
        ADOPT_EXISTING, FIELDS, PROVENANCE as external_provenance,
        language_declaration, target, basis)
    from .character_source_repair import _valid_numeric_witness_marker
    from .character_source_authority import numeric_value_digest
    marker_key = "authorization" if version == 2 else "numeric_marker"
    if (type(version) is not int or version not in {2, 3}
            or not _keys(value, 4) or set(value) != {"operation", "acquisition", marker_key, "basis_digest"}
            or type(value["operation"]) is not str or value["operation"] != ADOPT_EXISTING):
        raise SourceRepairError("The combined language receipt fragment is malformed.")
    row, marker = value["acquisition"], value[marker_key]
    if (not _keys(row, len(FIELDS)) or set(row) != FIELDS
            or type(row["schema_version"]) is not int or row["schema_version"] != 1
            or not _hex(row["id"]) or row["category"] != "languages"):
        raise SourceRepairError("The combined language acquisition is malformed.")
    declaration = language_declaration({"operation": ADOPT_EXISTING,
        **{key: row[key] for key in ("category", "name", "kind", "origin", "occurred_at", "evidence")}})
    if row != {"schema_version": 1, "id": row["id"],
               **{key: child for key, child in declaration.items() if key != "operation"}}:
        raise SourceRepairError("The combined language acquisition is not canonical.")
    if (not _keys(marker, 8) or set(marker) != {"schema_version", "character_slug", "target_kind",
            "target_id", "metric", "value_digest", "action_id", "provenance"}
            or any(type(marker[key]) is not str for key in marker if key != "schema_version")
            or not _valid_numeric_witness_marker(marker, character_slug, external_provenance)
            or marker["target_kind"] != "proficiency" or marker["metric"] != "grant"
            or marker["target_id"] != target(row) or marker["action_id"] != row["id"]
            or marker["value_digest"] != numeric_value_digest(row["name"])
            or not _hex(value["basis_digest"]) or value["basis_digest"] != basis(row)):
        raise SourceRepairError("The combined language numeric marker or basis changed.")
    return {"operation": ADOPT_EXISTING, "acquisition": deepcopy(row),
            "authorization": deepcopy(marker), "basis_digest": value["basis_digest"]}


def _encode_external_receipt(value, *, character_slug):
    """Persist only a validated numeric marker under its unambiguous name."""
    admitted = _decode_external_receipt(value, version=2, character_slug=character_slug)
    return {"operation": admitted["operation"], "acquisition": admitted["acquisition"],
            "numeric_marker": admitted["authorization"], "basis_digest": admitted["basis_digest"]}


def _metadata_values(proof, *, definition, prior_record, state, actor_id, generation,
                     review_digest, plan_digest, source_digest, policy_digest, review_basis):
    """Deterministic plain values shared by prewrite and actual confirmation."""
    review_fields = {"actor_user_id", "campaign_slug", "character_slug", "prior_generation",
        "primary_sha256", "secondary_sha256", "state_revision", "state_digest", "source_digest",
        "policy_digest", "plan_digest", "native_digest", "semantic_digest"}
    if (any(not _hex(value) for value in (review_digest, plan_digest, source_digest, policy_digest))
            or type(generation) is not int or generation != prior_record.committed_revision + 1
            or not _keys(review_basis) or set(review_basis) != review_fields
            or any(not _hex(review_basis[key]) for key in ("primary_sha256", "secondary_sha256",
                "state_digest", "source_digest", "policy_digest", "plan_digest", "native_digest", "semantic_digest"))
            or review_basis.get("actor_user_id") != actor_id
            or type(review_basis.get("actor_user_id")) is not int
            or (review_basis.get("campaign_slug"), review_basis.get("character_slug")) != (
                definition.campaign_slug, definition.character_slug)
            or type(review_basis.get("prior_generation")) is not int
            or review_basis["prior_generation"] != prior_record.committed_revision
            or type(review_basis.get("state_revision")) is not int
            or review_basis["state_revision"] != prior_record.state_record.revision
            or review_basis.get("state_digest") != proof.prior_identity["prior_state_raw_digest"]
            or digest(state) != proof.prior_identity["prior_state_digest"]
            or review_basis.get("primary_sha256") != proof.prior_identity["prior_primary_raw_digest"]
            or review_basis.get("secondary_sha256") != proof.prior_identity["prior_import_raw_digest"]
            or review_basis.get("plan_digest") != plan_digest
            or review_basis.get("source_digest") != source_digest
            or review_basis.get("policy_digest") != policy_digest):
        raise SourceRepairError("The signed language review basis changed before confirmation.")
    if proof.external_adoption is not None:
        proof.validate_external_delta(prior_record, definition)
    receipt = {"schema_version": 3 if proof.external_adoption is not None else 1, **deepcopy(proof.prior_identity),
        "decision_id": proof.decision_id, "review_digest": review_digest,
        "plan_digest": plan_digest, "source_digest": source_digest, "policy_digest": policy_digest,
        "published_generation": generation, "definition_digest": digest(definition.to_dict()),
        "outcomes": deepcopy(list(proof.outcomes)), "changed_slots": [list(key) for key in proof.changed_slots],
        "operation": deepcopy(proof.operation), "slot_contracts": deepcopy(list(proof.slot_contracts)),
        "language_authorizations": deepcopy(list(proof.markers)), "language_basis_digests": deepcopy(proof.bases)}
    if proof.external_adoption is not None:
        receipt["external_acquisition"] = _encode_external_receipt(
            proof.external_adoption, character_slug=definition.character_slug)
    return {"manager_action": OPERATION, OPERATION: receipt,
        "numeric_actor_id": actor_id, "action_id": proof.decision_id,
        "source_snapshot_digest": proof.source_snapshot_digest,
        "definition_digest": receipt["definition_digest"], "published_definition_digest": receipt["definition_digest"],
        "published_revision": generation, "published_state_revision": prior_record.state_record.revision,
        "preserved_state_digest": digest(state), "preserved_state_raw_digest": proof.prior_identity["prior_state_raw_digest"],
        "preserved_state_tuple_digest": proof.prior_identity["prior_state_tuple_digest"],
        "preserved_assignment_digest": proof.prior_identity["assignment_digest"]}


def prospective_metadata(proof, *, definition, prior_record, state, actor_id, generation,
                         review_digest, plan_digest, source_digest, policy_digest, review_basis):
    """Preflight values for the expected next generation, never confirmation."""
    if type(proof) is not PendingElectiveDecision:
        raise SourceRepairError("A prospective language audit requires its genuine reviewed proof.")
    proof.validate_binding(prior_record, definition, state, actor_id)
    return _metadata_values(proof, definition=definition, prior_record=prior_record,
        state=state, actor_id=actor_id, generation=generation, review_digest=review_digest,
        plan_digest=plan_digest, source_digest=source_digest, policy_digest=policy_digest,
        review_basis=review_basis)


def confirmed_metadata(proof, *, definition, prior_record, state, actor_id, generation,
                       review_digest, plan_digest, source_digest, policy_digest, review_basis):
    """Confirm actual appended generation/import binding before emitting values."""
    if type(proof) is not PendingElectiveDecision:
        raise SourceRepairError("A confirmed language audit requires its genuine reviewed proof.")
    proof.validate_binding(prior_record, definition, state, actor_id, published_generation=generation)
    return _metadata_values(proof, definition=definition, prior_record=prior_record,
        state=state, actor_id=actor_id, generation=generation, review_digest=review_digest,
        plan_digest=plan_digest, source_digest=source_digest, policy_digest=policy_digest,
        review_basis=review_basis)


def _observe_language_admission(kind, *, audit_row=None, refusal=0, error=None,
                                succeeded=False, row=None, slot=None, latest=None,
                                result=None):
    """Optional private observation; never a source of authority or a refusal."""
    try:
        from flask import current_app, has_app_context
        if not has_app_context():
            return
        observer = current_app.extensions.get("character_language_admission_observer")
        if not callable(observer):
            return
        fact = {"kind": kind}
        if kind == "verified_batch":
            identity = audit_row["id"]
            fact.update(audit_id=identity if type(identity) is int else None,
                        refusal=refusal, succeeded=succeeded)
        elif kind == "slot":
            fact.update(slot_present=slot is not None,
                witness_equal=latest == row,
                source_ref_equal=slot is not None and row["systems_ref"] == slot["systems_ref"],
                basis_equal=slot is not None and row["slot_basis_digest"] == slot["slot_basis_digest"],
                selection_legal=slot is not None and (
                    _adoption_allowed(slot, row["selected_value"], row["permission"])
                    if row["outcome"] == "adopted" else row["outcome"] != "selected"
                        or row["selected_value"] in slot["options"]),
                original_unresolved=slot is not None and slot["observation"].startswith("__unresolved_"))
        elif kind == "vector":
            fact.update(authenticated_slots=len(latest), retained_slots=len(result))
        else:
            return
        observer(fact, error)
    except BaseException:
        pass  # Observation must not replace any domain return or exception.


def verified_decision_batch(connection, campaign, character, audit_row, metadata, prior_witnesses):
    """One forward audit pass; no authority builds or recursive action loading."""
    from .character_native_requalification import _generation
    from .committed_source_store import _decode_mapping
    from .character_models import CharacterImportMetadata
    from .character_source_repair import _valid_numeric_witness_marker
    from .character_source_authority import numeric_target_values, numeric_value_digest
    from .repository import normalize_lookup
    receipt = metadata.get(OPERATION)
    fields = {"schema_version", "campaign_slug", "character_slug", "actor_user_id",
        "decision_id", "review_digest", "plan_digest", "source_digest", "policy_digest",
        "prior_generation", "published_generation", "prior_definition_digest", "definition_digest",
        "prior_primary_raw_digest", "prior_import_digest", "prior_import_raw_digest", "prior_state_revision",
        "prior_state_digest", "prior_state_raw_digest", "prior_state_tuple_digest",
        "assignment_digest", "outcomes", "changed_slots", "operation", "slot_contracts",
        "language_authorizations", "language_basis_digests"}
    combined = type(receipt) is dict and type(receipt.get("schema_version")) is int and receipt["schema_version"] in {2, 3}
    if combined:
        fields.add("external_acquisition")
    refusal, observed_error, succeeded = 0, None, False
    try:
        actor = audit_row["actor_user_id"]
        reviewed = metadata.get("language_review_basis")
        review_fields = {"actor_user_id", "campaign_slug", "character_slug", "prior_generation",
            "primary_sha256", "secondary_sha256", "state_revision", "state_digest", "source_digest",
            "policy_digest", "plan_digest", "native_digest", "semantic_digest"}
        if (audit_row["event_type"] != "character_update_applied" or type(actor) is not int or actor < 1
                or type(audit_row["metadata_json"]) is not str or len(audit_row["metadata_json"].encode("utf-8")) > 65536
                or type(audit_row["id"]) is not int or not _keys(receipt) or set(receipt) != fields
                or not _keys(reviewed) or set(reviewed) != review_fields
                or type(receipt["schema_version"]) is not int or receipt["schema_version"] not in {1, 2, 3}
                or metadata.get("source") != "character_update_preview" or metadata.get("manager_action") != OPERATION
                or metadata.get("numeric_actor_id") != actor or type(metadata.get("numeric_actor_id")) is not int
                or metadata.get("action_id") != receipt["decision_id"]
                or receipt["actor_user_id"] != actor or type(receipt["actor_user_id"]) is not int
                or (receipt["campaign_slug"], receipt["character_slug"]) != (campaign, character)
                or any(not _hex(receipt[key]) for key in ("decision_id", "review_digest", "plan_digest",
                    "source_digest", "policy_digest", "prior_definition_digest", "definition_digest",
                    "prior_primary_raw_digest", "prior_import_digest", "prior_import_raw_digest", "prior_state_digest",
                    "prior_state_raw_digest", "prior_state_tuple_digest", "assignment_digest"))
                or any(type(receipt[key]) is not int or receipt[key] < 1
                    for key in ("prior_generation", "published_generation", "prior_state_revision"))
                or receipt["published_generation"] != receipt["prior_generation"] + 1
                or receipt["review_digest"] != metadata.get("review_digest")
                or receipt["plan_digest"] != metadata.get("candidate_digest")
                or receipt["plan_digest"] != metadata.get("plan_digest")
                or receipt["definition_digest"] != metadata.get("published_definition_digest")
                or receipt["published_generation"] != metadata.get("published_revision")
                or receipt["prior_state_revision"] != metadata.get("published_state_revision")
                or receipt["prior_state_digest"] != metadata.get("preserved_state_digest")
                or receipt["prior_state_raw_digest"] != metadata.get("preserved_state_raw_digest")
                or receipt["prior_state_tuple_digest"] != metadata.get("preserved_state_tuple_digest")
                or receipt["assignment_digest"] != metadata.get("preserved_assignment_digest")
                or type(receipt["outcomes"]) is not list or not 1 <= len(receipt["outcomes"]) <= MAX_OUTCOMES):
            refusal = 1
            return ()
        if (type(reviewed["actor_user_id"]) is not int or reviewed["actor_user_id"] != actor
                or (reviewed["campaign_slug"], reviewed["character_slug"]) != (campaign, character)
                or type(reviewed["prior_generation"]) is not int or reviewed["prior_generation"] != receipt["prior_generation"]
                or type(reviewed["state_revision"]) is not int or reviewed["state_revision"] != receipt["prior_state_revision"]
                or reviewed["state_digest"] != receipt["prior_state_raw_digest"]
                or reviewed["primary_sha256"] != receipt["prior_primary_raw_digest"]
                or reviewed["secondary_sha256"] != receipt["prior_import_raw_digest"]
                or reviewed["source_digest"] != receipt["source_digest"] or reviewed["policy_digest"] != receipt["policy_digest"]
                or reviewed["plan_digest"] != receipt["plan_digest"]
                or any(not _hex(reviewed[key]) for key in ("primary_sha256", "secondary_sha256", "state_digest",
                    "source_digest", "policy_digest", "plan_digest", "native_digest", "semantic_digest"))):
            refusal = 2
            return ()
        payload, generation = _generation(connection, campaign, character,
            receipt["definition_digest"], actor, receipt["published_generation"])
        definition = CharacterDefinition.from_dict(payload)
        if outcome_rows(definition) != receipt["outcomes"]:
            refusal = 3
            return ()
        submitted = operation(receipt["operation"])
        if ("external_acquisition" in submitted) != combined:
            return ()
        contracts = receipt["slot_contracts"]
        if type(contracts) is not list or len(contracts) != len(submitted["decisions"]):
            refusal = 4
            return ()
        prior_keys = {"campaign_slug", "character_slug", "actor_user_id", "prior_generation",
            "prior_definition_digest", "prior_primary_raw_digest", "prior_import_digest", "prior_import_raw_digest",
            "prior_state_revision", "prior_state_digest", "prior_state_raw_digest",
            "prior_state_tuple_digest", "assignment_digest"}
        prior_identity = {key: receipt[key] for key in prior_keys}
        if digest({"domain": "native-language-elective-decision-v1", "prior": prior_identity,
                "operation": submitted, "slots": contracts}) != receipt["decision_id"]:
            refusal = 5
            return ()
        contract_keys = {"campaign_slug", "character_slug", "owner_id", "category", "position", "systems_ref",
            "slot_basis_digest", "slot_id", "options", "ordered_domains", "observation", "unresolved_marker"}
        for intent, slot in zip(submitted["decisions"], contracts):
            if (not _keys(slot) or set(slot) != contract_keys or slot["slot_id"] != intent["slot_id"]
                    or (slot["campaign_slug"], slot["character_slug"]) != (campaign, character)
                    or type(slot["owner_id"]) is not str or slot["category"] != "languages"
                    or type(slot["position"]) is not int or not 0 <= slot["position"] < MAX_OUTCOMES
                    or not _ref(slot["systems_ref"]) or type(slot["ordered_domains"]) is not list
                    or not 1 <= len(slot["ordered_domains"]) <= MAX_OUTCOMES
                    or any(type(domain) is not list or not 1 <= len(domain) <= 128
                        or any(type(label) is not str or not 1 <= len(label) <= 160 for label in domain)
                        for domain in slot["ordered_domains"])
                    or slot["position"] >= len(slot["ordered_domains"])
                    or slot["options"] != slot["ordered_domains"][slot["position"]]
                    or type(slot["observation"]) is not str or not slot["observation"].startswith("__unresolved_")
                    or type(slot["unresolved_marker"]) is not str):
                refusal = 6
                return ()
            basis = digest({"domain": "language-elective-slot-v1", "system": definition.system,
                "owner_id": slot["owner_id"], "systems_ref": slot["systems_ref"], "category": "languages",
                "ordered_domains": slot["ordered_domains"], "position": slot["position"]})
            identity = {key: slot[key] for key in ("campaign_slug", "character_slug", "owner_id", "category",
                "position", "systems_ref", "slot_basis_digest")}
            if basis != slot["slot_basis_digest"] or digest(identity) != slot["slot_id"]:
                refusal = 7
                return ()
            if intent["outcome"] == "selected" and intent["selected_value"] not in slot["options"]:
                refusal = 8
                return ()
            if intent["outcome"] == "adopted" and not _adoption_allowed(
                    slot, intent["selected_value"], intent["permission"]):
                refusal = 8
                return ()
        prior_row = connection.execute("SELECT actor_user_id,primary_sha256,secondary_bytes FROM committed_source_generations "
            "WHERE campaign_slug=? AND object_kind='character' AND object_ref=? AND revision=?",
            (campaign, character, receipt["prior_generation"])).fetchone()
        if (prior_row is None or type(prior_row["actor_user_id"]) is not int
                or prior_row["primary_sha256"] != reviewed["primary_sha256"]
                or type(prior_row["secondary_bytes"]) is not bytes
                or hashlib.sha256(prior_row["secondary_bytes"]).hexdigest() != reviewed["secondary_sha256"]
                or digest(CharacterImportMetadata.from_dict(_decode_mapping(prior_row["secondary_bytes"])).to_dict())
                    != receipt["prior_import_digest"]):
            refusal = 9
            return ()
        published_import = connection.execute("SELECT secondary_bytes FROM committed_source_generations "
            "WHERE campaign_slug=? AND object_kind='character' AND object_ref=? AND revision=?",
            (campaign, character, receipt["published_generation"])).fetchone()
        if (published_import is None or digest(CharacterImportMetadata.from_dict(
                _decode_mapping(published_import["secondary_bytes"])).to_dict()) != receipt["prior_import_digest"]):
            refusal = 10
            return ()
        if published_import["secondary_bytes"] != prior_row["secondary_bytes"]:
            refusal = 11
            return ()
        before, _ = _generation(connection, campaign, character,
            receipt["prior_definition_digest"], prior_row["actor_user_id"], receipt["prior_generation"])
        prior = CharacterDefinition.from_dict(before)
        from .character_reconstruction_authority import retained_reconstruction_source_links
        retained_reconstruction_source_links(prior, prior_witnesses, connection=connection)
        external = None
        external_target = None
        if combined:
            from .character_external_proficiencies import (language_adoption_descriptor,
                resolve as external_acquisitions, target as external_target_for)
            external_acquisitions(prior, prior_witnesses)
            external = language_adoption_descriptor(prior, submitted["external_acquisition"], actor,
                receipt["prior_generation"], receipt["prior_state_revision"], receipt["prior_state_digest"])
            if _decode_external_receipt(receipt["external_acquisition"],
                    version=receipt["schema_version"], character_slug=character) != external:
                return ()
            external_target = external_target_for(external["acquisition"])
        previous = {(row["owner_id"], row["position"]): row for row in outcome_rows(prior)}
        current = {(row["owner_id"], row["position"]): row for row in receipt["outcomes"]}
        changed = receipt["changed_slots"]
        if (type(changed) is not list or not 1 <= len(changed) <= MAX_OUTCOMES
                or any(type(key) is not list or len(key) != 2 or type(key[0]) is not str
                       or type(key[1]) is not int for key in changed)):
            refusal = 12
            return ()
        changed = [tuple(key) for key in changed]
        if len(changed) != len(set(changed)) or set(changed) != {key for key in current if current[key] != previous.get(key)}:
            refusal = 13
            return ()
        by_slot = {slot["slot_id"]: slot for slot in contracts}
        described_changes = set()
        for intent in submitted["decisions"]:
            slot = by_slot[intent["slot_id"]]
            key = slot["owner_id"], slot["position"]
            row = current.get(key)
            if key in changed:
                if row != _row(slot, intent, receipt["decision_id"]):
                    refusal = 14
                    return ()
                described_changes.add(key)
            elif intent["outcome"] != "declined" or previous.get(key, {}).get("outcome") != "declined":
                refusal = 15
                return ()
        if described_changes != set(changed):
            refusal = 16
            return ()
        custody = {}
        for witness in prior_witnesses:
            if type(witness) is NativeElectiveDecision:
                for row in witness["outcomes"]:
                    if row["decision_id"] == receipt["decision_id"]:
                        refusal = 23
                        return ()  # One decision cannot acquire a second receipt.
                    custody[row["owner_id"], row["position"]] = row
        # A carried outcome retains its original decision id and exact prior
        # authenticated custody. Changed rows alone acquire this new decision.
        if (set(previous) - set(current) or any(custody.get(key) != row for key, row in previous.items())
                or any(row["decision_id"] != receipt["decision_id"] for key, row in current.items() if key in changed)
                or any(previous.get(key) != row for key, row in current.items() if key not in changed)
                or any(previous.get(key, {}).get("outcome") != "declined"
                       for key in changed if current[key]["outcome"] == "selected")
                or any(key in previous for key in changed if current[key]["outcome"] == "declined")):
            refusal = 17
            return ()
        if (any(key in previous for key in changed if current[key]["outcome"] == "adopted")
                or len({normalize_lookup(row["selected_value"]) for row in current.values()
                    if row["outcome"] in {"selected", "adopted"}})
                    != sum(row["outcome"] in {"selected", "adopted"} for row in current.values())):
            refusal = 17
            return ()
        # Only the declared language delta is admissible. No original input,
        # source ref, ability/HP recipe, retained import or unrelated marker moves.
        old, new = deepcopy(before), deepcopy(payload)
        old = CharacterDefinition.from_dict(old).to_dict()
        new = deepcopy(definition.to_dict())
        for frame in (old, new):
            choices = frame["source"]["native_reconstruction_choices"]
            choices.pop(FRAME_KEY, None)
            choices["unresolved_proficiencies"] = [name for name in choices.get("unresolved_proficiencies", []) if name != "languages"]
            frame["proficiencies"].pop("languages", None)
            frame["source"]["source_authorizations"] = [row for row in frame["source"].get("source_authorizations", [])
                if not (row.get("target_kind") == "proficiency" and type(row.get("target_id")) is str
                    and row["target_id"].startswith("proficiencies.languages."))]
        if not combined and old != new:
            refusal = 18
            return ()
        expected_languages = _decision_languages(prior, submitted, contracts)
        if definition.proficiencies.get("languages", []) != expected_languages:
            refusal = 19
            return ()
        batch, bases = receipt["language_authorizations"], receipt["language_basis_digests"]
        values = numeric_target_values(definition, {})
        targets = {path: (metric, value) for (kind, path, metric), value in values.items()
            if kind == "proficiency" and path.startswith("proficiencies.languages.")}
        if combined:
            if external_target not in targets:
                return ()
            del targets[external_target]
        if (type(batch) is not list or not (0 if combined else 1) <= len(batch) <= MAX_OUTCOMES or type(bases) is not dict
                or len(batch) != len(targets) or set(bases) != set(targets)
                or any(not _hex(value) for value in bases.values())):
            refusal = 20
            return ()
        stored = definition.source.get("source_authorizations", [])
        seen = set()
        for marker in batch:
            if (not _valid_numeric_witness_marker(marker, character, PROVENANCE)
                    or marker["target_kind"] != "proficiency" or marker["metric"] != "grant"
                    or marker["target_id"] not in targets or marker["target_id"] in seen
                    or marker["action_id"] != receipt["decision_id"] or stored.count(marker) != 1
                    or marker["value_digest"] != numeric_value_digest(targets[marker["target_id"]][1])):
                refusal = 21
                return ()
            seen.add(marker["target_id"])
        if combined:
            expected = _combined_replay(prior, submitted, receipt["outcomes"], batch, external)
            if (expected.to_dict() != definition.to_dict()
                    or any((row["owner_id"], row["position"]) in previous for row in contracts)
                    or not _valid_numeric_witness_marker(external["authorization"], character, "native_external_proficiency")
                    or external["authorization"]["value_digest"] != numeric_value_digest(
                        values[("proficiency", external_target, "grant")])
                    or stored.count(external["authorization"]) != 1):
                return ()
            from .character_update_apply import canonical_digest, _semantic_rows_payload
            from .character_reconstruction_routes import language_elective_semantic_rows
            if (canonical_digest({"operation": submitted, "definition": definition.to_dict(),
                    "source": receipt["source_digest"], "policy": receipt["policy_digest"]}) != receipt["plan_digest"]
                    or canonical_digest({"operation": submitted, "outcomes": receipt["outcomes"]}) != reviewed["native_digest"]
                    or canonical_digest(_semantic_rows_payload(language_elective_semantic_rows(prior, definition)))
                        != reviewed["semantic_digest"]):
                return ()
        witness = NativeElectiveDecision(receipt["outcomes"], origin=("confirmed_language_decision",
            campaign, character, audit_row["id"], actor, generation["revision"], digest(receipt)), _issuer=_ISSUER)
        result = (witness, *( {"authorization": deepcopy(marker), "source_basis_digest": bases[marker["target_id"]]}
                          for marker in batch))
        if combined:
            from .character_external_proficiencies import custody
            result += (custody(definition, external["acquisition"], origin=("confirmed_external_proficiency",
                audit_row["id"], actor, generation["revision"], receipt["definition_digest"])),
                {"authorization": deepcopy(external["authorization"]), "source_basis_digest": external["basis_digest"]})
        succeeded = True
        return result
    except (KeyError, TypeError, ValueError) as error:
        observed_error = error
        refusal = 22
        return ()
    finally:
        _observe_language_admission("verified_batch", audit_row=audit_row,
            refusal=refusal, error=observed_error, succeeded=succeeded)

def confirmed_batch_for_audit(witnesses, audit_id, metadata):
    """Forward already-admitted custody into renewal; never reload an audit."""
    receipt = metadata.get(OPERATION)
    if (type(receipt) is not dict or type(receipt.get("schema_version")) is not int
            or receipt["schema_version"] not in {1, 2, 3}):
        return ()
    matches = [witness for witness in witnesses if type(witness) is NativeElectiveDecision
        and witness.origin[0] == "confirmed_language_decision" and witness.origin[3] == audit_id
        and witness.origin[6] == digest(receipt) and witness.get("outcomes") == receipt.get("outcomes")]
    if len(matches) != 1:
        return ()
    markers = receipt.get("language_authorizations")
    bases = receipt.get("language_basis_digests")
    if type(markers) is not list or type(bases) is not dict:
        return ()
    accepted = tuple(witness for witness in witnesses if type(witness) is dict
        and witness.get("authorization") in markers
        and witness.get("source_basis_digest") == bases.get(witness.get("authorization", {}).get("target_id")))
    if len(accepted) != len(markers):
        return ()
    if receipt["schema_version"] in {2, 3}:
        from .character_external_proficiencies import ExternalProficiencyCustody
        try:
            external = _decode_external_receipt(receipt.get("external_acquisition"),
                version=receipt["schema_version"], character_slug=receipt.get("character_slug"))
        except (KeyError, TypeError, ValueError):
            return ()
        custody = [witness for witness in witnesses if type(witness) is ExternalProficiencyCustody
            and witness.origin == ("confirmed_external_proficiency", audit_id, receipt.get("actor_user_id"),
                receipt.get("published_generation"), receipt.get("definition_digest"))
            and witness.get("acquisition") == external.get("acquisition")]
        external_markers = [witness for witness in witnesses if type(witness) is dict
            and witness.get("authorization") == external.get("authorization")
            and witness.get("source_basis_digest") == external.get("basis_digest")]
        if len(custody) != 1 or len(external_markers) != 1:
            return ()
        accepted += tuple(external_markers)
    return accepted


# Finite ordinary callback surface omitted by invocation-owned current inputs.
_CURRENT_INPUT_RECIPE = tuple((name, globals()[name]) for name in (
    'resolve_outcomes',
    'language_basis',
    'source_slots',
))
