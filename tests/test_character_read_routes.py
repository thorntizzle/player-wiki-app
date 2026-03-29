from __future__ import annotations

from copy import deepcopy
import yaml
from datetime import datetime, timezone

from player_wiki.systems_models import SystemsEntryRecord


def _write_character_definition(app, character_slug: str, mutator) -> None:
    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / character_slug
        / "definition.yaml"
    )
    payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    mutator(payload)
    definition_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_character_state(app, character_slug: str, mutator) -> None:
    with app.app_context():
        repository = app.extensions["character_repository"]
        store = app.extensions["character_state_store"]
        record = repository.get_character("linden-pass", character_slug)
        assert record is not None
        payload = deepcopy(record.state_record.state)
        mutator(payload)
        store.replace_state(
            record.definition,
            payload,
            expected_revision=record.state_record.revision,
        )


def test_dm_can_open_character_roster_and_read_sheet(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    roster = client.get("/campaigns/linden-pass/characters")
    sheet = client.get("/campaigns/linden-pass/characters/selene-brook")

    assert roster.status_code == 200
    roster_html = roster.get_data(as_text=True)
    assert "Selene Brook" in roster_html
    assert "Arden March" in roster_html
    assert "Tobin Slate" in roster_html
    assert "Back to wiki" not in roster_html

    assert sheet.status_code == 200
    sheet_html = sheet.get_data(as_text=True)
    assert "At a glance" in sheet_html
    assert "Enter session mode" in sheet_html
    assert "Back to character roster" not in sheet_html
    assert "Open campaign wiki" not in sheet_html


def test_player_cannot_open_character_roster_or_sheet_when_characters_are_dm_only(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    roster = client.get("/campaigns/linden-pass/characters")
    sheet = client.get("/campaigns/linden-pass/characters/arden-march")

    assert roster.status_code == 404
    assert sheet.status_code == 404


def test_owner_player_can_open_session_mode_when_character_visibility_allows_players(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=quick")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Active session" in html
    assert "Save vitals" in html
    assert "Back to read mode" in html
    assert "?mode=session&amp;page=quick" in html
    assert "?mode=session&amp;page=personal" in html
    assert "Save personal details" not in html


def test_unassigned_player_falls_back_to_read_mode_when_character_visibility_allows_players(
    client, sign_in, users, set_campaign_visibility
):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Active session" not in html
    assert "Save vitals" not in html
    assert "Enter session mode" not in html


def test_observer_cannot_read_character_when_characters_are_dm_only(client, sign_in, users):
    sign_in(users["observer"]["email"], users["observer"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session")

    assert response.status_code == 404


def test_character_sheet_subpages_show_requested_sections(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        reference_notes = dict(payload.get("reference_notes") or {})
        reference_notes["additional_notes_markdown"] = "Keep an eye on the harbor."
        payload["reference_notes"] = reference_notes

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?page=features")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Quick Reference" in html
    assert "Features" in html
    assert "Equipment" in html
    assert "Personal" in html
    assert "Notes" in html
    assert "?page=quick" in html
    assert "?page=features" in html
    assert "?page=equipment" in html
    assert "?page=personal" in html
    assert "?page=notes" in html
    assert "Features and traits" in html
    assert "At a glance" not in html
    assert "Equipment and currency" not in html
    assert "Keep an eye on the harbor." not in html
    assert "mode=session&amp;page=features" in html


def test_character_sheet_invalid_subpage_defaults_to_quick_reference(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?page=not-a-real-page")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "At a glance" in html
    assert "Abilities and skills" in html
    assert "Features and traits" not in html
    assert "Equipment and currency" not in html
    assert "No notes yet." not in html


def test_character_sheet_personal_and_notes_subpages_render_markdown_fields_and_hide_legacy_action_sections(
    app, client, sign_in, users
):
    def _mutate_definition(payload: dict) -> None:
        reference_notes = dict(payload.get("reference_notes") or {})
        reference_notes["additional_notes_markdown"] = "Keep an eye on the harbor."
        reference_notes["custom_sections"] = [
            {"title": "Actions: Bonus Actions", "body_markdown": "Second Wind"}
        ]
        payload["reference_notes"] = reference_notes

    def _mutate_state(payload: dict) -> None:
        notes = dict(payload.get("notes") or {})
        notes["player_notes_markdown"] = "Remember the **dock code**."
        notes["physical_description_markdown"] = "Tall, scarred, and always in dark leathers."
        notes["background_markdown"] = "Raised along the harbor and quick to vanish into crowds."
        payload["notes"] = notes

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    personal_response = client.get("/campaigns/linden-pass/characters/arden-march?page=personal")
    notes_response = client.get("/campaigns/linden-pass/characters/arden-march?page=notes")

    assert personal_response.status_code == 200
    personal_html = personal_response.get_data(as_text=True)
    assert "Personal" in personal_html
    assert "Physical Description" in personal_html
    assert "Tall, scarred, and always in dark leathers." in personal_html
    assert "Background" in personal_html
    assert "Raised along the harbor and quick to vanish into crowds." in personal_html
    assert "Save personal details" in personal_html
    assert 'name="physical_description_markdown"' in personal_html
    assert 'name="background_markdown"' in personal_html
    assert "No personal details yet." not in personal_html

    assert notes_response.status_code == 200
    notes_html = notes_response.get_data(as_text=True)
    assert "Notes" in notes_html
    assert "Remember the" in notes_html
    assert "dock code" in notes_html
    assert "Keep an eye on the harbor." in notes_html
    assert "Save note" in notes_html
    assert 'name="player_notes_markdown"' in notes_html
    assert "Actions: Bonus Actions" not in notes_html
    assert "Second Wind" not in notes_html
    assert "No notes yet." not in notes_html


def test_read_mode_note_save_stays_in_read_mode(client, sign_in, users, get_character, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    assert record is not None

    response = client.post(
        "/campaigns/linden-pass/characters/arden-march/session/notes",
        data={
            "expected_revision": record.state_record.revision,
            "page": "notes",
            "player_notes_markdown": "Read mode note save.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/campaigns/linden-pass/characters/arden-march?page=notes#session-notes")
    assert "mode=session" not in response.headers["Location"]


def test_session_mode_uses_same_subpage_ui_as_read_mode(client, sign_in, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=personal")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Active session" not in html
    assert "?mode=session&amp;page=quick" in html
    assert "?mode=session&amp;page=personal" in html
    assert "?mode=session&amp;page=notes" in html
    assert "Save personal details" in html
    assert "Save note" not in html
    assert "At a glance" not in html


def test_session_active_widget_stays_on_quick_reference_only(client, sign_in, users, set_campaign_visibility):
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["owner"]["email"], users["owner"]["password"])

    quick_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=quick")
    features_response = client.get("/campaigns/linden-pass/characters/arden-march?mode=session&page=features")

    assert quick_response.status_code == 200
    quick_html = quick_response.get_data(as_text=True)
    assert "Active session" in quick_html
    assert "Save vitals" in quick_html

    assert features_response.status_code == 200
    features_html = features_response.get_data(as_text=True)
    assert "Active session" not in features_html
    assert "Save vitals" not in features_html


def test_character_sheet_renders_systems_links_when_present(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        classes = list(profile.get("classes") or [])
        if classes:
            first_class = dict(classes[0] or {})
            first_class["systems_ref"] = {
                "entry_type": "class",
                "slug": "phb-class-sorcerer",
                "title": "Sorcerer",
                "source_id": "PHB",
            }
            first_class["subclass_ref"] = {
                "entry_type": "subclass",
                "slug": "phb-subclass-wild-magic",
                "title": "Wild Magic",
                "source_id": "PHB",
            }
            classes[0] = first_class
        profile["classes"] = classes
        profile["class_ref"] = {
            "entry_type": "class",
            "slug": "phb-class-sorcerer",
            "title": "Sorcerer",
            "source_id": "PHB",
        }
        profile["subclass_ref"] = {
            "entry_type": "subclass",
            "slug": "phb-subclass-wild-magic",
            "title": "Wild Magic",
            "source_id": "PHB",
        }
        profile["species_ref"] = {
            "entry_type": "race",
            "slug": "phb-race-human",
            "title": "Human",
            "source_id": "PHB",
        }
        profile["background_ref"] = {
            "entry_type": "background",
            "slug": "phb-background-noble",
            "title": "Noble",
            "source_id": "PHB",
        }
        payload["profile"] = profile

        features = list(payload.get("features") or [])
        if features:
            features[2]["systems_ref"] = {
                "entry_type": "classfeature",
                "slug": "phb-classfeature-spellcasting",
                "title": "Spellcasting",
                "source_id": "PHB",
            }
        payload["features"] = features

        attacks = list(payload.get("attacks") or [])
        if attacks:
            attacks[0]["systems_ref"] = {
                "entry_type": "item",
                "slug": "phb-item-crossbow-light",
                "title": "Crossbow, Light",
                "source_id": "PHB",
            }
        payload["attacks"] = attacks

        spellcasting = dict(payload.get("spellcasting") or {})
        spells = list(spellcasting.get("spells") or [])
        if spells:
            spells[0]["systems_ref"] = {
                "entry_type": "spell",
                "slug": "phb-spell-message",
                "title": "Message",
                "source_id": "PHB",
            }
        spellcasting["spells"] = spells
        payload["spellcasting"] = spellcasting

        equipment_catalog = list(payload.get("equipment_catalog") or [])
        if len(equipment_catalog) > 4:
            equipment_catalog[4]["systems_ref"] = {
                "entry_type": "item",
                "slug": "phb-item-backpack",
                "title": "Backpack",
                "source_id": "PHB",
            }
        payload["equipment_catalog"] = equipment_catalog

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    quick_response = client.get("/campaigns/linden-pass/characters/arden-march?page=quick")
    features_response = client.get("/campaigns/linden-pass/characters/arden-march?page=features")
    equipment_response = client.get("/campaigns/linden-pass/characters/arden-march?page=equipment")

    assert quick_response.status_code == 200
    assert features_response.status_code == 200
    assert equipment_response.status_code == 200

    quick_html = quick_response.get_data(as_text=True)
    features_html = features_response.get_data(as_text=True)
    equipment_html = equipment_response.get_data(as_text=True)

    assert '/campaigns/linden-pass/systems/entries/phb-class-sorcerer' in quick_html
    assert '/campaigns/linden-pass/systems/entries/phb-subclass-wild-magic' in quick_html
    assert '/campaigns/linden-pass/systems/entries/phb-race-human' in quick_html
    assert '/campaigns/linden-pass/systems/entries/phb-background-noble' in quick_html
    assert '/campaigns/linden-pass/systems/entries/phb-item-crossbow-light' in quick_html
    assert '/campaigns/linden-pass/systems/entries/phb-spell-message' in quick_html
    assert '/campaigns/linden-pass/systems/entries/phb-classfeature-spellcasting' in features_html
    assert '/campaigns/linden-pass/systems/entries/phb-item-backpack' in equipment_html
    assert 'View source entry' not in quick_html
    assert 'View source entry' not in features_html
    assert 'View source entry' not in equipment_html


def test_character_sheet_shows_systems_feature_text_inline_and_hides_source_metadata(
    app, client, sign_in, users, monkeypatch
):
    def _mutate(payload: dict) -> None:
        features = list(payload.get("features") or [])
        if not features:
            return
        features[0] = {
            "name": "Spellcasting",
            "category": "class_feature",
            "source": "Unique Source 77",
            "description_markdown": "",
            "activation_type": "bonus_action",
            "tracker_ref": None,
            "systems_ref": {
                "entry_type": "classfeature",
                "slug": "phb-classfeature-spellcasting",
                "title": "Spellcasting",
                "source_id": "PHB",
            },
        }
        payload["features"] = features

    _write_character_definition(app, "arden-march", _mutate)

    fake_entry = SystemsEntryRecord(
        id=999,
        library_slug="DND-5E",
        source_id="PHB",
        entry_key="dnd-5e|classfeature|phb|spellcasting",
        entry_type="classfeature",
        slug="phb-classfeature-spellcasting",
        title="Spellcasting",
        source_page="",
        source_path="",
        search_text="spellcasting",
        player_safe_default=True,
        dm_heavy=False,
        metadata={},
        body={"entries": ["You can cast spells using your force of personality as your spellcasting focus."]},
        rendered_html="",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    systems_service = app.extensions["systems_service"]
    original_get_entry = systems_service.get_entry_by_slug_for_campaign

    def _fake_get_entry(campaign_slug: str, entry_slug: str):
        if campaign_slug == "linden-pass" and entry_slug == "phb-classfeature-spellcasting":
            return fake_entry
        return original_get_entry(campaign_slug, entry_slug)

    monkeypatch.setattr(systems_service, "get_entry_by_slug_for_campaign", _fake_get_entry)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?page=features")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '>Spellcasting</a>' in html
    assert '/campaigns/linden-pass/systems/entries/phb-classfeature-spellcasting' in html
    assert 'You can cast spells using your force of personality as your spellcasting focus.' in html
    assert 'Unique Source 77' not in html
    assert 'View source entry' not in html


def test_character_sheet_hides_redundant_choice_placeholder_features(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        features = list(payload.get("features") or [])
        features.extend(
            [
                {
                    "name": "Hit Points",
                    "category": "class_feature",
                    "source": "PHB 71",
                    "description_markdown": "Your hit points increase by 1d10 plus your Constitution modifier at fighter level 1.",
                    "activation_type": "passive",
                    "tracker_ref": None,
                },
                {
                    "name": "Proficiencies",
                    "category": "class_feature",
                    "source": "PHB 71",
                    "description_markdown": "You gain proficiency with all armor, shields, simple weapons, and martial weapons.",
                    "activation_type": "passive",
                    "tracker_ref": None,
                },
                {
                    "name": "Languages",
                    "category": "species_trait",
                    "source": "BR 31",
                    "description_markdown": "You can speak, read, and write Common and one extra language.",
                    "activation_type": "passive",
                    "tracker_ref": None,
                },
                {
                    "name": "Ability Score Increase",
                    "category": "species_trait",
                    "source": "BR 31",
                    "description_markdown": "Two different ability scores of your choice increase by 1.",
                    "activation_type": "passive",
                    "tracker_ref": None,
                },
                {
                    "name": "Skills",
                    "category": "species_trait",
                    "source": "BR 31",
                    "description_markdown": "You gain proficiency in one skill of your choice.",
                    "activation_type": "passive",
                    "tracker_ref": None,
                },
                {
                    "name": "Feat",
                    "category": "species_trait",
                    "source": "BR 31",
                    "description_markdown": "You gain one feat of your choice.",
                    "activation_type": "passive",
                    "tracker_ref": None,
                },
                {
                    "name": "Ability Score Improvement",
                    "category": "class_feature",
                    "source": "PHB 72",
                    "description_markdown": "Increase one ability score by 2 or two ability scores by 1.",
                    "activation_type": "passive",
                    "tracker_ref": None,
                },
                {
                    "name": "Sentinel",
                    "category": "feat",
                    "source": "PHB 169",
                    "description_markdown": "Creatures provoke opportunity attacks from you even if they take the Disengage action.",
                    "activation_type": "reaction",
                    "tracker_ref": None,
                },
            ]
        )
        payload["features"] = features

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march?page=features")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Your hit points increase by 1d10 plus your Constitution modifier at fighter level 1." not in html
    assert "You gain proficiency with all armor, shields, simple weapons, and martial weapons." not in html
    assert "You can speak, read, and write Common and one extra language." not in html
    assert "Two different ability scores of your choice increase by 1." not in html
    assert "You gain proficiency in one skill of your choice." not in html
    assert "You gain one feat of your choice." not in html
    assert "Increase one ability score by 2 or two ability scores by 1." not in html
    assert "Creatures provoke opportunity attacks from you even if they take the Disengage action." in html


def test_character_sheet_renders_long_form_imported_ability_keys(app, client, sign_in, users):
    def _mutate(payload: dict) -> None:
        stats = dict(payload.get("stats") or {})
        stats["ability_scores"] = {
            "strength": {"score": 17, "modifier": 3, "save_bonus": 6},
            "dexterity": {"score": 13, "modifier": 1, "save_bonus": 1},
            "constitution": {"score": 16, "modifier": 3, "save_bonus": 3},
            "intelligence": {"score": 8, "modifier": -1, "save_bonus": -1},
            "wisdom": {"score": 12, "modifier": 1, "save_bonus": 1},
            "charisma": {"score": 19, "modifier": 4, "save_bonus": 7},
        }
        payload["stats"] = stats

    _write_character_definition(app, "arden-march", _mutate)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/characters/arden-march")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<h3>17</h3>" in html
    assert "<p>Strength</p>" in html
    assert "Modifier +3 | Save +6" in html
    assert "<h3>19</h3>" in html
    assert "<p>Charisma</p>" in html
    assert "Modifier +4 | Save +7" in html

