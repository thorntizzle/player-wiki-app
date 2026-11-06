"""Explicit operations shared by ordinary and private read catalog inputs.

Private catalogs intentionally do not implement Mapping. Selection must name
the index/scan it needs; an incidental dict(index) cannot hydrate everything.
Ordinary adapters retain the existing dictionary and record boundaries.
"""
from __future__ import annotations


def native_catalog(value):
    from .character_read_catalogs import ReadCatalogInput
    if type(value) is ReadCatalogInput:
        value.check()
        return value
    return None


def catalog_snapshot(value):
    native = native_catalog(value)
    return native if native is not None else dict(value or {})


def catalog_index(value, name, *, copy=False, required=False):
    native = native_catalog(value)
    if native is not None:
        return native.index(name)
    index = value[name] if required else value.get(name) or {}
    return dict(index) if copy else index


def catalog_aux(value, name, default=None):
    native = native_catalog(value)
    return native.aux(name, default) if native is not None else value.get(name, default)


def catalog_rows(value, *, raw=False):
    native = native_catalog(value)
    if native is not None:
        return native.rows()
    return value.get("entries", []) if raw else list(value.get("entries") or [])


def catalog_is_record(value, row):
    native = native_catalog(value)
    if native is not None:
        return True  # Rows were issued from the complete stock-record snapshot.
    from .systems_models import SystemsEntryRecord
    return isinstance(row, SystemsEntryRecord)


def catalog_field(value, row, name):
    native = native_catalog(value)
    return native.field(row, name) if native is not None else getattr(row, name)


def catalog_record(value, row, *, origin="entries"):
    native = native_catalog(value)
    return native.materialize(row, origin) if native is not None else row

