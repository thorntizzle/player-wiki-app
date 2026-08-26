from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from player_wiki.campaign_combat_preset_sources import (
    COMBAT_SEED_VERSION_SCHEME,
    CampaignCombatPresetSourceResolver,
    CampaignCombatPresetSourceValidationError,
)
from player_wiki.combat_npc_resources import NpcResourceCounterSeed, NpcResourceNoteSeed
from player_wiki.combat_preset_models import CampaignCombatPresetEntryInput


def _version(projection: dict[str, object]) -> str:
    payload = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


class _CharacterRepository:
    def __init__(self, records=()):
        self.records = {
            record.definition.character_slug: record for record in records
        }
        self.calls: list[tuple[str, str]] = []

    def get_combat_seed_character(self, campaign_slug, character_slug):
        self.calls.append((campaign_slug, character_slug))
        return self.records.get(character_slug)


class _DMContentService:
    @staticmethod
    def get_statblock_dexterity_modifier(statblock):
        return statblock.dexterity_modifier


class _SystemsStore:
    def __init__(self, entries, *, library_present=True):
        self.entries = {entry.entry_key: entry for entry in entries}
        self.library_present = library_present
        self.identity_calls = 0
        self.mutation_calls: list[str] = []

    def get_library(self, library_slug):
        assert library_slug == "dnd-5e"
        if not self.library_present:
            return None
        return SimpleNamespace(library_slug="dnd-5e")

    def list_sources(self, library_slug):
        assert library_slug == "dnd-5e"
        return [
            SimpleNamespace(library_slug=library_slug, source_id=source_id)
            for source_id in sorted(
                {entry.source_id for entry in self.entries.values()}
            )
        ]

    @staticmethod
    def list_campaign_enabled_sources(campaign_slug):
        assert campaign_slug == "linden-pass"
        return []

    def upsert_library(self, *_args, **_kwargs):
        self.mutation_calls.append("upsert_library")
        raise AssertionError("resolver attempted to seed a Systems library")

    def upsert_source(self, *_args, **_kwargs):
        self.mutation_calls.append("upsert_source")
        raise AssertionError("resolver attempted to seed a Systems source")

    def list_entries_for_campaign_by_identity(
        self,
        campaign_slug,
        library_slug,
        source_ids,
        *,
        entry_type,
        entry_keys=None,
        entry_slugs=None,
        exact_titles=None,
    ):
        self.identity_calls += 1
        assert campaign_slug == "linden-pass"
        assert library_slug == "dnd-5e"
        assert entry_type == "monster"
        assert entry_slugs is None and exact_titles is None
        return [
            self.entries[key]
            for key in entry_keys or []
            if key in self.entries
            and self.entries[key].source_id in source_ids
            and self.entries[key].enabled
        ]

    def get_entry(self, library_slug, entry_key):
        assert library_slug == "dnd-5e"
        return self.entries.get(entry_key)


class _SystemsService:
    def __init__(self, entries=(), *, source_enabled=True, library_present=True):
        self.store = _SystemsStore(entries, library_present=library_present)
        self.source_enabled = source_enabled

    def get_campaign_library_slug(self, campaign_slug):
        assert campaign_slug == "linden-pass"
        return "dnd-5e"

    def _campaign_source_seed_map(self, campaign_slug):
        assert campaign_slug == "linden-pass"
        return {
            source_id: {"enabled": self.source_enabled}
            for source_id in {
                entry.source_id for entry in self.store.entries.values()
            }
        }

    def _default_enabled_for_source(self, _source):
        return self.source_enabled

    @staticmethod
    def build_monster_combat_seed(entry):
        return entry.seed


def _resolver(
    *,
    characters=(),
    statblocks=(),
    systems_entries=(),
    source_enabled=True,
    systems_library_present=True,
):
    character_repository = _CharacterRepository(characters)
    systems_service = _SystemsService(
        systems_entries,
        source_enabled=source_enabled,
        library_present=systems_library_present,
    )
    dm_batch_calls: list[tuple[str, tuple[int, ...]]] = []

    def load_dm_statblocks(campaign_slug, ids):
        dm_batch_calls.append((campaign_slug, ids))
        return {
            str(statblock.id): statblock
            for statblock in statblocks
            if statblock.id in ids and statblock.campaign_slug == campaign_slug
        }

    resolver = CampaignCombatPresetSourceResolver(
        character_repository,
        _DMContentService(),
        systems_service,
        dm_statblock_batch_loader=load_dm_statblocks,
        systems_campaign_config_loader=lambda campaign_slug: (
            "dnd-5e",
            {
                source_id: {"enabled": source_enabled}
                for source_id in {
                    entry.source_id for entry in systems_entries
                }
            },
        ),
    )
    resolver.test_dm_batch_calls = dm_batch_calls
    return resolver, character_repository, systems_service


def _manual(**overrides):
    values = {
        "source_kind": "manual_npc",
        "custom_name": " Guard ",
        "initiative_bonus": 1,
        "dexterity_modifier": 2,
        "max_hp": 12,
        "movement_total": 30,
    }
    values.update(overrides)
    return CampaignCombatPresetEntryInput(**values)


def test_manual_preparation_and_materialization_need_no_source_reads():
    resolver, character_repository, systems_service = _resolver()
    prepared = resolver.prepare_entries_for_save(
        "linden-pass",
        (_manual(quantity="2", turn_value="7"),),
    )
    materialized = resolver.resolve_entries_for_apply("linden-pass", prepared)

    assert prepared == (
        _manual(
            custom_name="Guard",
            quantity=2,
            turn_value=7,
            source_version=None,
            version_scheme=None,
        ),
    )
    assert len(materialized) == 2
    assert all(seed.display_name == "Guard" and seed.turn_value == 7 for seed in materialized)
    assert character_repository.calls == []
    assert systems_service.store.identity_calls == 0


def test_character_versions_use_definition_seed_facts_and_deduplicate_exact_refs():
    definition = SimpleNamespace(
        campaign_slug="linden-pass",
        character_slug="arden-march",
        name="Arden March",
        status="active",
        stats={
            "initiative_bonus": 4,
            "ability_scores": {"dex": {"score": 14, "modifier": 2}},
            "max_hp": 31,
            "speed": "30 ft., fly 60 ft.",
        },
    )
    record = SimpleNamespace(
        definition=definition,
        state_record=SimpleNamespace(
            state={"vitals": {"current_hp": 17, "temp_hp": 5}}
        ),
    )
    resolver, repository, _systems_service = _resolver(characters=(record,))
    entries = (
        CampaignCombatPresetEntryInput(source_kind="character", source_ref="arden-march"),
        CampaignCombatPresetEntryInput(
            source_kind="character", source_ref="arden-march", quantity=2, turn_value=18
        ),
    )
    prepared = resolver.prepare_entries_for_save("linden-pass", entries)

    expected_version = _version(
        {
            "dexterity_modifier": 2,
            "display_name": "Arden March",
            "initiative_bonus": 4,
            "max_hp": 31,
            "movement_total": 60,
            "source_ref": "arden-march",
        }
    )
    assert [entry.source_version for entry in prepared] == [expected_version, expected_version]
    assert all(entry.version_scheme == COMBAT_SEED_VERSION_SCHEME for entry in prepared)
    assert repository.calls == [("linden-pass", "arden-march")]
    seeds = resolver.resolve_entries_for_apply("linden-pass", prepared)
    assert [seed.turn_value for seed in seeds] == [4, 18, 18]
    assert all(seed.current_hp == 17 and seed.temp_hp == 5 for seed in seeds)

    record.state_record.state["vitals"] = {"current_hp": 9, "temp_hp": 2}
    refreshed = resolver.prepare_entries_for_save("linden-pass", entries)
    assert [entry.source_version for entry in refreshed] == [
        expected_version,
        expected_version,
    ]
    assert resolver.inspect_entries("linden-pass", prepared)[0].status == "current"
    rematerialized = resolver.resolve_entries_for_apply("linden-pass", prepared)
    assert all(seed.current_hp == 9 and seed.temp_hp == 2 for seed in rematerialized)


def test_character_missing_state_is_sanitized_unavailable():
    resolver, repository, _systems_service = _resolver()
    entry = CampaignCombatPresetEntryInput(
        source_kind="character",
        source_ref="arden-march",
    )
    with pytest.raises(CampaignCombatPresetSourceValidationError, match="inaccessible"):
        resolver.prepare_entries_for_save("linden-pass", (entry,))
    assert repository.calls == [("linden-pass", "arden-march")]

    saved = replace(
        entry,
        source_version="0" * 64,
        version_scheme=COMBAT_SEED_VERSION_SCHEME,
    )
    inspection = resolver.inspect_entries("linden-pass", (saved,))
    assert inspection[0].status == "missing_or_inaccessible"


def test_dm_and_system_versions_include_normalized_resources_and_parser_drift():
    statblock = SimpleNamespace(
        id=7,
        campaign_slug="linden-pass",
        title="Mute Scribe",
        body_markdown="Ink Burst (3/day).",
        max_hp=22,
        movement_total=30,
        initiative_bonus=1,
        dexterity_modifier=3,
    )
    system_entry = SimpleNamespace(
        entry_key="monster|MM|owlbear",
        entry_type="monster",
        source_id="MM",
        title="Owlbear",
        enabled=True,
        body={"traits": [{"name": "Keen Sight", "entries": ["Focus (2/day)."]}]},
        seed=SimpleNamespace(
            entry_key="monster|MM|owlbear",
            title="Owlbear",
            source_id="MM",
            max_hp=59,
            movement_total=40,
            initiative_bonus=1,
            dexterity_modifier=1,
        ),
    )
    resolver, _repository, systems_service = _resolver(
        statblocks=(statblock,), systems_entries=(system_entry,)
    )
    entries = (
        CampaignCombatPresetEntryInput(source_kind="dm_statblock", source_ref="7"),
        CampaignCombatPresetEntryInput(
            source_kind="dm_statblock", source_ref="7", quantity=2
        ),
        CampaignCombatPresetEntryInput(
            source_kind="systems_monster", source_ref="monster|MM|owlbear"
        ),
    )
    prepared = resolver.prepare_entries_for_save("linden-pass", entries)
    assert all(len(entry.source_version or "") == 64 for entry in prepared)
    assert resolver.test_dm_batch_calls == [("linden-pass", (7,))]
    assert systems_service.store.identity_calls == 1

    statblock.body_markdown = "Ink Burst (4/day)."
    inspection = resolver.inspect_entries("linden-pass", prepared)
    assert [row.status for row in inspection] == [
        "source_changed",
        "source_changed",
        "current",
    ]
    assert inspection[0].source_ref == "" and inspection[0].source_version is None
    with pytest.raises(CampaignCombatPresetSourceValidationError, match="changed"):
        resolver.resolve_entries_for_apply("linden-pass", prepared)


@pytest.mark.parametrize(
    "entry",
    [
        _manual(quantity=0),
        _manual(quantity=51),
        _manual(source_ref="not-empty"),
        _manual(source_version="a" * 64),
        _manual(version_scheme=COMBAT_SEED_VERSION_SCHEME),
        _manual(custom_name=""),
        CampaignCombatPresetEntryInput(
            source_kind="character", source_ref="arden-march", custom_name="Override"
        ),
        CampaignCombatPresetEntryInput(
            source_kind="character", source_ref="arden-march", max_hp=99
        ),
    ],
)
def test_field_matrix_and_per_row_quantity_are_enforced(entry):
    resolver, _repository, _systems_service = _resolver()
    with pytest.raises(CampaignCombatPresetSourceValidationError):
        resolver.prepare_entries_for_save("linden-pass", (entry,))


def test_total_expanded_quantity_is_limited_to_fifty():
    resolver, _repository, _systems_service = _resolver()
    with pytest.raises(CampaignCombatPresetSourceValidationError, match="50"):
        resolver.prepare_entries_for_save(
            "linden-pass",
            (_manual(quantity=25), _manual(custom_name="Second", quantity=26)),
        )


@pytest.mark.parametrize(
    ("source_enabled", "entry_enabled", "expected_status"),
    [(False, True, "source_disabled"), (True, False, "entry_disabled")],
)
def test_systems_disabled_states_are_sanitized(source_enabled, entry_enabled, expected_status):
    entry = SimpleNamespace(
        entry_key="monster|MM|hidden",
        entry_type="monster",
        source_id="MM",
        title="Secret Name",
        enabled=entry_enabled,
        body={},
        seed=SimpleNamespace(
            entry_key="monster|MM|hidden",
            title="Secret Name",
            source_id="MM",
            max_hp=1,
            movement_total=1,
            initiative_bonus=0,
            dexterity_modifier=0,
        ),
    )
    resolver, _repository, _systems_service = _resolver(
        systems_entries=(entry,), source_enabled=source_enabled
    )
    saved = replace(
        CampaignCombatPresetEntryInput(
            source_kind="systems_monster", source_ref=entry.entry_key
        ),
        source_version="0" * 64,
        version_scheme=COMBAT_SEED_VERSION_SCHEME,
    )
    inspection = resolver.inspect_entries("linden-pass", (saved,))
    assert inspection[0].status == expected_status
    assert inspection[0].source_ref == "" and inspection[0].display_name == ""


def test_missing_and_foreign_sources_share_one_sanitized_status():
    resolver, _repository, _systems_service = _resolver()
    saved = CampaignCombatPresetEntryInput(
        source_kind="dm_statblock",
        source_ref="999",
        source_version="0" * 64,
        version_scheme=COMBAT_SEED_VERSION_SCHEME,
    )
    inspection = resolver.inspect_entries("linden-pass", (saved,))
    assert inspection[0].status == "missing_or_inaccessible"
    assert inspection[0].source_ref == "" and inspection[0].source_version is None


def test_missing_systems_library_is_read_only_and_sanitized_unavailable():
    resolver, _repository, systems_service = _resolver(
        systems_library_present=False
    )
    saved = CampaignCombatPresetEntryInput(
        source_kind="systems_monster",
        source_ref="monster|MM|missing",
        source_version="0" * 64,
        version_scheme=COMBAT_SEED_VERSION_SCHEME,
    )

    assert resolver.inspect_entries("linden-pass", (saved,))[0].status == (
        "missing_or_inaccessible"
    )
    with pytest.raises(CampaignCombatPresetSourceValidationError, match="inaccessible"):
        resolver.prepare_entries_for_save(
            "linden-pass",
            (replace(saved, source_version=None, version_scheme=None),),
        )
    assert systems_service.store.mutation_calls == []
    assert systems_service.store.identity_calls == 0


def test_incomplete_systems_library_does_not_seed_missing_source_rows():
    entry = SimpleNamespace(
        entry_key="monster|MM|orphan",
        entry_type="monster",
        source_id="MM",
        title="Orphan",
        enabled=True,
        body={},
        seed=SimpleNamespace(),
    )
    resolver, _repository, systems_service = _resolver(systems_entries=(entry,))
    systems_service.store.list_sources = lambda _library_slug: []
    saved = CampaignCombatPresetEntryInput(
        source_kind="systems_monster",
        source_ref=entry.entry_key,
        source_version="0" * 64,
        version_scheme=COMBAT_SEED_VERSION_SCHEME,
    )

    inspection = resolver.inspect_entries("linden-pass", (saved,))
    assert inspection[0].status == "missing_or_inaccessible"
    assert systems_service.store.mutation_calls == []


def test_static_resolver_has_no_tracker_adoption_or_broad_source_discovery():
    project_root = Path(__file__).resolve().parents[1]
    resolver_source = (
        project_root / "player_wiki" / "campaign_combat_preset_sources.py"
    ).read_text(encoding="utf-8")
    app_source = (project_root / "player_wiki" / "app.py").read_text(encoding="utf-8")

    for forbidden in (
        ".add_player_character(",
        ".add_npc_combatant(",
        ".create_combatant(",
        ".ensure_tracker(",
        ".bump_tracker_revision(",
        ".list_visible_characters(",
        ".list_statblocks(",
        ".list_monster_entries_for_campaign(",
        "exact_titles=",
        "entry_slugs=",
    ):
        assert forbidden not in resolver_source
    assert ".resolve_entries_for_apply(" not in app_source
