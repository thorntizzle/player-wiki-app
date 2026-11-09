"""Current spell-role confirmation, separate from acquisition or entitlement.

The producer is pure: current sources classify retained observations, while the
saved validator authenticates historical structure without querying sources.
Only the existing native requalification publisher can turn this pending scope
into an audited confirmation. Outer proof owns removal/model and other deltas.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .character_source_repair import SourceRepairError

_ISSUER = object()
_STATE = "native_class_choice_state"
_ROLES = frozenset({"cantrip", "prepared", "known", "book", "available", "automatic", "item"})
_SELECTED = frozenset({"cantrip", "prepared", "known", "book"})
_ENTRY_FIELDS = frozenset({"spell_id", "role", "spell_level", "prior_row_digest", "row_digest", "spell_ref"})
_DIGEST_FIELDS = frozenset({"prior_definition_digest", "prior_spellcasting_digest", "spellcasting_digest",
    "prior_profile_digest", "profile_digest", "prior_ability_inputs_digest", "ability_inputs_digest", "source_facts_digest"})
_FIELDS = _DIGEST_FIELDS | frozenset({"schema_version", "campaign_slug", "character_slug", "actor_id",
    "action_id", "prior_generation", "prior_state_revision", "class_row", "mode", "cantrip_limit",
    "prepared_limit", "known_limit", "maximum_spell_level", "entries"})


def _fail(message="The current spell checkpoint needs complete, unambiguous retained roles."):
    raise SourceRepairError(message)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _book_membership_digest(raw):
    return _digest({key: value for key, value in raw.items()
                   if key not in {_STATE, "mark", "prepared", "is_prepared"}})


def _text(value):
    return type(value) is str and bool(value) and "\x00" not in value and value == value.strip() and len(value.encode("utf-8")) <= 512


def _sha(value):
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _ref(raw):
    from .character_spell_grants import publication_identity
    ref = raw.get("systems_ref")
    try:
        valid = type(ref) is dict and publication_identity(ref)["entry_type"] == "spell" and not raw.get("page_ref")
    except (TypeError, ValueError):
        valid = False
    if not valid:
        _fail()
    return deepcopy(ref)


def _marks(raw):
    from .character_builder_spells import _spell_mark_tokens
    fields = ("is_prepared", "prepared", "is_always_prepared", "always_prepared", "is_bonus_known",
              "base_is_always_prepared", "base_is_bonus_known", "is_ritual", "ritual")
    if (any(key in raw and type(raw[key]) is not bool for key in fields)
            or "mark" in raw and type(raw["mark"]) is not str):
        _fail()
    for aliases in (("is_prepared", "prepared"), ("is_always_prepared", "always_prepared"), ("is_ritual", "ritual")):
        if len({raw[key] for key in aliases if key in raw}) > 1:
            _fail()
    tokens = _spell_mark_tokens(raw.get("mark", ""))
    if tokens & {"p", "po"}:
        tokens = tokens | {"prepared"}
    prepared = raw.get("is_prepared", raw.get("prepared", "prepared" in tokens))
    if "prepared" in tokens and prepared is False:
        _fail()
    return tokens, prepared


def _rows(definition):
    spells = definition.spellcasting.get("spells")
    if type(spells) is not list or len(spells) > 256:
        _fail()
    rows = {}
    for raw in spells:
        if type(raw) is not dict or not _text(raw.get("id")) or raw["id"] in rows:
            _fail()
        _marks(raw)
        rows[raw["id"]] = raw
    return rows


def _class(definition):
    rows = definition.profile.get("classes")
    frame, origin = (definition.source.get(key) for key in ("native_reconstruction_choices", "native_reconstruction"))
    if (definition.system != "DND-5E" or definition.source.get("source_type") != "native_character_builder"
            or type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict
            or not _text(rows[0].get("row_id")) or type(rows[0].get("level")) is not int
            or not 1 <= rows[0]["level"] <= 20
            or type(frame) is not dict or type(frame.get("schema_version")) is not int or frame["schema_version"] != 1
            or type(frame.get("inputs")) is not dict or type(frame.get("choices")) is not dict
            or type(origin) is not dict or type(origin.get("schema_version")) is not int or origin["schema_version"] != 1
            or origin.get("campaign_slug") != definition.campaign_slug or origin.get("character_slug") != definition.character_slug
            or origin.get("input_digest") != _digest(frame["inputs"])):
        _fail("A current spell checkpoint requires the existing single-class native reconstruction foundation.")
    from .character_spell_grants import publication_identity
    if publication_identity(rows[0].get("systems_ref"))["entry_type"] != "class":
        _fail()
    return rows[0]


def _scope(definition):
    return {"spellcasting_digest": _digest(definition.spellcasting), "profile_digest": _digest(definition.profile),
            "ability_inputs_digest": _digest({key: deepcopy(definition.stats[key]) for key in ("ability_inputs",) if key in definition.stats})}


def legacy_class_spell_adoption_required(definition, class_row_id=None):
    """A retained reconstructed pool is readable, but not an ordinary editor.

    Canonical available-list observations need not have an active choice yet.
    Their existing model/custody checks, rather than a per-row flag, own that
    distinction. This predicate supplies no authority or migration exception.
    """
    from .character_spell_grants import has_native_grants
    if (not isinstance(definition.source.get("native_reconstruction_choices"), dict)
            or has_native_grants(definition)):
        return False
    rows = definition.spellcasting.get("spells", [])
    if type(rows) is not list:
        return True
    return any(isinstance(row, dict) and row.get("class_row_id")
               and not row.get("spell_source_row_id")
               and (class_row_id is None or row["class_row_id"] == class_row_id)
               for row in rows)


LEGACY_SPELL_ADOPTION_MESSAGE = (
    "Adopt current class spell ownership in Character Source Repair before "
    "changing these retained spell choices. Nothing was saved."
)


def _preparation_ids(prior, values):
    """Closed current-manager intent, never a historical acquisition claim."""
    from .character_spell_grants import has_native_grants
    _class(prior)
    if (has_native_grants(prior) or type(values) is not list or len(values) > 128
            or any(not _text(value) or len(value.encode("utf-8")) > 128 for value in values)
            or len(set(values)) != len(values)
            or any(_STATE in row for row in _rows(prior).values())):
        _fail("Current preparation adoption requires unique retained IDs and an unmigrated reconstructed pool.")
    return sorted(values)


def _with_preparation(raw, selected):
    tokens, _ = _marks(raw)
    if tokens - {"prepared", "p"}:
        _fail("Current preparation adoption cannot reinterpret another retained spell mark.")
    result = deepcopy(raw)
    if selected or "mark" in result:
        result["mark"] = "Prepared" if selected else ""
    for key in ("prepared", "is_prepared"):
        if key in result:
            result[key] = selected
    return result


def current_preparation_adoption_options(definition, systems_service):
    """Non-entitling GET choices; Review repeats complete source validation."""
    from .character_source_authority import (current_native_automatic_spell_origins,
        _reconstructed_spell_choice_eligibility, _source_derived_spell_choice_bases)
    from .character_builder_foundation import _spellcasting_mode_from_progression
    if not legacy_class_spell_adoption_required(definition):
        return ()
    try:
        _preparation_ids(definition, [])
        cls = _class(definition)
        automatic = current_native_automatic_spell_origins(definition, systems_service)
        probe = deepcopy(definition)
        probe.spellcasting["spells"] = [row for row in _rows(probe).values()
            if row.get("class_row_id") == cls["row_id"] and not row.get("spell_source_row_id")
            and row["id"] not in automatic]
        eligible = _reconstructed_spell_choice_eligibility(probe, {cls["row_id"]: cls},
            systems_service, enforce_capacity=False)
        bases = _source_derived_spell_choice_bases(probe, systems_service=systems_service,
            pages={}, verified_class_rows=frozenset({cls["row_id"]}), source_snapshot_digest=_digest(cls))
        options = []
        for raw in probe.spellcasting["spells"]:
            frame = eligible.get(raw["id"])
            if (frame is None or _spellcasting_mode_from_progression(frame["profile"]) != "prepared"
                    or f"spell_choice:{raw['id']}" not in bases):
                continue
            matches = [row for row in frame["selections"] if row["id"] == raw["id"]]
            if len(matches) != 1 or matches[0]["level"] <= 0:
                continue
            _with_preparation(raw, False)
            options.append({"id": raw["id"], "name": raw.get("name") or raw["id"],
                "level": matches[0]["level"], "source": _ref(raw)["source_id"]})
        return tuple(sorted(options, key=lambda row: (row["level"], row["name"].casefold(), row["id"])))
    except (SourceRepairError, TypeError, ValueError):
        return ()


def _check_checkpoint(checkpoint, candidate):
    """Historical structural validation; this does not issue audit authority."""
    explicit = type(checkpoint) is dict and checkpoint.get("schema_version") == 3
    if (type(checkpoint) is not dict or set(checkpoint) != _FIELDS | ({"prepared_selection"} if explicit else set())
            or type(checkpoint["schema_version"]) is not int or checkpoint["schema_version"] not in {1, 2, 3}
            or any(not _text(checkpoint[key]) for key in ("campaign_slug", "character_slug", "action_id"))
            or any(type(checkpoint[key]) is not int or checkpoint[key] < 1 for key in ("actor_id", "prior_generation"))
            or type(checkpoint["prior_state_revision"]) is not int or checkpoint["prior_state_revision"] < 0
            or any(not _sha(checkpoint[key]) for key in _DIGEST_FIELDS)
            or type(checkpoint["mode"]) is not str or checkpoint["mode"] not in {"prepared", "known", "wizard"}
            or (checkpoint["schema_version"] == 2) != (checkpoint["mode"] == "wizard")
            or explicit and checkpoint["mode"] != "prepared"
            or any(type(checkpoint[key]) is not int or checkpoint[key] < 0
                   for key in ("cantrip_limit", "prepared_limit", "known_limit", "maximum_spell_level"))
            or checkpoint["maximum_spell_level"] > 9
            or (checkpoint["campaign_slug"], checkpoint["character_slug"]) != (candidate.campaign_slug, candidate.character_slug)
            or type(checkpoint["class_row"]) is not dict or checkpoint["class_row"] != _class(candidate)
            or any(checkpoint[key] != value for key, value in _scope(candidate).items())):
        _fail("The saved current spell checkpoint is malformed or changed.")
    rows = _rows(candidate)
    from .character_spell_grants import validate_native_grant_model
    model = validate_native_grant_model(candidate)
    automatic = {edge["old_spell_id"] for edge in model["migration_edges"] if edge["grant_ids"]} & set(rows)
    entries = checkpoint["entries"]
    if type(entries) is not list or len(entries) != len(rows):
        _fail()
    seen, identities, selected = set(), set(), {role: 0 for role in _SELECTED}
    book_prepared = 0
    for entry in entries:
        if (type(entry) is not dict or set(entry) != _ENTRY_FIELDS or not _text(entry.get("spell_id"))
                or type(entry.get("role")) is not str or entry["role"] not in _ROLES
                or type(entry.get("spell_level")) is not int or not 0 <= entry["spell_level"] <= 9
                or not _sha(entry.get("prior_row_digest")) or not _sha(entry.get("row_digest"))
                or entry["spell_id"] in seen or entry["spell_id"] not in rows):
            _fail()
        raw, role, level = rows[entry["spell_id"]], entry["role"], entry["spell_level"]
        ref = _ref(raw)
        item = raw.get("spell_source_row_id")
        owner = raw.get("class_row_id")
        if ((owner not in (None, "", checkpoint["class_row"]["row_id"]))
                or item is not None and type(item) is not str
                or (role == "item") != bool(item)
                or role != "item" and owner != checkpoint["class_row"]["row_id"]
                or role == "item" and (not _text(item) or raw.get("spell_source_row_kind") != "item")
                or ref != entry["spell_ref"] or _digest(raw) != entry["row_digest"]):
            _fail()
        identity = (owner, item or "", ref["entry_key"], ref["source_id"])
        if identity in identities:
            _fail("A retained spell publication has duplicate ownership.")
        tokens, prepared = _marks(raw)
        from .character_spell_grants import native_class_choice_state
        state = native_class_choice_state(raw)
        if ((role == "automatic") != (entry["spell_id"] in automatic)
                or role in _SELECTED and state != "active" or role not in _SELECTED and state is not None
                or role == "cantrip" and level != 0
                or role in {"prepared", "available", "known", "book"} and level == 0
                or role == "book" and (checkpoint["mode"] != "wizard" or not tokens & {"spellbook", "o", "po"})
                or checkpoint["mode"] == "wizard" and role in {"prepared", "available", "known"}
                or checkpoint["mode"] == "known" and role in {"prepared", "available"}
                or checkpoint["mode"] == "prepared" and role == "known"
                or role == "known" and (prepared or "known" not in tokens)
                or role != "item" and level > checkpoint["maximum_spell_level"]
                or role == "prepared" and not prepared or role == "available" and prepared
                or "level" in raw and (type(raw["level"]) is not int or raw["level"] != level)
                or role in {"cantrip", "prepared", "known", "available", "book"} and (
                    "granted" in tokens or any(raw.get(key) is True for key in ("is_always_prepared", "always_prepared", "is_bonus_known")))
                or "cantrip" in tokens and level != 0):
            _fail()
        if role in _SELECTED:
            selected[role] += 1
        if role == "book" and prepared:
            book_prepared += 1
        seen.add(entry["spell_id"])
        identities.add(identity)
    if ([entry["spell_id"] for entry in entries] != sorted(seen) or seen != set(rows)
            or selected["cantrip"] > checkpoint["cantrip_limit"] or selected["prepared"] > checkpoint["prepared_limit"]
            or selected["known"] > checkpoint["known_limit"]):
        _fail("The current ordinary spell selections exceed their complete source limits.")
    if book_prepared > checkpoint["prepared_limit"]:
        _fail("The current spellbook preparations exceed their complete source limit.")
    if explicit:
        selection = checkpoint["prepared_selection"]
        ids = [entry["spell_id"] for entry in entries if entry["role"] == "prepared"]
        if (type(selection) is not dict or set(selection) != {"class_row_id", "spell_ids"}
                or selection["class_row_id"] != checkpoint["class_row"]["row_id"]
                or type(selection["spell_ids"]) is not list or selection["spell_ids"] != sorted(ids)
                or any(not _text(value) or len(value.encode("utf-8")) > 128 for value in ids)
                or len(ids) > 128):
            _fail("The explicit current prepared set differs from its complete checkpoint.")
    return rows


def checkpoint_choice_ids(checkpoint, candidate):
    """Selected identities from a complete validated frame, never audit custody."""
    _check_checkpoint(checkpoint, candidate)
    return frozenset(entry["spell_id"] for entry in checkpoint["entries"] if entry["role"] in _SELECTED)


def validate_saved_spell_checkpoint(prior, candidate, checkpoint):
    """Validate exact history only after the caller authenticates its audit pair.

    The outer native proof separately proves removed IDs and the grant model.
    Retained rows can only acquire selected `active` metadata, never a birth.
    """
    rows = _check_checkpoint(checkpoint, candidate)
    old = _rows(prior)
    explicit = checkpoint["schema_version"] == 3
    if explicit:
        selected = _preparation_ids(prior, checkpoint["prepared_selection"]["spell_ids"])
    if (checkpoint["prior_definition_digest"] != _digest(prior.to_dict())
            or any(checkpoint["prior_" + key] != value for key, value in _scope(prior).items())
            or _class(prior) != checkpoint["class_row"]
            or any(prior.source.get(key) != candidate.source.get(key)
                   for key in ("native_reconstruction", "native_reconstruction_choices"))
            or not set(rows) <= set(old)
            or [row["id"] for row in candidate.spellcasting["spells"]]
               != [row["id"] for row in prior.spellcasting["spells"] if row["id"] in rows]):
        _fail("The current spell checkpoint changed its authenticated original frame.")
    for entry in checkpoint["entries"]:
        before = old[entry["spell_id"]]
        expected = deepcopy(before)
        if explicit and entry["role"] in {"prepared", "available"}:
            expected = _with_preparation(before, entry["spell_id"] in selected)
        if entry["role"] in _SELECTED:
            if _STATE in before and before[_STATE] != "active":
                _fail("An actual retired spell decision cannot become a current confirmation.")
            expected[_STATE] = "active"
        if entry["prior_row_digest"] != _digest(before) or _digest(expected) != _digest(rows[entry["spell_id"]]):
            _fail("A retained spell changed beyond its selected current-state confirmation.")
    return True


def superseded_preparation_authorizations(prior, candidate, checkpoint):
    """Derive obsolete current markers, never authenticate an audit or a grant.

    Producers/readers must additionally prove each returned marker from their
    independently verified earlier numeric witnesses. Pending transitions use
    only the genuine issuer-bound, freshly regenerated complete native result.
    """
    if checkpoint is None or checkpoint.get("schema_version") != 3:
        return ()
    validate_saved_spell_checkpoint(prior, candidate, checkpoint)
    before, after = _rows(prior), _rows(candidate)
    changed = {entry["spell_id"] for entry in checkpoint["entries"]
               if entry["role"] == "available"
               and _marks(before[entry["spell_id"]])[1] is True
               and before[entry["spell_id"]] != after[entry["spell_id"]]}
    if not changed:
        return ()
    from .character_source_repair import _valid_numeric_witness_marker
    markers = prior.source.get("source_authorizations", [])
    if type(markers) is not list or any(type(marker) is not dict for marker in markers):
        _fail("The superseded preparation witnesses are malformed.")
    retired = []
    for identity in sorted(changed):
        matching = [marker for marker in markers if (
            marker.get("target_kind"), marker.get("target_id"), marker.get("metric"))
            == ("spell_choice", f"spell_choice:{identity}", "selection")]
        if not matching:
            continue
        if len(matching) != 1:
            _fail("A superseded preparation has conflicting witnesses.")
        marker = matching[0]
        provenance = marker.get("provenance")
        if (provenance not in {"native_reconstruction", "native_requalification"}
                or not _valid_numeric_witness_marker(marker, prior.character_slug, provenance)
                or marker["value_digest"] != _digest(before[identity])):
            _fail("A superseded preparation needs its exact prior native witness.")
        retired.append(marker)
    return tuple(marker for marker in markers if marker in retired)


@dataclass(frozen=True, slots=True)
class PendingSpellCheckpoint:
    """Immutable issuer-bound prospective role facts, never durable witnesses."""
    checkpoint_json: str
    _issuer: Any = field(default=None, init=False, repr=False, compare=False)

    @property
    def checkpoint(self):
        return json.loads(self.checkpoint_json)

    def matches_definition(self, definition):
        try:
            if type(self) is not PendingSpellCheckpoint or self._issuer is not _ISSUER:
                return False
            checkpoint = self.checkpoint
            _check_checkpoint(checkpoint, definition)
            return _json(checkpoint) == self.checkpoint_json
        except (AttributeError, KeyError, TypeError, ValueError, SourceRepairError):
            return False

    def role_for(self, raw):
        if type(self) is not PendingSpellCheckpoint or self._issuer is not _ISSUER or type(raw) is not dict:
            return None
        try:
            for entry in self.checkpoint["entries"]:
                if entry["spell_id"] == raw.get("id") and entry["row_digest"] == _digest(raw):
                    return entry["role"]
        except (KeyError, TypeError, ValueError):
            return None
        return None

    def confirms_choice(self, raw):
        return self.role_for(raw) in _SELECTED


def prepare_current_spell_checkpoint(prior, candidate, systems_service, *, actor_id, action_id,
                                     prior_generation, prior_state_revision, automatic_ids,
                                     prepared_spell_ids=None):
    """Confirm current roles, optionally adopting an explicit preparation set.

    `automatic_ids` is the complete source-plan raw-ID set, never a client
    subset. Numeric capacity still needs the caller's qualified ability ledger.
    Without explicit preparations, the historical raw-mark contract is unchanged.
    """
    from .character_spell_grants import validate_native_grant_model
    from .character_source_authority import _reconstructed_spell_choice_eligibility, _source_derived_spell_choice_bases
    from .character_builder_foundation import _spellcasting_mode_from_progression
    if (type(actor_id) is not int or actor_id < 1 or not _text(action_id)
            or type(prior_generation) is not int or prior_generation < 1
            or type(prior_state_revision) is not int or prior_state_revision < 0
            or type(automatic_ids) not in (tuple, list, set, frozenset)
            or any(not _text(value) for value in automatic_ids) or len(set(automatic_ids)) != len(automatic_ids)):
        _fail()
    cls = _class(candidate)
    old, rows = _rows(prior), _rows(candidate)
    explicit_ids = _preparation_ids(prior, prepared_spell_ids) if prepared_spell_ids is not None else None
    for field_name, kind in (("systems_ref", "class"), ("subclass_ref", "subclass")):
        ref = cls.get(field_name)
        if field_name == "subclass_ref" and ref in (None, {}):
            continue
        entry = (systems_service.get_entry_for_campaign(candidate.campaign_slug, ref.get("entry_key"))
                 if type(ref) is dict else None)
        if (entry is None or entry.entry_type != kind or any(ref[key] != getattr(entry, key, None) for key in ref)):
            _fail("The current class and subclass must match their complete admitted source references.")
    automatic = frozenset(automatic_ids)
    model = validate_native_grant_model(candidate)
    mapped = {edge["old_spell_id"] for edge in model["migration_edges"] if edge["grant_ids"]}
    if automatic != mapped & set(rows) or not set(rows) <= set(old):
        _fail("Automatic roles require the complete source-derived migration mapping.")
    # Probe only ordinary observations. Migrated legacy aggregate flags are not
    # elective eligibility, and repeated issuance must compare the same input.
    def ordinary_probe(current):
        probe = deepcopy(current)
        probe.spellcasting["spells"] = [deepcopy(raw) for raw in _rows(current).values()
            if raw["id"] not in automatic and not raw.get("spell_source_row_id")]
        for raw in probe.spellcasting["spells"]:
            if _STATE not in old[raw["id"]] and raw.get(_STATE) == "active":
                raw.pop(_STATE)
        return probe
    probe = ordinary_probe(candidate)
    eligible = _reconstructed_spell_choice_eligibility(probe, {cls["row_id"]: cls}, systems_service,
        enforce_capacity=False, current_wizard_preparation=True)
    ordinary_ids = {raw["id"] for raw in probe.spellcasting["spells"]}
    if not ordinary_ids or set(eligible) != ordinary_ids:
        _fail("Every ordinary retained spell needs exact current class/source/level eligibility.")
    frame = eligible[next(iter(sorted(ordinary_ids)))]
    if any(_digest(value) != _digest(frame) for value in eligible.values()):
        _fail()
    mode = _spellcasting_mode_from_progression(frame["profile"])
    if mode not in {"prepared", "known", "wizard"}:
        _fail("The current class has no supported spell checkpoint mode.")
    if explicit_ids is not None:
        if mode != "prepared":
            _fail("Explicit preparation adoption supports prepared classes only.")
        leveled = {row["id"] for row in frame["selections"] if row["level"] > 0}
        if not set(explicit_ids) <= leveled:
            _fail("Choose only retained ordinary leveled spells of the current class.")
        candidate = deepcopy(candidate)
        for index, raw in enumerate(candidate.spellcasting["spells"]):
            if raw["id"] in leveled:
                candidate.spellcasting["spells"][index] = _with_preparation(raw, raw["id"] in explicit_ids)
        rows = _rows(candidate)
        probe = ordinary_probe(candidate)
        eligible = _reconstructed_spell_choice_eligibility(probe, {cls["row_id"]: cls}, systems_service,
            enforce_capacity=False, current_wizard_preparation=True)
        if set(eligible) != ordinary_ids:
            _fail("Current preparation adoption changed its source-eligible observation inventory.")
        frame = eligible[next(iter(sorted(ordinary_ids)))]
        if (any(_digest(value) != _digest(frame) for value in eligible.values())
                or _spellcasting_mode_from_progression(frame["profile"]) != "prepared"):
            _fail()
    limits = {key: frame[key] for key in ("cantrip_limit", "prepared_limit", "known_limit", "maximum_spell_level")}
    if any(type(value) is not int or value < 0 for value in limits.values()):
        _fail("The current cantrip, preparation and known limits must be complete.")
    bases = _source_derived_spell_choice_bases(probe, systems_service=systems_service, pages={},
        verified_class_rows=frozenset({cls["row_id"]}), source_snapshot_digest=_digest(frame))
    if set(bases) != {f"spell_choice:{value}" for value in ordinary_ids}:
        _fail("Every ordinary observation must belong to the exact current class spell list.")
    proposed, entries = deepcopy(candidate), []
    proposed_rows = _rows(proposed)
    for spell_id in sorted(rows):
        raw = proposed_rows[spell_id]
        ref = _ref(raw)
        entry = systems_service.get_entry_for_campaign(candidate.campaign_slug, ref["entry_key"])
        if (entry is None or entry.entry_type != "spell" or any(ref[key] != getattr(entry, key, None) for key in ref)
                or type(entry.metadata.get("level")) is not int or not 0 <= entry.metadata["level"] <= 9):
            _fail("A retained spell needs its exact admitted source publication and level.")
        level = entry.metadata["level"]
        tokens, prepared = _marks(raw)
        role = ("item" if raw.get("spell_source_row_id") else "automatic" if spell_id in automatic
                else "cantrip" if level == 0 else "book" if mode == "wizard" else "known" if mode == "known"
                else "prepared" if prepared else "available")
        if role == "known" and (prepared or "known" not in tokens):
            _fail("A current known spell requires its exact retained Known mark without preparation.")
        if role in _SELECTED:
            if _STATE in raw and raw[_STATE] != "active":
                _fail("A retired spell decision conflicts with the current selected set.")
            raw[_STATE] = "active"
        entries.append({"spell_id": spell_id, "role": role, "spell_level": level,
            "prior_row_digest": _digest(old[spell_id]), "row_digest": _digest(raw), "spell_ref": ref})
    checkpoint = {"schema_version": 2 if mode == "wizard" else 1, "campaign_slug": prior.campaign_slug, "character_slug": prior.character_slug,
        "actor_id": actor_id, "action_id": action_id, "prior_generation": prior_generation,
        "prior_state_revision": prior_state_revision, "prior_definition_digest": _digest(prior.to_dict()),
        **{"prior_" + key: value for key, value in _scope(prior).items()}, **_scope(proposed),
        "class_row": deepcopy(cls), "mode": mode, **limits,
        "source_facts_digest": _digest({"eligibility": frame, "list_bases": bases}), "entries": entries}
    if explicit_ids is not None:
        checkpoint.update(schema_version=3,
            prepared_selection={"class_row_id": cls["row_id"], "spell_ids": explicit_ids})
    validate_saved_spell_checkpoint(prior, proposed, checkpoint)
    pending = PendingSpellCheckpoint(_json(checkpoint))
    object.__setattr__(pending, "_issuer", _ISSUER)
    return proposed, deepcopy(checkpoint), pending


class NativeSpellReconstructionFact(dict):
    """Exact durable role evidence, issued only after the saved audit joins.

    This wrapper never supplies an acquisition date or numeric authorization.
    """
    def __init__(self, *, role, spell_level, target_id, row_digest, origin, membership_digest=None):
        if (type(role) is not str or role not in _ROLES or type(spell_level) is not int or not 0 <= spell_level <= 9
                or type(target_id) is not str or not target_id.startswith("spell_choice:")
                or not _text(target_id.removeprefix("spell_choice:")) or not _sha(row_digest)
                or type(origin) is not tuple or len(origin) != 5
                or any(not _text(value) for value in origin[:2])
                or any(type(value) is not int or value < 1 for value in origin[2:])
                or (not _sha(membership_digest) if role == "book" else membership_digest is not None)):
            _fail("A durable spell role requires the actual confirmed audit origin.")
        super().__init__(role=role, spell_level=spell_level, target_id=target_id, row_digest=row_digest)
        if role == "book":
            self["membership_digest"] = membership_digest
        self.origin = origin

    def _matches_shape(self, raw):
        try:
            expected = {"role", "spell_level", "target_id", "row_digest"}
            if self.get("role") == "book":
                expected.add("membership_digest")
            return (type(self) is NativeSpellReconstructionFact and set(self) == expected
                and set(vars(self)) == {"origin"} and type(raw) is dict and _text(raw.get("id"))
                and type(self.get("role")) is str and self["role"] in _ROLES
                and type(self.get("spell_level")) is int and 0 <= self["spell_level"] <= 9
                and self.get("target_id") == f"spell_choice:{raw.get('id')}"
                and _sha(self.get("row_digest"))
                and (self.get("role") != "book" or _sha(self.get("membership_digest")))
                and type(self.origin) is tuple and len(self.origin) == 5
                and all(_text(value) for value in self.origin[:2])
                and all(type(value) is int and value > 0 for value in self.origin[2:]))
        except (TypeError, ValueError):
            return False

    def matches(self, raw):
        return (self._matches_shape(raw) and self.get("row_digest") == _digest(raw)
                and (self.get("role") != "book" or self.get("membership_digest") == _book_membership_digest(raw)))

    def matches_membership(self, raw):
        """Select the book basis recipe, never confirm a changed current choice.

        The reader issued this book fact after the real audit joins. Preparation
        aliases/mark and active/retired state have their own independent proofs.
        Every other publication/owner/observation field must still match.
        """
        if type(self) is not NativeSpellReconstructionFact or self.get("role") != "book" or type(raw) is not dict:
            return False
        return self._matches_shape(raw) and self.get("membership_digest") == _book_membership_digest(raw)


def reconstruction_facts(checkpoint, candidate, *, origin):
    """Materialize roles only in the reader that completed all saved proof joins."""
    rows = _check_checkpoint(checkpoint, candidate)
    if (type(origin) is not tuple or len(origin) != 5
            or origin[:2] != (candidate.campaign_slug, candidate.character_slug)
            or origin[3] != checkpoint["actor_id"] or type(origin[3]) is not int
            or type(origin[4]) is not int or origin[4] != checkpoint["prior_generation"] + 1):
        _fail("The durable current spell checkpoint changed its audit actor or generation.")
    return tuple(NativeSpellReconstructionFact(role=entry["role"], spell_level=entry["spell_level"],
        target_id=f"spell_choice:{entry['spell_id']}",
        row_digest=entry["row_digest"], origin=origin,
        membership_digest=_book_membership_digest(rows[entry["spell_id"]]) if entry["role"] == "book" else None)
        for entry in checkpoint["entries"])


def carry_preparation_role(before, after, spell_id, prior_witnesses, *, origin):
    """Transport historical list/book role only after the real event joins.

    The caller authenticates the complete selected/leveled audit and decisions.
    A changed preparation must not erase a prior prepared-class classification
    merely because its row digest changes. No fact is inferred without an exact
    previously admitted typed fact, and no current source entitlement is issued.
    """
    old = next((row for row in before.spellcasting.get("spells", [])
        if type(row) is dict and row.get("id") == spell_id), None)
    new = next((row for row in after.spellcasting.get("spells", [])
        if type(row) is dict and row.get("id") == spell_id), None)
    candidates = [fact for fact in prior_witnesses if type(fact) is NativeSpellReconstructionFact
        and fact.matches(old) and fact.origin[:2] == (before.campaign_slug, before.character_slug)]
    if not candidates:
        return None
    latest = max((fact.origin[4], fact.origin[2]) for fact in candidates)
    facts = [fact for fact in candidates if (fact.origin[4], fact.origin[2]) == latest]
    roles = {(fact["role"], fact["spell_level"]) for fact in facts}
    if len(roles) != 1:
        _fail("The prior reconstructed spell role is ambiguous.")
    role, level = roles.pop()
    if role not in {"available", "prepared", "book"}:
        return None
    owner = old.get("class_row_id")
    classes = [[row for row in model.profile.get("classes", [])
        if type(row) is dict and row.get("row_id") == owner] for model in (before, after)]
    changed = {key for key in set(old or {}) | set(new or {})
        if (key in (old or {})) != (key in (new or {})) or (old or {}).get(key) != (new or {}).get(key)}
    if (type(new) is not dict or level <= 0 or new.get("class_row_id") != owner
            or new.get(_STATE) not in ({"active", "retired"} if role == "book" else {"active"})
            or new.get("spell_source_row_id")
            or not changed <= {_STATE, "mark", "prepared", "is_prepared"}
            or any(len(rows) != 1 for rows in classes)
            or any(classes[0][0].get(key) != classes[1][0].get(key) for key in ("systems_ref", "subclass_ref"))):
        _fail("A preparation cannot rewrite the confirmed class-list observation.")
    _marks(old)
    _, prepared = _marks(new)
    return NativeSpellReconstructionFact(role="book" if role == "book" else "prepared" if prepared else "available", spell_level=level,
        target_id="spell_choice:" + spell_id, row_digest=_digest(new), origin=origin,
        membership_digest=_book_membership_digest(new) if role == "book" else None)
