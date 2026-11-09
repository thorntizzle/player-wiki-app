"""Bounded manager renewal from confirmed native inputs and current sources.

This module never publishes, writes state, or treats a saved total as an input.
Its pending markers are usable only by the reviewed publication boundary; the
separate confirmed-audit loader qualifies the eventual durable result.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
import hashlib
import json
from typing import Any

from .character_models import CharacterDefinition
from .character_source_repair import SourceRepairError


def _digest(value: Any) -> str:
    from .character_update_apply import canonical_digest
    return canonical_digest(value)


def _fail() -> None:
    raise SourceRepairError("Confirmed native inputs or their current source ownership need repair.")


def _check_prospective_aggregate_parity(
    candidate, state, authority, validated_batch, *,
    systems_service, campaign_page_records, source_read_phase,
):
    """Check new native aggregate output using the genuine current read binder.

    Inputs are the actual private producer's already validated candidate/state,
    already built SourceAuthority and newly generated batch. Ordinary pending
    dictionaries remain ordinary pending dictionaries. Nothing is retyped into
    NativeAggregateWitness, persisted, or granted durable origin/history proof.

    Exactly one bind_current_numbers delegate is called for a native batch.
    Original binder/phase exceptions propagate unchanged. No new callback or
    cleanup owner is introduced. Raw/effective outputs are compared only as
    exact primitive values/types; bool never stands in for a numeric total.
    """
    from dataclasses import fields, replace
    import math
    from .character_models import CharacterDefinition
    from .character_source_authority import (
        SourceAuthority, EffectiveStatus, NATIVE_BASELINE_FIELDS,
        VERIFIED, UNKNOWN, CONFLICT, numeric_target_values, numeric_value_digest,
    )

    if (type(candidate) is not CharacterDefinition or type(authority) is not SourceAuthority
            or type(state) is not dict or type(validated_batch) is not tuple
            or not 1 <= len(validated_batch) <= 128):
        _fail()
    candidate_digest = numeric_value_digest(candidate.to_dict())
    state_digest = numeric_value_digest(state)
    if authority.original_definition_digest != candidate_digest or authority.state_digest != state_digest:
        _fail()
    if source_read_phase is not None:
        source_read_phase.require_open()

    seen, native, selected = set(), False, {}
    progression = candidate.source.get('native_progression')
    if progression is not None and type(progression) is not dict:
        _fail()
    hp_recipe_present = type((progression or {}).get('hp_recipe')) is dict
    required = set(NATIVE_BASELINE_FIELDS)
    if hp_recipe_present:
        required.add('stats.max_hp')
    for marker in validated_batch:
        if type(marker) is not dict:
            _fail()
        key = tuple(marker.get(name) for name in ('target_kind', 'target_id', 'metric'))
        if (any(type(value) is not str or not value for value in key)
                or key in seen or marker.get('character_slug') != candidate.character_slug
                or marker.get('provenance') not in {'native_requalification', 'manager'}):
            _fail()
        seen.add(key)
        if marker['provenance'] != 'native_requalification':
            continue
        native = True
        if key[0] == 'field' and key[2] == 'final' and key[1] in required:
            if key[1] in selected:
                _fail()
            selected[key[1]] = marker
    if not native:
        return authority  # Explicit fixed/manual output is not automatic proof.
    if set(selected) != required:
        _fail()  # Omitting a native aggregate cannot bypass the recipe gate.

    raw_values = numeric_target_values(candidate, state)
    stored = candidate.source.get('source_authorizations')
    if type(stored) is not list:
        _fail()
    # The candidate's admitted definition-size bound already bounds this scan.
    # It performs no source lookup and retains only the <=9 selected identities.
    stored_selected = {path: [] for path in required}
    for marker in stored:
        if type(marker) is not dict:
            continue
        path = marker.get('target_id')
        if (marker.get('target_kind') == 'field' and marker.get('metric') == 'final'
                and type(path) is str and path in required):
            stored_selected[path].append(marker)

    def exact_output(left, right):
        kind = type(left)
        return (kind in {int, float, str} and type(right) is kind
                and (kind is not float or math.isfinite(left) and math.isfinite(right))
                and left == right)

    selected_rows = {}
    for path, marker in selected.items():
        key = ('field', path, 'final')
        matches = [row for row in authority.field_statuses if row.path == path]
        if (len(matches) != 1 or type(matches[0]) is not EffectiveStatus
                or matches[0].status == CONFLICT or matches[0].status != VERIFIED
                or not matches[0].is_effective or key not in raw_values
                or len(stored_selected[path]) != 1 or stored_selected[path][0] != marker
                or marker.get('value_digest') != numeric_value_digest(raw_values[key])
                or not exact_output(matches[0].raw, raw_values[key])
                or not exact_output(matches[0].effective, raw_values[key])):
            _fail()
        selected_rows[path] = matches[0]

    # Only output decisions change on this ephemeral copy. All evidence/input/
    # custody fields are shared with the original frozen authority unchanged.
    pending_fields = tuple(
        replace(row, status=UNKNOWN, effective=None, reason='native_aggregate_recipe_pending')
        if row.path in selected else row for row in authority.field_statuses
    )
    original_identity = authority.identity
    pending = replace(authority, field_statuses=pending_fields)
    bound = pending.bind_current_numbers(
        candidate, state, systems_service=systems_service,
        campaign_page_records=campaign_page_records,
    )
    # Do not use bind_projected_numbers(historical_resource_custody=True),
    # construct an alternate normalizer, rebuild authority or catch its errors.
    if source_read_phase is not None:
        source_read_phase.require_open()
    if (type(bound) is not SourceAuthority or authority.identity != original_identity
            or numeric_value_digest(candidate.to_dict()) != candidate_digest
            or numeric_value_digest(state) != state_digest):
        _fail()
    # Raw source authority has no current item context yet. The same binder
    # derives these immutable outputs for v2 casting and v4 prepared items;
    # their contents are not retained witness/input/custody objects.
    item_context_outputs = {'item_spell_context_json', 'item_prepared_context_json'}
    for name in item_context_outputs:
        if type(getattr(authority, name)) is not str or type(getattr(bound, name)) is not str:
            _fail()
    for attribute in fields(SourceAuthority):
        if attribute.name not in {'field_statuses', 'resource_statuses', *item_context_outputs}:
            if getattr(bound, attribute.name) is not getattr(authority, attribute.name):
                _fail()  # No witness/input/source/custody replacement by binding.
    for path in selected:
        matches = [row for row in bound.field_statuses if row.path == path]
        if (len(matches) != 1 or type(matches[0]) is not EffectiveStatus
                or matches[0].status != VERIFIED
                or matches[0].reason != 'derived_from_qualified_native_recipe'
                or not matches[0].is_effective
                or not exact_output(matches[0].raw, selected_rows[path].raw)
                or not exact_output(matches[0].effective, raw_values[('field', path, 'final')])):
            _fail()
    return bound


def source_identity(connection: Any, campaign_slug: str, character_slug: str) -> dict[str, Any]:
    """Keep the existing global source guards, independently of play state."""
    from .character_source_repair import _current_transition_identity
    identity = _current_transition_identity(connection, campaign_slug, character_slug)
    if not identity:
        _fail()
    return {key: deepcopy(identity[key]) for key in ("config", "systems", "pages", "page_current")}


def _generation(connection: Any, campaign: str, character: str, digest: str,
                actor: int, revision: int | None = None,
                index: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    from .committed_source_store import _decode_mapping
    rows = index if index is not None else [dict(row) for row in connection.execute(
        "SELECT revision,primary_bytes,primary_sha256,actor_user_id,tombstone "
        "FROM committed_source_generations WHERE campaign_slug=? "
        "AND object_kind='character' AND object_ref=? ORDER BY revision",
        (campaign, character),
    ).fetchall()]
    found = []
    for row in rows:
        if revision is not None and row["revision"] != revision:
            continue
        raw = row["primary_bytes"]
        if (row["tombstone"] or row["actor_user_id"] != actor or type(raw) is not bytes
                or len(raw) > 2 * 1024 * 1024
                or hashlib.sha256(raw).hexdigest() != row["primary_sha256"]):
            continue
        if "decoded" not in row:
            row["decoded"] = _decode_mapping(raw)
            row["canonical_digest"] = (_digest(CharacterDefinition.from_dict(row["decoded"]).to_dict())
                                       if isinstance(row["decoded"], dict) else None)
        payload = row["decoded"]
        if (isinstance(payload, dict) and row["canonical_digest"] == digest
                and payload.get("campaign_slug") == campaign and payload.get("character_slug") == character):
            found.append((payload, {"revision": row["revision"], "primary_sha256": row["primary_sha256"],
                                    "definition_digest": digest, "actor_user_id": actor}))
    if len(found) != 1:
        _fail()
    return found[0]


def _confirmed_history(connection: Any, campaign: str, character: str) -> list[dict[str, Any]]:
    """Audit/generation joins are evidence; a current YAML marker is not."""
    rows = connection.execute(
        "SELECT id,actor_user_id,event_type,metadata_json FROM auth_audit_log "
        "WHERE campaign_slug=? AND character_slug=? AND event_type IN "
        "('character_native_created','character_native_leveled','character_native_spell_selected','character_native_edited','character_update_applied') ORDER BY id",
        (campaign, character),
    ).fetchall()
    result = []
    generations = [dict(row) for row in connection.execute(
        "SELECT revision,primary_bytes,primary_sha256,actor_user_id,tombstone "
        "FROM committed_source_generations WHERE campaign_slug=? "
        "AND object_kind='character' AND object_ref=? ORDER BY revision", (campaign, character)).fetchall()]
    if len(generations) > 512 or len(rows) > 2048:
        raise SourceRepairError("Native history needs a separately bounded review.")
    for row in rows:
        actor = row["actor_user_id"]
        if type(actor) is not int or actor < 1:
            continue
        try:
            metadata = json.loads(row["metadata_json"])
            if not isinstance(metadata, dict):
                continue
            event = row["event_type"]
            if (event == "character_update_applied" and metadata.get("manager_action") == "native_requalify"
                    and isinstance(metadata.get("native_requalification"), dict)
                    and metadata["native_requalification"].get("schema_version") in {5, 6, 7, 8}):
                from .character_source_repair import _strict_grant_audit_json
                if len(row["metadata_json"].encode("utf-8")) > 64 * 1024:
                    continue
                metadata = _strict_grant_audit_json(row["metadata_json"])
            creation_receipt = None
            if event == "character_native_created":
                valid = metadata.get("source") == "native_create_confirmed" and metadata.get("numeric_actor_id") == actor
                digest, revision = metadata.get("definition_digest"), None
                if "native_grant_confirmation" in metadata:
                    from .character_source_repair import (_strict_grant_audit_json,
                        _grant_context_from_receipt, _sha256_hex)
                    metadata = _strict_grant_audit_json(row["metadata_json"])
                    creation_receipt = metadata["native_grant_confirmation"]
                    fields = {"schema_version", "event_type", "actor_id", "generation", "definition_digest",
                        "state_revision", "model_digest", "intent", "source_facts_digest", "capacity_frame"}
                    if (not isinstance(creation_receipt, dict) or set(creation_receipt) != fields
                            or type(creation_receipt["schema_version"]) is not int or creation_receipt["schema_version"] != 1
                            or creation_receipt["event_type"] != event
                            or type(creation_receipt["actor_id"]) is not int or creation_receipt["actor_id"] != actor
                            or type(metadata.get("numeric_actor_id")) is not int
                            or type(creation_receipt["generation"]) is not int or creation_receipt["generation"] != 1
                            or creation_receipt["definition_digest"] != digest
                            or type(creation_receipt["state_revision"]) is not int or creation_receipt["state_revision"] < 1
                            or any(not _sha256_hex(creation_receipt[key]) for key in (
                                "definition_digest", "model_digest", "source_facts_digest"))
                            or not _sha256_hex(metadata.get("source_snapshot_digest"))):
                        continue
                    context = _grant_context_from_receipt(creation_receipt["intent"])
                    if context.mode != "create" or context.actor_id != actor or context.campaign_slug != campaign:
                        continue
                    revision = creation_receipt["generation"]
            elif event == "character_native_leveled":
                valid = metadata.get("source") == "native_level_up_confirmed" and metadata.get("numeric_actor_id") == actor
                digest = metadata.get("definition_digest")
                decision = metadata.get("spell_choice_decisions")
                if decision is not None and not isinstance(decision, dict):
                    continue
                revision = decision.get("generation") if decision is not None else None
            elif event == "character_native_spell_selected":
                valid = metadata.get("source") == "native_spell_choice_confirmed" and metadata.get("numeric_actor_id") == actor
                digest = metadata.get("definition_digest")
                decision = metadata.get("spell_choice_decisions")
                if decision is not None and not isinstance(decision, dict):
                    continue
                revision = decision.get("generation") if decision is not None else None
            elif event == "character_native_edited":
                valid = metadata.get("source") == "native_edit_confirmed"
                digest, revision = metadata.get("published_definition_digest"), metadata.get("published_revision")
                valid = valid and type(revision) is int and revision > 0
            else:
                valid = (metadata.get("source") in {"character_source_repair", "character_update_preview"}
                         and isinstance(metadata.get("review_digest"), str)
                         and len(metadata["review_digest"]) == 64)
                digest = metadata.get("published_definition_digest")
                revision = metadata.get("published_revision")
                expected_digest = (metadata.get("definition_digest") if metadata.get("manager_action") in {"native_reconstruct", "native_language_elective_decision"}
                                   else metadata.get("candidate_digest"))
                valid = valid and type(revision) is int and revision > 0 and digest == expected_digest
            if not valid or not isinstance(digest, str) or len(digest) != 64:
                continue
            payload, generation = _generation(connection, campaign, character, digest, actor, revision, generations)
            if creation_receipt is not None:
                from .character_spell_grants import grant_model_digest, validate_acquisition_context
                definition = CharacterDefinition.from_dict(payload)
                validate_acquisition_context(definition, context, actor_id=actor)
                if grant_model_digest(definition) != creation_receipt["model_digest"]:
                    continue
                # This exact join is historical identity, not numeric/ordinary
                # authority. The existing complete loader admits those proofs.
            result.append({"audit_id": row["id"], "actor_user_id": actor, "event_type": event,
                           "metadata_sha256": hashlib.sha256(row["metadata_json"].encode()).hexdigest(),
                           "generation": generation, "definition": payload, "metadata": metadata})
        except (TypeError, ValueError, KeyError):
            continue
    return result


def _input_identity(row: dict[str, Any]) -> dict[str, Any]:
    # A base record's applied layers/pre_penalty are derived output. For an
    # explicit pre_penalty input, its prior layers are necessary interpretation.
    fields = ("stage", "score", "fixed_bonus", "provenance")
    result = {key: deepcopy(row.get(key, 0 if key == "fixed_bonus" else None)) for key in fields}
    if row.get("stage") == "pre_penalty":
        result["layers"] = deepcopy(row.get("layers", {"bonus": 0, "minimum": 0}))
    return result


def _retained_identity(kind: str, path: str, metric: str, value: Any) -> Any:
    """Historical observations are inputs; maxima and totals remain output."""
    if metric == "base":
        return _input_identity(value)
    if kind == "spell_metric" and metric == "formula":
        if not isinstance(value, dict):
            _fail()
        return {key: deepcopy(item) for key, item in value.items() if key != "value"}
    if kind == "field" and path == "stats.max_hp" and metric == "final":
        return None  # Exact class/progression/CON custody is checked separately.
    if kind == "resource":
        if not isinstance(value, dict):
            _fail()
        fields = (("id", "class_row_id", "reset_on", "reset_to", "rest_behavior", "initial_current") if path.startswith("resource:")
                  else ("slot_lane_id", "level") if path.startswith("spell_slot:") else ("faces",))
        if path.startswith("resource:") and type(value.get("initial_current")) is int and value["initial_current"] < 0:
            _fail()
        return {name: deepcopy(value.get(name)) for name in fields}
    if path.startswith("skills."):
        return {"name": value["name"], "proficiency_level": value["proficiency_level"]}
    return deepcopy(value)


def _confirmed_spell_metric_keys(definition, state, witnesses):
    """Keep the original, independently loaded source-qualified formulas closed."""
    from .character_source_authority import numeric_target_values, numeric_value_digest
    values = numeric_target_values(definition, state)
    markers = definition.source.get("source_authorizations") or []
    keys = set()
    for witness in witnesses:
        if type(witness) is not dict:
            continue
        marker = witness.get("authorization", witness)
        key = (marker.get("target_kind"), marker.get("target_id"), marker.get("metric"))
        if (key[0] == "spell_metric" and key in values and markers.count(marker) == 1
                and marker.get("value_digest") == numeric_value_digest(values[key])):
            keys.add(key)
    return keys


def _historical_capacity_state(definition, metadata):
    from .character_hit_dice import derive_hit_dice_max_pools
    frame = metadata.get("capacity_frame")
    if frame is None and isinstance(metadata.get("native_requalification"), dict):
        frame = metadata["native_requalification"].get("capacity_frame")
    return deepcopy(frame) if isinstance(frame, dict) else {"hit_dice": {"pools": derive_hit_dice_max_pools(definition)}}


def _canonical_skill_inputs(definition: CharacterDefinition) -> None:
    from .character_builder_constants import SKILL_LABELS
    allowed = {label.casefold() for label in SKILL_LABELS.values()}
    names = []
    reconstructed = isinstance(definition.source.get("native_reconstruction_choices"), dict)
    if not isinstance(definition.skills, list) or len(definition.skills) != len(allowed):
        _fail()
    for row in definition.skills:
        name = row.get("name") if isinstance(row, dict) else None
        if (not isinstance(name, str) or name != name.strip() or name.casefold() not in allowed
                or row.get("proficiency_level") not in (
                    {"none", "proficient", "expertise", "half_proficient"} if reconstructed else {"none", "proficient"})):
            _fail()
        names.append(name.casefold())
    if len(set(names)) != len(allowed):
        _fail()


def _unresolved_proficiency_target(definition, key):
    if definition is None or key[0] != "proficiency":
        return False
    frame = definition.source.get("native_reconstruction_choices")
    if not isinstance(frame, dict):
        return False
    category = "skills" if key[1].startswith("skills.") else key[1].split(".")[1]
    return category in frame.get("unresolved_proficiencies", [])


def _retained_key_closure(values, retained, background_tools, definition=None, *, current_resource_keys=frozenset()) -> None:
    keys = [(item.get("target_kind"), item.get("target_id"), item.get("metric")) for item in retained]
    required = {key for key in values if key[0] in {"proficiency", "resource"}
                and not _unresolved_proficiency_target(definition, key)}
    extras = {("proficiency", f"proficiencies.tools.{name}", "grant") for name in background_tools}
    if (len(keys) != len(set(keys)) or not set(keys) <= set(values)
            or set(keys) & set(current_resource_keys)
            or not set(current_resource_keys) <= {key for key in required if key[0] == "resource" and key[1].startswith("resource:")}
            or not (required - extras) <= set(keys) | set(current_resource_keys)):
        _fail()


def _current_background_tools(definition: CharacterDefinition, service: Any) -> set[str]:
    from .character_builder import validated_background_instrument_names
    if definition.profile.get("background_choices") is None:
        return set()
    return {name.casefold() for name in validated_background_instrument_names(definition, service, strict=True)}


def _historical_numeric_marker(entry, key, *, accepted_currentness=()):
    """Require actual numeric issuance, not a copied historical container."""
    from .character_source_authority import numeric_target_values, numeric_value_digest, numeric_target_owner_digest
    from .character_source_repair import _valid_numeric_witness_marker, _native_source_bound_marker, _sha256_hex
    from .character_hit_dice import derive_hit_dice_max_pools
    from .character_source_repair import NativeSpellChoiceDecision
    metadata, event, actor = entry["metadata"], entry["event_type"], entry["actor_user_id"]
    if metadata.get("numeric_actor_id") != actor:
        return None
    batch = metadata.get("numeric_authorizations")
    if event == "character_update_applied" and metadata.get("manager_action") == "native_requalify":
        batch = [row.get("authorization", row) for row in accepted_currentness if type(row) is dict]
    elif event == "character_update_applied" and metadata.get("manager_action") in {"native_reconstruct", "native_language_elective_decision"}:
        from .character_reconstruction_authority import verified_reconstruction_batch
        # The caller loads this audit through the independently verified origin
        # loader before it may nominate it as a retained input.
        batch = [row.get("authorization", row) for row in accepted_currentness if type(row) is dict]
        if not batch:
            return None
    elif event == "character_native_edited" and "external_proficiency_confirmation" in metadata:
        from .character_external_proficiencies import historical_marker
        try:
            batch = historical_marker(entry, accepted_currentness)
        except (ValueError, KeyError, TypeError):
            return None
    elif event in {"character_native_created", "character_native_leveled", "character_native_spell_selected"}:
        created = event == "character_native_created"
        selected = event == "character_native_spell_selected"
        provenance = "native_creation" if created else "native_spell_choice" if selected else "native_level_up"
        source = "native_create_confirmed" if created else "native_spell_choice_confirmed" if selected else "native_level_up_confirmed"
        basis = metadata.get("source_basis_digests")
        if (metadata.get("source") != source or not _sha256_hex(metadata.get("definition_digest"))
                or not isinstance(batch, list) or not 1 <= len(batch) <= 128
                or not isinstance(metadata.get("action_id"), str) or not metadata["action_id"]
                or not isinstance(basis, dict)):
            return None
        if not created and (type(metadata.get("prior_state_revision")) is not int
                or metadata["prior_state_revision"] < 0 or type(metadata.get("state_revision")) is not int
                or (metadata["state_revision"] not in {metadata["prior_state_revision"], metadata["prior_state_revision"] + 1}
                    if metadata.get("spell_choice_decisions") is not None else metadata["state_revision"] != metadata["prior_state_revision"] + 1)
                or not _sha256_hex(metadata.get("source_snapshot_digest"))):
            return None
        if any(not _valid_numeric_witness_marker(marker, entry["definition"]["character_slug"], provenance)
               or marker["action_id"] != metadata["action_id"]
               or (not created or marker.get("target_kind") in {"resource", "spell_metric", "spell_choice"})
               and not _native_source_bound_marker(marker) for marker in batch):
            return None
        bound_ids = [marker["target_id"] for marker in batch if _native_source_bound_marker(marker)]
        if (len(bound_ids) != len(set(bound_ids)) or set(basis) != set(bound_ids)
                or any(not _sha256_hex(value) for value in basis.values())):
            return None
    elif event == "character_update_applied" and metadata.get("manager_action") == "numeric_attest":
        marker = metadata.get("numeric_authorization")
        if batch is None:
            batch = [marker]
            if not isinstance(metadata.get("review_digest"), str) or len(metadata["review_digest"]) != 64:
                return None
        else:
            from .character_builder_constants import SKILL_LABELS
            from .repository import normalize_lookup
            path = marker.get("target_id") if isinstance(marker, dict) else None
            name = path.removeprefix("skills.") if isinstance(path, str) else ""
            passive = {"investigation":"passive_investigation", "insight":"passive_insight", "perception":"passive_perception"}.get(normalize_lookup(name))
            expected = [("proficiency", path, "grant")]
            if passive:
                expected.append(("field", f"stats.{passive}", "final"))
            if (not isinstance(batch, list) or normalize_lookup(name) not in SKILL_LABELS
                    or path != f"skills.{SKILL_LABELS[normalize_lookup(name)].casefold()}"
                    or metadata.get("source") != "character_source_repair" or metadata.get("review_action") != "numeric_attest"
                    or metadata.get("review_target_id") != path
                    or metadata.get("confirmed_skill_level") not in {"none", "half_proficient", "proficient", "expertise"}
                    or any(not _sha256_hex(metadata.get(field)) for field in ("review_digest", "candidate_digest", "published_definition_digest"))
                    or metadata["candidate_digest"] != metadata["published_definition_digest"]
                    or type(metadata.get("published_revision")) is not int or metadata["published_revision"] < 1
                    or type(metadata.get("published_state_revision")) is not int or metadata["published_state_revision"] < 1
                    or marker not in batch
                    or [(item.get("target_kind"), item.get("target_id"), item.get("metric")) for item in batch] != expected):
                return None
        if any(not _valid_numeric_witness_marker(marker, entry["definition"]["character_slug"], "manager")
               or marker["action_id"] != metadata.get("action_id") for marker in batch):
            return None
    else:
        return None
    matches = [marker for marker in batch if (marker.get("target_kind"), marker.get("target_id"), marker.get("metric")) == key]
    if len(matches) != 1:
        return None
    marker = matches[0]
    definition = CharacterDefinition.from_dict(entry["definition"])
    if list(definition.source.get("source_authorizations") or []).count(marker) != 1:
        return None
    if key[0] == "spell_choice":
        from .character_spell_grants import CLASS_CHOICE_STATE_FIELD
        from .character_source_authority import ordinary_native_spell_choice_state
        raw_row = next((row for row in definition.spellcasting.get("spells", []) if isinstance(row, dict)
            and f"spell_choice:{row.get('id')}" == key[1]), {})
        if CLASS_CHOICE_STATE_FIELD in raw_row and ordinary_native_spell_choice_state(raw_row, marker,
                verified_numeric_actions=accepted_currentness) not in {"active", "retired"}:
            return None
    state = _historical_capacity_state(definition, metadata)
    values = numeric_target_values(definition, state)
    if key not in values or marker.get("value_digest") != numeric_value_digest(values[key]):
        return None
    if marker.get("provenance") == "manager" and marker.get("owner_digest") != numeric_target_owner_digest(definition, state, *key):
        return None
    return marker


def _selection(row: dict[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(row.get(key)) for key in ("id", "class_row_id", "systems_ref", "page_ref") } | {
        "selected_choices": deepcopy(dict(row.get("campaign_option") or {}).get("selected_choices"))}


def _audit_prefix(connection: Any, campaign: str, character: str, before: int | None = None) -> str:
    rows = connection.execute(
        "SELECT id,actor_user_id,event_type,metadata_json FROM auth_audit_log "
        "WHERE campaign_slug=? AND character_slug=? ORDER BY id", (campaign, character)).fetchall()
    return _digest([tuple(row) for row in rows if before is None or row["id"] < before])


def _validate_current_proficiencies(definition: CharacterDefinition, service: Any, background_tools: set[str], *, elective_witnesses=()) -> None:
    """Check retained labels against current supported source grant shapes."""
    from . import character_builder as builder
    from .repository import normalize_lookup
    from .character_builder_constants import SKILL_LABELS, STANDARD_LANGUAGE_OPTIONS
    from .character_language_choices import language_options_for_block
    reconstructed = isinstance(definition.source.get("native_reconstruction_choices"), dict)
    if reconstructed:
        from .character_reconstruction_proficiencies import validate_current
        if validate_current(definition, service, elective_witnesses=elective_witnesses) != definition.source["native_reconstruction_choices"].get("unresolved_proficiencies", []):
            raise SourceRepairError("Current unresolved proficiency dependencies need a new reconstruction review.")
        return
    if not reconstructed and any(row.get("proficiency_level") not in {"none", "proficient"} for row in definition.skills):
        raise SourceRepairError("Native revalidation cannot renew half proficiency or expertise; review its current source separately.")
    classes = definition.profile.get("classes") or []
    if len(classes) != 1:
        _fail()  # This bounded recovery does not infer multiclass pick ownership.
    def entry(ref):
        if not isinstance(ref, dict) or not ref.get("entry_key"):
            _fail()
        current = service.get_entry_for_campaign(definition.campaign_slug, ref["entry_key"])
        if current is None or any(ref.get(key) != getattr(current, key, None) for key in (
                "entry_key", "entry_type", "title", "slug", "source_id")):
            _fail()
        return current
    cls = entry(classes[0].get("systems_ref"))
    species = entry(definition.profile.get("species_ref"))
    background = entry(definition.profile.get("background_ref"))
    from .character_language_choices import current_parent_languages
    parent_languages = current_parent_languages(definition, service)
    allowed = {
        "armor": builder._extract_class_armor_proficiencies(cls),
        "weapons": builder._extract_class_weapon_proficiencies(cls),
        "tools": (builder._extract_class_tool_proficiencies(cls) + builder._extract_fixed_tool_proficiencies(species)
                  + builder._extract_fixed_tool_proficiencies(background) + list(background_tools)),
        "languages": (parent_languages if parent_languages is not None else
                      builder._extract_fixed_languages(species) + builder._extract_fixed_languages(background)),
    }
    fixed_skills = builder._extract_fixed_skills(species) + builder._extract_fixed_skills(background)
    from .character_feature_proficiency_grants import retained_native_grants
    feature_grants, native_features = retained_native_grants(definition, service)
    fixed_skills += feature_grants["skills"]
    for category in allowed:
        allowed[category] += feature_grants[category]
    expected_automatic_tools = builder._apply_feature_expertise_to_tool_proficiencies([],
        available_tool_proficiencies=definition.proficiencies.get("tools", []),
        feature_selections=[row for row in native_features if any(block == {"allProficientTools": True}
            for block in builder._supported_feature_expertise_blocks(row["entry"]))], strict=True)
    if expected_automatic_tools:
        allowed["tool_expertise"] = expected_automatic_tools
    current_features = []
    if reconstructed:
        grant_sources = {cls.entry_key, species.entry_key, background.entry_key}
        for feature in definition.features:
            ref = feature.get("systems_ref") if isinstance(feature, dict) else None
            if not isinstance(ref, dict) or not ref.get("entry_key"):
                continue
            source = entry(ref)
            if source.entry_key in grant_sources:
                continue
            grant_sources.add(source.entry_key)
            current_features.append((feature, source))
            fixed_skills += builder._extract_fixed_skills(source)
            allowed["tools"] += builder._extract_fixed_tool_proficiencies(source)
            allowed["languages"] += builder._extract_fixed_languages(source)
    skill_slots = []
    starting = dict(cls.metadata.get("starting_proficiencies") or {})
    for block in starting.get("skills") or []:
        choose = dict(block.get("choose") or {}) if isinstance(block, dict) else {}
        count = choose.get("count", 0)
        if type(count) is not int or not 0 <= count <= 18:
            _fail()
        skill_slots.extend([{normalize_lookup(value) for value in choose.get("from") or []}] * count)
    language_slots = []
    for source in (species, background, *(current for _feature, current in current_features)):
        for block in source.metadata.get("skill_proficiencies") or []:
            if isinstance(block, dict) and "any" in block:
                count = block["any"]
                if type(count) is not int or not 0 <= count <= 18:
                    _fail()
                skill_slots.extend([set(SKILL_LABELS)] * count)
        for block in source.metadata.get("languages") or source.metadata.get("language_proficiencies") or []:
            if parent_languages is not None and source in (species, background):
                continue  # Exact retained parent choices were validated above.
            if isinstance(block, dict):
                count = block.get("anyStandard", block.get("any", 0))
                if type(count) is not int or not 0 <= count <= 16:
                    _fail()
                language_slots.extend([{normalize_lookup(value) for value in language_options_for_block(block)}] * count)
    # These helpers consume only currently verified feature metadata/choices.
    from .character_builder_derivation import _campaign_option_feat_selections_from_features, _campaign_option_feat_selected_choices_from_features
    selections = _campaign_option_feat_selections_from_features(definition.features)
    choices = _campaign_option_feat_selected_choices_from_features(definition.features)
    if reconstructed:
        choices.update(deepcopy(definition.source["native_reconstruction_choices"].get("choices") or {}))
    for category, extractor in (("armor", builder._extract_feat_armor_proficiencies),
                                ("weapons", builder._extract_feat_weapon_proficiencies),
                                ("tools", builder._extract_feat_tool_proficiencies),
                                ("languages", builder._extract_feat_language_proficiencies)):
        allowed[category] += extractor(selections, choices)
    fixed_skills += builder._extract_feat_skill_proficiencies(selections, choices)
    def fits(values, slots):
        if len(values) > len(slots):
            return False
        assigned = {}
        def assign(value, visited):
            for index, slot in enumerate(slots):
                if index in visited or value not in slot:
                    continue
                visited.add(index)
                if index not in assigned or assign(assigned[index], visited):
                    assigned[index] = value
                    return True
            return False
        return all(assign(value, set()) for value in values)
    skilled = {normalize_lookup(row["name"]) for row in definition.skills if row.get("proficiency_level") in {"proficient", "expertise"}}
    fixed = {normalize_lookup(value) for value in fixed_skills}
    if not fixed <= skilled or not fits(sorted(skilled - fixed), skill_slots):
        _fail()
    if reconstructed:
        feature_selections = [{"entry": source, "instance_key": feature["id"]}
                              for feature, source in current_features if source.entry_type != "feat"]
        feat_selections = [{"entry": source, "instance_key": feature["id"]}
                           for feature, source in current_features if source.entry_type == "feat"]
        base = {normalize_lookup(row["name"]): "proficient" if normalize_lookup(row["name"]) in skilled else "none"
                for row in definition.skills}
        expected = builder._apply_feature_expertise_to_skill_proficiency_levels(base,
            feature_selections=feature_selections, selected_choices=choices, strict=True)
        expected = builder._apply_feat_expertise_to_skill_proficiency_levels(expected,
            feat_selections=feat_selections, selected_choices=choices, strict=True)
        effects = builder._extract_character_effect_keys(definition.features)
        for effect in effects:
            for target in builder._skill_targets_for_effect_key(effect):
                expected[target] = builder._max_skill_proficiency_level(expected.get(target), "half_proficient")
        if any(row.get("proficiency_level") != expected[normalize_lookup(row["name"])] for row in definition.skills):
            _fail()
        expected_tools = builder._apply_feature_expertise_to_tool_proficiencies([], available_tool_proficiencies=definition.proficiencies.get("tools", []),
            feature_selections=feature_selections, selected_choices=choices, strict=True)
        if {normalize_lookup(value) for value in definition.proficiencies.get("tool_expertise", [])} != {normalize_lookup(value) for value in expected_tools}:
            _fail()
    for category, rows in definition.proficiencies.items():
        if category == "tool_expertise" and reconstructed:
            continue
        if category in {"skills", "tool_expertise"} and not rows:
            continue
        if category not in allowed:
            _fail()
        fixed = {normalize_lookup(value) for value in allowed[category]}
        actual = {normalize_lookup(value) for value in rows}
        if category == "languages":
            if not fixed <= actual or not fits(sorted(actual - fixed), language_slots):
                _fail()
        elif not actual <= fixed:
            _fail()


_NATIVE_RESULT_ISSUER = object()


@dataclass(frozen=True, slots=True)
class NativeRequalification:
    candidate: CharacterDefinition
    authorizations: tuple[dict[str, Any], ...]
    provenance: dict[str, Any]
    authority: Any
    spell_checkpoint: Any = field(default=None, repr=False, compare=False)
    atomic_item_adoption: Any = field(default=None, repr=False, compare=False)
    # Issued only after the actual original/history/current-source producer
    # succeeds. Not persisted, accepted as a caller argument, or a receipt.
    _binding: tuple[Any, ...] | None = field(default=None, init=False, repr=False, compare=False)

    def _validate_candidate_binding(self, record, actor_id, action_id=None):
        binding = self._binding
        if (self.provenance.get("schema_version") in {5, 6, 7, 8}) != (self.spell_checkpoint is not None):
            _fail()
        if (type(binding) is not tuple or len(binding) != 14 or binding[0] is not _NATIVE_RESULT_ISSUER
                or type(actor_id) is not int or actor_id < 1
                or type(record.committed_revision) is not int or type(record.state_record.revision) is not int
                or binding[1:7] != (record.definition.campaign_slug, record.definition.character_slug,
                    actor_id, record.committed_revision, record.state_record.revision,
                    action_id if action_id is not None else binding[6])
                or binding[7:] != (_digest(record.definition.to_dict()),
                    _digest(record.state_record.state), _digest(self.candidate.to_dict()),
                    _digest(self.authorizations), _digest(self.provenance),
                    self.authority.identity, self.authority.source_snapshot_digest)):
            _fail()
        if self.provenance.get("schema_version") == 8:
            excluded = _historical_capacity_keys(record.definition, self.candidate, self.provenance,
                                                state=record.state_record.state)
            if any((row.get("target_kind"), row.get("target_id"), row.get("metric")) in excluded
                   for row in self.authorizations):
                _fail()
        if self.spell_checkpoint is not None:
            from .character_spell_reconstruction import PendingSpellCheckpoint
            plan = self.provenance.get("spell_origin_plan")
            if (type(self.spell_checkpoint) is not PendingSpellCheckpoint
                    or self.provenance.get("schema_version") not in {5, 6, 7, 8}
                    or not isinstance(plan, dict) or plan.get("schema_version") not in {3, 4, 5}
                    or self.spell_checkpoint.checkpoint != plan.get("current_checkpoint")
                    or any(plan["current_checkpoint"].get(key) != value for key, value in (
                        ("actor_id", actor_id), ("action_id", binding[6]),
                        ("prior_generation", record.committed_revision),
                        ("prior_state_revision", record.state_record.revision)))
                    or not self.spell_checkpoint.matches_definition(self.candidate)):
                _fail()
            from .character_spell_reconstruction import validate_saved_spell_checkpoint
            validate_saved_spell_checkpoint(record.definition, self.candidate, plan["current_checkpoint"])
            from .character_spell_reconstruction import superseded_preparation_authorizations
            superseded = superseded_preparation_authorizations(
                record.definition, self.candidate, plan["current_checkpoint"])
            expected = _replay_numeric_authorizations(record.definition.to_dict(), self.authorizations,
                                                     superseded=superseded)
            if expected["source"].get("source_authorizations", []) != self.candidate.source.get("source_authorizations", []):
                _fail()
        if self.provenance.get("schema_version") == 7:
            from .character_atomic_source_adoption import PendingAtomicItemSpellAdoption, validate_saved_adoption
            if type(self.atomic_item_adoption) is not PendingAtomicItemSpellAdoption:
                _fail()
            mapping = self.atomic_item_adoption.mapping
            mapping.validate_binding(record, type(record.definition).from_dict(mapping.candidate(record)),
                                     record.state_record.state, actor_id)
            validate_saved_adoption(record.definition, self.candidate, self.provenance,
                                    actor_id=actor_id, action_id=binding[6])
            if self.atomic_item_adoption.descriptor(self.candidate, self.authority) != self.provenance["atomic_item_adoption"]:
                _fail()
        elif self.atomic_item_adoption is not None or "atomic_item_adoption" in self.provenance:
            _fail()
        return binding

    def bind_atomic_history(self, authority, systems_service):
        if self.atomic_item_adoption is None:
            return authority
        from .character_atomic_source_adoption import PendingAtomicItemSpellAdoption
        if type(self.atomic_item_adoption) is not PendingAtomicItemSpellAdoption or self.provenance.get("schema_version") != 7:
            _fail()
        bound = self.atomic_item_adoption.bind_authority(authority, self.candidate,
            self.provenance["spell_origin_plan"], self.spell_checkpoint, systems_service)
        if self.atomic_item_adoption.descriptor(self.candidate, bound) != self.provenance["atomic_item_adoption"]:
            _fail()
        return bound

    def permits_item_mapping(self, prior_record, definition, identity, actor_id):
        self._validate_candidate_binding(prior_record, actor_id)
        return (self.atomic_item_adoption is not None
            and self.atomic_item_adoption.mapping.target_id == identity
            and definition.to_dict() == self.candidate.to_dict())

    def permits_resource_owner_mapping(self, prior_record, definition, identity, actor_id):
        """Narrow an already authenticated result to one sealed owner annotation.

        Readiness and pending publication custody still authenticate current
        sources and state. This permission is not a standalone write proof.
        """
        if type(self) is not NativeRequalification or type(identity) is not str or not identity:
            return False
        self._validate_candidate_binding(prior_record, actor_id)
        if (self.provenance.get("schema_version") not in {6, 7, 8}
                or _digest(definition.to_dict()) != _digest(self.candidate.to_dict())):
            return False
        rows = self.provenance.get("current_resource_inputs")
        if type(rows) is not list:
            return False
        matches = [row for row in rows if type(row) is dict
                   and row.get("target_id") == "resource:" + identity]
        old = [row for row in prior_record.definition.resource_templates
               if type(row) is dict and row.get("id") == identity]
        new = [row for row in definition.resource_templates
               if type(row) is dict and row.get("id") == identity]
        if len(matches) != 1 or len(old) != 1 or len(new) != 1:
            return False
        admission = matches[0]
        owner = admission.get("class_row_id")
        seed_present = "initial_current" in old[0]
        return (type(owner) is str and bool(owner)
                and old[0].get("class_row_id") in (None, "")
                and new[0].get("class_row_id") == owner
                and _digest(old[0]) == admission.get("prior_template_digest")
                and _digest(new[0]) == admission.get("published_template_digest")
                and admission.get("initial_current_present") is seed_present
                and ("initial_current" in new[0]) == seed_present
                and _digest(old[0].get("initial_current")) == _digest(admission.get("initial_current"))
                and _digest(new[0].get("initial_current")) == _digest(admission.get("initial_current")))

    def validate_binding(self, record, actor_id, action_id=None, *, source_read_phase=None):
        from .db import get_db
        from .committed_publication import current
        from .committed_source_store import _decode_mapping
        binding = self._validate_candidate_binding(record, actor_id, action_id)
        campaign, character = binding[1:3]
        if source_read_phase is not None:
            source_read_phase.bind_record(record)
            generation = source_read_phase.fact("generation")
            row = source_read_phase.fact("state")
            actual_source = source_read_phase.fact("identity")
            actual_audit = source_read_phase.fact("audit")
        else:
            db = get_db()
            generation = current(campaign, "character", character, connection=db)
            row = db.execute("SELECT revision,state_json FROM character_state "
                             "WHERE campaign_slug=? AND character_slug=?", (campaign, character)).fetchone()
            actual_source = source_identity(db, campaign, character)
            actual_audit = _audit_prefix(db, campaign, character)
        if (generation is None or generation["revision"] != binding[4]
                or _digest(CharacterDefinition.from_dict(_decode_mapping(generation["primary_bytes"])).to_dict()) != binding[7]
                or row is None or row["revision"] != binding[5]
                or _digest(json.loads(row["state_json"])) != binding[8]
                or _digest(actual_source) != _digest(self.provenance["source_identity"])
                or actual_audit != self.provenance["audit_prefix_digest"]):
            _fail()


def native_requalification_state(record, result, actor_id, *, source_read_phase=None):
    """Derive only the existing producer-qualified capacity delta, not a merge."""
    result.validate_binding(record, actor_id, source_read_phase=source_read_phase)
    desired = deepcopy(record.state_record.state)
    if result.provenance.get("spell_origin_plan") is None:
        for template in result.candidate.resource_templates:
            matches = [row for row in desired.get("resources", [])
                       if isinstance(row, dict) and row.get("id") == template["id"]]
            if (len(matches) != 1
                    or not result.authority.resource_status("resource", template["id"]).is_effective):
                _fail()
            matches[0]["max"] = template["max"]
    from .character_equipment_activation import ActivationPrerequisiteError, native_activation_readiness
    try:
        native_activation_readiness(record, result.candidate, desired, final=True,
                                    atomic_item_adoption=result.atomic_item_adoption)
    except ActivationPrerequisiteError as exc:
        raise SourceRepairError("Native activation cannot retain this desired state; separate manager repair is required.") from exc
    if result.provenance.get("schema_version") == 8 and _digest(desired) != _digest(record.state_record.state):
        _fail()
    return desired


def retained_requalification_inputs(proof):
    """Losslessly expand compact headers before any historical validation."""
    retained = proof.get("retained_inputs") if isinstance(proof, dict) else None
    if not isinstance(proof, dict) or proof.get("schema_version") not in {3, 4, 5, 6, 7, 8}:
        return retained
    headers = proof.get("origin_headers")
    header_keys = {"audit_id", "actor_user_id", "event_type", "metadata_sha256", "generation"}
    input_keys = {"origin_ref", "target_kind", "target_id", "metric", "input_digest"}
    from .character_source_repair import _sha256_hex
    if (not isinstance(headers, list) or not 1 <= len(headers) <= 128
            or not isinstance(retained, list) or not 6 <= len(retained) <= 128
            or any(not isinstance(row, dict) or set(row) != header_keys for row in headers)
            or len({row["audit_id"] for row in headers if type(row["audit_id"]) is int}) != len(headers)):
        _fail()
    for header in headers:
        generation = header["generation"]
        if (type(header["audit_id"]) is not int or header["audit_id"] < 1
                or type(header["actor_user_id"]) is not int or header["actor_user_id"] < 1
                or header["event_type"] not in {"character_native_created", "character_native_leveled",
                    "character_native_spell_selected", "character_native_edited", "character_update_applied"}
                or not _sha256_hex(header["metadata_sha256"])
                or not isinstance(generation, dict)
                or set(generation) != {"revision", "primary_sha256", "definition_digest", "actor_user_id"}
                or type(generation["revision"]) is not int or generation["revision"] < 1
                or type(generation["actor_user_id"]) is not int
                or generation["actor_user_id"] != header["actor_user_id"]
                or not _sha256_hex(generation["primary_sha256"]) or not _sha256_hex(generation["definition_digest"])):
            _fail()
    used, expanded = set(), []
    for row in retained:
        ref = row.get("origin_ref") if isinstance(row, dict) else None
        if (not isinstance(row, dict) or set(row) != input_keys or type(ref) is not int
                or not 0 <= ref < len(headers) or not _sha256_hex(row["input_digest"])
                or any(not isinstance(row[key], str) or not row[key] for key in ("target_kind", "target_id", "metric"))):
            _fail()
        used.add(ref)
        expanded.append({**deepcopy(headers[ref]),
                         **{key: deepcopy(row[key]) for key in input_keys - {"origin_ref"}}})
    if used != set(range(len(headers))):
        _fail()
    return expanded


def _compact_retained_origins(retained):
    headers, positions, inputs = [], {}, []
    for row in retained:
        header = {key: deepcopy(row[key]) for key in (
            "audit_id", "actor_user_id", "event_type", "metadata_sha256", "generation")}
        identity = _digest(header)
        if identity not in positions:
            positions[identity] = len(headers)
            headers.append(header)
        inputs.append({"origin_ref": positions[identity], **{key: deepcopy(row[key]) for key in (
            "target_kind", "target_id", "metric", "input_digest")}})
    return headers, inputs


def _retained_resource_source_frame(definition, state, retained, *, systems_service, campaign_page_records,
                                    state_revision, prospective_spell_checkpoint=None,
                                    atomic_item_adoption=None, spell_origin_plan=None,
                                    verified_numeric_actions=None, verified_manual_actions=()):
    """Qualify source/formula inputs without issuing any resource witness.

    Callers independently authenticate retained origins first. Current permanent
    owners must also qualify; saved totals and the new batch are not evidence.
    Historical capacity frames deliberately supply no usage/equipment history.
    Omitted witnesses retain the saved proof3/4 path; current preparation must
    pass its independently recovered witnesses, never its prospective batch.
    """
    from .character_ability_inputs import KEYS, input_records
    from .character_source_authority import (
        VERIFIED, build_reconciled_source_authority, _eligible_page_records,
        _source_derived_resource_bases,
    )
    checkpoint_kwargs = ({"prospective_spell_checkpoint": prospective_spell_checkpoint}
        if prospective_spell_checkpoint is not None
        and prospective_spell_checkpoint.matches_definition(definition) else {})
    current_kwargs = ({"verified_numeric_actions": tuple(verified_numeric_actions),
                       "verified_manual_actions": tuple(verified_manual_actions)}
                      if verified_numeric_actions is not None else {})
    baseline = build_reconciled_source_authority(
        definition=definition, state=state, state_revision=state_revision,
        systems_service=systems_service, campaign_page_records=campaign_page_records,
        **checkpoint_kwargs, **current_kwargs)
    if atomic_item_adoption is not None:
        baseline = atomic_item_adoption.bind_authority(baseline, definition, spell_origin_plan,
                                                      prospective_spell_checkpoint, systems_service)
    records = input_records(definition.stats)
    paths = {f"stats.ability_scores.{key}.score" for key in KEYS}
    inputs = [row for row in retained if row.get("target_kind") == "field"
              and row.get("metric") == "base" and row.get("target_id") in paths]
    if (set(records) != set(KEYS) or len(inputs) != len(KEYS)
            or {row["target_id"] for row in inputs} != paths
            or any(baseline.numeric_basis_digest(path) is None for path in paths)
            or any(row["input_digest"] != _digest(_input_identity(records[row["target_id"].split(".")[2]]))
                   for row in inputs)):
        _fail()
    provisional = replace(baseline, field_statuses=tuple(
        replace(row, status=VERIFIED, effective=None, reason="baseline_authorized") if row.path in paths else row
        for row in baseline.field_statuses))
    current_resource_kwargs = {}
    if verified_numeric_actions is not None:
        from .character_armor_models import selectors
        current_resource_kwargs = {
            "tracker_bindings": provisional.tracker_associations,
            "armor_selectors": selectors(definition, systems_service, current_kwargs["verified_numeric_actions"]),
        }
    bases = _source_derived_resource_bases(
        definition, systems_service=systems_service, pages=_eligible_page_records(campaign_page_records),
        verified_class_rows=provisional.verified_class_rows, feature_statuses=provisional.statuses,
        field_statuses=provisional.field_statuses, feature_composition=provisional.feature_composition,
        **current_resource_kwargs)
    return provisional, bases


def _claimed_resource_paths(definition, history):
    """A malformed or unaccepted old claim never becomes a new-input fallback."""
    paths = set()
    containers = [definition.source.get("source_authorizations", [])]
    for entry in history:
        metadata = entry.get("metadata", {})
        containers.extend((metadata.get("numeric_authorizations", []),
            [metadata.get("numeric_authorization")],
            entry.get("definition", {}).get("source", {}).get("source_authorizations", [])))
    for rows in containers:
        if type(rows) is not list:
            continue
        for row in rows:
            if type(row) is not dict:
                continue
            marker = row.get("authorization", row)
            if type(marker) is dict and type(marker.get("target_id")) is str and marker["target_id"].startswith("resource:"):
                paths.add(marker["target_id"])
    return paths


def _historical_capacity_keys(prior, candidate, proof, *, state=None, history=None):
    """Closed proof8 role exclusions, never numeric/reset admission authority."""
    if proof.get("schema_version") != 8:
        return set()
    if type(proof["schema_version"]) is not int:
        _fail()
    plan = proof.get("spell_origin_plan")
    admissions = proof.get("current_resource_inputs")
    if (type(plan) is not dict or plan.get("schema_version") != 5
            or "atomic_item_adoption" in proof or type(admissions) is not list
            or type(proof.get("renewed_source_bases")) is not dict
            or type(proof.get("targets")) is not list):
        _fail()
    from .character_feature_capacities import verify_historical_counter_inputs
    try:
        keys = verify_historical_counter_inputs(prior, candidate,
            proof.get("historical_capacity_inputs"), state=state)
    except (ValueError, TypeError, KeyError, AttributeError):
        _fail()
    excluded = {key[1] for key in keys}
    admitted = [row.get("target_id") for row in admissions if type(row) is dict]
    stored = candidate.source.get("source_authorizations", [])
    if (len(admitted) != len(admissions) or any(type(path) is not str for path in admitted)
            or admitted != sorted(set(admitted)) or excluded & set(admitted)
            or excluded & set(proof.get("renewed_source_bases", {}))
            or any(type(key) is not list or len(key) != 3
                   or any(type(value) is not str for value in key) or tuple(key) in keys
                   for key in proof.get("targets", []))
            or any(type(marker) is dict and (
                marker.get("target_kind"), marker.get("target_id"), marker.get("metric")) in keys for marker in stored)
            or history is not None and excluded & _claimed_resource_paths(prior, history)):
        _fail()
    return keys


def _admission_feature_rows(prior, proof):
    """Exact missing-owner annotations only; grants never inherit other edits."""
    rows = proof.get("current_resource_inputs")
    if proof.get("schema_version") in {7, 8} and type(rows) is list and not rows:
        return deepcopy(prior.features)
    if type(rows) is not list or not 1 <= len(rows) <= 16:
        _fail()
    result = deepcopy(prior.features)
    seen = set()
    for row in rows:
        if (type(row) is not dict or type(row.get("target_id")) is not str
                or not row["target_id"].startswith("resource:") or row["target_id"] in seen
                or type(row.get("feature_ids")) is not list or not row["feature_ids"]
                or any(type(value) is not str or not value for value in row["feature_ids"])
                or row["feature_ids"] != sorted(set(row["feature_ids"]))
                or type(row.get("class_row_id")) is not str or not row["class_row_id"]):
            _fail()
        seen.add(row["target_id"])
        for identity in row["feature_ids"]:
            matches = [item for item in result if type(item) is dict and item.get("id") == identity]
            if len(matches) != 1 or matches[0].get("class_row_id") not in (None, "", row["class_row_id"]):
                _fail()
            matches[0]["class_row_id"] = row["class_row_id"]
    return result


def _resource_refusal(path, reason):
    import re
    safe = path if type(path) is str and re.fullmatch(r"resource:[a-z0-9_-]{1,120}", path) else "resource"
    raise SourceRepairError(f"Current {safe} {reason}; review its source and ownership.")


def _intrinsic_resource_template(pool, original, definition):
    """Finite current rules, with no imported maximum or item/history input."""
    from .character_profile import profile_class_rows
    from .managed_resource_registry import resolve_managed_resource_family_and_member
    from .character_feature_trackers import build_managed_resource_tracker_template
    feature = pool["members"][0]["canonical"]
    family, member = resolve_managed_resource_family_and_member(feature)
    formula = dict(dict((member or {}).get("tracker") or {}).get("max_formula") or {})
    rows = profile_class_rows(definition.profile)
    if (family is None or formula.get("kind") not in {"fixed", "total_half_level"}
            or any(type(row.get("level")) is not int or not 1 <= row["level"] <= 20 for row in rows)
            or not 1 <= sum(row["level"] for row in rows) <= 20
            or type(original.get("display_order")) is not int):
        _resource_refusal("resource:" + str(original.get("id") or ""), "has no supported intrinsic recipe")
    expected = build_managed_resource_tracker_template(member, feature, ability_scores={},
        current_level=pool["class"]["level"], total_character_level=sum(row["level"] for row in rows),
        display_order=original["display_order"])
    if expected is None or type(expected.get("max")) is not int or expected["max"] < 0:
        _resource_refusal("resource:" + str(original.get("id") or ""), "has an invalid intrinsic capacity")
    expected.pop("activation_type", None)
    expected["class_row_id"] = pool["class_row_id"]
    # initial_current is an old observation, not today's count or a rule seed.
    if "initial_current" in original:
        seed = original["initial_current"]
        if seed is not None and (type(seed) is not int or seed < 0):
            _resource_refusal("resource:" + str(original.get("id") or ""), "has an invalid retained seed")
        expected["initial_current"] = seed
    else:
        expected.pop("initial_current", None)
    return {**deepcopy(original), **expected}


def _current_admission_recipe(pool, definition, authority, systems_service):
    from .character_feature_composition import (TIDES_KEY, REGISTERED_WILD_GRANT,
        SORCERER_KEY, WILD_SUBCLASS_KEY)
    from .character_source_authority import _current_systems_entry, _source_identity
    if len(pool["members"]) != 1:
        _fail()
    feature = pool["members"][0]["canonical"]
    kind, key = _source_identity(feature)
    entry = _current_systems_entry(definition.campaign_slug, kind, key, systems_service)
    registration = ("phb_tides_of_chaos@1" if key == TIDES_KEY else REGISTERED_WILD_GRANT
        if authority.feature_composition is not None
        and authority.feature_composition.resource_owner(feature["id"]) is not None else None)
    if entry is None or registration is None:
        _fail()
    return {"schema_version": 1, "registration": registration,
        "source_ref": {name: getattr(entry, name) for name in
            ("library_slug", "entry_key", "entry_type", "source_id", "slug", "title")},
        "publication_digest": _digest({"metadata": entry.metadata, "body": entry.body}),
        "owner_rules": {"class_entry_key": SORCERER_KEY,
            "subclass_entry_key": WILD_SUBCLASS_KEY, "attained_level": 1}}


def _historical_admission_pool(prior, row):
    """Interpret a sealed finite recipe without consulting today's source.

    This proves past admission shape and inputs, not present eligibility. The
    normal authority reader independently compares today's per-target basis.
    """
    from .character_feature_composition import (TIDES_KEY, REGISTERED_WILD_GRANT,
        SORCERER_KEY, WILD_SUBCLASS_KEY, CLAIM_FIELD, wild_replacement_effect)
    from .character_profile import profile_class_rows
    from .character_source_repair import _sha256_hex
    recipe = row["source_recipe"]
    if (type(recipe) is not dict or set(recipe) != {"schema_version", "registration", "source_ref", "publication_digest", "owner_rules"}
            or type(recipe["schema_version"]) is not int or recipe["schema_version"] != 1
            or not _sha256_hex(recipe["publication_digest"])
            or _digest(recipe["owner_rules"]) != _digest({"class_entry_key": SORCERER_KEY,
                "subclass_entry_key": WILD_SUBCLASS_KEY, "attained_level": 1})
            or len(row["feature_ids"]) != 1):
        _fail()
    ref = recipe["source_ref"]
    if (type(ref) is not dict or set(ref) != {"library_slug", "entry_key", "entry_type", "source_id", "slug", "title"}
            or any(type(value) is not str or not value for value in ref.values())
            or ref["library_slug"] != "DND-5E"):
        _fail()
    classes = [item for item in profile_class_rows(prior.profile) if item.get("row_id") == row["class_row_id"]]
    features = [item for item in prior.features if type(item) is dict and item.get("id") == row["feature_ids"][0]]
    if (len(classes) != 1 or len(features) != 1
            or dict(classes[0].get("systems_ref") or {}).get("entry_key") != SORCERER_KEY
            or dict(classes[0].get("subclass_ref") or {}).get("entry_key") != WILD_SUBCLASS_KEY
            or type(classes[0].get("level")) is not int or not 1 <= classes[0]["level"] <= 20
            or features[0].get("class_row_id") not in (None, "", row["class_row_id"])
            or features[0].get("page_ref")
            or type(features[0].get("systems_ref")) is not dict
            or any(features[0]["systems_ref"].get(name) != ref[name]
                for name in ("entry_key", "entry_type", "source_id", "slug"))):
        _fail()
    canonical = deepcopy(features[0])
    canonical.update(class_row_id=row["class_row_id"], source=ref["source_id"])
    if recipe["registration"] == "phb_tides_of_chaos@1":
        if (row["target_id"] != "resource:tides-of-chaos" or ref["entry_key"] != TIDES_KEY
                or ref["entry_type"] != "subclassfeature" or ref["source_id"] != "PHB"):
            _fail()
    elif recipe["registration"] == REGISTERED_WILD_GRANT:
        claim = canonical.get(CLAIM_FIELD)
        if (row["target_id"] != "resource:wild-die" or ref["entry_type"] != "feature"
                or not ref["entry_key"].startswith("dnd-5e|custom|")
                or type(claim) is not dict or set(claim) != {"schema_version", "source_ref", "declaration", "class_row_id"}
                or type(claim["schema_version"]) is not int or claim["schema_version"] != 1
                or claim["source_ref"] != ref or claim["class_row_id"] not in ("", row["class_row_id"])
                or _digest(claim["declaration"]) != _digest(wild_replacement_effect())):
            _fail()
        canonical["mechanic_effects"] = [wild_replacement_effect()]
    else:
        _fail()
    return {"members": [{"canonical": canonical}], "class": classes[0], "class_row_id": row["class_row_id"]}


def _prepare_current_resource_admissions(original, working, state, missing, retained, *,
        systems_service, campaign_page_records, state_revision, prospective_spell_checkpoint=None,
        atomic_item_adoption=None, spell_origin_plan=None,
        verified_numeric_actions, verified_manual_actions):
    """Admit genuinely current source inputs, never fabricate a historical origin."""
    from .character_source_authority import _current_managed_pool_owners, _eligible_page_records, _qualified_current_managed_templates
    from .character_equipment_activation import effective_definition
    from .character_armor_models import selectors
    if not missing:
        return working, []
    if type(missing) is not set or not 1 <= len(missing) <= 16 or any(
            kind != "resource" or metric != "owner_reset" or not path.startswith("resource:")
            for kind, path, metric in missing):
        _fail()
    provisional, _ = _retained_resource_source_frame(working, state, retained,
        systems_service=systems_service, campaign_page_records=campaign_page_records,
        state_revision=state_revision, prospective_spell_checkpoint=prospective_spell_checkpoint,
        atomic_item_adoption=atomic_item_adoption, spell_origin_plan=spell_origin_plan,
        verified_numeric_actions=verified_numeric_actions, verified_manual_actions=verified_manual_actions)
    pools = _current_managed_pool_owners(working, systems_service=systems_service,
        pages=_eligible_page_records(campaign_page_records), verified_class_rows=provisional.verified_class_rows,
        feature_statuses=provisional.statuses, infer_missing=True, feature_composition=provisional.feature_composition,
        tracker_bindings=provisional.tracker_associations,
        armor_selectors=selectors(working, systems_service, verified_numeric_actions))
    payload = deepcopy(working.to_dict())
    observations = state.get("resources")
    if type(observations) is not list:
        _fail()
    records = []
    for _kind, path, _metric in sorted(missing):
        tracker_id = path.removeprefix("resource:")
        pool = pools.get(tracker_id)
        old = [row for row in original.resource_templates if type(row) is dict and row.get("id") == tracker_id]
        current = [row for row in observations if type(row) is dict and row.get("id") == tracker_id]
        if pool is None or len(old) != 1 or len(current) != 1:
            _resource_refusal(path, "lacks one current source owner/template/observation")
        expected = _intrinsic_resource_template(pool, old[0], working)
        observation = {key: deepcopy(current[0].get(key)) for key in ("id", "current", "max")}
        if (type(observation["current"]) is not int or type(observation["max"]) is not int
                or observation["max"] != expected["max"] or not 0 <= observation["current"] <= expected["max"]):
            _resource_refusal(path, "cannot preserve its exact current observation")
        member_ids = [member["feature"]["id"] for member in pool["members"]]
        if len(member_ids) != len(set(member_ids)):
            _resource_refusal(path, "has ambiguous current source citations")
        for identity in member_ids:
            features = [row for row in payload["features"] if type(row) is dict and row.get("id") == identity]
            if len(features) != 1 or features[0].get("class_row_id") not in (None, "", pool["class_row_id"]):
                _resource_refusal(path, "has a conflicting class owner")
            features[0]["class_row_id"] = pool["class_row_id"]
        matching = [row for row in payload["resource_templates"] if type(row) is dict and row.get("id") == tracker_id]
        if len(matching) != 1 or matching[0].get("class_row_id") not in (None, "", pool["class_row_id"]):
            _resource_refusal(path, "has a conflicting template owner")
        matching[0].clear(); matching[0].update(expected)
        records.append({"schema_version": 1, "target_id": path, "feature_ids": sorted(member_ids),
            "source_recipe": _current_admission_recipe(pool, working, provisional, systems_service),
            "class_row_id": pool["class_row_id"], "prior_template_digest": _digest(old[0]),
            "prior_state_observation": observation, "prior_state_row_digest": _digest(current[0]),
            "initial_current_present": "initial_current" in old[0],
            "initial_current": deepcopy(old[0].get("initial_current")),
            "published_template_digest": _digest(expected)})
    candidate = CharacterDefinition.from_dict(payload)
    provisional, bases = _retained_resource_source_frame(candidate, state, retained,
        systems_service=systems_service, campaign_page_records=campaign_page_records,
        state_revision=state_revision, prospective_spell_checkpoint=prospective_spell_checkpoint,
        atomic_item_adoption=atomic_item_adoption, spell_origin_plan=spell_origin_plan,
        verified_numeric_actions=verified_numeric_actions, verified_manual_actions=verified_manual_actions)
    bound = provisional.bind_current_numbers(candidate, state, systems_service=systems_service,
        campaign_page_records=campaign_page_records)
    activated, _ = effective_definition(candidate, state)
    expected = _qualified_current_managed_templates(bound, activated,
        systems_service=systems_service, campaign_page_records=campaign_page_records,
        armor_selectors=selectors(candidate, systems_service, verified_numeric_actions))
    for record in records:
        path = record["target_id"]; tracker_id = path.removeprefix("resource:")
        template = next(row for row in candidate.resource_templates if row["id"] == tracker_id)
        # This first-admission lane proves intrinsic fixed/half-total recipes.
        # Item-dependent new capacities need their own qualified observation,
        # never an invented activation history in the saved capacity_frame.
        if (bases.get(path) is None or expected.get(tracker_id) is None
                or expected[tracker_id]["max"] != template["max"]):
            _resource_refusal(path, "has no independent intrinsic current basis")
        record["source_basis_digest"] = bases[path]
    return candidate, records


def _verify_current_resource_admissions(prior, candidate, proof, retained, *, history):
    """Receiving check of the exact current-admission lane and preserved seeds.

    Observed current values are contemporaneous audit facts from the sealed,
    re-prepared publication, not claims of historically source-authorized use.
    They never set a future current or replace an initial_current observation.
    """
    rows = proof.get("current_resource_inputs")
    if proof.get("schema_version") in {7, 8} and type(rows) is list and not rows:
        if _digest(prior.features) != _digest(candidate.features):
            _fail()
        return set()
    fields = {"schema_version", "target_id", "feature_ids", "class_row_id", "prior_template_digest",
        "prior_state_observation", "prior_state_row_digest", "initial_current_present", "initial_current",
        "published_template_digest", "source_basis_digest", "source_recipe"}
    if type(rows) is not list or not 1 <= len(rows) <= 16:
        _fail()
    seen, feature_owners = set(), {}
    for row in rows:
        if (type(row) is not dict or set(row) != fields or type(row["schema_version"]) is not int
                or row["schema_version"] != 1 or type(row["target_id"]) is not str
                or not row["target_id"].startswith("resource:") or row["target_id"] in seen
                or type(row["feature_ids"]) is not list or not row["feature_ids"]
                or any(type(value) is not str or not value for value in row["feature_ids"])
                or row["feature_ids"] != sorted(set(row["feature_ids"]))
                or type(row["class_row_id"]) is not str or not row["class_row_id"]
                or type(row["initial_current_present"]) is not bool):
            _fail()
        path = row["target_id"]; seen.add(path); tracker_id = path.removeprefix("resource:")
        if path in _claimed_resource_paths(prior, history):
            _resource_refusal(path, "already has historical custody and cannot use current admission")
        old = [item for item in prior.resource_templates if type(item) is dict and item.get("id") == tracker_id]
        new = [item for item in candidate.resource_templates if type(item) is dict and item.get("id") == tracker_id]
        observation = row["prior_state_observation"]
        from .character_source_repair import _sha256_hex
        if (len(old) != 1 or len(new) != 1 or _digest(old[0]) != row["prior_template_digest"]
                or _digest(new[0]) != row["published_template_digest"]
                or old[0].get("class_row_id") not in (None, "", row["class_row_id"])
                or ("initial_current" in old[0]) != row["initial_current_present"]
                or ("initial_current" in new[0]) != row["initial_current_present"]
                or _digest(old[0].get("initial_current")) != _digest(row["initial_current"])
                or _digest(new[0].get("initial_current")) != _digest(row["initial_current"])
                or any(not _sha256_hex(row[key]) for key in ("prior_template_digest", "prior_state_row_digest",
                    "published_template_digest", "source_basis_digest"))
                or type(observation) is not dict or set(observation) != {"id", "current", "max"}
                or observation["id"] != tracker_id or type(observation["current"]) is not int
                or type(observation["max"]) is not int or type(new[0].get("max")) is not int
                or observation["max"] != new[0]["max"]
                or not 0 <= observation["current"] <= observation["max"]):
            _fail()
        for identity in row["feature_ids"]:
            if identity in feature_owners and feature_owners[identity] != row["class_row_id"]:
                _fail()
            feature_owners[identity] = row["class_row_id"]
    # Only missing owner annotations are admitted; feature selection, source,
    # declarations and every unrelated row remain exact original-generation inputs.
    expected_features = deepcopy(prior.features)
    for identity, owner in feature_owners.items():
        matches = [row for row in expected_features if type(row) is dict and row.get("id") == identity]
        if len(matches) != 1 or matches[0].get("class_row_id") not in (None, "", owner):
            _fail()
        matches[0]["class_row_id"] = owner
    if _digest(expected_features) != _digest(candidate.features):
        _fail()
    for row in rows:
        path = row["target_id"]; tracker_id = path.removeprefix("resource:")
        old = next(item for item in prior.resource_templates if item["id"] == tracker_id)
        new = next(item for item in candidate.resource_templates if item["id"] == tracker_id)
        pool = _historical_admission_pool(prior, row)
        if (_digest(_intrinsic_resource_template(pool, old, candidate)) != _digest(new)
                or proof.get("renewed_source_bases", {}).get(path) != row["source_basis_digest"]):
            _resource_refusal(path, "has inconsistent saved source admission")
    return {("resource", path, "owner_reset") for path in seen}


def _prepare_legacy_spell_origin_correction(definition, systems_service, request):
    """Rebuild one explicit plan from the original definition and fresh sources.

    Both preparation and the independent durable loader call this with their
    own authenticated prior generation. No caller supplies flags or origins.
    """
    from .character_source_authority import current_native_automatic_spell_origins
    from .character_profile import profile_class_rows
    if (not isinstance(request, dict) or set(request) != {"automatic_ids", "remove_ids", "confirm_removal"}
            or definition.system != "DND-5E"
            or definition.source.get("source_type") != "native_character_builder"
            or not isinstance(definition.source.get("native_reconstruction_choices"), dict)):
        raise SourceRepairError("Spell-origin correction requires reconstructed native inputs and an explicit plan.")
    automatic, removed = request["automatic_ids"], request["remove_ids"]
    if (not isinstance(automatic, list) or not isinstance(removed, list)
            or not 1 <= len(automatic) + len(removed) <= 16 or len(removed) > 1
            or type(request["confirm_removal"]) is not bool
            or request["confirm_removal"] != bool(removed)
            or any(not isinstance(value, str) or not value or value != value.strip()
                   or len(value.encode("utf-8")) > 128 for value in [*automatic, *removed])
            or len(set([*automatic, *removed])) != len(automatic) + len(removed)):
        raise SourceRepairError("Choose unique exact spell IDs and separately confirm the unsupported removal.")
    spells = definition.spellcasting.get("spells")
    if (not isinstance(spells, list) or len(spells) > 256
            or any(not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] for row in spells)
            or len({row["id"] for row in spells}) != len(spells)):
        _fail()
    by_id = {row["id"]: row for row in spells}
    if not set([*automatic, *removed]) <= set(by_id):
        _fail()
    origins = current_native_automatic_spell_origins(definition, systems_service) if automatic else {}
    payload = definition.to_dict()
    book = deepcopy(definition.spellcasting)
    changed = {row["id"]: row for row in book["spells"]}
    adoption_rows, removal_rows = [], []
    for spell_id in sorted(automatic):
        row, origin = by_id[spell_id], origins.get(spell_id)
        if (origin is None or any(type(row.get(field)) is not bool for field in ("is_always_prepared", "is_bonus_known"))
                or any(field in row and type(row[field]) is not bool for field in (
                    "always_prepared", "prepared", "is_prepared", "base_is_always_prepared", "base_is_bonus_known"))
                or "always_prepared" in row and row["always_prepared"] != row["is_always_prepared"]
                or "prepared" in row and "is_prepared" in row and row["prepared"] != row["is_prepared"]):
            raise SourceRepairError("The selected spell needs unambiguous current automatic source ownership and flags.")
        flags = {"is_always_prepared": origin["always_prepared"], "is_bonus_known": origin["bonus_known"]}
        if "always_prepared" in row:
            flags["always_prepared"] = origin["always_prepared"]
        changed[spell_id].update(flags)
        adoption_rows.append({"spell_id": spell_id, **origin,
            "before_flags": {field: row[field] for field in flags}, "after_flags": flags,
            "before_digest": _digest(row), "after_digest": _digest(changed[spell_id])})
    classes = profile_class_rows(definition.profile)
    for spell_id in removed:
        row = by_id[spell_id]
        owners = [owner for owner in classes if owner.get("row_id") == row.get("class_row_id")]
        if (len(owners) != 1 or row.get("systems_ref") or row.get("page_ref") or row.get("spell_source_row_id")
                or any(isinstance(marker, dict) and marker.get("target_id") in {spell_id, f"spell_choice:{spell_id}"}
                       for marker in [*list(definition.source.get("source_authorizations") or []),
                                      *list(definition.spellcasting.get("manual_authorizations") or [])])):
            raise SourceRepairError("Removal requires one unsupported unlinked spell without another witnessed owner.")
        owner = owners[0]
        ref = owner.get("systems_ref")
        entry = (systems_service.get_entry_for_campaign(definition.campaign_slug, ref["entry_key"])
                 if isinstance(ref, dict) and ref.get("entry_key") else None)
        if (entry is None or entry.entry_type != "class" or type(owner.get("level")) is not int
                or not 1 <= owner["level"] <= 20
                or any(ref.get(field) and ref[field] != getattr(entry, field, None)
                       for field in ("entry_key", "entry_type", "slug", "source_id", "title", "library_slug"))):
            _fail()
        removal_rows.append({"spell_id": spell_id, "class_row_id": row["class_row_id"],
            "row_digest": _digest(row), "class_row_digest": _digest(owner),
            "reason": "manager_confirmed_unsupported_unlinked"})
    book["spells"] = [row for row in book["spells"] if row["id"] not in removed]
    payload["spellcasting"] = book
    corrected = CharacterDefinition.from_dict(payload)
    plan = {"schema_version": 1, "request": {"automatic_ids": sorted(automatic),
        "remove_ids": sorted(removed), "confirm_removal": bool(removed)},
        "prior_spellcasting_digest": _digest(definition.spellcasting),
        "result_spellcasting_digest": _digest(corrected.spellcasting),
        "automatic": adoption_rows, "removed": removal_rows}
    return corrected, plan


def prepare_spell_origin_correction(definition, systems_service, request, *,
                                    prior_generation, prior_definition_digest,
                                    prior_state_revision, actor_id=None, action_id=None):
    """Adopt complete current feature occurrences without rewriting raw facts.

    The prior generation is independently authenticated by each caller. The
    explicit IDs are a correction subset; the source-driven producer owns the
    complete attained feature model, including unflagged grants.
    """
    from .character_spell_grants import (
        GrantContractError, grant_model_digest, prepare_feature_grant_migration,
        inspect_native_grant_proposal,
    )
    base_keys = {"automatic_ids", "remove_ids", "confirm_removal"}
    checkpoint_requested = isinstance(request, dict) and "confirm_current_spells" in request
    item_only = isinstance(request, dict) and "item_only_correction" in request
    preparation_set = isinstance(request, dict) and "prepared_spell_ids" in request
    if (not isinstance(request, dict) or set(request) != base_keys | ({"confirm_current_spells"} if checkpoint_requested else set())
            | ({"item_only_correction"} if item_only else set())
            | ({"prepared_spell_ids"} if preparation_set else set())
            or checkpoint_requested and request["confirm_current_spells"] is not True
            or preparation_set and (not checkpoint_requested or item_only)
            or item_only and (not checkpoint_requested or request["automatic_ids"] != []
                             or request["confirm_removal"] is not True)
            or definition.system != "DND-5E"
            or definition.source.get("source_type") != "native_character_builder"
            or not isinstance(definition.source.get("native_reconstruction_choices"), dict)
            or type(prior_generation) is not int or prior_generation < 1
            or type(prior_state_revision) is not int or prior_state_revision < 1
            or prior_definition_digest != _digest(definition.to_dict())):
        raise SourceRepairError("Feature-grant migration requires exact reconstructed native custody.")
    automatic, removed = request["automatic_ids"], request["remove_ids"]
    if (not isinstance(automatic, list) or not isinstance(removed, list)
            or not (0 if checkpoint_requested else 1) <= len(automatic) + len(removed) <= 16 or len(removed) > 1
            or type(request["confirm_removal"]) is not bool
            or request["confirm_removal"] != bool(removed)
            or any(not isinstance(value, str) or not value or value != value.strip()
                   or len(value.encode("utf-8")) > 128 for value in [*automatic, *removed])
            or len(set([*automatic, *removed])) != len(automatic) + len(removed)):
        raise SourceRepairError("Choose unique exact spell IDs and separately confirm the unsupported removal.")
    spells = definition.spellcasting.get("spells")
    if (not isinstance(spells, list) or len(spells) > 256
            or any(not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] for row in spells)
            or len({row["id"] for row in spells}) != len(spells)):
        _fail()
    by_id = {row["id"]: row for row in spells}
    if not set([*automatic, *removed]) <= set(by_id):
        _fail()
    if preparation_set:
        from .character_spell_reconstruction import _preparation_ids
        _preparation_ids(definition, request["prepared_spell_ids"])
    try:
        migrated, model = prepare_feature_grant_migration(
            definition, systems_service, prior_generation=prior_generation,
            prior_definition_digest=prior_definition_digest, prior_state_revision=prior_state_revision)
    except GrantContractError as exc:
        raise SourceRepairError(str(exc)) from exc
    edges = model["migration_edges"]
    by_old = {edge["old_spell_id"]: edge for edge in edges if edge["grant_ids"]}
    if not set(automatic) <= set(by_old) or any(not by_old[value]["grant_ids"] for value in automatic):
        raise SourceRepairError("Every correction target needs an exact proposed feature-grant mapping.")
    # Keep historical unlinked removal separate from the new, explicitly
    # confirmed item-only observation disposition; no aggregate origin is adopted.
    removal_rows = []
    if removed:
        if item_only:
            from .character_spell_observation_correction import prepare_item_only_removal_rows
            removal_rows = prepare_item_only_removal_rows(definition, systems_service, removed, request["item_only_correction"])
        else:
            _, removal_plan = _prepare_legacy_spell_origin_correction(definition, systems_service,
                {"automatic_ids": [], "remove_ids": removed, "confirm_removal": True})
            removal_rows = removal_plan["removed"]
        if set(removed) & set(by_old):
            raise SourceRepairError("A current feature-owned spell cannot be removed as unsupported.")
    elif item_only:
        raise SourceRepairError("Select the exact erroneous book observation for item-only correction.")
    payload = deepcopy(migrated.to_dict())
    payload["spellcasting"]["spells"] = [row for row in payload["spellcasting"]["spells"] if row["id"] not in removed]
    corrected = CharacterDefinition.from_dict(payload)
    # Draft facts are a separate type and never enter verified_numeric_actions
    # or SourceAuthority. Only the actual durable audit can later supply custody.
    try:
        draft = inspect_native_grant_proposal(corrected, systems_service,
            prior_definition=definition, prior_generation=prior_generation,
            prior_definition_digest=prior_definition_digest, prior_state_revision=prior_state_revision)
    except GrantContractError as exc:
        raise SourceRepairError(str(exc)) from exc
    supported = {row["id"] for row in draft.occurrences if row.get("status") == "DRAFT"}
    if any(not supported.intersection(by_old[spell_id]["grant_ids"]) for spell_id in automatic):
        raise SourceRepairError("Each correction target needs source-supported proposed grant facts.")
    adoption_rows = [{"spell_id": edge["old_spell_id"],
        "class_row_id": by_id[edge["old_spell_id"]].get("class_row_id"),
        "grant_ids": deepcopy(edge["grant_ids"]),
        "unresolved_observation_digest": edge["unresolved_observation_digest"],
        "correction_target": edge["old_spell_id"] in automatic} for edge in edges if edge["grant_ids"]]
    plan = {"schema_version": 2, "request": {"automatic_ids": sorted(automatic),
        "remove_ids": sorted(removed), "confirm_removal": bool(removed)},
        "prior_generation": prior_generation, "prior_definition_digest": prior_definition_digest,
        "prior_state_revision": prior_state_revision,
        "prior_spellcasting_digest": _digest(definition.spellcasting),
        "result_spellcasting_digest": _digest(corrected.spellcasting),
        "grant_model_digest": grant_model_digest(corrected),
        "proposal_source_digest": draft.source_digest, "supported_grant_ids": sorted(supported),
        "automatic": adoption_rows, "removed": removal_rows}
    if checkpoint_requested:
        from .character_spell_reconstruction import prepare_current_spell_checkpoint
        corrected, checkpoint, _ = prepare_current_spell_checkpoint(
            definition, corrected, systems_service, actor_id=actor_id, action_id=action_id,
            prior_generation=prior_generation, prior_state_revision=prior_state_revision,
            automatic_ids={row["spell_id"] for row in adoption_rows},
            prepared_spell_ids=request.get("prepared_spell_ids") if preparation_set else None)
        plan["schema_version"] = 5 if preparation_set else 4 if item_only else 3
        plan["request"]["confirm_current_spells"] = True
        if preparation_set:
            plan["request"]["prepared_spell_ids"] = sorted(request["prepared_spell_ids"])
        if item_only:
            plan["request"]["item_only_correction"] = deepcopy(request["item_only_correction"])
        plan["current_checkpoint"] = checkpoint
        plan["result_spellcasting_digest"] = _digest(corrected.spellcasting)
    return corrected, plan


def _saved_spell_origin_correction(prior, candidate, plan):
    """Authenticate historical migration custody without current-source veto.

    Generation and audit joins are proved by the caller. This pure comparison
    authenticates the exact original observations, mapping and removal delta;
    it never says those sources remain eligible today.
    """
    if isinstance(plan, dict) and type(plan.get("schema_version")) is int and plan["schema_version"] in {3, 4, 5}:
        return _saved_current_spell_origin_correction(prior, candidate, plan)
    return _saved_spell_origin_comparison(prior, candidate, plan, checkpoint_validated=False)


def _saved_spell_origin_comparison(prior, candidate, plan, *, checkpoint_validated, item_only_correction=None):
    """Shared exact grant delta; only the complete checkpoint wrapper admits an empty subset."""
    from .character_spell_grants import grant_model_digest, validate_feature_grant_migration_custody
    from .character_profile import profile_class_rows
    fields = {"schema_version", "request", "prior_generation", "prior_definition_digest",
        "prior_state_revision", "prior_spellcasting_digest", "result_spellcasting_digest",
        "grant_model_digest", "proposal_source_digest", "supported_grant_ids", "automatic", "removed"}
    request = plan.get("request") if isinstance(plan, dict) else None
    if (not isinstance(plan, dict) or set(plan) != fields or type(plan["schema_version"]) is not int
            or plan["schema_version"] != 2 or not isinstance(request, dict)
            or set(request) != {"automatic_ids", "remove_ids", "confirm_removal"}):
        _fail()
    automatic, removed = request["automatic_ids"], request["remove_ids"]
    if (not isinstance(automatic, list) or not isinstance(removed, list)
            or not (0 if checkpoint_validated else 1) <= len(automatic) + len(removed) <= 16 or len(removed) > 1
            or type(request["confirm_removal"]) is not bool or request["confirm_removal"] != bool(removed)
            or any(not isinstance(value, str) or not value or value != value.strip()
                   or len(value.encode("utf-8")) > 128 for value in [*automatic, *removed])
            or len(set([*automatic, *removed])) != len(automatic) + len(removed)
            or automatic != sorted(automatic) or removed != sorted(removed)):
        _fail()
    # This validator owns the two grant containers only. Rule-derived numeric
    # output is validated by the separate numeric batch, never copied into the
    # original observation frame used to authenticate acquisition custody.
    restored = deepcopy(prior.to_dict())
    restored["source"]["native_acquisitions"] = deepcopy(candidate.source["native_acquisitions"])
    restored["spellcasting"]["native_spell_grants"] = deepcopy(candidate.spellcasting["native_spell_grants"])
    corrected = CharacterDefinition.from_dict(restored)
    validate_feature_grant_migration_custody(prior, corrected,
        prior_generation=plan["prior_generation"], prior_definition_digest=plan["prior_definition_digest"],
        prior_state_revision=plan["prior_state_revision"])
    spells = prior.spellcasting.get("spells")
    if not isinstance(spells, list) or any(not isinstance(row, dict) or not row.get("id") for row in spells):
        _fail()
    by_id = {row["id"]: row for row in spells}
    if len(by_id) != len(spells) or not set([*automatic, *removed]) <= set(by_id):
        _fail()
    expected_book = deepcopy(prior.spellcasting)
    expected_book["native_spell_grants"] = deepcopy(candidate.spellcasting["native_spell_grants"])
    expected_book["spells"] = [deepcopy(row) for row in spells if row["id"] not in removed]
    edges = expected_book["native_spell_grants"]["migration_edges"]
    by_old = {edge["old_spell_id"]: edge for edge in edges if edge["grant_ids"]}
    if not set(automatic) <= set(by_old) or set(removed) & set(by_old):
        _fail()
    expected_automatic = [{"spell_id": edge["old_spell_id"],
        "class_row_id": by_id[edge["old_spell_id"]].get("class_row_id"),
        "grant_ids": deepcopy(edge["grant_ids"]),
        "unresolved_observation_digest": edge["unresolved_observation_digest"],
        "correction_target": edge["old_spell_id"] in automatic} for edge in edges if edge["grant_ids"]]
    from .character_source_repair import _sha256_hex
    supported = plan["supported_grant_ids"]
    if (not _sha256_hex(plan["proposal_source_digest"]) or not isinstance(supported, list)
            or any(not isinstance(value, str) for value in supported)
            or supported != sorted(set(supported))
            or not set(supported) <= {row["id"] for row in expected_book["native_spell_grants"]["occurrences"]}
            or any(not set(supported).intersection(by_old[spell_id]["grant_ids"]) for spell_id in automatic)):
        _fail()
    expected_removals = []
    if item_only_correction is not None:
        from .character_spell_observation_correction import item_only_removal_rows
        if not checkpoint_validated or automatic or request["confirm_removal"] is not True:
            _fail()
        claimed = plan["removed"]
        if type(claimed) is not list or len(claimed) != 1 or type(claimed[0]) is not dict:
            _fail()
        expected_removals = item_only_removal_rows(prior, removed, item_only_correction,
                                                source_level=claimed[0].get("spell_level"))
    for spell_id in ([] if item_only_correction is not None else removed):
        row = by_id[spell_id]
        owners = [owner for owner in profile_class_rows(prior.profile) if owner.get("row_id") == row.get("class_row_id")]
        if (len(owners) != 1 or row.get("systems_ref") or row.get("page_ref") or row.get("spell_source_row_id")
                or any(isinstance(marker, dict) and marker.get("target_id") in {spell_id, f"spell_choice:{spell_id}"}
                       for marker in [*list(prior.source.get("source_authorizations") or []),
                                      *list(prior.spellcasting.get("manual_authorizations") or [])])):
            _fail()
        expected_removals.append({"spell_id": spell_id, "class_row_id": row["class_row_id"],
            "row_digest": _digest(row), "class_row_digest": _digest(owners[0]),
            "reason": "manager_confirmed_unsupported_unlinked"})
    if (candidate.spellcasting != expected_book or plan["automatic"] != expected_automatic
            or plan["removed"] != expected_removals
            or plan["prior_spellcasting_digest"] != _digest(prior.spellcasting)
            or plan["result_spellcasting_digest"] != _digest(candidate.spellcasting)
            or plan["grant_model_digest"] != grant_model_digest(candidate)):
        _fail()
    return candidate, plan


def _saved_current_spell_origin_correction(prior, candidate, plan):
    """Compose the unchanged grant validator with the exact checkpoint delta."""
    from .character_spell_grants import CLASS_CHOICE_STATE_FIELD
    from .character_spell_reconstruction import validate_saved_spell_checkpoint
    old_plan = deepcopy(plan)
    checkpoint = old_plan.pop("current_checkpoint", None)
    request = old_plan.get("request")
    if (not isinstance(request, dict) or request.pop("confirm_current_spells", None) is not True):
        _fail()
    explicit = plan["schema_version"] == 5
    if explicit:
        selected = request.pop("prepared_spell_ids", None)
        if (type(checkpoint) is not dict or checkpoint.get("schema_version") != 3
                or type(checkpoint.get("class_row")) is not dict
                or type(selected) is not list
                or checkpoint.get("prepared_selection") != {
                    "class_row_id": checkpoint.get("class_row", {}).get("row_id"), "spell_ids": selected}):
            _fail()
    elif type(checkpoint) is dict and checkpoint.get("schema_version") == 3:
        _fail()
    item_only_correction = None
    if plan["schema_version"] == 4:
        item_only_correction = request.pop("item_only_correction", None)
        if type(item_only_correction) is not dict:
            _fail()
    old_plan["schema_version"] = 2
    # The schema-2 reader still sees the original raw book, with only its exact
    # grant/removal containers. Only newly added current-state metadata is
    # stripped. Version5 also restores only the exact preparation fields that
    # the pure checkpoint validator authenticates against the actual original.
    old_rows = {row["id"]: row for row in prior.spellcasting.get("spells", [])}
    validate_saved_spell_checkpoint(prior, candidate, checkpoint)
    stripped = deepcopy(candidate.to_dict())
    preparation_ids = ({entry["spell_id"] for entry in checkpoint["entries"]
        if entry["role"] in {"prepared", "available"}} if explicit else set())
    for row in stripped["spellcasting"].get("spells", []):
        old = old_rows.get(row.get("id"))
        if old is not None and CLASS_CHOICE_STATE_FIELD not in old:
            row.pop(CLASS_CHOICE_STATE_FIELD, None)
        if old is not None and row["id"] in preparation_ids:
            # Only the separately validated current-preparation bit is restored
            # for the unchanged historical grant/removal comparator.
            for key in ("mark", "prepared", "is_prepared"):
                if key in old:
                    row[key] = deepcopy(old[key])
                else:
                    row.pop(key, None)
    stripped_definition = CharacterDefinition.from_dict(stripped)
    old_plan["result_spellcasting_digest"] = _digest(stripped_definition.spellcasting)
    _saved_spell_origin_comparison(prior, stripped_definition, old_plan, checkpoint_validated=True,
                                  item_only_correction=item_only_correction)
    if plan["result_spellcasting_digest"] != _digest(candidate.spellcasting):
        _fail()
    return candidate, plan


def prepare_native_requalification(*, record: Any, systems_service: Any,
                                   campaign_page_records: list[Any] | None,
                                   action_id: str, actor_id: int,
                                   connection: Any | None = None,
                                   spell_origin_request: dict[str, Any] | None = None,
                                   atomic_item_request: dict[str, Any] | None = None,
                                   source_read_owner=None, campaign=None) -> NativeRequalification:
    from .db import get_db
    from .character_source_reads import SourceReadOwner, native_source_phase, SourceReadConflict
    db = connection if connection is not None else get_db()
    owned = source_read_owner is None
    owner = source_read_owner if source_read_owner is not None else SourceReadOwner.owned(
        db, record.definition.campaign_slug, record.definition.character_slug)
    if owner.connection is not db:
        raise SourceReadConflict("Native producer connection differs from its explicit owner.")
    try:
        with native_source_phase(owner, systems_service=systems_service, campaign=campaign,
                                 record=record, purpose="native-producer") as phase:
            if phase is not None:
                phase.bind_pages(campaign_page_records)
            return _prepare_native_requalification(
                record=record, systems_service=phase.systems_view() if phase is not None else systems_service,
                campaign_page_records=phase.character_pages() if phase is not None else campaign_page_records,
                action_id=action_id, actor_id=actor_id, connection=db,
                spell_origin_request=spell_origin_request, atomic_item_request=atomic_item_request,
                source_read_phase=phase)
    finally:
        if owned:
            owner.close()


def _prepare_native_requalification(*, record: Any, systems_service: Any,
                                   campaign_page_records: list[Any] | None,
                                   action_id: str, actor_id: int,
                                   connection: Any | None = None,
                                   spell_origin_request: dict[str, Any] | None = None,
                                   atomic_item_request: dict[str, Any] | None = None,
                                   source_read_phase=None) -> NativeRequalification:
    from .db import get_db
    from .character_ability_inputs import KEYS, input_records
    from .character_builder import normalize_definition_to_native_model
    from .character_source_authority import (
        VERIFIED, EffectiveStatus, build_reconciled_source_authority,
        native_baseline_target, numeric_target_values, numeric_target_owner_digest,
        numeric_value_digest,
    )
    from .character_source_repair import (
        add_numeric_authorization, load_verified_manual_actions,
        load_verified_numeric_actions, numeric_authorization_record,
    )
    from .character_profile import profile_class_rows
    db = connection if connection is not None else get_db()
    definition = record.definition
    reconstructed = isinstance(definition.source.get("native_reconstruction_choices"), dict)
    state = deepcopy(record.state_record.state)
    campaign, character = definition.campaign_slug, definition.character_slug
    if (type(actor_id) is not int or actor_id < 1 or not isinstance(action_id, str)
            or not action_id or len(action_id) > 512
            or definition.system != "DND-5E"
            or definition.source.get("source_type") != "native_character_builder"):
        _fail()
    identity = source_identity(db, campaign, character)
    working_definition, spell_origin_plan, spell_checkpoint = definition, None, None
    atomic_item_adoption = None
    from .committed_publication import current as current_generation
    current = current_generation(campaign, "character", character, connection=db)
    if (current is None or current.get("revision") != record.committed_revision
            or source_identity(db, campaign, character) != identity):
        _fail()
    from .committed_source_store import _decode_mapping
    committed = _decode_mapping(current["primary_bytes"])
    exact_state = db.execute(
        "SELECT revision,state_json FROM character_state WHERE campaign_slug=? AND character_slug=?",
        (campaign, character)).fetchone()
    if (not isinstance(committed, dict)
            or _digest(CharacterDefinition.from_dict(committed).to_dict()) != _digest(definition.to_dict())
            or exact_state is None or exact_state["revision"] != record.state_record.revision
            or _digest(json.loads(exact_state["state_json"])) != _digest(state)):
        _fail()
    if spell_origin_request is None:
        from .character_source_repair import require_confirmed_native_grant_custody
        require_confirmed_native_grant_custody(record, connection=db)
    history = _confirmed_history(db, campaign, character)
    from .character_language_choices import PARENT_FRAME
    created = [row for row in history if row["event_type"] == "character_native_created"]
    if PARENT_FRAME in definition.source or any(PARENT_FRAME in row["definition"].get("source", {}) for row in created):
        if (len(created) != 1 or definition.source.get(PARENT_FRAME) != created[0]["definition"].get("source", {}).get(PARENT_FRAME)
                or (PARENT_FRAME in definition.source) != (PARENT_FRAME in created[0]["definition"].get("source", {}))):
            _fail()
    natives = [entry for entry in history if entry["event_type"] in {
        "character_native_created", "character_native_leveled"}
        or entry["event_type"] == "character_update_applied" and entry["metadata"].get("manager_action") == "native_reconstruct"]
    if not natives:
        _fail()
    native = natives[-1]
    if (definition.profile.get("classes") != native["definition"].get("profile", {}).get("classes")
            or definition.source.get("native_progression") != native["definition"].get("source", {}).get("native_progression")):
        _fail()
    inputs = input_records(definition.stats)
    if set(inputs) != set(KEYS) or any(row.get("stage") == "unresolved" for row in inputs.values()):
        _fail()
    _canonical_skill_inputs(definition)
    numeric = load_verified_numeric_actions(campaign, character, connection=db, strict=True)
    if reconstructed:
        from .character_reconstruction_proficiencies import validate_current
        if validate_current(definition, systems_service, elective_witnesses=numeric) != sorted(
                definition.source["native_reconstruction_choices"].get("unresolved_proficiencies", [])):
            _fail()
    origins = load_verified_numeric_actions(campaign, character, connection=db, strict=True, include_origin=True)
    by_audit = {entry["audit_id"]: entry for entry in history}
    retained = []
    retained_history_cache = {"history": history}
    retained_history_cache["prior_numeric_witnesses"] = tuple(item["witness"] for item in origins)

    def retain(kind: str, path: str, metric: str, current: Any, *, skill: bool = False,
               resource: bool = False) -> None:
        matching = []
        for origin in origins:
            witness = origin["witness"]
            if type(witness) is not dict:
                continue
            marker = witness.get("authorization", witness)
            if (marker.get("target_kind"), marker.get("target_id"), marker.get("metric")) == (kind, path, metric):
                matching.append((origin, marker))
        if not matching:
            _fail()
        origin, marker = matching[-1]
        old = by_audit.get(origin["audit_id"])
        if old is None or old["metadata_sha256"] != origin["metadata_sha256"]:
            _fail()
        accepted = ()
        if old["event_type"] in {"character_native_created", "character_native_spell_selected", "character_native_leveled", "character_native_edited"}:
            accepted = tuple(item["witness"] for item in origins if item["audit_id"] == old["audit_id"])
        if old["event_type"] == "character_update_applied" and old["metadata"].get("manager_action") == "native_reconstruct":
            from .character_reconstruction_authority import verified_reconstruction_batch
            accepted = verified_reconstruction_batch(db, campaign, character,
                {"actor_user_id": old["actor_user_id"]}, old["metadata"],
                prior_witnesses=tuple(item["witness"] for item in origins if item["audit_id"] < old["audit_id"]))
        if old["event_type"] == "character_update_applied" and old["metadata"].get("manager_action") == "native_language_elective_decision":
            from .character_language_electives import confirmed_batch_for_audit
            accepted = confirmed_batch_for_audit(tuple(item["witness"] for item in origins),
                old["audit_id"], old["metadata"])
        if old["event_type"] == "character_update_applied" and old["metadata"].get("manager_action") == "native_requalify":
            accepted = verified_requalification_batch(
                db, campaign, character,
                {"id": old["audit_id"], "actor_user_id": old["actor_user_id"],
                 "metadata_json": json.dumps(old["metadata"])}, old["metadata"],
                history_cache=retained_history_cache,
            )
        if _historical_numeric_marker(old, (kind, path, metric), accepted_currentness=accepted) != marker:
            _fail()
        old_definition = CharacterDefinition.from_dict(old["definition"])
        from .character_hit_dice import derive_hit_dice_max_pools
        old_state = _historical_capacity_state(old_definition, old["metadata"])
        values = numeric_target_values(old_definition, old_state)
        raw = values.get((kind, path, metric))
        if numeric_value_digest(raw) != marker["value_digest"]:
            _fail()
        current_input = _retained_identity(kind, path, metric, current)
        if current_input != _retained_identity(kind, path, metric, raw):
            _fail()
        retained.append({key: deepcopy(old[key]) for key in (
            "audit_id", "actor_user_id", "event_type", "metadata_sha256", "generation")} | {
                "target_kind": kind, "target_id": path, "metric": metric,
                "input_digest": numeric_value_digest(current_input)})

    for key in KEYS:
        retain("field", f"stats.ability_scores.{key}.score", "base", inputs[key])
    skill_names = []
    for row in definition.skills:
        name = str(row.get("name") or "").strip().casefold()
        if not name or name in skill_names or row.get("proficiency_level") not in {"none", "half_proficient", "proficient", "expertise"}:
            _fail()
        skill_names.append(name)
        if not _unresolved_proficiency_target(definition, ("proficiency", f"skills.{name}", "grant")):
            retain("proficiency", f"skills.{name}", "grant", row, skill=True)
    for feature in definition.features:
        matches = [entry for entry in history if any(
            row.get("id") == feature.get("id") for row in entry["definition"].get("features", []))]
        if not matches:
            _fail()
        old_rows = [row for row in matches[-1]["definition"].get("features", []) if row.get("id") == feature.get("id")]
        if len(old_rows) != 1 or _selection(old_rows[0]) != _selection(feature):
            _fail()
    if spell_origin_request is not None:
        working_definition, spell_origin_plan = prepare_spell_origin_correction(
            definition, systems_service, spell_origin_request,
            prior_generation=record.committed_revision,
            prior_definition_digest=_digest(definition.to_dict()),
            prior_state_revision=record.state_record.revision,
            actor_id=actor_id, action_id=action_id)
        if spell_origin_plan.get("schema_version") in {3, 4, 5}:
            from .character_spell_reconstruction import prepare_current_spell_checkpoint
            working_definition, checkpoint, spell_checkpoint = prepare_current_spell_checkpoint(
                definition, working_definition, systems_service, actor_id=actor_id, action_id=action_id,
                prior_generation=record.committed_revision, prior_state_revision=record.state_record.revision,
                automatic_ids={row["spell_id"] for row in spell_origin_plan["automatic"]},
                prepared_spell_ids=spell_origin_plan["request"].get("prepared_spell_ids"))
            if checkpoint != spell_origin_plan["current_checkpoint"]:
                _fail()
    if atomic_item_request is not None:
        from .character_atomic_source_adoption import PendingAtomicItemSpellAdoption
        if (spell_origin_plan is None or spell_origin_plan.get("schema_version") != 5
                or spell_checkpoint is None or not reconstructed):
            _fail()
        atomic_item_adoption = PendingAtomicItemSpellAdoption.prepare(record, atomic_item_request,
            actor_id=actor_id, action_id=action_id, service=systems_service, pages=campaign_page_records)
        working_definition = atomic_item_adoption.compose(record, working_definition)
    background_tools = _current_background_tools(definition, systems_service)
    for kind, rows in definition.proficiencies.items():
        seen = set()
        for value in rows:
            name = str(value).strip().casefold()
            if not name or name in seen:
                _fail()
            seen.add(name)
            if kind == "tools" and name in background_tools:
                continue  # An exact current structured background choice, not an old-total witness.
            if _unresolved_proficiency_target(definition, ("proficiency", f"proficiencies.{kind}.{name}", "grant")):
                continue
            retain("proficiency", f"proficiencies.{kind}.{name}", "grant", value)
    manual = load_verified_manual_actions(campaign, character, connection=db, strict=True)

    def authority_for(candidate: CharacterDefinition, witnesses=numeric):
        checkpoint_kwargs = ({"prospective_spell_checkpoint": spell_checkpoint}
            if spell_checkpoint is not None and spell_checkpoint.matches_definition(candidate) else {})
        authority = build_reconciled_source_authority(
            definition=candidate, state=state, state_revision=record.state_record.revision,
            systems_service=systems_service, campaign_page_records=campaign_page_records,
            verified_manual_actions=manual, verified_numeric_actions=tuple(witnesses), **checkpoint_kwargs)
        return (atomic_item_adoption.bind_authority(authority, candidate, spell_origin_plan,
                    spell_checkpoint, systems_service) if atomic_item_adoption is not None else authority)

    initial = authority_for(working_definition)
    if spell_origin_plan is not None and spell_origin_plan.get("schema_version") == 4:
        from .character_spell_observation_correction import require_current_item_only_grant
        require_current_item_only_grant(working_definition, initial, spell_origin_plan["removed"])
    from .character_source_authority import validate_native_spell_choice_decision_transition
    if spell_checkpoint is None:
        validate_native_spell_choice_decision_transition(record, working_definition, state,
            prior_authority=initial, actor_id=actor_id, operation_kind="character_update_apply",
            systems_service=systems_service, campaign_page_records=campaign_page_records)
    if (set(initial.verified_class_rows) != {row["row_id"] for row in profile_class_rows(definition.profile)}
            or any(row.status == "CONFLICT" for row in (*initial.field_statuses, *initial.resource_statuses))
            or any(row.status != VERIFIED for row in initial.statuses
                   if (row.kind != "item" or row.instance_id in initial.active_item_ids)
                   and not (reconstructed and row.kind == "feature")
                   and not (row.kind == "feature" and row.status == "REPLACED"
                       and initial.feature_composition is not None
                       and row.instance_id in initial.feature_composition.replaced_ids))):
        _fail()
    _validate_current_proficiencies(initial.effective_definition(working_definition), systems_service,
        background_tools, elective_witnesses=numeric)
    missing_resources = set()
    claimed_resources = _claimed_resource_paths(definition, history)
    historical_capacity_inputs, historical_capacity_keys = [], set()
    if reconstructed and spell_checkpoint is not None and spell_origin_plan.get("schema_version") == 5:
        from .character_feature_capacities import (
            historical_counter_candidates, prepare_historical_counter_inputs, verify_historical_counter_inputs,
        )
        if historical_counter_candidates(working_definition):
            # Authenticated ability bases are inputs, not current effective
            # scores. Use the ordinary source/state-bound numeric derivation
            # for capacity qualification, keeping initial for transitions.
            capacity_authority = initial.bind_current_numbers(
                working_definition, state, systems_service=systems_service,
                campaign_page_records=campaign_page_records)
            historical_capacity_inputs = prepare_historical_counter_inputs(
                working_definition, state, capacity_authority, systems_service)
        if historical_capacity_inputs:
            if atomic_item_adoption is not None:
                _fail()  # Proof8 must never be overwritten/downgraded to atomic proof7.
            try:
                historical_capacity_keys = verify_historical_counter_inputs(
                    definition, working_definition, historical_capacity_inputs, state=state)
            except (ValueError, TypeError, KeyError, AttributeError):
                _fail()
            if {key[1] for key in historical_capacity_keys} & claimed_resources:
                _fail()  # An admitted old resource is not an exclusion fallback.
    for (kind, path, metric), raw in numeric_target_values(definition, state).items():
        if kind == "resource":
            if (kind, path, metric) in historical_capacity_keys:
                continue
            if path.startswith("spell_slot:") and not reconstructed:
                _fail()
            if (reconstructed and spell_checkpoint is not None and path.startswith("resource:")
                    and metric == "owner_reset" and path not in claimed_resources):
                missing_resources.add((kind, path, metric))
            else:
                retain(kind, path, metric, raw, resource=True)
    working_definition, current_resource_inputs = _prepare_current_resource_admissions(
        definition, working_definition, state, missing_resources, retained,
        systems_service=systems_service, campaign_page_records=campaign_page_records,
        state_revision=record.state_record.revision, prospective_spell_checkpoint=spell_checkpoint,
        atomic_item_adoption=atomic_item_adoption, spell_origin_plan=spell_origin_plan,
        verified_numeric_actions=numeric, verified_manual_actions=manual)
    # The prior authority remains the original input for transition validation.
    # Source-qualified missing-owner annotations belong to the desired frame.
    desired_initial = authority_for(working_definition) if current_resource_inputs else initial
    values = numeric_target_values(definition, state)
    input_paths = {f"stats.ability_scores.{key}.score" for key in KEYS}
    input_paths.update(item["target_id"] for item in retained if item["target_kind"] == "proficiency")
    pending_fields = tuple(replace(row, status=VERIFIED, effective=(deepcopy(row.raw)
                           if row.path not in {f"stats.ability_scores.{key}.score" for key in KEYS} else None),
                           reason="baseline_authorized" if row.path.startswith("stats.ability_scores.") else "retained_native_input")
                           if row.path in input_paths else row for row in desired_initial.field_statuses)
    pending = replace(desired_initial, field_statuses=pending_fields)
    from .character_equipment_activation import (
        ActivationPrerequisiteError, effective_definition as activation_definition, native_activation_readiness,
    )
    try:
        native_activation_readiness(record, working_definition, state, atomic_item_adoption=atomic_item_adoption)
    except ActivationPrerequisiteError as exc:
        raise SourceRepairError("Native equipment activation needs separate manager repair.") from exc
    activated_definition, activation_warnings = activation_definition(working_definition, state)
    # Shared typed readiness above permits only a genuinely absent marker's
    # sole migration warning; reconstructed=True is never a warning bypass.
    derived = normalize_definition_to_native_model(
        activated_definition, mode="authoring", source_authority=pending,
        systems_service=systems_service, campaign_page_records=campaign_page_records)
    if [row.get("id") for row in derived.features] != [row.get("id") for row in definition.features]:
        _fail()
    # Requalification updates derived sheet output, never selected links,
    # feature/equipment rows, spell choices, history or descriptive content.
    if reconstructed:
        from .character_reconstruction import retain_reconstruction_content
        candidate = retain_reconstruction_content(working_definition, derived)
    else:
        candidate_payload = definition.to_dict()
        for field in ("stats", "skills", "attacks", "resource_templates"):
            candidate_payload[field] = deepcopy(getattr(derived, field))
        candidate = CharacterDefinition.from_dict(candidate_payload)
    if spell_origin_plan is not None:
        # The explicit plan owns only its grant containers/removal. Derived formula/slot
        # outputs cannot enlarge the reviewed spellcasting delta.
        candidate_payload = candidate.to_dict()
        candidate_payload["spellcasting"] = deepcopy(working_definition.spellcasting)
        candidate_payload["source"]["native_acquisitions"] = deepcopy(working_definition.source["native_acquisitions"])
        candidate = CharacterDefinition.from_dict(candidate_payload)
    if spell_checkpoint is not None and not spell_checkpoint.matches_definition(candidate):
        # Normalization may renew the ability-input interpretation. Bind the
        # final exact input frame once it exists; selected row metadata is
        # idempotent and every original observation is rechecked.
        from .character_spell_reconstruction import prepare_current_spell_checkpoint
        candidate, checkpoint, spell_checkpoint = prepare_current_spell_checkpoint(
            definition, candidate, systems_service, actor_id=actor_id, action_id=action_id,
            prior_generation=record.committed_revision, prior_state_revision=record.state_record.revision,
            automatic_ids={row["spell_id"] for row in spell_origin_plan["automatic"]},
            prepared_spell_ids=spell_origin_plan["request"].get("prepared_spell_ids"))
        spell_origin_plan["current_checkpoint"] = checkpoint
        spell_origin_plan["result_spellcasting_digest"] = _digest(candidate.spellcasting)
    # HP is recomputed from the immutable native baseline/events. The retained
    # CON input must match that lineage; no old final HP value is an input.
    old_con = input_records(native["definition"].get("stats", {})).get("con", {})
    if _input_identity(old_con) != _input_identity(inputs["con"]):
        _fail()
    check = authority_for(candidate)
    if check.numeric_basis_digest("stats.max_hp") is None:
        _fail()
    prior_ids = [row.get("id") for row in definition.resource_templates]
    candidate_ids = [row.get("id") for row in candidate.resource_templates]
    observed_resources = state.get("resources") if isinstance(state.get("resources"), list) else []
    state_ids = [row.get("id") for row in observed_resources if isinstance(row, dict)]
    if (any(not value for value in prior_ids + candidate_ids + state_ids)
            or len(prior_ids) != len(set(prior_ids))
            or len(state_ids) != len(set(state_ids))
            or set(prior_ids) != set(candidate_ids)
            or (not set(state_ids) <= set(prior_ids) if reconstructed else set(prior_ids) != set(state_ids))):
        _fail()
    from .character_source_authority import _qualified_current_managed_templates
    from .character_armor_models import selectors
    provisional, resource_bases = _retained_resource_source_frame(
        candidate, state, retained, systems_service=systems_service,
        campaign_page_records=campaign_page_records, state_revision=record.state_record.revision,
        prospective_spell_checkpoint=spell_checkpoint,
        atomic_item_adoption=atomic_item_adoption, spell_origin_plan=spell_origin_plan,
        verified_numeric_actions=numeric, verified_manual_actions=manual)
    bound = provisional.bind_current_numbers(candidate, state, systems_service=systems_service,
        campaign_page_records=campaign_page_records)
    current_candidate, _ = activation_definition(candidate, state)
    expected_templates = _qualified_current_managed_templates(
        bound, current_candidate, systems_service=systems_service, campaign_page_records=campaign_page_records,
        armor_selectors=selectors(candidate, systems_service, numeric))
    historical_ids = {key[1].removeprefix("resource:") for key in historical_capacity_keys}
    if (len(candidate_ids) != len(set(candidate_ids)) or set(candidate_ids) - historical_ids != set(expected_templates)
            or any(value is None for value in expected_templates.values())):
        _fail()
    for template in candidate.resource_templates:
        if template["id"] in historical_ids:
            continue
        expected = expected_templates[template["id"]]
        # Historical bootstrap current is not a rule maximum or a refill.
        retained_template = next(row for row in definition.resource_templates if row["id"] == template["id"])
        expected["initial_current"] = retained_template.get("initial_current")
        # Retained notes are history; the proof still binds the current recipe.
        if (any(template.get(key) != value for key, value in expected.items() if key not in {"max", "initial_current", "notes"})
                or not reconstructed and (type(expected["initial_current"]) is not int
                    or expected["initial_current"] < 0)):
            _fail()
        observed = next((row for row in observed_resources if isinstance(row, dict) and row.get("id") == template["id"]), None)
        if observed is not None and (type(observed.get("current")) is int and not 0 <= observed["current"] <= expected["max"]
                or not reconstructed and type(observed.get("current")) is not int):
            _fail()
        # The old capacity is output, not a retained input. Unknown resource
        # authority can withhold item bonuses during ordinary normalization;
        # this independently rebuilt current source formula is the renewal.
        # Initial/current observations remain exact and no rest is implied.
        template["max"] = expected["max"]
        if "initial_current" in retained_template:
            template["initial_current"] = expected["initial_current"]
    fresh_values = numeric_target_values(candidate, state)
    if historical_capacity_keys:
        try:
            if verify_historical_counter_inputs(definition, candidate, historical_capacity_inputs,
                    state=state) != historical_capacity_keys:
                _fail()
        except (ValueError, TypeError, KeyError, AttributeError):
            _fail()
        fresh_values = {key: value for key, value in fresh_values.items() if key not in historical_capacity_keys}
    _canonical_skill_inputs(candidate)
    _retained_key_closure(fresh_values, retained, background_tools, candidate, current_resource_keys=missing_resources)
    check = authority_for(candidate)
    checkpoint_choice_keys = {key for key, raw in fresh_values.items()
        if key[0] == "spell_choice" and spell_checkpoint is not None
        and spell_checkpoint.confirms_choice(raw)}
    keys = [key for key in fresh_values if not _unresolved_proficiency_target(candidate, key) and (
        native_baseline_target(*key) or key[0] == "resource"
        or key == ("field", "stats.proficiency_bonus", "final")
        or key == ("field", "stats.max_hp", "final")
        or key[0] == "field" and key[2] == "base"
        or reconstructed and key[0] in {"spell_metric", "spell_choice"}
            and (spell_checkpoint is None or key[0] != "spell_choice" or key in checkpoint_choice_keys)
            and not (spell_origin_plan is not None and key[0] == "spell_choice"
                     and key[1].removeprefix("spell_choice:") in {
                         row["spell_id"] for row in spell_origin_plan["automatic"]})
            and check.numeric_basis_digest(key[1]) is not None)]
    if not 1 <= len(keys) <= 128 or len(keys) != len(set(keys)):
        _fail()
    if spell_checkpoint is not None and not (checkpoint_choice_keys
            | _confirmed_spell_metric_keys(definition, state, numeric)) <= set(keys):
        _fail()
    from .character_spell_reconstruction import superseded_preparation_authorizations
    superseded = superseded_preparation_authorizations(definition, candidate,
        spell_checkpoint.checkpoint if spell_checkpoint is not None else None)
    _require_preparation_retirement_custody(superseded, numeric)
    payload = _replay_numeric_authorizations(deepcopy(candidate.to_dict()), (), superseded=superseded)
    batch = []
    source_bases = {}
    for kind, path, metric in keys:
        if fresh_values[(kind, path, metric)] is None:
            _fail()
        if kind != "resource" and check.numeric_basis_digest(path) is None:
            _fail()
        if path.startswith("spell_slot:") and not reconstructed:
            _fail()  # This bounded native-input route does not reselect spells.
        if path.startswith("hit_die:") and resource_bases.get(path) is None:
            _fail()
        if reconstructed:
            if kind in {"spell_metric", "spell_choice"} and (kind, path, metric) not in checkpoint_choice_keys:
                retain(kind, path, metric, fresh_values[(kind, path, metric)])
            basis = resource_bases.get(path) if kind == "resource" else check.numeric_basis_digest(path)
            if basis is None:
                _fail()
            marker = numeric_authorization_record(
                character_slug=character, target_kind=kind, target_id=path, metric=metric,
                raw_value=fresh_values[(kind, path, metric)], action_id=action_id,
                provenance="native_requalification")
            source_bases[path] = basis
            batch.append(marker)
            payload = add_numeric_authorization(payload, marker)
            continue
        marker = numeric_authorization_record(
            character_slug=character, target_kind=kind, target_id=path, metric=metric,
            raw_value=fresh_values[(kind, path, metric)], action_id=action_id, provenance="manager",
            owner_digest=numeric_target_owner_digest(candidate, state, kind, path, metric))
        batch.append(marker)
        payload = add_numeric_authorization(payload, marker)
    candidate = CharacterDefinition.from_dict(payload)
    simulated = tuple({"authorization": marker, "source_basis_digest": source_bases[marker["target_id"]]}
                      if marker.get("provenance") == "native_requalification" else marker for marker in batch)
    final = authority_for(candidate, (*numeric, *simulated))
    final = _check_prospective_aggregate_parity(
        candidate, state, final, tuple(batch), systems_service=systems_service,
        campaign_page_records=campaign_page_records, source_read_phase=source_read_phase)
    provenance = {"schema_version": 1, "source_identity": identity,
                  "audit_prefix_digest": _audit_prefix(db, campaign, character),
                  "prior_generation": record.committed_revision,
                  "prior_definition_digest": _digest(definition.to_dict()),
                  "prior_state_revision": record.state_record.revision,
                  "prior_state_digest": _digest(state),
                  "retained_inputs": retained,
                  "native_lineage": {key: deepcopy(native[key]) for key in (
                      "audit_id", "actor_user_id", "event_type", "metadata_sha256", "generation")},
                  "background_tools": sorted(background_tools),
                  "source_snapshot_digest": final.source_snapshot_digest,
                  "targets": [list(key) for key in keys]}
    if reconstructed:
        from .character_reconstruction_authority import capacity_frame
        provenance["schema_version"] = 2
        provenance["capacity_frame"] = capacity_frame(state)
        provenance["renewed_source_bases"] = source_bases
        provenance["targets"] = [[row["target_kind"], row["target_id"], row["metric"]] for row in batch]
    if spell_origin_plan is not None:
        provenance["schema_version"] = (6 if current_resource_inputs else 5) if spell_checkpoint is not None else 4
        if current_resource_inputs:
            provenance["current_resource_inputs"] = current_resource_inputs
        provenance["spell_origin_plan"] = spell_origin_plan
        provenance["origin_headers"], provenance["retained_inputs"] = _compact_retained_origins(retained)
        if retained_requalification_inputs(provenance) != retained:
            _fail()
    if atomic_item_adoption is not None:
        if historical_capacity_inputs:
            _fail()
        provenance["schema_version"] = 7
        provenance["current_resource_inputs"] = current_resource_inputs
        provenance["atomic_item_adoption"] = atomic_item_adoption.descriptor(candidate, final)
    if historical_capacity_inputs:
        provenance["schema_version"] = 8
        provenance["current_resource_inputs"] = current_resource_inputs
        provenance["historical_capacity_inputs"] = historical_capacity_inputs
        _historical_capacity_keys(definition, candidate, provenance, state=state, history=history)
    if source_identity(db, campaign, character) != identity:
        _fail()
    result = NativeRequalification(candidate, tuple(batch), provenance, final, spell_checkpoint, atomic_item_adoption)
    object.__setattr__(result, "_binding", (_NATIVE_RESULT_ISSUER, campaign, character,
        actor_id, record.committed_revision, record.state_record.revision, action_id,
        _digest(definition.to_dict()), _digest(state), _digest(candidate.to_dict()),
        _digest(result.authorizations), _digest(provenance), final.identity, final.source_snapshot_digest))
    if spell_checkpoint is not None:
        validate_native_spell_choice_decision_transition(record, candidate, state,
            prior_authority=initial, actor_id=actor_id, operation_kind="character_update_apply",
            systems_service=systems_service, campaign_page_records=campaign_page_records,
            checkpoint_proof=result, connection=db)
    if source_read_phase is not None:
        source_read_phase.finish()
    return result


def _require_preparation_retirement_custody(superseded, witnesses):
    """Only earlier independently admitted witnesses can lose current custody."""
    for marker in superseded:
        if not any(type(witness) is dict and witness.get("authorization", witness) == marker
                   for witness in witnesses):
            _fail("A superseded preparation witness has no authenticated earlier origin.")


def _replay_numeric_authorizations(payload, batch, *, copy_first=False, superseded=()):
    """Rebuild only private expected source content, never an authority result."""
    from .character_source_authority import _plain_preparation_data
    from .character_source_repair import add_numeric_authorization
    if type(batch) in (list, tuple) and not batch and not superseded:
        return payload
    if superseded:
        # This pure replay grants no authority. Callers derive this exact set
        # from validated CP3 history and authenticate its earlier origins.
        if copy_first:
            payload = deepcopy(payload)
            copy_first = False
        source = dict(payload.get("source") or {})
        existing = source.get("source_authorizations", [])
        if type(existing) is not list or any(type(row) is not dict for row in existing):
            _fail()
        if any(existing.count(marker) != 1 for marker in superseded):
            _fail()
        source["source_authorizations"] = [row for row in existing if row not in superseded]
        payload["source"] = source
    if not _plain_preparation_data((payload, batch)):
        for marker in batch:
            payload = add_numeric_authorization(payload, marker)
        return payload
    if copy_first:
        payload = deepcopy(payload)
    source = dict(payload.get("source") or {})
    for marker in batch:
        existing = source.get("source_authorizations") or []
        if not isinstance(existing, list) or any(not isinstance(row, dict) for row in existing):
            raise SourceRepairError("Existing source authorizations are malformed.")
        # Ordinary rows were proved above. Match the public helper's linear
        # removal, normalization and append order without mutating descendants.
        source["source_authorizations"] = [
            dict(row) for row in existing
            if not (row.get("target_kind") == marker["target_kind"]
                    and row.get("target_id") == marker["target_id"]
                    and row.get("metric") == marker["metric"])
        ] + [dict(marker)]
    payload["source"] = source
    return payload


def _verified_requalification_batch(connection: Any, campaign: str, character: str,
                                    audit_row: Any, metadata: dict[str, Any], *,
                                    history_cache: dict[str, Any] | None = None) -> tuple[dict[str, Any], ...]:
    """Validate one dedicated confirmed manager batch; never an ordinary attest."""
    from .character_ability_inputs import input_records
    from .character_source_authority import numeric_target_values, numeric_target_owner_digest, numeric_value_digest
    from .character_source_repair import _sha256_hex, _valid_numeric_witness_marker
    actor = audit_row["actor_user_id"]
    proof = metadata.get("native_requalification")
    fields = {"schema_version", "source_identity", "audit_prefix_digest", "prior_generation",
              "prior_definition_digest", "prior_state_revision", "prior_state_digest", "retained_inputs",
              "native_lineage", "background_tools", "source_snapshot_digest", "targets"}
    if isinstance(proof, dict) and proof.get("schema_version") in {2, 3, 4, 5, 6, 7, 8}:
        fields.update({"capacity_frame", "renewed_source_bases"})
    if isinstance(proof, dict) and proof.get("schema_version") in {3, 4, 5, 6, 7, 8}:
        fields.update({"spell_origin_plan", "origin_headers"})
    if isinstance(proof, dict) and proof.get("schema_version") in {6, 7, 8}:
        fields.add("current_resource_inputs")
    if isinstance(proof, dict) and proof.get("schema_version") == 8:
        fields.add("historical_capacity_inputs")
    if isinstance(proof, dict) and proof.get("schema_version") == 7:
        fields.add("atomic_item_adoption")
    if (type(actor) is not int or actor < 1 or metadata.get("numeric_actor_id") != actor
            or metadata.get("source") != "character_source_repair"
            or metadata.get("manager_action") != "native_requalify"
            or metadata.get("review_action") != "native_requalify"
            or not isinstance(proof, dict) or set(proof) != fields or proof.get("schema_version") not in {1, 2, 3, 4, 5, 6, 7, 8}
            or any(not _sha256_hex(metadata.get(key)) for key in (
                "review_digest", "candidate_digest", "published_definition_digest", "review_source_digest"))
            or metadata["candidate_digest"] != metadata["published_definition_digest"]
            or type(metadata.get("published_revision")) is not int
            or type(metadata.get("published_state_revision")) is not int
            or type(proof.get("prior_state_revision")) is not int
            or metadata["published_state_revision"] not in {
                proof["prior_state_revision"], proof["prior_state_revision"] + 1}
            or (proof.get("schema_version") == 1 and proof.get("source_identity") != source_identity(connection, campaign, character))
            or (proof.get("schema_version") in {2, 3, 4, 5, 6, 7, 8} and (not isinstance(proof.get("source_identity"), dict)
                or set(proof["source_identity"]) != {"config", "systems", "pages", "page_current"}))
            or (proof.get("schema_version") == 8
                and metadata["published_state_revision"] != proof["prior_state_revision"])
            or proof.get("audit_prefix_digest") != _audit_prefix(connection, campaign, character, audit_row["id"])):
        return ()
    if proof["schema_version"] in {5, 6, 7, 8} and any(not _sha256_hex(proof.get(key)) for key in (
            "prior_definition_digest", "prior_state_digest", "source_snapshot_digest", "audit_prefix_digest")):
        return ()
    try:
        payload, generation = _generation(connection, campaign, character,
            metadata["candidate_digest"], actor, metadata["published_revision"])
        definition = CharacterDefinition.from_dict(payload)
        _canonical_skill_inputs(definition)
        prior_revision = proof.get("prior_generation")
        if type(prior_revision) is not int or not 1 <= prior_revision < generation["revision"]:
            return ()
        prior_row = connection.execute(
            "SELECT actor_user_id FROM committed_source_generations WHERE campaign_slug=? "
            "AND object_kind='character' AND object_ref=? AND revision=?",
            (campaign, character, prior_revision)).fetchone()
        if prior_row is None:
            return ()
        prior_payload, _ = _generation(connection, campaign, character, proof["prior_definition_digest"],
                                       prior_row["actor_user_id"], prior_revision)
        prior_definition = CharacterDefinition.from_dict(prior_payload)
        _canonical_skill_inputs(prior_definition)
        automatic_keys = set()
        checkpoint_keys = set()
        origin_identity = None
        origin_service = None
        if proof["schema_version"] in {3, 4, 5, 6, 7, 8}:
            from .auth import get_systems_service
            plan = proof.get("spell_origin_plan")
            if (type(proof["schema_version"]) is not int or not isinstance(plan, dict)
                    or type(metadata.get("numeric_actor_id")) is not int
                    or metadata["published_state_revision"] != proof["prior_state_revision"]):
                return ()
            if proof["schema_version"] in {3, 4}:
                origin_identity = source_identity(connection, campaign, character)
                origin_service = get_systems_service()
            # Reconstruct from the authenticated ORIGINAL generation and fresh
            # attained sources. The published candidate supplies no origin.
            if proof["schema_version"] in {4, 5, 6, 7, 8}:
                if metadata["published_revision"] != prior_revision + 1 or any(plan.get(key) != value for key, value in (
                        ("prior_generation", prior_revision),
                        ("prior_definition_digest", proof["prior_definition_digest"]),
                        ("prior_state_revision", proof["prior_state_revision"]))):
                    return ()
                corrected, expected_plan = _saved_spell_origin_correction(prior_definition, definition, plan)
                if proof["schema_version"] in {5, 6, 7, 8}:
                    checkpoint = plan.get("current_checkpoint")
                    if (plan.get("schema_version") not in {3, 4, 5} or not isinstance(checkpoint, dict)
                            or any(checkpoint.get(key) != value for key, value in (
                                ("actor_id", actor), ("action_id", metadata.get("action_id")),
                                ("prior_generation", prior_revision),
                                ("prior_state_revision", proof["prior_state_revision"])))):
                        return ()
                    from .character_spell_reconstruction import checkpoint_choice_ids
                    checkpoint_keys = {("spell_choice", f"spell_choice:{identity}", "selection")
                        for identity in checkpoint_choice_ids(checkpoint, definition)}
                elif plan.get("schema_version") != 2:
                    return ()
            else:
                corrected, expected_plan = _prepare_legacy_spell_origin_correction(
                    prior_definition, origin_service, plan.get("request"))
            if _digest(expected_plan) != _digest(plan) or _digest(corrected.spellcasting) != _digest(definition.spellcasting):
                return ()
            if proof["schema_version"] == 3:
                automatic_keys = {("spell_choice", f"spell_choice:{row['spell_id']}", "selection")
                                  for row in expected_plan["automatic"]}
        preserved = ("profile", "proficiencies", "reference_notes")
        if proof["schema_version"] == 7:
            from .character_atomic_source_adoption import validate_saved_adoption
            validate_saved_adoption(prior_definition, definition, proof, actor_id=actor,
                                    action_id=metadata.get("action_id"))
        else:
            preserved += ("equipment_catalog",)
        if proof["schema_version"] not in {6, 7, 8}:
            preserved += ("features",)
        if proof["schema_version"] not in {3, 4, 5, 6, 7, 8}:
            preserved += ("spellcasting",)
        for name in preserved:
            if (_digest(prior_payload.get(name)) != _digest(payload.get(name)) if proof["schema_version"] in {3, 4, 5, 6, 7, 8}
                    else prior_payload.get(name) != payload.get(name)):
                return ()
        if dict(prior_payload.get("source") or {}).get("native_progression") != definition.source.get("native_progression"):
            return ()
        if history_cache is not None and "history" in history_cache:
            history = history_cache["history"]
        else:
            history = _confirmed_history(connection, campaign, character)
            if history_cache is not None:
                history_cache["history"] = history
        by_audit = {row["audit_id"]: row for row in history if row["audit_id"] < audit_row["id"]}
        lineage = proof["native_lineage"]
        native = by_audit.get(lineage.get("audit_id")) if isinstance(lineage, dict) else None
        if (native is None or not (native["event_type"] in {"character_native_created", "character_native_leveled"}
                or native["event_type"] == "character_update_applied" and native["metadata"].get("manager_action") == "native_reconstruct")
                or any(lineage.get(key) != native[key] for key in (
                    "audit_id", "actor_user_id", "event_type", "metadata_sha256", "generation"))
                or definition.profile.get("classes") != native["definition"].get("profile", {}).get("classes")
                or definition.source.get("native_progression") != native["definition"].get("source", {}).get("native_progression")):
            return ()
        retained = retained_requalification_inputs(proof)
        if not isinstance(retained, list) or not 6 <= len(retained) <= 128:
            return ()
        from .character_hit_dice import derive_hit_dice_max_pools
        proof_state = _historical_capacity_state(definition, metadata)
        values = numeric_target_values(definition, proof_state)
        historical_capacity_keys = _historical_capacity_keys(prior_definition, definition, proof,
            history=[entry for entry in by_audit.values()])
        if historical_capacity_keys:
            values = {key: value for key, value in values.items() if key not in historical_capacity_keys}
        retained_keys = []
        for item in retained:
            old = by_audit.get(item.get("audit_id")) if isinstance(item, dict) else None
            if old is None or any(item.get(key) != old[key] for key in (
                    "actor_user_id", "event_type", "metadata_sha256", "generation")):
                return ()
            key = (item.get("target_kind"), item.get("target_id"), item.get("metric"))
            if key in retained_keys or key not in values:
                return ()
            retained_keys.append(key)
            current = values[key]
            old_definition = CharacterDefinition.from_dict(old["definition"])
            old_values = numeric_target_values(old_definition, _historical_capacity_state(old_definition, old["metadata"]))
            previous = old_values.get(key)
            accepted = dict(history_cache or {}).get("accepted_batches", {}).get(old["audit_id"], ())
            if old["event_type"] in {"character_native_created", "character_native_spell_selected", "character_native_leveled"}:
                from .character_source_repair import NativeSpellChoiceDecision
                accepted = tuple(w for w in dict(history_cache or {}).get("prior_numeric_witnesses", ())
                    if type(w) is NativeSpellChoiceDecision and w.origin[2] == old["audit_id"])
            if old["event_type"] == "character_native_edited":
                from .character_external_proficiencies import ExternalProficiencyCustody
                accepted = tuple(w for w in dict(history_cache or {}).get("prior_numeric_witnesses", ())
                    if type(w) is ExternalProficiencyCustody and w.origin[1] == old["audit_id"])
            if old["metadata"].get("manager_action") == "native_reconstruct":
                from .character_reconstruction_authority import verified_reconstruction_batch
                accepted = verified_reconstruction_batch(connection, campaign, character,
                    {"actor_user_id": old["actor_user_id"]}, old["metadata"],
                    prior_witnesses=tuple(dict(history_cache or {}).get("prior_numeric_witnesses", ())))
            if old["metadata"].get("manager_action") == "native_language_elective_decision":
                from .character_language_electives import confirmed_batch_for_audit
                accepted = confirmed_batch_for_audit(tuple(dict(history_cache or {}).get("prior_numeric_witnesses", ())),
                    old["audit_id"], old["metadata"])
            if _historical_numeric_marker(old, key, accepted_currentness=accepted) is None:
                return ()
            current = _retained_identity(*key, current)
            previous = _retained_identity(*key, previous)
            # Equality authenticates the seed before either hash format is
            # interpreted. Legacy omission hashes never excuse substitution.
            if current != previous:
                return ()
            hashes = {numeric_value_digest(current)}
            if key[0] == "resource" and key[1].startswith("resource:"):
                hashes.add(numeric_value_digest({name:value for name,value in current.items() if name != "initial_current"}))
            if item.get("input_digest") not in hashes:
                return ()
        from .character_ability_inputs import KEYS
        if not all(("field", f"stats.ability_scores.{ability}.score", "base") in retained_keys for ability in KEYS):
            return ()
        tools = proof["background_tools"]
        if (not isinstance(tools, list) or any(not isinstance(name, str) for name in tools)
                or tools != sorted(set(tools))):
            return ()
        try:
            from .auth import get_systems_service
            service = get_systems_service() if definition.profile.get("background_choices") is not None else None
            background_tools = _current_background_tools(definition, service)
        except (AttributeError, KeyError, RuntimeError, TypeError, ValueError):
            return ()
        if tools != sorted(background_tools):
            return ()
        current_resource_keys = set()
        if proof["schema_version"] in {6, 7, 8}:
            current_resource_keys = _verify_current_resource_admissions(prior_definition, definition,
                proof, retained, history=[entry for entry in by_audit.values()])
        _retained_key_closure(values, retained, background_tools, definition,
            current_resource_keys=current_resource_keys)
        batch = metadata.get("numeric_authorizations")
        targets = proof.get("targets")
        if (not isinstance(batch, list) or not 1 <= len(batch) <= 128
                or not isinstance(targets, list) or len(targets) != len(batch)):
            return ()
        keys = []
        # Resource owner digests do not include current/spent values. Hit Die
        # owner data is reconstructed from the published definition/class rows.
        state = _historical_capacity_state(definition, metadata)
        state.setdefault("resources", [])
        state.setdefault("spell_slots", [])
        raw_values = numeric_target_values(definition, state)
        if historical_capacity_keys:
            raw_values = {key: value for key, value in raw_values.items() if key not in historical_capacity_keys}
        current_resource_bases = {}
        if proof["schema_version"] in {3, 4}:
            _, current_resource_bases = _retained_resource_source_frame(
                definition, state, retained, systems_service=origin_service, campaign_page_records=None,
                state_revision=metadata["published_state_revision"])
        for marker in batch:
            source_bound = marker.get("provenance") == "native_requalification" if isinstance(marker, dict) else False
            if (not _valid_numeric_witness_marker(marker, character, "native_requalification" if source_bound else "manager")
                    or marker.get("action_id") != metadata.get("action_id")):
                return ()
            key = (marker["target_kind"], marker["target_id"], marker["metric"])
            if (key in keys or key not in raw_values
                    or numeric_value_digest(raw_values[key]) != marker["value_digest"]
                    or (not source_bound and numeric_target_owner_digest(definition, state, *key) != marker["owner_digest"])
                    or (source_bound and (proof.get("schema_version") not in {2, 3, 4, 5, 6, 7, 8}
                        or not _sha256_hex(dict(proof.get("renewed_source_bases") or {}).get(marker["target_id"]))))
                    or (proof["schema_version"] in {3, 4} and key[0] == "resource" and (
                        current_resource_bases.get(key[1]) is None
                        or current_resource_bases[key[1]] != proof["renewed_source_bases"].get(key[1])))):
                return ()
            keys.append(key)
        if [list(key) for key in keys] != targets:
            return ()
        from .character_source_authority import native_baseline_target
        expected_keys = {key for key in raw_values if not _unresolved_proficiency_target(definition, key) and (
            native_baseline_target(*key) or key[0] == "resource"
            or key in {("field", "stats.proficiency_bonus", "final"), ("field", "stats.max_hp", "final")}
            or key[0] == "field" and key[2] == "base"
            )}
        optional_spell_keys = {key for key in raw_values if proof.get("schema_version") in {2, 3, 4, 5, 6, 7, 8}
                               and key[0] in {"spell_metric", "spell_choice"}}
        if not expected_keys <= set(keys) <= expected_keys | optional_spell_keys:
            return ()
        if (not automatic_keys <= set(keys) or automatic_keys & set(retained_keys)
                or not checkpoint_keys <= set(keys) or checkpoint_keys & set(retained_keys)
                or any(key not in retained_keys and key not in automatic_keys and key not in checkpoint_keys
                       for key in set(keys) & optional_spell_keys)
                or proof["schema_version"] in {5, 6, 7, 8} and any(key[0] == "spell_choice" and key not in checkpoint_keys for key in keys)):
            return ()
        if proof["schema_version"] in {5, 6, 7, 8}:
            earlier_witnesses = (*dict(history_cache or {}).get("prior_numeric_witnesses", ()),
                *(w for old_id, old_batch in dict(history_cache or {}).get("accepted_batches", {}).items()
                    if old_id < audit_row["id"] for w in old_batch))
            if not _confirmed_spell_metric_keys(prior_definition,
                    _historical_capacity_state(prior_definition, metadata), earlier_witnesses) <= set(keys):
                return ()
        if proof.get("schema_version") in {2, 3, 4, 5, 6, 7, 8} and any(marker.get("provenance") != "native_requalification" for marker in batch):
            return ()
        source_bases = dict(proof.get("renewed_source_bases") or {})
        if set(source_bases) != {marker["target_id"] for marker in batch if marker.get("provenance") == "native_requalification"}:
            return ()
        if proof["schema_version"] == 3:
            from .character_source_authority import _source_derived_spell_choice_bases
            from .character_profile import profile_class_rows
            bases = _source_derived_spell_choice_bases(
                definition, systems_service=origin_service, pages={},
                verified_class_rows=frozenset(row["row_id"] for row in profile_class_rows(definition.profile)),
                source_snapshot_digest=proof["source_snapshot_digest"])
            if any(bases.get(key[1]) is None or bases[key[1]] != source_bases.get(key[1]) for key in automatic_keys):
                return ()
            renewed = _replay_numeric_authorizations(prior_payload, batch, copy_first=True)
            if (_digest(renewed.get("source")) != _digest(payload.get("source"))
                    or source_identity(connection, campaign, character) != origin_identity):
                return ()
        if proof["schema_version"] in {4, 5, 6, 7, 8}:
            from .character_spell_grants import grant_model_digest
            if (grant_model_digest(corrected) != grant_model_digest(definition)
                    or any(marker.get("target_kind") == "spell_choice"
                           and marker.get("target_id", "").removeprefix("spell_choice:") in {
                               row["spell_id"] for row in expected_plan["automatic"]} for marker in batch)):
                return ()
            renewed = deepcopy(prior_payload)
            renewed["source"]["native_acquisitions"] = deepcopy(corrected.source["native_acquisitions"])
            superseded = ()
            if proof["schema_version"] in {5, 6, 7, 8}:
                from .character_spell_reconstruction import superseded_preparation_authorizations
                superseded = superseded_preparation_authorizations(prior_definition, definition, checkpoint)
                _require_preparation_retirement_custody(superseded, earlier_witnesses)
            renewed = _replay_numeric_authorizations(renewed, batch, superseded=superseded)
            if (_digest(renewed.get("source")) != _digest(payload.get("source"))
                    or proof["schema_version"] == 4 and source_identity(connection, campaign, character) != origin_identity):
                return ()
        result = tuple({"authorization": dict(marker), "source_basis_digest": source_bases[marker["target_id"]]}
                     if marker.get("provenance") == "native_requalification" else dict(marker) for marker in batch)
        if proof["schema_version"] in {5, 6, 7, 8}:
            from .character_spell_reconstruction import reconstruction_facts
            from .character_source_repair import NativeSpellChoiceDecision
            from .character_spell_grants import native_class_choice_state
            origin = (campaign, character, audit_row["id"], actor, generation["revision"])
            facts = reconstruction_facts(checkpoint, definition, origin=origin)
            rows = {row["id"]: row for row in definition.spellcasting["spells"]}
            decisions = tuple(NativeSpellChoiceDecision(target_id=marker["target_id"],
                row_digest=_digest(rows[marker["target_id"].removeprefix("spell_choice:")]),
                state=native_class_choice_state(rows[marker["target_id"].removeprefix("spell_choice:")]),
                authorization=marker, origin=origin,
                source_snapshot_digest=(proof.get("source_snapshot_digest")
                    if _sha256_hex(proof.get("source_snapshot_digest")) else None)) for marker in batch
                if (marker["target_kind"], marker["target_id"], marker["metric"]) in checkpoint_keys)
            result += tuple(facts) + decisions
        return result
    except (AttributeError, KeyError, RuntimeError, TypeError, ValueError):
        return ()


def _verified_spell_grant_migration_custody(connection, campaign, character, audit_row, metadata):
    """Authenticate only saved grant custody, independently of current numbers."""
    from .character_spell_grants import NativeGrantCustody
    from .character_source_repair import _sha256_hex
    proof = metadata.get("native_requalification")
    actor = audit_row["actor_user_id"]
    fields = {"schema_version", "source_identity", "audit_prefix_digest", "prior_generation",
        "prior_definition_digest", "prior_state_revision", "prior_state_digest", "retained_inputs",
        "native_lineage", "background_tools", "source_snapshot_digest", "targets",
        "capacity_frame", "renewed_source_bases", "spell_origin_plan", "origin_headers"}
    if isinstance(proof, dict) and proof.get("schema_version") in {6, 7, 8}:
        fields.add("current_resource_inputs")
    if isinstance(proof, dict) and proof.get("schema_version") == 8:
        fields.add("historical_capacity_inputs")
    if isinstance(proof, dict) and proof.get("schema_version") == 7:
        fields.add("atomic_item_adoption")
    if (not isinstance(proof, dict) or type(proof.get("schema_version")) is not int
            or proof["schema_version"] not in {4, 5, 6, 7, 8} or set(proof) != fields or type(actor) is not int or actor < 1
            or metadata.get("numeric_actor_id") != actor
            or metadata.get("source") != "character_source_repair"
            or metadata.get("manager_action") != "native_requalify"
            or metadata.get("review_action") != "native_requalify"
            or any(not _sha256_hex(metadata.get(key)) for key in (
                "review_digest", "candidate_digest", "published_definition_digest", "review_source_digest"))
            or metadata["candidate_digest"] != metadata["published_definition_digest"]
            or type(metadata.get("published_revision")) is not int
            or type(proof.get("prior_generation")) is not int
            or proof["prior_generation"] < 1
            or metadata["published_revision"] != proof["prior_generation"] + 1
            or type(proof.get("prior_state_revision")) is not int
            or metadata.get("published_state_revision") != proof["prior_state_revision"]
            or proof.get("audit_prefix_digest") != _audit_prefix(connection, campaign, character, audit_row["id"])):
        return ()
    try:
        retained_requalification_inputs(proof)  # Lossless bounded historical envelope.
        payload, generation = _generation(connection, campaign, character,
            metadata["candidate_digest"], actor, metadata["published_revision"])
        prior_actor = connection.execute(
            "SELECT actor_user_id FROM committed_source_generations WHERE campaign_slug=? "
            "AND object_kind='character' AND object_ref=? AND revision=?",
            (campaign, character, proof["prior_generation"])).fetchone()
        if prior_actor is None:
            return ()
        prior_payload, prior_generation = _generation(connection, campaign, character,
            proof["prior_definition_digest"], prior_actor["actor_user_id"], proof["prior_generation"])
        prior = CharacterDefinition.from_dict(prior_payload)
        candidate = CharacterDefinition.from_dict(payload)
        historical_capacity_keys = _historical_capacity_keys(prior, candidate, proof)
        if historical_capacity_keys and any(type(marker) is dict and (
                marker.get("target_kind"), marker.get("target_id"), marker.get("metric")) in historical_capacity_keys
                for marker in metadata.get("numeric_authorizations", [])):
            return ()
        plan = proof["spell_origin_plan"]
        preserved = ("profile", "proficiencies", "reference_notes")
        if proof["schema_version"] == 7:
            from .character_atomic_source_adoption import validate_saved_adoption
            validate_saved_adoption(prior, candidate, proof, actor_id=actor, action_id=metadata.get("action_id"))
        else:
            preserved += ("equipment_catalog",)
        if (any(plan.get(key) != proof.get(key) for key in (
                "prior_generation", "prior_definition_digest", "prior_state_revision"))
                or any(prior_payload.get(name) != payload.get(name) for name in preserved)
                or _digest(_admission_feature_rows(prior, proof) if proof["schema_version"] in {6, 7, 8} else prior.features)
                    != _digest(candidate.features)):
            return ()
        if proof["schema_version"] in {5, 6, 7, 8}:
            checkpoint = plan.get("current_checkpoint")
            if (plan.get("schema_version") not in {3, 4, 5} or type(checkpoint) is not dict
                    or any(checkpoint.get(key) != value for key, value in (
                        ("actor_id", actor), ("action_id", metadata.get("action_id")),
                        ("prior_generation", proof["prior_generation"]),
                        ("prior_state_revision", proof["prior_state_revision"])))):
                return ()
        elif plan.get("schema_version") != 2:
            return ()
        expected_source = deepcopy(prior.source)
        expected_source["native_acquisitions"] = deepcopy(candidate.source["native_acquisitions"])
        expected_source["source_authorizations"] = deepcopy(candidate.source.get("source_authorizations", []))
        if expected_source != candidate.source:
            return ()
        _saved_spell_origin_correction(prior, candidate, plan)
        return (NativeGrantCustody(candidate, origin=("confirmed_native_migration", campaign, character,
            audit_row["id"], metadata["review_digest"], prior_generation, generation)),)
    except (AttributeError, KeyError, RuntimeError, TypeError, ValueError):
        return ()


def verified_requalification_batch(connection: Any, campaign: str, character: str,
                                    audit_row: Any, metadata: dict[str, Any], *,
                                    history_cache: dict[str, Any] | None = None) -> tuple[dict[str, Any], ...]:
    """Validate the bounded older-origin DAG before accepting its descendant.

    The cache is request/source/history framed, never a persistent trust store.
    Iterative ordering avoids an additional Python recursion-depth contract.
    """
    cache = history_cache if history_cache is not None else {}
    try:
        if "prior_numeric_witnesses" not in cache:
            # The composed uncached reader needs the same independently admitted
            # decisions as the outer loader. Its own calls already supply this
            # key, so this does not recurse through another uncached history.
            from .character_source_repair import load_verified_numeric_actions
            cache["prior_numeric_witnesses"] = load_verified_numeric_actions(
                campaign, character, connection=connection, strict=True)
        if "history" not in cache:
            cache["history"] = _confirmed_history(connection, campaign, character)
        history = cache["history"]
        by_audit = {entry["audit_id"]: entry for entry in history}
        entry = by_audit.get(audit_row["id"])
        if (entry is None or entry["actor_user_id"] != audit_row["actor_user_id"]
                or entry["metadata"] != metadata):
            return ()
        frame = _digest({"campaign":campaign, "character":character,
            "source":source_identity(connection, campaign, character),
            "audit_prefix":_audit_prefix(connection, campaign, character),
            "history":[{name:item[name] for name in ("audit_id", "actor_user_id", "metadata_sha256", "generation")} for item in history]})
        if cache.get("accepted_batch_frame") != frame:
            cache["accepted_batch_frame"] = frame
            cache["accepted_batches"] = {}
        accepted = cache["accepted_batches"]
        pending, required = [entry["audit_id"]], set()
        while pending:
            audit_id = pending.pop()
            if audit_id in required or audit_id in accepted:
                continue
            required.add(audit_id)
            if len(required) > 2048:
                return ()
            current = by_audit[audit_id]
            proof = current["metadata"].get("native_requalification")
            retained = retained_requalification_inputs(proof)
            if not isinstance(retained, list) or not 6 <= len(retained) <= 128:
                continue  # The semantic validator below memoizes refusal.
            for item in retained:
                prior_id = item.get("audit_id") if isinstance(item, dict) else None
                if type(prior_id) is not int or prior_id >= audit_id:
                    continue  # Missing/future/self origins fail exact lookup below.
                prior = by_audit.get(prior_id)
                if (prior is not None and prior["event_type"] == "character_update_applied"
                        and prior["metadata"].get("manager_action") == "native_requalify"):
                    pending.append(prior_id)
        for audit_id in sorted(required):
            current = by_audit[audit_id]
            accepted[audit_id] = _verified_requalification_batch(
                connection, campaign, character,
                {"id":audit_id, "actor_user_id":current["actor_user_id"]},
                current["metadata"], history_cache=cache,
            )
            from .character_spell_grants import NativeGrantCustody
            numeric = tuple(row for row in accepted[audit_id] if not isinstance(row, NativeGrantCustody))
            from .character_source_repair import NativeSpellChoiceDecision, _sha256_hex
            from .character_spell_grants import native_class_choice_state
            from .character_source_authority import ordinary_native_spell_choice_state
            current_definition = CharacterDefinition.from_dict(current["definition"])
            choice_rows = {row.get("id"): row for row in current_definition.spellcasting.get("spells", []) if isinstance(row, dict)}
            decision_renewals = []
            checkpoint_keys = set()
            current_proof = current["metadata"].get("native_requalification")
            if isinstance(current_proof, dict) and current_proof.get("schema_version") in {5, 6, 7, 8}:
                from .character_spell_reconstruction import checkpoint_choice_ids
                checkpoint_keys = {f"spell_choice:{identity}" for identity in checkpoint_choice_ids(
                    current_proof["spell_origin_plan"]["current_checkpoint"], current_definition)}
            for witness in numeric:
                if type(witness) is not dict:
                    continue  # Preserve typed facts/decisions, never coerce them into numeric markers.
                marker = witness.get("authorization", witness)
                if marker.get("target_kind") != "spell_choice":
                    continue
                if marker.get("target_id") in checkpoint_keys:
                    continue  # The complete schema-5 reader already issued its actual decision.
                raw = choice_rows.get(marker.get("target_id", "").removeprefix("spell_choice:"))
                if raw is None or native_class_choice_state(raw) is None:
                    continue
                retained = [item for item in retained_requalification_inputs(current["metadata"].get("native_requalification"))
                    if item.get("target_kind") == "spell_choice" and item.get("target_id") == marker["target_id"]]
                if len(retained) != 1:
                    return ()
                origin = by_audit.get(retained[0]["audit_id"])
                old_markers = [m for m in origin["definition"].get("source", {}).get("source_authorizations", [])
                    if isinstance(m, dict) and m.get("target_kind") == "spell_choice" and m.get("target_id") == marker["target_id"]]
                earlier = (*cache.get("prior_numeric_witnesses", ()),
                    *(w for batch in accepted.values() for w in batch))
                prior_decisions = tuple(w for w in earlier if type(w) is NativeSpellChoiceDecision
                    and w.origin[2] == origin["audit_id"])
                if (len(old_markers) != 1 or ordinary_native_spell_choice_state(raw, old_markers[0],
                        verified_numeric_actions=prior_decisions) != native_class_choice_state(raw)):
                    return ()
                decision_renewals.append(NativeSpellChoiceDecision(target_id=marker["target_id"],
                    row_digest=_digest(raw), state=native_class_choice_state(raw), authorization=marker,
                    origin=(campaign, character, audit_id, current["actor_user_id"], current["generation"]["revision"]),
                    source_snapshot_digest=(current_proof.get("source_snapshot_digest")
                        if isinstance(current_proof, dict) and _sha256_hex(
                            current_proof.get("source_snapshot_digest")) else None)))
            numeric += tuple(decision_renewals)
            accepted[audit_id] = numeric + _verified_spell_grant_migration_custody(
                connection, campaign, character,
                {"id": audit_id, "actor_user_id": current["actor_user_id"]}, current["metadata"])
        return tuple(deepcopy(marker) for marker in accepted.get(entry["audit_id"], ()))
    except (KeyError, TypeError, ValueError):
        return ()
