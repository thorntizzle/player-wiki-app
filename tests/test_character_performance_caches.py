from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event, Lock
from types import SimpleNamespace
from typing import Any, Callable

import pytest
from flask import Flask, g

import player_wiki.character_builder as builder_module
import player_wiki.character_builder_catalogs as catalog_module
import player_wiki.character_builder_derivation as derivation_module
import player_wiki.character_builder_foundation as foundation_module
import player_wiki.character_builder_progression as progression_module
from player_wiki import character_mechanics_projection as projection_module
from player_wiki.character_builder_catalogs import (
    _builder_normalization_page_key,
    _builder_progress_cache_get,
    _builder_static_cache_get,
    _clear_builder_static_bundle_cache,
)
from player_wiki.character_builder_constants import BUILDER_STATIC_ENTRY_TYPES
from player_wiki.character_mechanics_projection import (
    NORMALIZATION_SYSTEMS_ENTRY_TYPES,
    _clear_normalized_definition_cache,
    build_character_mechanics_projection,
)
from player_wiki.character_models import CharacterDefinition
from player_wiki.models import Campaign
from player_wiki.systems_models import SystemsEntryRecord
from player_wiki.systems_service import SystemsService, _systems_service_cache_clear
from tests.helpers.character_builder_fakes import _systems_entry


@pytest.fixture(autouse=True)
def _clear_process_caches_between_tests():
    _clear_builder_static_bundle_cache()
    _clear_normalized_definition_cache()
    yield
    _clear_builder_static_bundle_cache()
    _clear_normalized_definition_cache()


def _campaign() -> Campaign:
    return Campaign(
        title="Linden Pass",
        slug="linden-pass",
        summary="",
        system="DND-5E",
        current_session=1,
        source_wiki_root="",
        player_content_dir="",
        assets_dir="",
    )


def _definition(**overrides: Any) -> CharacterDefinition:
    payload = {
        "campaign_slug": "linden-pass",
        "character_slug": "cache-test",
        "name": "Cache Test",
        "status": "active",
        "profile": {},
        "stats": {"max_hp": 20},
        "skills": [],
        "proficiencies": {},
        "attacks": [],
        "features": [],
        "spellcasting": {},
        "equipment_catalog": [],
        "reference_notes": {},
        "resource_templates": [],
        "source": {},
    }
    payload.update(overrides)
    return CharacterDefinition.from_dict(payload)


def _test_systems_ref(entry: SystemsEntryRecord) -> dict[str, str]:
    return {
        "entry_key": str(entry.entry_key or ""),
        "entry_type": str(entry.entry_type or ""),
        "slug": str(entry.slug or ""),
        "title": str(entry.title or ""),
        "source_id": str(entry.source_id or ""),
    }


def _install_prepared_spellcasting_static_bundle(
    monkeypatch,
    *,
    class_entries: list[SystemsEntryRecord],
    subclass_entries: list[SystemsEntryRecord] | None = None,
) -> dict[str, Any]:
    static_bundle = {
        "supported_class_entries": list(class_entries),
        "subclass_entries": list(subclass_entries or []),
        "species_options": [],
        "background_options": [],
        "item_catalog": builder_module._build_item_catalog([]),
        "spell_catalog": builder_module._build_spell_catalog([]),
    }
    monkeypatch.setattr(
        builder_module,
        "_build_common_builder_static_bundle",
        lambda *_args, **_kwargs: static_bundle,
    )
    monkeypatch.setattr(
        builder_module,
        "_prepare_automatic_prepared_spell_lookup_keys",
        lambda **_kwargs: {},
    )
    return static_bundle


def _page_record(
    page_ref: str,
    section: str,
    updated_at: str,
    *,
    title: str = "Cache Page",
    subsection: str = "",
    summary: str = "",
    metadata: dict[str, Any] | None = None,
    body_markdown: str = "",
    content_loaded: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        page_ref=page_ref,
        updated_at=updated_at,
        metadata=dict(metadata or {}),
        body_markdown=body_markdown,
        page=SimpleNamespace(
            route_slug=page_ref,
            title=title,
            summary=summary,
            section=section,
            subsection=subsection,
            page_type="item" if section == "Items" else "mechanic",
            published=True,
            reveal_after_session=0,
            content_loaded=content_loaded,
        ),
    )


class _RevisionSystemsService:
    def __init__(self) -> None:
        self.revision = "systems-v1"
        self.revision_calls = 0
        self.revision_entry_types_calls: list[tuple[str, ...]] = []

    def get_builder_static_revision(
        self,
        campaign_slug: str,
        *,
        entry_types: tuple[str, ...],
    ) -> tuple[object, ...]:
        self.revision_calls += 1
        self.revision_entry_types_calls.append(tuple(entry_types))
        return (campaign_slug, self.revision, tuple(entry_types))


def _project(
    definition: CharacterDefinition,
    service: _RevisionSystemsService,
    pages: list[object],
    *,
    current_hp: int = 7,
):
    return build_character_mechanics_projection(
        campaign=_campaign(),
        definition=definition,
        state={"vitals": {"current_hp": current_hp, "temp_hp": 0}},
        systems_service=service,
        campaign_page_records=pages,
    )


def _project_scoped(
    definition: CharacterDefinition,
    service: _RevisionSystemsService,
    pages: list[object],
    *,
    current_hp: int = 7,
    components: frozenset[str] = frozenset({"divine_avatar"}),
    catalog_components: frozenset[str] = frozenset(),
    derivation_components: frozenset[str] = frozenset({"item_ability_minimums"}),
):
    return build_character_mechanics_projection(
        campaign=_campaign(),
        definition=definition,
        state={"vitals": {"current_hp": current_hp, "temp_hp": 0}},
        systems_service=service,
        campaign_page_records=pages,
        components=components,
        catalog_components=catalog_components,
        derivation_components=derivation_components,
    )


@pytest.mark.parametrize(
    ("cache_get", "expected"),
    (
        (_builder_static_cache_get, {"value": "built"}),
        (_builder_progress_cache_get, [{"value": "built"}]),
    ),
)
def test_builder_process_caches_single_flight_identical_cold_keys(
    cache_get: Callable[..., Any],
    expected: Any,
):
    callers_ready = Barrier(4)
    build_started = Event()
    release_build = Event()
    build_lock = Lock()
    build_count = 0

    def build_value():
        nonlocal build_count
        with build_lock:
            build_count += 1
        build_started.set()
        assert release_build.wait(timeout=2)
        return expected

    def call_cache():
        callers_ready.wait(timeout=2)
        return cache_get(("same-key",), build_value)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(call_cache) for _ in range(4)]
        assert build_started.wait(timeout=2)
        release_build.set()
        results = [future.result(timeout=2) for future in futures]

    assert results == [expected] * 4
    assert build_count == 1


def test_builder_process_cache_allows_different_keys_to_build_concurrently():
    both_builders_entered = Barrier(2)

    def build_value(value: str) -> dict[str, str]:
        both_builders_entered.wait(timeout=2)
        return {"value": value}

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            _builder_static_cache_get,
            ("first-key",),
            lambda: build_value("first"),
        )
        second = executor.submit(
            _builder_static_cache_get,
            ("second-key",),
            lambda: build_value("second"),
        )
        assert first.result(timeout=2) == {"value": "first"}
        assert second.result(timeout=2) == {"value": "second"}


@pytest.mark.parametrize(
    ("cache_get", "success_value"),
    (
        (_builder_static_cache_get, {"value": "recovered"}),
        (_builder_progress_cache_get, [{"value": "recovered"}]),
    ),
)
def test_builder_process_cache_failure_wakes_waiters_and_retry_succeeds(
    cache_get: Callable[..., Any],
    success_value: Any,
):
    callers_ready = Barrier(4)
    build_started = Event()
    release_failure = Event()
    build_count = 0
    build_lock = Lock()

    def failing_build():
        nonlocal build_count
        with build_lock:
            build_count += 1
        build_started.set()
        assert release_failure.wait(timeout=2)
        raise RuntimeError("cold build failed")

    def call_cache():
        callers_ready.wait(timeout=2)
        return cache_get(("failing-key",), failing_build)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(call_cache) for _ in range(4)]
        assert build_started.wait(timeout=2)
        release_failure.set()
        for future in futures:
            with pytest.raises(RuntimeError, match="cold build failed"):
                future.result(timeout=2)

    assert build_count == 1
    assert cache_get(("failing-key",), lambda: success_value) == success_value


def test_builder_cache_clear_generation_rejects_stale_inflight_repopulation():
    old_started = Event()
    release_old = Event()

    def old_build():
        old_started.set()
        assert release_old.wait(timeout=2)
        return {"value": "old"}

    with ThreadPoolExecutor(max_workers=1) as executor:
        old_future = executor.submit(_builder_static_cache_get, ("clear-key",), old_build)
        assert old_started.wait(timeout=2)
        _clear_builder_static_bundle_cache()
        assert _builder_static_cache_get(
            ("clear-key",), lambda: {"value": "new"}
        ) == {"value": "new"}
        release_old.set()
        assert old_future.result(timeout=2) == {"value": "old"}

    assert _builder_static_cache_get(
        ("clear-key",), lambda: pytest.fail("stale value repopulated cache")
    ) == {"value": "new"}


def test_normalized_definition_cache_keys_revisions_and_returns_detached_values(monkeypatch):
    service = _RevisionSystemsService()
    definition = _definition()
    mechanics = _page_record("mechanics/cache-rule", "Mechanics", "2026-07-20T12:00:00Z")
    item = _page_record("items/cache-item", "Items", "2026-07-20T12:00:00Z")
    lore = _page_record("lore/unrelated", "Lore", "2026-07-20T12:00:00Z")
    normalize_calls = []

    def fake_normalize(raw_definition, *, systems_service=None, campaign_page_records=None):
        del systems_service
        normalize_calls.append([record.page_ref for record in campaign_page_records or []])
        return CharacterDefinition.from_dict(raw_definition.to_dict())

    monkeypatch.setattr(projection_module, "normalize_definition_to_native_model", fake_normalize)

    first = _project(definition, service, [mechanics, item, lore], current_hp=3)
    first["definition"].stats["max_hp"] = 999
    lore.updated_at = "2026-07-20T12:05:00Z"
    second = _project(definition, service, [mechanics, item, lore], current_hp=4)
    assert second["definition"].stats["max_hp"] == 20
    assert second["state"]["vitals"]["current_hp"] == 4
    assert normalize_calls == [["mechanics/cache-rule", "items/cache-item"]]

    mechanics.updated_at = "2026-07-20T12:06:00Z"
    _project(definition, service, [mechanics, item, lore])
    item.updated_at = "2026-07-20T12:07:00Z"
    _project(definition, service, [mechanics, item, lore])
    service.revision = "systems-v2"
    _project(definition, service, [mechanics, item, lore])
    _project(_definition(stats={"max_hp": 21}), service, [mechanics, item, lore])
    assert len(normalize_calls) == 5


def test_full_normalization_preserves_static_revision_recipe_while_scoped_uses_union(
    monkeypatch,
):
    service = _RevisionSystemsService()
    definition = _definition()
    pages = [_page_record("mechanics/cache-rule", "Mechanics", "2026-08-11T12:00:00Z")]
    monkeypatch.setattr(
        projection_module,
        "normalize_definition_to_native_model",
        lambda raw_definition, **_kwargs: CharacterDefinition.from_dict(
            raw_definition.to_dict()
        ),
    )

    _project(definition, service, pages)
    _project_scoped(
        definition,
        service,
        pages,
        components=frozenset(),
        derivation_components=frozenset({"sheet_entries"}),
    )

    assert service.revision_entry_types_calls == [
        tuple(sorted(BUILDER_STATIC_ENTRY_TYPES)),
        NORMALIZATION_SYSTEMS_ENTRY_TYPES,
    ]


def test_scoped_normalization_churn_does_not_evict_warmed_full_definition(
    monkeypatch,
):
    service = _RevisionSystemsService()
    pages = [_page_record("mechanics/cache-rule", "Mechanics", "2026-08-11T12:00:00Z")]
    normalize_recipes: list[str] = []

    def fake_normalize(raw_definition, **kwargs):
        normalize_recipes.append(
            "scoped" if "derivation_components" in kwargs else "full"
        )
        return CharacterDefinition.from_dict(raw_definition.to_dict())

    monkeypatch.setattr(
        projection_module,
        "normalize_definition_to_native_model",
        fake_normalize,
    )

    full_definition = _definition(character_slug="full-cache-anchor")
    _project(full_definition, service, pages)
    for index in range(13):
        _project_scoped(
            _definition(character_slug=f"scoped-cache-churn-{index}"),
            service,
            pages,
            components=frozenset(),
            derivation_components=frozenset({"sheet_entries"}),
        )

    _project(full_definition, service, pages)

    assert normalize_recipes.count("full") == 1
    assert normalize_recipes.count("scoped") == 13


def test_warm_scoped_decode_does_not_hold_lock_against_unrelated_full_hit(
    monkeypatch,
):
    service = _RevisionSystemsService()
    pages = [_page_record("mechanics/cache-rule", "Mechanics", "2026-08-11T12:00:00Z")]
    full_definition = _definition(
        character_slug="full-decode",
        stats={"max_hp": 31},
    )
    scoped_definition = _definition(
        character_slug="scoped-decode",
        stats={"max_hp": 47},
    )
    monkeypatch.setattr(
        projection_module,
        "normalize_definition_to_native_model",
        lambda raw_definition, **_kwargs: CharacterDefinition.from_dict(
            raw_definition.to_dict()
        ),
    )

    _project(full_definition, service, pages)
    _project_scoped(
        scoped_definition,
        service,
        pages,
        components=frozenset(),
        derivation_components=frozenset({"sheet_entries"}),
    )

    scoped_decode_started = Event()
    release_scoped_decode = Event()
    original_loads = projection_module.json.loads

    def stalled_scoped_loads(payload, *args, **kwargs):
        if '"max_hp":47' in payload:
            scoped_decode_started.set()
            assert release_scoped_decode.wait(timeout=2)
        return original_loads(payload, *args, **kwargs)

    monkeypatch.setattr(projection_module.json, "loads", stalled_scoped_loads)

    with ThreadPoolExecutor(max_workers=2) as executor:
        scoped_future = executor.submit(
            _project_scoped,
            scoped_definition,
            service,
            pages,
            components=frozenset(),
            derivation_components=frozenset({"sheet_entries"}),
        )
        assert scoped_decode_started.wait(timeout=2)
        full_future = executor.submit(_project, full_definition, service, pages)
        try:
            assert full_future.result(timeout=0.5)["definition"].stats["max_hp"] == 31
        finally:
            release_scoped_decode.set()
        assert scoped_future.result(timeout=2)["definition"].stats["max_hp"] == 47


def test_scoped_normalized_definition_cache_warm_hit_defers_catalogs_and_keeps_state_fresh(
    monkeypatch,
):
    service = _RevisionSystemsService()
    definition = _definition(
        equipment_catalog=[
            {
                "id": "cache-item",
                "name": "Cache Item",
                "default_quantity": 1,
                "is_equipped": True,
            }
        ]
    )
    page = _page_record(
        "items/cache-item",
        "Items",
        "2026-08-11T12:00:00Z",
        title="Cache Item",
        body_markdown="Cache item body.",
        content_loaded=True,
    )
    normalize_calls = 0
    catalog_calls = 0

    def fake_catalog(*_args, **_kwargs):
        nonlocal catalog_calls
        catalog_calls += 1
        return projection_module._build_item_catalog([])

    def fake_normalize(raw_definition, **_kwargs):
        nonlocal normalize_calls
        normalize_calls += 1
        return CharacterDefinition.from_dict(raw_definition.to_dict())

    monkeypatch.setattr(
        projection_module,
        "_build_targeted_item_support_catalog",
        fake_catalog,
    )
    monkeypatch.setattr(
        projection_module,
        "normalize_definition_to_native_model",
        fake_normalize,
    )

    app = Flask(__name__)
    with app.test_request_context("/characters/cache-test"):
        first = _project_scoped(
            definition,
            service,
            [page],
            current_hp=3,
            components=frozenset({"attacks"}),
        )
        first["definition"].stats["max_hp"] = 999
        second = _project_scoped(
            definition,
            service,
            [page],
            current_hp=4,
            components=frozenset({"attacks"}),
        )

    assert normalize_calls == 1
    assert catalog_calls == 1
    assert service.revision_calls == 1
    assert second["definition"].stats["max_hp"] == 20
    assert second["state"]["vitals"]["current_hp"] == 4


def test_scoped_normalized_definition_cache_separates_exact_projection_recipes(monkeypatch):
    service = _RevisionSystemsService()
    definition = _definition(
        equipment_catalog=[
            {
                "id": "cache-item",
                "name": "Cache Item",
                "default_quantity": 1,
                "is_equipped": False,
            }
        ]
    )
    pages = [_page_record("items/cache-item", "Items", "2026-08-11T12:00:00Z")]
    normalize_recipes: list[tuple[tuple[str, ...], bool, bool]] = []
    targeted_modes: list[bool] = []

    def fake_normalize(raw_definition, **kwargs):
        normalize_recipes.append(
            (
                tuple(sorted(kwargs.get("derivation_components") or ())),
                bool(dict(kwargs.get("item_catalog") or {}).get("recipe_item_full")),
                bool(dict(kwargs.get("spell_catalog") or {}).get("recipe_spell_full")),
            )
        )
        return CharacterDefinition.from_dict(raw_definition.to_dict())

    monkeypatch.setattr(
        projection_module,
        "normalize_definition_to_native_model",
        fake_normalize,
    )
    def fake_targeted_catalog(*_args, **kwargs):
        targeted_modes.append(bool(kwargs["include_inactive"]))
        return {"targeted_include_inactive": kwargs["include_inactive"]}

    monkeypatch.setattr(
        projection_module,
        "_build_targeted_item_support_catalog",
        fake_targeted_catalog,
    )
    monkeypatch.setattr(
        projection_module,
        "_build_scoped_item_catalog",
        lambda *_args, **_kwargs: {"recipe_item_full": True},
    )
    monkeypatch.setattr(
        projection_module,
        "_build_scoped_spell_catalog",
        lambda *_args, **_kwargs: {"recipe_spell_full": True},
    )

    variants = (
        # Targeted active and targeted all must never collide.
        (frozenset({"divine_avatar"}), frozenset(), frozenset({"item_ability_minimums"})),
        (frozenset({"attacks"}), frozenset(), frozenset({"item_ability_minimums"})),
        # Full item and full spell catalog recipes are distinct from targeted/empty recipes.
        (frozenset(), frozenset({"items"}), frozenset({"sheet_entries"})),
        (frozenset(), frozenset({"spells"}), frozenset({"sheet_entries"})),
        # Derivation recipes remain exact even with the same component/catalog recipe.
        (frozenset(), frozenset(), frozenset({"sheet_entries"})),
        (frozenset(), frozenset(), frozenset({"spellcasting_math"})),
    )
    for components, catalogs, derivation in variants:
        _project_scoped(
            definition,
            service,
            pages,
            components=components,
            catalog_components=catalogs,
            derivation_components=derivation,
        )
    for components, catalogs, derivation in variants:
        _project_scoped(
            definition,
            service,
            pages,
            components=components,
            catalog_components=catalogs,
            derivation_components=derivation,
        )

    assert len(normalize_recipes) == len(variants)
    assert targeted_modes == [False, True]


def test_scoped_normalized_definition_cache_keys_exact_page_materialization(monkeypatch):
    service = _RevisionSystemsService()
    definition = _definition()
    normalize_calls = 0

    def fake_normalize(raw_definition, **_kwargs):
        nonlocal normalize_calls
        normalize_calls += 1
        return CharacterDefinition.from_dict(raw_definition.to_dict())

    monkeypatch.setattr(
        projection_module,
        "normalize_definition_to_native_model",
        fake_normalize,
    )

    metadata_only = _page_record(
        "items/cache-item",
        "Items",
        "2026-08-11T12:00:00Z",
        title="Cache Item",
        metadata={"item_mechanics": {"status": "approved"}},
    )
    loaded = _page_record(
        "items/cache-item",
        "Items",
        "2026-08-11T12:00:00Z",
        title="Cache Item",
        metadata={"item_mechanics": {"status": "approved"}},
        body_markdown="First body.",
        content_loaded=True,
    )
    changed_body = deepcopy(loaded)
    changed_body.body_markdown = "Second body."
    changed_metadata = deepcopy(changed_body)
    changed_metadata.metadata = {
        "item_mechanics": {"status": "approved", "bonus_weapon": 1}
    }
    changed_visibility = deepcopy(changed_metadata)
    changed_visibility.page.published = False
    changed_update = deepcopy(changed_visibility)
    changed_update.updated_at = "2026-08-11T12:01:00Z"

    for page in (
        metadata_only,
        loaded,
        changed_body,
        changed_metadata,
        changed_visibility,
        changed_update,
        deepcopy(changed_update),
    ):
        _project_scoped(
            definition,
            service,
            [page],
            components=frozenset(),
            derivation_components=frozenset({"sheet_entries"}),
        )

    assert normalize_calls == 6


def test_scoped_normalized_definition_cache_invalidates_changed_page_summary(
    monkeypatch,
):
    service = _RevisionSystemsService()
    page_record = _page_record(
        "mechanics/cache-species",
        "Mechanics",
        "2026-08-11T12:00:00Z",
        title="Cache Species",
        summary="First summary.",
    )

    normalize_calls: list[str] = []

    def normalize_with_page_summary(raw_definition, **kwargs):
        page = kwargs["campaign_page_records"][0].page
        normalize_calls.append(page.summary)
        payload = raw_definition.to_dict()
        payload["reference_notes"] = {"cache_probe_summary": page.summary}
        return CharacterDefinition.from_dict(payload)

    monkeypatch.setattr(
        projection_module,
        "normalize_definition_to_native_model",
        normalize_with_page_summary,
    )

    first = _project_scoped(
        _definition(),
        service,
        [page_record],
        components=frozenset(),
        derivation_components=frozenset({"sheet_entries"}),
    )
    page_record.page.summary = "Second summary."
    second = _project_scoped(
        _definition(),
        service,
        [page_record],
        components=frozenset(),
        derivation_components=frozenset({"sheet_entries"}),
    )

    assert first["definition"].reference_notes["cache_probe_summary"] == "First summary."
    assert second["definition"].reference_notes["cache_probe_summary"] == "Second summary."
    assert normalize_calls == ["First summary.", "Second summary."]


def test_normalization_page_key_treats_dict_materialization_like_object_record():
    object_record = _page_record(
        "items/cache-item",
        "Items",
        "2026-08-11T12:00:00Z",
        title="Cache Item",
        subsection="Treasures",
        summary="Cache summary.",
        metadata={"item_mechanics": {"status": "approved"}},
        body_markdown="Cache body.",
        content_loaded=True,
    )
    common_page = {
        "page_ref": "items/cache-item",
        "route_slug": "items/cache-item",
        "title": "Cache Item",
        "section": "Items",
        "subsection": "Treasures",
        "page_type": "item",
        "published": True,
        "reveal_after_session": 0,
        "summary": "Cache summary.",
    }
    record_level_dict = {
        "page_ref": "items/cache-item",
        "updated_at": "2026-08-11T12:00:00Z",
        "title": "Cache Item",
        "section": "Items",
        "subsection": "Treasures",
        "summary": "Cache summary.",
        "metadata": {"item_mechanics": {"status": "approved"}},
        "body_markdown": "Cache body.",
        "content_loaded": True,
        "page": {
            **common_page,
            "title": "Ignored title",
            "section": "Ignored section",
            "subsection": "Ignored subsection",
            "summary": "Ignored summary.",
        },
    }
    page_level_dict = {
        "updated_at": "2026-08-11T12:00:00Z",
        "page": {
            **common_page,
            "metadata": {"item_mechanics": {"status": "approved"}},
            "body_markdown": "Cache body.",
            "content_loaded": True,
        },
    }

    object_key = _builder_normalization_page_key([object_record])
    assert _builder_normalization_page_key([record_level_dict]) == object_key
    assert _builder_normalization_page_key([page_level_dict]) == object_key

    changed_object = deepcopy(object_record)
    changed_object.page.summary = "Changed summary."
    changed_record_dict = deepcopy(record_level_dict)
    changed_record_dict["summary"] = "Changed summary."
    changed_page_dict = deepcopy(page_level_dict)
    changed_page_dict["page"]["summary"] = "Changed summary."
    for changed_record in (
        changed_object,
        changed_record_dict,
        changed_page_dict,
    ):
        assert _builder_normalization_page_key([changed_record]) != object_key


def test_scoped_normalized_cache_applies_transient_projection_on_every_state_read(
    monkeypatch,
):
    service = _RevisionSystemsService()
    definition = _definition()
    page = _page_record("mechanics/transient", "Mechanics", "2026-08-11T12:00:00Z")
    normalize_calls = 0
    transient_calls: list[int] = []

    def fake_normalize(raw_definition, **_kwargs):
        nonlocal normalize_calls
        normalize_calls += 1
        return CharacterDefinition.from_dict(raw_definition.to_dict())

    def fake_active_effects(_definition, state):
        return {"current_hp": int(dict(state.get("vitals") or {}).get("current_hp") or 0)}

    def fake_transient(definition_to_project, effects, **_kwargs):
        current_hp = int(effects["current_hp"])
        transient_calls.append(current_hp)
        payload = definition_to_project.to_dict()
        payload["stats"] = {**dict(payload.get("stats") or {}), "max_hp": 20 + current_hp}
        return CharacterDefinition.from_dict(payload)

    monkeypatch.setattr(
        projection_module,
        "normalize_definition_to_native_model",
        fake_normalize,
    )
    monkeypatch.setattr(
        projection_module,
        "active_divine_avatar_transient_effects",
        fake_active_effects,
    )
    monkeypatch.setattr(
        projection_module,
        "project_definition_with_transient_effects",
        fake_transient,
    )

    first = _project_scoped(
        definition,
        service,
        [page],
        current_hp=3,
        components=frozenset({"divine_avatar"}),
        derivation_components=frozenset({"sheet_entries"}),
    )
    second = _project_scoped(
        definition,
        service,
        [page],
        current_hp=4,
        components=frozenset({"divine_avatar"}),
        derivation_components=frozenset({"sheet_entries"}),
    )

    assert normalize_calls == 1
    assert transient_calls == [3, 4]
    assert first["definition"].stats["max_hp"] == 23
    assert second["definition"].stats["max_hp"] == 24


@pytest.mark.parametrize(
    "projector",
    (_project, _project_scoped),
    ids=("full", "scoped"),
)
def test_normalized_definition_cache_single_flights_and_merges_each_mutable_state(
    monkeypatch,
    projector,
):
    service = _RevisionSystemsService()
    definition = _definition()
    page = _page_record("mechanics/concurrent", "Mechanics", "2026-07-20T12:00:00Z")
    callers_ready = Barrier(4)
    build_started = Event()
    release_build = Event()
    normalize_count = 0
    build_lock = Lock()

    def fake_normalize(raw_definition, **kwargs):
        nonlocal normalize_count
        del kwargs
        with build_lock:
            normalize_count += 1
        build_started.set()
        assert release_build.wait(timeout=2)
        return CharacterDefinition.from_dict(raw_definition.to_dict())

    monkeypatch.setattr(projection_module, "normalize_definition_to_native_model", fake_normalize)

    def project(current_hp: int):
        callers_ready.wait(timeout=2)
        return projector(definition, service, [page], current_hp=current_hp)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(project, current_hp) for current_hp in range(1, 5)]
        assert build_started.wait(timeout=2)
        release_build.set()
        projections = [future.result(timeout=2) for future in futures]

    assert normalize_count == 1
    assert [row["state"]["vitals"]["current_hp"] for row in projections] == [1, 2, 3, 4]
    assert len({id(row["definition"]) for row in projections}) == 4


@pytest.mark.parametrize(
    "projector",
    (_project, _project_scoped),
    ids=("full", "scoped"),
)
def test_normalized_definition_failure_wakes_waiters_and_retry_works(
    monkeypatch,
    projector,
):
    service = _RevisionSystemsService()
    definition = _definition()
    page = _page_record("mechanics/failure", "Mechanics", "2026-07-20T12:00:00Z")
    callers_ready = Barrier(3)
    failed_started = Event()
    release_failure = Event()
    normalize_count = 0

    def failing_normalize(raw_definition, **kwargs):
        nonlocal normalize_count
        del raw_definition, kwargs
        normalize_count += 1
        failed_started.set()
        assert release_failure.wait(timeout=2)
        raise RuntimeError("normalization failed")

    monkeypatch.setattr(projection_module, "normalize_definition_to_native_model", failing_normalize)

    def project():
        callers_ready.wait(timeout=2)
        return projector(definition, service, [page])

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(project) for _ in range(3)]
        assert failed_started.wait(timeout=2)
        release_failure.set()
        for future in futures:
            with pytest.raises(RuntimeError, match="normalization failed"):
                future.result(timeout=2)

    assert normalize_count == 1
    monkeypatch.setattr(
        projection_module,
        "normalize_definition_to_native_model",
        lambda raw_definition, **kwargs: CharacterDefinition.from_dict(raw_definition.to_dict()),
    )
    assert projector(definition, service, [page])["definition"].stats["max_hp"] == 20


@pytest.mark.parametrize(
    "projector",
    (_project, _project_scoped),
    ids=("full", "scoped"),
)
def test_normalized_definition_clear_generation_keeps_new_value(
    monkeypatch,
    projector,
):
    service = _RevisionSystemsService()
    definition = _definition()
    page = _page_record("mechanics/clear", "Mechanics", "2026-07-20T12:00:00Z")
    old_started = Event()
    release_old = Event()
    values = iter((20, 21))

    def normalize(raw_definition, **kwargs):
        del kwargs
        value = next(values)
        if value == 20:
            old_started.set()
            assert release_old.wait(timeout=2)
        payload = raw_definition.to_dict()
        payload["stats"] = {"max_hp": value}
        return CharacterDefinition.from_dict(payload)

    monkeypatch.setattr(projection_module, "normalize_definition_to_native_model", normalize)

    with ThreadPoolExecutor(max_workers=1) as executor:
        old_future = executor.submit(projector, definition, service, [page])
        assert old_started.wait(timeout=2)
        _clear_normalized_definition_cache()
        assert projector(definition, service, [page])["definition"].stats["max_hp"] == 21
        release_old.set()
        assert old_future.result(timeout=2)["definition"].stats["max_hp"] == 20

    assert projector(definition, service, [page])["definition"].stats["max_hp"] == 21


def _entry(index: int) -> SystemsEntryRecord:
    timestamp = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    return SystemsEntryRecord(
        id=index,
        library_slug="DND-5E",
        source_id="PHB",
        entry_key=f"dnd-5e|classfeature|phb|cache-entry-{index}",
        entry_type="classfeature",
        slug=f"cache-entry-{index}",
        title=f"Cache Entry {index}",
        source_page="",
        source_path="",
        search_text=f"cache entry {index}",
        player_safe_default=True,
        dm_heavy=False,
        metadata={},
        body={"entries": [f"Body {index}"]},
        rendered_html="",
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_systems_character_render_request_cache_is_revision_aware_detached_and_clearable(
    app,
    monkeypatch,
):
    service = SystemsService(store=object(), repository_store=object())
    source_scan_count = 0
    render_count = 0
    entry = _entry(1)

    monkeypatch.setattr(
        service,
        "list_campaign_source_states",
        lambda campaign_slug: [
            SimpleNamespace(source=SimpleNamespace(source_id="PHB"), is_enabled=True)
        ],
    )

    def list_source_entries(*args, **kwargs):
        nonlocal source_scan_count
        del args, kwargs
        source_scan_count += 1
        return []

    def render_embedded_content(*args, **kwargs):
        nonlocal render_count
        del args, kwargs
        render_count += 1
        return (f"<p>Render {render_count}</p>", [])

    monkeypatch.setattr(service, "list_entries_for_campaign_source", list_source_entries)
    monkeypatch.setattr(service, "_render_embedded_content", render_embedded_content)

    with app.test_request_context("/campaigns/linden-pass/characters/cache-test"):
        assert service.build_character_sheet_entry_body_html("linden-pass", entry) == "<p>Render 1</p>"
        assert service.build_character_sheet_entry_body_html("linden-pass", entry) == "<p>Render 1</p>"
        first_lookup = service._build_optionalfeature_entry_lookup("linden-pass")
        first_lookup["mutated"] = []
        assert "mutated" not in service._build_optionalfeature_entry_lookup("linden-pass")
        assert source_scan_count == 1

        entry.updated_at += timedelta(seconds=1)
        assert service.build_character_sheet_entry_body_html("linden-pass", entry) == "<p>Render 2</p>"
        _systems_service_cache_clear()
        assert service.build_character_sheet_entry_body_html("linden-pass", entry) == "<p>Render 3</p>"

    assert render_count == 3


def test_prepared_native_derivation_is_detached_and_matches_live_normalization_without_live_lookups(
    monkeypatch,
):
    definition = _definition(
        profile={"level": 5},
        stats={
            "max_hp": 20,
            "armor_class": 11,
            "ability_scores": {
                key: {"score": 10, "modifier": 0, "save_bonus": 0}
                for key in ("str", "dex", "con", "int", "wis", "cha")
            },
        },
        features=[
            {
                "id": "campaign-boon",
                "name": "Campaign Boon",
                "resource_template": {
                    "id": "campaign-boon-uses",
                    "name": "Campaign Boon",
                    "max": 2,
                },
            }
        ],
    )
    pages = [_page_record("mechanics/campaign-boon", "Mechanics", "revision-v1")]
    service = _RevisionSystemsService()
    static_bundle = {
        "supported_class_entries": [],
        "subclass_entries": [],
        "species_options": [],
        "background_options": [],
        "item_catalog": {},
        "spell_catalog": {},
    }
    static_calls = 0

    def build_static(*_args, **_kwargs):
        nonlocal static_calls
        static_calls += 1
        return deepcopy(static_bundle)

    monkeypatch.setattr(builder_module, "_build_common_builder_static_bundle", build_static)
    live = builder_module.normalize_definition_to_native_model(
        definition,
        systems_service=service,
        campaign_page_records=pages,
    )
    candidate = CharacterDefinition.from_dict(deepcopy(definition.to_dict()))
    foundation = builder_module.prepare_native_derivation_foundation(
        definition,
        systems_service=service,
        campaign_page_records=pages,
    )

    static_bundle["item_catalog"]["late-mutation"] = {"name": "Mutated"}
    pages[0].page.title = "Mutated page"
    definition.features[0]["name"] = "Mutated definition"
    monkeypatch.setattr(
        builder_module,
        "_build_common_builder_static_bundle",
        lambda *_args, **_kwargs: pytest.fail("prepared normalization touched the static bundle"),
    )
    monkeypatch.setattr(
        builder_module,
        "_resolve_definition_sheet_entries",
        lambda *_args, **_kwargs: pytest.fail("prepared normalization resolved live entries"),
    )

    prepared = builder_module.normalize_definition_with_prepared_native_foundation(
        candidate,
        foundation,
    )

    assert prepared.to_dict() == live.to_dict()
    assert static_calls == 2


@pytest.mark.parametrize("prewarm", (False, True), ids=("cold", "warm"))
def test_prepared_native_callback_preserves_static_progress_and_request_cache_snapshots(
    monkeypatch,
    prewarm,
):
    definition = _definition(profile={"level": 3})
    service = _RevisionSystemsService()
    pages = [_page_record("mechanics/cache-foundation", "Mechanics", "v1")]
    static_bundle = {
        "supported_class_entries": [],
        "subclass_entries": [],
        "species_options": [],
        "background_options": [],
        "item_catalog": {},
        "spell_catalog": {},
    }

    def build_static(*_args, **_kwargs):
        return catalog_module._builder_cache_get(
            ("prepared-native-request", service.revision),
            lambda: catalog_module._builder_static_cache_get(
                ("prepared-native-static", service.revision),
                lambda: deepcopy(static_bundle),
            ),
        )

    monkeypatch.setattr(builder_module, "_build_common_builder_static_bundle", build_static)
    app = Flask(__name__)
    with app.test_request_context("/campaigns/linden-pass/characters/cache-test/update-preview"):
        if prewarm:
            builder_module.prepare_native_derivation_foundation(
                definition,
                systems_service=service,
                campaign_page_records=pages,
            )
            g._character_builder_request_cache = {}
        foundation = builder_module.prepare_native_derivation_foundation(
            definition,
            systems_service=service,
            campaign_page_records=pages,
        )
        static_snapshot = deepcopy(list(catalog_module._BUILDER_STATIC_BUNDLE_CACHE.items()))
        progress_snapshot = deepcopy(list(catalog_module._BUILDER_PROGRESS_CACHE.items()))
        request_snapshot = deepcopy(dict(g._character_builder_request_cache))

        def forbidden(*_args, **_kwargs):
            pytest.fail("prepared native callback touched a sealed live/cache boundary")

        service.get_builder_static_revision = forbidden
        monkeypatch.setattr(builder_module, "_build_common_builder_static_bundle", forbidden)
        monkeypatch.setattr(builder_module, "_resolve_definition_sheet_entries", forbidden)
        monkeypatch.setattr(progression_module, "_class_progression_for_builder", forbidden)
        monkeypatch.setattr(progression_module, "_subclass_progression_for_builder", forbidden)
        monkeypatch.setattr(catalog_module, "_builder_request_cache", forbidden)
        monkeypatch.setattr(catalog_module, "_builder_cache_get", forbidden)
        monkeypatch.setattr(catalog_module, "_builder_static_cache_get", forbidden)
        monkeypatch.setattr(catalog_module, "_builder_progress_cache_get", forbidden)
        monkeypatch.setattr(derivation_module, "utcnow", forbidden)

        normalized = builder_module.normalize_definition_with_prepared_native_foundation(
            CharacterDefinition.from_dict(deepcopy(definition.to_dict())),
            foundation,
        )

        assert normalized.character_slug == definition.character_slug
        assert list(catalog_module._BUILDER_STATIC_BUNDLE_CACHE.items()) == static_snapshot
        assert list(catalog_module._BUILDER_PROGRESS_CACHE.items()) == progress_snapshot
        assert dict(g._character_builder_request_cache) == request_snapshot


@pytest.mark.parametrize("prewarm", (False, True), ids=("cold", "warm"))
def test_prepared_native_spellcasting_callbacks_preserve_phb_progression_lru_cache_info(
    monkeypatch,
    prewarm,
):
    wizard = _systems_entry("class", "phb-class-wizard", "Wizard")
    fighter = _systems_entry("class", "phb-class-fighter", "Fighter")
    eldritch_knight = _systems_entry(
        "subclass",
        "phb-subclass-eldritch-knight",
        "Eldritch Knight",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
    )

    definition = _definition(
        profile={
            "level": 6,
            "classes": [
                {
                    "row_id": "wizard-row",
                    "class_name": "Wizard",
                    "level": 3,
                    "systems_ref": _test_systems_ref(wizard),
                },
                {
                    "row_id": "fighter-row",
                    "class_name": "Fighter",
                    "subclass_name": "Eldritch Knight",
                    "level": 3,
                    "systems_ref": _test_systems_ref(fighter),
                    "subclass_ref": _test_systems_ref(eldritch_knight),
                },
            ],
        },
        stats={
            "max_hp": 30,
            "ability_scores": {
                key: {"score": 16 if key == "int" else 10}
                for key in ("str", "dex", "con", "int", "wis", "cha")
            },
        },
        spellcasting={"slot_progression": [], "spells": []},
    )
    _install_prepared_spellcasting_static_bundle(
        monkeypatch,
        class_entries=[wizard, fighter],
        subclass_entries=[eldritch_knight],
    )
    foundation_module._load_phb_class_progression.cache_clear()
    foundation_module._load_phb_subclass_spell_progression.cache_clear()
    if prewarm:
        foundation_module._load_phb_class_progression()
        foundation_module._load_phb_subclass_spell_progression()

    foundation = builder_module.prepare_native_derivation_foundation(
        definition,
        systems_service=object(),
        campaign_page_records=[],
    )
    prepared_entries = foundation._resolved_entries
    profiles_by_row = prepared_entries["effective_spellcasting_profiles_by_row"]
    shared_slot_table = prepared_entries["shared_multiclass_slot_progression"]
    assert set(profiles_by_row) == {"wizard-row", "fighter-row"}
    assert profiles_by_row["wizard-row"]["caster_progression"] == "full"
    assert profiles_by_row["fighter-row"]["caster_progression"] == "1/3"
    assert shared_slot_table
    cached_wizard_slots = foundation_module._load_phb_class_progression()[
        "Wizard"
    ]["slot_progression"]
    assert shared_slot_table is not cached_wizard_slots
    assert shared_slot_table[0] is not cached_wizard_slots[0]

    class_loader = foundation_module._load_phb_class_progression
    subclass_loader = foundation_module._load_phb_subclass_spell_progression
    class_cache_snapshot = class_loader.cache_info()
    subclass_cache_snapshot = subclass_loader.cache_info()

    def forbidden(*_args, **_kwargs):
        pytest.fail("prepared spellcasting callback touched progression or filesystem")

    monkeypatch.setattr(foundation_module, "Path", forbidden)
    monkeypatch.setattr(foundation_module, "_load_phb_class_progression", forbidden)
    monkeypatch.setattr(
        foundation_module,
        "_load_phb_subclass_spell_progression",
        forbidden,
    )
    monkeypatch.setattr(builder_module, "_class_spell_progression", forbidden)
    monkeypatch.setattr(
        builder_module,
        "_effective_spellcasting_profile_for_row",
        forbidden,
    )
    monkeypatch.setattr(derivation_module, "_class_spell_progression", forbidden)
    monkeypatch.setattr(
        derivation_module,
        "_effective_spellcasting_profile_for_row",
        forbidden,
    )

    for _ in range(2):
        normalized = builder_module.normalize_definition_with_prepared_native_foundation(
            CharacterDefinition.from_dict(deepcopy(definition.to_dict())),
            foundation,
        )
        assert [
            row["caster_progression"]
            for row in normalized.spellcasting["class_rows"]
        ] == ["full", "1/3"]

    assert {
        "class": class_loader.cache_info(),
        "subclass": subclass_loader.cache_info(),
    } == {
        "class": class_cache_snapshot,
        "subclass": subclass_cache_snapshot,
    }


@pytest.mark.parametrize(
    ("case_name", "row_specs", "expected_progressions", "expected_shared_lanes"),
    (
        ("single-full", (("wizard", 3),), ("full",), (False,)),
        ("single-half", (("paladin", 3),), ("1/2",), (False,)),
        ("single-artificer", (("artificer", 3),), ("artificer",), (False,)),
        ("single-phb-third", (("fighter-ek", 3),), ("1/3",), (False,)),
        ("single-structured-third", (("structured-third", 3),), ("1/3",), (False,)),
        ("single-pact", (("warlock", 3),), ("pact",), (False,)),
        ("full-half", (("wizard", 3), ("paladin", 2)), ("full", "1/2"), (True,)),
        (
            "full-artificer",
            (("wizard", 3), ("artificer", 2)),
            ("full", "artificer"),
            (True,),
        ),
        (
            "phb-third-full",
            (("fighter-ek", 3), ("wizard", 3)),
            ("1/3", "full"),
            (True,),
        ),
        (
            "structured-third-full",
            (("structured-third", 3), ("wizard", 3)),
            ("1/3", "full"),
            (True,),
        ),
        (
            "full-pact",
            (("wizard", 3), ("warlock", 3)),
            ("full", "pact"),
            (False, False),
        ),
        (
            "third-pact",
            (("fighter-ek", 3), ("warlock", 3)),
            ("1/3", "pact"),
            (False, False),
        ),
        (
            "full-third-pact",
            (("wizard", 3), ("fighter-ek", 3), ("warlock", 3)),
            ("full", "1/3", "pact"),
            (True, False),
        ),
        (
            "unknown-custom-empty",
            (("unknown", 3), ("custom-noncaster", 3)),
            (),
            (),
        ),
    ),
)
def test_live_and_prepared_spellcasting_parity_uses_materialized_row_profiles_and_slot_table(
    monkeypatch,
    case_name,
    row_specs,
    expected_progressions,
    expected_shared_lanes,
):
    del case_name
    classes = {
        "wizard": _systems_entry("class", "phb-class-wizard", "Wizard"),
        "paladin": _systems_entry("class", "phb-class-paladin", "Paladin"),
        "artificer": _systems_entry("class", "tce-class-artificer", "Artificer", source_id="TCE"),
        "fighter-ek": _systems_entry("class", "phb-class-fighter", "Fighter"),
        "warlock": _systems_entry("class", "phb-class-warlock", "Warlock"),
        "structured-third": _systems_entry(
            "class",
            "custom-structured-third",
            "Structured Third",
            source_id="CUSTOM-TEST",
            metadata={
                "spellcasting_ability": "int",
                "spell_list_class_name": "Wizard",
                "caster_progression": "1/3",
                "spells_known_progression": [0, 0, 3],
                "slot_progression": [[], [], [{"level": 1, "max_slots": 2}]],
            },
        ),
        "custom-noncaster": _systems_entry(
            "class",
            "custom-noncaster",
            "Custom Noncaster",
            source_id="CUSTOM-TEST",
        ),
    }
    eldritch_knight = _systems_entry(
        "subclass",
        "phb-subclass-eldritch-knight",
        "Eldritch Knight",
        metadata={"class_name": "Fighter", "class_source": "PHB"},
    )
    rows = []
    class_entries = []
    for index, (row_kind, row_level) in enumerate(row_specs, start=1):
        row_id = f"row-{index}-{row_kind}"
        if row_kind == "unknown":
            rows.append(
                {
                    "row_id": row_id,
                    "class_name": "Unknown Class",
                    "level": row_level,
                    "systems_ref": {
                        "slug": "missing-unknown-class",
                        "title": "Unknown Class",
                        "source_id": "CUSTOM-MISSING",
                    },
                }
            )
            continue
        selected_class = classes[row_kind]
        class_entries.append(selected_class)
        row = {
            "row_id": row_id,
            "class_name": selected_class.title,
            "level": row_level,
            "systems_ref": _test_systems_ref(selected_class),
        }
        if row_kind == "fighter-ek":
            row["subclass_name"] = eldritch_knight.title
            row["subclass_ref"] = _test_systems_ref(eldritch_knight)
        rows.append(row)

    unique_class_entries = {
        entry.entry_key: entry for entry in class_entries
    }
    _install_prepared_spellcasting_static_bundle(
        monkeypatch,
        class_entries=list(unique_class_entries.values()),
        subclass_entries=[eldritch_knight],
    )
    definition = _definition(
        profile={"classes": rows},
        stats={
            "max_hp": 30,
            "ability_scores": {
                key: {"score": 16 if key in {"int", "wis", "cha"} else 10}
                for key in ("str", "dex", "con", "int", "wis", "cha")
            },
        },
        spellcasting={"slot_progression": [], "spells": []},
    )

    live = builder_module.normalize_definition_to_native_model(
        definition,
        systems_service=object(),
        campaign_page_records=[],
    )
    foundation = builder_module.prepare_native_derivation_foundation(
        definition,
        systems_service=object(),
        campaign_page_records=[],
    )
    if not expected_progressions:
        monkeypatch.setattr(
            derivation_module,
            "_effective_spellcasting_profile_for_row",
            lambda *_args, **_kwargs: pytest.fail(
                "prepared empty row profile fell back to live progression"
            ),
        )
    prepared = builder_module.normalize_definition_with_prepared_native_foundation(
        CharacterDefinition.from_dict(deepcopy(definition.to_dict())),
        foundation,
    )

    assert prepared.to_dict() == live.to_dict()
    profiles_by_row = foundation._resolved_entries[
        "effective_spellcasting_profiles_by_row"
    ]
    assert set(profiles_by_row) == {row["row_id"] for row in rows}
    if not expected_progressions:
        assert all(profile == {} for profile in profiles_by_row.values())
    assert tuple(
        row["caster_progression"]
        for row in prepared.spellcasting["class_rows"]
    ) == expected_progressions
    assert tuple(
        bool(lane["shared"])
        for lane in prepared.spellcasting["slot_lanes"]
    ) == expected_shared_lanes


def test_prepared_spellcasting_profiles_are_detached_revisioned_and_reject_class_row_drift(
    monkeypatch,
):
    custom_caster = _systems_entry(
        "class",
        "custom-revision-caster",
        "Revision Caster",
        source_id="CUSTOM-TEST",
        metadata={
            "spellcasting_ability": "int",
            "spell_list_class_name": "Wizard",
            "caster_progression": "full",
            "spells_known_progression": [2],
            "slot_progression": [[{"level": 1, "max_slots": 2}]],
        },
    )
    static_bundle = _install_prepared_spellcasting_static_bundle(
        monkeypatch,
        class_entries=[custom_caster],
    )
    definition = _definition(
        profile={
            "classes": [
                {
                    "row_id": "revision-row",
                    "class_name": custom_caster.title,
                    "level": 1,
                    "systems_ref": _test_systems_ref(custom_caster),
                }
            ]
        },
        spellcasting={"slot_progression": [], "spells": []},
    )
    v1 = builder_module.prepare_native_derivation_foundation(
        definition,
        systems_service=object(),
        campaign_page_records=[],
    )

    custom_caster.metadata["caster_progression"] = "1/2"
    custom_caster.metadata["slot_progression"][0][0]["max_slots"] = 1
    static_bundle["supported_class_entries"][0].metadata = deepcopy(
        custom_caster.metadata
    )
    v2 = builder_module.prepare_native_derivation_foundation(
        definition,
        systems_service=object(),
        campaign_page_records=[],
    )
    normalized_v1 = builder_module.normalize_definition_with_prepared_native_foundation(
        CharacterDefinition.from_dict(deepcopy(definition.to_dict())),
        v1,
    )
    normalized_v2 = builder_module.normalize_definition_with_prepared_native_foundation(
        CharacterDefinition.from_dict(deepcopy(definition.to_dict())),
        v2,
    )

    assert v1._resolved_entries["effective_spellcasting_profiles_by_row"][
        "revision-row"
    ]["caster_progression"] == "full"
    assert v2._resolved_entries["effective_spellcasting_profiles_by_row"][
        "revision-row"
    ]["caster_progression"] == "1/2"
    assert normalized_v1.spellcasting["slot_progression"] == [
        {"level": 1, "max_slots": 2}
    ]
    assert normalized_v2.spellcasting["slot_progression"] == [
        {"level": 1, "max_slots": 1}
    ]

    drifted = CharacterDefinition.from_dict(deepcopy(definition.to_dict()))
    drifted.profile["classes"][0]["level"] = 2
    with pytest.raises(ValueError, match="does not match the character baseline"):
        builder_module.normalize_definition_with_prepared_native_foundation(
            drifted,
            v1,
        )


def test_prepared_native_foundations_isolate_item_catalog_revisions():
    definition = _definition(
        profile={"level": 3},
        stats={
            "max_hp": 20,
            "armor_class": 9,
            "ability_scores": {
                key: {"score": 10, "modifier": 0, "save_bonus": 0}
                for key in ("str", "dex", "con", "int", "wis", "cha")
            },
        },
        equipment_catalog=[
            {
                "id": "revision-mail",
                "name": "Revision Mail",
                "default_quantity": 1,
                "is_equipped": True,
            }
        ],
    )
    def item_entry(ac):
        return _systems_entry(
            "item",
            "revision-mail",
            "Revision Mail",
            metadata={"type": "HA", "ac": ac},
        )

    def prepare(ac):
        return builder_module.prepare_native_derivation_foundation(
            definition,
            item_catalog=builder_module._build_item_catalog([item_entry(ac)]),
            spell_catalog={},
        )

    v1 = prepare(16)
    v2 = prepare(18)
    candidate = CharacterDefinition.from_dict(deepcopy(definition.to_dict()))

    normalized_v1 = builder_module.normalize_definition_with_prepared_native_foundation(
        candidate,
        v1,
    )
    normalized_v2 = builder_module.normalize_definition_with_prepared_native_foundation(
        CharacterDefinition.from_dict(deepcopy(definition.to_dict())),
        v2,
    )

    assert normalized_v1.stats["armor_class"] == 16
    assert normalized_v2.stats["armor_class"] == 18
    assert normalized_v1.equipment_catalog[0]["systems_ref"]["slug"] == "revision-mail"


def test_automatic_prepared_lookup_preparation_is_row_scoped_and_application_is_pure(
    monkeypatch,
):
    wizard = _systems_entry("class", "wizard", "Wizard")
    cleric = _systems_entry("class", "cleric", "Cleric")
    rows = [
        {
            "row_id": "class-row-1",
            "row_level": 3,
            "selected_class": wizard,
            "selected_subclass": None,
        },
        {
            "row_id": "class-row-2",
            "row_level": 3,
            "selected_class": cleric,
            "selected_subclass": None,
        },
    ]

    class ProgressService:
        def __init__(self):
            self.calls = []

        def build_class_feature_progression_for_class_entry(
            self, campaign_slug, entry
        ):
            self.calls.append((campaign_slug, entry.title))
            return [{"level": 1, "feature_rows": []}]

    service = ProgressService()
    monkeypatch.setattr(
        progression_module,
        "_automatic_prepared_spell_lookup_keys_for_row",
        lambda *, selected_class, **_kwargs: (
            {"Bane"} if selected_class.title == "Cleric" else set()
        ),
    )
    lookup = progression_module._prepare_automatic_prepared_spell_lookup_keys(
        campaign_slug="linden-pass",
        systems_service=service,
        resolved_class_rows=rows,
        spell_catalog={},
        campaign_page_records=[],
    )
    service.build_class_feature_progression_for_class_entry = (
        lambda *_args, **_kwargs: pytest.fail("pure application re-read progression")
    )

    spells = progression_module._apply_prepared_automatic_prepared_spell_flags(
        [
            {"name": "Bane", "mark": "Spellbook", "class_row_id": "class-row-1"},
            {"name": "Bane", "mark": "Prepared", "class_row_id": "class-row-2"},
        ],
        resolved_class_rows=rows,
        row_lookup_keys=lookup,
    )
    by_row = {spell["class_row_id"]: spell for spell in spells}

    assert service.calls == [
        ("linden-pass", "Wizard"),
        ("linden-pass", "Cleric"),
    ]
    assert by_row["class-row-1"].get("is_always_prepared") is not True
    assert by_row["class-row-2"]["is_always_prepared"] is True
    assert by_row["class-row-2"]["mark"] == ""
