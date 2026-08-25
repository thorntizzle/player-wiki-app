from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from player_wiki.auth_store import AuthStore
from player_wiki.campaign_combat_preset_store import (
    CampaignCombatPresetConflictError,
    CampaignCombatPresetStore,
    CampaignCombatPresetStoreHooks,
)
from player_wiki.combat_preset_models import CampaignCombatPresetEntryInput
from player_wiki.db import get_db, get_db_query_metrics, reset_db_query_metrics


def _entry(source_kind: str, **overrides) -> CampaignCombatPresetEntryInput:
    values = {
        "source_kind": source_kind,
        "source_ref": "",
        "source_version": None,
        "version_scheme": None,
        "quantity": 1,
        "turn_value": None,
        "initiative_priority": 1,
        "custom_name": "",
        "initiative_bonus": None,
        "dexterity_modifier": None,
        "max_hp": None,
        "movement_total": None,
    }
    values.update(overrides)
    return CampaignCombatPresetEntryInput(**values)


def _four_kinds() -> tuple[CampaignCombatPresetEntryInput, ...]:
    return (
        _entry(
            "character",
            source_ref="hero",
            source_version="sheet-revision-7",
            version_scheme="character-state-revision",
            turn_value=18,
        ),
        _entry("dm_statblock", source_ref="42", quantity=2, initiative_priority=3),
        _entry(
            "systems_monster",
            source_ref="dnd-5e/srd/goblin",
            source_version="2024.1",
            version_scheme="source-version",
        ),
        _entry(
            "manual_npc",
            custom_name="Bridge Guard",
            initiative_bonus=2,
            dexterity_modifier=1,
            max_hp=11,
            movement_total=30,
        ),
    )


def test_four_kind_aggregate_round_trips_in_stable_order_with_actor_metadata(app, users):
    with app.app_context():
        store = CampaignCombatPresetStore()
        created = store.create_preset(
            "linden-pass",
            name="  Night Watch  ",
            entries=_four_kinds(),
            created_by_user_id=users["dm"]["id"],
        )

        assert created.id > 0
        assert created.name == "Night Watch"
        assert created.name_key == "night watch"
        assert created.revision == 1
        assert created.created_by_user_id == users["dm"]["id"]
        assert created.updated_by_user_id == users["dm"]["id"]
        assert [entry.position for entry in created.entries] == [0, 1, 2, 3]
        assert [entry.source_kind for entry in created.entries] == [
            "character",
            "dm_statblock",
            "systems_monster",
            "manual_npc",
        ]
        assert created.entries[0].source_version == "sheet-revision-7"
        assert created.entries[3].custom_name == "Bridge Guard"

        loaded = store.get_preset("linden-pass", created.id)
        assert loaded == created
        assert store.get_preset("foreign-campaign", created.id) is None


def test_names_are_normalized_per_campaign_and_list_is_one_ordered_query(app):
    with app.app_context():
        store = CampaignCombatPresetStore()
        store.create_preset("linden-pass", name="Zulu", entries=())
        alpha = store.create_preset("linden-pass", name="ＡLPHA", entries=())
        store.create_preset("other-campaign", name="alpha", entries=())

        with pytest.raises(CampaignCombatPresetConflictError):
            store.create_preset("linden-pass", name="alpha", entries=())

        reset_db_query_metrics()
        listed = store.list_presets("linden-pass")
        metrics = get_db_query_metrics()
        assert [preset.id for preset in listed] == [alpha.id, listed[1].id]
        assert [preset.name_key for preset in listed] == ["alpha", "zulu"]
        assert all(preset.entries == () for preset in listed)
        assert metrics["query_count"] == 1
        assert metrics["commit_count"] == 0


def test_revision_guarded_update_preserves_retained_ids_and_rolls_back_stale_write(app):
    with app.app_context():
        store = CampaignCombatPresetStore()
        created = store.create_preset("linden-pass", name="Watch", entries=_four_kinds())
        retained = created.entries[2]
        replacement = _entry(
            "manual_npc",
            custom_name="Captain",
            initiative_bonus=0,
            dexterity_modifier=0,
            max_hp=20,
            movement_total=25,
        )

        updated = store.update_preset(
            "linden-pass",
            created.id,
            expected_revision=1,
            name="Watch Revised",
            entries=(retained, replacement),
        )

        assert updated.revision == 2
        assert [entry.id for entry in updated.entries] == [retained.id, updated.entries[1].id]
        assert updated.entries[0].position == 0
        assert updated.entries[1].position == 1
        assert updated.entries[1].id not in {entry.id for entry in created.entries}

        with pytest.raises(CampaignCombatPresetConflictError):
            store.update_preset(
                "linden-pass",
                created.id,
                expected_revision=1,
                name="Stale",
                entries=(),
            )
        assert store.get_preset("linden-pass", created.id) == updated


def test_missing_or_foreign_retained_entry_rolls_back_all_aggregate_bytes(app):
    with app.app_context():
        store = CampaignCombatPresetStore()
        first = store.create_preset("linden-pass", name="First", entries=_four_kinds())
        foreign = store.create_preset("other-campaign", name="Foreign", entries=_four_kinds())
        before = store.get_preset("linden-pass", first.id)

        for invalid in (
            CampaignCombatPresetEntryInput.from_record(first.entries[0], id=999999),
            foreign.entries[0],
        ):
            with pytest.raises(CampaignCombatPresetConflictError):
                store.update_preset(
                    "linden-pass",
                    first.id,
                    expected_revision=1,
                    name="Must Roll Back",
                    entries=(invalid,),
                )
            assert store.get_preset("linden-pass", first.id) == before


def test_injected_mid_entry_failure_rolls_back_create_and_update(app):
    events: list[tuple[str, int]] = []

    def fail_second(operation: str, position: int) -> None:
        events.append((operation, position))
        if position == 1:
            raise RuntimeError("injected entry failure")

    with app.app_context():
        failing = CampaignCombatPresetStore(
            hooks=CampaignCombatPresetStoreHooks(before_entry_write=fail_second)
        )
        with pytest.raises(RuntimeError, match="injected"):
            failing.create_preset("linden-pass", name="Broken", entries=_four_kinds())
        assert CampaignCombatPresetStore().list_presets("linden-pass") == []

        healthy = CampaignCombatPresetStore()
        created = healthy.create_preset("linden-pass", name="Stable", entries=_four_kinds())
        before = healthy.get_preset("linden-pass", created.id)
        with pytest.raises(RuntimeError, match="injected"):
            failing.update_preset(
                "linden-pass",
                created.id,
                expected_revision=1,
                name="Broken Update",
                entries=created.entries,
            )
        assert healthy.get_preset("linden-pass", created.id) == before
        assert ("create", 1) in events and ("update", 1) in events


def test_revision_guarded_delete_cascades_only_entries_and_preserves_tracker(app):
    with app.app_context():
        connection = get_db()
        connection.execute(
            """INSERT INTO campaign_combat_trackers
            (campaign_slug, round_number, revision, updated_at)
            VALUES ('linden-pass', 4, 9, 'before')"""
        )
        connection.commit()
        store = CampaignCombatPresetStore()
        created = store.create_preset("linden-pass", name="Disposable", entries=_four_kinds())

        with pytest.raises(CampaignCombatPresetConflictError):
            store.delete_preset("linden-pass", created.id, expected_revision=2)
        assert store.get_preset("linden-pass", created.id) is not None

        store.delete_preset("linden-pass", created.id, expected_revision=1)
        assert store.get_preset("linden-pass", created.id) is None
        assert connection.execute(
            "SELECT COUNT(*) FROM campaign_encounter_preset_entries WHERE preset_id = ?",
            (created.id,),
        ).fetchone()[0] == 0
        tracker = connection.execute(
            "SELECT round_number, revision, updated_at FROM campaign_combat_trackers WHERE campaign_slug = ?",
            ("linden-pass",),
        ).fetchone()
        assert tuple(tracker) == (4, 9, "before")


def test_each_successful_aggregate_write_commits_exactly_once(app):
    with app.app_context():
        store = CampaignCombatPresetStore()

        reset_db_query_metrics()
        created = store.create_preset("linden-pass", name="Commit Count", entries=_four_kinds())
        assert get_db_query_metrics()["commit_count"] == 1

        reset_db_query_metrics()
        updated = store.update_preset(
            "linden-pass",
            created.id,
            expected_revision=created.revision,
            name=created.name,
            entries=created.entries,
        )
        assert updated.revision == created.revision + 1
        assert get_db_query_metrics()["commit_count"] == 1

        reset_db_query_metrics()
        store.delete_preset(
            "linden-pass",
            created.id,
            expected_revision=updated.revision,
        )
        assert get_db_query_metrics()["commit_count"] == 1


def test_actor_deletion_sets_metadata_to_null_without_deleting_presets(app):
    with app.app_context():
        actor = AuthStore().create_user(
            "preset-actor@example.invalid",
            "Preset Actor",
            status="active",
        )
        store = CampaignCombatPresetStore()
        preset = store.create_preset(
            "linden-pass",
            name="Actor Round Trip",
            entries=_four_kinds(),
            created_by_user_id=actor.id,
        )
        connection = get_db()
        connection.execute("DELETE FROM users WHERE id = ?", (actor.id,))
        connection.commit()

        loaded = store.get_preset("linden-pass", preset.id)
        assert loaded is not None
        assert loaded.created_by_user_id is None
        assert loaded.updated_by_user_id is None
        assert all(entry.created_by_user_id is None for entry in loaded.entries)
        assert all(entry.updated_by_user_id is None for entry in loaded.entries)


@pytest.mark.parametrize(
    "entry",
    [
        _entry(
            "manual_npc",
            custom_name="",
            initiative_bonus=0,
            dexterity_modifier=0,
            max_hp=1,
            movement_total=1,
        ),
        _entry(
            "manual_npc",
            source_ref="forbidden",
            custom_name="NPC",
            initiative_bonus=0,
            dexterity_modifier=0,
            max_hp=1,
            movement_total=1,
        ),
        _entry(
            "manual_npc",
            custom_name="NPC",
            initiative_bonus=0,
            dexterity_modifier=0,
            max_hp=-1,
            movement_total=1,
        ),
        _entry(
            "manual_npc",
            custom_name="NPC",
            initiative_bonus=None,
            dexterity_modifier=0,
            max_hp=1,
            movement_total=1,
        ),
        _entry(
            "manual_npc",
            custom_name="NPC",
            initiative_bonus=0,
            dexterity_modifier=None,
            max_hp=1,
            movement_total=1,
        ),
        _entry(
            "manual_npc",
            custom_name="NPC",
            initiative_bonus=0,
            dexterity_modifier=0,
            max_hp=None,
            movement_total=1,
        ),
        _entry(
            "manual_npc",
            custom_name="NPC",
            initiative_bonus=0,
            dexterity_modifier=0,
            max_hp=1,
            movement_total=None,
        ),
        _entry("character", source_ref="", custom_name=""),
        _entry("character", source_ref="hero", source_version="7", version_scheme=None),
        _entry("character", source_ref="hero", custom_name="copied title"),
        _entry("unsupported", source_ref="x"),
    ],
)
def test_invalid_entry_shapes_are_bounded_domain_conflicts(app, entry):
    with app.app_context(), pytest.raises(CampaignCombatPresetConflictError):
        CampaignCombatPresetStore().create_preset(
            "linden-pass",
            name="Invalid",
            entries=(entry,),
        )


@pytest.mark.parametrize("campaign_slug", ["Bad-Slug", "-bad", "bad-", "bad--slug"])
def test_invalid_campaign_slugs_are_bounded_domain_conflicts(app, campaign_slug):
    with app.app_context(), pytest.raises(CampaignCombatPresetConflictError):
        CampaignCombatPresetStore().create_preset(
            campaign_slug,
            name="Invalid Campaign",
            entries=(),
        )


def test_dense_aggregate_query_plans_and_counts_remain_stable(app):
    with app.app_context():
        store = CampaignCombatPresetStore()
        rows = tuple(_four_kinds() for _ in range(250))
        for index, entries in enumerate(rows):
            store.create_preset(
                "linden-pass",
                name=f"Preset {index:03d}",
                entries=entries,
            )

        reset_db_query_metrics()
        listed = store.list_presets("linden-pass")
        list_metrics = get_db_query_metrics()
        assert len(listed) == 250
        assert list_metrics["query_count"] == 1

        reset_db_query_metrics()
        detail = store.get_preset("linden-pass", listed[100].id)
        detail_metrics = get_db_query_metrics()
        assert detail is not None and len(detail.entries) == 4
        assert detail_metrics["query_count"] == 2

        connection = get_db()
        list_plan = connection.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM campaign_encounter_presets "
            "WHERE campaign_slug = ? ORDER BY name_key, id",
            ("linden-pass",),
        ).fetchall()
        source_plan = connection.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM campaign_encounter_preset_entries "
            "WHERE campaign_slug = ? AND source_kind = ? AND source_ref = ? ORDER BY id",
            ("linden-pass", "character", "hero"),
        ).fetchall()
        assert any("sqlite_autoindex_campaign_encounter_presets" in row[3] for row in list_plan)
        assert any("idx_campaign_encounter_preset_entries_source" in row[3] for row in source_plan)


def test_ordinary_combat_and_source_health_owners_do_not_adopt_preset_queries():
    project_root = Path(__file__).parents[1]
    for relative in (
        "player_wiki/campaign_combat_store.py",
        "player_wiki/campaign_combat_service.py",
        "player_wiki/combat_routes.py",
        "player_wiki/combat_api_routes.py",
        "player_wiki/source_health.py",
    ):
        source = (project_root / relative).read_text(encoding="utf-8")
        assert "campaign_encounter_preset" not in source
        assert "CampaignCombatPresetStore" not in source
