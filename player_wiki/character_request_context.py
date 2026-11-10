"""Selected Character read lifetimes and detached common qualification.

This is request/phase-owned preparation, separate from the external-fact cache.
Presenters still run their own normalization, transient and numeric recipes.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import fields
from datetime import datetime, date, time, timedelta, timezone
from pathlib import PurePosixPath, PureWindowsPath, PosixPath, WindowsPath
from types import FunctionType, ModuleType

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
_QUALIFIED_CLASS_DECLARATIONS = tuple(tuple(vars(kind).items()) for kind in _QUALIFIED_RECORD_KINDS)
_QUALIFIED_FUNCTION_BODIES = tuple((function, function.__code__, function.__defaults__,
    function.__kwdefaults__, function.__closure__)
    for declarations in _QUALIFIED_CLASS_DECLARATIONS for _name, value in declarations
    for function in ((value,) if type(value) is FunctionType else
        (object.__getattribute__(value, "__func__"),) if type(value) is classmethod or type(value) is staticmethod else ())
    if type(function) is FunctionType)
_QUALIFIED_CLOSURE_BINDINGS = tuple((cell, cell.cell_contents)
    for function, *_rest in _QUALIFIED_FUNCTION_BODIES
    for cell in (function.__closure__ or ()))


def _plain_recipe(value):
    remaining = 4096
    active = set()
    def visit(item, depth=0):
        nonlocal remaining
        remaining -= 1
        kind = type(item)
        if remaining < 0 or depth > 32:
            raise ValueError("Unbounded callback defaults")
        if any(kind is atom for atom in (type(None), str, bytes, bool, int)):
            return (kind, item)
        if kind is float:
            return (kind, item.hex())
        if kind is not tuple and kind is not list and kind is not dict:
            raise ValueError("Custom callback defaults")
        identity = id(item)
        if identity in active:
            raise ValueError("Cyclic callback defaults")
        active.add(identity)
        try:
            return (kind, tuple((visit(k, depth+1), visit(v, depth+1)) for k, v in item.items())
                    if kind is dict else tuple(visit(v, depth+1) for v in item))
        finally:
            active.remove(identity)
    return visit(value)


def _capture_qualification_bodies():
    # The same closed callback family already owned by the qualifier, captured
    # at module import rather than blessed again at a later request.
    from . import character_builder as builder, character_reconstruction_authority as reconstruction
    from . import character_reconstruction_proficiencies as proficiencies, character_reconstruction_instruments as instruments
    from . import character_ability_inputs as abilities, character_profile as profile
    from . import character_source_authority as authority, character_builder_equipment as equipment
    from . import character_read_foundation as foundation, character_feature_proficiency_grants as grants
    from . import character_skill_adoptions as skills, character_language_electives as languages
    from . import character_mechanics_projection as projection, character_source_repair as history
    rows = []
    for module, recipe_name in tuple((module, "_CURRENT_INPUT_RECIPE") for module in (
            builder, reconstruction, proficiencies, instruments, abilities, profile, authority,
            equipment, foundation, grants, skills, languages)) + (
            (projection, "_QUALIFIED_PREFIX_RECIPE"), (history, None)):
        recipe = (tuple((name, vars(history)[name]) for name in (
            "load_verified_manual_actions", "load_verified_numeric_actions"))
            if recipe_name is None else vars(module)[recipe_name])
        for name, value in recipe:
            if type(value) is FunctionType:
                rows.append((module, name, value, value.__code__, value.__defaults__,
                             value.__kwdefaults__, value.__closure__))
    return tuple(rows)


_QUALIFICATION_BODIES = _capture_qualification_bodies()
_QUALIFICATION_DEFAULTS = tuple(_plain_recipe((function.__defaults__, function.__kwdefaults__,
    tuple(cell.cell_contents for cell in function.__closure__) if function.__closure__ else None))
    for _module, _name, function, *_rest in _QUALIFICATION_BODIES)
_QUALIFICATION_MODULES = tuple({id(row[0]): row[0] for row in _QUALIFICATION_BODIES}.values())


def _ordinary_qualification_bodies():
    if any(type(module) is not ModuleType or any(type(key) is not str for key in vars(module))
           for module in _QUALIFICATION_MODULES):
        return False
    if not all(vars(module).get(name) is function and function.__code__ is code
        and function.__defaults__ is defaults and function.__kwdefaults__ is keywords
        and function.__closure__ is closure
        for module, name, function, code, defaults, keywords, closure in _QUALIFICATION_BODIES):
        return False
    try:
        return all(_plain_recipe((function.__defaults__, function.__kwdefaults__,
            tuple(cell.cell_contents for cell in function.__closure__) if function.__closure__ else None)) == expected
            for (_module, _name, function, *_rest), expected in zip(_QUALIFICATION_BODIES, _QUALIFICATION_DEFAULTS))
    except (TypeError, ValueError, RecursionError):
        return False


def _ordinary_record_policy():
    for kind, declarations in zip(_QUALIFIED_RECORD_KINDS, _QUALIFIED_CLASS_DECLARATIONS):
        namespace = type.__getattribute__(kind, "__dict__")
        # copyreg lazily publishes its native slot-name list on slotted classes.
        # It is bookkeeping, with exactly the already-admitted slot vocabulary.
        slotnames = namespace.get("__slotnames__")
        extra = "__slotnames__" in namespace and not any(name == "__slotnames__" for name, _ in declarations)
        if (extra and (type(slotnames) is not list
                or any(type(name) is not str for name in slotnames)
                or tuple(slotnames) != namespace.get("__slots__"))):
            return False
        if (len(namespace) != len(declarations) + int(extra) or any(type(name) is not str for name in namespace)
                or any(namespace.get(name) is not value for name, value in declarations)):
            return False
    if any(function.__code__ is not code or function.__defaults__ is not defaults
           or function.__kwdefaults__ is not keywords or function.__closure__ is not closure
           for function, code, defaults, keywords, closure in _QUALIFIED_FUNCTION_BODIES):
        return False
    if any(cell.cell_contents is not expected for cell, expected in _QUALIFIED_CLOSURE_BINDINGS):
        return False
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
        ordinary_state = (phase.purpose == "ordinary-state-action"
                          and getattr(phase.owner, "_state_action", False))
        if (type(phase) is not SourceReadPhase
                or (phase.owner._reserved and not ordinary_state)
                or phase.purpose not in {"selected-character-read", "ordinary-state-action"}):
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
                or not _ordinary_qualification_bodies()
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
    if phase.purpose not in {"selected-character-read", "ordinary-state-action"}:
        return producer()
    phase.require_open()
    if phase.systems_view() is not service:
        raise SourceReadConflict("Qualified Character reader belongs to another view.")
    context = phase._qualified_context
    return context.resolve(key, producer) if context is not None else producer()


_STATE_ACTION = ContextVar("character_state_observation", default=None)


class _StateActionObservation:
    """Lazy, original-record authority within one captured state reservation.

    The app's ordinary provider still performs its current-record checks and
    numeric projection on every call. Equivalent qualification is shared by
    the existing admitted prefix context. No positive
    fact survives the first store write or an exceptional action exit.
    """

    def __init__(self, service, record):
        from threading import get_ident
        self.service, self.record = service, record
        self.service_id = id(service)
        self.thread = get_ident()
        self.owner = self.phase = self.scope = None
        self.key = self.actor = self.policy = self.authority = None
        self.provider = None
        self.entered = False
        self.declined = self.closed = False

    def resolve(self, record, *, campaign, systems_service, page_store, producer):
        from threading import get_ident
        from .character_current_inputs import _actor, _ordinary_recipes
        from .character_source_reads import SourceReadOwner, SourceReadUnavailable
        from .db import get_db
        if self.closed or self.thread != get_ident():
            raise SourceReadConflict("State observation ownership has ended.")
        if self.declined:
            return producer(None)
        actor = _actor()
        native = (actor is not None and _ordinary_recipes() and _ordinary_qualification_bodies()
                  and _stock_provider(systems_service, page_store=page_store))
        if self.phase is None and not native:
            self.declined = True
            return producer(None)
        if not native:
            raise SourceReadConflict("State source provider changed during the action.")
        try:
            key = _detached_fact((record.definition, record.state_record.state,
                                  record.state_record.revision, record.committed_revision))
            original = _detached_fact((self.record.definition, self.record.state_record.state,
                                       self.record.state_record.revision, self.record.committed_revision))
        except (SourceReadConflict, TypeError, ValueError, RecursionError):
            if self.phase is not None:
                raise SourceReadConflict("State original record representation changed.")
            self.declined = True
            return producer(None)
        if key != original:
            raise SourceReadConflict("State observation received another original record.")
        if self.phase is None:
            self.owner = SourceReadOwner._after_state_action_reserve(
                get_db(), record.definition.campaign_slug, record.definition.character_slug)
            self.scope = self.owner.open_phase("ordinary-state-action", systems_service=systems_service,
                                               campaign=campaign, record=record)
            try:
                self.phase = self.scope.__enter__()
                self.entered = True
            except SourceReadUnavailable:
                # Construction declined before any numeric producer entered.
                # The caller's writer reservation remains owned and untouched.
                self.owner.close()
                self.owner = self.scope = None
                self.declined = True
                return producer(None)
            self.phase._qualified_context = QualifiedCharacterContext(self.phase)
            self.actor, self.key = actor, key
            self.policy = systems_service, page_store
            self.provider = vars(self.service).get("authority_provider")
        else:
            self.phase.require_open()
            if (key != self.key or any(a is not b for a, b in zip(self.actor[:-1], actor[:-1]))
                    or self.actor[-1] != actor[-1]
                    or systems_service is not self.policy[0] or page_store is not self.policy[1]):
                raise SourceReadConflict("State observation inputs or actor changed.")
            # Fresh uncached basis, complete history and Systems readset under
            # the still-held writer reservation, before consuming a prior result.
            self.phase._fresh_guard(self.phase._basis, tuple(self.phase._readset.values()))
        # Each original full numeric producer still runs once. Its normalization,
        # transient effects and proposed-state consumer are separate recipes;
        # only the explicitly admitted common qualification prefix may reuse.
        return producer(self.phase)

    def _check_final_bindings(self):
        from threading import get_ident
        from flask import current_app
        from .character_current_inputs import _actor, _ordinary_recipes
        actor = _actor()
        extensions = current_app.extensions
        if (self.thread != get_ident() or actor is None
                or len(actor) != len(self.actor)
                or any(a is not b for a, b in zip(actor[:-1], self.actor[:-1]))
                or actor[-1] != self.actor[-1]
                or vars(self.service).get("authority_provider") is not self.provider
                or extensions.get("systems_service") is not self.policy[0]
                or extensions.get("campaign_page_store") is not self.policy[1]
                or not _ordinary_recipes()
                or not _ordinary_qualification_bodies()
                or not _stock_provider(self.policy[0], page_store=self.policy[1])
                or _detached_fact((self.record.definition, self.record.state_record.state,
                    self.record.state_record.revision, self.record.committed_revision)) != self.key):
            raise SourceReadConflict("State observation ownership or recipe changed before saving.")

    def close(self, *exc, _before_write=False):
        if self.closed:
            return
        self.closed = True
        try:
            if self.scope is not None and self.phase is not None:
                if _before_write:
                    try:
                        self._check_final_bindings()
                    except BaseException:
                        import sys
                        self.scope.__exit__(*sys.exc_info())
                        raise
                self.scope.__exit__(*(exc or (None, None, None)))
                if _before_write:
                    self._check_final_bindings()
                    self.owner.before_state_write()
        finally:
            if self.owner is not None:
                self.owner.close()
            self.authority = self.actor = self.key = self.policy = None
            self.phase = self.scope = self.record = self.service = None
            self.provider = None

    def before_write(self):
        # Finish invalidates every live cache and performs the final raw guard.
        # No caller-owned transaction is committed or rolled back here.
        self.close(_before_write=True)


@contextmanager
def ordinary_state_action_observation(service, record, *, enabled):
    import sys
    observation = _StateActionObservation(service, record) if enabled else None
    token = _STATE_ACTION.set(observation)
    try:
        yield
    except BaseException as error:
        if observation is not None:
            observation.close(*sys.exc_info())
        if observation is not None and observation.entered and isinstance(error, SourceReadConflict):
            from .character_store import CharacterStateConflictError
            raise CharacterStateConflictError(str(error)) from error
        raise
    else:
        if observation is not None:
            observation.close()
    finally:
        _STATE_ACTION.reset(token)


def has_state_action_observation(service):
    observation = _STATE_ACTION.get()
    return observation is not None and observation.service_id == id(service)


def state_action_authority(service, record, *, campaign, systems_service, page_store, producer):
    observation = _STATE_ACTION.get()
    if observation is not None and observation.closed and observation.service_id == id(service):
        raise SourceReadConflict("State observation already crossed its write boundary.")
    if observation is None or observation.service is not service:
        return producer(None)
    return observation.resolve(record, campaign=campaign, systems_service=systems_service,
                               page_store=page_store, producer=producer)


def before_state_observation_write(service):
    observation = _STATE_ACTION.get()
    if observation is not None and observation.service is service:
        observation.before_write()
