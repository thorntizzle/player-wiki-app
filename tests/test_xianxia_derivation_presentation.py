from __future__ import annotations

from copy import deepcopy
import re
from html import unescape

import pytest
import yaml

from player_wiki.auth_store import AuthStore
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


def _html_section(html: str, heading: str) -> str:
    start = html.index(heading)
    end = html.index("</article>", start)
    return html[start:end]


def _create_assigned_xianxia_session_character(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    *,
    character_slug: str,
    name: str,
) -> None:
    _configure_xianxia_campaign(app)
    set_campaign_visibility("linden-pass", characters="public", session="public")
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            **_valid_xianxia_create_data(name),
            "character_slug": character_slug,
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    with app.app_context():
        AuthStore().upsert_character_assignment(
            users["owner"]["id"],
            "linden-pass",
            character_slug,
        )

    session_response = client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    assert session_response.status_code == 302


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
    expected_tool = {
        "name": "Fishing rod, spear, or net",
        "reason": "Required for Fishing",
        "status": "",
        "type": "",
        "notes": "",
    }
    assert any(
        all(tool.get(key) == value for key, value in expected_tool.items())
        for tool in xianxia_read["equipment"]["necessary_tools"]
    )

    first_art = xianxia_read["martial_arts"][0]
    assert first_art["name"] == "Demon's Fist"
    assert first_art["href"] == "/campaigns/linden-pass/systems/entries/demons-fist"
    first_rank = first_art["learned_rank_refs"][0]
    assert first_rank["ref"] == "xianxia:demons-fist:initiate"
    assert first_rank["label"] == "Initiate"
    assert first_rank["href"] == (
        "/campaigns/linden-pass/systems/entries/demons-fist#xianxia-demons-fist-initiate"
    )
    first_ability = first_rank["abilities"][0]
    assert first_ability["name"] == "Qi Fist Technique"
    assert (
        first_ability["href"]
        == "/campaigns/linden-pass/systems/entries/demons-fist"
           "#xianxia-demons-fist-initiate-qi-fist-technique"
    )
    assert first_ability["ref"] == "xianxia:demons-fist:initiate:qi-fist-technique"
    assert first_ability["source_ref"] == first_ability["ref"]
    assert first_ability["kind"] == "Technique"
    assert first_ability["support_label"] == "Reference only"
    assert first_ability["rank_label"] == "Initiate"
    assert first_ability["resource_cost_text"] == "qi 1"
    assert first_ability["range_text"] == "self"
    assert first_ability["damage_effort_text"] == "weapon effort damage"
    assert first_ability["duration_text"] == "rest of combat"
    assert first_art["rank_progress"]["summary"] == "Rank progress: 1 / 5 ranks learned."
    assert [
        (rank["label"], rank["status_label"])
        for rank in first_art["rank_progress"]["steps"]
    ] == [
        ("Initiate", "Current"),
        ("Novice", "Unlearned"),
        ("Apprentice", "Unlearned"),
        ("Master", "Unlearned"),
        ("Legendary", "Unlearned"),
    ]
    assert xianxia_read["basic_actions"][0]["title"] == "Recoup"
    assert xianxia_read["basic_actions"][0]["href"] == (
        "/campaigns/linden-pass/systems/entries/recoup"
    )
    assert xianxia_read["quick_reference"]["defense"]["value"] == 15
    assert xianxia_read["quick_reference"]["actions"]["actions_per_turn"] == 2
    assert character["spellcasting"] is None


def test_xianxia_techniques_page_shows_approval_status_records(
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
        data=_valid_xianxia_create_data("Approval Crane"),
        follow_redirects=False,
    )

    assert create_response.status_code == 302
    record = get_character("approval-crane")
    assert record is not None
    payload = record.definition.to_dict()
    payload["xianxia"]["variants"] = [
        {
            "variant_type": "karmic_constraint",
            "name": "Falling Palm Oath",
            "approval_status": "approved",
            "approval_notes": "Approved for the Heavenly Palm initiate technique.",
            "approved_at": "2026-04-25T19:30:00-04:00",
        },
        {
            "type": "Karmic Constraint",
            "name": "Mountain-Crossing Oath",
        },
        {
            "variant_type": "ascendant_art",
            "name": "Skyfire Crown",
            "status": "pending",
            "notes": "Awaiting sect elder review.",
        },
        {
            "type": "Ascendant Art",
            "name": "Starfall Halo",
        },
    ]
    payload["xianxia"]["approval_requests"] = [
        {
            "request_type": "ascendant_art",
            "name": "Cloud-Splitting Revision",
            "status": "rejected",
            "gm_approval_notes": "Too broad for this rank.",
            "gm_reviewed_at": "2026-04-26 09:15",
        }
    ]
    payload["xianxia"]["dao_immolating_techniques"]["use_history"] = [
        {
            "name": "River-Cleaving Spark",
            "approval_status": "approved",
            "approval_notes": "Spent after the duel began.",
            "approval_timestamp": "2026-04-26T10:00:00-04:00",
        },
        {
            "name": "Unspoken Furnace Vow",
        }
    ]
    _write_raw_xianxia_character_definition(app, "approval-crane", payload)
    record = get_character("approval-crane")
    assert record is not None

    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        character = present_character_detail(
            campaign,
            record,
            systems_service=app.extensions["systems_service"],
        )

    approval_groups = character["xianxia_read"]["approval"]["status_groups"]
    assert [(group["title"], [record["status_label"] for record in group["records"]]) for group in approval_groups] == [
        ("Karmic Constraints", ["Approved", "Pending"]),
        ("Ascendant Arts", ["Pending", "Pending", "Rejected"]),
        ("Dao Immolating Technique Use Records", ["Approved", "Pending"]),
    ]
    assert approval_groups[0]["records"][0]["notes"] == "Approved for the Heavenly Palm initiate technique."
    assert approval_groups[0]["records"][0]["approval_timestamp"] == "2026-04-25T19:30:00-04:00"
    assert approval_groups[1]["records"][2]["notes"] == "Too broad for this rank."
    assert approval_groups[1]["records"][2]["approval_timestamp"] == "2026-04-26 09:15"
    assert approval_groups[2]["records"][0]["approval_timestamp"] == "2026-04-26T10:00:00-04:00"

    response = client.get("/campaigns/linden-pass/characters/approval-crane?page=techniques")

    assert response.status_code == 200
    html = unescape(response.get_data(as_text=True))
    assert "Karmic Constraints" in html
    assert "Falling Palm Oath" in html
    assert "Approved for the Heavenly Palm initiate technique." in html
    assert "Approval timestamp: 2026-04-25T19:30:00-04:00" in html
    assert "Mountain-Crossing Oath" in html
    assert "Approval state: Approved" in html
    assert "approval-state-badge--approved" in html
    assert "Karmic Constraint" in html
    assert "Variant" in html
    assert "Ascendant Arts" in html
    assert "Skyfire Crown" in html
    assert "Starfall Halo" in html
    assert "Approval state: Pending" in html
    assert "approval-state-badge--pending" in html
    assert "Cloud-Splitting Revision" in html
    assert "Too broad for this rank." in html
    assert "Approval timestamp: 2026-04-26 09:15" in html
    assert "Approval state: Rejected" in html
    assert "approval-state-badge--rejected" in html
    assert "Dao Immolating Technique Use Records" in html
    assert "River-Cleaving Spark" in html
    assert "Spent after the duel began." in html
    assert "Approval timestamp: 2026-04-26T10:00:00-04:00" in html
    assert "Unspoken Furnace Vow" in html
    assert "Dao Immolating Technique Use" in html
    assert "Use record" in html
    assert "Prepared Dao Immolating Techniques" in html


def test_xianxia_unapproved_variants_remain_approval_records_not_usable_modeled_abilities(
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
        data=_valid_xianxia_create_data("Unapproved Variant Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    with app.app_context():
        qi_blast = app.extensions["systems_service"].get_entry_by_slug_for_campaign(
            "linden-pass",
            "qi-blast",
        )
        assert qi_blast is not None

    record = get_character("unapproved-variant-crane")
    assert record is not None
    payload = record.definition.to_dict()
    payload["xianxia"]["generic_techniques"] = []
    payload["xianxia"]["variants"] = [
        {
            "variant_type": "karmic_constraint",
            "name": "Unapproved Falling Palm Variant",
            "approval_status": "pending",
            "systems_ref": _systems_ref(qi_blast),
            "ability_ref": "xianxia:demons-fist:initiate:qi-fist-technique",
            "support_state": "modeled",
            "modeled_effects": ["extra-damage"],
        },
        {
            "variant_type": "ascendant_art",
            "name": "Rejected Skyfire Crown",
            "approval_status": "rejected",
            "systems_ref": _systems_ref(qi_blast),
            "support_state": "modeled",
            "modeled_effects": ["range-extension"],
        },
    ]
    _write_raw_xianxia_character_definition(app, "unapproved-variant-crane", payload)
    record = get_character("unapproved-variant-crane")
    assert record is not None

    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        character = present_character_detail(
            campaign,
            record,
            systems_service=app.extensions["systems_service"],
        )

    xianxia_read = character["xianxia_read"]
    variant_names = {"Unapproved Falling Palm Variant", "Rejected Skyfire Crown"}
    assert xianxia_read["generic_techniques"] == []
    rank_ability_names = {
        ability["name"]
        for martial_art in xianxia_read["martial_arts"]
        for rank_ref in martial_art["learned_rank_refs"]
        for ability in rank_ref["abilities"]
    }
    assert "Qi Fist Technique" in rank_ability_names
    assert rank_ability_names.isdisjoint(variant_names)
    approval_names = {
        approval_record["name"]
        for group in xianxia_read["approval"]["status_groups"]
        for approval_record in group["records"]
    }
    assert variant_names <= approval_names

    techniques_response = client.get(
        "/campaigns/linden-pass/characters/unapproved-variant-crane?page=techniques"
    )
    assert techniques_response.status_code == 200
    techniques_html = unescape(techniques_response.get_data(as_text=True))
    known_generic_section = _html_section(techniques_html, "Known Generic Techniques")
    assert "No Generic Techniques are recorded on this sheet yet." in known_generic_section
    assert "Qi Blast" not in known_generic_section
    for variant_name in variant_names:
        assert variant_name not in known_generic_section
        assert variant_name in techniques_html
    assert "Approval state: Pending" in techniques_html
    assert "Approval state: Rejected" in techniques_html

    martial_arts_response = client.get(
        "/campaigns/linden-pass/characters/unapproved-variant-crane?page=martial_arts"
    )
    assert martial_arts_response.status_code == 200
    martial_arts_html = unescape(martial_arts_response.get_data(as_text=True))
    assert "Qi Fist Technique" in martial_arts_html
    for variant_name in variant_names:
        assert variant_name not in martial_arts_html

    session_response = client.get(
        "/campaigns/linden-pass/session/character?character=unapproved-variant-crane&page=techniques"
    )
    assert session_response.status_code == 200
    session_html = unescape(session_response.get_data(as_text=True))
    session_generic_section = _html_section(session_html, "Known Generic Techniques")
    assert "No Generic Techniques are recorded on this sheet yet." in session_generic_section
    for variant_name in variant_names:
        assert variant_name not in session_generic_section
        assert variant_name in session_html


def test_xianxia_techniques_page_records_ad_hoc_dao_immolating_use_request(
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
        data=_valid_xianxia_create_data("Request Crane"),
        follow_redirects=False,
    )

    assert create_response.status_code == 302
    record = get_character("request-crane")
    assert record is not None
    edit_response = client.get(
        "/campaigns/linden-pass/characters/request-crane?mode=session&page=techniques"
    )
    edit_html = unescape(edit_response.get_data(as_text=True))
    assert edit_response.status_code == 200
    assert "Ad Hoc Dao Immolating Use Request" in edit_html
    assert "dao_immolating_request_name" in edit_html

    response = client.post(
        "/campaigns/linden-pass/characters/request-crane/xianxia/dao-immolating-use-requests",
        data={
            "expected_revision": record.state_record.revision,
            "mode": "session",
            "page": "techniques",
            "dao_immolating_request_name": "Lotus-Burning Last Word",
            "dao_immolating_request_notes": "Invented at the duel's turning point.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "page=techniques" in response.headers["Location"]
    assert "mode=session" in response.headers["Location"]
    assert "xianxia-dao-immolating-use-request" in response.headers["Location"]
    updated = get_character("request-crane")
    assert updated is not None
    xianxia = updated.definition.to_dict()["xianxia"]
    assert xianxia["dao_immolating_techniques"]["use_history"] == [
        {
            "name": "Lotus-Burning Last Word",
            "request_type": "dao_immolating_use",
            "request_source": "ad_hoc",
            "approval_required": True,
            "approval_status": "pending",
            "insight_cost": 10,
            "one_use": True,
            "notes": "Invented at the duel's turning point.",
        }
    ]
    assert xianxia["dao_immolating_techniques"]["prepared"] == []
    assert xianxia["insight"] == {"available": 0, "spent": 0}
    assert xianxia["advancement_history"] == []

    sheet_response = client.get(
        "/campaigns/linden-pass/characters/request-crane?mode=session&page=techniques"
    )
    html = unescape(sheet_response.get_data(as_text=True))
    assert "Lotus-Burning Last Word" in html
    assert "Pending" in html
    assert "Dao Immolating Technique Use" in html
    assert "Invented at the duel's turning point." in html
    assert "Insight cost: 10" in html
    assert "One-use history: not recorded yet" in html


def test_xianxia_techniques_page_uses_prepared_dao_immolating_reference_without_requiring_it(
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
        data=_valid_xianxia_create_data("Prepared Request Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    record = get_character("prepared-request-crane")
    assert record is not None
    payload = record.definition.to_dict()
    payload["xianxia"]["dao_immolating_techniques"]["prepared"] = [
        {
            "name": "Dawn Ash Mercy",
            "notes": "Prepared review context for the GM.",
        }
    ]
    _write_raw_xianxia_character_definition(app, "prepared-request-crane", payload)
    record = get_character("prepared-request-crane")
    assert record is not None

    edit_response = client.get(
        "/campaigns/linden-pass/characters/prepared-request-crane?mode=session&page=techniques"
    )
    assert edit_response.status_code == 200
    edit_html = unescape(edit_response.get_data(as_text=True))
    assert "Prepared note" in edit_html
    assert 'name="dao_immolating_prepared_index"' in edit_html
    assert '<option value="0">Dawn Ash Mercy</option>' in edit_html

    response = client.post(
        "/campaigns/linden-pass/characters/prepared-request-crane/xianxia/dao-immolating-use-requests",
        data={
            "expected_revision": record.state_record.revision,
            "mode": "session",
            "page": "techniques",
            "dao_immolating_request_name": "",
            "dao_immolating_prepared_index": "0",
            "dao_immolating_request_notes": "Requesting the prepared vow at the table.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    updated = get_character("prepared-request-crane")
    assert updated is not None
    xianxia = updated.definition.to_dict()["xianxia"]
    assert xianxia["dao_immolating_techniques"]["prepared"] == [
        {
            "name": "Dawn Ash Mercy",
            "notes": "Prepared review context for the GM.",
        }
    ]
    assert xianxia["dao_immolating_techniques"]["use_history"] == [
        {
            "name": "Dawn Ash Mercy",
            "request_type": "dao_immolating_use",
            "request_source": "prepared_record",
            "approval_required": True,
            "approval_status": "pending",
            "notes": "Requesting the prepared vow at the table.",
            "prepared_record_index": 0,
            "prepared_record_name": "Dawn Ash Mercy",
            "prepared_record_notes": "Prepared review context for the GM.",
            "insight_cost": 10,
            "one_use": True,
        }
    ]
    assert xianxia["insight"] == {"available": 0, "spent": 0}
    assert xianxia["advancement_history"] == []

    sheet_response = client.get(
        "/campaigns/linden-pass/characters/prepared-request-crane?mode=session&page=techniques"
    )
    assert sheet_response.status_code == 200
    html = unescape(sheet_response.get_data(as_text=True))
    assert "Prepared note request" in html
    assert "Prepared support:" in html
    assert "Dawn Ash Mercy" in html
    assert "Prepared review context for the GM." in html
    assert "Requesting the prepared vow at the table." in html
    assert "One-use history: not recorded yet" in html


def test_xianxia_techniques_page_records_dao_immolating_insight_cost_and_one_use_history(
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
        data=_valid_xianxia_create_data("Spend Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    record = get_character("spend-crane")
    assert record is not None
    payload = record.definition.to_dict()
    payload["xianxia"]["insight"] = {"available": 12, "spent": 3}
    payload["xianxia"]["dao_immolating_techniques"]["prepared"] = [
        {"name": "Dawn Ash Mercy", "notes": "Prepared but not required."}
    ]
    payload["xianxia"]["dao_immolating_techniques"]["use_history"] = [
        {
            "name": "Lotus-Burning Last Word",
            "request_type": "dao_immolating_use",
            "request_source": "ad_hoc",
            "approval_status": "approved",
            "approval_notes": "GM approved at the duel table.",
        },
        {
            "name": "Unapproved Furnace Vow",
            "request_type": "dao_immolating_use",
            "approval_status": "pending",
        },
    ]
    _write_raw_xianxia_character_definition(app, "spend-crane", payload)
    record = get_character("spend-crane")
    assert record is not None

    sheet_response = client.get(
        "/campaigns/linden-pass/characters/spend-crane?mode=session&page=techniques"
    )
    sheet_html = unescape(sheet_response.get_data(as_text=True))
    assert sheet_response.status_code == 200
    assert "Insight cost: 10" in sheet_html
    assert "One-use history: not recorded yet" in sheet_html
    assert "dao_immolating_use_index" in sheet_html
    assert "Record One-Use Spend" in sheet_html

    response = client.post(
        "/campaigns/linden-pass/characters/spend-crane/xianxia/dao-immolating-use-records",
        data={
            "expected_revision": record.state_record.revision,
            "mode": "session",
            "page": "techniques",
            "dao_immolating_use_index": "0",
            "dao_immolating_use_notes": "Spent when the magistrate could not dodge.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "page=techniques" in response.headers["Location"]
    assert "mode=session" in response.headers["Location"]
    assert "xianxia-approval-dao-immolating-use-records" in response.headers["Location"]
    updated = get_character("spend-crane")
    assert updated is not None
    xianxia = updated.definition.to_dict()["xianxia"]
    assert xianxia["insight"] == {"available": 2, "spent": 13}
    used_record = xianxia["dao_immolating_techniques"]["use_history"][0]
    assert used_record["insight_cost"] == 10
    assert used_record["insight_spent"] == 10
    assert used_record["one_use"] is True
    assert used_record["used"] is True
    assert used_record["one_use_status"] == "used"
    assert used_record["use_notes"] == "Spent when the magistrate could not dodge."
    assert xianxia["dao_immolating_techniques"]["prepared"] == [
        {"name": "Dawn Ash Mercy", "notes": "Prepared but not required."}
    ]
    assert xianxia["dao_immolating_techniques"]["use_history"][1]["approval_status"] == "pending"
    assert xianxia["advancement_history"][-1] == {
        "action": "dao_immolating_technique_used",
        "amount": 10,
        "target": "Lotus-Burning Last Word",
        "use_history_index": 0,
        "insight_cost": 10,
        "one_use": True,
        "one_use_status": "used",
        "notes": "Spent when the magistrate could not dodge.",
    }

    updated_html = unescape(
        client.get(
            "/campaigns/linden-pass/characters/spend-crane?mode=session&page=techniques"
        ).get_data(as_text=True)
    )
    assert "One-use history: used; Insight spent 10" in updated_html
    assert "Spent when the magistrate could not dodge." in updated_html

    duplicate_response = client.post(
        "/campaigns/linden-pass/characters/spend-crane/xianxia/dao-immolating-use-records",
        data={
            "expected_revision": updated.state_record.revision,
            "mode": "session",
            "page": "techniques",
            "dao_immolating_use_index": "0",
        },
        follow_redirects=False,
    )
    assert duplicate_response.status_code == 302
    unchanged = get_character("spend-crane")
    assert unchanged is not None
    assert unchanged.state_record.revision == updated.state_record.revision
    assert unchanged.definition.to_dict()["xianxia"]["insight"] == {"available": 2, "spent": 13}


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
    record = get_character("subpage-crane")
    assert record is not None
    depleted_state = deepcopy(record.state_record.state)
    depleted_state["vitals"] = {"current_hp": 6, "temp_hp": 2}
    depleted_state["xianxia"]["vitals"] = {
        "current_hp": 6,
        "temp_hp": 2,
        "current_stance": 4,
        "temp_stance": 5,
    }
    depleted_state["xianxia"]["energies"] = {
        "jing": {"current": 0},
        "qi": {"current": 1},
        "shen": {"current": 0},
    }
    depleted_state["xianxia"]["yin_yang"] = {"yin_current": 0, "yang_current": 1}
    depleted_state["xianxia"]["dao"] = {"current": 2}
    _replace_character_state(app, record, depleted_state)

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
    assert "Source:" in martial_arts_html
    assert "Current rank key:" in martial_arts_html
    assert "/campaigns/linden-pass/systems/entries/demons-fist#xianxia-demons-fist-initiate" in martial_arts_html
    assert "<summary>" in martial_arts_html
    assert "Learned ranks" in martial_arts_html
    assert "Qi Fist Technique" in martial_arts_html
    assert "Rank: Initiate" in martial_arts_html
    assert "Kind: Technique" in martial_arts_html
    assert "Support: Reference only" in martial_arts_html
    assert re.search(
        r"<strong>Source/ref:</strong>\s*xianxia:demons-fist:initiate:qi-fist-technique",
        martial_arts_html,
    )
    assert "Costs:" in martial_arts_html
    assert "Range:" in martial_arts_html
    assert "Damage/Effort:" in martial_arts_html
    assert "Duration:" in martial_arts_html
    assert (
        "/campaigns/linden-pass/systems/entries/demons-fist"
        "#xianxia-demons-fist-initiate-qi-fist-technique"
    ) in martial_arts_html
    assert "Qi Blast" not in martial_arts_html
    assert "Known Generic Techniques" not in martial_arts_html
    assert "Features and traits" not in martial_arts_html

    techniques_response = client.get(
        "/campaigns/linden-pass/characters/subpage-crane?page=techniques"
    )
    assert techniques_response.status_code == 200
    techniques_html = unescape(techniques_response.get_data(as_text=True))
    assert "Known Generic Techniques" in techniques_html
    assert "Qi Blast" in techniques_html
    assert "/campaigns/linden-pass/systems/entries/qi-blast" in techniques_html
    assert "Insight 1" in techniques_html
    assert "Resource Costs: 1 Qi" in techniques_html
    assert "2 Qi" in techniques_html
    assert "Range: Near, Far" in techniques_html
    assert "Effort: Magic Effort Damage" in techniques_html
    assert "Learnable without a Master" in techniques_html
    assert "Current rank:" not in techniques_html
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
    assert "Current 6 / Max 10" in resources_html
    assert "Temporary HP: 2" in resources_html
    assert "Stance" in resources_html
    assert "Current 4 / Max 10" in resources_html
    assert "Temporary Stance: 5" in resources_html
    assert "Jing" in resources_html
    assert "Current 0 / Max 1" in resources_html
    assert "Qi" in resources_html
    assert "Current 1 / Max 1" in resources_html
    assert "Shen" in resources_html
    assert "Yin" in resources_html
    assert "Yang" in resources_html
    assert "Dao" in resources_html
    assert "Current 2 / Max 3" in resources_html
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
    assert "Defense calculation" in equipment_html
    assert "Base" in equipment_html
    assert "<strong>10</strong>" in equipment_html
    assert "Manual armor bonus: 2" in equipment_html
    assert "Constitution" in equipment_html
    assert "Defense = 10 + 2 + 3" in equipment_html
    assert "<strong>15</strong>" in equipment_html
    assert "Necessary weapons" in equipment_html
    assert "Jian" in equipment_html
    assert "Required by Taoist Blade" in equipment_html
    assert "Necessary tools" in equipment_html
    assert "Fishing rod, spear, or net" in equipment_html
    assert "Required for Fishing" in equipment_html
    assert "Calligraphy brush" in equipment_html
    assert "Required for Calligraphy" in equipment_html
    assert "Tea set" in equipment_html
    assert "Required for Tea Ceremony" in equipment_html
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


def test_xianxia_read_sheet_renders_all_first_pass_subpages_and_systems_links(
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
            **_valid_xianxia_create_data("Rendering Link Crane"),
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

    record = get_character("rendering-link-crane")
    assert record is not None
    payload = record.definition.to_dict()
    payload["xianxia"]["generic_techniques"] = [
        {
            "name": "Qi Blast",
            "systems_ref": _systems_ref(qi_blast),
        }
    ]
    payload["xianxia"]["dao_immolating_techniques"]["prepared"] = [
        {
            "name": "Star-Severing Promise",
            "status": "pending",
            "prepared_notes": "Prepared for later GM approval.",
        }
    ]
    _write_raw_xianxia_character_definition(app, "rendering-link-crane", payload)

    record = get_character("rendering-link-crane")
    assert record is not None
    enriched_state = deepcopy(record.state_record.state)
    enriched_state["notes"] = {
        "player_notes_markdown": "Remember the jade token.",
        "physical_description_markdown": "A crane-styled cultivator in river robes.",
        "background_markdown": "Raised near the market docks.",
        "session_notes": [],
    }
    enriched_state["inventory"] = [
        {
            "id": "jade-token",
            "name": "Jade Token",
            "quantity": 2,
            "notes": "Sect marker.",
        }
    ]
    _replace_character_state(app, record, enriched_state)

    subpage_expectations = {
        "quick": [
            "At a glance",
            "Check formula",
            "/campaigns/linden-pass/systems/entries/honor",
            "/campaigns/linden-pass/systems/entries/skills",
            "/campaigns/linden-pass/systems/entries/ranges-and-distance",
            "/campaigns/linden-pass/systems/entries/timing-and-initiative",
            "/campaigns/linden-pass/systems/entries/critical-hits",
            "/campaigns/linden-pass/systems/entries/sneak-attacks",
            "/campaigns/linden-pass/systems/entries/minions",
            "/campaigns/linden-pass/systems/entries/companion-derivation",
            "/campaigns/linden-pass/systems/entries/stance-activation-rules",
            "/campaigns/linden-pass/systems/entries/aura-activation-rules",
        ],
        "martial_arts": [
            "Martial Arts",
            "/campaigns/linden-pass/systems/entries/demons-fist",
            "/campaigns/linden-pass/systems/entries/demons-fist#xianxia-demons-fist-initiate",
            (
                "/campaigns/linden-pass/systems/entries/demons-fist"
                "#xianxia-demons-fist-initiate-qi-fist-technique"
            ),
        ],
        "techniques": [
            "Techniques",
            "/campaigns/linden-pass/systems/entries/qi-blast",
            "/campaigns/linden-pass/systems/entries/recoup",
            "/campaigns/linden-pass/systems/entries/throat-jab",
            "Prepared Dao Immolating Techniques",
            "Star-Severing Promise",
            "Prepared for later GM approval.",
        ],
        "resources": [
            "Resources",
            "Current 10 / Max 10",
            "Current 2 / Max 3",
        ],
        "skills": [
            "Skills",
            "Fishing",
            "/campaigns/linden-pass/systems/entries/skills",
        ],
        "equipment": [
            "Equipment",
            "Defense calculation",
            "Defense = 10 + 2 + 3",
            "Jian",
            "Fishing rod, spear, or net",
        ],
        "inventory": [
            "Inventory",
            "xianxia-inventory",
            "Jade Token",
            "x2",
        ],
        "personal": [
            "Personal",
            "Physical Description",
            "A crane-styled cultivator in river robes.",
            "Background",
            "Raised near the market docks.",
        ],
        "notes": [
            "Notes",
            "Remember the jade token.",
        ],
        "controls": [
            "Controls",
            "Player controls",
            "Current owner",
        ],
    }

    expected_subpage_links = tuple(subpage_expectations)
    for page, expected_fragments in subpage_expectations.items():
        response = client.get(
            f"/campaigns/linden-pass/characters/rendering-link-crane?page={page}"
        )
        assert response.status_code == 200
        html = unescape(response.get_data(as_text=True))
        for expected_page in expected_subpage_links:
            assert f"?page={expected_page}" in html
        assert "?page=features" not in html
        assert "?page=spellcasting" not in html
        for fragment in expected_fragments:
            assert fragment in html


def test_xianxia_session_character_uses_read_sheet_subpage_chrome(
    client,
    sign_in,
    users,
    app,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=_valid_xianxia_create_data("Session Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    response = client.get(
        "/campaigns/linden-pass/session/character?character=session-crane&page=martial_arts"
    )

    assert response.status_code == 200
    html = unescape(response.get_data(as_text=True))
    assert "Character subpages" in html
    assert "character-subpage-nav" in html
    assert "combat-workspace-nav" not in html
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
    ):
        assert f"/campaigns/linden-pass/session/character?character=session-crane&page={page}" in html
    assert "?page=controls" not in html
    assert ">Spells<" not in html
    assert ">Features<" not in html
    assert ">Abilities and Skills<" not in html
    assert "Demon's Fist" in html
    assert "Current rank: Initiate" in html
    assert "Rank: Initiate" in html
    assert "Qi Fist Technique" in html
    assert "Learned ranks" in html
    assert re.search(
        r"<strong>Source/ref:</strong>\s*xianxia:demons-fist:initiate:qi-fist-technique",
        html,
    )
    assert "/campaigns/linden-pass/characters/session-crane?page=martial_arts" in html

    legacy_response = client.get(
        "/campaigns/linden-pass/session/character?character=session-crane&page=spellcasting"
    )
    assert legacy_response.status_code == 200
    legacy_html = unescape(legacy_response.get_data(as_text=True))
    assert "At a glance" in legacy_html
    assert "?page=spellcasting" not in legacy_html
    assert ">Spellcasting<" not in legacy_html


def test_xianxia_session_resources_allow_hp_and_temp_hp_updates(
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
        data=_valid_xianxia_create_data("Session HP Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    resources_response = client.get(
        "/campaigns/linden-pass/session/character?character=session-hp-crane&page=resources"
    )

    assert resources_response.status_code == 200
    resources_html = unescape(resources_response.get_data(as_text=True))
    assert 'id="session-vitals"' in resources_html
    assert 'name="current_hp" value="10" min="0" max="10"' in resources_html
    assert 'name="temp_hp" value="0" min="0"' in resources_html
    assert 'name="current_stance" value="10" min="0" max="10"' in resources_html
    assert 'name="temp_stance" value="0" min="0"' in resources_html
    assert "Save HP" in resources_html

    record = get_character("session-hp-crane")
    assert record is not None
    response = client.post(
        "/campaigns/linden-pass/characters/session-hp-crane/session/vitals",
        data={
            "expected_revision": record.state_record.revision,
            "current_hp": "7",
            "temp_hp": "3",
            "mode": "session",
            "page": "resources",
            "return_view": "session-character",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert (
        "/campaigns/linden-pass/session/character?character=session-hp-crane"
        "&page=resources#session-vitals"
    ) in response.headers["Location"]
    updated = get_character("session-hp-crane")
    assert updated is not None
    assert updated.state_record.state["vitals"] == {"current_hp": 7, "temp_hp": 3}
    assert updated.state_record.state["xianxia"]["vitals"]["current_hp"] == 7
    assert updated.state_record.state["xianxia"]["vitals"]["temp_hp"] == 3

    sheet_response = client.get(
        "/campaigns/linden-pass/characters/session-hp-crane?mode=session&page=resources"
    )
    assert sheet_response.status_code == 200
    sheet_html = unescape(sheet_response.get_data(as_text=True))
    assert 'id="session-vitals"' in sheet_html
    assert 'name="current_hp" value="7" min="0" max="10"' in sheet_html

    response = client.post(
        "/campaigns/linden-pass/characters/session-hp-crane/session/vitals",
        data={
            "expected_revision": updated.state_record.revision,
            "current_hp": "6",
            "temp_hp": "1",
            "mode": "session",
            "page": "resources",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/campaigns/linden-pass/characters/session-hp-crane?" in response.headers["Location"]
    assert "mode=session" in response.headers["Location"]
    assert "page=resources" in response.headers["Location"]
    assert response.headers["Location"].endswith("#session-vitals")
    updated = get_character("session-hp-crane")
    assert updated is not None
    assert updated.state_record.state["vitals"] == {"current_hp": 6, "temp_hp": 1}
    assert updated.state_record.state["xianxia"]["vitals"]["current_hp"] == 6
    assert updated.state_record.state["xianxia"]["vitals"]["temp_hp"] == 1


def test_xianxia_session_resources_allow_stance_and_temp_stance_updates(
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
        data=_valid_xianxia_create_data("Session Stance Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    resources_response = client.get(
        "/campaigns/linden-pass/session/character?character=session-stance-crane&page=resources"
    )

    assert resources_response.status_code == 200
    resources_html = unescape(resources_response.get_data(as_text=True))
    assert "HP, Stance, Energy, Yin/Yang, and Dao" in resources_html
    assert 'name="current_stance" value="10" min="0" max="10"' in resources_html
    assert 'name="temp_stance" value="0" min="0"' in resources_html
    assert "Save HP, Stance, Energy, Yin/Yang, and Dao" in resources_html

    record = get_character("session-stance-crane")
    assert record is not None
    response = client.post(
        "/campaigns/linden-pass/characters/session-stance-crane/session/vitals",
        data={
            "expected_revision": record.state_record.revision,
            "current_stance": "4",
            "temp_stance": "2",
            "mode": "session",
            "page": "resources",
            "return_view": "session-character",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert (
        "/campaigns/linden-pass/session/character?character=session-stance-crane"
        "&page=resources#session-vitals"
    ) in response.headers["Location"]
    updated = get_character("session-stance-crane")
    assert updated is not None
    assert updated.state_record.state["vitals"] == {"current_hp": 10, "temp_hp": 0}
    assert updated.state_record.state["xianxia"]["vitals"] == {
        "current_hp": 10,
        "temp_hp": 0,
        "current_stance": 4,
        "temp_stance": 2,
    }

    sheet_response = client.get(
        "/campaigns/linden-pass/characters/session-stance-crane?mode=session&page=resources"
    )
    assert sheet_response.status_code == 200
    sheet_html = unescape(sheet_response.get_data(as_text=True))
    assert 'name="current_stance" value="4" min="0" max="10"' in sheet_html
    assert 'name="temp_stance" value="2" min="0"' in sheet_html

    response = client.post(
        "/campaigns/linden-pass/characters/session-stance-crane/session/vitals",
        data={
            "expected_revision": updated.state_record.revision,
            "current_stance": "99",
            "temp_stance": "5",
            "mode": "session",
            "page": "resources",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    updated = get_character("session-stance-crane")
    assert updated is not None
    assert updated.state_record.state["xianxia"]["vitals"] == {
        "current_hp": 10,
        "temp_hp": 0,
        "current_stance": 10,
        "temp_stance": 5,
    }


def test_xianxia_session_resources_allow_manual_active_stance_and_aura_updates(
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
        data=_valid_xianxia_create_data("Session Active Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    resources_response = client.get(
        "/campaigns/linden-pass/session/character?character=session-active-crane&page=resources"
    )

    assert resources_response.status_code == 200
    resources_html = unescape(resources_response.get_data(as_text=True))
    assert 'id="session-active-state"' in resources_html
    assert "No active Stance recorded" in resources_html
    assert "No active Aura recorded" in resources_html
    assert 'name="active_stance_name" value=""' in resources_html
    assert 'name="active_aura_name" value=""' in resources_html
    assert "Save Active Stance and Aura" in resources_html

    record = get_character("session-active-crane")
    assert record is not None
    response = client.post(
        "/campaigns/linden-pass/characters/session-active-crane/session/xianxia-active-state",
        data={
            "expected_revision": record.state_record.revision,
            "active_stance_name": "  Stone   Root  ",
            "active_aura_name": "Azure Bell",
            "mode": "session",
            "page": "resources",
            "return_view": "session-character",
            "dying_rounds_remaining": "4",
            "statuses": "Burn",
            "attacks": "Duel Strike",
            "target_effects": "Sealed Bandit",
            "action_resolution": "Hit",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert (
        "/campaigns/linden-pass/session/character?character=session-active-crane"
        "&page=resources#session-active-state"
    ) in response.headers["Location"]
    updated = get_character("session-active-crane")
    assert updated is not None
    xianxia_state = updated.state_record.state["xianxia"]
    assert xianxia_state["active_stance"] == {"name": "Stone Root"}
    assert xianxia_state["active_aura"] == {"name": "Azure Bell"}
    for deferred_key in (
        "dying",
        "dying_rounds_remaining",
        "statuses",
        "attacks",
        "targets",
        "target_effects",
        "action_resolution",
    ):
        assert deferred_key not in xianxia_state

    quick_response = client.get(
        "/campaigns/linden-pass/characters/session-active-crane?mode=session&page=quick"
    )
    assert quick_response.status_code == 200
    quick_html = unescape(quick_response.get_data(as_text=True))
    assert "Active Stance: Stone Root" in quick_html
    assert "Active Aura: Azure Bell" in quick_html

    response = client.post(
        "/campaigns/linden-pass/characters/session-active-crane/session/xianxia-active-state",
        data={
            "expected_revision": updated.state_record.revision,
            "active_stance_name": "Flowing Reed",
            "active_aura_name": "",
            "mode": "session",
            "page": "resources",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    updated = get_character("session-active-crane")
    assert updated is not None
    assert updated.state_record.state["xianxia"]["active_stance"] == {
        "name": "Flowing Reed"
    }
    assert updated.state_record.state["xianxia"]["active_aura"] is None


def test_xianxia_session_resources_allow_jing_qi_and_shen_updates(
    client,
    sign_in,
    users,
    app,
    get_character,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_data = _valid_xianxia_create_data("Session Energy Crane")
    create_data.update({"energy_jing": "2", "energy_qi": "1", "energy_shen": "0"})
    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=create_data,
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    resources_response = client.get(
        "/campaigns/linden-pass/session/character?character=session-energy-crane&page=resources"
    )

    assert resources_response.status_code == 200
    resources_html = unescape(resources_response.get_data(as_text=True))
    assert 'name="current_jing" value="2" min="0" max="2"' in resources_html
    assert 'name="current_qi" value="1" min="0" max="1"' in resources_html
    assert 'name="current_shen" value="0" min="0" max="0"' in resources_html
    assert "Save HP, Stance, Energy, Yin/Yang, and Dao" in resources_html

    record = get_character("session-energy-crane")
    assert record is not None
    response = client.post(
        "/campaigns/linden-pass/characters/session-energy-crane/session/vitals",
        data={
            "expected_revision": record.state_record.revision,
            "current_jing": "1",
            "current_qi": "0",
            "current_shen": "1",
            "mode": "session",
            "page": "resources",
            "return_view": "session-character",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert (
        "/campaigns/linden-pass/session/character?character=session-energy-crane"
        "&page=resources#session-vitals"
    ) in response.headers["Location"]
    updated = get_character("session-energy-crane")
    assert updated is not None
    assert updated.state_record.state["vitals"] == {"current_hp": 10, "temp_hp": 0}
    assert updated.state_record.state["xianxia"]["energies"] == {
        "jing": {"current": 1},
        "qi": {"current": 0},
        "shen": {"current": 0},
    }

    sheet_response = client.get(
        "/campaigns/linden-pass/characters/session-energy-crane?mode=session&page=resources"
    )
    assert sheet_response.status_code == 200
    sheet_html = unescape(sheet_response.get_data(as_text=True))
    assert 'name="current_jing" value="1" min="0" max="2"' in sheet_html
    assert 'name="current_qi" value="0" min="0" max="1"' in sheet_html
    assert 'name="current_shen" value="0" min="0" max="0"' in sheet_html

    response = client.post(
        "/campaigns/linden-pass/characters/session-energy-crane/session/vitals",
        data={
            "expected_revision": updated.state_record.revision,
            "current_jing": "99",
            "current_qi": "2",
            "current_shen": "-3",
            "mode": "session",
            "page": "resources",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    updated = get_character("session-energy-crane")
    assert updated is not None
    assert updated.state_record.state["xianxia"]["energies"] == {
        "jing": {"current": 2},
        "qi": {"current": 1},
        "shen": {"current": 0},
    }


def test_xianxia_session_resources_allow_yin_and_yang_updates(
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
        data=_valid_xianxia_create_data("Session Yin Yang Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    resources_response = client.get(
        "/campaigns/linden-pass/session/character?character=session-yin-yang-crane&page=resources"
    )

    assert resources_response.status_code == 200
    resources_html = unescape(resources_response.get_data(as_text=True))
    assert 'name="current_yin" value="1" min="0" max="1"' in resources_html
    assert 'name="current_yang" value="1" min="0" max="1"' in resources_html
    assert "Save HP, Stance, Energy, Yin/Yang, and Dao" in resources_html

    record = get_character("session-yin-yang-crane")
    assert record is not None
    response = client.post(
        "/campaigns/linden-pass/characters/session-yin-yang-crane/session/vitals",
        data={
            "expected_revision": record.state_record.revision,
            "current_yin": "0",
            "current_yang": "1",
            "mode": "session",
            "page": "resources",
            "return_view": "session-character",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert (
        "/campaigns/linden-pass/session/character?character=session-yin-yang-crane"
        "&page=resources#session-vitals"
    ) in response.headers["Location"]
    updated = get_character("session-yin-yang-crane")
    assert updated is not None
    assert updated.state_record.state["vitals"] == {"current_hp": 10, "temp_hp": 0}
    assert updated.state_record.state["xianxia"]["yin_yang"] == {
        "yin_current": 0,
        "yang_current": 1,
    }

    sheet_response = client.get(
        "/campaigns/linden-pass/characters/session-yin-yang-crane?mode=session&page=resources"
    )
    assert sheet_response.status_code == 200
    sheet_html = unescape(sheet_response.get_data(as_text=True))
    assert 'name="current_yin" value="0" min="0" max="1"' in sheet_html
    assert 'name="current_yang" value="1" min="0" max="1"' in sheet_html

    response = client.post(
        "/campaigns/linden-pass/characters/session-yin-yang-crane/session/vitals",
        data={
            "expected_revision": updated.state_record.revision,
            "current_yin": "99",
            "current_yang": "-3",
            "mode": "session",
            "page": "resources",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    updated = get_character("session-yin-yang-crane")
    assert updated is not None
    assert updated.state_record.state["xianxia"]["yin_yang"] == {
        "yin_current": 1,
        "yang_current": 0,
    }


def test_xianxia_session_resources_allow_dao_update_with_cap(
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
        data={**_valid_xianxia_create_data("Session Dao Crane"), "dao_current": "2"},
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    resources_response = client.get(
        "/campaigns/linden-pass/session/character?character=session-dao-crane&page=resources"
    )

    assert resources_response.status_code == 200
    resources_html = unescape(resources_response.get_data(as_text=True))
    assert 'name="current_dao" value="2" min="0" max="3"' in resources_html
    assert "Dao 2 / 3" in resources_html
    assert "Save HP, Stance, Energy, Yin/Yang, and Dao" in resources_html

    record = get_character("session-dao-crane")
    assert record is not None
    response = client.post(
        "/campaigns/linden-pass/characters/session-dao-crane/session/vitals",
        data={
            "expected_revision": record.state_record.revision,
            "current_dao": "1",
            "mode": "session",
            "page": "resources",
            "return_view": "session-character",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert (
        "/campaigns/linden-pass/session/character?character=session-dao-crane"
        "&page=resources#session-vitals"
    ) in response.headers["Location"]
    updated = get_character("session-dao-crane")
    assert updated is not None
    assert updated.state_record.state["vitals"] == {"current_hp": 10, "temp_hp": 0}
    assert updated.state_record.state["xianxia"]["dao"] == {"current": 1}

    sheet_response = client.get(
        "/campaigns/linden-pass/characters/session-dao-crane?mode=session&page=resources"
    )
    assert sheet_response.status_code == 200
    sheet_html = unescape(sheet_response.get_data(as_text=True))
    assert 'name="current_dao" value="1" min="0" max="3"' in sheet_html

    response = client.post(
        "/campaigns/linden-pass/characters/session-dao-crane/session/vitals",
        data={
            "expected_revision": updated.state_record.revision,
            "current_dao": "99",
            "mode": "session",
            "page": "resources",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    updated = get_character("session-dao-crane")
    assert updated is not None
    assert updated.state_record.state["xianxia"]["dao"] == {"current": 3}


def test_xianxia_session_notes_allow_editable_users_to_update_notes(
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
        data=_valid_xianxia_create_data("Session Note Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    session_response = client.get(
        "/campaigns/linden-pass/session/character?character=session-note-crane&page=notes"
    )

    assert session_response.status_code == 200
    session_html = unescape(session_response.get_data(as_text=True))
    assert 'id="session-notes"' in session_html
    assert 'data-character-sheet-edit-form="notes"' in session_html
    assert 'name="player_notes_markdown"' in session_html
    assert "Save note" in session_html

    record = get_character("session-note-crane")
    assert record is not None
    response = client.post(
        "/campaigns/linden-pass/characters/session-note-crane/session/notes",
        data={
            "expected_revision": record.state_record.revision,
            "player_notes_markdown": "Track the jade token between scenes.",
            "mode": "session",
            "page": "notes",
            "return_view": "session-character",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert (
        "/campaigns/linden-pass/session/character?character=session-note-crane"
        "&page=notes#session-notes"
    ) in response.headers["Location"]
    updated = get_character("session-note-crane")
    assert updated is not None
    assert (
        updated.state_record.state["notes"]["player_notes_markdown"]
        == "Track the jade token between scenes."
    )
    assert updated.state_record.state["xianxia"]["notes"] == {
        "player_notes_markdown": "Track the jade token between scenes."
    }

    sheet_response = client.get(
        "/campaigns/linden-pass/characters/session-note-crane?mode=session&page=notes"
    )
    assert sheet_response.status_code == 200
    sheet_html = unescape(sheet_response.get_data(as_text=True))
    assert 'id="session-notes"' in sheet_html
    assert 'data-character-sheet-edit-form="notes"' in sheet_html
    assert "Track the jade token between scenes." in sheet_html


@pytest.mark.parametrize(
    ("user_key", "current_hp"),
    [
        ("dm", 8),
        ("admin", 7),
        ("owner", 6),
    ],
)
def test_xianxia_session_state_permissions_allow_editable_roles(
    client,
    sign_in,
    users,
    app,
    get_character,
    set_campaign_visibility,
    user_key,
    current_hp,
):
    character_slug = f"xianxia-permission-{user_key}"
    _create_assigned_xianxia_session_character(
        app,
        client,
        sign_in,
        users,
        set_campaign_visibility,
        character_slug=character_slug,
        name=f"Permission {user_key.title()} Crane",
    )

    sign_in(users[user_key]["email"], users[user_key]["password"])
    session_response = client.get(
        f"/campaigns/linden-pass/session/character?character={character_slug}&page=resources"
    )

    assert session_response.status_code == 200
    session_html = unescape(session_response.get_data(as_text=True))
    assert 'id="session-vitals"' in session_html
    assert "Save HP, Stance, Energy, Yin/Yang, and Dao" in session_html

    record = get_character(character_slug)
    assert record is not None
    response = client.post(
        f"/campaigns/linden-pass/characters/{character_slug}/session/vitals",
        data={
            "expected_revision": record.state_record.revision,
            "current_hp": str(current_hp),
            "mode": "session",
            "page": "resources",
            "return_view": "session-character",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert (
        f"/campaigns/linden-pass/session/character?character={character_slug}"
        "&page=resources#session-vitals"
    ) in response.headers["Location"]
    updated = get_character(character_slug)
    assert updated is not None
    assert updated.state_record.state["vitals"]["current_hp"] == current_hp
    assert updated.state_record.state["xianxia"]["vitals"]["current_hp"] == current_hp


@pytest.mark.parametrize("user_key", ["observer", "party"])
def test_xianxia_session_state_permissions_keep_read_only_roles_from_writing(
    client,
    sign_in,
    users,
    app,
    get_character,
    set_campaign_visibility,
    user_key,
):
    character_slug = f"xianxia-readonly-{user_key}"
    _create_assigned_xianxia_session_character(
        app,
        client,
        sign_in,
        users,
        set_campaign_visibility,
        character_slug=character_slug,
        name=f"Readonly {user_key.title()} Crane",
    )

    sign_in(users[user_key]["email"], users[user_key]["password"])
    read_response = client.get(
        f"/campaigns/linden-pass/characters/{character_slug}?mode=session&page=resources"
    )

    assert read_response.status_code == 200
    read_html = unescape(read_response.get_data(as_text=True))
    assert "Resources" in read_html
    assert 'id="session-vitals"' not in read_html
    assert "Save HP, Stance, Energy, Yin/Yang, and Dao" not in read_html

    session_response = client.get(
        f"/campaigns/linden-pass/session/character?character={character_slug}&page=resources"
    )
    assert session_response.status_code == 403

    record = get_character(character_slug)
    assert record is not None
    original_revision = record.state_record.revision
    original_state = deepcopy(record.state_record.state)

    blocked_vitals = client.post(
        f"/campaigns/linden-pass/characters/{character_slug}/session/vitals",
        data={
            "expected_revision": original_revision,
            "current_hp": "1",
            "current_stance": "1",
            "current_dao": "1",
            "mode": "session",
            "page": "resources",
            "return_view": "session-character",
        },
        follow_redirects=False,
    )
    blocked_active_state = client.post(
        f"/campaigns/linden-pass/characters/{character_slug}/session/xianxia-active-state",
        data={
            "expected_revision": original_revision,
            "active_stance_name": "Forbidden Stance",
            "active_aura_name": "Forbidden Aura",
            "mode": "session",
            "page": "resources",
            "return_view": "session-character",
        },
        follow_redirects=False,
    )
    blocked_notes = client.post(
        f"/campaigns/linden-pass/characters/{character_slug}/session/notes",
        data={
            "expected_revision": original_revision,
            "player_notes_markdown": "Forbidden note.",
            "mode": "session",
            "page": "notes",
            "return_view": "session-character",
        },
        follow_redirects=False,
    )

    assert blocked_vitals.status_code == 403
    assert blocked_active_state.status_code == 403
    assert blocked_notes.status_code == 403
    updated = get_character(character_slug)
    assert updated is not None
    assert updated.state_record.revision == original_revision
    assert updated.state_record.state == original_state


def test_xianxia_session_resources_reject_stale_revision_conflicts(
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
        data=_valid_xianxia_create_data("Session Conflict Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    record = get_character("session-conflict-crane")
    assert record is not None
    stale_revision = record.state_record.revision

    first = client.post(
        "/campaigns/linden-pass/characters/session-conflict-crane/session/vitals",
        data={
            "expected_revision": stale_revision,
            "current_hp": "8",
            "temp_hp": "1",
            "current_stance": "6",
            "temp_stance": "2",
            "current_jing": "0",
            "current_qi": "1",
            "current_shen": "0",
            "current_yin": "0",
            "current_yang": "1",
            "current_dao": "2",
            "mode": "session",
            "page": "resources",
            "return_view": "session-character",
        },
        follow_redirects=False,
    )
    assert first.status_code == 302

    second = client.post(
        "/campaigns/linden-pass/characters/session-conflict-crane/session/vitals",
        data={
            "expected_revision": stale_revision,
            "current_hp": "1",
            "temp_hp": "9",
            "current_stance": "1",
            "temp_stance": "9",
            "current_jing": "1",
            "current_qi": "0",
            "current_shen": "1",
            "current_yin": "1",
            "current_yang": "0",
            "current_dao": "3",
            "mode": "session",
            "page": "resources",
            "return_view": "session-character",
        },
        follow_redirects=True,
    )

    assert second.status_code == 200
    conflict_html = unescape(second.get_data(as_text=True))
    assert "This sheet changed in another session. Refresh the page and try again." in conflict_html
    assert 'name="current_hp" value="8" min="0" max="10"' in conflict_html
    assert 'name="temp_hp" value="1" min="0"' in conflict_html
    assert 'name="current_stance" value="6" min="0" max="10"' in conflict_html
    assert 'name="current_dao" value="2" min="0" max="3"' in conflict_html

    updated = get_character("session-conflict-crane")
    assert updated is not None
    assert updated.state_record.revision == stale_revision + 1
    assert updated.state_record.state["vitals"] == {"current_hp": 8, "temp_hp": 1}
    assert updated.state_record.state["xianxia"]["vitals"] == {
        "current_hp": 8,
        "temp_hp": 1,
        "current_stance": 6,
        "temp_stance": 2,
    }
    assert updated.state_record.state["xianxia"]["energies"] == {
        "jing": {"current": 0},
        "qi": {"current": 1},
        "shen": {"current": 0},
    }
    assert updated.state_record.state["xianxia"]["yin_yang"] == {
        "yin_current": 0,
        "yang_current": 1,
    }
    assert updated.state_record.state["xianxia"]["dao"] == {"current": 2}


def test_xianxia_session_active_state_rejects_stale_revision_conflicts(
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
        data=_valid_xianxia_create_data("Active Conflict Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    record = get_character("active-conflict-crane")
    assert record is not None
    stale_revision = record.state_record.revision

    first = client.post(
        "/campaigns/linden-pass/characters/active-conflict-crane/session/xianxia-active-state",
        data={
            "expected_revision": stale_revision,
            "active_stance_name": "Stone Root",
            "active_aura_name": "Azure Bell",
            "mode": "session",
            "page": "resources",
            "return_view": "session-character",
        },
        follow_redirects=False,
    )
    assert first.status_code == 302

    second = client.post(
        "/campaigns/linden-pass/characters/active-conflict-crane/session/xianxia-active-state",
        data={
            "expected_revision": stale_revision,
            "active_stance_name": "Flowing Reed",
            "active_aura_name": "Scarlet Wind",
            "mode": "session",
            "page": "resources",
            "return_view": "session-character",
        },
        follow_redirects=True,
    )

    assert second.status_code == 200
    conflict_html = unescape(second.get_data(as_text=True))
    assert "This sheet changed in another session. Refresh the page and try again." in conflict_html
    assert 'name="active_stance_name" value="Stone Root"' in conflict_html
    assert 'name="active_aura_name" value="Azure Bell"' in conflict_html
    assert "Flowing Reed" not in conflict_html
    assert "Scarlet Wind" not in conflict_html

    updated = get_character("active-conflict-crane")
    assert updated is not None
    assert updated.state_record.revision == stale_revision + 1
    assert updated.state_record.state["xianxia"]["active_stance"] == {"name": "Stone Root"}
    assert updated.state_record.state["xianxia"]["active_aura"] == {"name": "Azure Bell"}


def test_xianxia_session_note_conflict_stays_on_session_surface(
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
        data=_valid_xianxia_create_data("Note Conflict Crane"),
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    record = get_character("note-conflict-crane")
    assert record is not None
    stale_revision = record.state_record.revision

    first = client.post(
        "/campaigns/linden-pass/characters/note-conflict-crane/session/notes",
        data={
            "expected_revision": stale_revision,
            "player_notes_markdown": "Existing Xianxia session note.",
            "mode": "session",
            "page": "notes",
            "return_view": "session-character",
        },
        follow_redirects=False,
    )
    assert first.status_code == 302

    conflict = client.post(
        "/campaigns/linden-pass/characters/note-conflict-crane/session/notes",
        data={
            "expected_revision": stale_revision,
            "player_notes_markdown": "Draft note from stale Xianxia session state.",
            "mode": "session",
            "page": "notes",
            "return_view": "session-character",
        },
        follow_redirects=True,
    )

    assert conflict.status_code == 409
    conflict_html = unescape(conflict.get_data(as_text=True))
    assert "Session Character" in conflict_html
    assert "Save note" in conflict_html
    assert "Draft note from stale Xianxia session state." in conflict_html
    assert "This sheet changed in another session. Refresh the page and try again." in conflict_html

    updated = get_character("note-conflict-crane")
    assert updated is not None
    assert updated.state_record.revision == stale_revision + 1
    assert updated.state_record.state["notes"]["player_notes_markdown"] == (
        "Existing Xianxia session note."
    )
    assert updated.state_record.state["xianxia"]["notes"] == {
        "player_notes_markdown": "Existing Xianxia session note."
    }


def test_xianxia_martial_arts_page_marks_incomplete_rank_progress(
    client,
    sign_in,
    users,
    app,
):
    _configure_xianxia_campaign(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_data = _valid_xianxia_create_data("Incomplete Dagger Crane")
    create_data.update(
        {
            "martial_art_1_slug": "flying-daggers",
            "martial_art_1_rank": "initiate",
            "martial_art_2_slug": "demons-fist",
            "martial_art_2_rank": "initiate",
            "martial_art_3_slug": "heavenly-palm",
            "martial_art_3_rank": "initiate",
        }
    )
    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data=create_data,
        follow_redirects=False,
    )

    assert create_response.status_code == 302

    martial_arts_response = client.get(
        "/campaigns/linden-pass/characters/incomplete-dagger-crane?page=martial_arts"
    )
    assert martial_arts_response.status_code == 200
    martial_arts_html = unescape(martial_arts_response.get_data(as_text=True))

    assert "Flying Daggers" in martial_arts_html
    assert "Rank progress: 1 / 2 available ranks learned; 3 higher ranks incomplete." in martial_arts_html
    assert "Intentional draft content" in martial_arts_html
    assert "not an import failure" in martial_arts_html
    assert "Initiate" in martial_arts_html
    assert "Current" in martial_arts_html
    assert "Novice" in martial_arts_html
    assert "Unlearned" in martial_arts_html
    assert "Apprentice" in martial_arts_html
    assert "Master" in martial_arts_html
    assert "Legendary" in martial_arts_html
    assert "Incomplete draft" in martial_arts_html
    assert (
        "/campaigns/linden-pass/systems/entries/flying-daggers"
        "#xianxia-flying-daggers-initiate"
    ) in martial_arts_html


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
