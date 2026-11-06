"""Connection-owned external facts for one native Character read phase.

These are private, nonpersisted lifetimes. Models, authority, custody and
positive issuances are deliberately outside the immutable source cache.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from datetime import datetime, date, time, timedelta, timezone
from pathlib import PurePath
from typing import Any
from weakref import WeakSet


class SourceReadConflict(RuntimeError):
    """A source phase cannot establish its required ownership or freshness."""


class SourceReadUnavailable(SourceReadConflict):
    """Predispatch missing-library fallback; never retry completed work."""


_OWNED_READ = object()
_RESERVED_READ = object()


def _require_app_connection(connection):
    from flask import g, has_app_context
    if not has_app_context() or getattr(g, "db_connection", None) is not connection:
        raise SourceReadConflict("Source reads require the application's exact current connection.")
    from .db import get_db
    if get_db() is not connection:  # Also refuse a previously quarantined handle.
        raise SourceReadConflict("Source connection ownership is unavailable.")


class PhaseRepositoryStore:
    """A detached one-campaign view, never a live repository reload owner."""

    def __init__(self, phase):
        self.source_read_phase = phase
        self.page_store = phase.page_store()

    def get(self):
        phase = self.source_read_phase
        phase.require_open()
        from .repository import Repository
        return Repository({phase.owner.campaign_slug: phase.campaign()}, phase.page_store())


def freeze(value):
    """Preserve types and order without JSON coercion or mutable aliases."""
    kind = type(value)
    if kind is float:
        return ("float", value.hex())
    if value is None or kind in (str, bytes, bool, int, datetime, date, time,
                                 timedelta, timezone):
        return ("scalar", kind, value)
    if isinstance(value, PurePath):
        return ("path", kind, str(value))
    if kind is dict:
        return ("dict", tuple((freeze(k), freeze(v)) for k, v in value.items()))
    if kind in (tuple, list, set, frozenset):
        return ("sequence", kind, tuple(freeze(v) for v in value))
    if is_dataclass(value) and not isinstance(value, type):
        return ("record", kind, tuple((f.name, f.init, freeze(getattr(value, f.name)))
                                      for f in fields(value)))
    raise SourceReadConflict("Unsupported mutable source fact type.")


def thaw(value):
    tag = value[0]
    if tag == "scalar":
        return value[2]
    if tag == "float":
        return float.fromhex(value[1])
    if tag == "path":
        return value[1](value[2])
    if tag == "dict":
        return {thaw(k): thaw(v) for k, v in value[1]}
    if tag == "sequence":
        return value[1](thaw(v) for v in value[2])
    if tag == "record":
        result = value[1](**{name: thaw(v) for name, init, v in value[2] if init})
        for name, init, v in value[2]:
            if not init:
                object.__setattr__(result, name, thaw(v))
        return result
    raise SourceReadConflict("Unknown immutable source fact tag.")


def phase_of(value):
    phase = getattr(value, "source_read_phase", None)
    if phase is not None:
        phase.require_open()
    return phase


def source_active(systems_service=None, *, phase=None):
    phase = phase if phase is not None else phase_of(systems_service)
    if phase is not None:
        phase.require_open()
        return True
    from .committed_publication import active
    return active()


class SourceReadOwner:
    """Only owned mode may end transactions; reservation belongs to publisher."""

    def __init__(self, connection, campaign_slug, character_slug, *, _mode):
        if _mode is not _OWNED_READ and _mode is not _RESERVED_READ:
            raise SourceReadConflict("Source owner requires an explicit transaction owner.")
        _require_app_connection(connection)
        self.connection = connection
        self.campaign_slug = str(campaign_slug)
        self.character_slug = str(character_slug)
        self._reserved = _mode is _RESERVED_READ
        self._reserved_changes = connection.total_changes if self._reserved else None
        self._open = True
        self._phase = None
        self._failed = False
        self._rollback_failed = False
        self._owned_transaction_active = False
        self._write_started = False
        self._last_guard = None
        self._declined = False
        self.counts = {"phases": 0, "guards": 0, "source_loads": 0}

    @classmethod
    def owned(cls, connection, campaign_slug, character_slug):
        if connection.in_transaction:
            raise SourceReadConflict("Native source reads require an owned transaction boundary.")
        return cls(connection, campaign_slug, character_slug, _mode=_OWNED_READ)

    @classmethod
    def _after_publication_reserve(cls, connection, campaign_slug, character_slug):
        # The sole caller is lexically after publish_update's successful _reserve.
        if not connection.in_transaction:
            raise SourceReadConflict("Publication source reservation is unavailable.")
        return cls(connection, campaign_slug, character_slug, _mode=_RESERVED_READ)

    def require_live(self):
        if not self._open or self._failed or self._write_started:
            raise SourceReadConflict("Native source owner is no longer usable.")
        _require_app_connection(self.connection)
        if self._reserved and self.connection.total_changes != self._reserved_changes:
            self._failed = True
            raise SourceReadConflict("Reserved source reads encountered a database write.")

    def _rollback_owned(self):
        if self._rollback_failed:
            from .db import SourceReadConnectionFatal
            raise SourceReadConnectionFatal("Source rollback already failed; connection requires disposal.")
        try:
            from .db import rollback_source_read_connection
            rollback_source_read_connection(self.connection)
            self._owned_transaction_active = False
        except BaseException:
            self._failed = True
            self._rollback_failed = True
            raise

    @contextmanager
    def open_phase(self, purpose, *, systems_service, campaign, record=None):
        self.require_live()
        if self._phase is not None:
            raise SourceReadConflict("Positive issuers cannot nest an owned source phase.")
        connection = self.connection
        if self._reserved:
            if not connection.in_transaction:
                raise SourceReadConflict("Publication lost its source reservation.")
        elif connection.in_transaction:
            raise SourceReadConflict("Unowned ambient source transaction.")
        begun = False
        phase = None
        primary = None
        try:
            if not self._reserved:
                begun = True
                self._owned_transaction_active = True
                connection.execute("BEGIN")
            phase = SourceReadPhase(self, purpose, systems_service, campaign, record)
            self._phase = phase
            self.counts["phases"] += 1
            yield phase
            phase.finish()
        except BaseException as exc:
            primary = exc
            if not isinstance(exc, SourceReadUnavailable) or self._reserved:
                self._failed = True
            raise
        finally:
            cleanup = []
            try:
                if phase is not None:
                    phase.invalidate()
            except BaseException as exc:
                cleanup.append(exc)
            try:
                if begun and not self._rollback_failed and self._owned_transaction_active:
                    self._rollback_owned()
            except BaseException as exc:
                cleanup.append(exc)
            finally:
                self._phase = None
            if cleanup:
                self._failed = True
                from .db import SourceReadConnectionFatal
                fatal = next((error for error in cleanup if isinstance(error, SourceReadConnectionFatal)), None)
                if fatal is not None:
                    others = ([primary] if primary is not None else []) + [error for error in cleanup if error is not fatal]
                    if fatal.__cause__ is not None:
                        others.append(fatal.__cause__)
                    if others:
                        raise fatal from BaseExceptionGroup("Source read primary and cleanup failures", others)
                    raise fatal
                if primary is not None:
                    details = list(cleanup)
                    if primary.__cause__ is not None:
                        details.append(primary.__cause__)
                    raise primary from BaseExceptionGroup("Source read cleanup failures", details)
                if len(cleanup) == 1:
                    raise cleanup[0]
                raise BaseExceptionGroup("Source read cleanup failures", cleanup)

    def before_publication_write(self):
        self.require_live()
        if self._phase is not None:
            raise SourceReadConflict("A source view is still open before publication.")
        self._write_started = True
        self._open = False
        self._last_guard = None

    def checkpoint(self):
        """Fresh post-callback guard, never a reusable positive admission."""
        self.require_live()
        if self._declined:
            if self._phase is not None or self.connection.in_transaction:
                raise SourceReadConflict("Unphased fallback left an unknown read transaction.")
            return  # Existing unphased checks apply; no phase proof is claimed.
        if self._phase is not None or self._last_guard is None:
            raise SourceReadConflict("Native issuance lacks a completed source phase.")
        phase, basis, reads = self._last_guard
        phase._fresh_guard(basis, reads)

    def close(self):
        self._open = False
        self._last_guard = None
        phase, self._phase = self._phase, None
        if phase is not None:
            phase.invalidate()


class SourceReadPhase:
    def __init__(self, owner, purpose, service, campaign, record):
        self.owner = owner
        self.purpose = str(purpose)
        self._open = True
        self._finished = False
        self._cache = {}
        self._readset = {}
        self._read_catalog_inputs = WeakSet()
        self._service = service
        self._campaign_path = None
        self._basis = None
        self._initial_changes = owner.connection.total_changes
        try:
            if campaign is not None and campaign.slug != owner.campaign_slug:
                raise SourceReadConflict("Source campaign ownership differs.")
            from pathlib import Path
            # The path supplies existing hydration roots only, never file content.
            self._campaign_path = Path(service.repository_store.campaigns_dir) / owner.campaign_slug / "campaign.yaml"
            self._basis = freeze(self._observe_basis())
            self._page_index = {row["page_ref"]: freeze((row, source))
                                for row, source in self.fact("pages")}
            from .systems_store import ConnectionReadSystemsStore
            self.store = ConnectionReadSystemsStore(service.store, owner.connection, self)
            previous = owner._last_guard
            if previous is not None:
                if self._basis != previous[1]:
                    raise SourceReadConflict("Source facts changed between native read phases.")
                # Comparison material is never reused as a cache value. Repeat
                # actual reads in the new snapshot before consuming prior
                # issued model facts, even if the revision token is unchanged.
                for method, args, kwargs, observation in previous[2]:
                    if freeze(getattr(self.store, method)(*thaw(args), **thaw(kwargs))) != observation:
                        raise SourceReadConflict("Systems facts changed between native read phases.")
            from .systems_service import PhaseCharacterReadSystemsService
            self._view = PhaseCharacterReadSystemsService(service, self)
            actual_campaign = self.campaign()
            if campaign is not None and any(getattr(campaign, key) != getattr(actual_campaign, key) for key in (
                    "slug", "title", "summary", "system", "current_session", "source_wiki_root",
                    "player_content_dir", "assets_dir", "systems_library_slug", "systems_source_defaults")):
                raise SourceReadConflict("Supplied campaign differs from captured committed settings.")
            library_slug = self._view.get_campaign_library_slug(owner.campaign_slug)
            if not library_slug or self.store.get_library(library_slug) is None:
                raise SourceReadUnavailable("Missing Systems library requires unphased initialization.")
            if record is not None:
                self.bind_record(record)
        except BaseException:
            self.invalidate()
            raise

    @property
    def connection(self):
        self.require_open()
        return self.owner.connection

    def require_open(self):
        self.owner.require_live()
        if not self._open or not self.owner.connection.in_transaction:
            raise SourceReadConflict("Source phase has ended or lost its snapshot.")

    def resolve(self, namespace, key, loader, *, domain_errors=()):
        self.require_open()
        try:
            identity = (namespace, freeze(key))
            if identity not in self._cache:
                self._cache[identity] = freeze(loader())
                self.owner.counts["source_loads"] += 1
            return thaw(self._cache[identity])
        except BaseException as exc:
            if not isinstance(exc, domain_errors):
                self.owner._failed = True
            raise

    def store_read(self, method, args, kwargs, loader):
        self.require_open()
        identity = (method, freeze(args), freeze(kwargs))
        result = self.resolve("store", (method, args, kwargs), loader)
        if identity not in self._readset:
            self._readset[identity] = (method, freeze(args), freeze(kwargs), freeze(result))
        return result

    def store_fact_read(self, method, args, kwargs, loader):
        """Private ordinary-store signature; share generic cache and guard identity."""
        self.require_open()
        try:
            identity = ("store", freeze((method, args, kwargs)))
            if identity not in self._cache:
                self._cache[identity] = loader()
                self.owner.counts["source_loads"] += 1
            observation = self._cache[identity]
            from .systems_feature_read_model import _plain_catalog
            eligible = _plain_catalog(observation)
            if eligible:
                read_key = (method, freeze(args), freeze(kwargs))
                self._readset.setdefault(read_key, (method, read_key[1], read_key[2], observation))
            # A nonplain catalog stays in the SAME ordinary store cache. The
            # legacy facade consumes it once, registers its post-thaw readset
            # observation and preserves all original constructor callbacks.
            return observation, eligible
        except BaseException:
            self.owner._failed = True
            raise

    def _observe_basis(self):
        from .committed_publication import active, config, _page_row_facts
        from .committed_character_publication import exact_character
        from .character_native_requalification import source_identity, _audit_prefix
        connection = self.owner.connection
        campaign, character = self.owner.campaign_slug, self.owner.character_slug
        if not active(connection):
            raise SourceReadConflict("Native source phase requires committed activation.")
        settings_source, settings = config(campaign, connection=connection)
        generation = exact_character(campaign, character, connection=connection)
        state = connection.execute("SELECT * FROM character_state WHERE campaign_slug=? AND character_slug=?",
                                   (campaign, character)).fetchone()
        if generation is None or state is None:
            raise SourceReadConflict("Native character generation/state is unavailable.")
        pages = [(dict(row), source) for row, source in
                 _page_row_facts(campaign, connection=connection)]
        return {"config": (settings_source, settings), "generation": generation,
                "state": dict(state), "pages": pages,
                "identity": source_identity(connection, campaign, character),
                "audit": _audit_prefix(connection, campaign, character)}

    def facts(self):
        self.require_open()
        return thaw(self._basis)

    def fact(self, name):
        self.require_open()
        for key, value in self._basis[1]:
            if thaw(key) == name:
                return thaw(value)
        raise SourceReadConflict("Unknown source phase fact.")

    def page_fact(self, ref):
        self.require_open()
        value = self._page_index.get(ref)
        return thaw(value) if value is not None else None

    def page_source(self, ref):
        value = self.page_fact(ref)
        return value[1] if value is not None else None

    def bind_record(self, record):
        from .character_models import CharacterDefinition, CharacterImportMetadata
        from .committed_source_store import _decode_mapping
        from .auth_store import parse_timestamp
        import json
        generation, state = self.fact("generation"), self.fact("state")
        if (record.definition.campaign_slug != self.owner.campaign_slug
                or record.definition.character_slug != self.owner.character_slug
                or record.committed_revision != generation["revision"]
                or freeze(record.definition.to_dict()) != freeze(CharacterDefinition.from_dict(
                    _decode_mapping(generation["primary_bytes"])).to_dict())
                or freeze(record.import_metadata.to_dict()) != freeze(CharacterImportMetadata.from_dict(
                    _decode_mapping(generation["secondary_bytes"])).to_dict())
                or record.state_record.revision != state["revision"]
                or record.state_record.campaign_slug != self.owner.campaign_slug
                or record.state_record.character_slug != self.owner.character_slug
                or record.state_record.updated_at != parse_timestamp(state["updated_at"])
                or record.state_record.updated_by_user_id != state["updated_by_user_id"]
                or freeze(record.state_record.state) != freeze(json.loads(state["state_json"]))):
            raise SourceReadConflict("Supplied native record differs from the captured generation.")

    def character_pages(self):
        return [record for record in self.page_records(include_body=True)
                if str(record.page.section or "").strip() != "Sessions"]

    def bind_pages(self, supplied, *, sections=None):
        selected = [record for record in supplied or []
                    if sections is None or str(record.page.section or "").strip() in sections]
        actual = [record for record in self.character_pages()
                  if sections is None or str(record.page.section or "").strip() in sections]
        if [record.page_ref for record in selected] != [record.page_ref for record in actual]:
            raise SourceReadConflict("Supplied source page membership differs from captured inputs.")
        for record in selected:
            self.bind_page_record(record)

    def bind_page_record(self, record):
        """Compare all rule-facing fields, including detached Page projections."""
        self.require_open()
        if record.campaign_slug != self.owner.campaign_slug:
            raise SourceReadConflict("Supplied page belongs to another campaign.")
        if not self._page_record_matches(record):
            raise SourceReadConflict("Supplied page differs from captured source facts.")

    def _page_record_matches(self, record):
        """Comparison only; an unsupported private recipe may stay ordinary."""
        self.require_open()
        expected = self.page_store().get_page_record(self.owner.campaign_slug, record.page_ref,
                    include_body=bool(record.page.content_loaded))
        def semantic(value):
            if value is None:
                return None
            rendered_only = {"body_html", "html_loaded", "resolved_links", "backlinks"}
            page = {field.name: getattr(value.page, field.name)
                    for field in fields(value.page) if field.name not in rendered_only}
            return (value.campaign_slug, value.page_ref, value.relative_path, value.metadata,
                    value.updated_at, value.body_markdown, page)
        return freeze(semantic(record)) == freeze(semantic(expected))

    def systems_view(self):
        self.require_open()
        return self._view

    def campaign(self):
        self.require_open()
        from .repository import CampaignConfig, hydrate_campaign, build_alias_index, resolve_campaign_links
        settings = self.fact("config")[1]
        spec = CampaignConfig(self._campaign_path, settings,
                              self._campaign_path.parent / settings.get("player_content_dir", "content"),
                              settings["slug"], ())
        result = hydrate_campaign(self._campaign_path, spec, self.page_store().list_pages(self.owner.campaign_slug))
        result.alias_index = build_alias_index(result)
        resolve_campaign_links(result)
        return result

    def page_store(self):
        self.require_open()
        from .campaign_page_store import PhaseCampaignPageStore
        return PhaseCampaignPageStore(self, self._service.repository_store.page_store)

    def page_records(self, *, include_body=True):
        self.require_open()
        from .models import page_sort_key
        settings_source, settings = self.fact("config")
        def load():
            records = self.page_store().list_page_records(self.owner.campaign_slug, include_body=include_body)
            return sorted((record for record in records
                           if record.page.published and not record.page.is_deprecated_wiki_overview
                           and record.page.reveal_after_session <= int(settings["current_session"])),
                          key=lambda record: (*page_sort_key(record.page), record.page_ref))
        return self.resolve("visible-character-pages", (include_body,), load)

    def finish(self):
        if self._finished:
            self.owner.require_live()
            return
        self.require_open()
        if self.owner.connection.total_changes != self._initial_changes:
            self.owner._failed = True
            raise SourceReadConflict("A source phase performed a database write.")
        expected = self._basis
        reads = tuple(self._readset.values())
        self.invalidate()
        self._fresh_guard(expected, reads, closing_snapshot=True)
        self.owner._last_guard = (self, expected, reads)
        self._finished = True

    def _fresh_guard(self, expected, reads, *, closing_snapshot=False):
        self.owner.require_live()
        connection = self.owner.connection
        owns_cleanup = False
        primary = None
        try:
            if not self.owner._reserved:
                if closing_snapshot:
                    self.owner._rollback_owned()
                elif connection.in_transaction:
                    raise SourceReadConflict("Native postphase guard cannot borrow another transaction.")
                owns_cleanup = True
                self.owner._owned_transaction_active = True
                connection.execute("BEGIN")
            elif not connection.in_transaction:
                raise SourceReadConflict("Native guard lost publication reservation.")
            self.owner.require_live()
            if freeze(self._observe_basis()) != expected:
                raise SourceReadConflict("Native source facts changed after the read phase.")
            from .systems_store import ConnectionReadSystemsStore
            reader = ConnectionReadSystemsStore(self._service.store, connection, None)
            for method, args, kwargs, observation in reads:
                if freeze(getattr(reader, method)(*thaw(args), **thaw(kwargs))) != observation:
                    raise SourceReadConflict("Captured Systems facts changed after the read phase.")
            self.owner.counts["guards"] += 1
        except BaseException as exc:
            primary = exc
            self.owner._failed = True
            raise
        finally:
            if owns_cleanup and not self.owner._rollback_failed:
                try:
                    self.owner._rollback_owned()
                except BaseException as cleanup:
                    if primary is not None:
                        details = [primary]
                        if cleanup.__cause__ is not None:
                            details.append(cleanup.__cause__)
                        raise cleanup from BaseExceptionGroup("Source guard primary and cleanup failures", details)
                    raise

    def invalidate(self):
        self._open = False
        self._basis = None
        self._page_index = {}
        errors = []
        for catalog in list(self._read_catalog_inputs):
            try:
                catalog.close()
            except BaseException as exc:
                errors.append(exc)
        self._read_catalog_inputs.clear()
        view = getattr(self, "_view", None)
        caches = [self._cache, self._readset]
        if view is not None:
            caches.append(view._phase_subsets)
            model = view._feature_read_model
            if model is not None:
                model.close()
            view._feature_read_model = None
        for cache in caches:
            try:
                cache.clear()
            except BaseException as exc:
                errors.append(exc)
        if errors:
            self.owner._failed = True
            if len(errors) == 1:
                raise errors[0]
            raise BaseExceptionGroup("Source cache invalidation failures", errors)


@contextmanager
def native_source_phase(owner, *, systems_service, campaign, record, purpose):
    """Missing-library dispatch is chosen before any consumer is invoked."""
    if owner._declined:
        owner.require_live()
        if owner._reserved or owner.connection.in_transaction:
            raise SourceReadConflict("Unphased dispatch is unavailable in a reservation.")
        yield None
        return
    entered = False
    try:
        with owner.open_phase(purpose, systems_service=systems_service,
                              campaign=campaign, record=record) as phase:
            entered = True
            yield phase
    except SourceReadUnavailable:
        if entered or owner._reserved or owner._failed:
            raise
        owner._declined = True
        # No model/producer/callback ran. The caller follows its old path once.
        yield None


@contextmanager
def native_character_source_context(record, *, source_read_owner=None, systems_service=None,
                                    campaign=None, purpose="native-consumer", source_read_phase=None):
    """Explicit scope for consumers that need service and page inputs together."""
    if source_read_phase is not None:
        source_read_phase.require_open()
        if source_read_owner is not None and source_read_phase.owner is not source_read_owner:
            raise SourceReadConflict("Read consumer received different phase ownership.")
        source_read_phase.bind_record(record)
        yield (source_read_phase, source_read_phase.systems_view(),
               source_read_phase.character_pages(), source_read_phase.owner)
        return  # Read consumers do not finish or issue a nested phase.
    from .db import get_db
    if systems_service is None:
        from .auth import get_systems_service
        systems_service = get_systems_service().character_read_view()
    owned = source_read_owner is None
    owner = source_read_owner if source_read_owner is not None else SourceReadOwner.owned(
        get_db(), record.definition.campaign_slug, record.definition.character_slug)
    try:
        with native_source_phase(owner, systems_service=systems_service, campaign=campaign,
                                 record=record, purpose=purpose) as phase:
            if phase is not None:
                yield phase, phase.systems_view(), phase.character_pages(), owner
            else:
                from .character_page_records import list_visible_character_page_records
                if campaign is None:
                    campaign = systems_service._get_campaign(record.definition.campaign_slug)
                pages = list_visible_character_page_records(systems_service.repository_store.page_store,
                    record.definition.campaign_slug, campaign, include_body=True, excluded_sections={"Sessions"})
                yield None, systems_service, pages, owner
    finally:
        if owned:
            owner.close()


class BuilderPhaseReader:
    """Cache-incapable builder helper reader, NEVER an authority/digest service.

    None is the existing builder cache-unavailable capability sentinel. Actual
    semantic reads stay bound to the real phase service. A callable durable
    method preserves the builders' selected-entry re-fetch branch.
    """

    __slots__ = ("_service",)

    def __init__(self, service):
        self._service = service

    @property
    def source_read_phase(self):
        return phase_of(self._service)

    def character_read_view(self):
        self.source_read_phase.require_open()
        return self

    def get_durable_revision(self):
        self.source_read_phase.require_open()
        return None

    def get_builder_static_revision(self, *args, **kwargs):
        self.source_read_phase.require_open()
        return None

    def build_class_feature_progression_for_class_entry(self, *args, **kwargs):
        self.source_read_phase.require_open()
        return self._service.build_class_feature_progression_for_class_entry(*args, **kwargs)

    def build_subclass_feature_progression_for_subclass_entry(self, *args, **kwargs):
        self.source_read_phase.require_open()
        return self._service.build_subclass_feature_progression_for_subclass_entry(*args, **kwargs)

    def collect_attained_deterministic_feature_entries(self, *args, **kwargs):
        self.source_read_phase.require_open()
        return self._service.collect_attained_deterministic_feature_entries(*args, **kwargs)

    def get_cache_context(self, *args, **kwargs):
        self.source_read_phase.require_open()
        return self._service.get_cache_context(*args, **kwargs)

    def get_campaign_library(self, *args, **kwargs):
        self.source_read_phase.require_open()
        return self._service.get_campaign_library(*args, **kwargs)

    def get_campaign_library_slug(self, *args, **kwargs):
        self.source_read_phase.require_open()
        return self._service.get_campaign_library_slug(*args, **kwargs)

    def get_entry_by_slug_for_campaign(self, *args, **kwargs):
        self.source_read_phase.require_open()
        return self._service.get_entry_by_slug_for_campaign(*args, **kwargs)

    def get_entry_for_campaign(self, *args, **kwargs):
        self.source_read_phase.require_open()
        return self._service.get_entry_for_campaign(*args, **kwargs)

    def is_entry_enabled_for_campaign(self, *args, **kwargs):
        self.source_read_phase.require_open()
        return self._service.is_entry_enabled_for_campaign(*args, **kwargs)

    def list_campaign_source_states(self, *args, **kwargs):
        self.source_read_phase.require_open()
        return self._service.list_campaign_source_states(*args, **kwargs)

    def list_enabled_entries_for_campaign(self, *args, **kwargs):
        self.source_read_phase.require_open()
        return self._service.list_enabled_entries_for_campaign(*args, **kwargs)

    def list_entries_for_campaign_source(self, *args, **kwargs):
        self.source_read_phase.require_open()
        return self._service.list_entries_for_campaign_source(*args, **kwargs)

    def search_entries_for_campaign(self, *args, **kwargs):
        self.source_read_phase.require_open()
        return self._service.search_entries_for_campaign(*args, **kwargs)

def builder_source_reader(service):
    if isinstance(service, BuilderPhaseReader) or phase_of(service) is None:
        return service
    return BuilderPhaseReader(service)


# Closed builder interface used by private read preparation; unrelated benign
# class caches do not alter these specific capabilities.
_NATIVE_BUILDER_READ_CLASS = BuilderPhaseReader
_NATIVE_BUILDER_READ_MISSING = object()
_NATIVE_BUILDER_READ_BASES = BuilderPhaseReader.__bases__
_NATIVE_BUILDER_READ_RECIPE = {name: vars(BuilderPhaseReader).get(name, _NATIVE_BUILDER_READ_MISSING) for name in (
    "__init__", "__getattribute__", "_service", "source_read_phase",
    "get_durable_revision", "get_builder_static_revision", "get_cache_context",
    "list_enabled_entries_for_campaign", "get_entry_for_campaign",
    "get_entry_by_slug_for_campaign", "get_campaign_library", "get_campaign_library_slug",
    "list_campaign_source_states", "is_entry_enabled_for_campaign",
    "build_class_feature_progression_for_class_entry",
    "build_subclass_feature_progression_for_subclass_entry",
    "collect_attained_deterministic_feature_entries",
)}
