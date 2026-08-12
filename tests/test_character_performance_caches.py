from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event, Lock
from types import SimpleNamespace
from typing import Any, Callable

import pytest
from flask import Flask

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
