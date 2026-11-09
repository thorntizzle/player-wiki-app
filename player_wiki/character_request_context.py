"""Selected Character read lifetimes and detached common qualification.

This is request/phase-owned preparation, separate from the external-fact cache.
Presenters still run their own normalization, transient and numeric recipes.
"""
from contextlib import contextmanager
from dataclasses import fields
from datetime import datetime, date, time, timedelta, timezone
from pathlib import PurePosixPath, PureWindowsPath, PosixPath, WindowsPath

from .character_source_reads import SourceReadConflict, freeze, thaw


def _stock_provider(service, *, page_store=None):
    from .systems_service import ordinary_selected_character_service
    from .character_mechanics_projection import ordinary_qualified_prefix
    from .systems_store import ConnectionReadSystemsStore, ordinary_current_input_store
    if (not _ordinary_provider_declarations()
            or not ordinary_selected_character_service(service) or not ordinary_qualified_prefix()
            or not _ordinary_record_policy() or not _ordinary_page_repository(service, page_store)):
        return False
    # Identity-only existing stock-store admission; no facts/producer are read.
    return ordinary_current_input_store(ConnectionReadSystemsStore(service.store, None, object()))


@contextmanager
def selected_character_read_context(record, *, campaign, systems_service, page_store,
                                    enabled):
    """Choose fallback before entry; never replay a completed producer."""
    from .committed_publication import active
    from .db import get_db
    from .character_source_reads import SourceReadOwner, native_source_phase
    if (not enabled or get_db().in_transaction
            or not _stock_provider(systems_service, page_store=page_store)
            or not active()):
        yield systems_service, page_store
        return
    owner = SourceReadOwner.owned(get_db(), campaign.slug, record.definition.character_slug)
    try:
        with native_source_phase(owner, systems_service=systems_service, campaign=campaign,
                                 record=record, purpose="selected-character-read") as phase:
            if phase is None:
                yield systems_service, page_store
            else:
                phase._qualified_context = QualifiedCharacterContext(phase)
                yield phase.systems_view(), phase.page_store()
    finally:
        owner.close()


# These declarations are captured during ordinary app import, before extension
# configuration. Only this fixed freeze/thaw record family is admitted.
from ._native_read_policy import _capture_class_recipe, _class_recipe_matches
from . import character_models as _models, character_source_authority as _authority
from . import character_spell_grants as _grants, character_feature_composition as _composition
from . import campaign_page_store as _pages, models as _page_models
from . import repository_store as _repositories

_SELECTED_PAGE_STORE = _pages.CampaignPageStore
_SELECTED_REPOSITORY_STORE = _repositories.RepositoryStore
_SELECTED_PAGE_RECIPE = _capture_class_recipe(_SELECTED_PAGE_STORE,
    functions=("__init__",),
    inherited=("__new__", "__setattr__", "__getattribute__"),
    absent=("__getattr__",), getsets=("__dict__",))
_SELECTED_REPOSITORY_RECIPE = _capture_class_recipe(_SELECTED_REPOSITORY_STORE,
    functions=("__init__",),
    inherited=("__new__", "__setattr__", "__getattribute__"),
    absent=("__getattr__", "page_store", "campaigns_dir"), getsets=("__dict__",))
_SELECTED_PAGE_DECLARATIONS = tuple(type.__getattribute__(_SELECTED_PAGE_STORE, "__dict__").items())
_SELECTED_REPOSITORY_DECLARATIONS = tuple(type.__getattribute__(_SELECTED_REPOSITORY_STORE, "__dict__").items())
_SELECTED_PAGE_STATE = type.__getattribute__(_SELECTED_PAGE_STORE, "__dict__")["__dict__"]
_SELECTED_REPOSITORY_STATE = type.__getattribute__(_SELECTED_REPOSITORY_STORE, "__dict__")["__dict__"]
_SELECTED_OBJECT_PROTOCOLS = tuple(type.__getattribute__(object, "__dict__"))


def _ordinary_provider_declarations():
    # Complete raw snapshots of exactly these two stock classes. Staticmethods
    # remain unbound declarations; additions/removals also disable adoption.
    if (vars(_pages).get("CampaignPageStore") is not _SELECTED_PAGE_STORE
            or vars(_repositories).get("RepositoryStore") is not _SELECTED_REPOSITORY_STORE):
        return False
    for kind, recipe, expected in (
            (_SELECTED_PAGE_STORE, _SELECTED_PAGE_RECIPE, _SELECTED_PAGE_DECLARATIONS),
            (_SELECTED_REPOSITORY_STORE, _SELECTED_REPOSITORY_RECIPE, _SELECTED_REPOSITORY_DECLARATIONS)):
        if not _class_recipe_matches(recipe):
            return False
        namespace = type.__getattribute__(kind, "__dict__")
        if (len(namespace) != len(expected) or any(type(name) is not str for name in namespace)
                or any(name not in namespace or namespace[name] is not value
                       for name, value in expected)):
            return False
    return True


def _ordinary_page_repository(service, page_store):
    """Admit the exact supplied alias without calling replacement providers."""
    if (not _ordinary_provider_declarations() or type(page_store) is not _SELECTED_PAGE_STORE):
        return False
    # Service protocol/storage declarations have already been admitted above.
    repository = vars(service).get("repository_store")
    if type(repository) is not _SELECTED_REPOSITORY_STORE:
        return False
    page_state = _SELECTED_PAGE_STATE.__get__(page_store, _SELECTED_PAGE_STORE)
    repository_state = _SELECTED_REPOSITORY_STATE.__get__(repository, _SELECTED_REPOSITORY_STORE)
    if (type(page_state) is not dict or type(repository_state) is not dict
            or any(type(name) is not str for name in page_state)
            or any(type(name) is not str for name in repository_state)):
        return False
    if (any(name in page_state for name, _value in _SELECTED_PAGE_DECLARATIONS)
            or any(name in repository_state for name, _value in _SELECTED_REPOSITORY_DECLARATIONS)
            or any(name in page_state or name in repository_state for name in _SELECTED_OBJECT_PROTOCOLS)
            or repository_state.get("page_store") is not page_store
            or not any(type(repository_state.get("campaigns_dir")) is kind
                       for kind in (PosixPath, WindowsPath))):
        return False
    return _pages._native_page_mapping(page_store)

_QUALIFIED_RECORD_BINDINGS = (
    (_models, "CharacterDefinition"), (_authority, "SourceAuthority"),
    (_authority, "AuthorityGrant"), (_authority, "AuthorityStatus"),
    (_authority, "EffectiveStatus"), (_grants, "GrantView"),
    (_composition, "FeatureComposition"), (_pages, "CampaignPageRecord"),
    (_page_models, "Page"),
)
_QUALIFIED_RECORD_KINDS = tuple(vars(module)[name] for module, name in _QUALIFIED_RECORD_BINDINGS)
_QUALIFIED_RECORD_RECIPES = tuple(_capture_class_recipe(kind,
    functions=("__init__", "__setattr__", "__delattr__") if kind.__dataclass_params__.frozen else ("__init__",),
    inherited=("__new__", "__getattribute__") if kind.__dataclass_params__.frozen else
              ("__new__", "__getattribute__", "__setattr__", "__delattr__"),
    absent=("__getattr__", "__post_init__", "__dict__"), slots=True,
) for kind in _QUALIFIED_RECORD_KINDS)
_QUALIFIED_FIELD_DECLARATIONS = tuple((vars(kind)["__dataclass_fields__"],
    tuple((name, field, field.name, field.init, field._field_type)
          for name, field in vars(kind)["__dataclass_fields__"].items()))
    for kind in _QUALIFIED_RECORD_KINDS)


def _ordinary_record_policy():
    for (module, name), kind, recipe, (declaration, expected) in zip(
            _QUALIFIED_RECORD_BINDINGS, _QUALIFIED_RECORD_KINDS,
            _QUALIFIED_RECORD_RECIPES, _QUALIFIED_FIELD_DECLARATIONS):
        if (vars(module).get(name) is not kind or not _class_recipe_matches(recipe)
                or vars(kind).get("__dataclass_fields__") is not declaration
                or type(declaration) is not dict or len(declaration) != len(expected)):
            return False
        for (actual_name, actual_field), (key, field, field_name, init, field_type) in zip(
                declaration.items(), expected):
            if (actual_name is not key or actual_field is not field
                    or field.name is not field_name or field.init is not init
                    or field._field_type is not field_type):
                return False
    return True


def _record_kinds():
    return _QUALIFIED_RECORD_KINDS


def _detached_fact(value):
    """Admit only stock records/plain containers before established freeze/thaw."""
    if not _ordinary_record_policy():
        raise SourceReadConflict("Qualified record declarations changed.")
    allowed = _record_kinds()
    active = set()
    remaining = 32768

    def check(item, depth=0):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 64:
            raise SourceReadConflict("Qualified input exceeds its bounded representation.")
        kind = type(item)
        container = any(kind is candidate for candidate in (dict, list, tuple, set, frozenset))
        record = any(kind is candidate for candidate in allowed)
        if container or record:
            identity = id(item)
            if identity in active:
                raise SourceReadConflict("Cyclic qualified input is unsupported.")
            active.add(identity)
            try:
                if kind is dict:
                    for key, child in item.items():
                        check(key, depth + 1)
                        check(child, depth + 1)
                elif record:
                    for field in fields(item):
                        check(getattr(item, field.name), depth + 1)
                else:
                    for child in item:
                        check(child, depth + 1)
            finally:
                active.remove(identity)
        elif not any(kind is candidate for candidate in (
                type(None), str, bytes, bool, int, float, datetime, date, time,
                timedelta, timezone, PurePosixPath, PureWindowsPath, PosixPath, WindowsPath)):
            raise SourceReadConflict("Custom qualified values retain ordinary evaluation.")
        elif (kind is datetime or kind is time) and item.tzinfo is not None and type(item.tzinfo) is not timezone:
            raise SourceReadConflict("Custom qualified timezones retain ordinary evaluation.")
        # No custom copying or path-conversion protocol is invoked.

    check(value)
    return freeze(value)


class QualifiedCharacterContext:
    def __init__(self, phase):
        from .character_current_inputs import _actor
        from .character_source_reads import SourceReadPhase
        if (type(phase) is not SourceReadPhase or phase.owner._reserved
                or phase.purpose != "selected-character-read"):
            raise SourceReadConflict("Qualified Character context requires an owned selected read.")
        phase.require_open()
        self.phase = phase
        self.actor = _actor()
        self.basis = phase._basis
        self.cache = {}

    def close(self):
        self.cache.clear()
        self.actor = self.basis = self.phase = None

    def resolve(self, key, producer):
        from .character_current_inputs import _actor, _ordinary_recipes
        from .systems_service import ordinary_selected_character_phase
        from .character_mechanics_projection import ordinary_qualified_prefix
        phase = self.phase
        if phase is None:
            raise SourceReadConflict("Qualified Character context has closed.")
        phase.require_open()
        actor = _actor()
        if (self.actor is None or actor is None or len(actor) != len(self.actor)
                or any(a is not b for a, b in zip(actor[:-1], self.actor[:-1]))
                or actor[-1] != self.actor[-1] or phase._basis is not self.basis
                or phase._qualified_context is not self):
            raise SourceReadConflict("Qualified Character request ownership changed.")
        if (not ordinary_selected_character_phase(phase.systems_view())
                or not _ordinary_recipes() or not ordinary_qualified_prefix()
                or not _ordinary_record_policy()):
            return producer()
        try:
            identity = _detached_fact((key, phase.systems_view().get_cache_context(
                phase.owner.campaign_slug)))
        except (SourceReadConflict, TypeError, ValueError, RecursionError):
            return producer()
        if identity in self.cache:
            return thaw(self.cache[identity])
        result = producer()
        # An entered producer is never replayed on representation decline.
        try:
            from .character_source_authority import SourceAuthority
            if type(result) is not tuple or len(result) != 3:
                return result
            authority = result[2]
            if authority is not None and (type(authority) is not SourceAuthority
                    or authority.modifier_history_retention is not None):
                return result
            frozen = _detached_fact(result)
        except (SourceReadConflict, TypeError, ValueError, RecursionError):
            return result
        self.cache[identity] = frozen
        return result


def qualified_character_prefix(service, key, producer):
    from .systems_service import PhaseCharacterReadSystemsService
    # Legacy/custom/write contexts acquire no new provider capability probe.
    if type(service) is not PhaseCharacterReadSystemsService:
        return producer()
    phase = service.source_read_phase
    if phase.purpose != "selected-character-read":
        return producer()
    phase.require_open()
    if phase.systems_view() is not service:
        raise SourceReadConflict("Qualified Character reader belongs to another view.")
    context = phase._qualified_context
    return context.resolve(key, producer) if context is not None else producer()
