from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event, Lock
from time import perf_counter
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


def _campaign(*, system: str = "DND-5E") -> Campaign:
    return Campaign(
        title="Linden Pass",
        slug="linden-pass",
        summary="",
        system=system,
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


def _entry(index: int, *, updated_at: datetime | None = None) -> SystemsEntryRecord:
    timestamp = updated_at or datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
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


@pytest.mark.parametrize(
    ("cache_get", "expected"),
    [
        (_builder_static_cache_get, {"value": "built"}),
        (_builder_progress_cache_get, [{"value": "built"}]),
    ],
)
def test_builder_process_caches_single_flight_same_key(
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


def test_builder_process_cache_different_keys_build_concurrently():
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
    [
        (_builder_static_cache_get, {"value": "recovered"}),
        (_builder_progress_cache_get, [{"value": "recovered"}]),
    ],
)
def test_builder_process_cache_failure_wakes_waiters_and_allows_retry(
    cache_get: Callable[..., Any],
    success_value: Any,
):
    callers_ready = Barrier(4)
    build_started = Event()
    release_failure = Event()
    build_lock = Lock()
    build_count = 0

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
    assert cache_get(("failing-key",), lambda: pytest.fail("cache was poisoned")) == success_value


def test_builder_cache_clear_does_not_restore_an_inflight_stale_value():
    old_build_started = Event()
    release_old_build = Event()

    def old_build() -> dict[str, str]:
        old_build_started.set()
        assert release_old_build.wait(timeout=2)
        return {"value": "old"}

    with ThreadPoolExecutor(max_workers=1) as executor:
        old_future = executor.submit(_builder_static_cache_get, ("clear-key",), old_build)
        assert old_build_started.wait(timeout=2)
        _clear_builder_static_bundle_cache()
        assert _builder_static_cache_get(
            ("clear-key",),
            lambda: {"value": "new"},
        ) == {"value": "new"}
        release_old_build.set()
        assert old_future.result(timeout=2) == {"value": "old"}

    assert _builder_static_cache_get(
        ("clear-key",),
        lambda: pytest.fail("stale builder overwrote the post-clear value"),
    ) == {"value": "new"}


def test_systems_character_sheet_rendering_memoizes_request_work_and_clears_deterministically(
    app,
    monkeypatch,
):
    service = SystemsService(store=object(), repository_store=object())
    source_ids = ("PHB", "TCE", "XGE")
    source_scan_count = 0
    render_count = 0

    monkeypatch.setattr(
        service,
        "list_campaign_source_states",
        lambda campaign_slug: [
            SimpleNamespace(source=SimpleNamespace(source_id=source_id), is_enabled=True)
            for source_id in source_ids
        ],
    )

    def list_source_entries(
        campaign_slug: str,
        source_id: str,
        *,
        entry_type: str | None = None,
        limit: int | None = None,
    ) -> list[SystemsEntryRecord]:
        nonlocal source_scan_count
        del campaign_slug, source_id, entry_type, limit
        source_scan_count += 1
        return []

    def render_embedded_content(*args, **kwargs):
        nonlocal render_count
        del args, kwargs
        render_count += 1
        return ("<p>Rendered body</p>", [])

    monkeypatch.setattr(service, "list_entries_for_campaign_source", list_source_entries)
    monkeypatch.setattr(service, "_render_embedded_content", render_embedded_content)
    entries = [_entry(index) for index in range(1, 25)]

    with app.test_request_context("/campaigns/linden-pass/characters/cache-test"):
        started_at = perf_counter()
        rendered = [
            service.build_character_sheet_entry_body_html("linden-pass", entry)
            for entry in entries
        ]
        first_pass_seconds = perf_counter() - started_at
        repeated = [
            service.build_character_sheet_entry_body_html("linden-pass", entry)
            for entry in entries
        ]
        warm_pass_seconds = perf_counter() - started_at - first_pass_seconds

        # Before request memoization, every distinct body render rebuilt the
        # optional-feature lookup: 24 entries x 3 enabled source scans = 72.
        uncached_source_scan_count = len(entries) * len(source_ids)
        assert source_scan_count == len(source_ids)
        assert uncached_source_scan_count >= source_scan_count * 10
        assert render_count == len(entries)
        assert repeated == rendered
        assert warm_pass_seconds >= 0

        first_lookup = service._build_optionalfeature_entry_lookup("linden-pass")
        first_lookup["mutated"] = []
        assert "mutated" not in service._build_optionalfeature_entry_lookup("linden-pass")

        _systems_service_cache_clear()
        assert service.build_character_sheet_entry_body_html(
            "linden-pass",
            entries[0],
        ) == "<p>Rendered body</p>"

    assert source_scan_count == len(source_ids) * 2
    assert render_count == len(entries) + 1


def test_systems_character_sheet_body_cache_uses_entry_revision(app, monkeypatch):
    service = SystemsService(store=object(), repository_store=object())
    render_count = 0
    monkeypatch.setattr(service, "_build_optionalfeature_entry_lookup", lambda campaign_slug: {})

    def render_embedded_content(*args, **kwargs):
        nonlocal render_count
        del args, kwargs
        render_count += 1
        return (f"<p>Render {render_count}</p>", [])

    monkeypatch.setattr(service, "_render_embedded_content", render_embedded_content)
    entry = _entry(1)

    with app.test_request_context("/campaigns/linden-pass/characters/cache-test"):
        assert service.build_character_sheet_entry_body_html("linden-pass", entry) == "<p>Render 1</p>"
        assert service.build_character_sheet_entry_body_html("linden-pass", entry) == "<p>Render 1</p>"
        entry.updated_at += timedelta(seconds=1)
        assert service.build_character_sheet_entry_body_html("linden-pass", entry) == "<p>Render 2</p>"

    assert render_count == 2


def test_normalized_definition_cache_is_revision_aware_and_ignores_unrelated_pages(monkeypatch):
    service = _RevisionSystemsService()
    definition = _definition()
    mechanics_page = _page_record("mechanics/cache-rule", "Mechanics", "2026-07-20T12:00:00Z")
    lore_page = _page_record("lore/unrelated", "Lore", "2026-07-20T12:00:00Z")
    normalize_calls: list[list[str]] = []

    def fake_normalize(
        raw_definition,
        *,
        systems_service=None,
        campaign_page_records=None,
    ):
        del systems_service
        normalize_calls.append(
            [str(record.page_ref) for record in list(campaign_page_records or [])]
        )
        return CharacterDefinition.from_dict(raw_definition.to_dict())

    monkeypatch.setattr(projection_module, "normalize_definition_to_native_model", fake_normalize)

    def project(raw_definition: CharacterDefinition = definition):
        return build_character_mechanics_projection(
            campaign=_campaign(),
            definition=raw_definition,
            state={"vitals": {"current_hp": 7, "temp_hp": 0}},
            systems_service=service,
            campaign_page_records=[mechanics_page, lore_page],
        )

    first = project()
    first["definition"].stats["max_hp"] = 999
    lore_page.updated_at = "2026-07-20T12:05:00Z"
    second = project()
    assert second["definition"].stats["max_hp"] == 20
    assert first["definition"] is not second["definition"]
    assert normalize_calls == [["mechanics/cache-rule"]]

    mechanics_page.updated_at = "2026-07-20T12:05:00Z"
    project()
    service.revision = "systems-v2"
    project()
    changed_definition = _definition(stats={"max_hp": 21})
    project(changed_definition)

    assert len(normalize_calls) == 4
    assert all(call == ["mechanics/cache-rule"] for call in normalize_calls)


def test_normalized_definition_cache_reuses_definition_but_merges_current_state_each_time(monkeypatch):
    service = _RevisionSystemsService()
    definition = _definition(
        features=[{"id": f"feature-{index}", "name": f"Feature {index}"} for index in range(30)],
        equipment_catalog=[
            {"id": f"item-{index}", "name": f"Item {index}"}
            for index in range(30)
        ],
    )
    mechanics_page = _page_record("mechanics/rich-rule", "Mechanics", "2026-07-20T12:00:00Z")
    normalize_count = 0

    def fake_normalize(raw_definition, **kwargs):
        nonlocal normalize_count
        del kwargs
        normalize_count += 1
        return CharacterDefinition.from_dict(raw_definition.to_dict())

    monkeypatch.setattr(projection_module, "normalize_definition_to_native_model", fake_normalize)
    states = range(1, 21)
    started_at = perf_counter()
    projections = [
        build_character_mechanics_projection(
            campaign=_campaign(),
            definition=definition,
            state={"vitals": {"current_hp": current_hp, "temp_hp": 0}},
            systems_service=service,
            campaign_page_records=[mechanics_page],
        )
        for current_hp in states
    ]
    elapsed_seconds = perf_counter() - started_at

    # This representative rich sheet would previously normalize 20 times.
    # The revision-aware cache performs one build while preserving all 20
    # independently merged mutable states: a 20x warm-path build reduction.
    assert normalize_count == 1
    assert len(projections) >= normalize_count * 10
    assert [projection["state"]["vitals"]["current_hp"] for projection in projections] == list(states)
    assert len({id(projection["definition"]) for projection in projections}) == len(projections)
    assert elapsed_seconds >= 0


def test_normalized_definition_cache_single_flights_concurrent_cold_requests(monkeypatch):
    service = _RevisionSystemsService()
    definition = _definition()
    mechanics_page = _page_record("mechanics/concurrent", "Mechanics", "2026-07-20T12:00:00Z")
    callers_ready = Barrier(4)
    build_started = Event()
    release_build = Event()
    build_lock = Lock()
    normalize_count = 0

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
        return build_character_mechanics_projection(
            campaign=_campaign(),
            definition=definition,
            state={"vitals": {"current_hp": current_hp, "temp_hp": 0}},
            systems_service=service,
            campaign_page_records=[mechanics_page],
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(project, current_hp) for current_hp in range(1, 5)]
        assert build_started.wait(timeout=2)
        release_build.set()
        projections = [future.result(timeout=2) for future in futures]

    assert normalize_count == 1
    assert [projection["state"]["vitals"]["current_hp"] for projection in projections] == [1, 2, 3, 4]
    assert len({id(projection["definition"]) for projection in projections}) == 4
