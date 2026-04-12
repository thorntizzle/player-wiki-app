from __future__ import annotations

from pathlib import Path
import re

import yaml

from player_wiki.character_importer import import_character
from player_wiki.config import Config


def test_native_character_edits_can_apply_and_remove_campaign_page_spell_grants(
    app, client, sign_in, users, get_character, set_campaign_visibility
):
    blessing_page_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "content"
        / "mechanics"
        / "blessing-of-the-tide.md"
    )
    blessing_page_path.write_text(
        """---
title: Blessing of the Tide
section: Mechanics
subsection: Blessings
published: true
summary: A tide-bound boon for trusted wardens.
character_option:
  name: Blessing of the Tide
  description_markdown: Call on the tide to steady your footing.
  activation_type: bonus_action
  grants:
    languages:
      - Primordial
    spells:
      - spell: Light
        mark: Granted
      - spell: Detect Magic
        always_prepared: true
        ritual: true
---
Wardens call on the tide when the harbor turns dangerous.
""",
        encoding="utf-8",
    )

    with app.app_context():
        systems_store = app.extensions["systems_store"]
        systems_store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        systems_store.upsert_source(
            "DND-5E",
            "PHB",
            title="Player's Handbook",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["spell"],
            entries=[
                {
                    "entry_key": "dnd-5e|spell|phb|light",
                    "entry_type": "spell",
                    "slug": "phb-spell-light",
                    "title": "Light",
                    "source_page": "255",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "light",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"casting_time": [{"number": 1, "unit": "action"}], "ritual": False},
                    "body": {},
                    "rendered_html": "<p>Light.</p>",
                },
                {
                    "entry_key": "dnd-5e|spell|phb|detect-magic",
                    "entry_type": "spell",
                    "slug": "phb-spell-detect-magic",
                    "title": "Detect Magic",
                    "source_page": "231",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "detect magic",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"casting_time": [{"number": 1, "unit": "action"}], "ritual": True},
                    "body": {},
                    "rendered_html": "<p>Detect Magic.</p>",
                },
            ],
        )

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "mechanics/blessing-of-the-tide",
            "custom_feature_activation_type_1": "bonus_action",
            "custom_feature_description_1": "",
        },
        follow_redirects=False,
    )

    assert add_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    custom_feature = next(
        feature
        for feature in record.definition.features
        if feature.get("category") == "custom_feature" and feature.get("page_ref") == "mechanics/blessing-of-the-tide"
    )
    assert custom_feature["name"] == "Blessing of the Tide"
    assert custom_feature["description_markdown"] == "Call on the tide to steady your footing."
    assert "Primordial" in record.definition.proficiencies["languages"]

    spells_by_name = {spell["name"]: spell for spell in record.definition.spellcasting["spells"]}
    assert spells_by_name["Light"]["mark"] == "Granted"
    assert spells_by_name["Light"]["systems_ref"]["slug"] == "phb-spell-light"
    assert spells_by_name["Detect Magic"]["is_always_prepared"] is True
    assert spells_by_name["Detect Magic"]["is_ritual"] is True
    assert spells_by_name["Detect Magic"]["systems_ref"]["slug"] == "phb-spell-detect-magic"

    remove_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_id_1": custom_feature["id"],
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "",
            "custom_feature_activation_type_1": "passive",
            "custom_feature_description_1": "",
        },
        follow_redirects=False,
    )

    assert remove_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    assert "Primordial" not in record.definition.proficiencies["languages"]
    assert all(
        feature.get("page_ref") != "mechanics/blessing-of-the-tide"
        for feature in record.definition.features
    )
    spells_by_name = {spell["name"]: spell for spell in record.definition.spellcasting["spells"]}
    assert "Light" not in spells_by_name
    assert "Detect Magic" not in spells_by_name


def test_native_character_edits_can_apply_and_remove_campaign_page_spell_support_replacements(
    app, client, sign_in, users, get_character, set_campaign_visibility
):
    training_page_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "content"
        / "mechanics"
        / "harbor-spell-drill.md"
    )
    training_page_path.write_text(
        """---
title: Harbor Spell Drill
section: Mechanics
subsection: Blessings
published: true
summary: A harbor rite that teaches a new cantrip and rewires an old one.
character_option:
  name: Harbor Spell Drill
  description_markdown: Harbor drillmasters teach you a practiced magical exchange.
  activation_type: special
  spell_support:
    - grants:
        _:
          - spell: Detect Magic
            always_prepared: true
            ritual: true
      choices:
        _:
          - category: granted
            options:
              - Light
              - Mage Hand
            count: 1
            label_prefix: Drill Cantrip
            mark: Granted
      replacement:
        _:
          - kind: known
            from:
              options:
                - Message
            to:
              options:
                - Ray of Frost
                - Thaumaturgy
---
The drill is meant to replace a memorized shortcut with a more disciplined response.
""",
        encoding="utf-8",
    )

    with app.app_context():
        systems_store = app.extensions["systems_store"]
        systems_store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        systems_store.upsert_source(
            "DND-5E",
            "PHB",
            title="Player's Handbook",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["spell"],
            entries=[
                {
                    "entry_key": "dnd-5e|spell|phb|message",
                    "entry_type": "spell",
                    "slug": "phb-spell-message",
                    "title": "Message",
                    "source_page": "259",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "message",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
                    "body": {},
                    "rendered_html": "<p>Message.</p>",
                },
                {
                    "entry_key": "dnd-5e|spell|phb|detect-magic",
                    "entry_type": "spell",
                    "slug": "phb-spell-detect-magic",
                    "title": "Detect Magic",
                    "source_page": "231",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "detect magic",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "ritual": True},
                    "body": {},
                    "rendered_html": "<p>Detect Magic.</p>",
                },
                {
                    "entry_key": "dnd-5e|spell|phb|light",
                    "entry_type": "spell",
                    "slug": "phb-spell-light",
                    "title": "Light",
                    "source_page": "255",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "light",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
                    "body": {},
                    "rendered_html": "<p>Light.</p>",
                },
                {
                    "entry_key": "dnd-5e|spell|phb|mage-hand",
                    "entry_type": "spell",
                    "slug": "phb-spell-mage-hand",
                    "title": "Mage Hand",
                    "source_page": "256",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "mage hand",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
                    "body": {},
                    "rendered_html": "<p>Mage Hand.</p>",
                },
                {
                    "entry_key": "dnd-5e|spell|phb|ray-of-frost",
                    "entry_type": "spell",
                    "slug": "phb-spell-ray-of-frost",
                    "title": "Ray of Frost",
                    "source_page": "271",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "ray of frost",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
                    "body": {},
                    "rendered_html": "<p>Ray of Frost.</p>",
                },
                {
                    "entry_key": "dnd-5e|spell|phb|thaumaturgy",
                    "entry_type": "spell",
                    "slug": "phb-spell-thaumaturgy",
                    "title": "Thaumaturgy",
                    "source_page": "282",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "thaumaturgy",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
                    "body": {},
                    "rendered_html": "<p>Thaumaturgy.</p>",
                },
            ],
        )

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "mechanics/harbor-spell-drill",
            "custom_feature_activation_type_1": "special",
            "custom_feature_description_1": "",
            "custom_feature_spell_support_1_granted_1_1": "phb-spell-light",
            "custom_feature_spell_support_1_replace_known_1_from_1": "phb-spell-message",
            "custom_feature_spell_support_1_replace_known_1_to_1": "phb-spell-ray-of-frost",
        },
        follow_redirects=False,
    )

    assert add_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    spells_by_name = {spell["name"]: spell for spell in record.definition.spellcasting["spells"]}
    hidden_spells = list(record.definition.spellcasting.get("campaign_option_replacement_bases") or [])

    assert spells_by_name["Detect Magic"]["is_always_prepared"] is True
    assert spells_by_name["Detect Magic"]["is_ritual"] is True
    assert spells_by_name["Light"]["mark"] == "Granted"
    assert spells_by_name["Ray of Frost"]["mark"] == "Cantrip"
    assert "Message" not in spells_by_name
    assert any(spell.get("name") == "Message" for spell in hidden_spells)

    custom_feature = next(
        feature
        for feature in record.definition.features
        if feature.get("category") == "custom_feature" and feature.get("page_ref") == "mechanics/harbor-spell-drill"
    )

    remove_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_id_1": custom_feature["id"],
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "",
            "custom_feature_activation_type_1": "passive",
            "custom_feature_description_1": "",
        },
        follow_redirects=False,
    )

    assert remove_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    spells_by_name = {spell["name"]: spell for spell in record.definition.spellcasting["spells"]}

    assert "Message" in spells_by_name
    assert "Detect Magic" not in spells_by_name
    assert "Light" not in spells_by_name
    assert "Ray of Frost" not in spells_by_name
    assert not list(record.definition.spellcasting.get("campaign_option_replacement_bases") or [])


def test_character_retraining_route_updates_existing_spell_support_replacements(
    app, client, sign_in, users, get_character, set_campaign_visibility
):
    training_page_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "content"
        / "mechanics"
        / "harbor-spell-drill.md"
    )
    training_page_path.write_text(
        """---
title: Harbor Spell Drill
section: Mechanics
subsection: Blessings
published: true
summary: A harbor rite that teaches a new cantrip and rewires an old one.
character_option:
  name: Harbor Spell Drill
  description_markdown: Harbor drillmasters teach you a practiced magical exchange.
  activation_type: special
  spell_support:
    - grants:
        _:
          - spell: Detect Magic
            always_prepared: true
            ritual: true
      choices:
        _:
          - category: granted
            options:
              - Light
              - Mage Hand
            count: 1
            label_prefix: Drill Cantrip
            mark: Granted
      replacement:
        _:
          - kind: known
            from:
              options:
                - Message
            to:
              options:
                - Ray of Frost
                - Thaumaturgy
---
The drill is meant to replace a memorized shortcut with a more disciplined response.
""",
        encoding="utf-8",
    )

    with app.app_context():
        systems_store = app.extensions["systems_store"]
        systems_store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        systems_store.upsert_source(
            "DND-5E",
            "PHB",
            title="Player's Handbook",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["spell"],
            entries=[
                {
                    "entry_key": "dnd-5e|spell|phb|message",
                    "entry_type": "spell",
                    "slug": "phb-spell-message",
                    "title": "Message",
                    "source_page": "259",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "message",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
                    "body": {},
                    "rendered_html": "<p>Message.</p>",
                },
                {
                    "entry_key": "dnd-5e|spell|phb|detect-magic",
                    "entry_type": "spell",
                    "slug": "phb-spell-detect-magic",
                    "title": "Detect Magic",
                    "source_page": "231",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "detect magic",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"casting_time": [{"number": 1, "unit": "action"}], "level": 1, "ritual": True},
                    "body": {},
                    "rendered_html": "<p>Detect Magic.</p>",
                },
                {
                    "entry_key": "dnd-5e|spell|phb|light",
                    "entry_type": "spell",
                    "slug": "phb-spell-light",
                    "title": "Light",
                    "source_page": "255",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "light",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
                    "body": {},
                    "rendered_html": "<p>Light.</p>",
                },
                {
                    "entry_key": "dnd-5e|spell|phb|mage-hand",
                    "entry_type": "spell",
                    "slug": "phb-spell-mage-hand",
                    "title": "Mage Hand",
                    "source_page": "256",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "mage hand",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
                    "body": {},
                    "rendered_html": "<p>Mage Hand.</p>",
                },
                {
                    "entry_key": "dnd-5e|spell|phb|ray-of-frost",
                    "entry_type": "spell",
                    "slug": "phb-spell-ray-of-frost",
                    "title": "Ray of Frost",
                    "source_page": "271",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "ray of frost",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
                    "body": {},
                    "rendered_html": "<p>Ray of Frost.</p>",
                },
                {
                    "entry_key": "dnd-5e|spell|phb|thaumaturgy",
                    "entry_type": "spell",
                    "slug": "phb-spell-thaumaturgy",
                    "title": "Thaumaturgy",
                    "source_page": "282",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "thaumaturgy",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
                    "body": {},
                    "rendered_html": "<p>Thaumaturgy.</p>",
                },
            ],
        )

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "mechanics/harbor-spell-drill",
            "custom_feature_activation_type_1": "special",
            "custom_feature_description_1": "",
            "custom_feature_spell_support_1_granted_1_1": "phb-spell-light",
            "custom_feature_spell_support_1_replace_known_1_from_1": "phb-spell-message",
            "custom_feature_spell_support_1_replace_known_1_to_1": "phb-spell-ray-of-frost",
        },
        follow_redirects=False,
    )

    assert add_response.status_code == 302

    page_response = client.get("/campaigns/linden-pass/characters/arden-march/retraining")
    assert page_response.status_code == 200
    page_html = page_response.get_data(as_text=True)
    assert "Harbor Spell Drill" in page_html
    assert "Choose the replacement spell." in page_html
    assert 'value="phb-spell-ray-of-frost" selected' in page_html

    record = get_character("arden-march")
    assert record is not None
    invalid_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/retraining",
        data={
            "expected_revision": record.state_record.revision,
            "custom_feature_spell_support_1_granted_1_1": "phb-spell-light",
            "custom_feature_spell_support_1_replace_known_1_from_1": "phb-spell-message",
            "custom_feature_spell_support_1_replace_known_1_to_1": "",
        },
        follow_redirects=False,
    )

    assert invalid_response.status_code == 400

    record = get_character("arden-march")
    assert record is not None
    retrain_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/retraining",
        data={
            "expected_revision": record.state_record.revision,
            "custom_feature_spell_support_1_granted_1_1": "phb-spell-light",
            "custom_feature_spell_support_1_replace_known_1_from_1": "phb-spell-message",
            "custom_feature_spell_support_1_replace_known_1_to_1": "phb-spell-thaumaturgy",
        },
        follow_redirects=False,
    )

    assert retrain_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    spells_by_name = {spell["name"]: spell for spell in record.definition.spellcasting["spells"]}
    hidden_spells = list(record.definition.spellcasting.get("campaign_option_replacement_bases") or [])

    assert "Detect Magic" in spells_by_name
    assert spells_by_name["Light"]["mark"] == "Granted"
    assert "Thaumaturgy" in spells_by_name
    assert "Ray of Frost" not in spells_by_name
    assert "Message" not in spells_by_name
    assert any(spell.get("name") == "Message" for spell in hidden_spells)
    latest_event = list((record.definition.source or {}).get("native_progression", {}).get("history") or [])[-1]
    assert latest_event["action"] == "retrain"
    assert latest_event["kind"] == "retrain"


def test_native_character_edits_can_apply_and_remove_campaign_page_spell_support_source_rows(
    app, client, sign_in, users, get_character, set_campaign_visibility
):
    training_page_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "content"
        / "mechanics"
        / "harbor-moon-lesson.md"
    )
    training_page_path.write_text(
        """---
title: Harbor Moon Lesson
section: Mechanics
subsection: Blessings
published: true
summary: A moonlit harbor lesson that teaches one emergency spell.
character_option:
  name: Harbor Moon Lesson
  description_markdown: Harbor lantern-keepers teach you one emergency casting.
  activation_type: special
  spell_support:
    - source:
        title: Harbor Moon Lesson
        kind: feature
        ability_key: int
      choices:
        _:
          - category: granted
            options:
              - Shield
              - Feather Fall
            count: 1
            label_prefix: Harbor Lesson Spell
            mark: Granted
            access_type: free_cast
            access_uses: 1
            access_reset_on: long_rest
---
Lantern-keepers pass the lesson down from one storm season to the next.
""",
        encoding="utf-8",
    )

    with app.app_context():
        systems_store = app.extensions["systems_store"]
        systems_store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        systems_store.upsert_source(
            "DND-5E",
            "PHB",
            title="Player's Handbook",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["spell"],
            entries=[
                {
                    "entry_key": "dnd-5e|spell|phb|shield",
                    "entry_type": "spell",
                    "slug": "phb-spell-shield",
                    "title": "Shield",
                    "source_page": "275",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "shield",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"casting_time": [{"number": 1, "unit": "reaction"}], "level": 1},
                    "body": {},
                    "rendered_html": "<p>Shield.</p>",
                },
                {
                    "entry_key": "dnd-5e|spell|phb|feather-fall",
                    "entry_type": "spell",
                    "slug": "phb-spell-feather-fall",
                    "title": "Feather Fall",
                    "source_page": "239",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "feather fall",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"casting_time": [{"number": 1, "unit": "reaction"}], "level": 1},
                    "body": {},
                    "rendered_html": "<p>Feather Fall.</p>",
                },
            ],
        )

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "mechanics/harbor-moon-lesson",
            "custom_feature_activation_type_1": "special",
            "custom_feature_description_1": "",
            "custom_feature_spell_support_1_granted_1_1": "phb-spell-shield",
        },
        follow_redirects=False,
    )

    assert add_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    custom_feature = next(
        feature
        for feature in record.definition.features
        if feature.get("category") == "custom_feature" and feature.get("page_ref") == "mechanics/harbor-moon-lesson"
    )
    source_rows = [dict(row or {}) for row in list(record.definition.spellcasting.get("source_rows") or [])]
    assert len(source_rows) == 1
    source_row = source_rows[0]
    spells_by_name = {spell["name"]: spell for spell in record.definition.spellcasting["spells"]}

    assert custom_feature["name"] == "Harbor Moon Lesson"
    assert source_row["source_row_id"] == "spell-source:harbor-moon-lesson"
    assert source_row["source_row_kind"] == "feature"
    assert source_row["title"] == "Harbor Moon Lesson"
    assert source_row["spellcasting_ability"] == "Intelligence"
    assert spells_by_name["Shield"]["spell_source_row_id"] == "spell-source:harbor-moon-lesson"
    assert spells_by_name["Shield"]["spell_source_row_kind"] == "feature"
    assert spells_by_name["Shield"]["spell_source_row_title"] == "Harbor Moon Lesson"
    assert spells_by_name["Shield"]["spell_access_type"] == "free_cast"
    assert spells_by_name["Shield"]["spell_access_uses"] == 1
    assert spells_by_name["Shield"]["spell_access_reset_on"] == "long_rest"
    assert spells_by_name["Shield"]["grant_source_label"] == "Harbor Moon Lesson"

    remove_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_id_1": custom_feature["id"],
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "",
            "custom_feature_activation_type_1": "passive",
            "custom_feature_description_1": "",
        },
        follow_redirects=False,
    )

    assert remove_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    spells_by_name = {spell["name"]: spell for spell in record.definition.spellcasting["spells"]}
    assert "Shield" not in spells_by_name
    assert all(
        str(row.get("source_row_id") or "").strip() != "spell-source:harbor-moon-lesson"
        for row in list(record.definition.spellcasting.get("source_rows") or [])
    )


def test_native_character_edits_can_apply_and_remove_campaign_page_spell_manager(
    app, client, sign_in, users, get_character, set_campaign_visibility
):
    ritual_page_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "content"
        / "mechanics"
        / "harbor-ritual-book.md"
    )
    ritual_page_path.write_text(
        """---
title: Harbor Ritual Book
section: Mechanics
subsection: Blessings
published: true
summary: A warded ritual book copied by the harbor shrine.
character_option:
  name: Harbor Ritual Book
  description_markdown: The shrine scribes entrust you with a small ritual book.
  activation_type: special
  spell_manager:
    mode: ritual_book
    source_row_kind: feature
    source_title: Harbor Ritual Book
    spell_list_class_name: Wizard
    ability_key: int
    max_spell_level_formula: ritual_caster_half_level_rounded_up
    choice_fields:
      - category: spell_managed
        filter: level=1|class=Wizard|miscellaneous=ritual
        count: 1
        label_prefix: Harbor Ritual
        help_text: Choose a wizard ritual for the harbor ritual book.
        spell_mark: Ritual Book
        spell_is_ritual: true
---
The wardens keep the harbor rites bound in salted leather.
""",
        encoding="utf-8",
    )

    with app.app_context():
        systems_store = app.extensions["systems_store"]
        systems_store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        systems_store.upsert_source(
            "DND-5E",
            "PHB",
            title="Player's Handbook",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["spell"],
            entries=[
                {
                    "entry_key": "dnd-5e|spell|phb|detect-magic",
                    "entry_type": "spell",
                    "slug": "phb-spell-detect-magic",
                    "title": "Detect Magic",
                    "source_page": "231",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "detect magic",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {
                        "casting_time": [{"number": 1, "unit": "action"}],
                        "level": 1,
                        "ritual": True,
                        "class_lists": {"PHB": ["Wizard"]},
                    },
                    "body": {},
                    "rendered_html": "<p>Detect Magic.</p>",
                },
                {
                    "entry_key": "dnd-5e|spell|phb|alarm",
                    "entry_type": "spell",
                    "slug": "phb-spell-alarm",
                    "title": "Alarm",
                    "source_page": "211",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "alarm",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {
                        "casting_time": [{"number": 1, "unit": "minute"}],
                        "level": 1,
                        "ritual": True,
                        "class_lists": {"PHB": ["Wizard"]},
                    },
                    "body": {},
                    "rendered_html": "<p>Alarm.</p>",
                },
            ],
        )

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "mechanics/harbor-ritual-book",
            "custom_feature_activation_type_1": "special",
            "custom_feature_description_1": "",
            "custom_feature_spell_manager_1_spell_managed_1_1": "phb-spell-detect-magic",
        },
        follow_redirects=False,
    )

    assert add_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    custom_feature = next(
        feature
        for feature in record.definition.features
        if feature.get("category") == "custom_feature" and feature.get("page_ref") == "mechanics/harbor-ritual-book"
    )
    spell_manager = dict(custom_feature.get("spell_manager") or {})
    spells_by_name = {spell["name"]: spell for spell in record.definition.spellcasting["spells"]}

    assert custom_feature["name"] == "Harbor Ritual Book"
    assert spell_manager["mode"] == "ritual_book"
    assert spell_manager["title"] == "Harbor Ritual Book"
    assert spell_manager["spell_list_class_name"] == "Wizard"
    assert spells_by_name["Detect Magic"]["mark"] == "Ritual Book"
    assert spells_by_name["Detect Magic"]["spell_source_row_id"] == spell_manager["source_row_id"]
    assert spells_by_name["Detect Magic"]["is_ritual"] is True

    remove_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_id_1": custom_feature["id"],
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "",
            "custom_feature_activation_type_1": "passive",
            "custom_feature_description_1": "",
        },
        follow_redirects=False,
    )

    assert remove_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    assert "Detect Magic" not in {spell["name"] for spell in record.definition.spellcasting["spells"]}
    assert all(
        str(feature.get("page_ref") or "").strip() != "mechanics/harbor-ritual-book"
        for feature in record.definition.features
    )


def test_native_character_edits_require_complete_spell_support_replacement_pairs(
    app, client, sign_in, users, get_character, set_campaign_visibility
):
    training_page_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "content"
        / "mechanics"
        / "spell-swap-drill.md"
    )
    training_page_path.write_text(
        """---
title: Spell Swap Drill
section: Mechanics
subsection: Blessings
published: true
summary: A focused swap drill.
character_option:
  name: Spell Swap Drill
  description_markdown: Swap one practiced trick for another.
  activation_type: special
  spell_support:
    - replacement:
        _:
          - kind: known
            from:
              options:
                - Message
            to:
              options:
                - Ray of Frost
---
Swap training happens on the end of the pier.
""",
        encoding="utf-8",
    )

    with app.app_context():
        systems_store = app.extensions["systems_store"]
        systems_store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        systems_store.upsert_source(
            "DND-5E",
            "PHB",
            title="Player's Handbook",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["spell"],
            entries=[
                {
                    "entry_key": "dnd-5e|spell|phb|message",
                    "entry_type": "spell",
                    "slug": "phb-spell-message",
                    "title": "Message",
                    "source_page": "259",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "message",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
                    "body": {},
                    "rendered_html": "<p>Message.</p>",
                },
                {
                    "entry_key": "dnd-5e|spell|phb|ray-of-frost",
                    "entry_type": "spell",
                    "slug": "phb-spell-ray-of-frost",
                    "title": "Ray of Frost",
                    "source_page": "271",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "ray of frost",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"casting_time": [{"number": 1, "unit": "action"}], "level": 0},
                    "body": {},
                    "rendered_html": "<p>Ray of Frost.</p>",
                },
            ],
        )

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "mechanics/spell-swap-drill",
            "custom_feature_activation_type_1": "special",
            "custom_feature_description_1": "",
            "custom_feature_spell_support_1_replace_known_1_from_1": "phb-spell-message",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert b"Replace Spell 1 and Replacement Spell 1 must both be chosen together." in response.data


def test_native_character_edits_can_apply_and_remove_campaign_page_additional_spells(
    app, client, sign_in, users, get_character, set_campaign_visibility
):
    training_page_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "content"
        / "mechanics"
        / "harbor-spell-lessons.md"
    )
    training_page_path.write_text(
        """---
title: Harbor Spell Lessons
section: Mechanics
subsection: Blessings
published: true
summary: Harbor magisters drill a tide-touched spell cadence into your reflexes.
character_option:
  name: Harbor Spell Lessons
  description_markdown: Harbor magisters teach you a practiced magical cadence.
  activation_type: special
  additional_spells:
    - known:
        "1":
          - choose: level=0|class=Wizard
      prepared:
        "1":
          - Detect Magic
      innate:
        "1":
          daily:
            "1":
              - choose: level=1|class=Wizard
---
Salt-stiff harbor lessons leave a little magic behind.
""",
        encoding="utf-8",
    )

    with app.app_context():
        systems_store = app.extensions["systems_store"]
        systems_store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        systems_store.upsert_source(
            "DND-5E",
            "PHB",
            title="Player's Handbook",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["spell"],
            entries=[
                {
                    "entry_key": "dnd-5e|spell|phb|mage-hand",
                    "entry_type": "spell",
                    "slug": "phb-spell-mage-hand",
                    "title": "Mage Hand",
                    "source_page": "256",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "mage hand",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {
                        "casting_time": [{"number": 1, "unit": "action"}],
                        "level": 0,
                        "class_lists": {"PHB": ["Wizard"]},
                    },
                    "body": {},
                    "rendered_html": "<p>Mage Hand.</p>",
                },
                {
                    "entry_key": "dnd-5e|spell|phb|light",
                    "entry_type": "spell",
                    "slug": "phb-spell-light",
                    "title": "Light",
                    "source_page": "255",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "light",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {
                        "casting_time": [{"number": 1, "unit": "action"}],
                        "level": 0,
                        "class_lists": {"PHB": ["Wizard"]},
                    },
                    "body": {},
                    "rendered_html": "<p>Light.</p>",
                },
                {
                    "entry_key": "dnd-5e|spell|phb|detect-magic",
                    "entry_type": "spell",
                    "slug": "phb-spell-detect-magic",
                    "title": "Detect Magic",
                    "source_page": "231",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "detect magic",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {
                        "casting_time": [{"number": 1, "unit": "action"}],
                        "level": 1,
                        "class_lists": {"PHB": ["Wizard"]},
                        "ritual": True,
                    },
                    "body": {},
                    "rendered_html": "<p>Detect Magic.</p>",
                },
                {
                    "entry_key": "dnd-5e|spell|phb|shield",
                    "entry_type": "spell",
                    "slug": "phb-spell-shield",
                    "title": "Shield",
                    "source_page": "275",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "shield",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {
                        "casting_time": [{"number": 1, "unit": "reaction"}],
                        "level": 1,
                        "class_lists": {"PHB": ["Wizard"]},
                    },
                    "body": {},
                    "rendered_html": "<p>Shield.</p>",
                },
                {
                    "entry_key": "dnd-5e|spell|phb|feather-fall",
                    "entry_type": "spell",
                    "slug": "phb-spell-feather-fall",
                    "title": "Feather Fall",
                    "source_page": "239",
                    "source_path": "data/spells/spells-phb.json",
                    "search_text": "feather fall",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {
                        "casting_time": [{"number": 1, "unit": "reaction"}],
                        "level": 1,
                        "class_lists": {"PHB": ["Wizard"]},
                    },
                    "body": {},
                    "rendered_html": "<p>Feather Fall.</p>",
                },
            ],
        )

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "mechanics/harbor-spell-lessons",
            "custom_feature_activation_type_1": "special",
            "custom_feature_description_1": "",
            "custom_feature_additional_spells_1_known_1_1": "phb-spell-mage-hand",
            "custom_feature_additional_spells_1_granted_1_1": "phb-spell-shield",
        },
        follow_redirects=False,
    )

    assert add_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    spells_by_name = {spell["name"]: spell for spell in record.definition.spellcasting["spells"]}
    custom_feature = next(
        feature
        for feature in record.definition.features
        if feature.get("category") == "custom_feature" and feature.get("page_ref") == "mechanics/harbor-spell-lessons"
    )

    assert spells_by_name["Mage Hand"]["mark"] == "Cantrip"
    assert spells_by_name["Mage Hand"]["is_bonus_known"] is True
    assert spells_by_name["Detect Magic"]["is_always_prepared"] is True
    assert spells_by_name["Shield"]["mark"] == "1 / Long Rest"

    remove_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_id_1": custom_feature["id"],
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "",
            "custom_feature_activation_type_1": "passive",
            "custom_feature_description_1": "",
        },
        follow_redirects=False,
    )

    assert remove_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    spells_by_name = {spell["name"]: spell for spell in record.definition.spellcasting["spells"]}

    assert "Mage Hand" not in spells_by_name
    assert "Detect Magic" not in spells_by_name
    assert "Shield" not in spells_by_name


def test_native_character_edits_accept_page_backed_feat_links_and_preserve_tracker_state(
    app, client, sign_in, users, get_character, set_campaign_visibility
):
    feat_page_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "content"
        / "mechanics"
        / "tidecaller-gift.md"
    )
    feat_page_path.write_text(
        """---
title: Tidecaller Gift
section: Mechanics
subsection: Feats
published: true
summary: A harbor rite that answers with a little of the sea.
character_option:
  kind: feat
  name: Tidecaller Gift
  description_markdown: You can call a little of the tide to your side.
  activation_type: special
  resource:
    max: 3
    reset_on: long_rest
  grants:
    languages:
      - Primordial
---
The harbor priests mark trusted wardens with a breath of salt and storm.
""",
        encoding="utf-8",
    )

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "mechanics/tidecaller-gift",
            "custom_feature_activation_type_1": "special",
            "custom_feature_description_1": "",
        },
        follow_redirects=False,
    )

    assert add_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    tidecaller = next(
        feature
        for feature in record.definition.features
        if feature.get("category") == "custom_feature" and feature.get("page_ref") == "mechanics/tidecaller-gift"
    )
    tracker_ref = str(tidecaller.get("tracker_ref") or "")

    assert tidecaller["name"] == "Tidecaller Gift"
    assert tidecaller["activation_type"] == "special"
    assert tidecaller["description_markdown"] == "You can call a little of the tide to your side."
    assert "Primordial" in record.definition.proficiencies["languages"]
    assert any(resource["id"] == tracker_ref and resource["max"] == 3 for resource in record.definition.resource_templates)

    with app.app_context():
        repository = app.extensions["character_repository"]
        store = app.extensions["character_state_store"]
        refreshed = repository.get_character("linden-pass", "arden-march")
        assert refreshed is not None
        payload = dict(refreshed.state_record.state or {})
        resources = [dict(resource) for resource in list(payload.get("resources") or [])]
        for resource in resources:
            if resource.get("id") == tracker_ref:
                resource["current"] = 1
        payload["resources"] = resources
        store.replace_state(
            refreshed.definition,
            payload,
            expected_revision=refreshed.state_record.revision,
        )

    record = get_character("arden-march")
    assert record is not None
    save_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_id_1": tidecaller["id"],
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "mechanics/tidecaller-gift",
            "custom_feature_activation_type_1": "special",
            "custom_feature_description_1": "",
        },
        follow_redirects=False,
    )

    assert save_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    resource_state = next(resource for resource in record.state_record.state["resources"] if resource["id"] == tracker_ref)
    assert resource_state["current"] == 1
    assert resource_state["max"] == 3


def test_native_character_edits_support_page_backed_feat_optionalfeature_choices(
    app, client, sign_in, users, get_character, set_campaign_visibility
):
    feat_page_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "content"
        / "mechanics"
        / "harbor-drill.md"
    )
    feat_page_path.write_text(
        """---
title: Harbor Drill
section: Mechanics
subsection: Feats
published: true
summary: A harbor discipline that grants a fighting style.
character_option:
  kind: feat
  name: Harbor Drill
  description_markdown: Harbor veterans drill you into a practiced fighting style.
  optionalfeature_progression:
    - name: Fighting Style
      featureType:
        - FS:F
      progression:
        "1": 1
---
The harbor masters insist on repetition until every motion is clean.
""",
        encoding="utf-8",
    )

    with app.app_context():
        systems_store = app.extensions["systems_store"]
        systems_store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        systems_store.upsert_source(
            "DND-5E",
            "PHB",
            title="Player's Handbook",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["optionalfeature"],
            entries=[
                {
                    "entry_key": "dnd-5e|optionalfeature|phb|defense",
                    "entry_type": "optionalfeature",
                    "slug": "phb-optionalfeature-defense",
                    "title": "Defense",
                    "source_page": "72",
                    "source_path": "data/class/class-fighter.json",
                    "search_text": "defense fighting style",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"feature_type": ["FS:F"]},
                    "body": {},
                    "rendered_html": "<p>Defense.</p>",
                },
                {
                    "entry_key": "dnd-5e|optionalfeature|phb|dueling",
                    "entry_type": "optionalfeature",
                    "slug": "phb-optionalfeature-dueling",
                    "title": "Dueling",
                    "source_page": "72",
                    "source_path": "data/class/class-fighter.json",
                    "search_text": "dueling fighting style",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"feature_type": ["FS:F"]},
                    "body": {},
                    "rendered_html": "<p>Dueling.</p>",
                },
            ],
        )

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "mechanics/harbor-drill",
            "custom_feature_activation_type_1": "passive",
            "custom_feature_description_1": "",
            "custom_feature_optionalfeature_1_1_1": "phb-optionalfeature-defense",
        },
        follow_redirects=False,
    )

    assert add_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    harbor_drill = next(
        feature
        for feature in record.definition.features
        if feature.get("category") == "custom_feature" and feature.get("page_ref") == "mechanics/harbor-drill"
    )
    defense = next(
        feature
        for feature in record.definition.features
        if dict(feature.get("systems_ref") or {}).get("slug") == "phb-optionalfeature-defense"
    )

    assert harbor_drill["name"] == "Harbor Drill"
    assert defense["name"] == "Defense"
    assert defense["native_edit_parent_feature_id"] == harbor_drill["id"]
    assert defense["native_edit_optionalfeature_section_index"] == 1
    assert defense["native_edit_optionalfeature_choice_index"] == 1

    edit_response = client.get("/campaigns/linden-pass/characters/arden-march/edit")
    assert edit_response.status_code == 200
    edit_html = edit_response.get_data(as_text=True)
    assert "Harbor Drill Fighting Style" in edit_html
    assert 'value="phb-optionalfeature-defense" selected' in edit_html

    swap_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_id_1": harbor_drill["id"],
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "mechanics/harbor-drill",
            "custom_feature_activation_type_1": "passive",
            "custom_feature_description_1": "",
            "custom_feature_optionalfeature_1_1_1": "phb-optionalfeature-dueling",
        },
        follow_redirects=False,
    )

    assert swap_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    feature_slugs = {
        str(dict(feature.get("systems_ref") or {}).get("slug") or "").strip()
        for feature in record.definition.features
    }
    assert "phb-optionalfeature-defense" not in feature_slugs
    assert "phb-optionalfeature-dueling" in feature_slugs


def test_character_retraining_route_swaps_optionalfeature_choices_and_rebuilds_attacks(
    app, client, sign_in, users, get_character, set_campaign_visibility
):
    feat_page_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "content"
        / "mechanics"
        / "harbor-drill.md"
    )
    feat_page_path.write_text(
        """---
title: Harbor Drill
section: Mechanics
subsection: Feats
published: true
summary: A harbor discipline that grants a fighting style.
character_option:
  kind: feat
  name: Harbor Drill
  description_markdown: Harbor veterans drill you into a practiced fighting style.
  optionalfeature_progression:
    - name: Fighting Style
      featureType:
        - FS:F
      progression:
        "1": 1
---
The harbor masters insist on repetition until every motion is clean.
""",
        encoding="utf-8",
    )

    with app.app_context():
        systems_store = app.extensions["systems_store"]
        systems_store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        systems_store.upsert_source(
            "DND-5E",
            "PHB",
            title="Player's Handbook",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        systems_store.replace_entries_for_source(
            "DND-5E",
            "PHB",
            entry_types=["optionalfeature"],
            entries=[
                {
                    "entry_key": "dnd-5e|optionalfeature|phb|archery",
                    "entry_type": "optionalfeature",
                    "slug": "phb-optionalfeature-archery",
                    "title": "Archery",
                    "source_page": "72",
                    "source_path": "data/class/class-fighter.json",
                    "search_text": "archery fighting style",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"feature_type": ["FS:F"]},
                    "body": {},
                    "rendered_html": "<p>Archery.</p>",
                },
                {
                    "entry_key": "dnd-5e|optionalfeature|phb|defense",
                    "entry_type": "optionalfeature",
                    "slug": "phb-optionalfeature-defense",
                    "title": "Defense",
                    "source_page": "72",
                    "source_path": "data/class/class-fighter.json",
                    "search_text": "defense fighting style",
                    "player_safe_default": True,
                    "dm_heavy": False,
                    "metadata": {"feature_type": ["FS:F"]},
                    "body": {},
                    "rendered_html": "<p>Defense.</p>",
                },
            ],
        )

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None
    baseline_crossbow = next(attack for attack in record.definition.attacks if "Crossbow" in attack["name"])
    assert baseline_crossbow["attack_bonus"] == 5

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "mechanics/harbor-drill",
            "custom_feature_activation_type_1": "passive",
            "custom_feature_description_1": "",
            "custom_feature_optionalfeature_1_1_1": "phb-optionalfeature-archery",
        },
        follow_redirects=False,
    )

    assert add_response.status_code == 302

    read_response = client.get("/campaigns/linden-pass/characters/arden-march")
    assert read_response.status_code == 200
    read_html = read_response.get_data(as_text=True)
    assert "/campaigns/linden-pass/characters/arden-march/retraining" in read_html

    record = get_character("arden-march")
    assert record is not None
    boosted_crossbow = next(attack for attack in record.definition.attacks if "Crossbow" in attack["name"])
    assert boosted_crossbow["attack_bonus"] == 7

    retraining_page = client.get("/campaigns/linden-pass/characters/arden-march/retraining")
    assert retraining_page.status_code == 200
    retraining_html = retraining_page.get_data(as_text=True)
    assert "Harbor Drill Fighting Style" in retraining_html
    assert 'value="phb-optionalfeature-archery" selected' in retraining_html

    retrain_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/retraining",
        data={
            "expected_revision": record.state_record.revision,
            "custom_feature_optionalfeature_1_1_1": "phb-optionalfeature-defense",
        },
        follow_redirects=False,
    )

    assert retrain_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    feature_slugs = {
        str(dict(feature.get("systems_ref") or {}).get("slug") or "").strip()
        for feature in record.definition.features
    }
    retrained_crossbow = next(attack for attack in record.definition.attacks if "Crossbow" in attack["name"])

    assert "phb-optionalfeature-archery" not in feature_slugs
    assert "phb-optionalfeature-defense" in feature_slugs
    assert retrained_crossbow["attack_bonus"] == 5
    latest_event = list((record.definition.source or {}).get("native_progression", {}).get("history") or [])[-1]
    assert latest_event["action"] == "retrain"
    assert latest_event["kind"] == "retrain"


def test_native_character_edits_apply_fixed_page_backed_feat_metadata(
    app, client, sign_in, users, get_character, set_campaign_visibility
):
    feat_page_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "content"
        / "mechanics"
        / "harbor-veteran-rite.md"
    )
    feat_page_path.write_text(
        """---
title: Harbor Veteran Rite
section: Mechanics
subsection: Feats
published: true
summary: A rite that teaches hard-earned harbor reflexes.
character_option:
  kind: feat
  name: Harbor Veteran Rite
  description_markdown: Veteran wardens teach you the reflexes needed to survive the piers in a storm.
  skill_proficiencies:
    - athletics: true
  expertise:
    - perception: true
  language_proficiencies:
    - primordial: true
  tool_proficiencies:
    - smith's tools: true
  weapon_proficiencies:
    - martial: true
  armor_proficiencies:
    - shield: true
  saving_throw_proficiencies:
    - wis: true
---
The harbor veterans insist on quick eyes, a steady shield, and a practiced hand.
""",
        encoding="utf-8",
    )

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "mechanics/harbor-veteran-rite",
            "custom_feature_activation_type_1": "passive",
            "custom_feature_description_1": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    record = get_character("arden-march")
    assert record is not None

    veteran_rite = next(
        feature
        for feature in record.definition.features
        if feature.get("category") == "custom_feature" and feature.get("page_ref") == "mechanics/harbor-veteran-rite"
    )
    assert veteran_rite["name"] == "Harbor Veteran Rite"
    assert (
        veteran_rite["description_markdown"]
        == "Veteran wardens teach you the reflexes needed to survive the piers in a storm."
    )

    assert "Primordial" in record.definition.proficiencies["languages"]
    assert any(tool.casefold() == "smith's tools" for tool in record.definition.proficiencies["tools"])
    assert "Martial Weapons" in record.definition.proficiencies["weapons"]
    assert "Shields" in record.definition.proficiencies["armor"]

    skills_by_name = {skill["name"]: skill for skill in record.definition.skills}
    assert skills_by_name["Athletics"]["proficiency_level"] == "proficient"
    assert skills_by_name["Athletics"]["bonus"] == 3
    assert skills_by_name["Perception"]["proficiency_level"] == "expertise"
    assert skills_by_name["Perception"]["bonus"] == 7

    assert record.definition.stats["passive_perception"] == 17
    assert record.definition.stats["ability_scores"]["wis"]["save_bonus"] == 4


def test_native_character_edits_persist_page_backed_feat_choice_metadata(
    app, client, sign_in, users, get_character, set_campaign_visibility
):
    feat_page_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "content"
        / "mechanics"
        / "harbor-honors.md"
    )
    feat_page_path.write_text(
        """---
title: Harbor Honors
section: Mechanics
subsection: Feats
published: true
summary: A ceremonial reward that deepens a warden's training.
character_option:
  kind: feat
  name: Harbor Honors
  description_markdown: Harbor captains mark your service with a focused reward.
  ability:
    - choose:
        from:
          - str
          - dex
          - con
          - int
          - wis
          - cha
        count: 1
  skill_proficiencies:
    - any: 1
  language_proficiencies:
    - anyStandard: 1
  saving_throw_proficiencies:
    - choose:
        from:
          - str
          - dex
          - con
          - int
          - wis
          - cha
        count: 1
---
Harbor captains honor proven wardens with a deeper round of training.
""",
        encoding="utf-8",
    )

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None
    base_stats = dict(record.definition.stats or {})
    base_skills = {
        skill["name"]: dict(skill)
        for skill in list(record.definition.skills or [])
    }
    base_languages = set(record.definition.proficiencies["languages"])
    proficiency_bonus = int(base_stats["proficiency_bonus"])
    ability_scores = dict(base_stats["ability_scores"] or {})

    available_save_choices = [
        ability_key
        for ability_key, payload in ability_scores.items()
        if int(payload["save_bonus"]) == int(payload["modifier"])
    ]
    assert len(available_save_choices) >= 2
    first_ability = available_save_choices[0]
    second_ability = available_save_choices[1]

    skill_candidates = [
        skill_name
        for skill_name, payload in base_skills.items()
        if str(payload.get("proficiency_level") or "") == "none"
    ]
    assert skill_candidates
    first_skill = skill_candidates[0]

    def skill_token(skill_name: str) -> str:
        return "".join(character for character in skill_name.casefold() if character.isalnum())

    language_candidates = [
        language
        for language in (
            "Dwarvish",
            "Giant",
            "Gnomish",
            "Goblin",
            "Halfling",
            "Orc",
        )
        if language not in base_languages
    ]
    assert len(language_candidates) >= 2
    first_language = language_candidates[0]
    second_language = language_candidates[1]

    instance_key = "campaign-option-feat-custom-feature-harbor-honors"
    ability_field = f"feat_{instance_key}_ability_1"
    skill_field = f"feat_{instance_key}_skills_1"
    language_field = f"feat_{instance_key}_languages_1"
    save_field = f"feat_{instance_key}_saving_throws_1"

    add_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "mechanics/harbor-honors",
            "custom_feature_activation_type_1": "passive",
            "custom_feature_description_1": "",
            ability_field: first_ability,
            skill_field: skill_token(first_skill),
            language_field: first_language,
            save_field: first_ability,
        },
        follow_redirects=False,
    )

    assert add_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    harbor_honors = next(
        feature
        for feature in record.definition.features
        if feature.get("category") == "custom_feature"
        and feature.get("page_ref") == "mechanics/harbor-honors"
    )
    assert harbor_honors["name"] == "Harbor Honors"
    assert harbor_honors["campaign_option"]["selected_choices"] == {
        "ability": [first_ability],
        "skills": [skill_token(first_skill)],
        "languages": [first_language],
        "saving_throws": [first_ability],
    }

    updated_skills = {
        skill["name"]: dict(skill)
        for skill in list(record.definition.skills or [])
    }
    assert updated_skills[first_skill]["proficiency_level"] == "proficient"
    assert first_language in record.definition.proficiencies["languages"]
    assert record.definition.stats["ability_scores"][first_ability]["score"] == int(
        base_stats["ability_scores"][first_ability]["score"]
    ) + 1
    assert record.definition.stats["ability_scores"][first_ability]["save_bonus"] == (
        ((int(base_stats["ability_scores"][first_ability]["score"]) + 1) - 10) // 2
        + proficiency_bonus
    )

    edit_response = client.get("/campaigns/linden-pass/characters/arden-march/edit")
    assert edit_response.status_code == 200
    edit_html = edit_response.get_data(as_text=True)
    assert "Harbor Honors Ability" in edit_html
    saved_ability_field = re.search(r'name="(feat_[^"]+_ability_1)"', edit_html)
    saved_skill_field = re.search(r'name="(feat_[^"]+_skills_1)"', edit_html)
    saved_language_field = re.search(r'name="(feat_[^"]+_languages_1)"', edit_html)
    saved_save_field = re.search(r'name="(feat_[^"]+_saving_throws_1)"', edit_html)
    assert saved_ability_field is not None
    assert saved_skill_field is not None
    assert saved_language_field is not None
    assert saved_save_field is not None
    saved_ability_field_name = saved_ability_field.group(1)
    saved_skill_field_name = saved_skill_field.group(1)
    saved_language_field_name = saved_language_field.group(1)
    saved_save_field_name = saved_save_field.group(1)

    def selected_option_value(html: str, field_name: str) -> str:
        field_match = re.search(
            rf'<select name="{re.escape(field_name)}">(?P<body>.*?)</select>',
            html,
            re.S,
        )
        assert field_match is not None
        selected_match = re.search(r'<option value="([^"]*)" selected>', field_match.group("body"))
        assert selected_match is not None
        return selected_match.group(1)

    assert selected_option_value(edit_html, saved_ability_field_name) == first_ability
    assert selected_option_value(edit_html, saved_skill_field_name) == skill_token(first_skill)
    assert selected_option_value(edit_html, saved_language_field_name) == first_language
    assert selected_option_value(edit_html, saved_save_field_name) == first_ability

    swap_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_id_1": harbor_honors["id"],
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "mechanics/harbor-honors",
            "custom_feature_activation_type_1": "passive",
            "custom_feature_description_1": "",
            saved_ability_field_name: second_ability,
            saved_skill_field_name: skill_token(first_skill),
            saved_language_field_name: second_language,
            saved_save_field_name: second_ability,
        },
        follow_redirects=False,
    )

    assert swap_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    updated_skills = {
        skill["name"]: dict(skill)
        for skill in list(record.definition.skills or [])
    }
    assert updated_skills[first_skill]["proficiency_level"] == "proficient"
    assert first_language not in record.definition.proficiencies["languages"]
    assert second_language in record.definition.proficiencies["languages"]
    assert record.definition.stats["ability_scores"][first_ability]["score"] == int(
        base_stats["ability_scores"][first_ability]["score"]
    )
    assert record.definition.stats["ability_scores"][first_ability]["save_bonus"] == int(
        base_stats["ability_scores"][first_ability]["save_bonus"]
    )
    assert record.definition.stats["ability_scores"][second_ability]["score"] == int(
        base_stats["ability_scores"][second_ability]["score"]
    ) + 1
    assert record.definition.stats["ability_scores"][second_ability]["save_bonus"] == (
        ((int(base_stats["ability_scores"][second_ability]["score"]) + 1) - 10) // 2
        + proficiency_bonus
    )

    harbor_honors = next(
        feature
        for feature in record.definition.features
        if feature.get("category") == "custom_feature"
        and feature.get("page_ref") == "mechanics/harbor-honors"
    )
    assert harbor_honors["campaign_option"]["selected_choices"] == {
        "ability": [second_ability],
        "skills": [skill_token(first_skill)],
        "languages": [second_language],
        "saving_throws": [second_ability],
    }

    remove_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "Daggers\nLight Crossbows\nQuarterstaffs",
            "tool_proficiencies_text": "Navigator's Tools",
            "custom_feature_id_1": harbor_honors["id"],
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "",
            "custom_feature_activation_type_1": "passive",
            "custom_feature_description_1": "",
        },
        follow_redirects=False,
    )

    assert remove_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    final_skills = {
        skill["name"]: dict(skill)
        for skill in list(record.definition.skills or [])
    }
    assert first_language not in record.definition.proficiencies["languages"]
    assert second_language not in record.definition.proficiencies["languages"]
    assert final_skills[first_skill]["proficiency_level"] == base_skills[first_skill]["proficiency_level"]
    assert record.definition.stats["ability_scores"][first_ability]["score"] == int(
        base_stats["ability_scores"][first_ability]["score"]
    )
    assert record.definition.stats["ability_scores"][first_ability]["save_bonus"] == int(
        base_stats["ability_scores"][first_ability]["save_bonus"]
    )
    assert record.definition.stats["ability_scores"][second_ability]["score"] == int(
        base_stats["ability_scores"][second_ability]["score"]
    )
    assert record.definition.stats["ability_scores"][second_ability]["save_bonus"] == int(
        base_stats["ability_scores"][second_ability]["save_bonus"]
    )


def test_owner_player_can_open_native_character_edit_page(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march/edit")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Edit Arden March" in html
    assert "Save character edits" in html
    assert "Languages" in html
    assert "Reference Text" in html
    assert "Campaign Adjustments" in html
    assert "Custom Features" in html
    assert "Uses / Max" in html
    assert "Manual Equipment" in html
    assert "Linked Page" in html
    assert "Stormglass Compass | Items" in html
    assert "Arcane Overload | Mechanics / Class Modifications" in html


def test_native_character_edit_manual_equipment_rejects_non_item_linked_pages(
    client, sign_in, users, get_character, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "manual_item_name_1": "",
            "manual_item_page_ref_1": "notes/operations-brief",
            "manual_item_quantity_1": "1",
            "manual_item_weight_1": "",
            "manual_item_notes_1": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Choose a valid linked campaign page." in response.get_data(as_text=True)

    record = get_character("arden-march")
    assert record is not None
    assert all(item.get("source_kind") != "manual_edit" for item in record.definition.equipment_catalog)


def test_native_character_edit_custom_features_reject_item_linked_pages(
    client, sign_in, users, get_character, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "items/stormglass-compass",
            "custom_feature_activation_type_1": "passive",
            "custom_feature_description_1": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Choose a valid linked campaign page." in response.get_data(as_text=True)

    record = get_character("arden-march")
    assert record is not None
    assert all(
        str(feature.get("page_ref") or "").strip() != "items/stormglass-compass"
        for feature in record.definition.features
    )


def test_owner_player_can_save_native_character_edits_and_reconcile_inventory_state(
    client, sign_in, users, get_character, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    first_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish\nThieves' Cant",
            "armor_proficiencies_text": "Light Armor\nMedium Armor",
            "weapon_proficiencies_text": "Simple Weapons\nMartial Weapons",
            "tool_proficiencies_text": "Navigator's Tools\nThieves' Tools",
            "custom_feature_name_1": "",
            "custom_feature_page_ref_1": "mechanics/arcane-overload",
            "custom_feature_activation_type_1": "passive",
            "custom_feature_description_1": "You can usually find a friendly runner near the north piers.",
            "manual_item_name_1": "",
            "manual_item_page_ref_1": "items/stormglass-compass",
            "manual_item_quantity_1": "1",
            "manual_item_weight_1": "light",
            "manual_item_notes_1": "Stamped with blue wax.",
        },
        follow_redirects=False,
    )

    assert first_response.status_code == 302
    assert first_response.headers["Location"].endswith("/campaigns/linden-pass/characters/arden-march/edit")

    record = get_character("arden-march")
    assert record is not None
    assert record.import_metadata.import_status == "managed"
    assert "Elvish" in record.definition.proficiencies["languages"]
    assert "Navigator's Tools" in record.definition.proficiencies["tools"]

    custom_feature = next(
        feature for feature in record.definition.features if feature.get("category") == "custom_feature"
    )
    assert custom_feature["name"] == "Arcane Overload"
    assert custom_feature["description_markdown"] == "You can usually find a friendly runner near the north piers."
    assert custom_feature["page_ref"] == "mechanics/arcane-overload"

    manual_item = next(
        item
        for item in record.definition.equipment_catalog
        if item.get("source_kind") == "manual_edit"
    )
    assert manual_item["name"] == "Stormglass Compass"
    assert manual_item["default_quantity"] == 1
    assert manual_item["notes"] == "Stamped with blue wax."
    assert manual_item["page_ref"] == "items/stormglass-compass"

    inventory_item = next(
        item for item in record.state_record.state["inventory"] if item.get("catalog_ref") == manual_item["id"]
    )
    assert inventory_item["name"] == "Stormglass Compass"
    assert inventory_item["quantity"] == 1
    assert inventory_item["notes"] == "Stamped with blue wax."

    second_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish\nThieves' Cant",
            "armor_proficiencies_text": "Light Armor\nMedium Armor",
            "weapon_proficiencies_text": "Simple Weapons\nMartial Weapons",
            "tool_proficiencies_text": "Navigator's Tools\nThieves' Tools",
            "custom_feature_id_1": custom_feature["id"],
            "custom_feature_name_1": "Overloaded Arcana",
            "custom_feature_page_ref_1": "mechanics/arcane-overload",
            "custom_feature_activation_type_1": "passive",
            "custom_feature_description_1": "You can usually find a friendly runner near the north piers.",
            "manual_item_id_1": manual_item["id"],
            "manual_item_name_1": "Silver Compass",
            "manual_item_page_ref_1": "items/stormglass-compass",
            "manual_item_quantity_1": "2",
            "manual_item_weight_1": "1 lb.",
            "manual_item_notes_1": "Stamped with silver wax.",
        },
        follow_redirects=False,
    )

    assert second_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    inventory_item = next(
        item for item in record.state_record.state["inventory"] if item.get("catalog_ref") == manual_item["id"]
    )
    custom_feature = next(
        feature for feature in record.definition.features if feature.get("category") == "custom_feature"
    )
    manual_item = next(
        item
        for item in record.definition.equipment_catalog
        if item.get("source_kind") == "manual_edit"
    )
    assert custom_feature["name"] == "Overloaded Arcana"
    assert custom_feature["page_ref"] == "mechanics/arcane-overload"
    assert manual_item["name"] == "Silver Compass"
    assert manual_item["page_ref"] == "items/stormglass-compass"
    assert inventory_item["quantity"] == 2
    assert inventory_item["weight"] == "1 lb."
    assert inventory_item["notes"] == "Stamped with silver wax."

    read_response = client.get("/campaigns/linden-pass/characters/arden-march?page=features")
    assert read_response.status_code == 200
    read_html = read_response.get_data(as_text=True)
    assert "/campaigns/linden-pass/pages/mechanics/arcane-overload" in read_html

    equipment_response = client.get("/campaigns/linden-pass/characters/arden-march?page=equipment")
    assert equipment_response.status_code == 200
    equipment_html = equipment_response.get_data(as_text=True)
    assert "/campaigns/linden-pass/pages/items/stormglass-compass" in equipment_html


def test_stale_revision_is_rejected_for_native_character_edits(
    client, sign_in, users, get_character, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None
    stale_revision = record.state_record.revision

    first = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": stale_revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "Light Armor",
            "weapon_proficiencies_text": "Simple Weapons",
            "tool_proficiencies_text": "Thieves' Tools",
            "manual_item_name_1": "Storm Token",
            "manual_item_quantity_1": "1",
        },
        follow_redirects=False,
    )
    assert first.status_code == 302

    second = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": stale_revision,
            "languages_text": "Common\nDwarvish",
        },
        follow_redirects=True,
    )

    assert second.status_code == 409
    html = second.get_data(as_text=True)
    assert "This sheet changed in another session. Refresh the page and try again." in html

    record = get_character("arden-march")
    assert record is not None
    manual_items = [
        item for item in record.definition.equipment_catalog if item.get("source_kind") == "manual_edit"
    ]
    assert any(item["name"] == "Storm Token" for item in manual_items)
    assert "Dwarvish" not in record.definition.proficiencies["languages"]


def test_native_character_edits_can_manage_reference_text_and_feature_trackers(
    client, sign_in, users, get_character, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    first_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "Light Armor",
            "weapon_proficiencies_text": "Simple Weapons",
            "tool_proficiencies_text": "Thieves' Tools",
            "biography_markdown": "Raised on the storm coast.",
            "personality_markdown": "- Calm under pressure",
            "additional_notes_markdown": "Keeps a weather eye on the harbor.",
            "allies_and_organizations_markdown": "Harbor Wardens",
            "custom_feature_name_1": "Blessing of the Tide",
            "custom_feature_activation_type_1": "bonus_action",
            "custom_feature_description_1": "Call on the tide to steady your footing.",
            "custom_feature_resource_max_1": "3",
            "custom_feature_resource_reset_on_1": "long_rest",
        },
        follow_redirects=False,
    )

    assert first_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    assert record.definition.profile["biography_markdown"] == "Raised on the storm coast."
    assert record.definition.profile["personality_markdown"] == "- Calm under pressure"
    assert record.definition.reference_notes["additional_notes_markdown"] == "Keeps a weather eye on the harbor."
    assert record.definition.reference_notes["allies_and_organizations_markdown"] == "Harbor Wardens"

    custom_feature = next(
        feature
        for feature in record.definition.features
        if feature.get("category") == "custom_feature" and feature.get("name") == "Blessing of the Tide"
    )
    tracker_ref = str(custom_feature.get("tracker_ref") or "")
    assert tracker_ref.startswith("manual-feature-tracker:")

    tracker_template = next(
        template for template in record.definition.resource_templates if template.get("id") == tracker_ref
    )
    assert tracker_template["label"] == "Blessing of the Tide"
    assert tracker_template["max"] == 3
    assert tracker_template["reset_on"] == "long_rest"

    resource_state = next(
        resource for resource in record.state_record.state["resources"] if resource.get("id") == tracker_ref
    )
    assert resource_state["label"] == "Blessing of the Tide"
    assert resource_state["current"] == 3
    assert resource_state["max"] == 3
    assert resource_state["reset_on"] == "long_rest"

    notes_response = client.get("/campaigns/linden-pass/characters/arden-march?page=notes")
    assert notes_response.status_code == 200
    notes_html = notes_response.get_data(as_text=True)
    assert "Raised on the storm coast." in notes_html
    assert "Harbor Wardens" in notes_html

    features_response = client.get("/campaigns/linden-pass/characters/arden-march?page=features")
    assert features_response.status_code == 200
    features_html = features_response.get_data(as_text=True)
    assert "Blessing of the Tide: 3 / 3 (Long Rest)" in features_html

    second_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "Light Armor",
            "weapon_proficiencies_text": "Simple Weapons",
            "tool_proficiencies_text": "Thieves' Tools",
            "biography_markdown": "Raised on the storm coast.",
            "personality_markdown": "- Calm under pressure",
            "additional_notes_markdown": "Keeps a weather eye on the harbor.",
            "allies_and_organizations_markdown": "Harbor Wardens",
            "custom_feature_id_1": custom_feature["id"],
            "custom_feature_name_1": "",
            "custom_feature_activation_type_1": "bonus_action",
            "custom_feature_description_1": "",
            "custom_feature_resource_max_1": "",
            "custom_feature_resource_reset_on_1": "manual",
        },
        follow_redirects=False,
    )

    assert second_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    assert all(
        feature.get("name") != "Blessing of the Tide"
        for feature in record.definition.features
    )
    assert all(template.get("id") != tracker_ref for template in record.definition.resource_templates)
    assert all(resource.get("id") != tracker_ref for resource in record.state_record.state["resources"])


def test_native_character_edits_can_apply_campaign_stat_adjustments(
    client, sign_in, users, get_character, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None
    base_stats = dict(record.definition.stats or {})

    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common\nElvish",
            "armor_proficiencies_text": "Light Armor",
            "weapon_proficiencies_text": "Simple Weapons",
            "tool_proficiencies_text": "Thieves' Tools",
            "stat_adjustment_max_hp": "4",
            "stat_adjustment_armor_class": "1",
            "stat_adjustment_initiative_bonus": "2",
            "stat_adjustment_speed": "10",
            "stat_adjustment_passive_perception": "3",
            "stat_adjustment_passive_insight": "-1",
            "stat_adjustment_passive_investigation": "2",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    adjustments = record.definition.stats["manual_adjustments"]
    assert adjustments == {
        "max_hp": 4,
        "armor_class": 1,
        "initiative_bonus": 2,
        "speed": 10,
        "passive_perception": 3,
        "passive_insight": -1,
        "passive_investigation": 2,
    }
    assert record.definition.stats["max_hp"] == int(base_stats["max_hp"]) + 4
    assert record.definition.stats["armor_class"] == int(base_stats["armor_class"]) + 1
    assert record.definition.stats["initiative_bonus"] == int(base_stats["initiative_bonus"]) + 2
    assert record.definition.stats["speed"] == "40 ft."
    assert record.definition.stats["passive_perception"] == 17
    assert record.definition.stats["passive_insight"] == 13
    assert record.definition.stats["passive_investigation"] == 13

    read_response = client.get("/campaigns/linden-pass/characters/arden-march?page=quick")
    assert read_response.status_code == 200
    read_html = read_response.get_data(as_text=True)
    assert "40 ft." in read_html


def test_native_character_edits_preserve_medium_armor_master_ac_and_manual_layering_once(
    app, client, sign_in, users, get_character, set_campaign_visibility
):
    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / "arden-march"
        / "definition.yaml"
    )
    payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    payload["source"] = {
        "source_path": "builder://arden-march",
        "source_type": "native_character_builder",
        "imported_from": "In-app Native Level 5 Builder",
        "imported_at": "2026-04-10T00:00:00Z",
        "parse_warnings": [],
    }
    stats = dict(payload.get("stats") or {})
    ability_scores = dict(stats.get("ability_scores") or {})
    ability_scores["dex"] = {"score": 16, "modifier": 3, "save_bonus": 3}
    stats["ability_scores"] = ability_scores
    stats["armor_class"] = 99
    stats["manual_adjustments"] = {}
    payload["stats"] = stats
    payload["features"] = [
        {
            "id": "medium-armor-master-1",
            "name": "Medium Armor Master",
            "category": "feat",
            "source": "PHB",
            "description_markdown": "",
            "activation_type": "passive",
            "tracker_ref": None,
            "systems_ref": {
                "entry_type": "feat",
                "slug": "phb-feat-medium-armor-master",
                "title": "Medium Armor Master",
                "source_id": "PHB",
            },
        }
    ]
    payload["equipment_catalog"] = [
        {
            "id": "scale-mail-1",
            "name": "Scale Mail",
            "default_quantity": 1,
            "weight": "45 lb.",
            "notes": "",
            "is_equipped": True,
            "systems_ref": {
                "entry_type": "item",
                "slug": "phb-item-scale-mail",
                "title": "Scale Mail",
                "source_id": "PHB",
            },
        }
    ]
    definition_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    edit_payload = {
        "languages_text": "Common\nElvish",
        "armor_proficiencies_text": "Light Armor\nMedium Armor",
        "weapon_proficiencies_text": "Simple Weapons",
        "tool_proficiencies_text": "",
        "stat_adjustment_armor_class": "1",
        "biography_markdown": "Keeps a careful watch on every approach.",
    }
    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            **edit_payload,
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    assert record.definition.stats["armor_class"] == 18
    assert record.definition.stats["manual_adjustments"]["armor_class"] == 1

    second_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/edit",
        data={
            "expected_revision": record.state_record.revision,
            **{
                **edit_payload,
                "biography_markdown": "Still keeps a careful watch on every approach.",
            },
        },
        follow_redirects=False,
    )

    assert second_response.status_code == 302

    record = get_character("arden-march")
    assert record is not None
    assert record.definition.stats["armor_class"] == 18
    assert record.definition.stats["manual_adjustments"]["armor_class"] == 1


def test_native_character_edits_reconverge_imported_equipment_rows(
    app, client, sign_in, users, get_character, set_campaign_visibility, monkeypatch
):
    source_path = app.config["TEST_CAMPAIGNS_DIR"] / "_imports" / "zigzag-import.md"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        """
## Sheet Summary
| Field | Value |
| --- | --- |
| Sheet Name | Zigzag Blackscar |
| Class & Level | Fighter 1 |
| Species | Human |
| Background | Soldier |

## Defenses And Core Stats
| Metric | Value |
| --- | --- |
| Armor Class | 15 |
| Initiative | +2 |
| Speed | 30 ft. |
| Max HP | 12 |
| Proficiency Bonus | +2 |

## Ability Scores
| Ability | Score | Modifier | Save |
| --- | --- | --- | --- |
| Strength | 16 | +3 | +5 |
| Dexterity | 12 | +1 | +1 |
| Constitution | 14 | +2 | +4 |
| Intelligence | 10 | +0 | +0 |
| Wisdom | 12 | +1 | +1 |
| Charisma | 8 | -1 | -1 |

## Skills
| Skill | Bonus | Proficiency |
| --- | --- | --- |
| Athletics | +5 | Proficient |

## Proficiencies And Languages
- Languages: Common

## Attacks And Cantrips
| Attack | Hit | Damage | Notes |
| --- | --- | --- | --- |

## Features And Traits
### Fighter Features

- Second Wind - PHB 72

## Actions
### Actions
Attack

## Personality And Story

## Spellcasting
| Field | Value |
| --- | --- |
| Spellcasting Class |  |

## Equipment
| Item | Qty | Weight |
| --- | --- | --- |
| Crossbow Bolts | 1 | 1 lb. |
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(Config, "DB_PATH", app.config["DB_PATH"])
    project_root = Path(__file__).resolve().parents[1]
    import_character(
        project_root,
        "linden-pass",
        str(source_path),
        character_slug="zigzag-blackscar",
    )

    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / "zigzag-blackscar"
        / "definition.yaml"
    )
    payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    payload["equipment_catalog"].append(
        {
            "id": "crossbow-bolts-99",
            "name": "Crossbow Bolts (20)",
            "default_quantity": 2,
            "weight": "1 lb.",
            "notes": "",
            "tags": [],
        }
    )
    definition_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])

    record = get_character("zigzag-blackscar")
    assert record is not None

    response = client.post(
        "/campaigns/linden-pass/characters/zigzag-blackscar/edit",
        data={
            "expected_revision": record.state_record.revision,
            "languages_text": "Common",
            "armor_proficiencies_text": "",
            "weapon_proficiencies_text": "",
            "tool_proficiencies_text": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    record = get_character("zigzag-blackscar")
    assert record is not None
    assert record.import_metadata.import_status == "managed"
    assert len(record.definition.equipment_catalog) == 1
    assert record.definition.equipment_catalog[0]["name"] == "Crossbow Bolts"
    assert record.definition.equipment_catalog[0]["default_quantity"] == 3
