"""Private read foundations; public builder catalogs remain ordinary values.

Only owned, current read phases can issue these inputs. They carry complete
observations, never authorization or reusable qualification decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .character_read_catalogs import ReadCatalogInput, read_catalog_source
from .character_source_reads import SourceReadConflict


@dataclass(frozen=True, slots=True)
class NativeReadFoundation:
    campaign_slug: str
    character_slug: str
    system: str
    profile_identity: str
    derivation_components: frozenset[str] | None
    _campaign_page_records: tuple[Any, ...]
    _resolved_entries: dict[str, Any]
    _item_catalog: object
    _spell_catalog: object
    _automatic_prepared_lookup_keys_by_row: dict[str, frozenset[str]]


def _bound_catalog(value, phase, kind):
    if type(value) is not ReadCatalogInput:
        return False
    value.check()
    if value._phase is not phase or value._facts.kind != kind:
        raise SourceReadConflict("Read catalog does not belong to this source phase and kind.")
    return True


def detach_read_preparation(value, phase):
    from . import character_builder as builder
    if type(value) is ReadCatalogInput:
        value.check()
        if value._phase is not phase:
            raise SourceReadConflict("Cannot prepare a catalog from a different source phase.")
        return value.fork_for_foundation()
    # Match the existing recursive preparation recipe, including independently
    # copied record occurrences and conversion of MappingProxyType to dict.
    if isinstance(value, (dict, MappingProxyType)):
        return {builder.deepcopy(key): detach_read_preparation(item, phase)
                for key, item in value.items()}
    if isinstance(value, list):
        return [detach_read_preparation(item, phase) for item in value]
    if isinstance(value, tuple):
        return tuple(detach_read_preparation(item, phase) for item in value)
    if isinstance(value, set):
        return {detach_read_preparation(item, phase) for item in value}
    if isinstance(value, frozenset):
        return frozenset(detach_read_preparation(item, phase) for item in value)
    return builder.deepcopy(value)


def prepare_read_foundation(definition, *, item_catalog=None, spell_catalog=None,
                            systems_service=None, campaign_page_records=None, **kwargs):
    from . import character_builder as builder
    if type(definition) is not builder.CharacterDefinition:
        return None
    source = read_catalog_source(systems_service, definition.campaign_slug, campaign_page_records)
    if source is None:
        if type(item_catalog) is ReadCatalogInput or type(spell_catalog) is ReadCatalogInput:
            raise SourceReadConflict("Read preparation provider changed after catalog dispatch.")
        return None
    if source.phase.owner.character_slug != definition.character_slug:
        return None
    native_item = _bound_catalog(item_catalog, source.phase, "item")
    native_spell = _bound_catalog(spell_catalog, source.phase, "spell")
    # An explicit caller catalog is never relabeled as source facts. Mixed
    # catalogs retain ordinary detachment for the ordinary half.
    if not native_item and not native_spell and (item_catalog is not None or spell_catalog is not None):
        return None
    return builder._prepare_native_foundation_impl(
        definition, item_catalog=item_catalog, spell_catalog=spell_catalog,
        systems_service=systems_service, campaign_page_records=campaign_page_records,
        _read_source=source, _foundation_type=NativeReadFoundation, **kwargs)


def _read_catalog_for_definition(kind, definition, *, item_catalog=None,
                                 spell_catalog=None, systems_service=None,
                                 campaign_page_records=None):
    from . import character_builder as builder
    supplied = item_catalog if kind == "item" else spell_catalog
    legacy = (builder._effective_item_catalog_for_definition if kind == "item"
              else builder._effective_spell_catalog_for_definition)
    keyword = {kind + "_catalog": supplied}
    if type(supplied) is ReadCatalogInput:
        source = read_catalog_source(systems_service, definition.campaign_slug, campaign_page_records)
        if source is None:
            raise SourceReadConflict("Read catalog provider changed after source dispatch.")
        _bound_catalog(supplied, source.phase, kind)
        return supplied
    if supplied is None:
        source = read_catalog_source(systems_service, definition.campaign_slug, campaign_page_records)
        if source is not None:
            # Initial validators originally produced all eight sibling sources.
            # Preserve that recipe even though they consume one catalog.
            return source.bundle(campaign_page_records)[kind + "_catalog"]
    return legacy(definition, systems_service=systems_service,
                  campaign_page_records=campaign_page_records, **keyword)


def read_item_catalog_for_definition(definition, *, item_catalog=None,
                                     systems_service=None, campaign_page_records=None):
    return _read_catalog_for_definition("item", definition, item_catalog=item_catalog,
        systems_service=systems_service, campaign_page_records=campaign_page_records)


def read_spell_catalog_for_definition(definition, *, spell_catalog=None,
                                      systems_service=None, campaign_page_records=None):
    return _read_catalog_for_definition("spell", definition, spell_catalog=spell_catalog,
        systems_service=systems_service, campaign_page_records=campaign_page_records)


def build_read_item_catalog(service, campaign_slug, pages):
    source = read_catalog_source(service, campaign_slug, pages)
    return None if source is None else source.build_item(source.capture("item"), pages)


def build_read_spell_catalog(service, campaign_slug, *, scoped=False):
    source = read_catalog_source(service, campaign_slug)
    if source is None:
        return None
    if scoped:
        from .character_builder_catalogs import _builder_service_cache_identity
        _builder_service_cache_identity(source.reader)
        if source.reader.get_durable_revision() is not None:
            raise SourceReadConflict("Private spell reader unexpectedly acquired a cache revision.")
        source.reader.get_cache_context(campaign_slug)
    return source.build_spell(source.capture("spell", builder=scoped))


def read_enabled_spell_entries(service, campaign_slug):
    """Raw source-list recipe, without adding catalog auxiliary producers."""
    from .character_read_catalogs import _CatalogObservation, CatalogFacts, AuxiliaryFacts
    source = read_catalog_source(service, campaign_slug)
    if source is None:
        return None
    observation = source.capture("spell", builder=False)
    if type(observation) is not _CatalogObservation:
        return observation
    return ReadCatalogInput(source.phase,
        CatalogFacts("spell", observation.records, MappingProxyType({})), AuxiliaryFacts({}))


def normalize_read_facade(legacy_normalizer, definition, **kwargs):
    """Choose native preparation or the exact original caller's facade/kwargs."""
    from . import character_builder as builder
    mode = kwargs.get("mode", "historical")
    source = None
    if (type(definition) is builder.CharacterDefinition and type(mode) is str
            and mode in {"effective", "historical"}):
        source = read_catalog_source(kwargs.get("systems_service"), definition.campaign_slug,
                                     kwargs.get("campaign_page_records"))
        if source is not None and legacy_normalizer is not builder.normalize_definition_to_native_model:
            source = None
    if source is None:
        if any(type(kwargs.get(name)) is ReadCatalogInput for name in ("item_catalog", "spell_catalog")):
            raise SourceReadConflict("Read normalizer provider changed after catalog dispatch.")
        return legacy_normalizer(definition, **kwargs)
    return builder.normalize_definition_for_source_read(definition, **kwargs)


# Finite ordinary callback surface omitted by invocation-owned current inputs.
_CURRENT_INPUT_RECIPE = tuple((name, globals()[name]) for name in (
    'read_item_catalog_for_definition',
))
