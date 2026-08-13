from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest
from flask import Flask

import player_wiki.app as app_module
import player_wiki.character_builder_catalogs as catalogs_module
import player_wiki.character_builder_equipment as equipment_module
import player_wiki.character_mechanics_projection as mechanics_module
import player_wiki.character_page_records as page_records_module
import player_wiki.character_editor as editor_module
from player_wiki.character_builder_catalogs import (
    _build_item_catalog,
    _build_spell_catalog,
    _builder_static_revision_key,
    _clear_builder_static_bundle_cache,
)
from player_wiki.character_builder_equipment import (
    _resolve_item_entry,
    describe_equipment_state_support,
)
from player_wiki.character_builder_spells import (
    _assign_spell_payload_class_rows,
    _normalize_spell_payloads,
    _resolve_spell_payload_entry,
    _spell_payload_key,
    _spell_payload_map_key,
    _spell_selection_values_by_mark,
)
from player_wiki.character_builder_progression import _imported_spell_candidate_row_ids
from player_wiki.character_editor import (
    apply_character_spell_management_edit,
    build_character_spell_management_context,
)
from player_wiki.character_page_records import materialize_dnd_character_read_page_records
from player_wiki.character_models import (
    CharacterDefinition,
    CharacterImportMetadata,
    CharacterRecord,
    CharacterStateRecord,
)
from player_wiki.character_read_projection import (
    build_character_read_projection_cache_key,
    load_cached_character_read_projection,
    reset_character_read_projection_cache_for_tests,
)
from player_wiki.character_presenter import (
    present_character_detail,
    present_dnd_character_section as real_scoped_presenter,
)
from player_wiki.models import Campaign
from player_wiki.systems_models import SystemsEntryRecord
from tests.helpers.character_state_helpers import _write_character_definition


def _fail_full_presenter(*_args, **_kwargs):
    raise AssertionError("normal DND reads must not call the full character presenter")


def _systems_item(entry_key: str, slug: str, title: str) -> SystemsEntryRecord:
    timestamp = datetime(2026, 1, 1)
    return SystemsEntryRecord(
        id=1,
        library_slug="DND-5E",
        source_id="PHB",
        entry_key=entry_key,
        entry_type="item",
        slug=slug,
        title=title,
        source_page="1",
        source_path="test.json",
        search_text=title,
        player_safe_default=True,
        dm_heavy=False,
        metadata={},
        body={},
        rendered_html="",
        created_at=timestamp,
        updated_at=timestamp,
    )


def _systems_spell(
    entry_key: str,
    slug: str,
    title: str,
    *,
    source_id: str = "PHB",
    level: int = 1,
) -> SystemsEntryRecord:
    timestamp = datetime(2026, 1, 1)
    return SystemsEntryRecord(
        id=1,
        library_slug="DND-5E",
        source_id=source_id,
        entry_key=entry_key,
        entry_type="spell",
        slug=slug,
        title=title,
        source_page="1",
        source_path="test.json",
        search_text=title,
        player_safe_default=True,
        dm_heavy=False,
        metadata={"level": level},
        body={},
        rendered_html="",
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_item_catalog_resolves_entry_key_before_conflicting_slug_and_title():
    keyed = _systems_item("item|keyed", "keyed-item", "Shared Relic")
    conflicting = _systems_item("item|conflict", "conflicting-item", "Shared Relic")
    catalog = _build_item_catalog([keyed, conflicting])

    resolved = _resolve_item_entry(
        {
            "name": "Shared Relic",
            "systems_ref": {
                "entry_key": "item|keyed",
                "slug": "conflicting-item",
                "title": "Shared Relic",
            },
        },
        catalog,
    )

    assert resolved is keyed
    assert catalog["by_title"] == {}


def test_item_catalog_fails_closed_on_duplicate_normalized_title_without_exact_ref():
    first = _systems_item("item|first", "first-relic", "Storm's Eye")
    second = _systems_item("item|second", "second-relic", "Storms Eye")
    catalog = _build_item_catalog([first, second])

    resolved = _resolve_item_entry(
        {"name": "Storm's Eye", "systems_ref": {}},
        catalog,
    )

    assert resolved is None
    assert catalog["by_title"] == {}


def test_targeted_item_catalog_preserves_ambiguous_slug_candidates_for_scoped_consumers():
    exact = _systems_item("item|exact", "shared-relic", "Exact Relic")
    conflicting = _systems_item(
        "item|conflicting",
        "shared-relic",
        "Conflicting Relic",
    )

    class SystemsService:
        def list_enabled_entries_by_identity_for_campaign(self, *_args, **_kwargs):
            return [exact, conflicting]

    exact_payload = {
        "name": exact.title,
        "is_equipped": True,
        "systems_ref": {
            "entry_key": exact.entry_key,
            "slug": exact.slug,
        },
    }
    legacy_payload = {
        "name": "Legacy Relic",
        "is_equipped": True,
        "systems_ref": {"slug": exact.slug},
    }

    catalog = catalogs_module._build_targeted_item_support_catalog(
        [exact_payload, legacy_payload],
        campaign_slug="linden-pass",
        systems_service=SystemsService(),
        include_inactive=True,
    )

    assert {
        entry.entry_key for entry in catalog["entries"]
    } == {exact.entry_key, conflicting.entry_key}
    assert catalog["by_slug"] == {}
    assert _resolve_item_entry(exact_payload, catalog) is exact
    assert _resolve_item_entry(legacy_payload, catalog) is None


def test_targeted_item_catalog_fallback_dedupes_repeated_exact_entry():
    exact = _systems_item("item|repeated", "repeated-relic", "Repeated Relic")

    class LegacySystemsService:
        def get_entry_for_campaign(self, _campaign_slug, entry_key):
            return exact if entry_key == exact.entry_key else None

        def is_entry_enabled_for_campaign(self, _campaign_slug, entry):
            return entry is exact

    payload = {
        "name": exact.title,
        "is_equipped": True,
        "systems_ref": {
            "entry_key": exact.entry_key,
            "slug": exact.slug,
        },
    }
    catalog = catalogs_module._build_targeted_item_support_catalog(
        [payload, {**payload, "id": "second-row"}],
        campaign_slug="linden-pass",
        systems_service=LegacySystemsService(),
        include_inactive=True,
    )

    assert catalog["entries"] == [exact]
    assert catalog["by_entry_key"] == {exact.entry_key: exact}
    assert catalog["by_slug"] == {exact.slug: exact}
    assert _resolve_item_entry(payload, catalog) is exact


def test_item_catalog_reuses_detached_normalized_phb_profile_indexes():
    catalog = _build_item_catalog([])
    weapon = {
        "name": "Quarterstaff",
        "systems_ref": {},
    }
    armor = {
        "name": "Chain Mail",
        "systems_ref": {},
    }

    weapon_support = describe_equipment_state_support(
        weapon,
        item_catalog=catalog,
    )
    armor_support = describe_equipment_state_support(
        armor,
        item_catalog=catalog,
    )

    assert weapon_support["is_weapon"] is True
    assert armor_support["is_armor"] is True
    legacy_catalog = dict(catalog)
    legacy_catalog.pop("phb_weapon_profiles_normalized")
    legacy_catalog.pop("phb_armor_profiles_normalized")
    assert describe_equipment_state_support(
        weapon,
        item_catalog=legacy_catalog,
    ) == weapon_support
    assert describe_equipment_state_support(
        armor,
        item_catalog=legacy_catalog,
    ) == armor_support
    catalog["phb_weapon_profiles"]["quarterstaff"]["properties"].append(
        "MUTATED"
    )
    catalog["phb_armor_profiles"]["chainmail"]["type"] = "MUTATED"
    with pytest.raises(TypeError):
        catalog["phb_weapon_profiles_normalized"]["quarterstaff"] = {}
    with pytest.raises(TypeError):
        catalog["phb_weapon_profiles_normalized"]["quarterstaff"]["type"] = (
            "MUTATED"
        )
    with pytest.raises(AttributeError):
        catalog["phb_weapon_profiles_normalized"]["quarterstaff"][
            "properties"
        ].append("MUTATED")
    first_profile = equipment_module._resolve_weapon_profile(weapon, catalog)
    assert first_profile is not None
    assert isinstance(first_profile["properties"], list)
    first_profile["properties"].append("MUTATED")
    second_profile = equipment_module._resolve_weapon_profile(weapon, catalog)
    assert second_profile is not None
    assert "MUTATED" not in second_profile["properties"]
    rebuilt = _build_item_catalog([])
    assert rebuilt["phb_weapon_profiles"]["quarterstaff"]["type"] == "M"
    assert "MUTATED" not in rebuilt["phb_weapon_profiles"]["quarterstaff"][
        "properties"
    ]
    assert rebuilt["phb_armor_profiles"]["chainmail"]["type"] != "MUTATED"
    assert rebuilt["phb_weapon_profiles_normalized"]["quarterstaff"]["type"] == "M"


def test_immutable_builtin_profile_snapshot_tracks_replaced_loader(
    monkeypatch,
):
    catalogs_module._immutable_normalized_phb_item_profiles.cache_clear()
    monkeypatch.setattr(
        catalogs_module,
        "_load_phb_weapon_profiles",
        lambda: {
            "Test Blade": {
                "title": "Test Blade",
                "type": "M",
                "properties": ["L"],
            }
        },
    )
    monkeypatch.setattr(catalogs_module, "_load_phb_armor_profiles", lambda: {})

    catalog = catalogs_module._build_item_catalog([])

    assert catalog["phb_weapon_profiles_normalized"]["testblade"]["title"] == (
        "Test Blade"
    )


def test_equipment_support_resolves_an_unlinked_item_exactly_once(monkeypatch):
    catalog = _build_item_catalog([])
    calls: list[dict[str, object]] = []
    real_resolve = equipment_module._resolve_item_entry

    def tracked_resolve(item, item_catalog):
        calls.append(dict(item))
        return real_resolve(item, item_catalog)

    monkeypatch.setattr(equipment_module, "_resolve_item_entry", tracked_resolve)

    support = describe_equipment_state_support(
        {
            "name": "Unlinked Relic",
            "systems_ref": {"title": "Ambiguous Missing Relic"},
        },
        item_catalog=catalog,
    )

    assert support["supports_equipped_state"] is False
    assert len(calls) == 1


def _replace_session_character_builder_dependency(
    app,
    monkeypatch,
    name: str,
    replacement,
) -> None:
    dependencies = app.extensions["character_route_dependencies"]
    builder = dependencies.build_campaign_session_character_page_context
    closure_index = builder.__code__.co_freevars.index(name)
    monkeypatch.setattr(
        builder.__closure__[closure_index],
        "cell_contents",
        replacement,
    )


def test_session_explicit_character_denial_precedes_page_and_presentation_work(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    calls = []

    def _unexpected(name):
        def fail(*_args, **_kwargs):
            calls.append(name)
            raise AssertionError(f"explicit-character denial reached {name}")

        return fail

    _replace_session_character_builder_dependency(
        app,
        monkeypatch,
        "get_campaign_page_store",
        _unexpected("get_campaign_page_store"),
    )

    sign_in(users["party"]["email"], users["party"]["password"])
    response = client.get(
        "/campaigns/linden-pass/session/character?character=arden-march&page=equipment&fragment=1"
    )

    assert response.status_code == 403
    assert calls == []


@pytest.fixture(autouse=True)
def _reset_read_projection_cache():
    reset_character_read_projection_cache_for_tests()
    yield
    reset_character_read_projection_cache_for_tests()


def _cache_record(*, definition: dict | None = None, revision: int = 1):
    return SimpleNamespace(
        definition=definition or {"name": "Cache Character"},
        state_record=SimpleNamespace(revision=revision),
    )


def _cache_page_record(
    *,
    page_ref: str = "mechanics/cache-page",
    updated_at: str = "2026-08-11T12:00:00Z",
    title: str = "Cache Page",
):
    return SimpleNamespace(
        page_ref=page_ref,
        updated_at=updated_at,
        metadata={"character_option": {"kind": "feat"}},
        page=SimpleNamespace(
            route_slug=page_ref,
            title=title,
            section="Mechanics",
            subsection="",
            page_type="mechanic",
            published=True,
            reveal_after_session=0,
        ),
    )


class _RevisionedSystemsService:
    def __init__(self, revision: object = (1,)) -> None:
        self.revision = revision
        self.revision_calls = 0

    def get_builder_static_revision(self, _campaign_slug, *, entry_types):
        assert entry_types
        self.revision_calls += 1
        return self.revision


class _NonWeakSystemsService:
    __slots__ = ()

    @staticmethod
    def get_builder_static_revision(_campaign_slug, *, entry_types):
        assert entry_types
        return ("systems", 1)


def _body_record(
    page_ref: str,
    title: str,
    *,
    section: str = "Items",
    body: str = "",
    published: bool = True,
    updated_at: str = "2026-08-11T12:00:00Z",
):
    return SimpleNamespace(
        page_ref=page_ref,
        updated_at=updated_at,
        metadata={"title": title, "section": section, "published": published},
        body_markdown=body,
        page=SimpleNamespace(
            route_slug=page_ref,
            title=title,
            section=section,
            subsection="",
            page_type="item" if section == "Items" else "mechanic",
            published=published,
            reveal_after_session=0,
            content_loaded=bool(body),
            body_markdown=body,
        ),
    )


class _BodyStore:
    def __init__(self, full_records):
        self.full_records = {
            record.page_ref: record for record in list(full_records or [])
        }
        self.calls: list[tuple[str, bool]] = []

    def get_page_record(self, _campaign_slug, page_ref, *, include_body):
        self.calls.append((str(page_ref), bool(include_body)))
        return self.full_records.get(str(page_ref))


def _visible_campaign():
    return SimpleNamespace(
        is_page_visible=lambda page: bool(page and page.published)
    )


def _quick_parity_campaign() -> Campaign:
    return Campaign(
        title="Quick parity",
        slug="linden-pass",
        summary="",
        system="DND-5E",
        current_session=1,
        source_wiki_root="",
        player_content_dir="",
        assets_dir="",
    )


def _zero_quantity_weapon_record() -> CharacterRecord:
    definition = CharacterDefinition.from_dict(
        {
            "campaign_slug": "linden-pass",
            "character_slug": "zero-quantity-weapon",
            "name": "Zero Quantity Weapon",
            "status": "active",
            "system": "DND-5E",
            "profile": {"size": "Medium"},
            "stats": {
                "max_hp": 12,
                "armor_class": 10,
                "proficiency_bonus": 2,
                "ability_scores": {
                    "str": {"score": 16, "modifier": 3, "save_bonus": 3},
                    "dex": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "con": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "int": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "wis": {"score": 10, "modifier": 0, "save_bonus": 0},
                    "cha": {"score": 10, "modifier": 0, "save_bonus": 0},
                },
            },
            "skills": [],
            "proficiencies": {"weapons": ["Martial Weapons", "Longswords"]},
            "attacks": [],
            "features": [],
            "spellcasting": {},
            "equipment_catalog": [
                {
                    "id": "zero-blade",
                    "name": "Zero Blade",
                    "page_ref": "items/zero-blade",
                    "default_quantity": 1,
                }
            ],
            "reference_notes": {},
            "resource_templates": [],
            "source": {},
        }
    )
    return CharacterRecord(
        definition=definition,
        import_metadata=CharacterImportMetadata(
            campaign_slug=definition.campaign_slug,
            character_slug=definition.character_slug,
            source_path="test://zero-quantity-weapon",
            imported_at_utc="2026-08-11T00:00:00Z",
            parser_version="test",
            import_status="ok",
            warnings=[],
        ),
        state_record=CharacterStateRecord(
            campaign_slug=definition.campaign_slug,
            character_slug=definition.character_slug,
            revision=1,
            state={
                "vitals": {"current_hp": 12, "temp_hp": 0},
                "inventory": [
                    {
                        "catalog_ref": "zero-blade",
                        "name": "Zero Blade",
                        "quantity": 0,
                        "is_equipped": True,
                        "weapon_wield_mode": "one_handed",
                    }
                ],
                "resources": [],
                "spell_slots": [],
                "currency": {},
                "notes": {},
            },
            updated_at=datetime(2026, 8, 11),
            updated_by_user_id=None,
        ),
    )


def _projection_key(
    *,
    record=None,
    service=None,
    page_records=None,
    current_session: int = 3,
    visibility=None,
):
    return build_character_read_projection_cache_key(
        "dnd-header-actions",
        campaign_slug="linden-pass",
        record=record or _cache_record(),
        systems_service=service or _RevisionedSystemsService(),
        campaign_page_records=page_records or [_cache_page_record()],
        campaign_current_session=current_session,
        effective_visibility=visibility
        or {"campaign": "players", "characters": "players"},
    )


def test_projection_cache_key_invalidates_every_revision_aware_input():
    service = _RevisionedSystemsService(("systems", 1))
    record = _cache_record(definition={"name": "Arden"}, revision=4)
    page_records = [_cache_page_record()]
    visibility = {
        "campaign": "players",
        "characters": "players",
        "wiki": "players",
        "systems": "players",
    }
    baseline = _projection_key(
        record=record,
        service=service,
        page_records=page_records,
        current_session=3,
        visibility=visibility,
    )

    assert baseline == _projection_key(
        record=record,
        service=service,
        page_records=deepcopy(page_records),
        current_session=3,
        visibility=deepcopy(visibility),
    )
    assert baseline != _projection_key(
        record=_cache_record(definition={"name": "Arden Revised"}, revision=4),
        service=service,
        page_records=page_records,
        current_session=3,
        visibility=visibility,
    )
    assert baseline != _projection_key(
        record=_cache_record(definition={"name": "Arden"}, revision=5),
        service=service,
        page_records=page_records,
        current_session=3,
        visibility=visibility,
    )
    assert baseline != _projection_key(
        record=record,
        service=service,
        page_records=[_cache_page_record(updated_at="2026-08-11T12:01:00Z")],
        current_session=3,
        visibility=visibility,
    )
    assert baseline != _projection_key(
        record=record,
        service=service,
        page_records=[_cache_page_record(title="Cache Page Revised")],
        current_session=3,
        visibility=visibility,
    )
    assert baseline != _projection_key(
        record=record,
        service=service,
        page_records=[
            _cache_page_record(page_ref="mechanics/second"),
            _cache_page_record(),
        ],
        current_session=3,
        visibility=visibility,
    )
    service.revision = ("systems", 2)
    assert baseline != _projection_key(
        record=record,
        service=service,
        page_records=page_records,
        current_session=3,
        visibility=visibility,
    )
    service.revision = ("systems", 1)
    assert baseline != _projection_key(
        record=record,
        service=service,
        page_records=page_records,
        current_session=4,
        visibility=visibility,
    )
    assert baseline != _projection_key(
        record=record,
        service=service,
        page_records=page_records,
        current_session=3,
        visibility={**visibility, "systems": "dm"},
    )


def test_projection_cache_key_normalizes_page_adapters_and_invalidates_materialization():
    service = _RevisionedSystemsService(("systems", 1))
    object_record = _body_record(
        "items/cache-item",
        "Cache Item",
        body="Cache body.",
    )
    object_record.page.subsection = "Treasures"
    object_record.page.summary = "Cache summary."
    object_record.metadata = {"item_mechanics": {"status": "approved"}}
    common_page = {
        "page_ref": "items/cache-item",
        "route_slug": "items/cache-item",
        "title": "Cache Item",
        "section": "Items",
        "subsection": "Treasures",
        "summary": "Cache summary.",
        "page_type": "item",
        "published": True,
        "reveal_after_session": 0,
    }
    record_level_dict = {
        "page_ref": "items/cache-item",
        "updated_at": object_record.updated_at,
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
        "updated_at": object_record.updated_at,
        "page": {
            **common_page,
            "metadata": {"item_mechanics": {"status": "approved"}},
            "body_markdown": "Cache body.",
            "content_loaded": True,
        },
    }

    object_key = _projection_key(
        service=service,
        page_records=[object_record],
    )
    assert _projection_key(
        service=service,
        page_records=[record_level_dict],
    ) == object_key
    assert _projection_key(
        service=service,
        page_records=[page_level_dict],
    ) == object_key

    changed_records = []
    for source in (object_record, record_level_dict, page_level_dict):
        changed = deepcopy(source)
        if isinstance(changed, dict) and "summary" in changed:
            changed["summary"] = "Changed summary."
        elif isinstance(changed, dict):
            changed["page"]["summary"] = "Changed summary."
        else:
            changed.page.summary = "Changed summary."
        changed_records.append(changed)

    changed_body = deepcopy(page_level_dict)
    changed_body["page"]["body_markdown"] = "Changed body."
    changed_content = deepcopy(page_level_dict)
    changed_content["page"]["content_loaded"] = False
    changed_metadata = deepcopy(page_level_dict)
    changed_metadata["page"]["metadata"] = {
        "item_mechanics": {"status": "approved", "bonus_weapon": 1}
    }
    for changed in (
        *changed_records,
        changed_body,
        changed_content,
        changed_metadata,
    ):
        assert _projection_key(
            service=service,
            page_records=[changed],
        ) != object_key


def test_projection_cache_disables_itself_without_exact_service_identity():
    assert _projection_key(service=_NonWeakSystemsService()) is None


def test_shell_and_header_projection_keys_share_one_request_revision_lookup():
    service = _RevisionedSystemsService(("systems", 1))
    record = _cache_record(definition={"name": "Arden"}, revision=4)
    page_records = [_cache_page_record()]
    visibility = {"campaign": "players", "characters": "players"}
    app = Flask(__name__)

    with app.test_request_context("/campaigns/linden-pass/characters/arden"):
        shell_key = build_character_read_projection_cache_key(
            "dnd-shell",
            campaign_slug="linden-pass",
            record=record,
            systems_service=service,
            campaign_page_records=page_records,
            campaign_current_session=3,
            effective_visibility=visibility,
        )
        header_key = build_character_read_projection_cache_key(
            "dnd-header-actions",
            campaign_slug="linden-pass",
            record=record,
            systems_service=service,
            campaign_page_records=page_records,
            campaign_current_session=3,
            effective_visibility=visibility,
        )

    assert shell_key is not None
    assert header_key is not None
    assert shell_key != header_key
    assert service.revision_calls == 1


def test_revision_aware_header_keys_force_one_rebuild_per_exact_variant():
    service = _RevisionedSystemsService(("systems", 1))
    visibility = {"campaign": "players", "characters": "players"}
    exact_inputs = [
        (_cache_record(definition={"name": "Arden"}, revision=1), [_cache_page_record()], 3, visibility),
        (_cache_record(definition={"name": "Arden Revised"}, revision=1), [_cache_page_record()], 3, visibility),
        (_cache_record(definition={"name": "Arden"}, revision=2), [_cache_page_record()], 3, visibility),
        (
            _cache_record(definition={"name": "Arden"}, revision=1),
            [_cache_page_record(updated_at="2026-08-11T12:01:00Z")],
            3,
            visibility,
        ),
        (_cache_record(definition={"name": "Arden"}, revision=1), [_cache_page_record()], 4, visibility),
        (
            _cache_record(definition={"name": "Arden"}, revision=1),
            [_cache_page_record()],
            3,
            {**visibility, "characters": "dm"},
        ),
    ]
    keys = [
        _projection_key(
            record=record,
            service=service,
            page_records=pages,
            current_session=current_session,
            visibility=effective_visibility,
        )
        for record, pages, current_session, effective_visibility in exact_inputs
    ]
    service.revision = ("systems", 2)
    keys.append(
        _projection_key(
            record=exact_inputs[0][0],
            service=service,
            page_records=exact_inputs[0][1],
            current_session=3,
            visibility=visibility,
        )
    )
    assert len(set(keys)) == len(keys)

    build_calls: list[int] = []
    for index, cache_key in enumerate(keys):
        assert load_cached_character_read_projection(
            cache_key,
            lambda index=index: build_calls.append(index) or {"variant": index},
        ) == {"variant": index}
    assert build_calls == list(range(len(keys)))
    for index, cache_key in enumerate(keys):
        assert load_cached_character_read_projection(
            cache_key,
            lambda: pytest.fail("an exact revision-aware cache hit rebuilt"),
        ) == {"variant": index}


def test_projection_cache_is_detached_and_single_flight():
    cache_key = ("single-flight",)
    builder_started = Event()
    release_builder = Event()
    build_calls: list[str] = []

    def build_projection():
        build_calls.append("build")
        builder_started.set()
        assert release_builder.wait(timeout=5)
        return {"value": [1, {"nested": "safe"}]}

    with ThreadPoolExecutor(max_workers=4) as executor:
        first = executor.submit(
            load_cached_character_read_projection,
            cache_key,
            build_projection,
        )
        assert builder_started.wait(timeout=5)
        followers = [
            executor.submit(
                load_cached_character_read_projection,
                cache_key,
                build_projection,
            )
            for _ in range(3)
        ]
        release_builder.set()
        results = [first.result(timeout=5), *[future.result(timeout=5) for future in followers]]

    assert build_calls == ["build"]
    assert results == [{"value": [1, {"nested": "safe"}]}] * 4
    results[0]["value"][1]["nested"] = "mutated"
    cached = load_cached_character_read_projection(
        cache_key,
        lambda: pytest.fail("detached cache lookup rebuilt the projection"),
    )
    assert cached == {"value": [1, {"nested": "safe"}]}


def test_projection_cache_errors_and_unsafe_values_never_poison_later_builds():
    cache_key = ("error-no-poison",)
    with pytest.raises(RuntimeError, match="first build failed"):
        load_cached_character_read_projection(
            cache_key,
            lambda: (_ for _ in ()).throw(RuntimeError("first build failed")),
        )
    assert load_cached_character_read_projection(
        cache_key,
        lambda: {"status": "recovered"},
    ) == {"status": "recovered"}

    unsafe_key = ("unsafe-no-poison",)
    with pytest.raises(TypeError, match="not safe"):
        load_cached_character_read_projection(
            unsafe_key,
            lambda: {"rendered_html": "<p>unsafe</p>"},
        )
    assert load_cached_character_read_projection(
        unsafe_key,
        lambda: {"status": "safe"},
    ) == {"status": "safe"}

    disguised_html_key = ("disguised-html-no-poison",)
    with pytest.raises(TypeError, match="rendered HTML or URL"):
        load_cached_character_read_projection(
            disguised_html_key,
            lambda: {"message": "<p>unsafe</p>"},
        )
    url_key = ("url-no-poison",)
    with pytest.raises(TypeError, match="rendered HTML or URL"):
        load_cached_character_read_projection(
            url_key,
            lambda: {"message": "/campaigns/private/characters/private"},
        )

    object_key = ("object-no-poison",)
    with pytest.raises(TypeError, match="unsupported cached value type"):
        load_cached_character_read_projection(
            object_key,
            lambda: {"value": SimpleNamespace(secret="not scalar metadata")},
        )
    assert load_cached_character_read_projection(
        object_key,
        lambda: {"status": "safe"},
    ) == {"status": "safe"}


def test_dnd_body_selector_uses_active_items_for_common_projection_and_state_only_refs():
    metadata_records = [
        _body_record("items/state-held", "State Held"),
        _body_record("items/inactive", "Inactive Item"),
        _body_record("items/active", "Active Item"),
        _body_record("items/unrelated", "Unrelated Item"),
    ]
    full_records = [
        _body_record(record.page_ref, record.page.title, body=f"{record.page.title} body")
        for record in metadata_records
    ]
    store = _BodyStore(full_records)
    definition = SimpleNamespace(
        features=[],
        spellcasting={},
        equipment_catalog=[
            {
                "id": "active",
                "name": "Active Item",
                "page_ref": "items/active",
                "default_quantity": 1,
            },
            {
                "id": "inactive",
                "name": "Inactive Item",
                "page_ref": "items/inactive",
                "default_quantity": 1,
            },
            {
                "id": "unrelated",
                "name": "Unrelated Item",
                "page_ref": "items/unrelated",
                "default_quantity": 1,
            },
        ],
    )
    state = {
        "inventory": [
            {"catalog_ref": "active", "quantity": 1, "is_equipped": True},
            {"catalog_ref": "inactive", "quantity": 1, "is_equipped": False},
            {
                "id": "state-held",
                "name": "State Held",
                "page_ref": "items/state-held",
                "quantity": 1,
                "is_equipped": True,
            },
        ]
    }

    projected = materialize_dnd_character_read_page_records(
        store,
        "linden-pass",
        metadata_records,
        definition,
        state,
        section="overview",
        campaign=_visible_campaign(),
    )

    assert store.calls == [
        ("items/state-held", True),
        ("items/active", True),
    ]
    assert [record.body_markdown for record in projected] == [
        "State Held body",
        "",
        "Active Item body",
        "",
    ]


def test_dnd_body_selector_notes_does_not_materialize_effective_inventory(
    monkeypatch,
):
    definition = SimpleNamespace(
        features=[],
        spellcasting={},
        equipment_catalog=[{"id": "unused", "default_quantity": 1}],
    )

    def fail_inventory_materialization(*_args, **_kwargs):
        raise AssertionError("Notes cannot consume inventory-backed page bodies")

    monkeypatch.setattr(
        page_records_module,
        "_effective_inventory_items",
        fail_inventory_materialization,
    )

    projected = materialize_dnd_character_read_page_records(
        _BodyStore([]),
        "linden-pass",
        [],
        definition,
        {"inventory": [{"catalog_ref": "unused", "quantity": 1}]},
        section="notes",
        campaign=_visible_campaign(),
    )

    assert projected == []


@pytest.mark.parametrize("section", ("quick", "equipment", "inventory"))
def test_dnd_body_selector_loads_all_carried_items_only_for_visible_item_surfaces(section):
    metadata_records = [
        _body_record("items/carried", "Carried Item"),
        _body_record("items/zero", "Zero Item"),
        _body_record("items/state-only", "State Only"),
    ]
    store = _BodyStore(
        [
            _body_record(record.page_ref, record.page.title, body=f"{record.page.title} body")
            for record in metadata_records
        ]
    )
    definition = SimpleNamespace(
        features=[],
        spellcasting={},
        equipment_catalog=[
            {
                "id": "carried",
                "name": "Carried Item",
                "page_ref": "items/carried",
                "default_quantity": 1,
            },
            {
                "id": "zero",
                "name": "Zero Item",
                "page_ref": "items/zero",
                "default_quantity": 1,
            },
        ],
    )
    state = {
        "inventory": [
            {"catalog_ref": "carried", "quantity": 1, "is_equipped": False},
            {"catalog_ref": "zero", "quantity": 0, "is_equipped": True},
            {
                "id": "state-only",
                "name": "State Only",
                "quantity": 2,
                "is_equipped": False,
            },
        ]
    }

    materialize_dnd_character_read_page_records(
        store,
        "linden-pass",
        metadata_records,
        definition,
        state,
        section=section,
        campaign=_visible_campaign(),
    )

    assert store.calls == [
        ("items/carried", True),
        ("items/zero", True),
        ("items/state-only", True),
    ]


def test_zero_quantity_state_uses_definition_default_for_exact_normal_quick_parity():
    metadata_records = [
        _body_record("items/zero-blade", "Zero Blade"),
        _body_record("items/unrelated", "Unrelated Item"),
    ]
    full_records = [
        _body_record(
            "items/zero-blade",
            "Zero Blade",
            body=(
                "*Weapon (longsword), rare*\n\n"
                "You gain a +2 bonus to attack and damage rolls made with this weapon."
            ),
        ),
        _body_record(
            "items/unrelated",
            "Unrelated Item",
            body="*Wondrous item, common*",
        ),
    ]
    record = _zero_quantity_weapon_record()

    class EmptyCatalogService:
        def list_enabled_entries_for_campaign(self, *_args, **_kwargs):
            return []

    service = EmptyCatalogService()
    full = present_character_detail(
        _quick_parity_campaign(),
        record,
        systems_service=service,
        campaign_page_records=full_records,
    )
    store = _BodyStore(full_records)
    scoped_page_records = materialize_dnd_character_read_page_records(
        store,
        "linden-pass",
        metadata_records,
        record.definition,
        record.state_record.state,
        section="quick",
        campaign=_visible_campaign(),
    )
    scoped = real_scoped_presenter(
        _quick_parity_campaign(),
        record,
        section="quick",
        systems_service=service,
        campaign_page_records=scoped_page_records,
    )

    assert store.calls == [("items/zero-blade", True)]
    assert {
        field: scoped[field] for field in scoped["projection_fields"]
    } == {
        field: full[field] for field in scoped["projection_fields"]
    }
    assert [
        row["name"] for row in [*full["attacks"], *full["hidden_attacks"]]
    ] == ["Zero Blade", "Zero Blade (two-handed)"]


def test_dnd_body_selector_unique_direct_ref_wins_without_title_overfetch():
    metadata_records = [
        _body_record("items/direct-a", "Direct A"),
        _body_record("items/title-b", "Title B"),
    ]
    store = _BodyStore(
        [
            _body_record("items/direct-a", "Direct A", body="Direct A body"),
            _body_record("items/title-b", "Title B", body="Title B body"),
        ]
    )
    definition = SimpleNamespace(
        features=[],
        spellcasting={},
        equipment_catalog=[
            {
                "id": "direct-a",
                "name": "Title B",
                "page_ref": "items/direct-a",
                "default_quantity": 1,
                "is_equipped": True,
            },
            {
                "id": "shared-title-fallback",
                "name": "Direct A",
                "default_quantity": 1,
                "is_equipped": True,
            },
        ],
    )

    projected = materialize_dnd_character_read_page_records(
        store,
        "linden-pass",
        metadata_records,
        definition,
        {},
        section="quick",
        campaign=_visible_campaign(),
    )

    assert store.calls == [("items/direct-a", True)]
    assert [record.body_markdown for record in projected] == ["Direct A body", ""]


def test_dnd_body_selector_uses_unique_title_when_direct_ref_is_ambiguous():
    metadata_records = [
        _body_record("items/direct-a", "Direct A"),
        _body_record("items/title-fallback", "Title Fallback"),
    ]
    for record in metadata_records:
        record.page.route_slug = "items/ambiguous-direct"
    store = _BodyStore(
        [
            _body_record("items/direct-a", "Direct A", body="Direct A body"),
            _body_record(
                "items/title-fallback",
                "Title Fallback",
                body="Title fallback body",
            ),
        ]
    )
    definition = SimpleNamespace(
        features=[],
        spellcasting={},
        equipment_catalog=[
            {
                "id": "ambiguous-direct",
                "name": "Title Fallback",
                "page_ref": "items/ambiguous-direct",
                "default_quantity": 1,
                "is_equipped": True,
            }
        ],
    )

    projected = materialize_dnd_character_read_page_records(
        store,
        "linden-pass",
        metadata_records,
        definition,
        {},
        section="quick",
        campaign=_visible_campaign(),
    )

    assert store.calls == [("items/title-fallback", True)]
    assert [record.body_markdown for record in projected] == [
        "",
        "Title fallback body",
    ]


def test_dnd_body_selector_loads_selected_feature_and_spell_refs_but_not_unrelated_bodies():
    metadata_records = [
        _body_record("mechanics/selected-feature", "Selected Feature", section="Mechanics"),
        _body_record("mechanics/unrelated-feature", "Unrelated Feature", section="Mechanics"),
        _body_record("spells/selected-spell", "Selected Spell", section="Spells"),
        _body_record("spells/unrelated-spell", "Unrelated Spell", section="Spells"),
    ]
    full_records = [
        _body_record(
            record.page_ref,
            record.page.title,
            section=record.page.section,
            body=f"{record.page.title} body",
        )
        for record in metadata_records
    ]
    definition = SimpleNamespace(
        features=[
            {"name": "Selected Feature", "page_ref": "mechanics/selected-feature"}
        ],
        spellcasting={
            "spells": [
                {"name": "Selected Spell", "page_ref": "spells/selected-spell"}
            ]
        },
        equipment_catalog=[],
    )

    feature_store = _BodyStore(full_records)
    materialize_dnd_character_read_page_records(
        feature_store,
        "linden-pass",
        metadata_records,
        definition,
        {},
        section="features",
        campaign=_visible_campaign(),
    )
    assert feature_store.calls == [("mechanics/selected-feature", True)]

    spell_store = _BodyStore(full_records)
    materialize_dnd_character_read_page_records(
        spell_store,
        "linden-pass",
        metadata_records,
        definition,
        {},
        section="spellcasting",
        campaign=_visible_campaign(),
    )
    assert spell_store.calls == [("spells/selected-spell", True)]


def test_dnd_body_selector_fails_closed_for_ambiguous_titles_and_visibility_drift():
    ambiguous_records = [
        _body_record("items/twin-a", "Twin Item"),
        _body_record("items/twin-b", "Twin Item"),
    ]
    ambiguous_store = _BodyStore(
        [
            _body_record(record.page_ref, record.page.title, body="ambiguous body")
            for record in ambiguous_records
        ]
    )
    definition = SimpleNamespace(
        features=[],
        spellcasting={},
        equipment_catalog=[
            {
                "id": "twin",
                "name": "Twin Item",
                "default_quantity": 1,
                "is_equipped": True,
            }
        ],
    )
    ambiguous = materialize_dnd_character_read_page_records(
        ambiguous_store,
        "linden-pass",
        ambiguous_records,
        definition,
        {},
        section="quick",
        campaign=_visible_campaign(),
    )
    assert ambiguous_store.calls == []
    assert all(not record.body_markdown for record in ambiguous)

    visible_metadata = [_body_record("items/drifted", "Drifted Item")]
    invisible_full = _body_record(
        "items/drifted",
        "Drifted Item",
        body="must not escape",
        published=False,
    )
    drift_store = _BodyStore([invisible_full])
    drift_definition = SimpleNamespace(
        features=[],
        spellcasting={},
        equipment_catalog=[
            {
                "id": "drifted",
                "name": "Drifted Item",
                "page_ref": "items/drifted",
                "default_quantity": 1,
                "is_equipped": True,
            }
        ],
    )
    drifted = materialize_dnd_character_read_page_records(
        drift_store,
        "linden-pass",
        visible_metadata,
        drift_definition,
        {},
        section="overview",
        campaign=_visible_campaign(),
    )
    assert drift_store.calls == [("items/drifted", True)]
    assert drifted == visible_metadata


def test_normal_dnd_read_selects_the_page_before_scoped_presentation(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    presented_sections: list[str] = []

    def scoped_presenter(*args, **kwargs):
        presented_sections.append(str(kwargs.get("section") or ""))
        return real_scoped_presenter(*args, **kwargs)

    monkeypatch.setattr(app_module, "present_character_detail", _fail_full_presenter)
    monkeypatch.setattr(
        app_module,
        "present_dnd_character_section",
        scoped_presenter,
        raising=False,
    )
    sign_in(users["dm"]["email"], users["dm"]["password"])

    selected = client.get(
        "/campaigns/linden-pass/characters/arden-march?mode=read&page=features"
    )

    assert selected.status_code == 200
    assert 'data-character-read-shell-page="features"' in selected.get_data(as_text=True)
    assert presented_sections == ["features"]


def test_warm_normal_dnd_quick_read_stays_within_frozen_query_ceiling(
    app,
    client,
    sign_in,
    users,
):
    app.config["LIVE_DIAGNOSTICS"] = True
    sign_in(users["dm"]["email"], users["dm"]["password"])

    first = client.get(
        "/campaigns/linden-pass/characters/arden-march?mode=read&page=quick"
    )
    warm = client.get(
        "/campaigns/linden-pass/characters/arden-march?mode=read&page=quick"
    )

    assert first.status_code == warm.status_code == 200
    warm_query_count = int(warm.headers["X-Character-Read-Query-Count"])
    assert warm_query_count <= 40


def test_noncasting_dnd_spellcasting_fallback_is_selected_before_presentation(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    presented_sections: list[str] = []

    def scoped_presenter(*args, **kwargs):
        presented_sections.append(str(kwargs.get("section") or ""))
        return real_scoped_presenter(*args, **kwargs)

    monkeypatch.setattr(app_module, "present_character_detail", _fail_full_presenter)
    monkeypatch.setattr(
        app_module,
        "present_dnd_character_section",
        scoped_presenter,
        raising=False,
    )
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get(
        "/campaigns/linden-pass/characters/tobin-slate?mode=read&page=spellcasting"
    )

    assert response.status_code == 200
    assert 'data-character-read-shell-page="quick"' in response.get_data(as_text=True)
    assert presented_sections == ["quick"]


def test_selected_feature_materializes_only_its_body_from_one_metadata_manifest(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    page_store = app.extensions["campaign_page_store"]
    with app.app_context():
        page_store.upsert_page(
            "linden-pass",
            "mechanics/selected-read-feature",
            metadata={
                "title": "Selected Read Feature",
                "section": "Mechanics",
                "type": "mechanic",
                "published": True,
            },
            body_markdown="Selected body marker.",
        )
        page_store.upsert_page(
            "linden-pass",
            "mechanics/unrelated-read-feature",
            metadata={
                "title": "Unrelated Read Feature",
                "section": "Mechanics",
                "type": "mechanic",
                "published": True,
            },
            body_markdown="Unrelated body marker.",
        )

    def mutate_definition(payload: dict) -> None:
        payload["features"] = [
            *list(payload.get("features") or []),
            {
                "id": "selected-read-feature",
                "name": "Selected Read Feature",
                "category": "custom_feature",
                "page_ref": "mechanics/selected-read-feature",
                "description_markdown": "",
            },
        ]

    _write_character_definition(app, "arden-march", mutate_definition)
    with app.app_context():
        app.extensions["repository_store"].refresh_from_database()

    original_list = page_store.list_page_records
    original_get = page_store.get_page_record
    manifest_calls: list[dict[str, object]] = []
    body_calls: list[tuple[str, bool]] = []

    def list_page_records(*args, **kwargs):
        manifest_calls.append(dict(kwargs))
        return original_list(*args, **kwargs)

    def get_page_record(_campaign_slug, page_ref, **kwargs):
        body_calls.append((str(page_ref), bool(kwargs.get("include_body"))))
        return original_get(_campaign_slug, page_ref, **kwargs)

    monkeypatch.setattr(page_store, "list_page_records", list_page_records)
    monkeypatch.setattr(page_store, "get_page_record", get_page_record)
    monkeypatch.setattr(
        app.extensions["player_wiki_reconciler"],
        "recover_pending",
        lambda **_kwargs: {"conflict": 0, "pending": 0},
    )
    sign_in(users["dm"]["email"], users["dm"]["password"])
    manifest_calls.clear()
    body_calls.clear()

    response = client.get(
        "/campaigns/linden-pass/characters/arden-march?mode=read&page=features"
    )

    assert response.status_code == 200
    assert manifest_calls == [{"include_body": False}]
    assert body_calls == [("mechanics/selected-read-feature", True)]
    html = response.get_data(as_text=True)
    assert "Selected body marker." in html
    assert "Unrelated body marker." not in html


@pytest.mark.parametrize(
    (
        "page",
        "expected_item_catalog_calls",
        "expected_spell_catalog_calls",
        "expected_scoped_item_catalog_calls",
        "expected_scoped_spell_catalog_calls",
        "expected_targeted_item_catalog_calls",
        "expected_targeted_spell_catalog_calls",
        "expected_spell_manager_calls",
        "expected_equipment_manager_calls",
    ),
    (
        ("overview", 0, 0, 0, 0, 0, 0, 0, 0),
        ("spells", 0, 1, 0, 1, 0, 1, 1, 0),
        ("resources", 0, 0, 0, 0, 0, 0, 0, 0),
        ("features", 0, 0, 0, 0, 0, 0, 0, 0),
        ("equipment", 0, 0, 1, 0, 1, 0, 0, 1),
        ("inventory", 0, 0, 1, 0, 0, 0, 0, 0),
        ("abilities_skills", 0, 0, 0, 0, 0, 0, 0, 0),
        ("notes", 0, 0, 0, 0, 0, 0, 0, 0),
        ("personal", 0, 0, 0, 0, 0, 0, 0, 0),
    ),
)
def test_session_dnd_selected_section_builds_only_its_presenter_catalog_and_manager(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    page,
    expected_item_catalog_calls,
    expected_spell_catalog_calls,
    expected_scoped_item_catalog_calls,
    expected_scoped_spell_catalog_calls,
    expected_targeted_item_catalog_calls,
    expected_targeted_spell_catalog_calls,
    expected_spell_manager_calls,
    expected_equipment_manager_calls,
):
    calls = {
        "presented": [],
        "item_catalog": 0,
        "spell_catalog": 0,
        "scoped_item_catalog": 0,
        "scoped_spell_catalog": 0,
        "targeted_item_catalog": 0,
        "targeted_spell_catalog": 0,
        "manager_full_entry_enumeration": 0,
        "systems_full_entry_enumeration": 0,
        "systems_bounded_availability": 0,
        "systems_bounded_identity": 0,
        "spell_manager": 0,
        "equipment_manager": 0,
    }
    real_item_catalog = app_module.build_shared_character_item_catalog
    real_spell_catalog = app_module._build_spell_catalog
    real_scoped_item_catalog = mechanics_module._build_scoped_item_catalog
    real_scoped_spell_catalog = mechanics_module._build_scoped_spell_catalog
    real_manager_full_entry_enumeration = app_module._list_campaign_enabled_entries
    systems_service = app.extensions["systems_service"]
    character_read_service = systems_service.character_read_view()
    systems_store = systems_service.store
    real_list_entries = systems_store.list_entries_for_campaign
    real_list_entries_by_identity = systems_store.list_entries_for_campaign_by_identity

    def scoped_presenter(*args, **kwargs):
        calls["presented"].append(str(kwargs.get("section") or ""))
        return real_scoped_presenter(*args, **kwargs)

    def item_catalog(*args, **kwargs):
        calls["item_catalog"] += 1
        return real_item_catalog(*args, **kwargs)

    def spell_catalog(*args, **kwargs):
        calls["spell_catalog"] += 1
        return real_spell_catalog(*args, **kwargs)

    def scoped_item_catalog(*args, **kwargs):
        calls["scoped_item_catalog"] += 1
        return real_scoped_item_catalog(*args, **kwargs)

    def scoped_spell_catalog(*args, **kwargs):
        calls["scoped_spell_catalog"] += 1
        return real_scoped_spell_catalog(*args, **kwargs)

    def manager_full_entry_enumeration(*args, **kwargs):
        calls["manager_full_entry_enumeration"] += 1
        return real_manager_full_entry_enumeration(*args, **kwargs)

    def list_entries(*args, **kwargs):
        if kwargs.get("entry_type") in {"item", "spell"}:
            if kwargs.get("limit") is None:
                calls["systems_full_entry_enumeration"] += 1
            else:
                calls["systems_bounded_availability"] += 1
        return real_list_entries(*args, **kwargs)

    def list_entries_by_identity(*args, **kwargs):
        calls["systems_bounded_identity"] += 1
        return real_list_entries_by_identity(*args, **kwargs)

    dependencies = app.extensions["character_route_dependencies"]
    builder = dependencies.build_campaign_session_character_page_context
    closure = dict(zip(builder.__code__.co_freevars, builder.__closure__))
    real_spell_manager = closure["build_character_spell_manager_context"].cell_contents
    real_equipment_manager = closure["build_character_equipment_state_context"].cell_contents
    real_targeted_item_catalog = closure[
        "build_session_character_equipment_manager_catalog"
    ].cell_contents
    real_targeted_spell_catalog = closure[
        "build_session_character_spell_manager_catalog"
    ].cell_contents

    def targeted_item_catalog(*args, **kwargs):
        calls["targeted_item_catalog"] += 1
        return real_targeted_item_catalog(*args, **kwargs)

    def targeted_spell_catalog(*args, **kwargs):
        calls["targeted_spell_catalog"] += 1
        return real_targeted_spell_catalog(*args, **kwargs)

    def spell_manager(*args, **kwargs):
        calls["spell_manager"] += 1
        return real_spell_manager(*args, **kwargs)

    def equipment_manager(*args, **kwargs):
        calls["equipment_manager"] += 1
        return real_equipment_manager(*args, **kwargs)

    monkeypatch.setattr(app_module, "present_character_detail", _fail_full_presenter)
    monkeypatch.setattr(app_module, "present_dnd_character_section", scoped_presenter)
    monkeypatch.setattr(app_module, "build_shared_character_item_catalog", item_catalog)
    monkeypatch.setattr(app_module, "_build_spell_catalog", spell_catalog)
    monkeypatch.setattr(mechanics_module, "_build_scoped_item_catalog", scoped_item_catalog)
    monkeypatch.setattr(mechanics_module, "_build_scoped_spell_catalog", scoped_spell_catalog)
    monkeypatch.setattr(
        app_module,
        "_list_campaign_enabled_entries",
        manager_full_entry_enumeration,
    )
    monkeypatch.setattr(
        systems_store,
        "list_entries_for_campaign",
        list_entries,
    )
    monkeypatch.setattr(
        systems_store,
        "list_entries_for_campaign_by_identity",
        list_entries_by_identity,
    )
    mechanics_module._clear_normalized_definition_cache()
    _replace_session_character_builder_dependency(
        app,
        monkeypatch,
        "build_session_character_equipment_manager_catalog",
        targeted_item_catalog,
    )
    _replace_session_character_builder_dependency(
        app,
        monkeypatch,
        "build_session_character_spell_manager_catalog",
        targeted_spell_catalog,
    )
    _replace_session_character_builder_dependency(
        app,
        monkeypatch,
        "build_character_spell_manager_context",
        spell_manager,
    )
    _replace_session_character_builder_dependency(
        app,
        monkeypatch,
        "build_character_equipment_state_context",
        equipment_manager,
    )
    if page == "spells":
        def unlink_spells(payload: dict) -> None:
            spellcasting = dict(payload.get("spellcasting") or {})
            spellcasting["spells"] = [
                {
                    **dict(spell or {}),
                    "systems_ref": None,
                }
                for spell in list(spellcasting.get("spells") or [])
            ]
            payload["spellcasting"] = spellcasting

        _write_character_definition(app, "arden-march", unlink_spells)
        with app.app_context():
            app.extensions["repository_store"].refresh_from_database()
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get(
        f"/campaigns/linden-pass/session/character?character=arden-march&page={page}&fragment=1"
    )

    assert response.status_code == 200
    assert calls == {
        "presented": [page],
        "item_catalog": expected_item_catalog_calls,
        "spell_catalog": expected_spell_catalog_calls,
        "scoped_item_catalog": expected_scoped_item_catalog_calls,
        "scoped_spell_catalog": expected_scoped_spell_catalog_calls,
        "targeted_item_catalog": expected_targeted_item_catalog_calls,
        "targeted_spell_catalog": expected_targeted_spell_catalog_calls,
        "manager_full_entry_enumeration": 0,
        "systems_full_entry_enumeration": expected_scoped_spell_catalog_calls,
        "systems_bounded_availability": 0,
        "systems_bounded_identity": 1,
        "spell_manager": expected_spell_manager_calls,
        "equipment_manager": expected_equipment_manager_calls,
    }


def test_session_notes_warm_projection_skips_targeted_item_identity_work(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    systems_store = app.extensions["systems_service"].store
    real_identity_batch = systems_store.list_entries_for_campaign_by_identity
    real_targeted_catalog = app_module._build_targeted_item_support_catalog
    real_navigation = app_module.build_dnd_session_section_navigation
    identity_calls: list[str] = []
    catalog_calls: list[str] = []
    navigation_counts: list[dict[str, int]] = []

    def identity_batch(*args, **kwargs):
        identity_calls.append(str(kwargs.get("entry_type") or ""))
        return real_identity_batch(*args, **kwargs)

    def targeted_catalog(*args, **kwargs):
        catalog_calls.append(str(kwargs.get("campaign_slug") or ""))
        return real_targeted_catalog(*args, **kwargs)

    def navigation(section_counts, **kwargs):
        navigation_counts.append(dict(section_counts))
        return real_navigation(section_counts, **kwargs)

    monkeypatch.setattr(
        systems_store,
        "list_entries_for_campaign_by_identity",
        identity_batch,
    )
    monkeypatch.setattr(
        app_module,
        "_build_targeted_item_support_catalog",
        targeted_catalog,
    )
    monkeypatch.setattr(
        app_module,
        "build_dnd_session_section_navigation",
        navigation,
    )
    sign_in(users["owner"]["email"], users["owner"]["password"])
    route = "/campaigns/linden-pass/session/character?character=arden-march"

    cold_notes = client.get(f"{route}&page=notes&fragment=1")
    assert cold_notes.status_code == 200
    assert catalog_calls == ["linden-pass"]
    assert identity_calls == ["item"]

    warm_notes = client.get(f"{route}&page=notes&fragment=1")
    assert warm_notes.status_code == 200
    assert catalog_calls == ["linden-pass"]
    assert identity_calls == ["item"]
    assert navigation_counts[:2] == [navigation_counts[0], navigation_counts[0]]
    assert set(navigation_counts[0]) == {
        "overview",
        "spells",
        "resources",
        "features",
        "equipment",
        "inventory",
        "abilities_skills",
        "notes",
        "personal",
    }

    equipment = client.get(f"{route}&page=equipment&fragment=1")
    inventory = client.get(f"{route}&page=inventory&fragment=1")
    assert equipment.status_code == inventory.status_code == 200
    assert catalog_calls == ["linden-pass"] * 3
    assert identity_calls == ["item"] * 3


def test_session_dnd_selected_feature_uses_one_metadata_scan_and_only_selected_bodies(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    page_store = app.extensions["campaign_page_store"]
    with app.app_context():
        page_store.upsert_page(
            "linden-pass",
            "mechanics/selected-session-feature",
            metadata={
                "title": "Selected Session Feature",
                "section": "Mechanics",
                "type": "mechanic",
                "published": True,
            },
            body_markdown="Selected Session body marker.",
        )
        page_store.upsert_page(
            "linden-pass",
            "mechanics/unrelated-session-feature",
            metadata={
                "title": "Unrelated Session Feature",
                "section": "Mechanics",
                "type": "mechanic",
                "published": True,
            },
            body_markdown="Unrelated Session body marker.",
        )

    def mutate_definition(payload: dict) -> None:
        payload["features"] = [
            *list(payload.get("features") or []),
            {
                "id": "selected-session-feature",
                "name": "Selected Session Feature",
                "category": "custom_feature",
                "page_ref": "mechanics/selected-session-feature",
                "description_markdown": "",
            },
        ]

    _write_character_definition(app, "arden-march", mutate_definition)
    with app.app_context():
        app.extensions["repository_store"].refresh_from_database()

    original_list = page_store.list_page_records
    original_get = page_store.get_page_record
    manifest_calls: list[dict[str, object]] = []
    body_calls: list[tuple[str, bool]] = []

    def list_page_records(*args, **kwargs):
        manifest_calls.append(dict(kwargs))
        return original_list(*args, **kwargs)

    def get_page_record(_campaign_slug, page_ref, **kwargs):
        body_calls.append((str(page_ref), bool(kwargs.get("include_body"))))
        return original_get(_campaign_slug, page_ref, **kwargs)

    monkeypatch.setattr(page_store, "list_page_records", list_page_records)
    monkeypatch.setattr(page_store, "get_page_record", get_page_record)
    monkeypatch.setattr(
        app.extensions["player_wiki_reconciler"],
        "recover_pending",
        lambda **_kwargs: {"conflict": 0, "pending": 0},
    )
    sign_in(users["dm"]["email"], users["dm"]["password"])
    manifest_calls.clear()
    body_calls.clear()

    response = client.get(
        "/campaigns/linden-pass/session/character"
        "?character=arden-march&page=features&fragment=1"
    )

    assert response.status_code == 200
    assert manifest_calls == [{"include_body": False}]
    assert body_calls == [("mechanics/selected-session-feature", True)]
    html = response.get_data(as_text=True)
    assert "Selected Session body marker." in html
    assert "Unrelated Session body marker." not in html


def test_session_dnd_equipment_navigation_count_is_canonical_across_selected_sections(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    lightweight_counts = []
    manager_row_counts = []
    real_navigation = app_module.build_dnd_session_section_navigation
    dependencies = app.extensions["character_route_dependencies"]
    builder = dependencies.build_campaign_session_character_page_context
    closure = dict(zip(builder.__code__.co_freevars, builder.__closure__))
    real_equipment_manager = closure["build_character_equipment_state_context"].cell_contents

    def navigation(*args, **kwargs):
        lightweight_counts.append(int(kwargs.get("equipment_state_row_count") or 0))
        return real_navigation(*args, **kwargs)

    def equipment_manager(*args, **kwargs):
        manager = real_equipment_manager(*args, **kwargs)
        manager_row_counts.append(len(list((manager or {}).get("rows") or [])))
        return manager

    monkeypatch.setattr(app_module, "build_dnd_session_section_navigation", navigation)
    _replace_session_character_builder_dependency(
        app,
        monkeypatch,
        "build_character_equipment_state_context",
        equipment_manager,
    )
    sign_in(users["dm"]["email"], users["dm"]["password"])

    overview = client.get(
        "/campaigns/linden-pass/session/character"
        "?character=arden-march&page=overview&fragment=1"
    )
    equipment = client.get(
        "/campaigns/linden-pass/session/character"
        "?character=arden-march&page=equipment&fragment=1"
    )

    assert overview.status_code == 200
    assert equipment.status_code == 200
    assert lightweight_counts == [manager_row_counts[0], manager_row_counts[0]]
    assert manager_row_counts and manager_row_counts[0] > 0


def test_session_equipment_support_uses_exact_item_key_and_fails_closed_on_duplicate_title(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    systems_service = app.extensions["systems_service"]
    store = systems_service.store
    keyed = _systems_item("item|keyed-relic", "shared-relic", "Shared Relic")
    conflicting = _systems_item(
        "item|conflicting-relic",
        "shared-relic",
        "Shared Relic",
    )
    keyed.metadata = {"rarity": "rare"}
    conflicting.metadata = {}

    def identity_batch(*_args, **_kwargs):
        return [keyed, conflicting]

    monkeypatch.setattr(store, "list_entries_for_campaign_by_identity", identity_batch)

    def mutate_definition(payload: dict) -> None:
        payload["equipment_catalog"] = [
            {
                "id": "keyed-relic-1",
                "name": "Shared Relic",
                "default_quantity": 1,
                "is_equipped": True,
                "systems_ref": {
                    "entry_key": "item|keyed-relic",
                    "slug": "shared-relic",
                    "title": "Shared Relic",
                },
            },
            {
                "id": "ambiguous-relic-2",
                "name": "Shared Relic",
                "default_quantity": 1,
                "is_equipped": True,
                "systems_ref": {"slug": "shared-relic"},
            },
        ]

    _write_character_definition(app, "arden-march", mutate_definition)
    with app.app_context():
        app.extensions["repository_store"].refresh_from_database()

    captured_support: list[dict[str, dict[str, object]]] = []
    captured_catalogs: list[dict[str, object]] = []
    real_support_lookup = app_module.build_record_equipment_support_lookup

    def support_lookup(*args, **kwargs):
        captured_catalogs.append(dict(kwargs.get("item_catalog") or {}))
        definition_lookup, support = real_support_lookup(*args, **kwargs)
        captured_support.append(dict(support))
        return definition_lookup, support

    monkeypatch.setattr(
        app_module,
        "build_record_equipment_support_lookup",
        support_lookup,
    )
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get(
        "/campaigns/linden-pass/session/character"
        "?character=arden-march&page=equipment&fragment=1"
    )

    assert response.status_code == 200
    assert captured_support
    assert captured_catalogs
    latest_catalog = captured_catalogs[-1]
    assert {
        entry.entry_key for entry in list(latest_catalog.get("entries") or [])
    } == {keyed.entry_key, conflicting.entry_key}
    assert latest_catalog.get("by_slug") == {}
    latest_support = captured_support[-1]
    assert latest_support["keyed-relic-1"]["supports_equipped_state"] is True
    assert latest_support["ambiguous-relic-2"]["supports_equipped_state"] is False


@pytest.mark.parametrize(
    ("page", "document_byte_ceiling"),
    (
        ("overview", 74117),
        ("spells", 74098),
        ("resources", 74123),
        ("features", 74106),
        ("equipment", 74112),
        ("inventory", 74112),
        ("notes", 74090),
    ),
)
def test_session_dnd_selected_reads_meet_frozen_query_and_document_byte_ceilings(
    app,
    client,
    sign_in,
    users,
    page,
    document_byte_ceiling,
):
    app.config["LIVE_DIAGNOSTICS"] = True
    sign_in(users["owner"]["email"], users["owner"]["password"])
    route = (
        "/campaigns/linden-pass/session/character"
        f"?character=arden-march&page={page}"
    )

    client.get(f"{route}&fragment=1")
    fragment = client.get(f"{route}&fragment=1")
    client.get(route)
    document = client.get(route)

    assert fragment.status_code == document.status_code == 200
    assert int(fragment.headers["X-Character-Read-Query-Count"]) <= 24
    assert int(document.headers["X-Character-Read-Query-Count"]) <= 39
    assert len(document.get_data()) <= document_byte_ceiling


def test_identical_session_character_reads_reuse_stable_projection_and_query_ceiling(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    app.config["LIVE_DIAGNOSTICS"] = True
    systems_service = app.extensions["systems_service"]
    assert systems_service.character_read_view() is systems_service.character_read_view()
    builds = []
    real_shell_projection = app_module.build_dnd_character_read_shell_projection

    def tracked_shell_projection(*args, **kwargs):
        builds.append(1)
        return real_shell_projection(*args, **kwargs)

    with app.app_context():
        assert systems_service.ensure_builtin_library_seeded("DND-5E") is not None
    sign_in(users["owner"]["email"], users["owner"]["password"])
    route = (
        "/campaigns/linden-pass/session/character"
        "?character=arden-march&page=overview&fragment=1"
    )
    warm = client.get(route)
    assert warm.status_code == 200
    reset_character_read_projection_cache_for_tests()
    monkeypatch.setattr(
        app_module,
        "build_dnd_character_read_shell_projection",
        tracked_shell_projection,
    )

    first = client.get(route)
    second = client.get(route)

    assert first.status_code == second.status_code == 200
    assert builds == [1]
    assert int(first.headers["X-Character-Read-Query-Count"]) <= 24
    assert int(second.headers["X-Character-Read-Query-Count"]) <= 24


def test_session_character_badge_does_not_enumerate_visible_message_bodies(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    session_service = app.extensions["campaign_session_service"]

    sign_in(users["dm"]["email"], users["dm"]["password"])
    start = client.post(
        "/campaigns/linden-pass/session/start",
        follow_redirects=False,
    )
    assert start.status_code == 302

    def fail_message_enumeration(*_args, **_kwargs):
        raise AssertionError("Session Character must not load message bodies for a badge")

    monkeypatch.setattr(session_service, "list_messages", fail_message_enumeration)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get(
        "/campaigns/linden-pass/session/character"
        "?character=arden-march&page=overview&fragment=1"
    )

    assert response.status_code == 200


@pytest.mark.parametrize("page", ("spells", "equipment"))
def test_session_selected_manager_reuses_one_batched_systems_enumeration(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    page,
):
    systems_service = app.extensions["systems_service"]
    store = systems_service.store
    original_list = store.list_entries_for_campaign
    original_identity_list = store.list_entries_for_campaign_by_identity
    list_calls = []
    identity_calls = []

    def list_entries(*args, **kwargs):
        if kwargs.get("entry_type") in {"item", "spell"}:
            list_calls.append((kwargs.get("entry_type"), kwargs.get("limit")))
        return original_list(*args, **kwargs)

    def list_entries_by_identity(*args, **kwargs):
        identity_calls.append(
            (
                kwargs.get("entry_type"),
                tuple(kwargs.get("entry_keys") or ()),
                tuple(kwargs.get("entry_slugs") or ()),
                tuple(kwargs.get("exact_titles") or ()),
            )
        )
        return original_identity_list(*args, **kwargs)

    monkeypatch.setattr(store, "list_entries_for_campaign", list_entries)
    monkeypatch.setattr(
        store,
        "list_entries_for_campaign_by_identity",
        list_entries_by_identity,
    )
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get(
        "/campaigns/linden-pass/session/character"
        f"?character=arden-march&page={page}&fragment=1"
    )

    assert response.status_code == 200
    assert list_calls == ([('spell', None)] if page == "spells" else [])
    assert len(identity_calls) == 1
    assert identity_calls[0][0] == "item"
    assert any(identity_calls[0][1:])


def test_targeted_spell_manager_resolves_entry_key_without_publishing_ambiguous_title():
    first = SimpleNamespace(
        entry_type="spell",
        entry_key="spell|first",
        slug="first-echo",
        title="Echo",
        source_id="PHB",
    )
    second = SimpleNamespace(
        entry_type="spell",
        entry_key="spell|second",
        slug="second-echo",
        title="Echo",
        source_id="XGE",
    )
    definition = SimpleNamespace(
        spellcasting={
            "spells": [
                {
                    "name": "Echo",
                    "systems_ref": {
                        "entry_key": "spell|second",
                        "slug": "first-echo",
                    },
                },
                {"name": "Echo", "systems_ref": {}},
            ]
        }
    )

    catalog = app_module._build_targeted_spell_manager_catalog(
        definition,
        [first, second],
    )

    assert catalog["entries"] == [second]
    assert catalog["by_entry_key"] == {"spell|second": second}
    assert catalog["by_title"] == {}
    exact_payload = definition.spellcasting["spells"][0]
    title_only_payload = definition.spellcasting["spells"][1]
    assert _resolve_spell_payload_entry(exact_payload, catalog) is second
    assert _resolve_spell_payload_entry(title_only_payload, catalog) is None


def test_targeted_spell_manager_fails_closed_on_ambiguous_title_without_exact_ref():
    first = SimpleNamespace(
        entry_type="spell",
        entry_key="spell|first",
        slug="first-echo",
        title="Echo",
        source_id="PHB",
    )
    second = SimpleNamespace(
        entry_type="spell",
        entry_key="spell|second",
        slug="second-echo",
        title="Echo",
        source_id="XGE",
    )
    definition = SimpleNamespace(
        spellcasting={"spells": [{"name": "Echo", "systems_ref": {}}]}
    )

    catalog = app_module._build_targeted_spell_manager_catalog(
        definition,
        [first, second],
    )

    assert catalog["entries"] == []
    assert catalog["by_title"] == {}


def test_exact_key_spell_reaches_manager_and_progression_without_resolving_title_duplicate():
    first = SimpleNamespace(
        entry_type="spell",
        entry_key="spell|first",
        slug="stale-echo",
        title="Echo",
        source_id="PHB",
        source_page="",
        metadata={"level": 1, "class_lists": {"PHB": ["Wizard"]}},
    )
    second = SimpleNamespace(
        entry_type="spell",
        entry_key="spell|second",
        slug="stale-echo",
        title="Echo",
        source_id="XGE",
        source_page="",
        metadata={"level": 2, "class_lists": {"XGE": ["Artificer"]}},
    )
    exact_payload = {
        "name": "Echo",
        "mark": "Prepared",
        "class_row_id": "class-row-1",
        "systems_ref": {"entry_key": "spell|second", "slug": "stale-echo"},
    }
    legacy_slug_payload = {
        "name": "Legacy Echo",
        "mark": "Prepared",
        "class_row_id": "class-row-1",
        "systems_ref": {"slug": "stale-echo"},
    }
    definition = CharacterDefinition(
        campaign_slug="linden-pass",
        character_slug="echo-caster",
        name="Echo Caster",
        status="active",
        profile={
            "class_level_text": "Artificer 5",
            "classes": [{"row_id": "class-row-1", "class_name": "Artificer", "level": 5}],
        },
        stats={"proficiency_bonus": 3, "ability_scores": {"int": {"score": 16, "modifier": 3}}},
        skills=[],
        proficiencies={},
        attacks=[],
        features=[],
        spellcasting={
            "spellcasting_class": "Artificer",
            "spellcasting_ability": "Intelligence",
            "class_rows": [{
                "class_row_id": "class-row-1",
                "class_name": "Artificer",
                "level": 5,
                "spell_mode": "prepared",
                "spellcasting_ability": "Intelligence",
            }],
            "spells": [exact_payload, legacy_slug_payload],
        },
        equipment_catalog=[],
        reference_notes={},
        resource_templates=[],
        source={},
    )
    catalog = app_module._build_targeted_spell_manager_catalog(
        SimpleNamespace(spellcasting={"spells": [exact_payload, legacy_slug_payload]}),
        [first, second],
    )

    assert catalog["by_slug"] == {}
    assert _resolve_spell_payload_entry(exact_payload, catalog) is second
    assert _resolve_spell_payload_entry(legacy_slug_payload, catalog) is None
    manager = build_character_spell_management_context(definition, spell_catalog=catalog)
    rows = list(dict((manager or {}).get("sections", [])[0]).get("rows") or [])

    assert sorted((row["spell_level"], row["name"]) for row in rows) == [
        (0, "Legacy Echo"),
        (2, "Echo"),
    ]
    contexts = [
        {"row_id": "wizard", "class_name": "Wizard", "spell_list_class_name": "Wizard"},
        {"row_id": "artificer", "class_name": "Artificer", "spell_list_class_name": "Artificer"},
    ]
    assert _imported_spell_candidate_row_ids(
        exact_payload,
        spell_row_contexts=contexts,
        spell_catalog=catalog,
    ) == ["artificer"]
    assert _imported_spell_candidate_row_ids(
        legacy_slug_payload,
        spell_row_contexts=contexts,
        spell_catalog=catalog,
    ) == ["wizard", "artificer"]


def test_spell_normalization_preserves_distinct_entry_keys_with_stale_shared_slug():
    payloads = [
        {
            "name": "Echo",
            "mark": "Known",
            "systems_ref": {"entry_key": "spell|first", "slug": "stale-echo"},
        },
        {
            "name": "Echo",
            "mark": "Known",
            "systems_ref": {"entry_key": "spell|second", "slug": "stale-echo"},
        },
        {"name": "Echo", "mark": "Known", "systems_ref": {}},
    ]

    normalized = _normalize_spell_payloads(payloads)
    assigned = _assign_spell_payload_class_rows(
        payloads,
        spellcasting_rows=[{"class_row_id": "class-row-1"}],
    )

    assert len(normalized) == 3
    assert len(assigned) == 3
    assert {
        str(dict(payload.get("systems_ref") or {}).get("entry_key") or "title-only")
        for payload in assigned
    } == {"spell|first", "spell|second", "title-only"}
    assert len({_spell_payload_map_key(payload) for payload in assigned}) == 3
    assert _spell_payload_key(payloads[0]) == "stale-echo"
    assert _spell_selection_values_by_mark(payloads, "Known") == {"stale-echo", "Echo"}


def test_spell_management_update_targets_exact_entry_key_without_dropping_duplicates(
    monkeypatch,
):
    first = SimpleNamespace(
        entry_type="spell",
        entry_key="spell|first",
        slug="stale-echo",
        title="Echo",
        source_id="PHB",
        source_page="",
        metadata={"level": 1, "class_lists": {"PHB": ["Artificer"]}},
    )
    second = SimpleNamespace(
        entry_type="spell",
        entry_key="spell|second",
        slug="stale-echo",
        title="Echo",
        source_id="XGE",
        source_page="",
        metadata={"level": 1, "class_lists": {"XGE": ["Artificer"]}},
    )
    payloads = [
        {
            "name": "Echo",
            "mark": "",
            "class_row_id": "class-row-1",
            "systems_ref": {"entry_key": "spell|first", "slug": "stale-echo"},
        },
        {
            "name": "Echo",
            "mark": "Prepared",
            "class_row_id": "class-row-1",
            "systems_ref": {"entry_key": "spell|second", "slug": "stale-echo"},
        },
        {
            "name": "Echo",
            "level": 1,
            "mark": "",
            "class_row_id": "class-row-1",
            "systems_ref": {},
        },
    ]
    definition = CharacterDefinition(
        campaign_slug="linden-pass",
        character_slug="echo-caster",
        name="Echo Caster",
        status="active",
        profile={
            "class_level_text": "Artificer 5",
            "classes": [
                {"row_id": "class-row-1", "class_name": "Artificer", "level": 5}
            ],
        },
        stats={
            "proficiency_bonus": 3,
            "ability_scores": {"intelligence": {"score": 16, "modifier": 3}},
        },
        skills=[],
        proficiencies={},
        attacks=[],
        features=[],
        spellcasting={
            "spellcasting_class": "Artificer",
            "spellcasting_ability": "Intelligence",
            "class_rows": [
                {
                    "class_row_id": "class-row-1",
                    "class_name": "Artificer",
                    "level": 5,
                    "spell_mode": "prepared",
                    "spellcasting_ability": "Intelligence",
                }
            ],
            "spells": payloads,
        },
        equipment_catalog=[],
        reference_notes={},
        resource_templates=[],
        source={"source_type": "native_character_builder"},
    )
    catalog = {
        "entries": [first, second],
        "by_entry_key": {"spell|first": first, "spell|second": second},
        "by_slug": {"stale-echo": first},
        "by_title": {},
    }
    manager = build_character_spell_management_context(definition, spell_catalog=catalog)
    rows = list(dict((manager or {}).get("sections", [])[0]).get("rows") or [])

    assert len(rows) == 3
    target_key = next(
        row["spell_key"]
        for row in rows
        if dict(row["payload"].get("systems_ref") or {}).get("entry_key")
        == "spell|second"
    )
    monkeypatch.setattr(
        editor_module,
        "normalize_definition_to_native_model",
        lambda current_definition, **_kwargs: current_definition,
    )
    updated, _, _ = apply_character_spell_management_edit(
        "linden-pass",
        definition,
        CharacterImportMetadata(
            campaign_slug="linden-pass",
            character_slug="echo-caster",
            source_path="test",
            imported_at_utc="",
            parser_version="test",
            import_status="ok",
            warnings=[],
        ),
        spell_catalog=catalog,
        operation="update",
        spell_key=target_key,
        prepared_value="0",
        target_class_row_id="class-row-1",
    )

    updated_spells = list((updated.spellcasting or {}).get("spells") or [])
    assert len(updated_spells) == 3
    by_entry_key = {
        str(dict(payload.get("systems_ref") or {}).get("entry_key") or "title-only"):
        payload
        for payload in updated_spells
    }
    assert str(by_entry_key["spell|first"].get("mark") or "") == ""
    assert str(by_entry_key["spell|second"].get("mark") or "") == ""
    assert str(by_entry_key["title-only"].get("mark") or "") == ""
    assert _resolve_spell_payload_entry(by_entry_key["title-only"], catalog) is None


@pytest.mark.parametrize("operation", ["remove", "update"])
def test_spell_management_legacy_shared_slug_mutation_fails_closed(operation):
    first = SimpleNamespace(
        entry_type="spell",
        entry_key="spell|first",
        slug="stale-echo",
        title="First Echo",
        source_id="PHB",
        source_page="",
        metadata={"level": 1, "class_lists": {"PHB": ["Artificer"]}},
    )
    second = SimpleNamespace(
        entry_type="spell",
        entry_key="spell|second",
        slug="stale-echo",
        title="Second Echo",
        source_id="XGE",
        source_page="",
        metadata={"level": 1, "class_lists": {"XGE": ["Artificer"]}},
    )
    definition = CharacterDefinition(
        campaign_slug="linden-pass",
        character_slug="echo-caster",
        name="Echo Caster",
        status="active",
        profile={
            "class_level_text": "Artificer 5",
            "classes": [
                {"row_id": "class-row-1", "class_name": "Artificer", "level": 5}
            ],
        },
        stats={
            "proficiency_bonus": 3,
            "ability_scores": {"intelligence": {"score": 16, "modifier": 3}},
        },
        skills=[],
        proficiencies={},
        attacks=[],
        features=[],
        spellcasting={
            "spellcasting_class": "Artificer",
            "spellcasting_ability": "Intelligence",
            "class_rows": [
                {
                    "class_row_id": "class-row-1",
                    "class_name": "Artificer",
                    "level": 5,
                    "spell_mode": "prepared",
                    "spellcasting_ability": "Intelligence",
                }
            ],
            "spells": [
                {
                    "name": first.title,
                    "mark": "Prepared",
                    "class_row_id": "class-row-1",
                    "systems_ref": {"entry_key": first.entry_key, "slug": first.slug},
                },
                {
                    "name": second.title,
                    "mark": "Prepared",
                    "class_row_id": "class-row-1",
                    "systems_ref": {"entry_key": second.entry_key, "slug": second.slug},
                },
            ],
        },
        equipment_catalog=[],
        reference_notes={},
        resource_templates=[],
        source={"source_type": "native_character_builder"},
    )
    catalog = {
        "entries": [first, second],
        "by_entry_key": {first.entry_key: first, second.entry_key: second},
        "by_slug": {},
        "by_title": {},
    }
    original_definition = deepcopy(definition.to_dict())

    with pytest.raises(
        editor_module.CharacterEditValidationError,
        match=rf"Choose a valid spell to {operation}",
    ):
        apply_character_spell_management_edit(
            "linden-pass",
            definition,
            CharacterImportMetadata(
                campaign_slug="linden-pass",
                character_slug="echo-caster",
                source_path="test",
                imported_at_utc="",
                parser_version="test",
                import_status="ok",
                warnings=[],
            ),
            spell_catalog=catalog,
            operation=operation,
            spell_key="stale-echo",
            prepared_value="0",
            target_class_row_id="class-row-1",
        )
    assert definition.to_dict() == original_definition


def test_campaign_option_spell_replacement_uses_exact_durable_map_identity():
    original = _systems_spell(
        "spell|original",
        "stale-echo",
        "Original Echo",
    )
    conflicting = _systems_spell(
        "spell|conflicting",
        "stale-echo",
        "Conflicting Echo",
        source_id="XGE",
    )
    replacement = _systems_spell(
        "spell|replacement",
        "replacement-echo",
        "Replacement Echo",
    )
    catalog = _build_spell_catalog([original, conflicting, replacement])
    assert "stale-echo" not in catalog["by_slug"]
    current_spellcasting = {
        "spells": [
            {
                "name": "Original Echo",
                "mark": "Known",
                "systems_ref": {
                    "entry_key": "spell|original",
                    "slug": "stale-echo",
                },
                "class_row_id": "class-row-1",
            },
            {
                "name": "Conflicting Echo",
                "mark": "Known",
                "systems_ref": {
                    "entry_key": "spell|conflicting",
                    "slug": "stale-echo",
                },
                "class_row_id": "class-row-1",
            },
        ]
    }
    option = {
        "spell_support": [
            {
                "replacement": {
                    "_": [
                        {
                            "kind": "known",
                            "from": {"filter": "level=1"},
                            "to": {"options": ["Replacement Echo"]},
                        }
                    ]
                }
            }
        ]
    }
    entry = {
        "field_prefix": "exact_spell_support",
        "source_ref": "mechanics/exact-replacement",
        "campaign_option": option,
    }
    values = {
        "exact_spell_support_replace_known_1_from_1": "spell|conflicting",
        "exact_spell_support_replace_known_1_to_1": "replacement-echo",
    }
    replacement_fields = editor_module._build_editor_spell_support_replacement_fields_for_entry(
        entry=entry,
        existing_spells=list(current_spellcasting["spells"]),
        spell_catalog=catalog,
        values=values,
        current_level=5,
    )
    assert [field["name"] for field in replacement_fields] == [
        "exact_spell_support_replace_known_1_from_1",
        "exact_spell_support_replace_known_1_to_1",
    ]
    assert replacement_fields[0]["options"] == [
        {"label": "Original Echo", "value": "spell|original"},
        {"label": "Conflicting Echo", "value": "spell|conflicting"},
    ]
    assert replacement_fields[0]["selected"] == "spell|conflicting"

    granted = editor_module._apply_campaign_option_spells_to_spellcasting(
        current_spellcasting,
        existing_campaign_option_payloads=[],
        selected_campaign_option_payloads=[
            {
                "page_ref": "mechanics/exact-grant",
                "spells": [{"value": "spell|original", "mark": "Granted"}],
            }
        ],
        spell_catalog=catalog,
        values={},
        current_level=5,
    )
    granted_spells = list(granted.get("spells") or [])
    assert len(granted_spells) == 2
    granted_by_key = {
        dict(payload.get("systems_ref") or {}).get("entry_key"): payload
        for payload in granted_spells
    }
    assert "Granted" in str(granted_by_key["spell|original"].get("mark") or "")
    assert granted_by_key["spell|original"]["class_row_id"] == "class-row-1"

    updated = editor_module._apply_campaign_option_spells_to_spellcasting(
        current_spellcasting,
        existing_campaign_option_payloads=[],
        selected_campaign_option_payloads=[],
        spell_catalog=catalog,
        values=values,
        current_level=5,
        selected_spell_support_entries=[entry],
    )

    visible = list(updated.get("spells") or [])
    hidden = list(updated.get("campaign_option_replacement_bases") or [])
    assert [
        dict(payload.get("systems_ref") or {}).get("entry_key")
        for payload in visible
    ] == ["spell|original", "spell|replacement"]
    assert [
        dict(payload.get("systems_ref") or {}).get("entry_key")
        for payload in hidden
    ] == ["spell|conflicting"]
    assert len(visible) + len(hidden) == 3

    row_entry = {
        **entry,
        "field_prefix": "custom_feature_spell_support_1",
    }
    reopened_fields = editor_module._build_editor_spell_support_replacement_fields_for_row(
        row={"index": 1, "page_ref": entry["source_ref"], "campaign_option": option},
        tracked_spell_payloads=editor_module._campaign_option_tracked_spell_payloads(updated),
        provisional_spell_payloads=editor_module._campaign_option_tracked_spell_payloads(updated),
        spell_catalog=catalog,
        values={},
        current_level=5,
    )
    assert reopened_fields[0]["selected"] == "spell|conflicting"
    assert reopened_fields[1]["selected"] == "replacement-echo"

    resaved = editor_module._apply_campaign_option_spells_to_spellcasting(
        updated,
        existing_campaign_option_payloads=[option],
        selected_campaign_option_payloads=[option],
        spell_catalog=catalog,
        values={
            field["name"]: field["selected"]
            for field in reopened_fields
            if str(field.get("selected") or "").strip()
        },
        current_level=5,
        selected_spell_support_entries=[row_entry],
    )
    assert [
        dict(payload.get("systems_ref") or {}).get("entry_key")
        for payload in list(resaved.get("campaign_option_replacement_bases") or [])
    ] == ["spell|conflicting"]

    restored = editor_module._apply_campaign_option_spells_to_spellcasting(
        updated,
        existing_campaign_option_payloads=[option],
        selected_campaign_option_payloads=[],
        spell_catalog=catalog,
        values={},
        current_level=5,
        selected_spell_support_entries=[],
    )
    assert {
        dict(payload.get("systems_ref") or {}).get("entry_key")
        for payload in list(restored.get("spells") or [])
    } == {"spell|original", "spell|conflicting"}
    assert not list(restored.get("campaign_option_replacement_bases") or [])


def test_campaign_option_spell_resave_preserves_exact_base_across_legacy_grant_alias():
    base_entry = _systems_spell(
        "spell|exact-base",
        "legacy-base-slug",
        "Exact Base",
    )
    catalog = _build_spell_catalog([base_entry])
    option = {
        "page_ref": "mechanics/legacy-grant",
        "spells": [{"value": base_entry.slug, "mark": "Granted"}],
    }
    current_spellcasting = {
        "spells": [
            {
                "name": base_entry.title,
                "mark": "Known",
                "systems_ref": {
                    "entry_key": base_entry.entry_key,
                    "entry_type": base_entry.entry_type,
                    "title": base_entry.title,
                    "slug": base_entry.slug,
                    "source_id": base_entry.source_id,
                },
                "class_row_id": "class-row-1",
                "has_base_spell": True,
            },
            {
                "name": base_entry.title,
                "mark": "Granted",
                "systems_ref": {"slug": base_entry.slug},
                "has_base_spell": False,
                "campaign_option_sources": [
                    {
                        "source_ref": option["page_ref"],
                        "mode": "legacy_grant",
                        "mark": "Granted",
                    }
                ],
            },
        ]
    }

    resaved = editor_module._apply_campaign_option_spells_to_spellcasting(
        current_spellcasting,
        existing_campaign_option_payloads=[option],
        selected_campaign_option_payloads=[option],
        spell_catalog=catalog,
        values={},
        current_level=5,
    )
    resaved_spells = list(resaved.get("spells") or [])
    assert len(resaved_spells) == 1
    assert resaved_spells[0]["has_base_spell"] is True
    assert resaved_spells[0]["class_row_id"] == "class-row-1"
    assert dict(resaved_spells[0].get("systems_ref") or {}).get(
        "entry_key"
    ) == base_entry.entry_key

    deselected = editor_module._apply_campaign_option_spells_to_spellcasting(
        resaved,
        existing_campaign_option_payloads=[option],
        selected_campaign_option_payloads=[],
        spell_catalog=catalog,
        values={},
        current_level=5,
    )
    deselected_spells = list(deselected.get("spells") or [])
    assert len(deselected_spells) == 1
    assert deselected_spells[0]["has_base_spell"] is True
    assert deselected_spells[0]["class_row_id"] == "class-row-1"
    assert dict(deselected_spells[0].get("systems_ref") or {}).get(
        "entry_key"
    ) == base_entry.entry_key
    assert not list(deselected_spells[0].get("campaign_option_sources") or [])


def test_campaign_option_structured_replacement_hides_and_restores_orphan_legacy_slug():
    replacement = _systems_spell(
        "spell|orphan-replacement",
        "orphan-replacement",
        "Orphan Replacement",
    )
    catalog = _build_spell_catalog([replacement])
    orphan_payload = {
        "name": "Orphan Legacy",
        "mark": "Known",
        "systems_ref": {"slug": "orphan-legacy"},
        "has_base_spell": True,
    }
    ambiguous_first = {
        "name": "Ambiguous First",
        "mark": "Known",
        "systems_ref": {
            "entry_key": "spell|ambiguous-first",
            "slug": "shared-legacy",
        },
        "has_base_spell": True,
    }
    ambiguous_second = {
        "name": "Ambiguous Second",
        "mark": "Known",
        "systems_ref": {
            "entry_key": "spell|ambiguous-second",
            "slug": "shared-legacy",
        },
        "has_base_spell": True,
    }
    option = {
        "page_ref": "mechanics/orphan-replacement",
        "spell_support": [
            {
                "replacement": {
                    "_": [
                        {
                            "kind": "known",
                            "from": {"mark": "Known"},
                            "to": {"options": [replacement.title]},
                        }
                    ]
                }
            }
        ],
    }
    entry = {
        "field_prefix": "orphan_support",
        "source_ref": option["page_ref"],
        "campaign_option": option,
    }
    values = {
        "orphan_support_replace_known_1_from_1": "orphan-legacy",
        "orphan_support_replace_known_1_to_1": replacement.slug,
    }

    updated = editor_module._apply_campaign_option_spells_to_spellcasting(
        {
            "spells": [
                orphan_payload,
                ambiguous_first,
                ambiguous_second,
            ]
        },
        existing_campaign_option_payloads=[],
        selected_campaign_option_payloads=[],
        spell_catalog=catalog,
        values=values,
        current_level=5,
        selected_spell_support_entries=[entry],
    )

    visible_identities = {
        dict(payload.get("systems_ref") or {}).get("entry_key")
        or dict(payload.get("systems_ref") or {}).get("slug")
        for payload in list(updated.get("spells") or [])
    }
    hidden = list(updated.get("campaign_option_replacement_bases") or [])
    assert visible_identities == {
        replacement.entry_key,
        "spell|ambiguous-first",
        "spell|ambiguous-second",
    }
    assert len(hidden) == 1
    assert dict(hidden[0].get("systems_ref") or {}).get("slug") == "orphan-legacy"

    restored = editor_module._apply_campaign_option_spells_to_spellcasting(
        updated,
        existing_campaign_option_payloads=[option],
        selected_campaign_option_payloads=[],
        spell_catalog=catalog,
        values={},
        current_level=5,
        selected_spell_support_entries=[],
    )
    restored_identities = {
        dict(payload.get("systems_ref") or {}).get("entry_key")
        or dict(payload.get("systems_ref") or {}).get("slug")
        for payload in list(restored.get("spells") or [])
    }
    assert restored_identities == {
        "orphan-legacy",
        "spell|ambiguous-first",
        "spell|ambiguous-second",
    }
    assert not list(restored.get("campaign_option_replacement_bases") or [])


@pytest.mark.parametrize(
    "page",
    ("overview", "spells", "resources", "features", "equipment", "inventory", "notes"),
)
def test_session_character_hot_systems_reads_do_not_call_public_revalidating_path(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    page,
):
    systems_service = app.extensions["systems_service"]
    character_read_service = systems_service.character_read_view()
    with app.app_context():
        assert systems_service.ensure_builtin_library_seeded("DND-5E") is not None
    hot_calls = []
    real_hot_library = character_read_service.get_campaign_library_for_character_read

    def tracked_hot_library(campaign_slug):
        hot_calls.append(campaign_slug)
        return real_hot_library(campaign_slug)

    def fail_public_library(*_args, **_kwargs):
        raise AssertionError("the Character read must stay on its dedicated hot path")

    monkeypatch.setattr(
        character_read_service,
        "get_campaign_library_for_character_read",
        tracked_hot_library,
    )
    monkeypatch.setattr(
        type(systems_service),
        "get_campaign_library",
        fail_public_library,
    )
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get(
        "/campaigns/linden-pass/session/character"
        f"?character=arden-march&page={page}&fragment=1"
    )

    assert response.status_code == 200
    assert hot_calls


def test_session_character_panel_fragment_skips_base_loading_media_only(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    calls: list[str] = []

    def tracked_loading_media(campaign, **_kwargs):
        calls.append(campaign.slug)
        return []

    monkeypatch.setattr(
        app_module,
        "select_campaign_loading_image_urls",
        tracked_loading_media,
    )
    sign_in(users["owner"]["email"], users["owner"]["password"])

    panel = client.get(
        "/campaigns/linden-pass/session/character"
        "?character=arden-march&page=overview&fragment=1"
    )
    assert panel.status_code == 200
    assert calls == []

    document = client.get(
        "/campaigns/linden-pass/session/character"
        "?character=arden-march&page=overview"
    )
    assert document.status_code == 200
    assert calls == ["linden-pass"]

    other_fragment = client.get(
        "/campaigns/linden-pass/session?fragment=1",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert other_fragment.status_code == 200
    assert calls == ["linden-pass", "linden-pass"]


def test_character_read_library_lookup_seeds_only_when_library_is_absent(
    app,
    monkeypatch,
):
    systems_service = app.extensions["systems_service"]
    with app.app_context():
        library = systems_service.ensure_builtin_library_seeded("DND-5E")
    assert library is not None
    seed_calls = []

    monkeypatch.setattr(
        systems_service.store,
        "get_library",
        lambda _library_slug: None,
    )

    def seed_library(library_slug):
        seed_calls.append(library_slug)
        return library

    monkeypatch.setattr(
        systems_service,
        "ensure_builtin_library_seeded",
        seed_library,
    )

    with app.test_request_context("/"):
        resolved = systems_service.get_campaign_library_for_character_read(
            "linden-pass"
        )

    assert resolved == library
    assert seed_calls == ["DND-5E"]


def test_character_read_hot_library_does_not_suppress_public_seed_revalidation(
    app,
    monkeypatch,
):
    systems_service = app.extensions["systems_service"]
    with app.app_context():
        library = systems_service.ensure_builtin_library_seeded("DND-5E")
    assert library is not None
    seed_calls = []

    def seed_library(library_slug):
        seed_calls.append(library_slug)
        return library

    monkeypatch.setattr(
        systems_service,
        "ensure_builtin_library_seeded",
        seed_library,
    )

    with app.test_request_context("/"):
        assert (
            systems_service.get_campaign_library_for_character_read("linden-pass")
            == library
        )
        assert systems_service.get_campaign_library("linden-pass") == library

    assert seed_calls == ["DND-5E"]


def test_raw_builder_revalidates_while_stable_character_read_view_stays_hot(
    app,
    monkeypatch,
):
    systems_service = app.extensions["systems_service"]
    with app.app_context():
        library = systems_service.ensure_builtin_library_seeded("DND-5E")
    assert library is not None
    seed_calls = []

    def seed_library(library_slug):
        seed_calls.append(library_slug)
        return library

    monkeypatch.setattr(
        systems_service,
        "ensure_builtin_library_seeded",
        seed_library,
    )
    _clear_builder_static_bundle_cache()
    try:
        with app.test_request_context("/"):
            hot_revision = _builder_static_revision_key(
                systems_service.character_read_view(),
                "linden-pass",
                entry_types=("item",),
            )
            assert seed_calls == []
            public_revision = _builder_static_revision_key(
                systems_service,
                "linden-pass",
                entry_types=("item",),
            )
    finally:
        _clear_builder_static_bundle_cache()

    assert hot_revision is not None
    assert public_revision is not None
    assert seed_calls


def test_hot_high_level_policy_caches_do_not_suppress_later_public_revalidation(
    app,
    monkeypatch,
):
    systems_service = app.extensions["systems_service"]
    hot_service = systems_service.character_read_view()
    with app.app_context():
        library = systems_service.ensure_builtin_library_seeded("DND-5E")
    assert library is not None
    seed_calls = []

    def seed_library(library_slug):
        seed_calls.append(library_slug)
        return library

    monkeypatch.setattr(systems_service, "ensure_builtin_library_seeded", seed_library)

    with app.test_request_context("/"):
        hot_service._class_feature_entries_by_class_identity("linden-pass")
        hot_service._subclass_feature_entries_by_class_and_source("linden-pass")
        hot_service._build_optionalfeature_entry_lookup("linden-pass")
        assert seed_calls == []
        systems_service._class_feature_entries_by_class_identity("linden-pass")
        systems_service._subclass_feature_entries_by_class_and_source("linden-pass")
        systems_service._build_optionalfeature_entry_lookup("linden-pass")

    assert seed_calls


def test_character_hot_progression_pins_campaign_and_db_generation_without_suppressing_public_sync(
    app,
    monkeypatch,
):
    systems_service = app.extensions["systems_service"]
    hot_service = systems_service.character_read_view()
    repository_store = app.extensions["repository_store"]
    page_store = app.extensions["campaign_page_store"]
    with app.app_context():
        campaign = repository_store.get().get_campaign("linden-pass")
        assert campaign is not None

        sync_content_dirs = []
        real_repository_get = repository_store.get
        real_list_page_records = page_store.list_page_records

        def fail_repository_get():
            raise AssertionError(
                "the bound Character generation must not reload its repository"
            )

        def tracked_list_page_records(campaign_slug, **kwargs):
            if kwargs.get("content_dir") is not None:
                sync_content_dirs.append(kwargs["content_dir"])
            return real_list_page_records(campaign_slug, **kwargs)

        monkeypatch.setattr(repository_store, "get", fail_repository_get)
        monkeypatch.setattr(page_store, "list_page_records", tracked_list_page_records)

        with app.test_request_context("/"):
            hot_service.bind_campaign_for_request("linden-pass", campaign)
            hot_service._list_campaign_progression_entries("linden-pass")
            assert hot_service._build_campaign_page_body_html(
                "linden-pass",
                "mechanics/harbor-duels",
            )
            assert sync_content_dirs == []

            monkeypatch.setattr(repository_store, "get", real_repository_get)
            systems_service._list_campaign_progression_entries("linden-pass")

        assert sync_content_dirs == [Path(campaign.player_content_dir)]


def test_read_only_character_viewer_skips_header_readiness_and_retraining_work(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    monkeypatch,
):
    def fail_readiness(*_args, **_kwargs):
        raise AssertionError("read-only viewers cannot expose level-up header actions")

    def fail_retraining(*_args, **_kwargs):
        raise AssertionError("read-only viewers cannot expose retraining header actions")

    monkeypatch.setattr(app_module, "native_level_up_readiness", fail_readiness)
    monkeypatch.setattr(
        app_module,
        "build_native_character_retraining_context",
        fail_retraining,
    )
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.get(
        "/campaigns/linden-pass/characters/arden-march?mode=read&page=features"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Level up" not in html
    assert "Prepare for level-up" not in html
    assert ">Retrain<" not in html


def test_editable_header_projection_preserves_actions_reuses_cache_and_resets(
    client,
    sign_in,
    users,
    monkeypatch,
):
    calls = {"readiness": 0, "retraining": 0}

    def readiness(*_args, **_kwargs):
        calls["readiness"] += 1
        return {"status": "ready", "message": "Ready", "reasons": []}

    def linked_authoring(*_args, **_kwargs):
        return {"supported": True, "is_imported": False, "message": ""}

    def retraining(*_args, **_kwargs):
        calls["retraining"] += 1
        return {"feature_rows": [{"id": "retrainable"}]}

    monkeypatch.setattr(app_module, "native_level_up_readiness", readiness)
    monkeypatch.setattr(
        app_module,
        "build_linked_feature_authoring_support",
        linked_authoring,
    )
    monkeypatch.setattr(
        app_module,
        "build_native_character_retraining_context",
        retraining,
    )
    monkeypatch.setattr(
        app_module,
        "_list_campaign_enabled_entries",
        lambda *_args, **_kwargs: [],
    )
    sign_in(users["dm"]["email"], users["dm"]["password"])

    first = client.get(
        "/campaigns/linden-pass/characters/arden-march?mode=read&page=features"
    )
    second = client.get(
        "/campaigns/linden-pass/characters/arden-march?mode=read&page=features"
    )

    assert first.status_code == second.status_code == 200
    for response in (first, second):
        html = response.get_data(as_text=True)
        assert "/characters/arden-march/level-up" in html
        assert "/characters/arden-march/retraining" in html
        assert "Prepare for level-up" not in html
    assert calls == {"readiness": 1, "retraining": 1}

    reset_character_read_projection_cache_for_tests()
    rebuilt = client.get(
        "/campaigns/linden-pass/characters/arden-march?mode=read&page=features"
    )
    assert rebuilt.status_code == 200
    assert "/characters/arden-march/level-up" in rebuilt.get_data(as_text=True)
    assert "/characters/arden-march/retraining" in rebuilt.get_data(as_text=True)
    assert calls == {"readiness": 2, "retraining": 2}
