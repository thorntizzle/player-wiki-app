"""Explicit ordinary skill adoption inside the existing reconstruction proof.

History records an original observation, not a permanent current skill total.
Only the reconstruction issuer and independently recovered audit supply custody.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

from .character_source_repair import SourceRepairError

FRAME_KEY = "skill_adoptions"
PREFIX = "skill_adoption_"
KEEP = "keep"
_DRAFT = object()
_CONTRACT_FIELDS = {"owner_id", "category", "position", "systems_ref", "class_row_id", "slot_basis_digest"}
_FIELDS = _CONTRACT_FIELDS | {"schema_version", "skill_key", "row_index", "prior_row_json", "adopted_level"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def _skill_rows(definition):
    from .character_builder_constants import SKILL_LABELS
    from .repository import normalize_lookup
    allowed = {normalize_lookup(name) for name in SKILL_LABELS.values()}
    rows = {}
    if type(definition.skills) is not list or len(definition.skills) != len(allowed):
        raise SourceRepairError("Skill adoption needs the complete canonical retained skill rows.")
    for index, row in enumerate(definition.skills):
        name = row.get("name") if type(row) is dict else None
        if (type(name) is not str or name != name.strip()
                or name.casefold() not in {label.casefold() for label in SKILL_LABELS.values()}):
            raise SourceRepairError("Skill adoption has an invalid retained skill identity.")
        key = normalize_lookup(name)
        if key not in allowed or key in rows:
            raise SourceRepairError("Skill adoption has a duplicate or unsupported retained skill.")
        rows[key] = (index, row)
    return rows


def source_slots(definition, service, *, owners=None, slots=None):
    from .character_reconstruction_proficiencies import current_owners, grant_contract
    from .character_builder_equipment import _systems_ref_from_entry
    from .character_profile import profile_class_rows
    owners = current_owners(definition, service) if owners is None else owners
    if slots is None:
        # Artisan domains are irrelevant to the identity of a skill slot.
        _fixed, slots = grant_contract(definition, owners)
    entries = dict(owners)
    classes = profile_class_rows(definition.profile)
    counts, result = {}, {}
    for slot in slots:
        group = slot["owner"], slot["category"]
        position = counts.get(group, 0)
        counts[group] = position + 1
        if slot["category"] != "skills":
            continue
        entry = entries[slot["owner"]]
        contract = {"owner_id": slot["owner"], "category": "skills", "position": position,
            "systems_ref": _systems_ref_from_entry(entry),
            "class_row_id": classes[0].get("row_id") if slot["owner"] == "class" and len(classes) == 1 else None,
            "slot_basis_digest": digest({"entry_key": entry.entry_key, "metadata": entry.metadata,
                "body": entry.body, "slots": [s for s in slots if s["owner"] == slot["owner"] and s["category"] == "skills"]})}
        result[(slot["owner"], position)] = (contract, tuple(slot["options"]))
    return result


def stored(definition):
    from .character_source_repair import _sha256_hex
    from .character_builder_constants import SKILL_LABELS
    from .repository import normalize_lookup
    frame = definition.source.get("native_reconstruction_choices")
    if frame is None:
        return ()
    if type(frame) is not dict:
        raise SourceRepairError("Skill adoption needs a typed reconstruction frame.")
    rows = frame.get(FRAME_KEY, [])
    allowed = {normalize_lookup(name) for name in SKILL_LABELS.values()}
    if type(rows) is not list or len(rows) > len(allowed):
        raise SourceRepairError("Skill adoption history exceeds its supported bound.")
    skills, positions = set(), set()
    for row in rows:
        if (type(row) is not dict or set(row) != _FIELDS
                or type(row["schema_version"]) is not int or row["schema_version"] != 1
                or type(row["skill_key"]) is not str or row["skill_key"] not in allowed
                or row["adopted_level"] != "proficient" or row["category"] != "skills"
                or type(row["owner_id"]) is not str or not 1 <= len(row["owner_id"]) <= 512
                or type(row["position"]) is not int or not 0 <= row["position"] < 18
                or type(row["row_index"]) is not int or not 0 <= row["row_index"] < 18
                or not _sha256_hex(row["slot_basis_digest"])
                or row["class_row_id"] is not None and (type(row["class_row_id"]) is not str or not row["class_row_id"])
                or type(row["prior_row_json"]) is not str or not 1 <= len(row["prior_row_json"]) <= 32768):
            raise SourceRepairError("Skill adoption history is malformed.")
        ref = row["systems_ref"]
        if (type(ref) is not dict or not {"entry_key", "slug", "source_id", "entry_type", "title"} <= set(ref)
                or set(ref) - {"entry_key", "slug", "source_id", "entry_type", "title", "library_slug"}
                or any(type(value) is not str or not value for value in ref.values())):
            raise SourceRepairError("Skill adoption has no exact typed source owner.")
        prior = json.loads(row["prior_row_json"])
        if (type(prior) is not dict or canonical(prior) != row["prior_row_json"]
                or type(prior.get("name")) is not str or prior["name"] != prior["name"].strip()
                or prior["name"].casefold() not in {label.casefold() for label in SKILL_LABELS.values()}
                or normalize_lookup(prior["name"]) != row["skill_key"] or prior.get("proficiency_level") != "none"):
            raise SourceRepairError("Skill adoption must preserve the exact original none-level observation.")
        position = row["owner_id"], row["position"]
        if row["skill_key"] in skills or position in positions:
            raise SourceRepairError("Skill adoption history duplicates a skill or source slot.")
        skills.add(row["skill_key"])
        positions.add(position)
    return tuple(deepcopy(rows))


def choice_fields(definition, service):
    from .repository import normalize_lookup
    adopted = {row["skill_key"] for row in stored(definition)}
    slots = source_slots(definition, service)
    fields = []
    for key, (index, row) in _skill_rows(definition).items():
        if key in adopted or row.get("proficiency_level") != "none":
            continue
        options = []
        for (owner, position), (contract, domain) in slots.items():
            if key not in {normalize_lookup(name) for name in domain}:
                continue
            record = {**deepcopy(contract), "schema_version": 1, "skill_key": key, "row_index": index,
                "prior_row_json": canonical(row), "adopted_level": "proficient"}
            if len(record["prior_row_json"]) > 32768:
                raise SourceRepairError("The original skill observation exceeds the supported history bound.")
            options.append({"label": f"Confirm proficient from {contract['systems_ref']['title']} ({owner} skill choice {position + 1})",
                "value": digest(record), "record": record})
        if options:
            fields.append({"name": PREFIX + key, "label": row["name"], "prior": deepcopy(row), "options": options})
    return fields


def compose(prior, payload, service, values):
    """Compose a draft only; independent issuance must still prove its custody."""
    history = list(stored(prior))
    fields = {field["name"]: field for field in choice_fields(prior, service)}
    for name, value in values.items():
        if name.startswith(PREFIX) and name not in fields:
            raise SourceRepairError("A skill adoption confirmation has no current eligible observation.")
    for name, field in fields.items():
        value = values.get(name, KEEP)
        if value == KEEP:
            continue
        matches = [option["record"] for option in field["options"] if option["value"] == value]
        if len(matches) != 1:
            raise SourceRepairError("The skill adoption source slot or original observation changed.")
        row = matches[0]
        history.append(deepcopy(row))
        payload["skills"][row["row_index"]]["proficiency_level"] = "proficient"
    if history:
        payload["source"]["native_reconstruction_choices"][FRAME_KEY] = history


def custody(definition, origin, rows):
    return (({"skill_adoption_custody": {"campaign_slug": definition.campaign_slug,
        "character_slug": definition.character_slug, "action_id": origin["action_id"],
        "adoption_digest": digest(list(rows)), "adoptions": deepcopy(list(rows))}},) if rows else ())


def require_custody(definition, witnesses):
    rows = stored(definition)
    if not rows:
        return rows
    origin = definition.source.get("native_reconstruction") or {}
    if type(origin) is not dict or origin.get("skill_adoption_digest") != digest(list(rows)):
        raise SourceRepairError("Skill adoption history has no matching reconstruction origin.")
    decoded = [json.loads(value) if isinstance(value, str) else value for value in witnesses]
    if custody(definition, origin, rows)[0] not in decoded:
        raise SourceRepairError("Skill adoption history needs its independently recovered reconstruction witness.")
    return rows


def _current(definition, service, rows, *, owners=None, slots=None):
    from .repository import normalize_lookup
    current = source_slots(definition, service, owners=owners, slots=slots)
    skills = _skill_rows(definition)
    choices = definition.source["native_reconstruction_choices"].get("choices", {})
    for row in rows:
        slot = current.get((row["owner_id"], row["position"]))
        selected = choices.get(f"reconstruction:{row['owner_id']}:skills")
        if (slot is None or slot[0] != {key: row[key] for key in _CONTRACT_FIELDS}
                or row["skill_key"] not in {normalize_lookup(name) for name in slot[1]}
                or type(selected) is not list or len(selected) <= row["position"]
                or type(selected[row["position"]]) is not str
                or normalize_lookup(selected[row["position"]]) != row["skill_key"]
                or skills[row["skill_key"]][1].get("proficiency_level") not in {"proficient", "expertise"}):
            raise SourceRepairError("A skill adoption no longer matches its current selected source slot.")
    return rows


def validate_history(prior, candidate, service=None, *, witnesses=(), draft=False):
    """Validate initial preimages separately from immutable, witnessed replay."""
    old, rows = stored(prior), stored(candidate)
    if rows[:len(old)] != old:
        raise SourceRepairError("Retained skill adoption history cannot be changed or dropped.")
    if old and not draft:
        require_custody(prior, witnesses)
    if not rows:
        return rows
    if (prior.campaign_slug, prior.character_slug) != (candidate.campaign_slug, candidate.character_slug):
        raise SourceRepairError("Skill adoption cannot move between Characters.")
    before, after = _skill_rows(prior), _skill_rows(candidate)
    additions = {row["skill_key"]: row for row in rows[len(old):]}
    inputs = candidate.source["native_reconstruction_choices"].get("inputs", {})
    for key, (index, original) in before.items():
        new_index, current = after[key]
        expected = deepcopy(original)
        if key in additions:
            row = additions[key]
            if (row["row_index"] != index or row["prior_row_json"] != canonical(original)
                    or inputs.get(PREFIX + key) != digest(row)):
                raise SourceRepairError("A skill adoption lacks its exact prior observation and explicit confirmation.")
            expected["proficiency_level"] = "proficient"
        # The normal reconstruction derivation owns bonuses, not extra row edits.
        expected.pop("bonus", None)
        observed = {k: v for k, v in current.items() if k != "bonus"}
        if new_index != index or observed != expected:
            raise SourceRepairError("Reconstruction changed an unconfirmed skill observation.")
    if service is not None:
        _current(candidate, service, rows)
    else:
        # Historical recovery proves the confirmed selected slot independently
        # of whether that source still exists today. Current reads recheck it.
        from .repository import normalize_lookup
        choices = candidate.source["native_reconstruction_choices"].get("choices", {})
        for row in rows:
            values = choices.get(f"reconstruction:{row['owner_id']}:skills")
            if (type(values) is not list or len(values) <= row["position"]
                    or type(values[row["position"]]) is not str
                    or normalize_lookup(values[row["position"]]) != row["skill_key"]):
                raise SourceRepairError("Confirmed skill adoption has no matching selected source slot.")
    return rows


class _DraftAdoptions:
    def __init__(self, definition, *, issuer):
        if issuer is not _DRAFT:
            raise SourceRepairError("Draft skill adoption must come from reconstruction preparation.")
        self.definition_digest = digest(definition.to_dict())


def prepare_draft(prior, candidate, service):
    validate_history(prior, candidate, service, draft=True)
    return _DraftAdoptions(candidate, issuer=_DRAFT)


def resolve(definition, service, witnesses=(), *, owners=None, slots=None, prepared=None):
    rows = stored(definition)
    if not rows:
        return rows
    if not (type(prepared) is _DraftAdoptions and prepared.definition_digest == digest(definition.to_dict())):
        require_custody(definition, witnesses)
    return _current(definition, service, rows, owners=owners, slots=slots)


def validate_transition(prior_record, candidate, proof=None, *, actor_id=None, state=None):
    old, new = stored(prior_record.definition), stored(candidate)
    if old == new:
        return
    from .character_reconstruction_authority import PendingNativeReconstruction
    if type(proof) is not PendingNativeReconstruction or proof.skill_adoptions != new:
        raise SourceRepairError("Skill adoption history changes require the exact reviewed reconstruction.")
    proof.validate_binding(prior_record, candidate, state, actor_id)


def retain_derived_bonuses(composed, derived, payload):
    """Keep the original spelling/content while matching canonical skill output."""
    rows = stored(composed)
    if not rows:
        return
    originals, outputs = _skill_rows(composed), _skill_rows(derived)
    for row in rows:
        index = originals[row["skill_key"]][0]
        output = outputs[row["skill_key"]][1]
        if "bonus" in output:
            payload["skills"][index]["bonus"] = deepcopy(output["bonus"])


def require_qualified_outputs(prior, proof, derived, *, input_proof, state,
                              systems_service, campaign_page_records):
    """Check the actual normalizer output, never an integer retained by merging."""
    from .character_builder_constants import SKILL_ABILITY_KEYS
    old = {row["skill_key"] for row in stored(prior)}
    additions = [row for row in proof.skill_adoptions if row["skill_key"] not in old]
    if not additions:
        return
    bound = input_proof.authority.bind_projected_numbers(derived,
        input_definition=input_proof.candidate, input_state=state,
        systems_service=systems_service, campaign_page_records=campaign_page_records,
        formula_scope="durable")
    skills = _skill_rows(proof.candidate)
    outputs = _skill_rows(derived)
    for row in additions:
        current = skills[row["skill_key"]][1]
        output = outputs[row["skill_key"]][1]
        path = "skills." + current["name"].casefold()
        score = bound.field_status(f"stats.ability_scores.{SKILL_ABILITY_KEYS[row['skill_key']]}.score")
        pb = bound.field_status("stats.proficiency_bonus")
        if (not proof.authority.field_status(path).is_effective or not bound.field_status(path).is_effective
                or not score.is_effective or type(score.effective) is not int
                or not pb.is_effective or type(pb.effective) is not int
                or type(output.get("bonus")) is not int
                or any(current.get(key) != output.get(key) for key in ("bonus", "proficiency_level"))):
            raise SourceRepairError("The adopted skill has no qualified current derived output.")


# Finite ordinary callback surface omitted by invocation-owned current inputs.
_CURRENT_INPUT_RECIPE = tuple((name, globals()[name]) for name in (
    'digest',
    'resolve',
    'stored',
))
