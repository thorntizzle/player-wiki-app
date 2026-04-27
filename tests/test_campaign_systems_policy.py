from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from player_wiki.dnd5e_rules_reference import (
    DND5E_RULES_REFERENCE_SOURCE_ID,
    DND5E_RULES_REFERENCE_VERSION,
    build_dnd5e_rules_reference_entries,
)
from player_wiki.auth_store import AuthStore, utcnow
from player_wiki.auth import get_campaign_scope_visibility, get_effective_campaign_visibility
from player_wiki.campaign_visibility import VISIBILITY_DM, VISIBILITY_PLAYERS, VISIBILITY_PUBLIC
from player_wiki.system_policy import DND_5E_SYSTEM_CODE, XIANXIA_SYSTEM_CODE
from player_wiki.systems_service import (
    SystemsPolicyValidationError,
    XIANXIA_HOMEBREW_SOURCE_ID,
)
from player_wiki.xianxia_systems_seed import (
    XIANXIA_ENERGY_KEYS,
    XIANXIA_EFFORT_KEYS,
    XIANXIA_BASIC_ACTION_DEFAULT_SUPPORT_STATE,
    XIANXIA_BASIC_ACTION_DETAILS_STATUS_RANGE_TIMING_SEEDED,
    XIANXIA_ENTRY_FACET_KEYS,
    XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_NOTE_INSIGHT_STARTS_AT_0,
    XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_REASON_INSIGHT_STARTS_AT_0,
    XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_STATUS_SEEDED,
    XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_UNAVAILABLE_BY_DEFAULT,
    XIANXIA_GENERIC_TECHNIQUE_DEFAULT_SUPPORT_STATE,
    XIANXIA_GENERIC_TECHNIQUE_DETAILS_STATUS_COST_PREREQ_RESOURCE_RANGE_EFFORT_RESET_SUPPORT_SEEDED,
    XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_NONE,
    XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_NOTE_NO_MASTER_REQUIRED,
    XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_REASON_NO_MASTER_REQUIRED,
    XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_STATUS_LEARNABLE_WITHOUT_MASTER,
    XIANXIA_MAGIC_EFFORT_CANONICAL_LABEL,
    XIANXIA_MARTIAL_ART_ABILITY_KIND_KEYS,
    XIANXIA_MARTIAL_ART_ABILITY_DEFAULT_SUPPORT_STATE,
    XIANXIA_MARTIAL_ART_ABILITY_SUPPORT_STATES,
    XIANXIA_MARTIAL_ART_MISSING_RANK_REASON_INTENTIONAL_DRAFT,
    XIANXIA_MARTIAL_ART_RANK_KEYS,
    XIANXIA_MARTIAL_ART_RANK_ABILITY_EFFECTS_STATUS_COST_RANGE_DAMAGE_DURATION_SUPPORT_SEEDED,
    XIANXIA_MARTIAL_ART_RANK_ABILITY_GRANTS_STATUS_KIND_TAGS_SEEDED,
    XIANXIA_MARTIAL_ART_RANK_COMPLETION_STATUS_COMPLETE,
    XIANXIA_MARTIAL_ART_RANK_COMPLETION_STATUS_INTENTIONAL_DRAFT,
    XIANXIA_MARTIAL_ART_RANK_RECORDS_STATUS_ADVANCEMENT_METADATA_SEEDED,
    XIANXIA_MARTIAL_ART_RANK_RESOURCE_GRANTS_STATUS_ENERGY_MAXIMUMS_SEEDED,
    XIANXIA_MARTIAL_ART_RANK_STATUS_MISSING_INTENTIONAL_DRAFT,
    XIANXIA_MARTIAL_ART_RANK_STATUS_PRESENT,
    XIANXIA_SYSTEMS_SEED_DATA_RELATIVE_PATH,
    XIANXIA_SYSTEMS_SEED_STORAGE_STRATEGY,
    XIANXIA_SYSTEMS_SEED_VERSION,
    _build_seed_entry,
    build_xianxia_basic_action_details,
    build_xianxia_entry_facet_definitions,
    build_xianxia_effort_definitions,
    build_xianxia_generic_technique_details,
    build_xianxia_martial_art_rank_ability_effects,
    build_xianxia_martial_art_rank_ability_grants,
    build_xianxia_martial_art_rank_definitions,
    build_xianxia_martial_art_rank_resource_grants,
    build_xianxia_systems_seed_entries,
    get_xianxia_entry_facet_definition,
    get_xianxia_effort_definition,
    get_xianxia_martial_art_rank_definition,
)
from player_wiki.systems_importer import Dnd5eSystemsImporter
from player_wiki.systems_models import SystemsEntryRecord
from tests.test_systems_importer import (
    build_dmg_book_data_root,
    build_egw_character_option_wrapper_data_root,
    build_egw_dunamis_book_data_root,
    build_mtf_book_data_root,
    build_mm_book_data_root,
    build_phb_book_data_root,
    build_test_data_root,
    build_vgm_book_data_root,
)


def build_source_form(app, campaign_slug: str = "linden-pass") -> dict[str, str]:
    with app.app_context():
        service = app.extensions["systems_service"]
        rows = service.list_campaign_source_states(campaign_slug)

    data: dict[str, str] = {}
    for row in rows:
        if row.is_enabled:
            data[f"source_{row.source.source_id}_enabled"] = "1"
        data[f"source_{row.source.source_id}_visibility"] = row.default_visibility
    return data


def build_repo_local_test_root(name: str) -> Path:
    root = Path(__file__).resolve().parents[1] / ".local" / "pytest-temp" / "repo-local"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}-{uuid4().hex}"
    path.mkdir()
    return path


def build_warning_inventory_entry(
    *,
    entry_type: str,
    metadata: dict | None = None,
    body: dict | None = None,
) -> SystemsEntryRecord:
    now = utcnow()
    slug = f"warning-inventory-{entry_type.replace('_', '-').replace(' ', '-')}"
    return SystemsEntryRecord(
        id=0,
        library_slug="DND-5E",
        source_id="WARN",
        entry_key=f"dnd-5e|{entry_type}|warn|{slug}",
        entry_type=entry_type,
        slug=slug,
        title="Warning Inventory Entry",
        source_page="",
        source_path="",
        search_text="warning inventory entry",
        player_safe_default=True,
        dm_heavy=False,
        metadata=dict(metadata or {}),
        body=dict(body or {}),
        rendered_html="<p>Warning inventory entry.</p>",
        created_at=now,
        updated_at=now,
    )


@pytest.fixture()
def tmp_path() -> Path:
    return build_repo_local_test_root("pytest")


def test_party_member_sees_systems_nav_and_player_visible_sources(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    campaign = client.get("/campaigns/linden-pass")
    systems = client.get("/campaigns/linden-pass/systems")

    assert campaign.status_code == 200
    campaign_body = campaign.get_data(as_text=True)
    assert 'href="/campaigns/linden-pass/systems"' in campaign_body

    assert systems.status_code == 200
    body = systems.get_data(as_text=True)
    assert "RULES" in body
    assert "Character Rules Reference" in body
    assert "PHB" in body
    assert "Player&#39;s Handbook (2014)" in body
    assert "Xanathar&#39;s Guide to Everything" in body
    assert "Wayfarer&#39;s Guide to Eberron" not in body
    assert "DMG" not in body
    assert "MM" not in body


def test_dm_can_open_systems_control_panel_and_visibility_panel_shows_systems_scope(
    client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    visibility_panel = client.get("/campaigns/linden-pass/control-panel")
    systems_panel = client.get("/campaigns/linden-pass/systems/control-panel")

    assert visibility_panel.status_code == 200
    visibility_html = visibility_panel.get_data(as_text=True)
    assert "Systems" in visibility_html

    assert systems_panel.status_code == 200
    systems_html = systems_panel.get_data(as_text=True)
    assert "Systems Policy" in systems_html
    assert "Player&#39;s Handbook (2014)" in systems_html
    assert "Dungeon Master&#39;s Guide (2014)" in systems_html
    assert "Wayfarer&#39;s Guide to Eberron" not in systems_html
    assert "Proprietary-source acknowledgement" in systems_html
    assert "Authoring Model" in systems_html
    assert "First model: both, kept as separate lanes." in systems_html
    assert "Custom campaign entries are the DM-authored lane" in systems_html
    assert "Shared-source imports are admin-only shared-library refreshes" in systems_html
    assert "shared/core content editor is app-admin-only" in systems_html
    assert 'class="checkbox-label"' in systems_html


def test_xianxia_builtin_systems_library_identity_seeds_initial_homebrew_source(app):
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        seed_entries = build_xianxia_systems_seed_entries()

        library = service.ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)

        assert library is not None
        assert library.library_slug == XIANXIA_SYSTEM_CODE
        assert library.title == XIANXIA_SYSTEM_CODE
        assert library.system_code == XIANXIA_SYSTEM_CODE
        assert store.get_library(XIANXIA_SYSTEM_CODE) == library
        sources = store.list_sources(XIANXIA_SYSTEM_CODE)
        assert [source.source_id for source in sources] == [XIANXIA_HOMEBREW_SOURCE_ID]

        homebrew_source = sources[0]
        assert homebrew_source.title == "Xianxia Homebrew"
        assert homebrew_source.license_class == "open_license"
        assert homebrew_source.public_visibility_allowed is False
        assert homebrew_source.requires_unofficial_notice is False
        assert store.count_entries_for_source(XIANXIA_SYSTEM_CODE, XIANXIA_HOMEBREW_SOURCE_ID) == len(seed_entries)
        seeded_titles = {
            entry.title
            for entry in store.list_entries_for_source(
                XIANXIA_SYSTEM_CODE,
                XIANXIA_HOMEBREW_SOURCE_ID,
                entry_type="rule",
                limit=None,
            )
        }
        assert "Checks and Difficulty" in seeded_titles
        assert "Energy: Jing, Qi, and Shen" in seeded_titles
        assert "GM Approval Gates" in seeded_titles

        source_catalog_entry = service._source_catalog_entry(homebrew_source)
        assert source_catalog_entry is not None
        assert source_catalog_entry["seed_storage_strategy"] == XIANXIA_SYSTEMS_SEED_STORAGE_STRATEGY
        assert source_catalog_entry["seed_data_path"] == XIANXIA_SYSTEMS_SEED_DATA_RELATIVE_PATH
        assert source_catalog_entry["seed_version"] == XIANXIA_SYSTEMS_SEED_VERSION


def test_xianxia_entry_facet_definitions_cover_milestone_one_concepts():
    expected_facets = (
        "rule",
        "attribute",
        "effort",
        "energy",
        "yin_yang",
        "dao",
        "realm",
        "honor_rank",
        "skill_rule",
        "equipment",
        "armor",
        "martial_art",
        "martial_art_rank",
        "technique",
        "maneuver",
        "stance",
        "aura",
        "generic_technique",
        "basic_action",
        "condition",
        "status",
        "range_rule",
        "timing_rule",
        "critical_hit_rule",
        "sneak_attack_rule",
        "dying_rule",
        "minion_tag",
        "companion_rule",
        "gm_approval_rule",
    )

    definitions = build_xianxia_entry_facet_definitions()
    keys = tuple(definition["key"] for definition in definitions)

    assert XIANXIA_ENTRY_FACET_KEYS == expected_facets
    assert keys == expected_facets
    assert all(definition["label"] for definition in definitions)
    assert all(definition["group"] for definition in definitions)
    assert all(definition["default_entry_type"] for definition in definitions)
    assert all(definition["summary"] for definition in definitions)

    facet_map = {definition["key"]: definition for definition in definitions}
    assert facet_map["attribute"]["default_entry_type"] == "rule"
    assert facet_map["equipment"]["default_entry_type"] == "equipment"
    assert facet_map["armor"]["default_entry_type"] == "armor"
    assert facet_map["martial_art"]["default_entry_type"] == "martial_art"
    assert facet_map["generic_technique"]["default_entry_type"] == "generic_technique"
    assert facet_map["basic_action"]["default_entry_type"] == "basic_action"
    assert facet_map["basic_action"]["support_state"] == "reference_only"
    assert facet_map["condition"]["default_entry_type"] == "rule"
    assert facet_map["condition"]["support_state"] == "reference_only"
    assert facet_map["status"]["default_entry_type"] == "rule"
    assert facet_map["status"]["support_state"] == "reference_only"
    assert facet_map["dying_rule"]["default_entry_type"] == "rule"

    martial_art_facet = get_xianxia_entry_facet_definition("martial-art")
    assert martial_art_facet is not None
    assert martial_art_facet["key"] == "martial_art"
    assert martial_art_facet["label"] == "Martial Art"
    basic_action_facet = get_xianxia_entry_facet_definition("basic-action")
    assert basic_action_facet is not None
    assert basic_action_facet["key"] == "basic_action"
    assert basic_action_facet["label"] == "Basic Action"


def test_xianxia_effort_definitions_encode_magic_effort_as_canonical_label():
    definitions = build_xianxia_effort_definitions()
    keys = tuple(definition["key"] for definition in definitions)

    assert keys == XIANXIA_EFFORT_KEYS
    assert XIANXIA_MAGIC_EFFORT_CANONICAL_LABEL == "Magic Effort"
    assert all(definition["canonical_label"].endswith(" Effort") for definition in definitions)

    magic_effort = get_xianxia_effort_definition("magic")
    assert magic_effort is not None
    assert magic_effort["label"] == "Magic"
    assert magic_effort["canonical_label"] == XIANXIA_MAGIC_EFFORT_CANONICAL_LABEL
    assert magic_effort["die"] == "1d10"
    assert magic_effort["damage_bonus_key"] == "magic"
    assert magic_effort["damage_expression"] == "1d10 + Magic"


def test_xianxia_martial_art_rank_definitions_cover_milestone_one_rank_names():
    definitions = build_xianxia_martial_art_rank_definitions()
    keys = tuple(definition["key"] for definition in definitions)

    assert keys == XIANXIA_MARTIAL_ART_RANK_KEYS
    assert [definition["rank_name"] for definition in definitions] == [
        "Initiate",
        "Novice",
        "Apprentice",
        "Master",
        "Legendary",
    ]
    assert [definition["rank_order"] for definition in definitions] == [1, 2, 3, 4, 5]
    assert [definition["prerequisite_rank_key"] for definition in definitions] == [
        None,
        "initiate",
        "novice",
        "apprentice",
        "master",
    ]
    assert all(definition["insight_cost"] == 1 for definition in definitions)
    assert definitions[2]["teacher_breakthrough_requirement"] == "master"
    assert definitions[2]["teacher_breakthrough_note"].startswith("Requires learning under a Master")
    assert definitions[3]["teacher_breakthrough_requirement"] == "legendary_master"
    legendary = get_xianxia_martial_art_rank_definition("Legendary")
    assert legendary is not None
    assert legendary["key"] == "legendary"
    assert legendary["rank_name"] == "Legendary"
    assert legendary["rank_order"] == 5
    assert legendary["prerequisite_rank_key"] == "master"
    assert legendary["insight_cost"] == 1
    assert legendary["teacher_breakthrough_requirement"] == "ascension_breakthrough"
    assert legendary["teacher_breakthrough_note"] == "Requires an Ascension Breakthrough."
    assert "quest or mythic-level master" in legendary["legendary_prerequisite_note"]


def test_xianxia_core_rule_seed_entries_cover_milestone_one_references():
    entries = build_xianxia_systems_seed_entries()
    rule_entries = [entry for entry in entries if entry["entry_type"] == "rule"]
    entry_map = {entry["slug"]: entry for entry in rule_entries}
    required_slugs = {
        "checks-and-difficulty",
        "easy-normal-and-hard",
        "attributes",
        "efforts-and-damage",
        "energy-jing-qi-and-shen",
        "yin-and-yang",
        "dao",
        "hit-points",
        "stance",
        "defense",
        "insight",
        "realm-and-actions",
        "honor",
        "reputation",
        "skills",
        "basic-actions",
        "cultivation-time",
        "one-day-rest",
        "ranges-and-distance",
        "timing-and-initiative",
        "stance-activation-rules",
        "aura-activation-rules",
        "dying-and-unconsciousness",
        "critical-hits",
        "sneak-attacks",
        "minions",
        "companion-derivation",
        "gm-approval-gates",
        "bing-ti-legendary-errata",
    }

    assert set(entry_map) == required_slugs
    assert all(entry["entry_type"] == "rule" for entry in rule_entries)
    assert all(
        entry["metadata"]["seed_storage_strategy"] == XIANXIA_SYSTEMS_SEED_STORAGE_STRATEGY
        for entry in rule_entries
    )
    assert all(entry["metadata"]["seed_version"] == XIANXIA_SYSTEMS_SEED_VERSION for entry in rule_entries)
    assert all(entry["metadata"]["xianxia_rule_key"] for entry in rule_entries)
    assert all(entry["metadata"]["rule_key"] for entry in rule_entries)
    assert all(entry["metadata"]["xianxia_entry_facets"] for entry in rule_entries)
    assert all(entry["body"]["sections"] for entry in rule_entries)
    assert entry_map["efforts-and-damage"]["metadata"]["rule_key"] == "efforts_and_damage"
    assert "magic effort" in entry_map["efforts-and-damage"]["search_text"]
    assert entry_map["efforts-and-damage"]["metadata"]["effort_labels"]["magic"] == "Magic Effort"
    assert entry_map["efforts-and-damage"]["body"]["effort_labels"]["magic"] == "Magic Effort"
    assert entry_map["efforts-and-damage"]["metadata"]["xianxia_efforts"][3]["key"] == "magic"
    assert (
        entry_map["efforts-and-damage"]["metadata"]["xianxia_efforts"][3]["canonical_label"]
        == "Magic Effort"
    )
    assert entry_map["dying-and-unconsciousness"]["metadata"]["support_state"] == "reference_only"
    assert entry_map["minions"]["metadata"]["support_state"] == "reference_only"
    bing_ti_errata = entry_map["bing-ti-legendary-errata"]
    assert bing_ti_errata["metadata"]["support_state"] == "reference_only"
    assert bing_ti_errata["metadata"]["xianxia_rule_key"] == "bing_ti_legendary_errata"
    assert bing_ti_errata["metadata"]["xianxia_errata"] == {
        "subject": "Bing Ti",
        "scope": "Legendary rank",
        "incorrect_text": "Ji",
        "corrected_text": "Jing",
    }
    assert "bing ti" in bing_ti_errata["search_text"]
    assert "jing" in bing_ti_errata["search_text"]
    assert "read Ji as Jing" in bing_ti_errata["rendered_html"]


def test_xianxia_martial_art_parent_seed_entries_cover_requirements_catalog():
    entries = build_xianxia_systems_seed_entries()
    martial_art_entries = [entry for entry in entries if entry["entry_type"] == "martial_art"]
    rank_resource_grants = build_xianxia_martial_art_rank_resource_grants()
    rank_ability_grants = build_xianxia_martial_art_rank_ability_grants()
    rank_ability_effects = build_xianxia_martial_art_rank_ability_effects()
    expected_titles = [
        "Demon's Fist",
        "Heavenly Palm",
        "Taoist Blade",
        "Drunken Fist",
        "Striking Adder",
        "Bloody Saber",
        "Phoenix Descending",
        "Dragon Ascending",
        "Armored Elephant",
        "Swaying Willow",
        "Thundering Harmonics",
        "Shadow Puppet Theater",
        "Baihu Style",
        "Shuai Jiao",
        "Bing Ti",
        "Spiritualists' Binding Seals",
        "Formless Fist",
        "Cherry Blossom Swallow",
        "Ink-Stained Historian",
        "Manifesting Brush",
        "Beastmaster",
        "Beast-Tamer",
        "Courtier's Sting",
        "Madam's Piercing Blood",
        "Blooming Curse",
        "Rippling Melodies",
        "Strategist's Acumen",
        "Broken Tiger's Vessel",
        "The Four Winds",
        "Flying Daggers",
    ]

    assert [entry["title"] for entry in martial_art_entries] == expected_titles
    assert [entry["metadata"]["martial_art_catalog_order"] for entry in martial_art_entries] == list(
        range(1, 31)
    )
    assert all(entry["metadata"]["xianxia_entry_facets"] == ["martial_art"] for entry in martial_art_entries)
    assert all(entry["metadata"]["catalog_role"] == "parent" for entry in martial_art_entries)
    assert all(entry["metadata"]["rank_records_seeded"] is True for entry in martial_art_entries)
    assert all(
        entry["metadata"]["rank_records_status"]
        == XIANXIA_MARTIAL_ART_RANK_RECORDS_STATUS_ADVANCEMENT_METADATA_SEEDED
        for entry in martial_art_entries
    )
    assert all(
        entry["metadata"]["rank_resource_grants_seeded"] is True
        for entry in martial_art_entries
    )
    assert all(
        entry["metadata"]["rank_resource_grants_status"]
        == XIANXIA_MARTIAL_ART_RANK_RESOURCE_GRANTS_STATUS_ENERGY_MAXIMUMS_SEEDED
        for entry in martial_art_entries
    )
    assert all(
        entry["metadata"]["rank_ability_grants_seeded"] is True
        for entry in martial_art_entries
    )
    assert all(
        entry["metadata"]["rank_ability_grants_status"]
        == XIANXIA_MARTIAL_ART_RANK_ABILITY_GRANTS_STATUS_KIND_TAGS_SEEDED
        for entry in martial_art_entries
    )
    assert all(
        entry["metadata"]["rank_ability_effects_seeded"] is True
        for entry in martial_art_entries
    )
    assert all(
        entry["metadata"]["rank_ability_effects_status"]
        == XIANXIA_MARTIAL_ART_RANK_ABILITY_EFFECTS_STATUS_COST_RANGE_DAMAGE_DURATION_SUPPORT_SEEDED
        for entry in martial_art_entries
    )
    assert all(
        set(grants) == set(XIANXIA_ENERGY_KEYS)
        for rank_grants in rank_resource_grants.values()
        for grants in rank_grants.values()
    )
    assert all(
        grant["kind_key"] in XIANXIA_MARTIAL_ART_ABILITY_KIND_KEYS
        for rank_grants in rank_ability_grants.values()
        for grants in rank_grants.values()
        for grant in grants
    )
    assert all(
        effect["support_state"] in XIANXIA_MARTIAL_ART_ABILITY_SUPPORT_STATES
        for rank_effects in rank_ability_effects.values()
        for ability_effects in rank_effects.values()
        for effect in ability_effects.values()
    )
    assert all(
        effect["support_state"] == XIANXIA_MARTIAL_ART_ABILITY_DEFAULT_SUPPORT_STATE
        for rank_effects in rank_ability_effects.values()
        for ability_effects in rank_effects.values()
        for effect in ability_effects.values()
    )
    assert all(
        entry["metadata"]["rank_completion_status"]
        in {
            XIANXIA_MARTIAL_ART_RANK_COMPLETION_STATUS_COMPLETE,
            XIANXIA_MARTIAL_ART_RANK_COMPLETION_STATUS_INTENTIONAL_DRAFT,
        }
        for entry in martial_art_entries
    )
    assert all(entry["body"]["xianxia_martial_art"]["catalog_role"] == "parent" for entry in martial_art_entries)
    assert all(
        "rank records are seeded for the ranks present and include Jing, Qi, and Shen maximum increases"
        in entry["rendered_html"]
        for entry in martial_art_entries
    )
    assert all(
        "rank-granted ability names and kind tags" in entry["rendered_html"]
        for entry in martial_art_entries
    )
    assert all(
        "Detailed ability rules remain deferred" in entry["rendered_html"]
        for entry in martial_art_entries
    )

    entry_map = {entry["slug"]: entry for entry in martial_art_entries}
    assert entry_map["demons-fist"]["metadata"]["martial_art_style"] == "Unarmed Martial Art"
    assert "unarmed martial art" in entry_map["demons-fist"]["search_text"]
    assert entry_map["spiritualists-binding-seals"]["body"]["xianxia_martial_art"]["parent_note"].startswith(
        "Against Spirit and Divine targets"
    )
    assert "Ji, and Shen" not in entry_map["bing-ti"]["rendered_html"]
    demons_fist_html = entry_map["demons-fist"]["rendered_html"]
    assert "Rank Records" in demons_fist_html
    assert "Energy Maximum Increases" in demons_fist_html
    assert "xianxia:demons-fist:initiate" in demons_fist_html
    assert "Qi Fist Technique" in demons_fist_html
    assert "xianxia:demons-fist:initiate:qi-fist-technique" in demons_fist_html
    assert 'id="xianxia-demons-fist-initiate-qi-fist-technique"' in demons_fist_html
    assert 'href="#xianxia-demons-fist-initiate-qi-fist-technique"' in demons_fist_html
    assert set(rank_resource_grants) == {
        entry["metadata"]["martial_art_key"]
        for entry in martial_art_entries
    }
    assert set(rank_ability_grants) == {
        entry["metadata"]["martial_art_key"]
        for entry in martial_art_entries
    }
    assert set(rank_ability_effects) == {
        entry["metadata"]["martial_art_key"]
        for entry in martial_art_entries
    }
    for martial_art_key, rank_grants in rank_ability_grants.items():
        for rank_key, grants in rank_grants.items():
            assert set(rank_ability_effects[martial_art_key][rank_key]) == {
                grant["ability_key"] for grant in grants
            }
    assert rank_resource_grants["demons_fist"]["initiate"] == {"jing": 1, "qi": 0, "shen": 0}
    assert rank_resource_grants["demons_fist"]["legendary"] == {"jing": 2, "qi": 1, "shen": 1}
    assert rank_resource_grants["swaying_willow"]["master"] == {"jing": 0, "qi": 1, "shen": 1}
    assert rank_resource_grants["shadow_puppet_theater"]["legendary"] == {
        "jing": 0,
        "qi": 1,
        "shen": 3,
    }
    assert rank_resource_grants["spiritualists_binding_seals"]["legendary"] == {
        "jing": 0,
        "qi": 2,
        "shen": 2,
    }
    assert rank_resource_grants["rippling_melodies"]["initiate"] == {
        "jing": 0,
        "qi": 0,
        "shen": 1,
    }
    assert rank_resource_grants["broken_tigers_vessel"]["apprentice"] == {
        "jing": 2,
        "qi": 0,
        "shen": 0,
    }
    assert rank_ability_grants["demons_fist"]["initiate"][0]["name"] == "Qi Fist Technique"
    assert rank_ability_grants["demons_fist"]["initiate"][0]["kind_key"] == "technique"
    assert rank_ability_grants["bloody_saber"]["novice"][0]["kind_key"] == "aura"
    assert rank_ability_grants["cherry_blossom_swallow"]["novice"][0]["kind_key"] == "stance"
    assert [grant["name"] for grant in rank_ability_grants["strategists_acumen"]["initiate"]] == [
        "Eagle-Eyed Insight Maneuver",
        "Flow of Battle Maneuver",
    ]
    assert {grant["kind_key"] for grant in rank_ability_grants["strategists_acumen"]["initiate"]} == {
        "maneuver"
    }
    assert rank_ability_grants["formless_fist"]["legendary"][0]["kind_key"] == "other"
    assert rank_ability_effects["demons_fist"]["initiate"]["qi_fist_technique"] == {
        "resource_costs": [{"resource_key": "qi", "amount": 1}],
        "range_tags": ["self"],
        "damage_effort_tags": ["weapon_effort_damage"],
        "duration_tags": ["rest_of_combat"],
        "support_state": XIANXIA_MARTIAL_ART_ABILITY_DEFAULT_SUPPORT_STATE,
        "xianxia_support_state": XIANXIA_MARTIAL_ART_ABILITY_DEFAULT_SUPPORT_STATE,
    }
    assert rank_ability_effects["taoist_blade"]["initiate"]["wudang_sword_wave"][
        "range_tags"
    ] == ["far"]
    assert rank_ability_effects["taoist_blade"]["initiate"]["wudang_sword_wave"][
        "damage_effort_tags"
    ] == ["magical_effort_damage"]
    assert rank_ability_effects["bing_ti"]["legendary"]["death_s_touch_deep_freeze_technique"][
        "resource_costs"
    ] == [
        {"resource_key": "qi", "amount": 1},
        {"resource_key": "jing", "amount": 1},
        {"resource_key": "shen", "amount": 1},
    ]
    assert "ji" not in {
        cost["resource_key"]
        for cost in rank_ability_effects["bing_ti"]["legendary"][
            "death_s_touch_deep_freeze_technique"
        ]["resource_costs"]
    }
    assert rank_ability_effects["madams_piercing_blood"]["novice"][
        "luocha_s_vengeful_aura"
    ]["range_tags"] == ["5_feet_aura"]

    complete_rank_keys = list(XIANXIA_MARTIAL_ART_RANK_KEYS)
    rank_name_by_key = {
        definition["key"]: definition["rank_name"]
        for definition in build_xianxia_martial_art_rank_definitions()
    }
    incomplete_rank_keys = {
        "ink-stained-historian": ["initiate", "novice", "apprentice"],
        "manifesting-brush": ["initiate", "novice"],
        "beastmaster": ["initiate", "novice", "apprentice"],
        "beast-tamer": ["initiate", "novice"],
        "courtiers-sting": ["initiate", "novice"],
        "madams-piercing-blood": ["initiate", "novice"],
        "blooming-curse": ["initiate", "novice"],
        "rippling-melodies": ["initiate"],
        "strategists-acumen": ["initiate", "novice"],
        "broken-tigers-vessel": ["initiate", "novice", "apprentice"],
        "the-four-winds": ["initiate", "novice", "apprentice"],
        "flying-daggers": ["initiate", "novice"],
    }
    complete_slugs = {entry["slug"] for entry in martial_art_entries} - set(incomplete_rank_keys)
    assert len(complete_slugs) == 18

    for slug in complete_slugs:
        records = entry_map[slug]["metadata"]["martial_art_rank_records"]
        metadata = entry_map[slug]["metadata"]
        martial_art_body = entry_map[slug]["body"]["xianxia_martial_art"]
        assert [record["rank_key"] for record in records] == complete_rank_keys
        assert [record["rank_order"] for record in records] == [1, 2, 3, 4, 5]
        assert all(record["insight_cost"] == 1 for record in records)
        assert all(
            record["energy_maximum_increases"]
            == rank_resource_grants[record["martial_art_key"]][record["rank_key"]]
            for record in records
        )
        assert all(
            record["xianxia_energy_maximum_increases"] == record["energy_maximum_increases"]
            for record in records
        )
        assert all(
            record["rank_resource_grants_status"]
            == XIANXIA_MARTIAL_ART_RANK_RESOURCE_GRANTS_STATUS_ENERGY_MAXIMUMS_SEEDED
            for record in records
        )
        assert all(
            record["rank_ability_grants_status"]
            == XIANXIA_MARTIAL_ART_RANK_ABILITY_GRANTS_STATUS_KIND_TAGS_SEEDED
            for record in records
        )
        assert all(
            record["rank_ability_effects_status"]
            == XIANXIA_MARTIAL_ART_RANK_ABILITY_EFFECTS_STATUS_COST_RANGE_DAMAGE_DURATION_SUPPORT_SEEDED
            for record in records
        )
        assert all(record["xianxia_ability_grants"] == record["ability_grants"] for record in records)
        assert all(
            set(grant)
            >= {
                "resource_costs",
                "range_tags",
                "damage_effort_tags",
                "duration_tags",
                "support_state",
                "xianxia_support_state",
            }
            for record in records
            for grant in record["ability_grants"]
        )
        assert all(
            grant["support_state"] == XIANXIA_MARTIAL_ART_ABILITY_DEFAULT_SUPPORT_STATE
            for record in records
            for grant in record["ability_grants"]
        )
        assert metadata["martial_art_rank_resource_grants"] == {
            record["rank_key"]: record["energy_maximum_increases"]
            for record in records
        }
        assert metadata["xianxia_martial_art_rank_resource_grants"] == (
            metadata["martial_art_rank_resource_grants"]
        )
        assert martial_art_body["rank_resource_grants"] == metadata["martial_art_rank_resource_grants"]
        assert martial_art_body["xianxia_martial_art_rank_resource_grants"] == (
            metadata["martial_art_rank_resource_grants"]
        )
        assert metadata["martial_art_rank_ability_grants"] == {
            record["rank_key"]: record["ability_grants"]
            for record in records
        }
        assert metadata["xianxia_martial_art_rank_ability_grants"] == (
            metadata["martial_art_rank_ability_grants"]
        )
        assert martial_art_body["rank_ability_grants"] == metadata["martial_art_rank_ability_grants"]
        assert martial_art_body["xianxia_martial_art_rank_ability_grants"] == (
            metadata["martial_art_rank_ability_grants"]
        )
        assert metadata["rank_ability_effects_seeded"] is True
        assert martial_art_body["rank_ability_effects_seeded"] is True
        assert (
            metadata["rank_ability_effects_status"]
            == XIANXIA_MARTIAL_ART_RANK_ABILITY_EFFECTS_STATUS_COST_RANGE_DAMAGE_DURATION_SUPPORT_SEEDED
        )
        assert martial_art_body["rank_ability_effects_status"] == metadata["rank_ability_effects_status"]
        assert all(record["rank_available_in_seed"] is True for record in records)
        assert all(record["is_incomplete_rank"] is False for record in records)
        assert all(
            record["rank_completion_status"] == XIANXIA_MARTIAL_ART_RANK_STATUS_PRESENT
            for record in records
        )
        assert (
            entry_map[slug]["metadata"]["rank_records_status"]
            == XIANXIA_MARTIAL_ART_RANK_RECORDS_STATUS_ADVANCEMENT_METADATA_SEEDED
        )
        assert (
            entry_map[slug]["metadata"]["rank_completion_status"]
            == XIANXIA_MARTIAL_ART_RANK_COMPLETION_STATUS_COMPLETE
        )
        assert (
            entry_map[slug]["metadata"]["xianxia_rank_completion_status"]
            == XIANXIA_MARTIAL_ART_RANK_COMPLETION_STATUS_COMPLETE
        )
        assert "missing_rank_keys" not in entry_map[slug]["metadata"]
        assert "source_draft_status" not in entry_map[slug]["metadata"]
        assert entry_map[slug]["metadata"]["has_incomplete_ranks"] is False
        assert entry_map[slug]["metadata"]["incomplete_rank_flags"] == {
            rank_key: False for rank_key in complete_rank_keys
        }
        assert entry_map[slug]["metadata"]["martial_art_missing_rank_records"] == []
        assert "Intentional Draft Content" not in entry_map[slug]["rendered_html"]

    for slug, expected_rank_keys in incomplete_rank_keys.items():
        records = entry_map[slug]["metadata"]["martial_art_rank_records"]
        assert [record["rank_key"] for record in records] == expected_rank_keys
        assert all(record["rank_available_in_seed"] is True for record in records)
        assert all(record["is_incomplete_rank"] is False for record in records)
        assert all(
            record["energy_maximum_increases"]
            == rank_resource_grants[record["martial_art_key"]][record["rank_key"]]
            for record in records
        )
        assert all(record["rank_ability_grants_status"] is not None for record in records)
        assert all(record["rank_ability_effects_status"] is not None for record in records)
        assert all(record["ability_grants"] for record in records)
        assert all(
            grant["support_state"] == XIANXIA_MARTIAL_ART_ABILITY_DEFAULT_SUPPORT_STATE
            for record in records
            for grant in record["ability_grants"]
        )
        missing_rank_keys = complete_rank_keys[len(expected_rank_keys) :]
        missing_rank_names = [rank_name_by_key[rank_key] for rank_key in missing_rank_keys]
        metadata = entry_map[slug]["metadata"]
        martial_art_body = entry_map[slug]["body"]["xianxia_martial_art"]
        missing_records = metadata["martial_art_missing_rank_records"]
        assert metadata["rank_completion_status"] == (
            XIANXIA_MARTIAL_ART_RANK_COMPLETION_STATUS_INTENTIONAL_DRAFT
        )
        assert metadata["xianxia_rank_completion_status"] == (
            XIANXIA_MARTIAL_ART_RANK_COMPLETION_STATUS_INTENTIONAL_DRAFT
        )
        assert metadata["missing_rank_keys"] == missing_rank_keys
        assert metadata["missing_rank_names"] == missing_rank_names
        assert (
            metadata["missing_rank_reason"]
            == XIANXIA_MARTIAL_ART_MISSING_RANK_REASON_INTENTIONAL_DRAFT
        )
        assert (
            metadata["source_draft_status"]
            == XIANXIA_MARTIAL_ART_MISSING_RANK_REASON_INTENTIONAL_DRAFT
        )
        assert metadata["has_incomplete_ranks"] is True
        assert metadata["incomplete_rank_flags"] == {
            rank_key: rank_key in missing_rank_keys for rank_key in complete_rank_keys
        }
        assert [record["rank_key"] for record in missing_records] == missing_rank_keys
        assert [record["rank_order"] for record in missing_records] == list(
            range(len(expected_rank_keys) + 1, 6)
        )
        assert all(record["energy_maximum_increases"] is None for record in missing_records)
        assert all(record["rank_resource_grants_status"] is None for record in missing_records)
        assert all(record["ability_grants"] == [] for record in missing_records)
        assert all(record["xianxia_ability_grants"] == [] for record in missing_records)
        assert all(record["rank_ability_grants_status"] is None for record in missing_records)
        assert all(record["rank_ability_effects_status"] is None for record in missing_records)
        assert metadata["martial_art_rank_resource_grants"] == {
            record["rank_key"]: record["energy_maximum_increases"]
            for record in records
        }
        assert martial_art_body["rank_resource_grants"] == metadata["martial_art_rank_resource_grants"]
        assert metadata["martial_art_rank_ability_grants"] == {
            record["rank_key"]: record["ability_grants"]
            for record in records
        }
        assert martial_art_body["rank_ability_grants"] == metadata["martial_art_rank_ability_grants"]
        assert metadata["rank_ability_effects_seeded"] is True
        assert martial_art_body["rank_ability_effects_seeded"] is True
        assert all(record["rank_available_in_seed"] is False for record in missing_records)
        assert all(record["is_incomplete_rank"] is True for record in missing_records)
        assert all(
            record["rank_completion_status"]
            == XIANXIA_MARTIAL_ART_RANK_STATUS_MISSING_INTENTIONAL_DRAFT
            for record in missing_records
        )
        assert all(
            record["incomplete_rank_reason"]
            == XIANXIA_MARTIAL_ART_MISSING_RANK_REASON_INTENTIONAL_DRAFT
            for record in missing_records
        )
        assert martial_art_body["rank_completion_status"] == (
            XIANXIA_MARTIAL_ART_RANK_COMPLETION_STATUS_INTENTIONAL_DRAFT
        )
        assert martial_art_body["has_incomplete_ranks"] is True
        assert martial_art_body["incomplete_rank_flags"] == metadata["incomplete_rank_flags"]
        assert martial_art_body["missing_rank_records"] == missing_records
        assert martial_art_body["missing_rank_keys"] == missing_rank_keys
        assert martial_art_body["missing_rank_names"] == missing_rank_names
        assert "intentional draft content" in entry_map[slug]["search_text"]
        assert "not an import failure" in entry_map[slug]["search_text"]
        assert "Intentional Draft Content" in entry_map[slug]["rendered_html"]
        assert "Missing higher ranks:" in entry_map[slug]["rendered_html"]
        for missing_rank_name in missing_rank_names:
            assert missing_rank_name in entry_map[slug]["rendered_html"]

    demons_fist_ranks = entry_map["demons-fist"]["body"]["xianxia_martial_art"]["rank_records"]
    assert demons_fist_ranks[0]["martial_art_key"] == "demons_fist"
    assert demons_fist_ranks[0]["martial_art_slug"] == "demons-fist"
    assert demons_fist_ranks[0]["rank_key"] == "initiate"
    assert demons_fist_ranks[0]["rank_name"] == "Initiate"
    assert demons_fist_ranks[0]["rank_order"] == 1
    assert demons_fist_ranks[0]["rank_ref"] == "xianxia:demons-fist:initiate"
    assert demons_fist_ranks[0]["prerequisite_rank_key"] is None
    assert demons_fist_ranks[0]["prerequisite_rank_name"] is None
    assert demons_fist_ranks[0]["insight_cost"] == 1
    assert demons_fist_ranks[0]["teacher_breakthrough_requirement"] == "none"
    assert demons_fist_ranks[0]["teacher_breakthrough_note"] == ""
    assert demons_fist_ranks[0]["rank_available_in_seed"] is True
    assert demons_fist_ranks[0]["is_incomplete_rank"] is False
    assert demons_fist_ranks[-1]["rank_ref"] == "xianxia:demons-fist:legendary"
    assert demons_fist_ranks[-1]["prerequisite_rank_key"] == "master"
    assert demons_fist_ranks[-1]["teacher_breakthrough_requirement"] == "ascension_breakthrough"
    assert "quest or mythic-level master" in demons_fist_ranks[-1]["legendary_prerequisite_note"]
    qi_fist = demons_fist_ranks[0]["ability_grants"][0]
    assert qi_fist["ability_key"] == "qi_fist_technique"
    assert qi_fist["kind_key"] == "technique"
    assert qi_fist["ability_ref"] == "xianxia:demons-fist:initiate:qi-fist-technique"
    assert "qi fist technique" in entry_map["demons-fist"]["search_text"]
    assert qi_fist["ability_ref"] in demons_fist_html


def test_xianxia_generic_technique_seed_entries_cover_requirements_catalog():
    entries = build_xianxia_systems_seed_entries()
    generic_entries = [entry for entry in entries if entry["entry_type"] == "generic_technique"]
    expected_titles = [
        "Cultivation",
        "Meditation",
        "Conditioning",
        "Training",
        "Qi Blast",
        "Scolding Backhand",
        "Wind Glide",
        "Great Leap",
        "Meteor Walk",
        "Flight",
        "Duelist",
        "Flash Step",
        "Speed Blitz",
        "Graceful Balance",
        "Kip-Up",
        "Water Run",
        "Yin Healing",
        "Yin Cleansing",
        "Yin Regeneration",
        "Yin Fortification",
        "Yang Enhancement",
        "Yang Sundering",
        "Two-Finger Disarmament",
        "Throat Crush",
        "Knuckle Splitter",
        "Cyclone Barrage",
        "Disorientating Palm Strike",
        "Pressing Stance Break",
        "Piercing Blow",
        "Cushioning Sway",
        "Enhanced Recuperation",
        "Enhanced Recollection",
        "Enhanced Flowing Dao",
    ]

    assert [entry["title"] for entry in generic_entries] == expected_titles
    assert [entry["metadata"]["generic_technique_catalog_order"] for entry in generic_entries] == list(
        range(1, 34)
    )
    assert all(entry["metadata"]["xianxia_entry_facets"] == ["generic_technique"] for entry in generic_entries)
    assert all(entry["metadata"]["catalog_role"] == "standalone_generic_technique" for entry in generic_entries)
    generic_technique_details = build_xianxia_generic_technique_details()
    assert tuple(generic_technique_details) == tuple(
        entry["metadata"]["generic_technique_key"] for entry in generic_entries
    )
    assert all(entry["metadata"]["generic_technique_details_seeded"] is True for entry in generic_entries)
    assert all(
        entry["metadata"]["generic_technique_details_status"]
        == XIANXIA_GENERIC_TECHNIQUE_DETAILS_STATUS_COST_PREREQ_RESOURCE_RANGE_EFFORT_RESET_SUPPORT_SEEDED
        for entry in generic_entries
    )
    assert all(entry["metadata"]["insight_cost"] > 0 for entry in generic_entries)
    assert all(isinstance(entry["metadata"]["prerequisites"], list) for entry in generic_entries)
    assert all(isinstance(entry["metadata"]["resource_costs"], list) for entry in generic_entries)
    assert all(isinstance(entry["metadata"]["range_tags"], list) for entry in generic_entries)
    assert all(isinstance(entry["metadata"]["effort_tags"], list) for entry in generic_entries)
    assert all("reset_cadence" in entry["metadata"] for entry in generic_entries)
    assert all(
        entry["metadata"]["support_state"] == XIANXIA_GENERIC_TECHNIQUE_DEFAULT_SUPPORT_STATE
        for entry in generic_entries
    )
    assert all(
        detail["available_at_character_creation"] is False
        for detail in generic_technique_details.values()
    )
    assert all(
        detail["character_creation_availability"]
        == XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_UNAVAILABLE_BY_DEFAULT
        for detail in generic_technique_details.values()
    )
    assert all(
        detail["learnable_without_master"] is True
        for detail in generic_technique_details.values()
    )
    assert all(
        detail["requires_master"] is False
        for detail in generic_technique_details.values()
    )
    assert all(
        detail["master_requirement"] == XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_NONE
        for detail in generic_technique_details.values()
    )
    assert all(
        entry["metadata"]["available_at_character_creation"] is False
        for entry in generic_entries
    )
    assert all(
        entry["metadata"]["character_creation_availability"]
        == XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_UNAVAILABLE_BY_DEFAULT
        for entry in generic_entries
    )
    assert all(
        entry["metadata"]["character_creation_availability_reason"]
        == XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_REASON_INSIGHT_STARTS_AT_0
        for entry in generic_entries
    )
    assert all(
        entry["metadata"]["character_creation_availability_note"]
        == XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_NOTE_INSIGHT_STARTS_AT_0
        for entry in generic_entries
    )
    assert all(
        entry["metadata"]["character_creation_availability_status"]
        == XIANXIA_GENERIC_TECHNIQUE_CHARACTER_CREATION_AVAILABILITY_STATUS_SEEDED
        for entry in generic_entries
    )
    assert all(
        entry["metadata"]["learnable_without_master"] is True
        for entry in generic_entries
    )
    assert all(entry["metadata"]["requires_master"] is False for entry in generic_entries)
    assert all(
        entry["metadata"]["master_requirement"] == XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_NONE
        for entry in generic_entries
    )
    assert all(
        entry["metadata"]["master_requirement_reason"]
        == XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_REASON_NO_MASTER_REQUIRED
        for entry in generic_entries
    )
    assert all(
        entry["metadata"]["master_requirement_note"]
        == XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_NOTE_NO_MASTER_REQUIRED
        for entry in generic_entries
    )
    assert all(
        entry["metadata"]["master_requirement_status"]
        == XIANXIA_GENERIC_TECHNIQUE_MASTER_REQUIREMENT_STATUS_LEARNABLE_WITHOUT_MASTER
        for entry in generic_entries
    )
    assert all(
        entry["body"]["xianxia_generic_technique"]["details_status"]
        == XIANXIA_GENERIC_TECHNIQUE_DETAILS_STATUS_COST_PREREQ_RESOURCE_RANGE_EFFORT_RESET_SUPPORT_SEEDED
        for entry in generic_entries
    )
    assert all(
        entry["body"]["xianxia_generic_technique"]["available_at_character_creation"] is False
        for entry in generic_entries
    )
    assert all(
        entry["body"]["xianxia_generic_technique"]["learnable_without_master"] is True
        for entry in generic_entries
    )
    assert all(
        entry["body"]["xianxia_generic_technique"]["requires_master"] is False
        for entry in generic_entries
    )

    entry_map = {entry["slug"]: entry for entry in generic_entries}
    qi_blast = entry_map["qi-blast"]
    assert qi_blast["metadata"]["generic_technique_key"] == "qi_blast"
    assert qi_blast["metadata"]["insight_cost"] == 1
    assert qi_blast["metadata"]["resource_costs"] == [
        {"resource_key": "qi", "amount": 1, "timing": "near_range_use"},
        {
            "resource_key": "qi",
            "amount": 2,
            "timing": "far_range_option",
            "note": "Costs 2 Qi for Far range.",
        },
    ]
    assert qi_blast["metadata"]["range_tags"] == ["near", "far"]
    assert qi_blast["metadata"]["effort_tags"] == ["magic_effort_damage"]
    assert qi_blast["metadata"]["reset_cadence"] is None
    assert qi_blast["body"]["xianxia_generic_technique"]["source_text"].startswith(
        "[1] Qi Blast: Spend a point of Qi"
    )
    assert qi_blast["body"]["xianxia_generic_technique"]["insight_cost"] == 1
    assert "Spend a point of Qi" in qi_blast["rendered_html"]
    assert "Insight Cost" in qi_blast["rendered_html"]
    assert "Character Creation" in qi_blast["rendered_html"]
    assert "Insight starts at 0" in qi_blast["rendered_html"]
    assert "Learning" in qi_blast["rendered_html"]
    assert "learnable without a Master" in qi_blast["rendered_html"]
    assert "magic effort damage" in qi_blast["rendered_html"]
    assert "qi blast" in qi_blast["search_text"]
    assert "magic_effort_damage" in qi_blast["search_text"]
    assert "unavailable_by_default" in qi_blast["search_text"]
    assert "insight_starts_at_0" in qi_blast["search_text"]
    assert "generic_techniques_do_not_require_master" in qi_blast["search_text"]
    assert "learnable_without_master" in qi_blast["search_text"]

    scolding_backhand = entry_map["scolding-backhand"]
    assert scolding_backhand["metadata"]["reset_cadence"] == "once_per_combat"
    assert scolding_backhand["metadata"]["prerequisites"][0]["kind"] == "target_comparison"
    assert scolding_backhand["metadata"]["effort_tags"] == ["basic_effort_damage"]

    meteor_walk = entry_map["meteor-walk"]
    assert meteor_walk["metadata"]["insight_cost"] == 8
    assert meteor_walk["metadata"]["prerequisites"] == [
        {"kind": "realm", "value": "immortal", "label": "Immortal Status"}
    ]
    assert meteor_walk["metadata"]["resource_costs"] == [{"resource_key": "shen", "amount": 1}]

    enhanced_recollection = entry_map["enhanced-recollection"]
    assert enhanced_recollection["metadata"]["insight_cost"] == 6
    assert enhanced_recollection["metadata"]["prerequisites"][0]["value"] == "recollect"

    enhanced_flowing_dao = entry_map["enhanced-flowing-dao"]
    assert enhanced_flowing_dao["metadata"]["generic_technique_catalog_order"] == 33
    assert enhanced_flowing_dao["metadata"]["insight_cost"] == 5
    assert enhanced_flowing_dao["metadata"]["prerequisites"][0]["value"] == "flowing_dao"
    assert "Gain an additional +1 Action" in enhanced_flowing_dao["rendered_html"]


def test_xianxia_basic_action_seed_entries_cover_requirements_catalog():
    entries = build_xianxia_systems_seed_entries()
    basic_action_entries = [entry for entry in entries if entry["entry_type"] == "basic_action"]
    expected_titles = [
        "Recoup",
        "Recollect",
        "Duel",
        "Taunt",
        "Wide Dispatch",
        "Flowing Dao",
        "Throat Jab",
        "Knuckle Strike",
        "Defend",
        "All-Out Offense",
        "Parry",
    ]

    assert [entry["title"] for entry in basic_action_entries] == expected_titles
    assert [entry["metadata"]["basic_action_catalog_order"] for entry in basic_action_entries] == list(
        range(1, 12)
    )
    assert all(entry["metadata"]["xianxia_entry_facets"] == ["basic_action"] for entry in basic_action_entries)
    assert all(entry["metadata"]["catalog_role"] == "basic_action" for entry in basic_action_entries)
    basic_action_details = build_xianxia_basic_action_details()
    assert tuple(basic_action_details) == tuple(
        entry["metadata"]["basic_action_key"] for entry in basic_action_entries
    )
    assert all(entry["metadata"]["basic_action_details_seeded"] is True for entry in basic_action_entries)
    assert all(
        entry["metadata"]["basic_action_details_status"]
        == XIANXIA_BASIC_ACTION_DETAILS_STATUS_RANGE_TIMING_SEEDED
        for entry in basic_action_entries
    )
    assert all(isinstance(entry["metadata"]["range_tags"], list) for entry in basic_action_entries)
    assert all(isinstance(entry["metadata"]["timing_tags"], list) for entry in basic_action_entries)
    assert all(entry["metadata"]["timing_tags"] for entry in basic_action_entries)
    assert all(
        entry["metadata"]["support_state"] == XIANXIA_BASIC_ACTION_DEFAULT_SUPPORT_STATE
        for entry in basic_action_entries
    )
    assert all(
        entry["metadata"]["xianxia_support_state"] == XIANXIA_BASIC_ACTION_DEFAULT_SUPPORT_STATE
        for entry in basic_action_entries
    )
    assert all(
        entry["body"]["support_state"] == XIANXIA_BASIC_ACTION_DEFAULT_SUPPORT_STATE
        for entry in basic_action_entries
    )
    assert all(
        entry["body"]["xianxia_basic_action"]["details_status"]
        == XIANXIA_BASIC_ACTION_DETAILS_STATUS_RANGE_TIMING_SEEDED
        for entry in basic_action_entries
    )
    assert all(
        entry["body"]["xianxia_basic_action"]["range_tags"] == entry["metadata"]["range_tags"]
        for entry in basic_action_entries
    )
    assert all(
        entry["body"]["xianxia_basic_action"]["timing_tags"] == entry["metadata"]["timing_tags"]
        for entry in basic_action_entries
    )

    entry_map = {entry["slug"]: entry for entry in basic_action_entries}
    assert entry_map["recoup"]["metadata"]["basic_action_key"] == "recoup"
    assert entry_map["recoup"]["metadata"]["range_tags"] == ["self"]
    assert entry_map["recoup"]["metadata"]["timing_tags"] == ["action"]
    assert "recover 10 Stance" in entry_map["recoup"]["body"]["xianxia_basic_action"]["source_text"]
    assert "recover 10 Stance" in entry_map["recoup"]["rendered_html"]
    assert "Basic Action Details" in entry_map["recoup"]["rendered_html"]
    assert "Ranges" in entry_map["recoup"]["rendered_html"]
    assert "Timing" in entry_map["recoup"]["rendered_html"]
    assert "recoup action" in entry_map["recoup"]["search_text"]
    assert "range_timing_metadata_seeded" in entry_map["recoup"]["search_text"]

    duel = entry_map["duel"]
    assert duel["metadata"]["xianxia_basic_action_key"] == "duel"
    assert duel["metadata"]["range_tags"] == [
        "melee_attack_target",
        "close_combat",
        "one_space_disengage",
    ]
    assert duel["metadata"]["timing_tags"] == [
        "after_melee_attack",
        "action_to_disengage",
        "while_duel_active",
    ]
    assert "Ranged Attacks are automatically made HARD" in duel["rendered_html"]
    assert "one Space away" in duel["rendered_html"]
    assert "minion" in duel["search_text"]
    assert "close_combat" in duel["search_text"]

    flowing_dao = entry_map["flowing-dao"]
    assert flowing_dao["metadata"]["basic_action_catalog_order"] == 6
    assert flowing_dao["metadata"]["range_tags"] == ["self"]
    assert flowing_dao["metadata"]["timing_tags"] == ["once_per_turn"]
    assert "spend a point of Dao" in flowing_dao["rendered_html"]

    throat_jab = entry_map["throat-jab"]
    assert throat_jab["metadata"]["timing_tags"] == ["action", "1_round"]
    assert "1 Round" in throat_jab["rendered_html"]

    wide_dispatch = entry_map["wide-dispatch"]
    assert wide_dispatch["metadata"]["range_tags"] == [
        "area_within_3_spaces",
        "minion_targets",
    ]
    assert "15 feet" in wide_dispatch["rendered_html"]

    defend = entry_map["defend"]
    assert defend["title"] == "Defend"
    assert "Defend Stance" in defend["metadata"]["aliases"]
    assert defend["metadata"]["range_tags"] == ["self"]
    assert defend["metadata"]["timing_tags"] == ["action", "while_active"]
    assert "Defense is +5" in defend["rendered_html"]

    all_out_offense = entry_map["all-out-offense"]
    assert all_out_offense["metadata"]["basic_action_key"] == "all_out_offense"
    assert all_out_offense["metadata"]["timing_tags"] == ["action", "while_active"]
    assert "Deal an additional +5 Damage" in all_out_offense["rendered_html"]

    parry = entry_map["parry"]
    assert parry["metadata"]["basic_action_catalog_order"] == 11
    assert parry["metadata"]["range_tags"] == ["self", "opponent_attacking_self"]
    assert parry["metadata"]["timing_tags"] == [
        "action",
        "while_active",
        "immediate_counter_attack",
    ]
    assert "Counter-Attack" in parry["rendered_html"]
    assert "Weapon Effort" in parry["rendered_html"]


def test_xianxia_reference_only_seed_entry_facets_are_forced_reference_only():
    for facet in ("basic_action", "condition", "status"):
        entry = _build_seed_entry(
            {
                "title": f"Reference {facet}",
                "entry_type": facet,
                "facets": [facet],
                "summary": f"Reference-only Xianxia {facet} reminder.",
            },
            index=1,
            source_path="managed:test",
        )

        assert entry["entry_type"] == facet
        assert entry["metadata"]["facets"] == [facet]
        assert entry["metadata"]["support_state"] == "reference_only"
        assert entry["metadata"]["xianxia_support_state"] == "reference_only"
        assert entry["body"]["support_state"] == "reference_only"
        assert entry["body"]["xianxia_support_state"] == "reference_only"

    with pytest.raises(ValueError, match="reference-only facets condition"):
        _build_seed_entry(
            {
                "title": "Modeled condition draft",
                "entry_type": "rule",
                "facets": ["condition"],
                "summary": "This should stay reference-only in Milestone 1.",
                "metadata": {"support_state": "modeled"},
            },
            index=1,
            source_path="managed:test",
        )


def test_xianxia_curated_seed_manifest_replaces_stale_shared_rows(app):
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]

        service.ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)
        store.replace_entries_for_source(
            XIANXIA_SYSTEM_CODE,
            XIANXIA_HOMEBREW_SOURCE_ID,
            entries=[
                {
                    "entry_key": "xianxia|rule|xianxia-homebrew|admin-authored-draft",
                    "entry_type": "rule",
                    "slug": "admin-authored-draft",
                    "title": "Admin Authored Draft",
                    "search_text": "admin authored draft xianxia homebrew",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"rule_key": "admin-authored-draft"},
                    "body": {},
                    "rendered_html": "<p>Temporary shared draft row.</p>",
                }
            ],
        )

        service.ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)
        entries = store.list_entries_for_source(
            XIANXIA_SYSTEM_CODE,
            XIANXIA_HOMEBREW_SOURCE_ID,
            limit=None,
        )
        expected_titles = {entry["title"] for entry in build_xianxia_systems_seed_entries()}
        seeded_titles = {entry.title for entry in entries}

        assert seeded_titles == expected_titles
        assert "Admin Authored Draft" not in seeded_titles


def test_xianxia_homebrew_source_policy_defaults_dm_only_when_campaign_selects_library(app):
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    payload["system"] = "xianxia"
    payload["systems_library"] = "xianxia"
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with app.app_context():
        app.extensions["repository_store"].refresh()
        service = app.extensions["systems_service"]

        state = service.get_campaign_source_state("linden-pass", XIANXIA_HOMEBREW_SOURCE_ID)

        assert state is not None
        assert state.source.library_slug == XIANXIA_SYSTEM_CODE
        assert state.source.source_id == XIANXIA_HOMEBREW_SOURCE_ID
        assert state.is_enabled is False
        assert state.default_visibility == VISIBILITY_DM
        assert state.is_configured is False


def test_xianxia_homebrew_source_policy_unit_defaults_dm_and_rejects_public_visibility(
    app, users
):
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    payload["system"] = "xianxia"
    payload["systems_library"] = "xianxia"
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with app.app_context():
        app.extensions["repository_store"].refresh()
        service = app.extensions["systems_service"]
        service.ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)

        state = service.get_campaign_source_state("linden-pass", XIANXIA_HOMEBREW_SOURCE_ID)

        assert state is not None
        assert state.source.library_slug == XIANXIA_SYSTEM_CODE
        assert state.source.license_class == "open_license"
        assert state.source.public_visibility_allowed is False
        assert state.source.requires_unofficial_notice is False
        assert state.is_enabled is False
        assert state.default_visibility == VISIBILITY_DM
        assert state.is_configured is False

        with pytest.raises(SystemsPolicyValidationError, match="cannot be made public"):
            service.update_campaign_sources(
                "linden-pass",
                updates=[
                    {
                        "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                        "is_enabled": True,
                        "default_visibility": VISIBILITY_PUBLIC,
                    }
                ],
                actor_user_id=users["dm"]["id"],
                acknowledge_proprietary=False,
                can_set_private=False,
            )

        unchanged_state = service.get_campaign_source_state(
            "linden-pass",
            XIANXIA_HOMEBREW_SOURCE_ID,
        )
        assert unchanged_state is not None
        assert unchanged_state.is_enabled is False
        assert unchanged_state.default_visibility == VISIBILITY_DM
        assert unchanged_state.is_configured is False

        changed_sources = service.update_campaign_sources(
            "linden-pass",
            updates=[
                {
                    "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                    "is_enabled": True,
                    "default_visibility": VISIBILITY_PLAYERS,
                }
            ],
            actor_user_id=users["dm"]["id"],
            acknowledge_proprietary=False,
            can_set_private=False,
        )
        updated_state = service.get_campaign_source_state("linden-pass", XIANXIA_HOMEBREW_SOURCE_ID)

        assert [source.source_id for source in changed_sources] == [XIANXIA_HOMEBREW_SOURCE_ID]
        assert updated_state is not None
        assert updated_state.is_enabled is True
        assert updated_state.default_visibility == VISIBILITY_PLAYERS
        assert updated_state.is_configured is True


def test_xianxia_campaign_systems_scope_defaults_dm_only_while_wiki_stays_visible(
    app, client, sign_in, users
):
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    payload["system"] = "xianxia"
    payload["systems_library"] = "xianxia"
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with app.app_context():
        app.extensions["repository_store"].refresh()
        assert get_campaign_scope_visibility("linden-pass", "systems") == VISIBILITY_DM
        assert get_effective_campaign_visibility("linden-pass", "systems") == VISIBILITY_DM
        assert get_campaign_scope_visibility("linden-pass", "wiki") == VISIBILITY_PUBLIC
        assert get_effective_campaign_visibility("linden-pass", "wiki") == VISIBILITY_PUBLIC

    sign_in(users["party"]["email"], users["party"]["password"])
    campaign = client.get("/campaigns/linden-pass")
    wiki_page = client.get("/campaigns/linden-pass/pages/index")
    systems = client.get("/campaigns/linden-pass/systems")

    assert campaign.status_code == 200
    assert wiki_page.status_code == 200
    assert 'href="/campaigns/linden-pass/systems"' not in campaign.get_data(as_text=True)
    assert systems.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    dm_systems = client.get("/campaigns/linden-pass/systems")

    assert dm_systems.status_code == 200


def test_xianxia_source_policy_defaults_entries_dm_only_while_player_wiki_stays_visible(
    app, client, sign_in, users
):
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    payload["system"] = "xianxia"
    payload["systems_library"] = "xianxia"
    payload["systems_sources"] = [
        {
            "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
            "enabled": True,
        }
    ]
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    entry_slug = "dao"
    with app.app_context():
        app.extensions["repository_store"].refresh()
        service = app.extensions["systems_service"]
        service.ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)

        state = service.get_campaign_source_state("linden-pass", XIANXIA_HOMEBREW_SOURCE_ID)
        entry = service.get_entry_by_slug_for_campaign("linden-pass", entry_slug)

        assert state is not None
        assert state.is_enabled is True
        assert state.default_visibility == VISIBILITY_DM
        assert state.is_configured is False
        assert entry is not None
        assert service.is_entry_enabled_for_campaign("linden-pass", entry)
        assert get_campaign_scope_visibility("linden-pass", "systems") == VISIBILITY_DM
        assert get_effective_campaign_visibility("linden-pass", "systems") == VISIBILITY_DM
        assert get_campaign_scope_visibility("linden-pass", "wiki") == VISIBILITY_PUBLIC
        assert get_effective_campaign_visibility("linden-pass", "wiki") == VISIBILITY_PUBLIC

    sign_in(users["party"]["email"], users["party"]["password"])
    campaign = client.get("/campaigns/linden-pass")
    wiki_page = client.get("/campaigns/linden-pass/pages/index")
    systems = client.get("/campaigns/linden-pass/systems")
    source = client.get(f"/campaigns/linden-pass/systems/sources/{XIANXIA_HOMEBREW_SOURCE_ID}")
    entry_response = client.get(f"/campaigns/linden-pass/systems/entries/{entry_slug}")

    assert campaign.status_code == 200
    assert wiki_page.status_code == 200
    assert 'href="/campaigns/linden-pass/systems"' not in campaign.get_data(as_text=True)
    assert systems.status_code == 404
    assert source.status_code == 404
    assert entry_response.status_code == 404

    sign_in(users["dm"]["email"], users["dm"]["password"])
    dm_systems = client.get("/campaigns/linden-pass/systems")
    dm_search = client.get("/campaigns/linden-pass/systems/search?q=Dao")
    dm_entry = client.get(f"/campaigns/linden-pass/systems/entries/{entry_slug}")

    assert dm_systems.status_code == 200
    assert dm_search.status_code == 200
    assert "Dao" in dm_search.get_data(as_text=True)
    assert dm_entry.status_code == 200
    assert "Dao is a capped narrative and combat resource" in dm_entry.get_data(as_text=True)


def test_xianxia_systems_search_and_browse_stay_in_xianxia_library(
    app, client, sign_in, users
):
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    payload["system"] = "xianxia"
    payload["systems_library"] = "xianxia"
    payload["systems_sources"] = [
        {
            "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
            "enabled": True,
        }
    ]
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with app.app_context():
        app.extensions["repository_store"].refresh()
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        service.ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)
        service.ensure_builtin_library_seeded(DND_5E_SYSTEM_CODE)

        store.upsert_source(
            DND_5E_SYSTEM_CODE,
            XIANXIA_HOMEBREW_SOURCE_ID,
            title="DND Impostor Xianxia Source",
            license_class="open_license",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        store.replace_entries_for_source(
            DND_5E_SYSTEM_CODE,
            XIANXIA_HOMEBREW_SOURCE_ID,
            entries=[
                {
                    "entry_key": "dnd-5e|rule|xianxia-homebrew|dnd-dao-breathing",
                    "entry_type": "rule",
                    "slug": "dnd-dao-breathing",
                    "title": "DND Dao Breathing",
                    "search_text": "dao breathing xianxia homebrew dnd",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"rule_key": "dnd_dao_breathing"},
                    "body": {},
                    "rendered_html": "<p>This DND-5E row must not appear in Xianxia.</p>",
                }
            ],
        )

        search_results = service.search_entries_for_campaign(
            "linden-pass",
            query="Dao",
            include_source_ids=[XIANXIA_HOMEBREW_SOURCE_ID],
            limit=None,
        )
        rule_entries = service.list_entries_for_campaign_source(
            "linden-pass",
            XIANXIA_HOMEBREW_SOURCE_ID,
            entry_type="rule",
            limit=None,
        )

        assert "Dao" in {entry.title for entry in search_results}
        assert "DND Dao Breathing" not in {entry.title for entry in search_results}
        assert {entry.library_slug for entry in search_results} == {XIANXIA_SYSTEM_CODE}
        seed_rule_count = sum(
            1
            for entry in build_xianxia_systems_seed_entries()
            if entry["entry_type"] == "rule"
        )
        assert len(rule_entries) == seed_rule_count
        assert "Dao" in {entry.title for entry in rule_entries}
        assert {entry.library_slug for entry in rule_entries} == {XIANXIA_SYSTEM_CODE}
        assert service.get_entry_by_slug_for_campaign("linden-pass", "dnd-dao-breathing") is None

    sign_in(users["dm"]["email"], users["dm"]["password"])
    systems = client.get("/campaigns/linden-pass/systems/search?q=Dao")
    source = client.get(f"/campaigns/linden-pass/systems/sources/{XIANXIA_HOMEBREW_SOURCE_ID}")
    rule_category = client.get(
        f"/campaigns/linden-pass/systems/sources/{XIANXIA_HOMEBREW_SOURCE_ID}/types/rule"
    )
    martial_art_category = client.get(
        f"/campaigns/linden-pass/systems/sources/{XIANXIA_HOMEBREW_SOURCE_ID}/types/martial_art"
    )
    generic_technique_category = client.get(
        f"/campaigns/linden-pass/systems/sources/{XIANXIA_HOMEBREW_SOURCE_ID}/types/generic_technique"
    )
    basic_action_category = client.get(
        f"/campaigns/linden-pass/systems/sources/{XIANXIA_HOMEBREW_SOURCE_ID}/types/basic_action"
    )
    demons_fist_entry = client.get("/campaigns/linden-pass/systems/entries/demons-fist")
    qi_blast_entry = client.get("/campaigns/linden-pass/systems/entries/qi-blast")
    recoup_entry = client.get("/campaigns/linden-pass/systems/entries/recoup")
    dnd_entry = client.get("/campaigns/linden-pass/systems/entries/dnd-dao-breathing")

    assert systems.status_code == 200
    systems_html = systems.get_data(as_text=True)
    assert "Dao" in systems_html
    assert "DND Dao Breathing" not in systems_html
    assert "DND Impostor Xianxia Source" not in systems_html

    assert source.status_code == 200
    source_html = source.get_data(as_text=True)
    assert "Xianxia Homebrew" in source_html
    assert "DND Impostor Xianxia Source" not in source_html
    seed_entries = build_xianxia_systems_seed_entries()
    seed_count = len(seed_entries)
    seed_rule_count = sum(1 for entry in seed_entries if entry["entry_type"] == "rule")
    seed_generic_technique_count = sum(
        1 for entry in seed_entries if entry["entry_type"] == "generic_technique"
    )
    seed_basic_action_count = sum(
        1 for entry in seed_entries if entry["entry_type"] == "basic_action"
    )
    assert f"{seed_count} browsable entries across 4" in source_html
    assert "Generic Techniques" in source_html
    assert "Basic Actions" in source_html

    assert rule_category.status_code == 200
    category_html = rule_category.get_data(as_text=True)
    assert "Dao" in category_html
    assert "DND Dao Breathing" not in category_html
    assert f"Showing all {seed_rule_count} rules in this source." in category_html

    assert martial_art_category.status_code == 200
    martial_art_html = martial_art_category.get_data(as_text=True)
    assert "Demon&#39;s Fist" in martial_art_html
    assert "Flying Daggers" in martial_art_html
    assert "Showing all 30 martial arts in this source." in martial_art_html

    assert generic_technique_category.status_code == 200
    generic_technique_html = generic_technique_category.get_data(as_text=True)
    assert "Qi Blast" in generic_technique_html
    assert "Enhanced Flowing Dao" in generic_technique_html
    assert f"Showing all {seed_generic_technique_count} generic techniques in this source." in (
        generic_technique_html
    )

    assert basic_action_category.status_code == 200
    basic_action_html = basic_action_category.get_data(as_text=True)
    assert "Recoup" in basic_action_html
    assert "Parry" in basic_action_html
    assert f"Showing all {seed_basic_action_count} basic actions in this source." in (
        basic_action_html
    )

    assert demons_fist_entry.status_code == 200
    demons_fist_html = demons_fist_entry.get_data(as_text=True)
    assert "Demon&#39;s Fist" in demons_fist_html
    assert "Catalog Parent" in demons_fist_html
    assert "Structured rank records are seeded for the ranks present" in demons_fist_html
    assert "include Jing, Qi, and Shen maximum increases" in demons_fist_html
    assert "rank-granted ability names and kind tags" in demons_fist_html
    assert "Detailed ability rules remain deferred" in demons_fist_html
    assert "Rank Records" in demons_fist_html
    assert "Energy Maximum Increases" in demons_fist_html
    assert "xianxia:demons-fist:initiate" in demons_fist_html
    assert "Qi Fist Technique" in demons_fist_html
    assert "xianxia:demons-fist:initiate:qi-fist-technique" in demons_fist_html
    assert 'id="xianxia-demons-fist-initiate-qi-fist-technique"' in demons_fist_html
    assert 'href="#xianxia-demons-fist-initiate-qi-fist-technique"' in demons_fist_html

    assert qi_blast_entry.status_code == 200
    qi_blast_html = qi_blast_entry.get_data(as_text=True)
    assert "Qi Blast" in qi_blast_html
    assert "Spend a point of Qi" in qi_blast_html
    assert "Technique Details" in qi_blast_html
    assert "Insight Cost" in qi_blast_html
    assert "Resource Costs" in qi_blast_html
    assert "qi 1" in qi_blast_html

    assert recoup_entry.status_code == 200
    recoup_html = recoup_entry.get_data(as_text=True)
    assert "Recoup" in recoup_html
    assert "Spend an Action and 1 Energy" in recoup_html
    assert "Basic Action Details" in recoup_html
    assert "Ranges" in recoup_html
    assert "self" in recoup_html
    assert "Timing" in recoup_html
    assert "action" in recoup_html
    assert "Effort Tags" in qi_blast_html
    assert "magic effort damage" in qi_blast_html
    assert "Support State" in qi_blast_html
    assert "reference only" in qi_blast_html

    assert dnd_entry.status_code == 404


def test_xianxia_martial_art_parent_entry_renders_rank_info_and_ability_ref_links(
    app, client, sign_in, users
):
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    payload["system"] = "xianxia"
    payload["systems_library"] = "xianxia"
    payload["systems_sources"] = [
        {
            "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
            "enabled": True,
        }
    ]
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with app.app_context():
        app.extensions["repository_store"].refresh()
        service = app.extensions["systems_service"]
        service.ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)
        entry = service.get_entry_by_slug_for_campaign("linden-pass", "demons-fist")

        assert entry is not None
        assert entry.entry_type == "martial_art"
        assert entry.metadata["catalog_role"] == "parent"
        assert entry.metadata["martial_art_rank_records"][0]["rank_ref"] == (
            "xianxia:demons-fist:initiate"
        )
        assert entry.metadata["martial_art_rank_records"][0]["ability_grants"][0][
            "ability_ref"
        ] == "xianxia:demons-fist:initiate:qi-fist-technique"

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/systems/entries/demons-fist")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<h2>Rank Records</h2>" in html
    assert "<h3>Initiate</h3>" in html
    assert "Rank Ref:" in html
    assert 'href="#xianxia-demons-fist-initiate"' in html
    assert "xianxia:demons-fist:initiate" in html
    assert "Ability Refs" in html
    assert 'id="xianxia-demons-fist-initiate-qi-fist-technique"' in html
    assert 'href="#xianxia-demons-fist-initiate-qi-fist-technique"' in html
    assert "xianxia:demons-fist:initiate:qi-fist-technique" in html
    assert "Qi Fist Technique" in html
    assert "Technique" in html
    assert "Costs: qi 1" in html
    assert "Ranges: self" in html
    assert "Damage/Effort: weapon effort damage" in html
    assert "Duration: rest of combat" in html
    assert "reference only" in html


def test_xianxia_incomplete_martial_arts_stay_visible_with_draft_markers(
    app, client, sign_in, users
):
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    payload["system"] = "xianxia"
    payload["systems_library"] = "xianxia"
    payload["systems_sources"] = [
        {
            "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
            "enabled": True,
        }
    ]
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with app.app_context():
        app.extensions["repository_store"].refresh()
        service = app.extensions["systems_service"]
        service.ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)
        incomplete_entry = service.get_entry_by_slug_for_campaign("linden-pass", "flying-daggers")
        complete_entry = service.get_entry_by_slug_for_campaign("linden-pass", "demons-fist")

        assert incomplete_entry is not None
        assert incomplete_entry.entry_type == "martial_art"
        assert incomplete_entry.metadata["rank_completion_status"] == (
            XIANXIA_MARTIAL_ART_RANK_COMPLETION_STATUS_INTENTIONAL_DRAFT
        )
        assert incomplete_entry.metadata["missing_rank_names"] == [
            "Apprentice",
            "Master",
            "Legendary",
        ]
        assert incomplete_entry.metadata["has_incomplete_ranks"] is True

        assert complete_entry is not None
        assert complete_entry.metadata["rank_completion_status"] == (
            XIANXIA_MARTIAL_ART_RANK_COMPLETION_STATUS_COMPLETE
        )
        assert complete_entry.metadata["has_incomplete_ranks"] is False

    sign_in(users["dm"]["email"], users["dm"]["password"])
    category_response = client.get(
        f"/campaigns/linden-pass/systems/sources/{XIANXIA_HOMEBREW_SOURCE_ID}/types/martial_art"
    )
    incomplete_response = client.get("/campaigns/linden-pass/systems/entries/flying-daggers")
    complete_response = client.get("/campaigns/linden-pass/systems/entries/demons-fist")

    assert category_response.status_code == 200
    category_html = category_response.get_data(as_text=True)
    assert "Flying Daggers" in category_html
    assert "Demon&#39;s Fist" in category_html
    assert "Showing all 30 martial arts in this source." in category_html

    assert incomplete_response.status_code == 200
    incomplete_html = incomplete_response.get_data(as_text=True)
    assert "Flying Daggers" in incomplete_html
    assert "Intentional Draft Content" in incomplete_html
    assert "not an import failure" in incomplete_html
    assert "Missing higher ranks:" in incomplete_html
    assert "Apprentice, Master, Legendary" in incomplete_html
    assert "<h2>Rank Records</h2>" in incomplete_html
    assert "<h3>Initiate</h3>" in incomplete_html
    assert "<h3>Novice</h3>" in incomplete_html

    assert complete_response.status_code == 200
    complete_html = complete_response.get_data(as_text=True)
    assert "Demon&#39;s Fist" in complete_html
    assert "Intentional Draft Content" not in complete_html
    assert "Missing higher ranks:" not in complete_html


def test_xianxia_systems_source_and_category_labels_use_xianxia_vocabulary(
    app, client, sign_in, users
):
    source_id = "XIANXIA-LABEL-TEST"
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    payload["system"] = "xianxia"
    payload["systems_library"] = "xianxia"
    payload["systems_sources"] = [
        {
            "source_id": source_id,
            "enabled": True,
        }
    ]
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with app.app_context():
        app.extensions["repository_store"].refresh()
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        service.ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)
        store.upsert_source(
            XIANXIA_SYSTEM_CODE,
            source_id,
            title="Xianxia Label Test",
            license_class="open_license",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        store.upsert_entry(
            XIANXIA_SYSTEM_CODE,
            source_id,
            entry_key="xianxia|martial_art|label-test|azure-cloud-fist",
            entry_type="martial_art",
            slug="xianxia-azure-cloud-fist",
            title="Azure Cloud Fist",
            search_text="azure cloud fist martial art",
            player_safe_default=True,
            metadata={"xianxia_entry_facets": ["martial_art"]},
            body={},
            rendered_html="<p>A test Martial Art entry.</p>",
        )
        store.upsert_entry(
            XIANXIA_SYSTEM_CODE,
            source_id,
            entry_key="xianxia|generic_technique|label-test|meteor-step",
            entry_type="generic_technique",
            slug="xianxia-meteor-step",
            title="Meteor Step",
            search_text="meteor step generic technique",
            player_safe_default=True,
            metadata={"xianxia_entry_facets": ["generic_technique"]},
            body={},
            rendered_html="<p>A test Generic Technique entry.</p>",
        )
        store.upsert_entry(
            XIANXIA_SYSTEM_CODE,
            source_id,
            entry_key="xianxia|equipment|label-test|jade-compass",
            entry_type="equipment",
            slug="xianxia-jade-compass",
            title="Jade Compass",
            search_text="jade compass equipment",
            player_safe_default=True,
            metadata={"xianxia_entry_facets": ["equipment"]},
            body={},
            rendered_html="<p>A test equipment entry.</p>",
        )

    sign_in(users["dm"]["email"], users["dm"]["password"])
    source = client.get(f"/campaigns/linden-pass/systems/sources/{source_id}")
    martial_art_category = client.get(
        f"/campaigns/linden-pass/systems/sources/{source_id}/types/martial_art"
    )

    assert source.status_code == 200
    source_html = source.get_data(as_text=True)
    assert "Choose a Xianxia content category" in source_html
    assert "Player&#39;s Handbook" not in source_html
    assert "Martial Arts" in source_html
    assert "Generic Techniques" in source_html
    assert "Equipment" in source_html
    assert "Subclasses" not in source_html

    assert martial_art_category.status_code == 200
    category_html = martial_art_category.get_data(as_text=True)
    assert "Xianxia Label Test: Martial Arts" in category_html
    assert "Browse Martial Arts" in category_html
    assert "Azure Cloud Fist" in category_html
    assert "Showing all 1 martial arts in this source." in category_html
    assert "Category: Martial Arts" in category_html


def test_xianxia_systems_entries_appear_on_expected_source_category_pages(
    app, client, sign_in, users
):
    source_id = "XIANXIA-CATEGORY-TEST"
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    payload["system"] = "xianxia"
    payload["systems_library"] = "xianxia"
    payload["systems_sources"] = [
        {
            "source_id": source_id,
            "enabled": True,
        }
    ]
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    category_expectations = {
        "rule": ("Rules", "Check Formula Reference"),
        "martial_art": ("Martial Arts", "Azure Cloud Fist"),
        "martial_art_rank": ("Martial Art Ranks", "Initiate Rank Reference"),
        "generic_technique": ("Generic Techniques", "Meteor Step"),
        "basic_action": ("Basic Actions", "Recoup"),
        "equipment": ("Equipment", "Jade Compass"),
        "armor": ("Armor", "Cloud Silk Armor"),
    }

    with app.app_context():
        app.extensions["repository_store"].refresh()
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        service.ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)
        store.upsert_source(
            XIANXIA_SYSTEM_CODE,
            source_id,
            title="Xianxia Category Test",
            license_class="open_license",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        store.replace_entries_for_source(
            XIANXIA_SYSTEM_CODE,
            source_id,
            entries=[
                {
                    "entry_key": f"xianxia|{entry_type}|category-test|{entry_type}",
                    "entry_type": entry_type,
                    "slug": f"xianxia-category-{entry_type.replace('_', '-')}",
                    "title": title,
                    "search_text": f"{title.lower()} {label.lower()} xianxia",
                    "player_safe_default": True,
                    "metadata": {"xianxia_entry_facets": [entry_type]},
                    "body": {},
                    "rendered_html": f"<p>{title} test body.</p>",
                }
                for entry_type, (label, title) in category_expectations.items()
            ],
        )

    sign_in(users["dm"]["email"], users["dm"]["password"])
    source = client.get(f"/campaigns/linden-pass/systems/sources/{source_id}")

    assert source.status_code == 200
    source_html = source.get_data(as_text=True)
    assert "Xianxia Category Test" in source_html
    assert "This source currently has 7 browsable entries" in source_html
    assert "across 7" in source_html

    for entry_type, (label, title) in category_expectations.items():
        category_href = f"/campaigns/linden-pass/systems/sources/{source_id}/types/{entry_type}"
        assert category_href in source_html
        assert label in source_html

        category = client.get(category_href)
        assert category.status_code == 200
        category_html = category.get_data(as_text=True)
        assert f"Xianxia Category Test: {label}" in category_html
        assert f"Browse {label}" in category_html
        assert f"Category: {label}" in category_html
        assert title in category_html
        assert f"Showing all 1 {label.lower()} in this source." in category_html

        other_titles = {
            other_title
            for other_type, (_, other_title) in category_expectations.items()
            if other_type != entry_type
        }
        assert all(other_title not in category_html for other_title in other_titles)


def test_xianxia_systems_search_uses_title_and_metadata_without_prose_parsing(
    app, client, sign_in, users
):
    source_id = "XIANXIA-SEARCH-TEST"
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    payload["system"] = "xianxia"
    payload["systems_library"] = "xianxia"
    payload["systems_sources"] = [
        {
            "source_id": source_id,
            "enabled": True,
        }
    ]
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with app.app_context():
        app.extensions["repository_store"].refresh()
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        service.ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)
        store.upsert_source(
            XIANXIA_SYSTEM_CODE,
            source_id,
            title="Xianxia Search Test",
            license_class="open_license",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        store.upsert_entry(
            XIANXIA_SYSTEM_CODE,
            source_id,
            entry_key="xianxia|rule|search-test|metadata-lantern",
            entry_type="rule",
            slug="metadata-lantern",
            title="Metadata Lantern",
            search_text="metadata lantern curated title boundary",
            player_safe_default=True,
            metadata={
                "rule_key": "metadata_lantern",
                "rule_facets": ["structured_harmonizer"],
                "aliases": ["Structured Harmonizer"],
                "reference_terms": ["curated-metadata-test"],
                "xianxia_entry_facets": ["rule"],
                "xianxia_rule_key": "metadata_lantern",
            },
            body={"summary": "The prose-only term verdantphoenix should not be searchable."},
            rendered_html="<p>The prose-only term verdantphoenix appears only in full prose.</p>",
        )

        title_results = service.search_entries_for_campaign(
            "linden-pass",
            query="Metadata Lantern",
            include_source_ids=[source_id],
            limit=None,
        )
        prose_global_results = service.search_entries_for_campaign(
            "linden-pass",
            query="verdantphoenix",
            include_source_ids=[source_id],
            limit=None,
        )
        metadata_reference_results = service.search_rules_reference_entries_for_campaign(
            "linden-pass",
            query="structured harmonizer",
            include_source_ids=[source_id],
            limit=None,
        )
        prose_reference_results = service.search_rules_reference_entries_for_campaign(
            "linden-pass",
            query="verdantphoenix",
            include_source_ids=[source_id],
            limit=None,
        )
        prose_category_results = service.list_entries_for_campaign_source(
            "linden-pass",
            source_id,
            entry_type="rule",
            query="verdantphoenix",
            limit=None,
        )

        assert "Metadata Lantern" in {entry.title for entry in title_results}
        assert "Metadata Lantern" in {entry.title for entry in metadata_reference_results}
        assert "Metadata Lantern" not in {entry.title for entry in prose_global_results}
        assert "Metadata Lantern" not in {entry.title for entry in prose_reference_results}
        assert "Metadata Lantern" not in {entry.title for entry in prose_category_results}

    sign_in(users["dm"]["email"], users["dm"]["password"])
    title_search = client.get("/campaigns/linden-pass/systems/search?q=Metadata+Lantern")
    metadata_search = client.get(
        "/campaigns/linden-pass/systems/search?reference_q=structured+harmonizer"
    )
    prose_search = client.get(
        "/campaigns/linden-pass/systems/search?q=verdantphoenix&reference_q=verdantphoenix"
    )
    prose_category = client.get(
        f"/campaigns/linden-pass/systems/sources/{source_id}/types/rule"
        "?q=verdantphoenix"
    )

    assert title_search.status_code == 200
    assert "Metadata Lantern" in title_search.get_data(as_text=True)

    assert metadata_search.status_code == 200
    assert "Metadata Lantern" in metadata_search.get_data(as_text=True)

    assert prose_search.status_code == 200
    prose_html = prose_search.get_data(as_text=True)
    assert "Metadata Lantern" not in prose_html
    assert "No imported systems entries matched that search yet." in prose_html
    assert "No rules references matched that metadata search yet." in prose_html

    assert prose_category.status_code == 200
    prose_category_html = prose_category.get_data(as_text=True)
    assert "Metadata Lantern" not in prose_category_html
    assert "No rules matched that title/type search." in prose_category_html


def test_dm_can_later_enable_xianxia_systems_for_players_through_existing_controls(
    app, client, sign_in, users
):
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    payload["system"] = "xianxia"
    payload["systems_library"] = "xianxia"
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with app.app_context():
        app.extensions["repository_store"].refresh()
        assert get_campaign_scope_visibility("linden-pass", "systems") == VISIBILITY_DM
        state = app.extensions["systems_service"].get_campaign_source_state(
            "linden-pass",
            XIANXIA_HOMEBREW_SOURCE_ID,
        )
        assert state is not None
        assert state.is_enabled is False
        assert state.default_visibility == VISIBILITY_DM

    sign_in(users["dm"]["email"], users["dm"]["password"])
    scope_response = client.post(
        "/campaigns/linden-pass/control-panel/visibility",
        data={
            "campaign_visibility": VISIBILITY_PUBLIC,
            "wiki_visibility": VISIBILITY_PUBLIC,
            "systems_visibility": VISIBILITY_PLAYERS,
            "session_visibility": VISIBILITY_PLAYERS,
            "combat_visibility": VISIBILITY_PLAYERS,
            "characters_visibility": VISIBILITY_DM,
            "dm_content_visibility": VISIBILITY_DM,
        },
        follow_redirects=True,
    )
    assert scope_response.status_code == 200
    assert "Updated visibility for Systems." in scope_response.get_data(as_text=True)

    source_form = build_source_form(app)
    source_form[f"source_{XIANXIA_HOMEBREW_SOURCE_ID}_enabled"] = "1"
    source_form[f"source_{XIANXIA_HOMEBREW_SOURCE_ID}_visibility"] = VISIBILITY_PLAYERS
    source_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/sources",
        data=source_form,
        follow_redirects=True,
    )
    assert source_response.status_code == 200
    assert f"Updated systems sources: {XIANXIA_HOMEBREW_SOURCE_ID}." in source_response.get_data(as_text=True)

    with app.app_context():
        assert get_campaign_scope_visibility("linden-pass", "systems") == VISIBILITY_PLAYERS
        state = app.extensions["systems_service"].get_campaign_source_state(
            "linden-pass",
            XIANXIA_HOMEBREW_SOURCE_ID,
        )
        assert state is not None
        assert state.is_enabled is True
        assert state.default_visibility == VISIBILITY_PLAYERS

    sign_in(users["party"]["email"], users["party"]["password"])
    campaign = client.get("/campaigns/linden-pass")
    systems = client.get("/campaigns/linden-pass/systems")
    source = client.get(f"/campaigns/linden-pass/systems/sources/{XIANXIA_HOMEBREW_SOURCE_ID}")

    assert campaign.status_code == 200
    assert 'href="/campaigns/linden-pass/systems"' in campaign.get_data(as_text=True)
    assert systems.status_code == 200
    assert "Xianxia Homebrew" in systems.get_data(as_text=True)
    assert source.status_code == 200
    assert "Xianxia Homebrew" in source.get_data(as_text=True)


def test_shared_core_systems_edit_flow_stays_separate_from_overrides_and_custom_entries(
    app, client, sign_in, users
):
    source_id = f"IMPT-{uuid4().hex[:8].upper()}"
    entry_slug = "shared-spark"
    entry_key = f"dnd-5e|spell|{source_id.lower()}|{entry_slug}"

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        store.upsert_source(
            library_slug,
            source_id,
            title="Imported Test Source",
            license_class="open_license",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug=library_slug,
            source_id=source_id,
            is_enabled=True,
            default_visibility="players",
        )
        store.replace_entries_for_source(
            library_slug,
            source_id,
            entries=[
                {
                    "entry_key": entry_key,
                    "entry_type": "spell",
                    "slug": entry_slug,
                    "title": "Shared Spark",
                    "search_text": "shared spark imported test source",
                    "player_safe_default": True,
                    "metadata": {},
                    "body": {"imported": True},
                    "rendered_html": "<p>Original shared library body.</p>",
                }
            ],
            entry_types=["spell"],
        )

    sign_in(users["dm"]["email"], users["dm"]["password"])
    detail = client.get(f"/campaigns/linden-pass/systems/entries/{entry_slug}")

    assert detail.status_code == 200
    detail_body = detail.get_data(as_text=True)
    assert "Entry Management" in detail_body
    assert "Shared library entry" in detail_body
    assert "Manage campaign override" in detail_body
    assert "shared/core content editing is app-admin-only" in detail_body
    assert "#systems-entry-overrides" in detail_body
    assert "Edit shared/core entry" not in detail_body
    assert "Edit custom entry" not in detail_body
    assert f"/systems/control-panel/custom-entries/{entry_slug}" not in detail_body

    shared_edit_page = client.get(
        f"/campaigns/linden-pass/systems/control-panel/shared-entries/{entry_slug}/edit"
    )
    assert shared_edit_page.status_code == 403

    shared_edit_post = client.post(
        f"/campaigns/linden-pass/systems/control-panel/shared-entries/{entry_slug}",
        data={"title": "Shared Spark Edited"},
        follow_redirects=False,
    )
    assert shared_edit_post.status_code == 403

    override_page = client.get(
        "/campaigns/linden-pass/dm-content/systems",
        query_string={"entry_key": entry_key},
    )
    assert override_page.status_code == 200
    assert f'value="{entry_key}"' in override_page.get_data(as_text=True)

    custom_edit_attempt = client.post(
        f"/campaigns/linden-pass/systems/control-panel/custom-entries/{entry_slug}",
        data={
            "custom_entry_title": "Shared Spark Edited",
            "custom_entry_type": "spell",
            "custom_entry_visibility": "dm",
            "custom_entry_body_markdown": "This should not save.",
        },
        follow_redirects=False,
    )
    assert custom_edit_attempt.status_code == 404

    sign_in(users["admin"]["email"], users["admin"]["password"])
    admin_shared_edit_page = client.get(
        f"/campaigns/linden-pass/systems/control-panel/shared-entries/{entry_slug}/edit"
    )
    assert admin_shared_edit_page.status_code == 200
    admin_shared_edit_body = admin_shared_edit_page.get_data(as_text=True)
    assert "Shared/core Systems editor" in admin_shared_edit_body
    assert 'name="shared_entry_title"' in admin_shared_edit_body
    assert 'name="shared_entry_metadata_json"' in admin_shared_edit_body
    assert 'id="shared-entry-edit-form"' in admin_shared_edit_body
    assert 'name="shared_entry_mechanics_impact_acknowledged"' in admin_shared_edit_body
    assert "source reimport" in admin_shared_edit_body
    assert 'name="custom_entry_title"' not in admin_shared_edit_body
    assert 'name="visibility_override"' not in admin_shared_edit_body

    missing_ack_shared_edit = client.post(
        f"/campaigns/linden-pass/systems/control-panel/shared-entries/{entry_slug}",
        data={
            "shared_entry_title": "Shared Spark Edited",
            "shared_entry_source_page": "42",
            "shared_entry_source_path": "sources/shared-spark.md",
            "shared_entry_search_text": "shared spark edited admin browser flow",
            "shared_entry_player_safe_default": "1",
            "shared_entry_metadata_json": '{"edited": true}',
            "shared_entry_body_json": "{}",
            "shared_entry_rendered_html": "<p>This should not save yet.</p>",
        },
        follow_redirects=False,
    )
    assert missing_ack_shared_edit.status_code == 400
    assert "Review and acknowledge the mechanics impact warning" in missing_ack_shared_edit.get_data(
        as_text=True
    )

    invalid_shared_edit = client.post(
        f"/campaigns/linden-pass/systems/control-panel/shared-entries/{entry_slug}",
        data={
            "shared_entry_title": "Shared Spark Edited",
            "shared_entry_mechanics_impact_acknowledged": "1",
            "shared_entry_metadata_json": "{bad json",
            "shared_entry_body_json": "{}",
            "shared_entry_rendered_html": "<p>This should not save.</p>",
        },
        follow_redirects=False,
    )
    assert invalid_shared_edit.status_code == 400
    assert "Metadata JSON must be valid JSON." in invalid_shared_edit.get_data(as_text=True)

    admin_shared_edit_post = client.post(
        f"/campaigns/linden-pass/systems/control-panel/shared-entries/{entry_slug}",
        data={
            "shared_entry_title": "Shared Spark Edited",
            "shared_entry_source_page": "42",
            "shared_entry_source_path": "sources/shared-spark.md",
            "shared_entry_search_text": "shared spark edited admin browser flow",
            "shared_entry_player_safe_default": "1",
            "shared_entry_mechanics_impact_acknowledged": "1",
            "shared_entry_metadata_json": '{"edited": true, "original_source": "imported-test"}',
            "shared_entry_body_json": '{"editor": "shared-core-browser"}',
            "shared_entry_rendered_html": "<p>Edited shared library body.</p>",
        },
        follow_redirects=False,
    )
    assert admin_shared_edit_post.status_code == 302
    assert f"/campaigns/linden-pass/systems/entries/{entry_slug}" in admin_shared_edit_post.headers[
        "Location"
    ]

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        entry = store.get_entry(service.get_campaign_library_slug("linden-pass"), entry_key)
        assert entry is not None
        assert entry.title == "Shared Spark Edited"
        assert entry.source_page == "42"
        assert entry.source_path == "sources/shared-spark.md"
        assert entry.search_text == "shared spark edited admin browser flow"
        assert entry.player_safe_default is True
        assert entry.dm_heavy is False
        assert entry.metadata == {"edited": True, "original_source": "imported-test"}
        assert entry.body == {"editor": "shared-core-browser"}
        assert entry.rendered_html == "<p>Edited shared library body.</p>"
        assert store.get_campaign_entry_override("linden-pass", entry_key) is None
        expected_edited_fields = [
            "title",
            "source_page",
            "source_path",
            "search_text",
            "metadata",
            "body",
            "rendered_html",
        ]
        edit_events = store.list_shared_entry_edit_events(
            library_slug=service.get_campaign_library_slug("linden-pass"),
            entry_key=entry_key,
            limit=5,
        )
        assert len(edit_events) == 1
        edit_event = edit_events[0]
        assert edit_event.campaign_slug == "linden-pass"
        assert edit_event.source_id == source_id
        assert edit_event.entry_slug == entry_slug
        assert edit_event.actor_user_id == users["admin"]["id"]
        assert edit_event.audit_event_type == "campaign_systems_shared_entry_updated"
        assert edit_event.edited_fields == expected_edited_fields
        assert edit_event.original_source_identity == {
            "library_slug": service.get_campaign_library_slug("linden-pass"),
            "source_id": source_id,
            "entry_key": entry_key,
            "entry_slug": entry_slug,
            "entry_type": "spell",
            "title": "Shared Spark",
            "source_page": "",
            "source_path": "",
        }
        assert edit_event.audit_metadata["edited_fields"] == expected_edited_fields
        assert edit_event.audit_metadata["campaign_slug"] == "linden-pass"
        assert edit_event.audit_metadata["source"] == "campaign_systems_shared_entry_editor"
        shared_events = AuthStore().list_recent_audit_events(
            event_type="campaign_systems_shared_entry_updated",
            campaign_slug="linden-pass",
        )
        assert any(event.metadata.get("entry_key") == entry_key for event in shared_events)
        matching_shared_event = next(
            event for event in shared_events if event.metadata.get("entry_key") == entry_key
        )
        assert matching_shared_event.actor_user_id == users["admin"]["id"]
        assert matching_shared_event.metadata["edited_fields"] == expected_edited_fields
        assert matching_shared_event.metadata["original_source_identity"] == edit_event.original_source_identity

    override_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/overrides",
        data={
            "return_to": "dm-content-systems",
            "entry_key": entry_key,
            "visibility_override": "dm",
            "is_enabled_override": "disabled",
        },
        follow_redirects=False,
    )

    assert override_response.status_code == 302
    assert "/campaigns/linden-pass/dm-content/systems" in override_response.headers["Location"]
    assert "#systems-entry-overrides" in override_response.headers["Location"]

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        entry = store.get_entry(service.get_campaign_library_slug("linden-pass"), entry_key)
        assert entry is not None
        assert entry.title == "Shared Spark Edited"
        assert entry.rendered_html == "<p>Edited shared library body.</p>"
        override = store.get_campaign_entry_override("linden-pass", entry_key)
        assert override is not None
        assert override.visibility_override == "dm"
        assert override.is_enabled_override is False


def test_shared_core_systems_edit_warns_for_app_modeled_entries(app, client, sign_in, users):
    source_id = f"WARN-{uuid4().hex[:8].upper()}"
    source_key = source_id.lower()
    spell_slug = f"modeled-spark-{uuid4().hex[:8]}"
    book_slug = f"quiet-lore-{uuid4().hex[:8]}"
    spell_entry_key = f"dnd-5e|spell|{source_key}|{spell_slug}"
    book_entry_key = f"dnd-5e|book|{source_key}|{book_slug}"

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        store.upsert_source(
            library_slug,
            source_id,
            title="Warning Test Source",
            license_class="open_license",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug=library_slug,
            source_id=source_id,
            is_enabled=True,
            default_visibility="players",
        )
        store.replace_entries_for_source(
            library_slug,
            source_id,
            entries=[
                {
                    "entry_key": spell_entry_key,
                    "entry_type": "spell",
                    "slug": spell_slug,
                    "title": "Modeled Spark",
                    "search_text": "modeled spark warning test source",
                    "player_safe_default": True,
                    "metadata": {"spell_support": {"mode": "known"}},
                    "body": {"imported": True},
                    "rendered_html": "<p>Original modeled spell body.</p>",
                },
                {
                    "entry_key": book_entry_key,
                    "entry_type": "book",
                    "slug": book_slug,
                    "title": "Quiet Lore",
                    "search_text": "quiet lore warning test source",
                    "player_safe_default": True,
                    "metadata": {},
                    "body": {"imported": True},
                    "rendered_html": "<p>Reference prose only.</p>",
                },
            ],
            entry_types=["spell", "book"],
        )

    sign_in(users["admin"]["email"], users["admin"]["password"])

    modeled_page = client.get(
        f"/campaigns/linden-pass/systems/control-panel/shared-entries/{spell_slug}/edit"
    )
    assert modeled_page.status_code == 200
    modeled_body = modeled_page.get_data(as_text=True)
    assert "Mechanics Impact Review" in modeled_body
    assert "Character tools" in modeled_body
    assert "spell_support" in modeled_body
    assert "does not start a character repair" in modeled_body
    assert 'name="shared_entry_mechanics_impact_acknowledged"' in modeled_body
    assert 'name="visibility_override"' not in modeled_body

    modeled_save_without_ack = client.post(
        f"/campaigns/linden-pass/systems/control-panel/shared-entries/{spell_slug}",
        data={
            "shared_entry_title": "Modeled Spark Revised",
            "shared_entry_source_page": "",
            "shared_entry_source_path": "",
            "shared_entry_search_text": "modeled spark revised warning test source",
            "shared_entry_player_safe_default": "1",
            "shared_entry_metadata_json": '{"spell_support": {"mode": "prepared"}}',
            "shared_entry_body_json": '{"imported": true}',
            "shared_entry_rendered_html": "<p>Modeled spell revised.</p>",
        },
        follow_redirects=False,
    )
    assert modeled_save_without_ack.status_code == 400
    modeled_save_without_ack_body = modeled_save_without_ack.get_data(as_text=True)
    assert "Review and acknowledge the mechanics impact warning" in modeled_save_without_ack_body

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        entry = store.get_entry(service.get_campaign_library_slug("linden-pass"), spell_entry_key)
        assert entry is not None
        assert entry.title == "Modeled Spark"
        assert entry.metadata == {"spell_support": {"mode": "known"}}
        assert store.get_campaign_entry_override("linden-pass", spell_entry_key) is None
        assert not store.list_shared_entry_edit_events(
            library_slug=service.get_campaign_library_slug("linden-pass"),
            entry_key=spell_entry_key,
            limit=5,
        )

    prose_page = client.get(
        f"/campaigns/linden-pass/systems/control-panel/shared-entries/{book_slug}/edit"
    )
    assert prose_page.status_code == 200
    prose_page_body = prose_page.get_data(as_text=True)
    assert "Mechanics Impact Review" not in prose_page_body
    assert 'name="shared_entry_mechanics_impact_acknowledged"' not in prose_page_body
    assert "character repair" not in prose_page_body
    assert "combat repair" not in prose_page_body
    assert "session repair" not in prose_page_body

    prose_save = client.post(
        f"/campaigns/linden-pass/systems/control-panel/shared-entries/{book_slug}",
        data={
            "shared_entry_title": "Quiet Lore Revised",
            "shared_entry_source_page": "",
            "shared_entry_source_path": "",
            "shared_entry_search_text": "quiet lore revised warning test source",
            "shared_entry_player_safe_default": "1",
            "shared_entry_metadata_json": "{}",
            "shared_entry_body_json": '{"imported": true}',
            "shared_entry_rendered_html": "<p>Reference prose revised.</p>",
        },
        follow_redirects=False,
    )
    assert prose_save.status_code == 302

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        entry = store.get_entry(service.get_campaign_library_slug("linden-pass"), book_entry_key)
        assert entry is not None
        assert entry.title == "Quiet Lore Revised"
        assert store.get_campaign_entry_override("linden-pass", book_entry_key) is None
        edit_events = store.list_shared_entry_edit_events(
            library_slug=service.get_campaign_library_slug("linden-pass"),
            entry_key=book_entry_key,
            limit=5,
        )
        assert len(edit_events) == 1
        assert edit_events[0].edited_fields == ["title", "search_text", "rendered_html"]

        campaign_events = AuthStore().list_recent_audit_events(
            campaign_slug="linden-pass",
            limit=20,
        )
        prose_event = next(
            event
            for event in campaign_events
            if event.event_type == "campaign_systems_shared_entry_updated"
            and event.metadata.get("entry_key") == book_entry_key
        )
        assert prose_event.metadata["source"] == "campaign_systems_shared_entry_editor"
        assert not [
            event
            for event in campaign_events
            if event.metadata.get("entry_key") == book_entry_key
            and (
                "repair" in event.event_type
                or event.event_type == "campaign_systems_entry_override_updated"
            )
        ]


def test_shared_core_systems_warning_inventory_covers_character_entry_types(app):
    cases = [
        ("background", "Background"),
        ("class", "Class"),
        ("classfeature", "Class Feature"),
        ("class_feature", "Class Feature"),
        ("feat", "Feat"),
        ("item", "Item"),
        ("optionalfeature", "Optional Feature"),
        ("race", "Race"),
        ("spell", "Spell"),
        ("subclass", "Subclass"),
        ("subclass-feature", "Subclass Feature"),
    ]

    with app.app_context():
        service = app.extensions["systems_service"]
        for entry_type, label in cases:
            warning = service.build_shared_core_entry_mechanics_impact_warning(
                build_warning_inventory_entry(entry_type=entry_type)
            )

            assert warning is not None
            assert "Character tools" in warning.surfaces
            assert any(
                signal.label == "Character-facing entry type" and label in signal.detail
                for signal in warning.signals
            )


def test_shared_core_systems_warning_inventory_covers_combat_session_entry_types(app):
    cases = [
        ("monster", "Monster"),
        ("condition", "Condition"),
        ("status", "Status"),
        ("action", "Action"),
    ]

    with app.app_context():
        service = app.extensions["systems_service"]
        for entry_type, label in cases:
            warning = service.build_shared_core_entry_mechanics_impact_warning(
                build_warning_inventory_entry(entry_type=entry_type)
            )

            assert warning is not None
            assert "Combat/session reference" in warning.surfaces
            assert any(
                signal.label == "Combat/session-facing entry type" and label in signal.detail
                for signal in warning.signals
            )
            assert any(signal.label == "Rendered tactical reference" for signal in warning.signals)


def test_shared_core_systems_warning_inventory_covers_character_metadata_hooks(app):
    metadata = {
        "character_option": {"kind": "feat"},
        "character-progression": [{"kind": "class"}],
        "spellSupport": [{"mode": "known"}],
        "nested": {
            "spell_manager": {"sources": []},
            "modeled-effects": [{"kind": "speed_bonus"}],
            "managed-resource": {"key": "ki"},
            "derivedStats": ["armor_class"],
        },
    }
    body = {
        "sections": [
            {
                "name": "Structured Body Hook",
                "derived-stat": {"field": "initiative"},
            }
        ]
    }

    with app.app_context():
        service = app.extensions["systems_service"]
        warning = service.build_shared_core_entry_mechanics_impact_warning(
            build_warning_inventory_entry(entry_type="book", metadata=metadata, body=body)
        )

    assert warning is not None
    assert "Character tools" in warning.surfaces
    structured_signal = next(
        signal for signal in warning.signals if signal.label == "Structured character mechanics"
    )
    assert "character_option" in structured_signal.detail
    assert "character-progression (character_progression)" in structured_signal.detail
    assert "spellSupport (spell_support)" in structured_signal.detail
    assert "nested.spell_manager" in structured_signal.detail
    assert "nested.modeled-effects (modeled_effects)" in structured_signal.detail
    assert "nested.managed-resource (managed_resource)" in structured_signal.detail
    assert "body keys sections[].derived-stat (derived_stat)" in structured_signal.detail


def test_shared_core_systems_warning_inventory_covers_combat_metadata_hooks(app):
    metadata = {
        "hp": {"average": 7},
        "speed": {"walk": 30},
        "initiativeBonus": 2,
        "nested": {
            "conditionImmune": ["frightened"],
        },
    }
    body = {
        "traits": [{"name": "Pack Tactics"}],
        "actions": [{"name": "Bite"}],
        "bonusAction": [{"name": "Skitter"}],
        "legendary": [{"name": "Tail Swipe"}],
    }

    with app.app_context():
        service = app.extensions["systems_service"]
        warning = service.build_shared_core_entry_mechanics_impact_warning(
            build_warning_inventory_entry(entry_type="book", metadata=metadata, body=body)
        )

    assert warning is not None
    assert "Combat seeding" in warning.surfaces
    structured_signal = next(signal for signal in warning.signals if signal.label == "Structured combat mechanics")
    assert "hp" in structured_signal.detail
    assert "speed" in structured_signal.detail
    assert "initiativeBonus (initiative_bonus)" in structured_signal.detail
    assert "nested.conditionImmune (condition_immune)" in structured_signal.detail
    assert "body keys traits" in structured_signal.detail
    assert "actions" in structured_signal.detail
    assert "bonusAction (bonus_action)" in structured_signal.detail


def test_shared_core_systems_edit_warns_for_normalized_rules_entries(
    app, client, sign_in, users
):
    rules_entry = next(
        entry
        for entry in build_dnd5e_rules_reference_entries()
        if entry["metadata"]["rule_key"] == "ability-scores-and-ability-modifiers"
    )

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        service.ensure_builtin_library_seeded(library_slug)
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug=library_slug,
            source_id=DND5E_RULES_REFERENCE_SOURCE_ID,
            is_enabled=True,
            default_visibility="players",
        )
        seeded_entry = store.get_entry(library_slug, rules_entry["entry_key"])
        assert seeded_entry is not None
        assert seeded_entry.metadata["source_provenance"]["kind"] == "normalized_reference"

    sign_in(users["admin"]["email"], users["admin"]["password"])

    response = client.get(
        f"/campaigns/linden-pass/systems/control-panel/shared-entries/{rules_entry['slug']}/edit"
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Mechanics Impact Review" in body
    assert "Rules references" in body
    assert "Rules reference identity and provenance" in body
    assert "the shared RULES source" in body
    assert "metadata keys formula" in body
    assert "source_provenance; body keys formula" in body
    assert "character-math reference pages" in body


def test_proprietary_source_cannot_be_made_public(client, sign_in, users, app):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    form_data = build_source_form(app)
    form_data["source_PHB_visibility"] = "public"

    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/sources",
        data=form_data,
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "cannot be made public" in response.get_data(as_text=True)


def test_player_cannot_open_dm_only_source_but_dm_can(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])
    blocked = client.get("/campaigns/linden-pass/systems/sources/DMG")
    assert blocked.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    allowed = client.get("/campaigns/linden-pass/systems/sources/DMG")
    assert allowed.status_code == 200
    assert "Dungeon Master&#39;s Guide (2014)" in allowed.get_data(as_text=True)


def test_dm_can_update_source_visibility_and_audit_event_is_written(client, sign_in, users, app):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    form_data = build_source_form(app)
    form_data["source_XGE_visibility"] = "dm"

    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/sources",
        data=form_data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Updated systems sources: XGE." in response.get_data(as_text=True)

    with app.app_context():
        service = app.extensions["systems_service"]
        state = service.get_campaign_source_state("linden-pass", "XGE")
        assert state is not None
        assert state.default_visibility == "dm"

        events = AuthStore().list_recent_audit_events(
            event_type="campaign_systems_source_updated",
            campaign_slug="linden-pass",
        )
        assert any(event.metadata.get("source_id") == "XGE" for event in events)


def test_builder_static_revision_tracks_entry_and_override_changes(app):
    source_id = f"TST-{uuid4().hex[:8].upper()}"
    entry_key = f"dnd-5e|class|{source_id.lower()}|cache-fighter"

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")

        store.upsert_source(
            library_slug,
            source_id,
            title="Builder Cache Test Source",
            license_class="custom_campaign",
        )
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug=library_slug,
            source_id=source_id,
            is_enabled=True,
            default_visibility="players",
        )

        initial_revision = service.get_builder_static_revision(
            "linden-pass",
            entry_types=("class",),
        )

        store.replace_entries_for_source(
            library_slug,
            source_id,
            entries=[
                {
                    "entry_key": entry_key,
                    "entry_type": "class",
                    "slug": "cache-fighter",
                    "title": "Cache Fighter",
                    "search_text": "cache fighter",
                    "player_safe_default": True,
                    "metadata": {"hit_die": {"faces": 10}},
                    "body": {},
                }
            ],
            entry_types=["class"],
        )
        entry_revision = service.get_builder_static_revision(
            "linden-pass",
            entry_types=("class",),
        )

        store.upsert_campaign_entry_override(
            "linden-pass",
            library_slug=library_slug,
            entry_key=entry_key,
            visibility_override=None,
            is_enabled_override=False,
        )
        override_revision = service.get_builder_static_revision(
            "linden-pass",
            entry_types=("class",),
        )

    assert entry_revision != initial_revision
    assert override_revision != entry_revision


def test_campaign_entry_enablement_uses_bulk_override_map(app, monkeypatch):
    source_id = f"TST-{uuid4().hex[:8].upper()}"
    enabled_key = f"dnd-5e|spell|{source_id.lower()}|bulk-enable-alpha"
    disabled_key = f"dnd-5e|spell|{source_id.lower()}|bulk-enable-beta"

    with app.test_request_context("/"):
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")

        store.upsert_source(
            library_slug,
            source_id,
            title="Bulk Enablement Test Source",
            license_class="custom_campaign",
        )
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug=library_slug,
            source_id=source_id,
            is_enabled=True,
            default_visibility="players",
        )
        store.replace_entries_for_source(
            library_slug,
            source_id,
            entries=[
                {
                    "entry_key": enabled_key,
                    "entry_type": "spell",
                    "slug": "bulk-enable-alpha",
                    "title": "Bulk Enablement Alpha",
                    "search_text": "bulk enablement alpha",
                    "player_safe_default": True,
                    "metadata": {},
                    "body": {},
                },
                {
                    "entry_key": disabled_key,
                    "entry_type": "spell",
                    "slug": "bulk-enable-beta",
                    "title": "Bulk Enablement Beta",
                    "search_text": "bulk enablement beta",
                    "player_safe_default": True,
                    "metadata": {},
                    "body": {},
                },
            ],
            entry_types=["spell"],
        )
        store.upsert_campaign_entry_override(
            "linden-pass",
            library_slug=library_slug,
            entry_key=disabled_key,
            visibility_override=None,
            is_enabled_override=False,
        )

        def fail_per_entry_override_lookup(*_args, **_kwargs):
            raise AssertionError("per-entry campaign override lookup should not run")

        monkeypatch.setattr(store, "get_campaign_entry_override", fail_per_entry_override_lookup)

        results = service.search_entries_for_campaign(
            "linden-pass",
            query="bulk enablement",
            entry_type="spell",
            limit=10,
        )

    assert [entry.title for entry in results] == ["Bulk Enablement Alpha"]


def test_campaign_entry_override_update_invalidates_request_enablement_cache(app):
    source_id = f"TST-{uuid4().hex[:8].upper()}"
    entry_key = f"dnd-5e|spell|{source_id.lower()}|cache-invalidated"

    with app.test_request_context("/"):
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")

        store.upsert_source(
            library_slug,
            source_id,
            title="Override Cache Invalidation Source",
            license_class="custom_campaign",
        )
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug=library_slug,
            source_id=source_id,
            is_enabled=True,
            default_visibility="players",
        )
        store.replace_entries_for_source(
            library_slug,
            source_id,
            entries=[
                {
                    "entry_key": entry_key,
                    "entry_type": "spell",
                    "slug": "cache-invalidated",
                    "title": "Cache Invalidated",
                    "search_text": "cache invalidated",
                    "player_safe_default": True,
                    "metadata": {},
                    "body": {},
                }
            ],
            entry_types=["spell"],
        )
        entry = store.get_entry(library_slug, entry_key)

        assert entry is not None
        assert service.is_entry_enabled_for_campaign("linden-pass", entry) is True

        service.update_campaign_entry_override(
            "linden-pass",
            entry_key=entry_key,
            visibility_override=None,
            is_enabled_override=False,
            actor_user_id=1,
            can_set_private=True,
        )

        assert service.is_entry_enabled_for_campaign("linden-pass", entry) is False


def test_class_progression_builds_reuse_classfeature_index(app, monkeypatch):
    source_id = f"TST-{uuid4().hex[:8].upper()}"
    alpha_class_key = f"dnd-5e|class|{source_id.lower()}|alpha-adept"
    beta_class_key = f"dnd-5e|class|{source_id.lower()}|beta-adept"
    alpha_feature_key = f"dnd-5e|classfeature|{source_id.lower()}|alpha-feature"
    beta_feature_key = f"dnd-5e|classfeature|{source_id.lower()}|beta-feature"

    with app.test_request_context("/"):
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")

        store.upsert_source(
            library_slug,
            source_id,
            title="Progression Index Test Source",
            license_class="custom_campaign",
        )
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug=library_slug,
            source_id=source_id,
            is_enabled=True,
            default_visibility="players",
        )
        store.replace_entries_for_source(
            library_slug,
            source_id,
            entries=[
                {
                    "entry_key": alpha_class_key,
                    "entry_type": "class",
                    "slug": "alpha-adept",
                    "title": "Alpha Adept",
                    "search_text": "alpha adept",
                    "player_safe_default": True,
                    "metadata": {"hit_die": {"faces": 8}},
                    "body": {
                        "feature_progression": [
                            {"name": "1st Level", "entries": ["Alpha Feature"]}
                        ]
                    },
                },
                {
                    "entry_key": beta_class_key,
                    "entry_type": "class",
                    "slug": "beta-adept",
                    "title": "Beta Adept",
                    "search_text": "beta adept",
                    "player_safe_default": True,
                    "metadata": {"hit_die": {"faces": 8}},
                    "body": {
                        "feature_progression": [
                            {"name": "1st Level", "entries": ["Beta Feature"]}
                        ]
                    },
                },
                {
                    "entry_key": alpha_feature_key,
                    "entry_type": "classfeature",
                    "slug": "alpha-feature",
                    "title": "Alpha Feature",
                    "search_text": "alpha feature",
                    "player_safe_default": True,
                    "metadata": {
                        "class_name": "Alpha Adept",
                        "class_source": source_id,
                        "level": 1,
                    },
                    "body": {},
                },
                {
                    "entry_key": beta_feature_key,
                    "entry_type": "classfeature",
                    "slug": "beta-feature",
                    "title": "Beta Feature",
                    "search_text": "beta feature",
                    "player_safe_default": True,
                    "metadata": {
                        "class_name": "Beta Adept",
                        "class_source": source_id,
                        "level": 1,
                    },
                    "body": {},
                },
            ],
            entry_types=["class", "classfeature"],
        )
        alpha_class = store.get_entry(library_slug, alpha_class_key)
        beta_class = store.get_entry(library_slug, beta_class_key)
        assert alpha_class is not None
        assert beta_class is not None

        original_list_enabled = service.list_enabled_entries_for_campaign
        classfeature_calls = 0

        def count_list_enabled_entries(campaign_slug: str, **kwargs):
            nonlocal classfeature_calls
            if kwargs.get("entry_type") == "classfeature":
                classfeature_calls += 1
            return original_list_enabled(campaign_slug, **kwargs)

        monkeypatch.setattr(service, "list_enabled_entries_for_campaign", count_list_enabled_entries)

        alpha_progression = service.build_class_feature_progression_for_class_entry(
            "linden-pass",
            alpha_class,
        )
        beta_progression = service.build_class_feature_progression_for_class_entry(
            "linden-pass",
            beta_class,
        )

    assert classfeature_calls == 1
    assert alpha_progression[0]["feature_rows"][0]["label"] == "Alpha Feature"
    assert beta_progression[0]["feature_rows"][0]["label"] == "Beta Feature"


def test_builtin_rules_source_is_seeded_and_browsable_without_import(client, sign_in, users, app):
    with app.app_context():
        service = app.extensions["systems_service"]
        state = service.get_campaign_source_state("linden-pass", "RULES")
        assert state is not None
        assert state.is_enabled is True
        entries = service.list_entries_for_campaign_source(
            "linden-pass",
            "RULES",
            entry_type="rule",
            limit=None,
        )
        titles = {entry.title for entry in entries}
        assert "Ability Scores and Ability Modifiers" in titles
        assert "Spell Attacks and Save DCs" in titles
        attunement_entry = next(
            entry for entry in entries if entry.title == "Equipped Items, Inventory, and Attunement"
        )
        assert attunement_entry.metadata["content_origin"] == "managed_seed_file"
        assert attunement_entry.metadata["content_migration_stage"] == "seed_file_to_sqlite"
        assert attunement_entry.metadata["content_source_path"] == "player_wiki/data/dnd5e_rules_reference.json"
        assert attunement_entry.metadata["seed_version"] == DND5E_RULES_REFERENCE_VERSION
        assert attunement_entry.source_path.endswith(
            f"player_wiki/data/dnd5e_rules_reference.json#{DND5E_RULES_REFERENCE_VERSION}"
        )

    sign_in(users["party"]["email"], users["party"]["password"])

    source_response = client.get("/campaigns/linden-pass/systems/sources/RULES")
    category_response = client.get("/campaigns/linden-pass/systems/sources/RULES/types/rule")
    search_response = client.get("/campaigns/linden-pass/systems/search?q=attunement")
    detail_response = client.get(f"/campaigns/linden-pass/systems/entries/{attunement_entry.slug}")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Character Rules Reference" in source_body
    assert "Browse This Source" in source_body
    assert "Rules" in source_body
    assert "Searches only this source&#39;s rules entries using curated metadata" in source_body

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Ability Scores and Ability Modifiers" in category_body
    assert "Armor Class" in category_body
    assert "Equipped Items, Inventory, and Attunement" in category_body

    assert search_response.status_code == 200
    search_body = search_response.get_data(as_text=True)
    assert "Equipped Items, Inventory, and Attunement" in search_body
    assert "RULES | Rules" in search_body

    assert detail_response.status_code == 200
    detail_body = detail_response.get_data(as_text=True)
    assert "attunement is a separate state with a normal limit of 3 items" in detail_body
    assert "Inventory Versus Equipment" in detail_body


def test_related_rules_sidebar_respects_rules_source_visibility(client, sign_in, users, app, tmp_path):
    data_root = build_test_data_root(tmp_path / "dnd5e-source")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["item"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="RULES",
            is_enabled=True,
            default_visibility="dm",
        )
        longsword_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="item", limit=20)
            if entry.title == "Longsword"
        )

    sign_in(users["party"]["email"], users["party"]["password"])
    player_response = client.get(f"/campaigns/linden-pass/systems/entries/{longsword_entry.slug}")

    assert player_response.status_code == 200
    player_body = player_response.get_data(as_text=True)
    assert "Related Rules References" not in player_body
    assert "Attack Rolls and Attack Bonus" not in player_body

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    dm_response = client.get(f"/campaigns/linden-pass/systems/entries/{longsword_entry.slug}")

    assert dm_response.status_code == 200
    dm_body = dm_response.get_data(as_text=True)
    assert "Related Rules References" in dm_body
    assert "Attack Rolls and Attack Bonus" in dm_body


def test_phb_book_section_rule_links_respect_rules_source_visibility(client, sign_in, users, app, tmp_path):
    data_root = build_phb_book_data_root(tmp_path / "dnd5e-source-book-visibility")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("PHB", entry_types=["book"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="RULES",
            is_enabled=True,
            default_visibility="dm",
        )
        using_ability_scores_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "PHB", entry_type="book", limit=20)
            if entry.title == "Using Ability Scores"
        )

    sign_in(users["party"]["email"], users["party"]["password"])
    player_response = client.get(f"/campaigns/linden-pass/systems/entries/{using_ability_scores_entry.slug}")

    assert player_response.status_code == 200
    player_body = player_response.get_data(as_text=True)
    assert "Rules:" not in player_body
    assert "Passive Checks" in player_body

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    dm_response = client.get(f"/campaigns/linden-pass/systems/entries/{using_ability_scores_entry.slug}")

    assert dm_response.status_code == 200
    dm_body = dm_response.get_data(as_text=True)
    assert "Rules:" in dm_body
    assert '<a href="/campaigns/linden-pass/systems/entries/rules-rule-passive-checks">' in dm_body


def test_dmg_book_entries_stay_dm_only(client, sign_in, users, app, tmp_path):
    data_root = build_dmg_book_data_root(tmp_path / "dnd5e-source-dmg-book-visibility")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("DMG", entry_types=["book"])

        store = app.extensions["systems_store"]
        multiverse_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "DMG", entry_type="book", limit=20)
            if entry.title == "Creating a Multiverse"
        )

    sign_in(users["party"]["email"], users["party"]["password"])
    player_response = client.get(f"/campaigns/linden-pass/systems/entries/{multiverse_entry.slug}")
    assert player_response.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    dm_response = client.get(f"/campaigns/linden-pass/systems/entries/{multiverse_entry.slug}")

    assert dm_response.status_code == 200
    dm_body = dm_response.get_data(as_text=True)
    assert "Creating a Multiverse" in dm_body
    assert "Chapter 2" in dm_body


def test_mm_book_entries_stay_dm_only(client, sign_in, users, app, tmp_path):
    data_root = build_mm_book_data_root(tmp_path / "dnd5e-source-mm-book-visibility")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("MM", entry_types=["book"])

        store = app.extensions["systems_store"]
        book_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "MM", entry_type="book", limit=20)
        }

    sign_in(users["party"]["email"], users["party"]["password"])
    for title in (
        "Statistics",
        "Legendary Creatures",
        "Shadow Dragon Template",
        "Half-Dragon Template",
        "Spore Servant Template",
        "Customizing NPCs",
    ):
        player_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries[title].slug}")
        assert player_response.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    for title in (
        "Statistics",
        "Legendary Creatures",
        "Shadow Dragon Template",
        "Half-Dragon Template",
        "Spore Servant Template",
        "Customizing NPCs",
    ):
        dm_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries[title].slug}")
        assert dm_response.status_code == 200
        dm_body = dm_response.get_data(as_text=True)
        assert title in dm_body
        if title == "Customizing NPCs":
            assert "Appendix B" in dm_body
            assert "Appendix B: Nonplayer Characters" in dm_body
        else:
            assert "Introduction" in dm_body


def test_vgm_character_race_book_entries_stay_dm_only(client, sign_in, users, app, tmp_path):
    data_root = build_vgm_book_data_root(tmp_path / "dnd5e-source-vgm-book-policy")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("VGM", entry_types=["book"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="VGM",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "VGM", entry_type="book", limit=20)
        }

    sign_in(users["party"]["email"], users["party"]["password"])
    for title in (
        "Aasimar",
        "Firbolg",
        "Goliath",
        "Kenku",
        "Lizardfolk",
        "Tabaxi",
        "Triton",
        "Monstrous Adventurers",
        "Height and Weight",
    ):
        player_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries[title].slug}")
        assert player_response.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    for title in (
        "Aasimar",
        "Firbolg",
        "Goliath",
        "Kenku",
        "Lizardfolk",
        "Tabaxi",
        "Triton",
        "Monstrous Adventurers",
        "Height and Weight",
    ):
        dm_response = client.get(f"/campaigns/linden-pass/systems/entries/{book_entries[title].slug}")
        assert dm_response.status_code == 200
        dm_body = dm_response.get_data(as_text=True)
        assert title in dm_body
        assert "Character Races" in dm_body


def test_vgm_book_entries_stay_hidden_when_source_visibility_is_lowered_for_other_vgm_content(
    client, sign_in, users, app, tmp_path
):
    data_root = build_vgm_book_data_root(tmp_path / "dnd5e-source-vgm-book-policy-lowered")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("VGM", entry_types=["book", "race"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="VGM",
            is_enabled=True,
            default_visibility="players",
        )
        monstrous_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "VGM", entry_type="book", limit=20)
            if entry.title == "Monstrous Adventurers"
        )
        bugbear_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "VGM", entry_type="race", limit=20)
            if entry.title == "Bugbear"
        )

    sign_in(users["party"]["email"], users["party"]["password"])

    source_response = client.get("/campaigns/linden-pass/systems/sources/VGM")
    book_category_response = client.get("/campaigns/linden-pass/systems/sources/VGM/types/book")
    player_book_response = client.get(f"/campaigns/linden-pass/systems/entries/{monstrous_entry.slug}")
    player_race_response = client.get(f"/campaigns/linden-pass/systems/entries/{bugbear_entry.slug}")
    search_response = client.get("/campaigns/linden-pass/systems?q=monstrous")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" not in source_body
    assert "Monstrous Adventurers" not in source_body
    assert "Races" in source_body
    assert "default to DM visibility" in source_body

    assert book_category_response.status_code == 404
    assert player_book_response.status_code == 404

    assert player_race_response.status_code == 200
    assert "Bugbear" in player_race_response.get_data(as_text=True)

    assert search_response.status_code == 200
    assert "Monstrous Adventurers" not in search_response.get_data(as_text=True)

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_source_response = client.get("/campaigns/linden-pass/systems/sources/VGM")
    dm_book_category_response = client.get("/campaigns/linden-pass/systems/sources/VGM/types/book")
    dm_book_response = client.get(f"/campaigns/linden-pass/systems/entries/{monstrous_entry.slug}")

    assert dm_source_response.status_code == 200
    dm_source_body = dm_source_response.get_data(as_text=True)
    assert "Book Chapters" in dm_source_body
    assert "Monstrous Adventurers" in dm_source_body
    assert "default to DM visibility" in dm_source_body

    assert dm_book_category_response.status_code == 200
    assert "Monstrous Adventurers" in dm_book_category_response.get_data(as_text=True)

    assert dm_book_response.status_code == 200
    assert "Policy default visibility: DM" in dm_book_response.get_data(as_text=True)


def test_dmg_book_entries_stay_hidden_when_source_visibility_is_lowered_for_other_dmg_content(
    client, sign_in, users, app, tmp_path
):
    data_root = build_dmg_book_data_root(tmp_path / "dnd5e-source-dmg-book-policy")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("DMG", entry_types=["book", "item"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="DMG",
            is_enabled=True,
            default_visibility="players",
        )
        multiverse_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "DMG", entry_type="book", limit=20)
            if entry.title == "Creating a Multiverse"
        )
        potion_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "DMG", entry_type="item", limit=20)
            if entry.title == "Potion of Healing"
        )

    sign_in(users["party"]["email"], users["party"]["password"])

    source_response = client.get("/campaigns/linden-pass/systems/sources/DMG")
    book_category_response = client.get("/campaigns/linden-pass/systems/sources/DMG/types/book")
    player_book_response = client.get(f"/campaigns/linden-pass/systems/entries/{multiverse_entry.slug}")
    player_item_response = client.get(f"/campaigns/linden-pass/systems/entries/{potion_entry.slug}")
    search_response = client.get("/campaigns/linden-pass/systems?q=multiverse")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" not in source_body
    assert "Creating a Multiverse" not in source_body
    assert "Items" in source_body
    assert "default to DM visibility" in source_body

    assert book_category_response.status_code == 404
    assert player_book_response.status_code == 404

    assert player_item_response.status_code == 200
    assert "Potion of Healing" in player_item_response.get_data(as_text=True)

    assert search_response.status_code == 200
    assert "Creating a Multiverse" not in search_response.get_data(as_text=True)

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_source_response = client.get("/campaigns/linden-pass/systems/sources/DMG")
    dm_book_category_response = client.get("/campaigns/linden-pass/systems/sources/DMG/types/book")
    dm_book_response = client.get(f"/campaigns/linden-pass/systems/entries/{multiverse_entry.slug}")

    assert dm_source_response.status_code == 200
    dm_source_body = dm_source_response.get_data(as_text=True)
    assert "Book Chapters" in dm_source_body
    assert "Creating a Multiverse" in dm_source_body

    assert dm_book_category_response.status_code == 200
    assert "Creating a Multiverse" in dm_book_category_response.get_data(as_text=True)

    assert dm_book_response.status_code == 200
    assert "Policy default visibility: DM" in dm_book_response.get_data(as_text=True)


def test_mtf_book_entries_stay_hidden_when_source_visibility_is_lowered_for_other_mtf_content(
    client, sign_in, users, app, tmp_path
):
    data_root = build_mtf_book_data_root(tmp_path / "dnd5e-source-mtf-book-policy")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("MTF", entry_types=["book", "race"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="MTF",
            is_enabled=True,
            default_visibility="players",
        )
        book_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "MTF", entry_type="book", limit=20)
        }
        tiefling_wrapper_entry = book_entries["Tiefling Subraces"]
        demonic_boons_entry = book_entries["Demonic Boons"]
        elf_wrapper_entry = book_entries["Elf Subraces"]
        duergar_wrapper_entry = book_entries["Duergar Characters"]
        gith_wrapper_entry = book_entries["Gith Characters"]
        deep_gnome_wrapper_entry = book_entries["Deep Gnome Characters"]
        asmodeus_tiefling_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "MTF", entry_type="race", limit=20)
            if entry.title == "Asmodeus Tiefling"
        )
        sea_elf_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "MTF", entry_type="race", limit=20)
            if entry.title == "Sea Elf"
        )
        duergar_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "MTF", entry_type="race", limit=20)
            if entry.title == "Duergar"
        )
        githyanki_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "MTF", entry_type="race", limit=20)
            if entry.title == "Githyanki"
        )
        deep_gnome_entry = next(
            entry
            for entry in store.list_entries_for_source("DND-5E", "MTF", entry_type="race", limit=20)
            if entry.title == "Deep Gnome"
        )

    sign_in(users["party"]["email"], users["party"]["password"])

    source_response = client.get("/campaigns/linden-pass/systems/sources/MTF")
    book_category_response = client.get("/campaigns/linden-pass/systems/sources/MTF/types/book")
    player_tiefling_book_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{tiefling_wrapper_entry.slug}"
    )
    player_demonic_boons_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{demonic_boons_entry.slug}"
    )
    player_elf_book_response = client.get(f"/campaigns/linden-pass/systems/entries/{elf_wrapper_entry.slug}")
    player_duergar_book_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{duergar_wrapper_entry.slug}"
    )
    player_gith_book_response = client.get(f"/campaigns/linden-pass/systems/entries/{gith_wrapper_entry.slug}")
    player_deep_gnome_book_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{deep_gnome_wrapper_entry.slug}"
    )
    player_tiefling_race_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{asmodeus_tiefling_entry.slug}"
    )
    player_elf_race_response = client.get(f"/campaigns/linden-pass/systems/entries/{sea_elf_entry.slug}")
    player_duergar_race_response = client.get(f"/campaigns/linden-pass/systems/entries/{duergar_entry.slug}")
    player_githyanki_race_response = client.get(f"/campaigns/linden-pass/systems/entries/{githyanki_entry.slug}")
    player_deep_gnome_race_response = client.get(f"/campaigns/linden-pass/systems/entries/{deep_gnome_entry.slug}")
    search_response = client.get("/campaigns/linden-pass/systems?q=subraces")
    demonic_boons_search_response = client.get("/campaigns/linden-pass/systems?q=demonic+boons")
    duergar_search_response = client.get("/campaigns/linden-pass/systems?q=duergar+characters")
    gith_search_response = client.get("/campaigns/linden-pass/systems?q=gith+characters")
    deep_gnome_search_response = client.get("/campaigns/linden-pass/systems?q=deep+gnome+characters")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Book Chapters" not in source_body
    assert "Tiefling Subraces" not in source_body
    assert "Demonic Boons" not in source_body
    assert "Elf Subraces" not in source_body
    assert "Duergar Characters" not in source_body
    assert "Gith Characters" not in source_body
    assert "Deep Gnome Characters" not in source_body
    assert "Races" in source_body
    assert "default to DM visibility" in source_body

    assert book_category_response.status_code == 404
    assert player_tiefling_book_response.status_code == 404
    assert player_demonic_boons_response.status_code == 404
    assert player_elf_book_response.status_code == 404
    assert player_duergar_book_response.status_code == 404
    assert player_gith_book_response.status_code == 404
    assert player_deep_gnome_book_response.status_code == 404

    assert player_tiefling_race_response.status_code == 200
    assert "Asmodeus Tiefling" in player_tiefling_race_response.get_data(as_text=True)
    assert player_elf_race_response.status_code == 200
    assert "Sea Elf" in player_elf_race_response.get_data(as_text=True)
    assert player_duergar_race_response.status_code == 200
    assert "Duergar" in player_duergar_race_response.get_data(as_text=True)
    assert player_githyanki_race_response.status_code == 200
    assert "Githyanki" in player_githyanki_race_response.get_data(as_text=True)
    assert player_deep_gnome_race_response.status_code == 200
    assert "Deep Gnome" in player_deep_gnome_race_response.get_data(as_text=True)

    assert search_response.status_code == 200
    search_body = search_response.get_data(as_text=True)
    assert "Tiefling Subraces" not in search_body
    assert "Elf Subraces" not in search_body
    assert demonic_boons_search_response.status_code == 200
    assert "Demonic Boons" not in demonic_boons_search_response.get_data(as_text=True)
    assert duergar_search_response.status_code == 200
    assert "Duergar Characters" not in duergar_search_response.get_data(as_text=True)
    assert gith_search_response.status_code == 200
    assert "Gith Characters" not in gith_search_response.get_data(as_text=True)
    assert deep_gnome_search_response.status_code == 200
    assert "Deep Gnome Characters" not in deep_gnome_search_response.get_data(as_text=True)

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_source_response = client.get("/campaigns/linden-pass/systems/sources/MTF")
    dm_book_category_response = client.get("/campaigns/linden-pass/systems/sources/MTF/types/book")
    dm_tiefling_book_response = client.get(f"/campaigns/linden-pass/systems/entries/{tiefling_wrapper_entry.slug}")
    dm_demonic_boons_response = client.get(f"/campaigns/linden-pass/systems/entries/{demonic_boons_entry.slug}")
    dm_elf_book_response = client.get(f"/campaigns/linden-pass/systems/entries/{elf_wrapper_entry.slug}")
    dm_duergar_book_response = client.get(f"/campaigns/linden-pass/systems/entries/{duergar_wrapper_entry.slug}")
    dm_gith_book_response = client.get(f"/campaigns/linden-pass/systems/entries/{gith_wrapper_entry.slug}")
    dm_deep_gnome_book_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{deep_gnome_wrapper_entry.slug}"
    )
    dm_demonic_boons_search_response = client.get("/campaigns/linden-pass/systems?q=demonic+boons")
    dm_duergar_search_response = client.get("/campaigns/linden-pass/systems?q=duergar+characters")
    dm_gith_search_response = client.get("/campaigns/linden-pass/systems?q=gith+characters")
    dm_deep_gnome_search_response = client.get("/campaigns/linden-pass/systems?q=deep+gnome+characters")

    assert dm_source_response.status_code == 200
    dm_source_body = dm_source_response.get_data(as_text=True)
    assert "Book Chapters" in dm_source_body
    assert "Tiefling Subraces" in dm_source_body
    assert "Demonic Boons" in dm_source_body
    assert "Elf Subraces" in dm_source_body
    assert "Duergar Characters" in dm_source_body
    assert "Gith Characters" in dm_source_body
    assert "Deep Gnome Characters" in dm_source_body
    assert dm_source_body.index("Tiefling Subraces") < dm_source_body.index("Demonic Boons")
    assert dm_source_body.index("Demonic Boons") < dm_source_body.index("Elf Subraces")
    assert dm_source_body.index("Elf Subraces") < dm_source_body.index("Duergar Characters")
    assert dm_source_body.index("Duergar Characters") < dm_source_body.index("Gith Characters")
    assert dm_source_body.index("Gith Characters") < dm_source_body.index("Deep Gnome Characters")
    assert "default to DM visibility" in dm_source_body

    assert dm_book_category_response.status_code == 200
    dm_book_category_body = dm_book_category_response.get_data(as_text=True)
    assert "Tiefling Subraces" in dm_book_category_body
    assert "Demonic Boons" in dm_book_category_body
    assert "Elf Subraces" in dm_book_category_body
    assert "Duergar Characters" in dm_book_category_body
    assert "Gith Characters" in dm_book_category_body
    assert "Deep Gnome Characters" in dm_book_category_body
    assert dm_book_category_body.index("Tiefling Subraces") < dm_book_category_body.index("Demonic Boons")
    assert dm_book_category_body.index("Demonic Boons") < dm_book_category_body.index("Elf Subraces")
    assert dm_book_category_body.index("Elf Subraces") < dm_book_category_body.index("Duergar Characters")
    assert dm_book_category_body.index("Duergar Characters") < dm_book_category_body.index("Gith Characters")
    assert dm_book_category_body.index("Gith Characters") < dm_book_category_body.index("Deep Gnome Characters")

    assert dm_tiefling_book_response.status_code == 200
    assert "Policy default visibility: DM" in dm_tiefling_book_response.get_data(as_text=True)
    assert dm_demonic_boons_response.status_code == 200
    assert "Policy default visibility: DM" in dm_demonic_boons_response.get_data(as_text=True)
    assert dm_elf_book_response.status_code == 200
    assert "Policy default visibility: DM" in dm_elf_book_response.get_data(as_text=True)
    assert dm_duergar_book_response.status_code == 200
    assert "Policy default visibility: DM" in dm_duergar_book_response.get_data(as_text=True)
    assert dm_gith_book_response.status_code == 200
    assert "Policy default visibility: DM" in dm_gith_book_response.get_data(as_text=True)
    assert dm_deep_gnome_book_response.status_code == 200
    assert "Policy default visibility: DM" in dm_deep_gnome_book_response.get_data(as_text=True)
    assert dm_demonic_boons_search_response.status_code == 200
    assert "Demonic Boons" in dm_demonic_boons_search_response.get_data(as_text=True)
    assert dm_duergar_search_response.status_code == 200
    assert "Duergar Characters" in dm_duergar_search_response.get_data(as_text=True)
    assert dm_gith_search_response.status_code == 200
    assert "Gith Characters" in dm_gith_search_response.get_data(as_text=True)
    assert dm_deep_gnome_search_response.status_code == 200
    assert "Deep Gnome Characters" in dm_deep_gnome_search_response.get_data(as_text=True)


def test_egw_book_entries_follow_source_visibility(client, sign_in, users, app):
    data_root = build_egw_dunamis_book_data_root(
        build_repo_local_test_root("dnd5e-source-egw-book-entries-policy")
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("EGW", entry_types=["book"])

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="EGW",
            is_enabled=True,
            default_visibility="dm",
        )
        book_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "EGW", entry_type="book", limit=20)
        }

    sign_in(users["party"]["email"], users["party"]["password"])
    player_source_response = client.get("/campaigns/linden-pass/systems/sources/EGW")
    player_category_response = client.get("/campaigns/linden-pass/systems/sources/EGW/types/book")
    player_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Dunamis and Dunamancy'].slug}"
    )

    assert player_source_response.status_code == 404
    assert player_category_response.status_code == 404
    assert player_entry_response.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_source_response = client.get("/campaigns/linden-pass/systems/sources/EGW")
    dm_category_response = client.get("/campaigns/linden-pass/systems/sources/EGW/types/book")
    dm_entry_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Dunamis and Dunamancy'].slug}"
    )

    assert dm_source_response.status_code == 200
    dm_source_body = dm_source_response.get_data(as_text=True)
    assert "Book Chapters" in dm_source_body
    assert "Dunamis and Dunamancy" in dm_source_body

    assert dm_category_response.status_code == 200
    dm_category_body = dm_category_response.get_data(as_text=True)
    assert "Dunamis and Dunamancy" in dm_category_body
    assert "Heroic Chronicle" in dm_category_body

    assert dm_entry_response.status_code == 200
    dm_entry_body = dm_entry_response.get_data(as_text=True)
    assert "Chapter 4" in dm_entry_body
    assert "Character Options" in dm_entry_body
    assert "Beyond the Kryn Dynasty" in dm_entry_body


def test_egw_source_chapter_context_respects_wrapper_entry_visibility(
    client, sign_in, users, app
):
    data_root = build_egw_character_option_wrapper_data_root(
        build_repo_local_test_root("dnd5e-source-egw-wrapper-visibility")
    )

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source(
            "EGW",
            entry_types=["background", "book", "race", "spell", "subclass", "subclassfeature"],
        )

        store = app.extensions["systems_store"]
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug="DND-5E",
            source_id="EGW",
            is_enabled=True,
            default_visibility="players",
        )
        book_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "EGW", entry_type="book", limit=None)
        }
        spell_entries = {
            entry.title: entry
            for entry in store.list_entries_for_source("DND-5E", "EGW", entry_type="spell", limit=None)
        }
        for wrapper_title in ("Dunamancy Spells", "Spell Descriptions"):
            store.upsert_campaign_entry_override(
                "linden-pass",
                library_slug="DND-5E",
                entry_key=book_entries[wrapper_title].entry_key,
                visibility_override="dm",
                is_enabled_override=None,
            )

    sign_in(users["party"]["email"], users["party"]["password"])

    player_source_response = client.get("/campaigns/linden-pass/systems/sources/EGW")
    player_category_response = client.get("/campaigns/linden-pass/systems/sources/EGW/types/book")
    player_hidden_wrapper_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Dunamancy Spells'].slug}"
    )
    player_spell_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{spell_entries['Dark Star'].slug}"
    )

    assert player_source_response.status_code == 200
    player_source_body = player_source_response.get_data(as_text=True)
    assert "Book Chapters" in player_source_body
    assert "Heroic Chronicle" in player_source_body
    assert "Dunamancy Spells" not in player_source_body
    assert "Spell Descriptions" not in player_source_body

    assert player_category_response.status_code == 200
    player_category_body = player_category_response.get_data(as_text=True)
    assert "Heroic Chronicle" in player_category_body
    assert "Dunamancy Spells" not in player_category_body
    assert "Spell Descriptions" not in player_category_body

    assert player_hidden_wrapper_response.status_code == 404

    assert player_spell_response.status_code == 200
    player_spell_body = player_spell_response.get_data(as_text=True)
    assert "Dark Star" in player_spell_body
    assert "Source Chapter Context" not in player_spell_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{book_entries["Dunamancy Spells"].slug}"'
        not in player_spell_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{book_entries["Spell Descriptions"].slug}"'
        not in player_spell_body
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_source_response = client.get("/campaigns/linden-pass/systems/sources/EGW")
    dm_category_response = client.get("/campaigns/linden-pass/systems/sources/EGW/types/book")
    dm_hidden_wrapper_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{book_entries['Dunamancy Spells'].slug}"
    )
    dm_spell_response = client.get(
        f"/campaigns/linden-pass/systems/entries/{spell_entries['Dark Star'].slug}"
    )

    assert dm_source_response.status_code == 200
    dm_source_body = dm_source_response.get_data(as_text=True)
    assert "Dunamancy Spells" in dm_source_body
    assert "Spell Descriptions" in dm_source_body

    assert dm_category_response.status_code == 200
    dm_category_body = dm_category_response.get_data(as_text=True)
    assert "Dunamancy Spells" in dm_category_body
    assert "Spell Descriptions" in dm_category_body

    assert dm_hidden_wrapper_response.status_code == 200
    assert "Dunamancy Spells" in dm_hidden_wrapper_response.get_data(as_text=True)

    assert dm_spell_response.status_code == 200
    dm_spell_body = dm_spell_response.get_data(as_text=True)
    assert "Source Chapter Context" in dm_spell_body
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{book_entries["Dunamancy Spells"].slug}"'
        in dm_spell_body
    )
    assert (
        f'href="/campaigns/linden-pass/systems/entries/{book_entries["Spell Descriptions"].slug}"'
        in dm_spell_body
    )


def test_dmg_rules_reference_search_stays_source_scoped(client, sign_in, users, app, tmp_path):
    data_root = build_dmg_book_data_root(tmp_path / "dnd5e-source-dmg-search-scope")

    with app.app_context():
        importer = Dnd5eSystemsImporter(
            store=app.extensions["systems_store"],
            systems_service=app.extensions["systems_service"],
            data_root=data_root,
        )
        importer.import_source("DMG", entry_types=["book"])

    sign_in(users["dm"]["email"], users["dm"]["password"])

    landing_response = client.get("/campaigns/linden-pass/systems?reference_q=planar+travel")
    source_response = client.get("/campaigns/linden-pass/systems/sources/DMG?reference_q=planar+travel")

    assert landing_response.status_code == 200
    landing_body = landing_response.get_data(as_text=True)
    assert "No rules references matched that metadata search yet." in landing_body
    assert "Creating a Multiverse" not in landing_body
    assert "DM-heavy source-backed references stay on their own source pages" in landing_body
    assert 'href="/campaigns/linden-pass/systems/sources/DMG"' in landing_body

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Creating a Multiverse" in source_body
    assert "DM-heavy source keeps chapter browse and rules-reference metadata search on this source page" in source_body


def test_builtin_rules_source_reseeds_stale_rows_from_managed_payload(app):
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        service.ensure_builtin_library_seeded("DND-5E")

        stale_entries = build_dnd5e_rules_reference_entries()
        for entry in stale_entries:
            entry["source_path"] = "builtin:dnd5e-rules:legacy"
            entry["metadata"] = {
                **entry["metadata"],
                "seed_version": "2026-04-01.0",
                "content_origin": "code_seed",
                "content_source_path": "player_wiki/dnd5e_rules_reference.py",
                "content_migration_stage": "python_literal_seed",
            }

        store.replace_entries_for_source("DND-5E", "RULES", entries=stale_entries)

        refreshed_state = service.get_campaign_source_state("linden-pass", "RULES")
        assert refreshed_state is not None

        refreshed_entry = store.get_entry(
            "DND-5E",
            "rules-rule-character-math-overview",
        )
        assert refreshed_entry is not None
        assert refreshed_entry.metadata["seed_version"] == DND5E_RULES_REFERENCE_VERSION
        assert refreshed_entry.metadata["content_origin"] == "managed_seed_file"
        assert refreshed_entry.metadata["content_migration_stage"] == "seed_file_to_sqlite"
        assert refreshed_entry.metadata["content_source_path"] == "player_wiki/data/dnd5e_rules_reference.json"
        assert refreshed_entry.source_path.endswith(
            f"player_wiki/data/dnd5e_rules_reference.json#{DND5E_RULES_REFERENCE_VERSION}"
        )
