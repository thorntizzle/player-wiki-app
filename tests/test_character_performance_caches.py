from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event, Lock
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from player_wiki import character_mechanics_projection as projection_module
from player_wiki.character_builder_catalogs import (
    _builder_progress_cache_get,
    _builder_static_cache_get,
    _clear_builder_static_bundle_cache,
)
from player_wiki.character_mechanics_projection import (
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


def _page_record(page_ref: str, section: str, updated_at: str) -> SimpleNamespace:
    return SimpleNamespace(
        page_ref=page_ref,
        updated_at=updated_at,
        page=SimpleNamespace(section=section),
    )


class _RevisionSystemsService:
    def __init__(self) -> None:
        self.revision = "systems-v1"

    def get_builder_static_revision(
        self,
        campaign_slug: str,
        *,
        entry_types: tuple[str, ...],
    ) -> tuple[object, ...]:
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


def test_normalized_definition_cache_single_flights_and_merges_each_mutable_state(monkeypatch):
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
        return _project(definition, service, [page], current_hp=current_hp)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(project, current_hp) for current_hp in range(1, 5)]
        assert build_started.wait(timeout=2)
        release_build.set()
        projections = [future.result(timeout=2) for future in futures]

    assert normalize_count == 1
    assert [row["state"]["vitals"]["current_hp"] for row in projections] == [1, 2, 3, 4]
    assert len({id(row["definition"]) for row in projections}) == 4


def test_normalized_definition_failure_wakes_waiters_and_retry_works(monkeypatch):
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
        return _project(definition, service, [page])

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
    assert _project(definition, service, [page])["definition"].stats["max_hp"] == 20


def test_normalized_definition_clear_generation_keeps_new_value(monkeypatch):
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
        old_future = executor.submit(_project, definition, service, [page])
        assert old_started.wait(timeout=2)
        _clear_normalized_definition_cache()
        assert _project(definition, service, [page])["definition"].stats["max_hp"] == 21
        release_old.set()
        assert old_future.result(timeout=2)["definition"].stats["max_hp"] == 20

    assert _project(definition, service, [page])["definition"].stats["max_hp"] == 21


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
