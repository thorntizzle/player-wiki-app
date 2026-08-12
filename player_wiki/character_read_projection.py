from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
import re
from threading import Event, RLock
from typing import Any, Callable
from weakref import WeakKeyDictionary

from .character_builder_constants import (
    BUILDER_PROGRESS_ENTRY_TYPES,
    BUILDER_STATIC_ENTRY_TYPES,
)
from .character_mechanics_projection import build_character_mechanics_projection
from .character_spell_slots import spell_slot_lanes_from_spellcasting
from .system_policy import is_dnd_5e_system


_CACHE_MAX_ENTRIES = 256
_PROJECTION_CACHE: OrderedDict[tuple[Any, ...], dict[str, Any]] = OrderedDict()
_PROJECTION_FLIGHTS: dict[tuple[Any, ...], "_ProjectionFlight"] = {}
_PROJECTION_CACHE_LOCK = RLock()
_SYSTEMS_SERVICE_CACHE_TOKENS: WeakKeyDictionary[Any, int] = WeakKeyDictionary()
_SYSTEMS_SERVICE_CACHE_TOKEN_COUNTER = 0


class _ProjectionFlight:
    def __init__(self) -> None:
        self.event = Event()
        self.value: dict[str, Any] | None = None
        self.error: BaseException | None = None


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(sorted((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    try:
        hash(value)
    except TypeError:
        return repr(value)
    return value


def _definition_digest(definition: Any) -> str:
    payload = definition.to_dict() if hasattr(definition, "to_dict") else definition
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _systems_service_cache_token(
    systems_service: Any,
) -> tuple[str, str, int] | None:
    global _SYSTEMS_SERVICE_CACHE_TOKEN_COUNTER
    with _PROJECTION_CACHE_LOCK:
        try:
            token = _SYSTEMS_SERVICE_CACHE_TOKENS.get(systems_service)
            if token is None:
                _SYSTEMS_SERVICE_CACHE_TOKEN_COUNTER += 1
                token = _SYSTEMS_SERVICE_CACHE_TOKEN_COUNTER
                _SYSTEMS_SERVICE_CACHE_TOKENS[systems_service] = token
        except TypeError:
            return None
    return (
        type(systems_service).__module__,
        type(systems_service).__qualname__,
        token,
    )


def _page_manifest_key(page_records: list[Any]) -> tuple[tuple[str, str, str], ...]:
    manifest: list[tuple[str, str, str]] = []
    for record in list(page_records or []):
        page_ref = str(getattr(record, "page_ref", "") or "").strip()
        if not page_ref:
            continue
        page = getattr(record, "page", None)
        metadata = dict(getattr(record, "metadata", None) or {})
        effective_metadata = {
            "route_slug": str(getattr(page, "route_slug", "") or "").strip(),
            "title": str(getattr(page, "title", "") or "").strip(),
            "section": str(getattr(page, "section", "") or "").strip(),
            "subsection": str(getattr(page, "subsection", "") or "").strip(),
            "page_type": str(getattr(page, "page_type", "") or "").strip(),
            "published": bool(getattr(page, "published", False)),
            "reveal_after_session": int(
                getattr(page, "reveal_after_session", 0) or 0
            ),
            "metadata": metadata,
        }
        metadata_json = json.dumps(
            effective_metadata,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        )
        manifest.append(
            (
                page_ref,
                str(getattr(record, "updated_at", "") or "").strip(),
                hashlib.sha256(metadata_json.encode("utf-8")).hexdigest(),
            )
        )
    return tuple(manifest)


_FORBIDDEN_PROJECTION_KEYS = frozenset(
    {
        "actor",
        "actor_id",
        "catalog",
        "catalogs",
        "href",
        "html",
        "record",
        "records",
        "session",
        "session_id",
        "url",
        "user",
        "user_id",
    }
)
_HTML_TAG_PATTERN = re.compile(r"</?[a-z][^>]*>", re.IGNORECASE)
_URL_VALUE_PATTERN = re.compile(r"(?:https?://|^/campaigns/)", re.IGNORECASE)


def _sanitize_projection_value(value: Any, *, path: str = "projection") -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if _HTML_TAG_PATTERN.search(value) or _URL_VALUE_PATTERN.search(value):
            raise TypeError(f"{path} contains rendered HTML or URL data.")
        return value
    if isinstance(value, list):
        return [
            _sanitize_projection_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                raise TypeError(f"{path} contains a non-string projection key.")
            normalized_key = raw_key.strip().casefold()
            if (
                normalized_key in _FORBIDDEN_PROJECTION_KEYS
                or normalized_key.endswith("_href")
                or normalized_key.endswith("_html")
                or normalized_key.endswith("_url")
            ):
                raise TypeError(
                    f"{path}.{raw_key} is not safe character-read projection metadata."
                )
            sanitized[raw_key] = _sanitize_projection_value(
                item,
                path=f"{path}.{raw_key}",
            )
        return sanitized
    raise TypeError(
        f"{path} contains unsupported cached value type {type(value).__name__}."
    )


def build_character_read_projection_cache_key(
    kind: str,
    *,
    campaign_slug: str,
    record: Any,
    systems_service: Any,
    campaign_page_records: list[Any],
    campaign_current_session: int,
    effective_visibility: Any,
) -> tuple[Any, ...] | None:
    revision_loader = getattr(systems_service, "get_builder_static_revision", None)
    if not callable(revision_loader):
        return None
    entry_types = tuple(
        sorted(set(BUILDER_STATIC_ENTRY_TYPES) | set(BUILDER_PROGRESS_ENTRY_TYPES))
    )
    systems_revision = revision_loader(campaign_slug, entry_types=entry_types)
    if systems_revision is None:
        return None
    systems_service_token = _systems_service_cache_token(systems_service)
    if systems_service_token is None:
        return None
    state_record = getattr(record, "state_record", None)
    return (
        "character-read-projection",
        str(kind or "").strip(),
        systems_service_token,
        str(campaign_slug or "").strip(),
        _definition_digest(getattr(record, "definition", None)),
        int(getattr(state_record, "revision", 0) or 0),
        int(campaign_current_session or 0),
        _freeze(effective_visibility),
        _page_manifest_key(campaign_page_records),
        _freeze(systems_revision),
    )


def reset_character_read_projection_cache_for_tests() -> None:
    """Deterministically clear the process cache between isolated tests."""

    global _SYSTEMS_SERVICE_CACHE_TOKEN_COUNTER
    with _PROJECTION_CACHE_LOCK:
        if _PROJECTION_FLIGHTS:
            raise RuntimeError(
                "Cannot reset the character-read projection cache during an active build."
            )
        _PROJECTION_CACHE.clear()
        _SYSTEMS_SERVICE_CACHE_TOKENS.clear()
        _SYSTEMS_SERVICE_CACHE_TOKEN_COUNTER = 0


def load_cached_character_read_projection(
    cache_key: tuple[Any, ...] | None,
    build_projection: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    if cache_key is None:
        return deepcopy(
            _sanitize_projection_value(dict(build_projection() or {}))
        )

    with _PROJECTION_CACHE_LOCK:
        cached = _PROJECTION_CACHE.get(cache_key)
        if cached is not None:
            _PROJECTION_CACHE.move_to_end(cache_key)
            return deepcopy(cached)
        flight = _PROJECTION_FLIGHTS.get(cache_key)
        is_builder = flight is None
        if flight is None:
            flight = _ProjectionFlight()
            _PROJECTION_FLIGHTS[cache_key] = flight

    if not is_builder:
        flight.event.wait()
        if flight.error is not None:
            raise flight.error
        return deepcopy(dict(flight.value or {}))

    try:
        value = _sanitize_projection_value(dict(build_projection() or {}))
    except BaseException as exc:
        with _PROJECTION_CACHE_LOCK:
            flight.error = exc
            if _PROJECTION_FLIGHTS.get(cache_key) is flight:
                _PROJECTION_FLIGHTS.pop(cache_key, None)
            flight.event.set()
        raise

    with _PROJECTION_CACHE_LOCK:
        flight.value = deepcopy(value)
        if _PROJECTION_FLIGHTS.get(cache_key) is flight:
            _PROJECTION_CACHE[cache_key] = deepcopy(value)
            _PROJECTION_CACHE.move_to_end(cache_key)
            while len(_PROJECTION_CACHE) > _CACHE_MAX_ENTRIES:
                _PROJECTION_CACHE.popitem(last=False)
            _PROJECTION_FLIGHTS.pop(cache_key, None)
        flight.event.set()
    return deepcopy(value)


def build_dnd_character_read_shell_projection(
    campaign: Any,
    record: Any,
    *,
    systems_service: Any,
    campaign_page_records: list[Any],
) -> dict[str, Any]:
    if not is_dnd_5e_system(getattr(record.definition, "system", "")):
        raise ValueError("The DND Character read shell projection requires a DND-5E character.")
    mechanics_projection = build_character_mechanics_projection(
        campaign=campaign,
        definition=record.definition,
        state=record.state_record.state or {},
        systems_service=systems_service,
        campaign_page_records=campaign_page_records,
        components=frozenset({"divine_avatar"}),
        catalog_components=frozenset(),
        derivation_components=frozenset(
            {
                "item_ability_minimums",
                "item_resource_bonuses",
                "item_spell_grants",
                "sheet_entries",
                "spellcasting",
            }
        ),
    )
    definition = mechanics_projection["definition"]
    state = dict(mechanics_projection.get("state") or {})
    spellcasting = dict(definition.spellcasting or {})
    has_feature_spell_manager = any(
        dict(feature or {}).get("spell_manager")
        for feature in list(definition.features or [])
    )
    death_saves = dict(dict(state.get("vitals") or {}).get("death_saves") or {})
    successes = int(death_saves.get("successes") or 0)
    failures = int(death_saves.get("failures") or 0)
    death_save_summary = None
    if successes or failures:
        death_save_summary = (
            f"{successes} success{'' if successes == 1 else 'es'}, "
            f"{failures} failure{'' if failures == 1 else 's'}"
        )
    return {
        "include_spellcasting": bool(
            spellcasting.get("spells")
            or spell_slot_lanes_from_spellcasting(spellcasting)
            or has_feature_spell_manager
        ),
        "death_save_summary": death_save_summary,
        "divine_avatar_forms_state": deepcopy(
            dict(mechanics_projection.get("divine_avatar_forms_state") or {})
        ),
    }
