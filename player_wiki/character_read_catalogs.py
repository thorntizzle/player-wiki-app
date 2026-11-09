"""Closed, phase-owned item/spell inputs with explicit selected hydration.

Immutable source observations and indices are separate from operation-owned
ordinary selections. Neither object is a Mapping or a public catalog facade.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
import copy
import copyreg
from datetime import date, datetime, time, timedelta, timezone
from types import MappingProxyType, ModuleType

from .character_source_reads import SourceReadConflict, thaw
from .campaign_page_store import CampaignPageRecord
from .models import Page
from .systems_models import SystemsEntryRecord


_ABSENT = object()
_COPY_FAMILY = (type(None), str, bytes, bool, int, float, type, dict, list, tuple,
                date, datetime, time, timedelta, timezone, SystemsEntryRecord)
_COPY_HOOKS = ("__deepcopy__", "__reduce__", "__reduce_ex__", "__getstate__",
               "__setstate__", "__getnewargs__", "__getnewargs_ex__")
_COPY_FUNCTION = copy.deepcopy
_COPY_FUNCTION_CODE = copy.deepcopy.__code__
_COPY_DISPATCH = tuple((kind,
    copy._deepcopy_dict if kind is dict else
    copy._deepcopy_list if kind is list else
    copy._deepcopy_tuple if kind is tuple else
    copy._deepcopy_atomic if any(kind is atom for atom in (type(None), str, bytes, bool, int, float, type))
    else _ABSENT) for kind in _COPY_FAMILY)


def _ordinary_copy_policy():
    """Eligibility only; configured copy extensions keep ordinary catalogs.

    This binds the trusted startup's stock copy implementation for the closed
    record/plain/temporal family. It is not a replacement deepcopy algorithm or
    a claim to emulate arbitrarily modified Python internals.
    """
    from . import character_builder as builder
    if (copy.deepcopy is not _COPY_FUNCTION or builder.deepcopy is not _COPY_FUNCTION
            or copy.deepcopy.__code__ is not _COPY_FUNCTION_CODE
            or any(name in vars(SystemsEntryRecord) for name in _COPY_HOOKS)):
        return False
    dispatch = copy._deepcopy_dispatch
    if type(dispatch) is not dict:
        return False
    # Never hash or compare an unknown registry key in an eligibility probe.
    if any(type(kind) is not type for kind in dispatch):
        return False
    for kind, original in _COPY_DISPATCH:
        found = next((value for key, value in dispatch.items() if key is kind), _ABSENT)
        if found is not original:
            return False
    for registry in (copy.dispatch_table, copyreg.dispatch_table):
        if type(registry) is not dict or any(type(kind) is not type for kind in registry):
            return False
        if any(any(key is kind for kind in _COPY_FAMILY) for key in registry):
            return False
    return True


def _ordinary_provider_policy():
    """Finite actual legacy aliases that private construction bypasses.

    Unknown providers decline before source dispatch; this neither calls them
    as a probe nor substitutes a same-named callable from a different module.
    """
    from . import character_builder_catalogs as catalogs, character_builder_static_bundle as bundle
    from . import character_builder as builder, character_mechanics_projection as projection
    for module, recipe_name in (
        (catalogs, "_NATIVE_CATALOG_RECIPE"), (bundle, "_NATIVE_READ_BUNDLE_RECIPE"),
        (builder, "_NATIVE_READ_PREPARATION_RECIPE"), (projection, "_NATIVE_READ_CATALOG_RECIPE"),
    ):
        if type(module) is not ModuleType:
            return False
        namespace = vars(module)
        if type(namespace) is not dict or any(type(name) is not str for name in namespace):
            return False
        recipe = namespace.get(recipe_name)
        if (type(recipe) is not tuple or not recipe
                or any(type(row) is not tuple or len(row) != 2 or type(row[0]) is not str for row in recipe)):
            return False
        if any(name not in namespace or namespace[name] is not original
               for name, original in recipe):
            return False
    return True


_PAGE_RECIPES = {kind: (
    tuple((field, field.name, field.init) for field in fields(kind)),
    tuple((field.name, vars(kind).get(field.name, _ABSENT)) for field in fields(kind)),
    kind.__getattribute__, vars(kind).get("__getattr__", _ABSENT),
) for kind in (CampaignPageRecord, Page)}


class _AuxiliaryUnavailable(Exception):
    """Unsupported auxiliary data retains the already-produced legacy value."""


@dataclass(frozen=True, slots=True, init=False)
class AuxiliaryFacts:
    """Exact builtin-container types/aliases, without a custom copy protocol."""

    root: tuple
    nodes: tuple

    def __init__(self, value):
        nodes, seen, active = [], {}, set()
        visits = 0

        def capture(item, depth=0):
            nonlocal visits
            visits += 1
            if depth > 64 or visits > 32768:
                raise _AuxiliaryUnavailable()
            kind = type(item)
            if item is None or any(kind is allowed for allowed in (str, bool, int, float, datetime, date,
                                         time, timedelta, timezone)):
                if (kind is datetime or kind is time) and item.tzinfo is not None and item.tzinfo is not timezone.utc:
                    raise _AuxiliaryUnavailable()
                if kind is timezone and item is not timezone.utc:
                    raise _AuxiliaryUnavailable()
                return ("leaf", item)
            if not any(kind is allowed for allowed in (dict, list, tuple, MappingProxyType)):
                raise _AuxiliaryUnavailable()
            identity = id(item)
            if identity in active:
                raise _AuxiliaryUnavailable()  # Never invent cycle semantics.
            if identity in seen:
                return ("ref", seen[identity])
            position = len(nodes)
            seen[identity] = position
            active.add(identity)
            nodes.append(None)
            if kind is dict or kind is MappingProxyType:
                contents = tuple((capture(key, depth + 1), capture(child, depth + 1))
                                 for key, child in item.items())
            else:
                contents = tuple(capture(child, depth + 1) for child in item)
            nodes[position] = (kind, contents)
            active.remove(identity)
            return ("ref", position)

        object.__setattr__(self, "root", capture(value))
        object.__setattr__(self, "nodes", tuple(nodes))

    def value(self, reference, memo):
        if reference[0] == "leaf":
            return reference[1]  # Same immutable atom that deepcopy preserves.
        position = reference[1]
        if position in memo:
            return memo[position]
        kind, contents = self.nodes[position]
        if kind is dict or kind is MappingProxyType:
            result = {self.value(key, memo): self.value(value, memo) for key, value in contents}
            if kind is MappingProxyType:
                result = MappingProxyType(result)
        elif kind is list:
            result = [self.value(value, memo) for value in contents]
        else:
            result = tuple(self.value(value, memo) for value in contents)
        memo[position] = result
        return result

    def field(self, name, memo, default=None):
        kind, contents = self.nodes[self.root[1]]
        if kind is not dict:
            raise SourceReadConflict("Read catalog auxiliaries require a plain root mapping.")
        for key, value in contents:
            if key[0] == "leaf" and type(key[1]) is str and key[1] == name:
                return self.value(value, memo)
        return default


@dataclass(frozen=True, slots=True)
class CatalogFacts:
    """Complete ordered immutable observations and immutable integer indices."""

    kind: str
    records: tuple
    indices: MappingProxyType

    def field(self, position, name):
        for key, init, value in self.records[position][2]:
            if key == name:
                return thaw(value)
        raise AttributeError(name)


class _SelectedIndex:
    __slots__ = ("_input", "_name")

    def __init__(self, catalog, name):
        self._input, self._name = catalog, name

    def get(self, key, default=None):
        self._input.check()
        position = self._input._facts.indices[self._name].get(key)
        return (default if position is None else
                self._input.materialize(position, (self._name, key)))

    def __contains__(self, key):
        self._input.check()
        return key in self._input._facts.indices[self._name]

    def __getitem__(self, key):
        self._input.check()
        position = self._input._facts.indices[self._name][key]
        return self._input.materialize(position, (self._name, key))

    def __bool__(self):
        self._input.check()
        return bool(self._input._facts.indices[self._name])


class ReadCatalogInput:
    """Operation-owned adapter; it intentionally has no get/iter/copy API."""

    __slots__ = ("_phase", "_facts", "_auxiliary", "_base_records", "_base_aux",
                 "_selected", "_selected_aux", "_detached", "__weakref__")

    def __init__(self, phase, facts, auxiliary, *, base_records=None, base_aux=None,
                 detached=False):
        phase.require_open()
        self._phase, self._facts, self._auxiliary = phase, facts, auxiliary
        self._base_records = {} if base_records is None else base_records
        self._base_aux = {} if base_aux is None else base_aux
        self._selected, self._selected_aux = {}, {}
        self._detached = detached
        phase._read_catalog_inputs.add(self)

    def check(self):
        if self._phase is None:
            raise SourceReadConflict("Read catalog input has closed.")
        self._phase.require_open()

    def close(self):
        self._selected.clear()
        self._selected_aux.clear()
        self._base_records.clear()
        self._base_aux.clear()
        self._facts = self._auxiliary = self._phase = None

    def fork_for_foundation(self):
        self.check()
        if not _ordinary_copy_policy() or not _ordinary_provider_policy():
            raise SourceReadConflict("Read catalog provider/copy policy changed after source dispatch.")
        return ReadCatalogInput(self._phase, self._facts, self._auxiliary,
            base_records=self._base_records, base_aux=self._base_aux, detached=True)

    def rows(self):
        self.check()
        return range(len(self._facts.records))

    def field(self, position, name):
        self.check()
        return self._facts.field(position, name)

    def index(self, name):
        self.check()
        if name not in self._facts.indices:
            raise KeyError(name)
        return _SelectedIndex(self, name)

    def materialize(self, position, origin="entries"):
        self.check()
        if position not in self._base_records:
            self._base_records[position] = thaw(self._facts.records[position])
        if not self._detached:
            return self._base_records[position]
        key = (origin, position)
        if key not in self._selected:
            # The public preparation recipe deepcopies each record occurrence
            # independently. Preserve that recipe only for selected occurrences.
            from .character_builder import _deep_detach_native_derivation_value
            self._selected[key] = _deep_detach_native_derivation_value(self._base_records[position])
        return self._selected[key]

    def aux(self, name, default=None):
        self.check()
        value = self._auxiliary.field(name, self._base_aux, _ABSENT)
        if value is _ABSENT:
            return default
        if not self._detached:
            return value
        if name not in self._selected_aux:
            from .character_builder import _deep_detach_native_derivation_value
            self._selected_aux[name] = _deep_detach_native_derivation_value(value)
        return self._selected_aux[name]


def _ordinary_page_input(record):
    if type(record) is not CampaignPageRecord:
        return False
    for kind, (recipe, bindings, attribute_read, fallback_read) in _PAGE_RECIPES.items():
        current = fields(kind)
        if (kind.__getattribute__ is not attribute_read
                or vars(kind).get("__getattr__", _ABSENT) is not fallback_read
                or len(current) != len(recipe)
                or any(actual is not original or actual.name is not name or actual.init is not init
                       for actual, (original, name, init) in zip(current, recipe))
                or any((name in vars(kind) if value is _ABSENT else
                        name not in vars(kind) or vars(kind)[name] is not value)
                       for name, value in bindings)):
            return False
    try:
        if type(record.page) is not Page:
            return False
        plain = tuple(getattr(record, field.name) for field in fields(CampaignPageRecord)
                      if field.name != "page") + tuple(
            getattr(record.page, field.name) for field in fields(Page)
            if field.name not in {"body_html", "html_loaded", "resolved_links", "backlinks"})
        AuxiliaryFacts(plain)  # Exact builtin data only; no unknown value probes.
    except (AttributeError, _AuxiliaryUnavailable):
        return False
    return True


def read_catalog_source(service, campaign_slug, page_records=None):
    """Positive default read capability; no optional __getattr__ probes."""
    from .character_source_reads import (BuilderPhaseReader, _NATIVE_BUILDER_READ_RECIPE,
        _NATIVE_BUILDER_READ_CLASS, _NATIVE_BUILDER_READ_MISSING, _NATIVE_BUILDER_READ_BASES)
    from .systems_service import PhaseCharacterReadSystemsService
    if BuilderPhaseReader is not _NATIVE_BUILDER_READ_CLASS:
        return None
    namespace = vars(BuilderPhaseReader)
    if (BuilderPhaseReader.__bases__ is not _NATIVE_BUILDER_READ_BASES
            or any((name in namespace if original is _NATIVE_BUILDER_READ_MISSING else
                    name not in namespace or namespace[name] is not original)
                   for name, original in _NATIVE_BUILDER_READ_RECIPE.items())):
        return None
    if type(service) is BuilderPhaseReader:
        view = service._service
    elif type(service) is PhaseCharacterReadSystemsService:
        view = service
    else:
        return None
    if type(view) is not PhaseCharacterReadSystemsService:
        return None
    if not _ordinary_copy_policy():
        return None
    phase = view.source_read_phase
    phase.require_open()
    if (phase.systems_view() is not view or phase.owner.campaign_slug != campaign_slug
            or phase.owner._reserved or phase.purpose not in {
                "roster-card-read", "character-shell-read", "character-section-read", "selected-character-read", "assignment-read"}
            or not view._ordinary_feature_source or not view.store._supports_feature_facts()):
        return None
    if not _ordinary_provider_policy():
        return None
    if page_records is not None and not (type(page_records) is list or type(page_records) is tuple):
        return None
    for record in page_records or []:
        if (not _ordinary_page_input(record) or record.campaign_slug != campaign_slug
                or not phase._page_record_matches(record)):
            return None
    # Use the same cache-incapable reader as the old builder entrypoints.
    reader = BuilderPhaseReader(view)
    return _ReadCatalogSource(phase, reader, campaign_slug)


@dataclass(frozen=True, slots=True)
class _CatalogObservation:
    kind: str
    records: tuple

    def field(self, position, name):
        for key, init, value in self.records[position][2]:
            if key == name:
                return thaw(value)
        raise AttributeError(name)


class _ReadCatalogSource:
    """Shared bundle source adapter; captures at the original read positions."""

    __slots__ = ("phase", "reader", "campaign_slug")

    def __init__(self, phase, reader, campaign_slug):
        self.phase, self.reader, self.campaign_slug = phase, reader, campaign_slug

    def capture(self, kind, *, builder=True):
        self.phase.require_open()
        if not _ordinary_copy_policy() or not _ordinary_provider_policy():
            raise SourceReadConflict("Read catalog provider/copy policy changed after source dispatch.")
        if builder:
            from .character_builder_catalogs import _builder_service_cache_identity
            _builder_service_cache_identity(self.reader)
            self.reader.get_campaign_library_slug(self.campaign_slug)
            self.reader.get_durable_revision()
            self.reader.get_cache_context(self.campaign_slug, entry_types=(kind,))
            self.reader.get_durable_revision()
            self.reader.get_cache_context(self.campaign_slug)
        observation, eligible = self.phase.systems_view()._read_catalog_observation(self.campaign_slug, kind)
        if eligible:
            pending = [value for record in observation[2] for name, init, value in record[2]]
            while pending:
                value = pending.pop()
                if value[0] == "scalar" and (value[1] is datetime or value[1] is time):
                    stamp = value[2]
                    if stamp.tzinfo is not None and stamp.tzinfo is not timezone.utc:
                        eligible = False
                        break
                elif value[0] == "scalar" and value[1] is timezone and value[2] is not timezone.utc:
                    eligible = False
                    break
                elif value[0] == "dict":
                    pending.extend(child for key, child in value[1])
                elif value[0] == "sequence":
                    pending.extend(value[2])
        if not eligible:
            from .character_builder_catalogs import _sort_entries_for_builder
            # Rehydrate the already captured observation, without rerunning its
            # SQL, parser, sanitizer or auxiliary producers.
            entries = self.reader.list_enabled_entries_for_campaign(self.campaign_slug,
                entry_type=kind, **({"limit": None} if builder else {}))
            return _sort_entries_for_builder(entries) if builder else entries
        records = observation[2]
        if builder:
            from .character_builder_catalogs import _sort_entries_for_builder
            observed = _CatalogObservation(kind, records)
            positions = _sort_entries_for_builder(list(range(len(records))), field=observed.field)
            records = tuple(records[position] for position in positions)
        return _CatalogObservation(kind, records)

    def _input(self, observation, indices, auxiliary):
        try:
            auxiliary_facts = AuxiliaryFacts(auxiliary)
        except _AuxiliaryUnavailable:
            entries = [thaw(record) for record in observation.records]
            # Retain all already-produced auxiliary values; never rerun their
            # producer or source interpretation when the representation declines.
            mapped = {name: {key: entries[position] for key, position in index.items()}
                      for name, index in indices.items()}
            return {"entries": list(entries), **mapped, **auxiliary}
        immutable_indices = MappingProxyType({name: MappingProxyType(index)
                                              for name, index in indices.items()})
        facts = CatalogFacts(observation.kind, observation.records, immutable_indices)
        return ReadCatalogInput(self.phase, facts, auxiliary_facts)

    def build_item(self, observation, pages):
        from .character_builder_catalogs import (_build_item_catalog,
            _attach_campaign_item_page_support, _item_catalog_groups,
            _item_catalog_indices, _item_catalog_auxiliary)
        if type(observation) is not _CatalogObservation:
            return _attach_campaign_item_page_support(_build_item_catalog(observation), pages)
        groups = _item_catalog_groups(range(len(observation.records)), observation.field)
        auxiliary = _item_catalog_auxiliary()
        indices = _item_catalog_indices(groups)
        auxiliary = _attach_campaign_item_page_support(auxiliary, pages)
        return self._input(observation, indices, auxiliary)

    def build_spell(self, observation):
        from .character_builder_catalogs import (_build_spell_catalog,
            _spell_catalog_indices, _spell_catalog_auxiliary)
        if type(observation) is not _CatalogObservation:
            return _build_spell_catalog(observation)
        indices = _spell_catalog_indices(range(len(observation.records)), observation.field)
        return self._input(observation, indices, _spell_catalog_auxiliary())

    def bundle(self, pages):
        from .character_builder_static_bundle import (_build_builder_bundle_contents,
            _builder_request_page_key, _builder_service_cache_identity, _builder_static_revision_key)
        self.phase.require_open()
        # Preserve the ordinary wrapper's pre-build observations. This exact
        # reader advertises None, so no public cache may receive private inputs.
        _builder_request_page_key(pages)
        _builder_service_cache_identity(self.reader)
        if _builder_static_revision_key(self.reader, self.campaign_slug) is not None:
            raise SourceReadConflict("Private catalog reader unexpectedly acquired a public cache revision.")
        # These are the remaining pre-build observations of _builder_cache_get.
        # Do not place private bundle values into that public cache machinery.
        if self.reader.get_durable_revision() is not None:
            raise SourceReadConflict("Private catalog reader unexpectedly acquired a durable cache revision.")
        self.reader.get_cache_context(self.campaign_slug)
        return _build_builder_bundle_contents(self.reader, self.campaign_slug, pages,
                                             catalog_source=self)
