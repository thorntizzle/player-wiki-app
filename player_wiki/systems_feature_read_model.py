"""Private phase-owned feature facts; public facades return ordinary records.

The backing tree is the existing full frozen record observation, also consumed
by the fresh guard. Views and indices reference it without copying its graph.
Nothing here is a positive authority verdict or a cross-phase cache.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from .character_source_reads import thaw
from .systems_feature_semantics import FeatureSemantics
from .systems_models import SystemsEntryRecord


def _plain_catalog(value):
    """Eligibility only; unusual interpreted leaves retain full legacy thaw."""
    if value[0] != "sequence" or value[1] is not list:
        return False
    pending = []
    for record in value[2]:
        if record[0] != "record" or record[1] is not SystemsEntryRecord:
            return False
        pending.extend(item for name, init, item in record[2])
    while pending:
        item = pending.pop()
        if item[0] in {"scalar", "float"}:
            continue  # freeze admits only its closed immutable scalar types.
        if item[0] == "dict":
            pending.extend(child for key, child in item[1])
            if any(key[0] != "scalar" or key[1] is not str for key, child in item[1]):
                return False
        elif item[0] == "sequence" and item[1] is list:
            pending.extend(item[2])
        else:
            return False
    return True


def _view(value):
    if value[0] == "dict":
        return _FactMap(value)
    if value[0] == "sequence" and value[1] is list:
        return _FactList(value)
    return thaw(value)


class _FactMap(Mapping):
    __slots__ = ("_value",)

    def __init__(self, value):
        self._value = value

    def __getitem__(self, key):
        for candidate, value in self._value[1]:
            if thaw(candidate) == key:
                return _view(value)
        raise KeyError(key)

    def __iter__(self):
        return (thaw(key) for key, value in self._value[1])

    def __len__(self):
        return len(self._value[1])

    def __repr__(self):
        return repr(thaw(self._value))


class _FactList(Sequence):
    __slots__ = ("_value",)

    def __init__(self, value):
        self._value = value

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [_view(item) for item in self._value[2][index]]
        return _view(self._value[2][index])

    def __len__(self):
        return len(self._value[2])

    def __repr__(self):
        return repr(thaw(self._value))


class _FeatureFact:
    __slots__ = ("_value",)

    def __init__(self, value):
        self._value = value

    def __getattr__(self, name):
        for key, init, value in self._value[2]:
            if key == name:
                return _view(value)
        raise AttributeError(name)

    def __eq__(self, other):
        if self is other:
            return True
        if type(other) is _FeatureFact:
            return thaw(self._value) == thaw(other._value)
        return thaw(self._value) == other


class PhaseFeatureReadModel(FeatureSemantics):
    """One semantic adapter for the complete native class/subclass family."""

    def __init__(self, service):
        self._service = service
        self._catalogs = {}
        self._selected_records = None

    def __getattr__(self, name):
        # Only the shared semantics use the existing service helpers. Never
        # forward this object to authority or a public/native caller.
        return getattr(self._service, name)

    def close(self):
        self._catalogs.clear()
        self._selected_records = None
        self._service = None

    @staticmethod
    def _feature_is_map(value):
        return isinstance(value, dict) or type(value) is _FactMap

    @staticmethod
    def _feature_is_list(value):
        return isinstance(value, list) or type(value) is _FactList

    @staticmethod
    def _feature_is_entry(value):
        return isinstance(value, SystemsEntryRecord) or type(value) is _FeatureFact

    def _feature_public_entry(self, value):
        if type(value) is not _FeatureFact:
            return value
        identity = id(value)
        if identity not in self._selected_records:
            self._selected_records[identity] = thaw(value._value)
        return self._selected_records[identity]

    def result_for(self, method, *args, **kwargs):
        """One ordinary return owns selected records, including its decorators."""
        self._service.source_read_phase.require_open()
        if self._selected_records is not None:
            raise RuntimeError("Nested feature output adaptation is unavailable.")
        self._selected_records = {}
        try:
            value = getattr(self, method)(*args, **kwargs)
            return self._detach(value, set())
        finally:
            self._selected_records = None

    def _detach(self, value, visited):
        if type(value) is _FeatureFact:
            return self._feature_public_entry(value)
        if isinstance(value, SystemsEntryRecord):
            # Campaign rows and nonplain fallthrough already have the public
            # facade's ordinary ownership. Do not add constructor invocations.
            return value
        if type(value) is list or type(value) is dict:
            if id(value) in visited:
                return value
            visited.add(id(value))
            # These are newly constructed result containers, never fact trees.
            # In-place adaptation preserves their existing nested alias graph.
            if type(value) is list:
                for index, item in enumerate(value):
                    value[index] = self._detach(item, visited)
            else:
                for key in value:
                    value[key] = self._detach(value[key], visited)
        return value

    def _catalog(self, campaign_slug, kind):
        service = self._service
        service._check_campaign(campaign_slug)
        if kind not in self._catalogs:
            # Same library/policy/source-state recipe as enabled public lists.
            library = service.get_campaign_library(campaign_slug)
            lookup = {}
            if library is not None:
                source_ids = [str(row.source.source_id or "").strip()
                    for row in service.list_campaign_source_states(campaign_slug)
                    if row.is_enabled and str(row.source.source_id or "").strip()]
                if source_ids:
                    catalog, eligible = service.store._feature_catalog_facts(
                        campaign_slug, library.library_slug, source_ids,
                        entry_type=kind, query="", limit=None)
                    if not eligible:
                        self._catalogs[kind] = None
                        return None
                    for signature in catalog[2]:
                        candidate = _FeatureFact(signature)
                        name = str(candidate.metadata.get("class_name", "") or "").strip()
                        source = str(candidate.metadata.get("class_source", "") or "").strip().upper()
                        identity = (name, source)
                        if kind == "subclassfeature":
                            identity += (str(candidate.metadata.get("subclass_source", "") or "").strip().upper(),)
                        if all(identity):
                            lookup.setdefault(identity, []).append(candidate)
            self._catalogs[kind] = lookup
        return self._catalogs[kind]

    def _class_feature_entries_by_class_identity(self, campaign_slug, *, identity=None):
        lookup = self._catalog(campaign_slug, "classfeature")
        if lookup is None:
            return self._service._class_feature_entries_by_class_identity(campaign_slug, identity=identity)
        return lookup.get(identity, []) if identity is not None else lookup

    def _subclass_feature_entries_by_class_and_source(self, campaign_slug, *, identity=None):
        lookup = self._catalog(campaign_slug, "subclassfeature")
        if lookup is None:
            return self._service._subclass_feature_entries_by_class_and_source(campaign_slug, identity=identity)
        return lookup.get(identity, []) if identity is not None else lookup
