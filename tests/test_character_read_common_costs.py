from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from threading import Event
from types import SimpleNamespace

import pytest

import player_wiki.app as app_module
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
from tests.helpers.character_state_helpers import _write_character_definition


def _fail_full_presenter(*_args, **_kwargs):
    raise AssertionError("normal DND reads must not call the full character presenter")


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

    def get_builder_static_revision(self, _campaign_slug, *, entry_types):
        assert entry_types
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


def test_projection_cache_disables_itself_without_exact_service_identity():
    assert _projection_key(service=_NonWeakSystemsService()) is None


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
