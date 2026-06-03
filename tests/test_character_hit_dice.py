from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from player_wiki.character_hit_dice import hit_dice_summary_from_state
from player_wiki.character_models import (
    CharacterDefinition,
    CharacterImportMetadata,
    CharacterRecord,
    CharacterStateRecord,
)
from player_wiki.character_service import build_initial_state, merge_state_with_definition, validate_state
from player_wiki.character_state_service import CharacterStateService
from tests.sample_data import ASSIGNED_CHARACTER_SLUG, TEST_CAMPAIGN_SLUG


def _definition(classes: list[dict[str, object]]) -> CharacterDefinition:
    return CharacterDefinition.from_dict(
        {
            "campaign_slug": TEST_CAMPAIGN_SLUG,
            "character_slug": "hit-dice-test",
            "name": "Hit Dice Test",
            "status": "active",
            "profile": {
                "class_level_text": " / ".join(
                    f"{row['class_name']} {row['level']}" for row in classes
                ),
                "classes": classes,
                "species": "Human",
                "background": "Tester",
            },
            "stats": {
                "max_hp": 24,
                "armor_class": 14,
                "initiative_bonus": 1,
                "speed": "30 ft.",
                "proficiency_bonus": 2,
            },
            "skills": [],
            "proficiencies": {},
            "attacks": [],
            "features": [],
            "spellcasting": {},
            "equipment_catalog": [],
            "reference_notes": {},
            "resource_templates": [],
            "source": {},
        }
    )


def _record(definition: CharacterDefinition, state: dict[str, object]) -> CharacterRecord:
    return CharacterRecord(
        definition=definition,
        import_metadata=CharacterImportMetadata(
            campaign_slug=definition.campaign_slug,
            character_slug=definition.character_slug,
            source_path="test://hit-dice",
            imported_at_utc="2026-06-03T00:00:00Z",
            parser_version="test",
            import_status="complete",
            warnings=[],
        ),
        state_record=CharacterStateRecord(
            campaign_slug=definition.campaign_slug,
            character_slug=definition.character_slug,
            revision=1,
            state=state,
            updated_at=datetime.now(timezone.utc),
            updated_by_user_id=None,
        ),
    )


class _MemoryStateStore:
    def replace_state(
        self,
        definition: CharacterDefinition,
        state: dict[str, object],
        *,
        expected_revision: int,
        updated_by_user_id: int | None = None,
    ) -> CharacterStateRecord:
        return CharacterStateRecord(
            campaign_slug=definition.campaign_slug,
            character_slug=definition.character_slug,
            revision=expected_revision + 1,
            state=validate_state(definition, state),
            updated_at=datetime.now(timezone.utc),
            updated_by_user_id=updated_by_user_id,
        )


def test_initial_state_tracks_multiclass_hit_dice_by_die_size():
    definition = _definition(
        [
            {"class_name": "Rogue", "level": 1},
            {"class_name": "Fighter", "level": 1},
        ]
    )

    state = build_initial_state(definition)

    assert state["hit_dice"]["pools"] == [
        {"faces": 8, "current": 1, "max": 1},
        {"faces": 10, "current": 1, "max": 1},
    ]
    assert hit_dice_summary_from_state(definition, state)["value"] == "d8 1/1 | d10 1/1"


def test_merge_hit_dice_defaults_new_pools_and_clamps_existing_counts():
    original = _definition([{"class_name": "Fighter", "level": 1}])
    state = build_initial_state(original)
    state["hit_dice"] = {"pools": [{"faces": 10, "current": 7, "max": 1}]}
    leveled = _definition(
        [
            {"class_name": "Wizard", "level": 1},
            {"class_name": "Fighter", "level": 2},
        ]
    )

    merged = merge_state_with_definition(leveled, state)

    assert merged["hit_dice"]["pools"] == [
        {"faces": 6, "current": 1, "max": 1},
        {"faces": 10, "current": 2, "max": 2},
    ]


def test_long_rest_recovers_hit_dice_by_pool_without_auto_healing_hp():
    definition = _definition(
        [
            {"class_name": "Rogue", "level": 2},
            {"class_name": "Fighter", "level": 2},
        ]
    )
    state = build_initial_state(definition)
    state["vitals"]["current_hp"] = 3
    state["hit_dice"] = {
        "pools": [
            {"faces": 8, "current": 0, "max": 2},
            {"faces": 10, "current": 0, "max": 2},
        ]
    }

    result = CharacterStateService(_MemoryStateStore()).apply_rest(
        _record(definition, state),
        "long",
        expected_revision=1,
    )

    assert result.state["vitals"]["current_hp"] == 3
    assert result.state["hit_dice"]["pools"] == [
        {"faces": 8, "current": 0, "max": 2},
        {"faces": 10, "current": 2, "max": 2},
    ]


def test_hit_dice_current_counts_are_editable_through_vitals_update():
    definition = _definition(
        [
            {"class_name": "Rogue", "level": 1},
            {"class_name": "Fighter", "level": 1},
        ]
    )
    state = build_initial_state(definition)

    result = CharacterStateService(_MemoryStateStore()).update_vitals(
        _record(definition, state),
        expected_revision=1,
        hit_dice_current={8: "0", 10: "1"},
    )

    assert result.state["hit_dice"]["pools"] == [
        {"faces": 8, "current": 0, "max": 1},
        {"faces": 10, "current": 1, "max": 1},
    ]


def _make_assigned_character_rogue_fighter(app) -> None:
    definition_path = (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / TEST_CAMPAIGN_SLUG
        / "characters"
        / ASSIGNED_CHARACTER_SLUG
        / "definition.yaml"
    )
    payload = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    profile = dict(payload.get("profile") or {})
    profile["class_level_text"] = "Rogue 1 / Fighter 1"
    profile["classes"] = [
        {"class_name": "Rogue", "level": 1},
        {"class_name": "Fighter", "level": 1},
    ]
    payload["profile"] = profile
    payload["stats"] = {**dict(payload.get("stats") or {}), "max_hp": 18}
    definition_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_hit_dice_render_on_character_session_and_combat_surfaces(app, client, sign_in, users):
    _make_assigned_character_rogue_fighter(app)
    with app.app_context():
        repository = app.extensions["character_repository"]
        assert repository.get_visible_character(TEST_CAMPAIGN_SLUG, ASSIGNED_CHARACTER_SLUG) is not None
    sign_in(users["dm"]["email"], users["dm"]["password"])

    character_response = client.get(
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/characters/{ASSIGNED_CHARACTER_SLUG}"
    )
    assert character_response.status_code == 200
    character_html = character_response.get_data(as_text=True)
    assert "Hit Dice" in character_html
    assert 'name="hit_dice_d8"' in character_html
    assert 'name="hit_dice_d10"' in character_html
    assert "d8" in character_html
    assert "d10" in character_html

    sign_in(users["dm"]["email"], users["dm"]["password"])
    start_response = client.post(
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/session/start",
        follow_redirects=False,
    )
    assert start_response.status_code == 302
    sign_in(users["owner"]["email"], users["owner"]["password"])

    session_response = client.get(
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/session/character"
        f"?character={ASSIGNED_CHARACTER_SLUG}&page=overview"
    )
    assert session_response.status_code == 200
    session_html = session_response.get_data(as_text=True)
    assert "Hit Dice" in session_html
    assert "d8 1/1 | d10 1/1" in session_html

    sign_in(users["dm"]["email"], users["dm"]["password"])
    add_response = client.post(
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/combat/player-combatants",
        data={"character_slug": ASSIGNED_CHARACTER_SLUG, "turn_value": 18},
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        follow_redirects=False,
    )
    assert add_response.status_code == 200
    combat_response = client.get(f"/campaigns/{TEST_CAMPAIGN_SLUG}/combat", follow_redirects=True)
    assert combat_response.status_code == 200
    combat_html = combat_response.get_data(as_text=True)
    assert "Hit Dice" in combat_html
    assert 'name="hit_dice_d8"' in combat_html
    assert 'name="hit_dice_d10"' in combat_html
