from __future__ import annotations

from copy import deepcopy
from html import unescape

import yaml

from player_wiki.character_presenter import present_character_detail
from player_wiki.character_models import CharacterDefinition
from player_wiki.xianxia_character_model import (
    derive_xianxia_difficulty_state_adjustments,
    derive_xianxia_honor_interaction_reminders,
    normalize_xianxia_state_payload,
)
from player_wiki.systems_service import XIANXIA_HOMEBREW_SOURCE_ID


def _write_campaign_config(app, mutator) -> None:
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    mutator(payload)
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with app.app_context():
        app.extensions["repository_store"].refresh()


def _configure_xianxia_campaign(app) -> None:
    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"
        payload["systems_sources"] = [
            {
                "source_id": XIANXIA_HOMEBREW_SOURCE_ID,
                "enabled": True,
                "default_visibility": "dm",
            }
        ]

    _write_campaign_config(app, _mutate)


def _systems_ref(entry) -> dict[str, str]:
    return {
        "library_slug": entry.library_slug,
        "source_id": entry.source_id,
        "entry_key": entry.entry_key,
        "slug": entry.slug,
        "title": entry.title,
        "entry_type": entry.entry_type,
    }


def _valid_xianxia_create_data(name: str = "Armored Crane") -> dict[str, str]:
    return {
        "name": name,
        "character_slug": "",
        "attribute_str": "3",
        "attribute_dex": "0",
        "attribute_con": "3",
        "attribute_int": "0",
        "attribute_wis": "0",
        "attribute_cha": "0",
        "effort_basic": "3",
        "effort_weapon": "1",
        "effort_guns_explosive": "0",
        "effort_magic": "1",
        "effort_ultimate": "0",
        "energy_jing": "1",
        "energy_qi": "1",
        "energy_shen": "1",
        "trained_skill_1": "Fishing",
        "trained_skill_2": "Calligraphy",
        "trained_skill_3": "Tea Ceremony",
        "martial_art_1_slug": "demons-fist",
        "martial_art_1_rank": "initiate",
        "martial_art_2_slug": "heavenly-palm",
        "martial_art_2_rank": "initiate",
        "martial_art_3_slug": "taoist-blade",
        "martial_art_3_rank": "initiate",
    }


def _write_raw_xianxia_character_definition(app, character_slug: str, definition_payload: dict) -> None:
    character_dir = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / character_slug
    )
    character_dir.mkdir(parents=True, exist_ok=True)
    (character_dir / "definition.yaml").write_text(
        yaml.safe_dump(definition_payload, sort_keys=False),
        encoding="utf-8",
    )
    (character_dir / "import.yaml").write_text(
        yaml.safe_dump(
            {
                "campaign_slug": "linden-pass",
                "character_slug": character_slug,
                "source_path": "test://xianxia-realm-actions",
                "imported_at_utc": "2026-04-26T00:00:00Z",
                "parser_version": "test",
                "import_status": "ok",
                "warnings": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _replace_character_state(app, record, state: dict) -> None:
    with app.app_context():
        app.extensions["character_state_store"].replace_state(
            record.definition,
            state,
            expected_revision=record.state_record.revision,
        )


def test_xianxia_read_presenter_context_collects_first_pass_sheet_facts(
    app,
    client,
    sign_in,
    users,
    get_character,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            **_valid_xianxia_create_data("Presenter Context Crane"),
            "manual_armor_bonus": "2",
            "dao_current": "2",
        },
        follow_redirects=False,
    )

    assert create_response.status_code == 302
    record = get_character("presenter-context-crane")
    assert record is not None

    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        character = present_character_detail(
            campaign,
            record,
            systems_service=app.extensions["systems_service"],
        )

    xianxia_read = character["xianxia_read"]
    assert [subpage["label"] for subpage in xianxia_read["subpages"]] == [
        "Quick Reference",
        "Martial Arts",
        "Techniques",
        "Resources",
        "Skills",
        "Equipment",
        "Inventory",
        "Personal",
        "Notes",
        "Controls",
    ]
    assert xianxia_read["identity"] == {
        "realm": "Mortal",
        "actions_per_turn": 2,
        "honor": "Honorable",
        "reputation": "Unknown",
    }
    assert xianxia_read["resources"]["durability"] == [
        {"key": "hp", "label": "HP", "current": 10, "max": 10, "temp": 0},
        {"key": "stance", "label": "Stance", "current": 10, "max": 10, "temp": 0},
    ]
    assert xianxia_read["resources"]["energies"] == [
        {"key": "jing", "label": "Jing", "current": 1, "max": 1},
        {"key": "qi", "label": "Qi", "current": 1, "max": 1},
        {"key": "shen", "label": "Shen", "current": 1, "max": 1},
    ]
    assert xianxia_read["resources"]["yin_yang"] == [
        {"key": "yin", "label": "Yin", "current": 1, "max": 1},
        {"key": "yang", "label": "Yang", "current": 1, "max": 1},
    ]
    assert xianxia_read["resources"]["dao"] == {"current": 2, "max": 3}
    assert xianxia_read["resources"]["insight"] == {"available": 0, "spent": 0}
    assert xianxia_read["attributes"][2] == {
        "key": "con",
        "label": "Constitution",
        "score": 3,
    }
    assert xianxia_read["efforts"][0] == {
        "key": "basic",
        "label": "Basic",
        "score": 3,
        "damage": "1d4 + Basic",
    }
    assert xianxia_read["skills"]["trained"] == [
        {"name": "Fishing"},
        {"name": "Calligraphy"},
        {"name": "Tea Ceremony"},
    ]
    assert xianxia_read["equipment"]["manual_armor_bonus"] == 2
    assert xianxia_read["equipment"]["defense"] == 15
    assert {
        "name": "Fishing rod, spear, or net",
        "reason": "Required for Fishing",
        "status": "",
        "type": "",
        "notes": "",
    } in xianxia_read["equipment"]["necessary_tools"]

    first_art = xianxia_read["martial_arts"][0]
    assert first_art["name"] == "Demon's Fist"
    assert first_art["href"] == "/campaigns/linden-pass/systems/entries/demons-fist"
    first_rank = first_art["learned_rank_refs"][0]
    assert first_rank["ref"] == "xianxia:demons-fist:initiate"
    assert first_rank["label"] == "Initiate"
    assert first_rank["href"] == (
        "/campaigns/linden-pass/systems/entries/demons-fist#xianxia-demons-fist-initiate"
    )
    assert first_rank["abilities"][0] == {
        "name": "Qi Fist Technique",
        "href": (
            "/campaigns/linden-pass/systems/entries/demons-fist"
            "#xianxia-demons-fist-initiate-qi-fist-technique"
        ),
        "ref": "xianxia:demons-fist:initiate:qi-fist-technique",
        "kind": "Technique",
        "support_label": "Reference only",
    }
    assert xianxia_read["basic_actions"][0]["title"] == "Recoup"
    assert xianxia_read["basic_actions"][0]["href"] == (
        "/campaigns/linden-pass/systems/entries/recoup"
    )
    assert xianxia_read["quick_reference"]["defense"]["value"] == 15
    assert xianxia_read["quick_reference"]["actions"]["actions_per_turn"] == 2
    assert character["spellcasting"] is None


def test_xianxia_read_sheet_uses_system_specific_subpages(
    client,
    sign_in,
    users,
    app,
    get_character,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            **_valid_xianxia_create_data("Subpage Crane"),
            "manual_armor_bonus": "2",
            "dao_current": "2",
        },
        follow_redirects=False,
    )

    assert create_response.status_code == 302
    with app.app_context():
        qi_blast = app.extensions["systems_service"].get_entry_by_slug_for_campaign(
            "linden-pass",
            "qi-blast",
        )
        assert qi_blast is not None
    record = get_character("subpage-crane")
    assert record is not None
    payload = record.definition.to_dict()
    payload["xianxia"]["generic_techniques"] = [
        {
            "name": "Qi Blast",
            "systems_ref": _systems_ref(qi_blast),
        }
    ]
    _write_raw_xianxia_character_definition(app, "subpage-crane", payload)

    quick_response = client.get("/campaigns/linden-pass/characters/subpage-crane?page=quick")

    assert quick_response.status_code == 200
    quick_html = unescape(quick_response.get_data(as_text=True))
    for page in (
        "quick",
        "martial_arts",
        "techniques",
        "resources",
        "skills",
        "equipment",
        "inventory",
        "personal",
        "notes",
        "controls",
    ):
        assert f"?page={page}" in quick_html
    assert "?page=features" not in quick_html
    assert "?page=spellcasting" not in quick_html
    assert "Features" not in quick_html
    assert "Spellcasting" not in quick_html

    spellcasting_response = client.get(
        "/campaigns/linden-pass/characters/subpage-crane?page=spellcasting"
    )
    assert spellcasting_response.status_code == 200
    spellcasting_html = unescape(spellcasting_response.get_data(as_text=True))
    assert "At a glance" in spellcasting_html
    assert "?page=spellcasting" not in spellcasting_html
    assert "/spellcasting/" not in spellcasting_html
    assert "Spell slots" not in spellcasting_html
    assert "Spellcasting" not in spellcasting_html

    martial_arts_response = client.get(
        "/campaigns/linden-pass/characters/subpage-crane?page=martial_arts"
    )
    assert martial_arts_response.status_code == 200
    martial_arts_html = unescape(martial_arts_response.get_data(as_text=True))
    assert "Martial Arts" in martial_arts_html
    assert "Demon's Fist" in martial_arts_html
    assert "Current rank: Initiate" in martial_arts_html
    assert "/campaigns/linden-pass/systems/entries/demons-fist#xianxia-demons-fist-initiate" in martial_arts_html
    assert "Qi Fist Technique" in martial_arts_html
    assert (
        "/campaigns/linden-pass/systems/entries/demons-fist"
        "#xianxia-demons-fist-initiate-qi-fist-technique"
    ) in martial_arts_html
    assert "Features and traits" not in martial_arts_html

    techniques_response = client.get(
        "/campaigns/linden-pass/characters/subpage-crane?page=techniques"
    )
    assert techniques_response.status_code == 200
    techniques_html = unescape(techniques_response.get_data(as_text=True))
    assert "Generic Techniques" in techniques_html
    assert "Qi Blast" in techniques_html
    assert "/campaigns/linden-pass/systems/entries/qi-blast" in techniques_html
    assert "Basic Actions" in techniques_html
    assert "/campaigns/linden-pass/systems/entries/recoup" in techniques_html
    assert "/campaigns/linden-pass/systems/entries/throat-jab" in techniques_html
    assert "Reference only" in techniques_html

    resources_response = client.get(
        "/campaigns/linden-pass/characters/subpage-crane?page=resources"
    )
    assert resources_response.status_code == 200
    resources_html = unescape(resources_response.get_data(as_text=True))
    assert "Resources" in resources_html
    assert "HP" in resources_html
    assert "Stance" in resources_html
    assert "Jing" in resources_html
    assert "Yin" in resources_html
    assert "Dao" in resources_html
    assert "Insight" in resources_html
    assert "No active Stance recorded" in resources_html

    skills_response = client.get("/campaigns/linden-pass/characters/subpage-crane?page=skills")
    assert skills_response.status_code == 200
    skills_html = unescape(skills_response.get_data(as_text=True))
    assert "Fishing" in skills_html
    assert "Calligraphy" in skills_html
    assert "Tea Ceremony" in skills_html
    assert "Skill use guardrails" in skills_html

    equipment_response = client.get(
        "/campaigns/linden-pass/characters/subpage-crane?page=equipment"
    )
    assert equipment_response.status_code == 200
    equipment_html = unescape(equipment_response.get_data(as_text=True))
    assert "Manual armor bonus: 2" in equipment_html
    assert "Formula: 10 + 2 + 3" in equipment_html
    assert "Necessary weapons" in equipment_html
    assert "Necessary tools" in equipment_html
    assert "Fishing rod, spear, or net" in equipment_html
    assert "Attuned items" not in equipment_html

    inventory_response = client.get(
        "/campaigns/linden-pass/characters/subpage-crane?page=inventory"
    )
    assert inventory_response.status_code == 200
    inventory_html = unescape(inventory_response.get_data(as_text=True))
    assert "Inventory" in inventory_html
    assert "No inventory quantities are recorded on this sheet yet." in inventory_html
    assert "Currency" not in inventory_html

    controls_response = client.get(
        "/campaigns/linden-pass/characters/subpage-crane?page=controls"
    )
    assert controls_response.status_code == 200
    controls_html = unescape(controls_response.get_data(as_text=True))
    assert "Player controls" in controls_html
    assert "Current owner" in controls_html


def test_xianxia_quick_reference_presents_derived_defense(
    app,
    client,
    sign_in,
    users,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={**_valid_xianxia_create_data(), "manual_armor_bonus": "2"},
        follow_redirects=False,
    )

    assert create_response.status_code == 302
    assert create_response.headers["Location"].endswith(
        "/campaigns/linden-pass/characters/armored-crane"
    )

    sheet_response = client.get("/campaigns/linden-pass/characters/armored-crane?page=quick")

    assert sheet_response.status_code == 200
    html = unescape(sheet_response.get_data(as_text=True))
    assert "Check formula" in html
    assert "1d20 + Attribute + Realm modifier + situational modifiers" in html
    assert "+1d6" in html
    assert "per spent Energy/Yin/Yang point" in html
    assert (
        "Check formula = 1d20 + Attribute + Realm modifier + situational modifiers, "
        "plus +1d6 per spent Energy/Yin/Yang point."
    ) in html
    assert "Difficulty states" in html
    assert "Difficulty states = EASY -3, Normal 0, HARD +3." in html
    assert "Final DC adjustment" in html
    assert "<strong>-3</strong>" in html
    assert "<strong>0</strong>" in html
    assert "<strong>+3</strong>" in html
    assert "Resolve EASY/HARD influences to one final DC state" in html
    assert "Action count" in html
    assert "Actions per turn" in html
    assert "Actions per turn = Mortal -> 2 actions per turn" in html
    assert "Defense calculation" in html
    assert "Manual armor bonus" in html
    assert "Constitution" in html
    assert "Defense = 10 + 2 + 3" in html
    assert "<strong>15</strong>" in html
    assert "Effort damage" in html
    assert "1d4 + Basic" in html
    assert "1d6 + Weapon" in html
    assert "1d8 + Guns/Explosive" in html
    assert "1d10 + Magic" in html
    assert "1d12 + Ultimate" in html
    assert "Score 3" in html
    assert "Armor Class" not in html


def test_xianxia_quick_reference_derives_actions_from_realm_not_stored_value(
    app,
    client,
    sign_in,
    users,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    _write_raw_xianxia_character_definition(
        app,
        "divine-stale-actions",
        {
            "campaign_slug": "linden-pass",
            "character_slug": "divine-stale-actions",
            "name": "Divine Stale Actions",
            "status": "active",
            "system": "Xianxia",
            "xianxia": {
                "realm": "Divine",
                "actions_per_turn": 2,
                "attributes": {
                    "str": 0,
                    "dex": 0,
                    "con": 2,
                    "int": 0,
                    "wis": 0,
                    "cha": 0,
                },
                "durability": {"manual_armor_bonus": 1},
            },
        },
    )

    sheet_response = client.get("/campaigns/linden-pass/characters/divine-stale-actions?page=quick")

    assert sheet_response.status_code == 200
    html = unescape(sheet_response.get_data(as_text=True))
    assert "Action count" in html
    assert "Actions per turn = Divine -> 4 actions per turn" in html
    assert "<strong>Divine</strong>" in html
    assert "<strong>4</strong>" in html


def test_xianxia_difficulty_state_helper_presents_capped_final_dc_states():
    presentation = derive_xianxia_difficulty_state_adjustments()

    assert presentation["summary"] == "EASY -3, Normal 0, HARD +3"
    assert presentation["states"] == [
        {"key": "easy", "label": "EASY", "adjustment": -3, "adjustment_label": "-3"},
        {"key": "normal", "label": "Normal", "adjustment": 0, "adjustment_label": "0"},
        {"key": "hard", "label": "HARD", "adjustment": 3, "adjustment_label": "+3"},
    ]


def test_xianxia_state_normalizer_clamps_current_pools_without_resetting_reference_state():
    definition = CharacterDefinition.from_dict(
        {
            "campaign_slug": "linden-pass",
            "character_slug": "clamp-sage",
            "name": "Clamp Sage",
            "status": "active",
            "system": "Xianxia",
            "xianxia": {
                "energy_maxima": {"jing": 2, "qi": 1, "shen": 0},
                "yin_yang": {"yin_max": 1, "yang_max": 3},
                "dao_max": 3,
                "durability": {"hp_max": 10, "stance_max": 8},
            },
        }
    )

    state = normalize_xianxia_state_payload(
        definition,
        {
            "vitals": {
                "current_hp": "99",
                "temp_hp": "99",
                "current_stance": "22",
                "temp_stance": "77",
            },
            "energies": {
                "jing": {"current": "9"},
                "qi": {"current": "-1"},
                "shen": {"current": "6"},
            },
            "yin_yang": {"yin_current": "7", "yang_current": "-2"},
            "dao": {"current": "8"},
            "active_stance": {"name": "Stone Root"},
            "active_aura": {"name": "Azure Bell", "systems_ref": {"slug": "azure-bell"}},
            "inventory": {
                "enabled": True,
                "quantities": [{"id": "spirit-rice", "name": "Spirit rice", "quantity": 2}],
            },
            "notes": {"player_notes_markdown": "Track recovery blockers manually."},
        },
    )

    assert state["vitals"] == {
        "current_hp": 10,
        "temp_hp": 99,
        "current_stance": 8,
        "temp_stance": 77,
    }
    assert state["energies"] == {
        "jing": {"current": 2},
        "qi": {"current": 0},
        "shen": {"current": 0},
    }
    assert state["yin_yang"] == {"yin_current": 1, "yang_current": 0}
    assert state["dao"] == {"current": 3}
    assert state["active_stance"] == {"name": "Stone Root"}
    assert state["active_aura"] == {"name": "Azure Bell", "systems_ref": {"slug": "azure-bell"}}
    assert state["inventory"] == {
        "enabled": True,
        "quantities": [{"id": "spirit-rice", "name": "Spirit rice", "quantity": 2}],
    }
    assert state["notes"] == {"player_notes_markdown": "Track recovery blockers manually."}


def test_xianxia_honor_interaction_helper_presents_directional_contexts():
    majestic = derive_xianxia_honor_interaction_reminders("Majestic")
    assert majestic["honor"] == "Majestic"
    assert majestic["summary"] == (
        "Orthodox sects and individuals +5, Demonic backgrounds -5, "
        "Criminal backgrounds -5"
    )
    assert [
        (context["key"], context["modifier_label"])
        for context in majestic["contexts"]
    ] == [
        ("orthodox", "+5"),
        ("demonic", "-5"),
        ("criminal", "-5"),
    ]

    demonic = derive_xianxia_honor_interaction_reminders("demonic")
    assert demonic["honor"] == "Demonic"
    assert [
        (context["key"], context["modifier_label"])
        for context in demonic["contexts"]
    ] == [
        ("orthodox", "-5"),
        ("demonic", "+5"),
        ("criminal", "+5"),
    ]

    venerable = derive_xianxia_honor_interaction_reminders("Venerable")
    assert [
        (context["key"], context["modifier_label"])
        for context in venerable["contexts"]
    ] == [
        ("orthodox", "+3"),
        ("demonic", "-3"),
        ("criminal", "-3"),
    ]

    disgraced = derive_xianxia_honor_interaction_reminders("Disgraced")
    assert [
        (context["key"], context["modifier_label"])
        for context in disgraced["contexts"]
    ] == [
        ("orthodox", "-3"),
        ("demonic", "+3"),
        ("criminal", "+3"),
    ]

    honorable = derive_xianxia_honor_interaction_reminders("Honorable")
    assert {context["modifier_label"] for context in honorable["contexts"]} == {"0"}


def test_xianxia_dao_persists_across_session_surface_saves_and_rests(
    app,
    client,
    sign_in,
    users,
    get_character,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={**_valid_xianxia_create_data("Dao Keeper"), "dao_current": "2"},
        follow_redirects=False,
    )

    assert create_response.status_code == 302

    record = get_character("dao-keeper")
    assert record is not None
    assert record.state_record.state["xianxia"]["dao"] == {"current": 2}

    session_response = client.get(
        "/campaigns/linden-pass/session/character?character=dao-keeper&page=quick"
    )

    assert session_response.status_code == 200
    record_after_session_read = get_character("dao-keeper")
    assert record_after_session_read.state_record.revision == record.state_record.revision
    assert record_after_session_read.state_record.state["xianxia"]["dao"] == {"current": 2}

    vitals_response = client.post(
        "/campaigns/linden-pass/characters/dao-keeper/session/vitals",
        data={
            "expected_revision": record_after_session_read.state_record.revision,
            "current_hp": "7",
            "temp_hp": "1",
        },
        follow_redirects=False,
    )

    assert vitals_response.status_code == 302
    record_after_vitals = get_character("dao-keeper")
    assert record_after_vitals.state_record.state["vitals"] == {"current_hp": 7, "temp_hp": 1}
    assert record_after_vitals.state_record.state["xianxia"]["vitals"]["current_hp"] == 7
    assert record_after_vitals.state_record.state["xianxia"]["dao"] == {"current": 2}

    for rest_type in ("short", "long"):
        rest_response = client.post(
            f"/campaigns/linden-pass/characters/dao-keeper/session/rest/{rest_type}",
            data={
                "expected_revision": record_after_vitals.state_record.revision,
                "confirm_rest": "1",
            },
            follow_redirects=False,
        )

        assert rest_response.status_code == 302
        record_after_vitals = get_character("dao-keeper")
        assert record_after_vitals.state_record.state["xianxia"]["dao"] == {"current": 2}


def test_xianxia_one_day_rest_recovers_mutable_pools_and_preserves_dao(
    app,
    client,
    sign_in,
    users,
    get_character,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={**_valid_xianxia_create_data("Resting Crane"), "dao_current": "2"},
        follow_redirects=False,
    )

    assert create_response.status_code == 302
    record = get_character("resting-crane")
    assert record is not None

    depleted_state = deepcopy(record.state_record.state)
    depleted_state["vitals"] = {"current_hp": 4, "temp_hp": 2}
    depleted_state["xianxia"]["vitals"] = {
        "current_hp": 4,
        "temp_hp": 2,
        "current_stance": 3,
        "temp_stance": 5,
    }
    depleted_state["xianxia"]["energies"] = {
        "jing": {"current": 0},
        "qi": {"current": 0},
        "shen": {"current": 0},
    }
    depleted_state["xianxia"]["yin_yang"] = {"yin_current": 0, "yang_current": 0}
    depleted_state["xianxia"]["dao"] = {"current": 2}
    _replace_character_state(app, record, depleted_state)

    depleted_record = get_character("resting-crane")
    assert depleted_record is not None

    with app.app_context():
        preview = app.extensions["character_state_service"].preview_rest(depleted_record, "long")
    preview_changes = {
        change.label: (change.from_value, change.to_value)
        for change in preview.changes
    }

    assert preview_changes == {
        "HP": ("4 / 10", "10 / 10"),
        "Stance": ("3 / 10", "10 / 10"),
        "Jing Energy": ("0 / 1", "1 / 1"),
        "Qi Energy": ("0 / 1", "1 / 1"),
        "Shen Energy": ("0 / 1", "1 / 1"),
        "Yin": ("0 / 1", "1 / 1"),
        "Yang": ("0 / 1", "1 / 1"),
    }

    rest_response = client.post(
        "/campaigns/linden-pass/characters/resting-crane/session/rest/long",
        data={
            "expected_revision": depleted_record.state_record.revision,
            "confirm_rest": "1",
        },
        follow_redirects=False,
    )

    assert rest_response.status_code == 302
    rested_record = get_character("resting-crane")
    rested_state = rested_record.state_record.state
    assert rested_state["vitals"] == {"current_hp": 10, "temp_hp": 2}
    assert rested_state["xianxia"]["vitals"] == {
        "current_hp": 10,
        "temp_hp": 2,
        "current_stance": 10,
        "temp_stance": 5,
    }
    assert rested_state["xianxia"]["energies"] == {
        "jing": {"current": 1},
        "qi": {"current": 1},
        "shen": {"current": 1},
    }
    assert rested_state["xianxia"]["yin_yang"] == {"yin_current": 1, "yang_current": 1}
    assert rested_state["xianxia"]["dao"] == {"current": 2}


def test_xianxia_quick_reference_displays_stance_break_only_at_zero_stance(
    app,
    client,
    sign_in,
    users,
    get_character,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("Broken Stance"),
        follow_redirects=False,
    )

    assert create_response.status_code == 302

    normal_response = client.get("/campaigns/linden-pass/characters/broken-stance?page=quick")

    assert normal_response.status_code == 200
    normal_html = unescape(normal_response.get_data(as_text=True))
    assert "Stance Break" not in normal_html

    record = get_character("broken-stance")
    assert record is not None
    broken_state = deepcopy(record.state_record.state)
    broken_state["xianxia"]["vitals"]["current_stance"] = 0
    _replace_character_state(app, record, broken_state)

    broken_response = client.get("/campaigns/linden-pass/characters/broken-stance?page=quick")

    assert broken_response.status_code == 200
    broken_html = unescape(broken_response.get_data(as_text=True))
    assert "Stance Break" in broken_html
    assert "Current Stance 0" in broken_html
    assert "/campaigns/linden-pass/systems/entries/stance" in broken_html
    assert "When current Stance reaches 0, the character's Stance breaks." in broken_html
    assert "Stance recovers with one day of rest unless another effect prevents recovery." in broken_html


def test_xianxia_quick_reference_displays_honor_interaction_reminders(
    app,
    client,
    sign_in,
    users,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    _write_raw_xianxia_character_definition(
        app,
        "majestic-honor",
        {
            "campaign_slug": "linden-pass",
            "character_slug": "majestic-honor",
            "name": "Majestic Honor",
            "status": "active",
            "system": "Xianxia",
            "xianxia": {
                "honor": "Majestic",
                "attributes": {
                    "str": 0,
                    "dex": 0,
                    "con": 0,
                    "int": 0,
                    "wis": 0,
                    "cha": 0,
                },
            },
        },
    )

    response = client.get("/campaigns/linden-pass/characters/majestic-honor?page=quick")

    assert response.status_code == 200
    html = unescape(response.get_data(as_text=True))
    assert "Honor interactions" in html
    assert "Current Honor: Majestic" in html
    assert "/campaigns/linden-pass/systems/entries/honor" in html
    assert "Orthodox sects and individuals" in html
    assert "Demonic backgrounds" in html
    assert "Criminal backgrounds" in html
    assert "<strong>+5</strong>" in html
    assert html.count("<strong>-5</strong>") >= 2
    assert (
        "Venerable and Majestic grant +3 and +5 with orthodox sects and individuals."
        in html
    )
    assert (
        "Disgraced and Demonic grant +3 and +5 with demonic or criminal backgrounds."
        in html
    )
    assert (
        "When dealing with the opposite Honor alignment, the same value applies as a penalty."
        in html
    )
    assert (
        "Honor interactions = Orthodox sects and individuals +5, Demonic backgrounds -5, "
        "Criminal backgrounds -5."
    ) in html


def test_xianxia_quick_reference_displays_skill_use_guardrails(
    app,
    client,
    sign_in,
    users,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("Guarded Skill"),
        follow_redirects=False,
    )

    assert create_response.status_code == 302

    response = client.get("/campaigns/linden-pass/characters/guarded-skill?page=quick")

    assert response.status_code == 200
    html = unescape(response.get_data(as_text=True))
    assert "Skill use guardrails" in html
    assert "/campaigns/linden-pass/systems/entries/skills" in html
    assert "Skills rule" in html
    assert "Skills cannot be used in active battle to affect Attacks or Damage." in html
    assert "Skills can affect surroundings or pre-battle preparation when the GM agrees." in html


def test_xianxia_quick_reference_displays_rules_text_references(
    app,
    client,
    sign_in,
    users,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("Reference Scholar"),
        follow_redirects=False,
    )

    assert create_response.status_code == 302

    response = client.get("/campaigns/linden-pass/characters/reference-scholar?page=quick")

    assert response.status_code == 200
    html = unescape(response.get_data(as_text=True))
    assert "Rules text references" in html
    assert "/campaigns/linden-pass/systems/entries/ranges-and-distance" in html
    assert "/campaigns/linden-pass/systems/entries/timing-and-initiative" in html
    assert "/campaigns/linden-pass/systems/entries/critical-hits" in html
    assert "/campaigns/linden-pass/systems/entries/sneak-attacks" in html
    assert "/campaigns/linden-pass/systems/entries/minions" in html
    assert "/campaigns/linden-pass/systems/entries/companion-derivation" in html
    assert "Touch requires physical contact through a Melee Attack." in html
    assert "Close means within 5 feet, adjacent, or dueling." in html
    assert "Once-per-combat means once per combat encounter." in html
    assert (
        "Critical Hits automatically hit and deal additional +Ultimate Effort damage."
        in html
    )
    assert (
        "Sneak Attack only occurs under specific circumstances, such as a Martial Art "
        "or Technique explicitly enabling it or the target being completely off guard."
    ) in html
    assert (
        "Minions are NPCs whose Realm and HP/Stance are lower than the player characters"
        in html
    )
    assert (
        "Companions usually use half the user's Stats plus any listed modifications"
        in html
    )
    assert "Richer companion automation is deferred." in html
    assert "Reference only" in html


def test_xianxia_quick_reference_displays_active_stance_and_aura_reminders_without_state_automation(
    app,
    client,
    sign_in,
    users,
    get_character,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("Active Crane"),
        follow_redirects=False,
    )

    assert create_response.status_code == 302

    record = get_character("active-crane")
    assert record is not None
    active_state = deepcopy(record.state_record.state)
    active_state["xianxia"]["active_stance"] = {"name": "Stone Root"}
    active_state["xianxia"]["active_aura"] = {
        "name": "Azure Bell",
        "systems_ref": {"slug": "azure-bell"},
    }
    _replace_character_state(app, record, active_state)

    active_record = get_character("active-crane")
    assert active_record is not None
    response = client.get("/campaigns/linden-pass/characters/active-crane?page=quick")

    assert response.status_code == 200
    html = unescape(response.get_data(as_text=True))
    assert "Active Stance and Aura" in html
    assert "Stance Activation Rules" in html
    assert "Active Stance: Stone Root" in html
    assert "/campaigns/linden-pass/systems/entries/stance-activation-rules" in html
    assert "A character can have only one Stance active at a time." in html
    assert "Entering a Stance costs an Action plus any Stance-specific costs." in html
    assert "A Stance ends when the character switches Stances." in html
    assert "Aura Activation Rules" in html
    assert "Active Aura: Azure Bell" in html
    assert "/campaigns/linden-pass/systems/entries/aura-activation-rules" in html
    assert "A character can have only one Aura active at a time." in html
    assert (
        "Auras are assumed to remain active once activated unless the Aura says otherwise "
        "or the GM overrules it."
    ) in html
    assert "Reference only" in html

    after_read = get_character("active-crane")
    assert after_read.state_record.revision == active_record.state_record.revision
    assert after_read.state_record.state["xianxia"]["active_stance"] == {"name": "Stone Root"}
    assert after_read.state_record.state["xianxia"]["active_aura"] == {
        "name": "Azure Bell",
        "systems_ref": {"slug": "azure-bell"},
    }
