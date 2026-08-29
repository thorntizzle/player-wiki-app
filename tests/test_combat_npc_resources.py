from __future__ import annotations

from types import SimpleNamespace

import pytest

from player_wiki.combat_npc_resources import (
    build_npc_resource_seeds_from_markdown,
    build_npc_resource_seeds_from_systems_entry,
)
from player_wiki.campaign_combat_service import (
    CampaignCombatValidationError,
    normalize_npc_resource_counter_seeds,
)


@pytest.mark.parametrize(
    ("suffix", "threshold", "reset_label"),
    (
        ("(Recharge 6)", 6, "Recharge 6"),
        ("(recharge 2-6)", 2, "Recharge 2–6"),
        ("(Recharge 3 – 6)", 3, "Recharge 3–6"),
        ("(Recharge 4—6)", 4, "Recharge 4–6"),
        ("(RECHARGE 5 - 6)", 5, "Recharge 5–6"),
    ),
)
def test_markdown_atx_heading_strict_recharge_suffix_seeds_one_use_counter(
    suffix, threshold, reset_label
):
    counters, notes = build_npc_resource_seeds_from_markdown(
        f"### Ember Breath {suffix}\n\nThe wyrm exhales fire.",
        source_label="DM Content",
    )

    assert notes == []
    assert len(counters) == 1
    counter = counters[0]
    assert (
        counter.resource_key,
        counter.label,
        counter.current_value,
        counter.max_value,
        counter.reset_kind,
        counter.recharge_threshold,
        counter.reset_label,
        counter.source_label,
    ) == (
        "ember-breath",
        "Ember Breath",
        1,
        1,
        "recharge_d6",
        threshold,
        reset_label,
        "DM Content",
    )


@pytest.mark.parametrize(
    "line",
    (
        "Ember Breath (Recharge 5-6)",
        "- Ember Breath (Recharge 5-6)",
        "### Ember Breath (Recharge 1-6)",
        "### Ember Breath (Recharge 7)",
        "### Ember Breath (Recharge 5)",
        "### Ember Breath (Recharge 6-6)",
        "### Ember Breath (Recharge 5-7)",
        "### Ember Breath (Recharge 5-6, bloodied)",
        "### Ember Breath (Recharge 5-6) after use",
        "### Ember Breath (Recharge 5+6)",
        "### Ember Breath ( Recharge 5-6)",
        "### Ember Breath (Recharge  5-6)",
        "### Ember Breath (Recharge 5-6 )",
    ),
)
def test_markdown_false_positive_recharge_forms_remain_notes(line):
    counters, notes = build_npc_resource_seeds_from_markdown(
        line,
        source_label="DM Content",
    )

    assert counters == []
    assert notes


@pytest.mark.parametrize(
    ("name", "threshold", "reset_label"),
    (
        ("Arcane Burst {@recharge}", 6, "Recharge 6"),
        ("Arcane Burst {@recharge 2}", 2, "Recharge 2–6"),
        ("Arcane Burst {@RECHARGE 5}", 5, "Recharge 5–6"),
        ("Arcane Burst (Recharge 4 - 6)", 4, "Recharge 4–6"),
    ),
)
def test_systems_typed_ability_names_support_literal_and_recharge_tag_forms(
    name, threshold, reset_label
):
    entry = SimpleNamespace(
        source_id="MM",
        body={"actions": [{"name": name, "entries": ["The adept attacks."]}]},
    )

    counters, notes = build_npc_resource_seeds_from_systems_entry(entry)

    assert notes == []
    assert len(counters) == 1
    assert counters[0].label == "Arcane Burst"
    assert counters[0].recharge_threshold == threshold
    assert counters[0].reset_label == reset_label


@pytest.mark.parametrize(
    "name",
    (
        "Arcane Burst {@recharge 1}",
        "Arcane Burst {@recharge 7}",
        "Arcane Burst {@recharge 5|MM}",
        "Arcane Burst {@recharge 5 extra}",
        "Arcane Burst {@recharge  5}",
        "Arcane Burst {@recharge 5} after use",
    ),
)
def test_systems_malformed_or_nonterminal_recharge_tags_remain_notes(name):
    entry = SimpleNamespace(
        source_id="MM",
        body={"actions": [{"name": name, "entries": []}]},
    )

    counters, notes = build_npc_resource_seeds_from_systems_entry(entry)

    assert counters == []
    assert notes


def test_systems_recharge_only_seeds_from_typed_ability_name_positions():
    entry = SimpleNamespace(
        source_id="MM",
        body={
            "name": "Monster Title {@recharge 5}",
            "entries": ["Arbitrary prose (Recharge 5-6)."],
            "actions": [
                {
                    "name": "Plain Strike",
                    "entries": ["Nested prose {@recharge 4}."],
                }
            ],
        },
    )

    counters, notes = build_npc_resource_seeds_from_systems_entry(entry)

    assert counters == []
    assert {note.label for note in notes} == {
        "Monster Title",
        "Arbitrary prose",
        "Nested prose",
    }


def test_exact_duplicate_recharge_rules_deduplicate():
    counters, notes = build_npc_resource_seeds_from_markdown(
        "### Ember Breath (Recharge 5-6)\n### Ember Breath (Recharge 5 – 6)",
        source_label="DM Content",
    )

    assert len(counters) == 1
    assert counters[0].recharge_threshold == 5
    assert notes == []


def test_conflicting_recharge_thresholds_produce_no_counter_and_preserve_rules_as_notes():
    counters, notes = build_npc_resource_seeds_from_markdown(
        "### Ember Breath (Recharge 5-6)\n### Ember Breath (Recharge 6)",
        source_label="DM Content",
    )

    assert counters == []
    assert {(note.label, note.note) for note in notes} == {
        ("Ember Breath", "Recharge 5-6"),
        ("Ember Breath", "Recharge 6"),
    }


def test_recharge_collision_with_daily_counter_keeps_daily_counter_and_recharge_note():
    counters, notes = build_npc_resource_seeds_from_markdown(
        "### Ember Breath (1/day)\n### Ember Breath (Recharge 5-6)",
        source_label="DM Content",
    )

    assert len(counters) == 1
    assert counters[0].resource_key == "ember-breath"
    assert counters[0].reset_kind == "daily"
    assert counters[0].recharge_threshold is None
    assert [(note.label, note.note) for note in notes] == [
        ("Ember Breath", "Recharge 5-6")
    ]


def test_counter_normalization_preserves_internal_recharge_metadata_and_canonical_label():
    normalized = normalize_npc_resource_counter_seeds(
        (
            SimpleNamespace(
                resource_key="ember-breath",
                label="Ember Breath",
                current_value=1,
                max_value=1,
                reset_label="caller label",
                source_label="Systems MM",
                reset_kind="recharge_d6",
                recharge_threshold="4",
            ),
        )
    )

    assert normalized[0].reset_kind == "recharge_d6"
    assert normalized[0].recharge_threshold == 4
    assert normalized[0].reset_label == "Recharge 4–6"


@pytest.mark.parametrize(
    "seed",
    (
        SimpleNamespace(
            resource_key="bad", label="Bad", current_value=1, max_value=1,
            reset_label="Bad", source_label="Test", reset_kind="other",
            recharge_threshold=None,
        ),
        SimpleNamespace(
            resource_key="bad", label="Bad", current_value=1, max_value=1,
            reset_label="Bad", source_label="Test", reset_kind="source",
            recharge_threshold=5,
        ),
        SimpleNamespace(
            resource_key="bad", label="Bad", current_value=2, max_value=2,
            reset_label="Bad", source_label="Test", reset_kind="recharge_d6",
            recharge_threshold=5,
        ),
    ),
)
def test_counter_normalization_rejects_invalid_reset_metadata(seed):
    with pytest.raises(CampaignCombatValidationError):
        normalize_npc_resource_counter_seeds((seed,))
