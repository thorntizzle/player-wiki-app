"""One invocation's staged current inputs; never a persisted authority/cache.

Only the ordinary owned read path may share these results. Historical custody,
current source checks and the phase's complete closing proof remain external.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct

from .character_source_reads import SourceReadConflict


_MAX_NODES = 32768
_MAX_BYTES = 16 * 1024 * 1024


class _InputUnavailable(Exception):
    pass


class _InputBudget:
    """Count expanded occurrences before copying or encoding plain inputs.

    Depth-first iteration has no fanout-sized pending queue. Aliases count on
    every occurrence; an active ancestor is a cycle. The UTF8/JSON charge is a
    conservative upper bound, computed without encoding untrusted strings.
    """

    def __init__(self):
        self.nodes = self.bytes = 0
        self.active = set()

    def take(self, *, nodes=0, size=0):
        if nodes > _MAX_NODES - self.nodes or size > _MAX_BYTES - self.bytes:
            raise _InputUnavailable()
        self.nodes += nodes
        self.bytes += size

    def add(self, item, depth=0, *, container_mode=0):
        self.take(nodes=1)
        if depth > 64:
            raise _InputUnavailable()
        kind = type(item)
        if item is None:
            self.take(size=4)
        elif kind is str:
            self.take(size=6 * len(item) + 2)
        elif kind is bool:
            self.take(size=5)
        elif kind is int:
            bits = int.bit_length(item)
            if bits > 4096:
                raise _InputUnavailable()
            self.take(size=bits // 3 + 3)
        elif kind is float:
            if container_mode and not math.isfinite(item):
                raise _InputUnavailable()
            self.take(size=32)
        elif kind is dict:
            if container_mode == 2:
                raise _InputUnavailable()
            self._container(item, depth, mapping=True, container_mode=container_mode)
        elif kind is list or kind is tuple:
            if container_mode == 1 and kind is tuple or container_mode == 2 and kind is list:
                raise _InputUnavailable()
            self._container(item, depth, mapping=False, container_mode=container_mode)
        else:
            raise _InputUnavailable()

    def mapping(self, item):
        # Only an exactly admitted stock witness subclass reaches this method.
        self.take(nodes=1)
        self._container(item, 1, mapping=True, container_mode=1)

    def _container(self, item, depth, *, mapping, container_mode=0):
        identity = id(item)
        if identity in self.active:
            raise _InputUnavailable()
        count = dict.__len__(item) if mapping else len(item)
        if count * (2 if mapping else 1) > _MAX_NODES - self.nodes:
            raise _InputUnavailable()  # Before iteration or child allocation.
        self.take(size=2 + max(0, count - 1) + (count if mapping else 0))
        self.active.add(identity)
        try:
            if mapping:
                for key, value in dict.items(item):
                    if type(key) is not str:
                        raise _InputUnavailable()
                    self.add(key, depth + 1, container_mode=container_mode)
                    self.add(value, depth + 1, container_mode=container_mode)
            else:
                for value in item:
                    self.add(value, depth + 1, container_mode=container_mode)
        finally:
            self.active.remove(identity)


def _witness_kinds():
    """Closed exact kinds with fixed private tags, never class-name dispatch."""
    from .character_source_repair import NativeAggregateWitness, NativeSpellChoiceDecision
    from .character_spell_grants import NativeGrantCustody
    from .character_spell_reconstruction import NativeSpellReconstructionFact
    from .character_language_electives import NativeElectiveDecision, PendingElectiveOutcome
    from .character_external_proficiencies import ExternalProficiencyCustody, PendingExternalProficiency
    return ((dict, "plain-dict"), (NativeAggregateWitness, "native-aggregate"),
            (NativeSpellChoiceDecision, "native-spell-choice"),
            (NativeGrantCustody, "native-grant-custody"),
            (NativeSpellReconstructionFact, "native-spell-reconstruction"),
            (NativeElectiveDecision, "native-elective"),
            (PendingElectiveOutcome, "pending-elective"),
            (ExternalProficiencyCustody, "external-proficiency-custody"),
            (PendingExternalProficiency, "pending-external-proficiency"))


def _admit_witness_inputs(rows, budget, kinds):
    if type(rows) is not tuple or len(rows) > (_MAX_NODES - budget.nodes) // 7:
        raise _InputUnavailable()
    budget.take(nodes=1, size=128)  # Vector label/count and binary framing.
    for row in rows:
        if not any(type(row) is kind for kind, _tag in kinds):
            raise _InputUnavailable()
        # Private frame: root, three keys, type tag, and plain-dict origin None.
        # Payload/origin contents are admitted under the SAME aggregate budget.
        budget.take(nodes=6, size=264)
        budget.mapping(row)
        if type(row) is not dict:
            attributes = vars(row)
            if type(attributes) is not dict or len(attributes) != 1:
                raise _InputUnavailable()
            for key, origin in dict.items(attributes):
                if type(key) is not str or key != "origin":
                    raise _InputUnavailable()
                # Stock origins are tuples of scalar/tuple data; payloads are
                # JSON containers. Keep their types unambiguous under JSON,
                # declining other shapes before entry instead of coercing them.
                if type(origin) is not tuple:
                    raise _InputUnavailable()
                budget.add(origin, 1, container_mode=2)


def _witness_frame(row, kinds):
    """Materialize only after the complete aggregate passed admission.

    Public authority identity has its own serializer. This private binding also
    includes raw origins for kinds that the public serializer treats as maps.
    """
    for kind, tag in kinds:
        if type(row) is kind:
            return {"type": tag, "payload": {key: value for key, value in dict.items(row)},
                    "origin": None if kind is dict else vars(row)["origin"]}
    raise _InputUnavailable()


def _ordinary_recipes():
    from . import character_builder as builder
    from . import character_reconstruction_authority as reconstruction
    from . import character_reconstruction_proficiencies as proficiencies
    from . import character_reconstruction_instruments as instruments
    from . import character_ability_inputs as abilities, character_profile as profile
    from . import character_source_authority as authority, character_builder_equipment as equipment
    from . import character_read_foundation as foundation, character_feature_proficiency_grants as grants
    from . import character_skill_adoptions as skills, character_language_electives as languages
    from .character_read_catalogs import _ordinary_copy_policy, _ordinary_provider_policy
    return (_ordinary_copy_policy() and _ordinary_provider_policy()
        and all(all(vars(module).get(name) is original for name, original in
                    module._CURRENT_INPUT_RECIPE)
                for module in (builder, reconstruction, proficiencies, instruments, abilities,
                               profile, authority, equipment, foundation, grants, skills, languages)))


def _actor():
    from flask import g, has_request_context, request
    if not has_request_context():
        return None
    source = getattr(g, "current_auth_source", None)
    if type(source) is not str:
        return None
    return (request._get_current_object(), getattr(g, "current_user", None),
            getattr(g, "authenticated_user", None), getattr(g, "current_session_record", None),
            getattr(g, "current_api_token_record", None), source)


def current_input_compilation(*, definition, state, state_revision, statuses,
                              manual_actions, numeric_actions, source_snapshot_digest,
                              systems_service, prospective_checkpoint):
    """Decline custom/nonread contexts before any optimized qualifier enters."""
    from .character_models import CharacterDefinition
    from .character_source_authority import _NATIVE_CHARACTER_TO_DICT
    from .character_source_reads import SourceReadPhase
    from .systems_service import ordinary_current_input_service
    if (type(definition) is not CharacterDefinition or type(state) is not dict
            or CharacterDefinition.to_dict is not _NATIVE_CHARACTER_TO_DICT
            or not ordinary_current_input_service(systems_service)
            or prospective_checkpoint is not None):
        return None
    if type(definition.source) is not dict:
        return None
    frame = definition.source.get("native_reconstruction_choices")
    if (type(frame) is not dict or type(frame.get("schema_version")) is not int or frame["schema_version"] != 1
            or type(frame.get("ability_layers")) is not dict):
        return None
    phase = systems_service.source_read_phase
    if (type(phase) is not SourceReadPhase or phase.owner._reserved or type(phase.purpose) is not str
            or phase.purpose not in {"assignment-read", "character-shell-read", "character-section-read", "selected-character-read"}
            or not _ordinary_recipes()
            or _actor() is None):
        return None
    if (not (type(statuses) is list or type(statuses) is tuple)
            or len(statuses) > _MAX_NODES // 5):
        return None
    phase.require_open()
    try:
        result = CurrentInputCompilation(definition, state, state_revision, tuple(statuses),
            manual_actions, numeric_actions, source_snapshot_digest, systems_service, phase)
    except (TypeError, ValueError, RecursionError):
        return None  # Unsupported representations have not entered qualification.
    return result if result._basis is not None else None


class CurrentInputCompilation:
    """Private primitive Con and detached validation facts, scoped to one call."""

    def __init__(self, definition, state, state_revision, statuses, manual, numeric,
                 source_snapshot_digest, service, phase):
        self.definition, self.state, self.revision = definition, state, state_revision
        self.statuses, self.manual, self.numeric = statuses, manual, numeric
        self.source_snapshot_digest, self.service, self.phase = source_snapshot_digest, service, phase
        self._phase_basis, self._actor = phase._basis, _actor()
        self._validation = None
        self._con = None
        self._completed = False
        # A language-outcome frame retains the distinct legacy HP tail; its
        # catalog/no-catalog slot vectors have not been proved equivalent.
        self._basis = self._fingerprint()
        self.reuse_hp = (self._basis is not None and
            not definition.source["native_reconstruction_choices"].get("language_elective_outcomes"))

    def _fingerprint(self):
        from .character_source_authority import AuthorityStatus
        # These are invocation bindings, not accepted witness verdicts. The full
        # verifier and ordered witness serialization still run in every phase.
        try:
            budget = _InputBudget()
            kinds = _witness_kinds()
            # Fixed root keys, version and framing are charged before creating
            # their small wrapper. All variable payloads share this budget.
            budget.take(nodes=6, size=384)
            definition = self.definition.to_dict()
            for value in (definition, self.state, self.revision, self.source_snapshot_digest):
                budget.add(value, 1)
            if type(self.statuses) is not tuple or len(self.statuses) > (_MAX_NODES - budget.nodes) // 5:
                raise _InputUnavailable()
            budget.take(nodes=1, size=2 + max(0, len(self.statuses) - 1))
            status_values = []
            for row in self.statuses:
                if type(row) is not AuthorityStatus:
                    raise _InputUnavailable()
                value = (row.kind, row.instance_id, row.status, row.reason)
                budget.add(value, 2)
                status_values.append(value)
            for rows in (self.manual, self.numeric):
                _admit_witness_inputs(rows, budget, kinds)
        except _InputUnavailable:
            return None  # No witness conversion, copy or encoding has run.

        value = {"definition": definition, "state": self.state, "revision": self.revision,
                 "source": self.source_snapshot_digest, "statuses": status_values}
        result = hashlib.sha256()

        def frame(raw):
            result.update(struct.pack(">Q", len(raw)))
            result.update(raw)

        frame(b"current-inputs-v3")
        frame(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        for label, rows in ((b"manual", self.manual), (b"numeric", self.numeric)):
            frame(label)
            frame(str(len(rows)).encode("ascii"))
            for row in rows:
                # Private exact type/payload/origin; the public identity and
                # its ordered witness serialization are untouched.
                frame(json.dumps(_witness_frame(row, kinds), sort_keys=True,
                    separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        return result.digest()

    def check(self, definition, service, statuses=None):
        from .systems_service import ordinary_current_input_service
        from .character_models import CharacterDefinition
        from .character_source_authority import _NATIVE_CHARACTER_TO_DICT
        self.phase.require_open()
        actor = _actor()
        if (definition is not self.definition or service is not self.service
                or CharacterDefinition.to_dict is not _NATIVE_CHARACTER_TO_DICT
                or self.phase._basis is not self._phase_basis
                or actor is None or len(actor) != len(self._actor)
                or any(actual is not prior for actual, prior in zip(actor[:-1], self._actor[:-1]))
                or actor[-1] != self._actor[-1]
                or not ordinary_current_input_service(self.service) or not _ordinary_recipes()
                or statuses is not None and tuple(statuses) != self.statuses):
            self.phase.owner._failed = True
            raise SourceReadConflict("Current-input compilation no longer matches this invocation.")
        try:
            fingerprint = self._fingerprint()
        except (TypeError, ValueError, RecursionError) as exc:
            self.phase.owner._failed = True
            raise SourceReadConflict("Current inputs changed representation during qualification.") from exc
        if fingerprint != self._basis:
            self.phase.owner._failed = True
            raise SourceReadConflict("Current inputs changed during qualification.")

    def validated(self, optional_basis, instrument_basis):
        from .character_read_catalogs import AuxiliaryFacts, _AuxiliaryUnavailable
        self.check(self.definition, self.service)
        value = {"optional": optional_basis, "instrument": instrument_basis}
        try:
            _InputBudget().add(value)
            facts = AuxiliaryFacts(value)
        except (_InputUnavailable, _AuxiliaryUnavailable):
            return  # Original post-validation consumers still run once.
        self._validation = facts

    def validation(self, definition, service):
        self.check(definition, service)
        if self._validation is None:
            return None
        # Separate adapters preserve consumer ownership; no public graph shares
        # a mutable validation result or a SystemsEntryRecord proxy.
        return (self._validation.field("optional", {}),
                self._validation.field("instrument", {}))

    def complete(self, definition, service, ability_con):
        self.check(definition, service)
        if ability_con is not None and (type(ability_con) is not str or len(ability_con) != 64):
            return
        self._con, self._completed = ability_con, True

    def constitution(self, definition, service, statuses):
        self.check(definition, service, statuses)
        if not self._completed:
            raise SourceReadConflict("Current reconstruction inputs did not complete.")
        return self._con
