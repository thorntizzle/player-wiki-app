from __future__ import annotations

from tests.helpers.character_state_helpers import (
    _write_campaign_config,
    _write_character_definition,
    _write_character_state,
)
from tests.helpers.systems_import_helpers import _import_systems_goblin
import json
import inspect
import logging
import re
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
import player_wiki.app as app_module

import player_wiki.campaign_combat_service as campaign_combat_service_module
from player_wiki.app import create_app
from player_wiki.character_reconciliation import (
    CharacterPublicationCoordinator,
    CharacterReconciliationHooks,
)
from player_wiki.config import Config
from player_wiki.db import get_db, get_db_query_metrics, init_database, reset_db_query_metrics
from tests.sample_data import (
    TEST_CAMPAIGN_SLUG,
    approved_innovators_bolt_item_mechanics,
    build_test_campaigns_dir,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _combat_live_script_text() -> str:
    return (PROJECT_ROOT / "player_wiki" / "static" / "combat-live.js").read_text(encoding="utf-8")


def _combat_status_live_script_text() -> str:
    return (PROJECT_ROOT / "player_wiki" / "templates" / "_combat_status_live_scripts.html").read_text(
        encoding="utf-8"
    )


def _live_ui_helper_script_text() -> str:
    return (PROJECT_ROOT / "player_wiki" / "templates" / "_live_ui_helper.html").read_text(encoding="utf-8")


def _async_headers():
    return {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    }


def _live_poll_headers(revision: int, view_token: str, detail_state_token: str | None = None):
    headers = _async_headers()
    headers["X-Live-Revision"] = str(revision)
    headers["X-Live-View-Token"] = view_token
    if detail_state_token is not None:
        headers["X-Live-Detail-State-Token"] = detail_state_token
    return headers


def _assert_live_diagnostics_headers(response):
    assert response.headers["X-Live-Query-Count"]
    assert response.headers["X-Live-Query-Time-Ms"]
    assert response.headers["X-Live-Request-Time-Ms"]
    assert "db;dur=" in response.headers["Server-Timing"]
    assert "total;dur=" in response.headers["Server-Timing"]
    if "X-Live-Write-Count" in response.headers:
        assert response.headers["X-Live-Write-Count"]
        assert response.headers["X-Live-Write-Time-Ms"]
        assert response.headers["X-Live-Commit-Count"]
        assert response.headers["X-Live-Commit-Time-Ms"]


def _live_snapshot_sync_summary(response):
    summary_header = response.headers["X-Live-Snapshot-Sync"]
    return json.loads(summary_header)


def _get_tracker(app):
    with app.app_context():
        return app.extensions["campaign_combat_service"].get_tracker("linden-pass")


def _list_combatants(app):
    with app.app_context():
        return app.extensions["campaign_combat_service"].list_combatants("linden-pass")


def _find_combatant(app, *, name: str | None = None, character_slug: str | None = None):
    for combatant in _list_combatants(app):
        if name is not None and combatant.display_name == name:
            return combatant
        if character_slug is not None and combatant.character_slug == character_slug:
            return combatant
    return None


def _list_conditions(app, combatant_id: int):
    with app.app_context():
        return app.extensions["campaign_combat_service"].list_conditions_by_combatant("linden-pass").get(
            combatant_id,
            [],
        )


def _add_cleanup_probe_combatant(app, users, *, display_name: str, turn_value: int):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        combatant = service.add_npc_combatant(
            "linden-pass",
            display_name=display_name,
            turn_value=turn_value,
            current_hp=18,
            max_hp=18,
            movement_total=30,
            source_kind="systems_monster",
            source_ref=f"cleanup-{display_name.lower().replace(' ', '-')}",
            resource_counter_seeds=[
                SimpleNamespace(
                    resource_key="cleanup-charge",
                    label="Cleanup Charge",
                    current_value=2,
                    max_value=3,
                    reset_label="Long rest",
                    source_label="Cleanup probe",
                )
            ],
            resource_note_seeds=[
                SimpleNamespace(
                    label="Cleanup Note",
                    note="Cascade with the combatant.",
                    source_label="Cleanup probe",
                )
            ],
            created_by_user_id=users["dm"]["id"],
        )
        condition = service.add_condition(
            "linden-pass",
            combatant.id,
            name="Grappled",
            duration_text="Until escaped",
            created_by_user_id=users["dm"]["id"],
        )
    return combatant, condition


def _combat_dependent_counts(app, combatant_ids: list[int]) -> dict[str, int]:
    if not combatant_ids:
        return {}
    placeholders = ", ".join("?" for _ in combatant_ids)
    with app.app_context():
        connection = get_db()
        return {
            table: int(
                connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE combatant_id IN ({placeholders})",
                    tuple(combatant_ids),
                ).fetchone()[0]
            )
            for table in (
                "campaign_combat_conditions",
                "campaign_combatant_resource_counters",
                "campaign_combatant_resource_notes",
            )
        }


def _assert_expected_combatant_revision_field(html: str, revision: int, *, at_least: int = 1):
    marker = f'name="expected_combatant_revision" value="{revision}"'
    assert html.count(marker) >= at_least


def test_combat_async_form_posts_include_clicked_submit_button():
    combat_script = _combat_live_script_text()
    status_script = _combat_status_live_script_text()

    for script in (combat_script, status_script):
        assert "const submitterByForm = new WeakMap();" in script
        assert "const buildCombatFormData = (form, submitter) =>" in script
        assert "const resolveCombatSubmitter = (form, submitter) =>" in script
        assert 'event.target.closest("button, input[type=\'submit\'], input[type=\'image\']")' in script
        assert "submitterByForm.set(form, submitter);" in script
        assert "formData.append(submitter.name, submitter.value);" in script
        assert "const submitter = resolveCombatSubmitter(form, event.submitter);" in script
        assert "body: buildCombatFormData(form, submitter)" in script


def _assert_spell_slot_html_state(html: str, *, used: int, available: int, maximum: int):
    assert f"{available} available / {maximum}" in html
    assert f'name="used" value="{used}"' in html


def _convert_arden_spell_slots_to_class_lane(app, lane_id: str = "class-row-1-slots"):
    definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / "arden-march"
        / "definition.yaml"
    )
    payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    spellcasting = dict(payload.get("spellcasting") or {})
    slot_progression = [dict(slot or {}) for slot in list(spellcasting.get("slot_progression") or [])]
    spellcasting["slot_lanes"] = [
        {
            "id": lane_id,
            "title": "Sorcerer slots",
            "row_ids": ["class-row-1"],
            "slot_progression": slot_progression,
        }
    ]
    payload["spellcasting"] = spellcasting
    definition_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _inventory_item(record, item_id: str) -> dict:
    return next(
        item
        for item in list(record.state_record.state.get("inventory") or [])
        if str(item.get("catalog_ref") or item.get("id") or "") == item_id
    )


def _assert_form_has_priority_field(html: str, action: str) -> None:
    form_match = re.search(
        rf'<form\b[^>]*action="{re.escape(action)}"[\s\S]*?</form>',
        html,
    )
    assert form_match is not None
    form_html = form_match.group(0)
    assert "Priority" in form_html
    assert 'name="initiative_priority"' in form_html
    assert 'value="1"' in form_html
    assert 'min="1"' in form_html


def _seed_arden_innovators_bolt_item_action(app) -> None:
    item_ref = "items/combat-innovators-bolt"
    item_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "content"
        / "items"
        / "combat-innovators-bolt.md"
    )
    item_path.write_text(
        "\n".join(
            [
                "---",
                "title: Combat Innovator's Bolt",
                "section: Items",
                "page_type: item",
                "source_ref: Combat test item page",
                "published: true",
                "---",
                "",
                "*Weapon (pistol), very rare (requires attunement by an artificer)*",
                "",
                "A spell-slot-loaded firearm.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    with app.app_context():
        app.extensions["repository_store"].refresh()
        app.extensions["systems_service"].upsert_campaign_item_mechanics_entry_from_page(
            "linden-pass",
            item_ref,
            visibility="players",
            item_mechanics_review_status="approved",
            item_mechanics=approved_innovators_bolt_item_mechanics(allowed_levels=[1, 2]),
            actor_user_id=app.config["TEST_USERS"]["dm"]["id"],
            can_set_private=False,
        )

    def add_innovators_bolt(definition):
        equipment = list(definition.get("equipment_catalog") or [])
        equipment.append(
            {
                "id": "combat-innovators-bolt-1",
                "name": "Combat Innovator's Bolt",
                "default_quantity": 1,
                "weight": "",
                "notes": "",
                "page_ref": item_ref,
            }
        )
        definition["equipment_catalog"] = equipment

    def add_innovators_bolt_state(state):
        inventory = list(state.get("inventory") or [])
        inventory.append(
            {
                "id": "combat-innovators-bolt-1",
                "catalog_ref": "combat-innovators-bolt-1",
                "name": "Combat Innovator's Bolt",
                "quantity": 1,
                "is_equipped": True,
                "is_attuned": True,
            }
        )
        state["inventory"] = inventory
        for slot in list(state.get("spell_slots") or []):
            if int(slot.get("level") or 0) in {1, 2}:
                slot["used"] = 0

    _write_character_definition(app, "arden-march", add_innovators_bolt)
    _write_character_state(app, "arden-march", add_innovators_bolt_state)


def _create_dm_statblock(
    app,
    *,
    created_by_user_id: int | None = None,
    markdown_text: str | None = None,
    filename: str = "brass-hound.md",
):
    markdown_text = markdown_text or """---
title: Brass Hound
armor_class: 15
hp: 30
speed: 40 ft.
initiative_bonus: 2
---

## Bite

+6 to hit, 8 piercing damage.
"""
    with app.app_context():
        return app.extensions["campaign_dm_content_service"].create_statblock(
            TEST_CAMPAIGN_SLUG,
            filename=filename,
            data_blob=markdown_text.encode("utf-8"),
            created_by_user_id=created_by_user_id,
        )


def test_campaign_member_can_open_combat_page_and_campaign_links_to_it(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    campaign = client.get("/campaigns/linden-pass")
    combat_page = client.get("/campaigns/linden-pass/combat")

    assert campaign.status_code == 200
    campaign_html = campaign.get_data(as_text=True)
    assert "Combat" in campaign_html
    assert '/campaigns/linden-pass/combat' in campaign_html

    assert combat_page.status_code == 200
    combat_html = combat_page.get_data(as_text=True)
    assert "Combat tracker" in combat_html
    assert "Turn order" in combat_html
    assert "/campaigns/linden-pass/help#combat" in combat_html
    assert "/campaigns/linden-pass/combat/character" not in combat_html
    assert 'data-combat-live-root' in combat_html
    assert 'data-loading="0"' in combat_html
    assert '/static/combat-live.js?v=' in combat_html
    assert "window.__playerWikiLiveUiTools" in _combat_live_script_text()
    assert "/campaigns/linden-pass/combat/dm" not in combat_html
    assert "/campaigns/linden-pass/combat/status" not in combat_html
    assert "Add player character" not in combat_html
    assert "Add NPC from Systems" not in combat_html
    assert "Add custom combatant" not in combat_html
    assert 'data-live-active-interval-ms="500"' in combat_html
    assert 'data-live-idle-interval-ms="3000"' in combat_html


def test_combat_page_initializes_carousel_default_position_behavior(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    add_player = client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert add_player.status_code == 200
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None

    response = client.get(f"/campaigns/linden-pass/combat?combatant={arden.id}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'type="button"' in body
    assert "combat-turn-order-control--prev" in body
    assert "aria-label=\"Previous combatants\"" in body
    assert "data-combatant-carousel-prev" in body
    assert "combat-turn-order-control--next" in body
    assert "aria-label=\"Next combatants\"" in body
    assert "data-combatant-carousel-next" in body
    assert 'data-combatant-carousel-track' in body
    assert 'data-combatant-carousel-prev' in body
    assert 'data-combatant-carousel-next' in body
    assert 'data-combatant-current-turn="' in body
    assert 'data-combatant-selected="' in body
    combat_script = _combat_live_script_text()
    assert 'const getDefaultCombatantCarouselCard' in combat_script
    assert "const scrollCombatantCarouselByCard = (track, direction) => {" in combat_script
    assert "scrollBy({" in combat_script
    assert 'behavior: "smooth"' in combat_script
    assert 'const scrollToDefaultCombatantCarouselCard' in combat_script
    current_turn_precedence = combat_script.find('card.dataset.combatantCurrentTurn === "true"')
    selected_precedence = combat_script.find('card.dataset.combatantSelected === "true"')
    first_card_fallback = combat_script.find("return cards[0];")
    assert current_turn_precedence != -1
    assert selected_precedence != -1
    assert first_card_fallback != -1
    assert current_turn_precedence < selected_precedence < first_card_fallback
    assert 'data-combatant-initial-default' in combat_script


def test_character_hard_delete_preserves_existing_combat_snapshot_reference(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    add_response = client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert add_response.status_code == 200
    before = _find_combatant(app, character_slug="arden-march")
    assert before is not None

    delete_response = client.post(
        "/campaigns/linden-pass/characters/arden-march/controls/delete",
        data={"confirm_character_slug": "arden-march"},
        follow_redirects=False,
    )
    assert delete_response.status_code == 302

    after = _find_combatant(app, character_slug="arden-march")
    assert after is not None
    assert after.id == before.id
    assert after.display_name == before.display_name
    assert client.get(
        "/campaigns/linden-pass/combat", follow_redirects=True
    ).status_code == 200


def test_combat_page_player_workspace_carousel_renders_jump_dropdown_options(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        headers=_async_headers(),
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )
    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None

    response = client.get(f"/campaigns/linden-pass/combat?combatant={arden.id}")
    assert response.status_code == 200

    body = response.get_data(as_text=True)
    assert "data-combatant-carousel-jump" in body
    assert "data-combatant-carousel-jump-select" in body
    assert "Jump to combatant" in body
    assert "Arden March - Turn 18" in body
    assert "Clockwork Hound - Turn 12" in body
    assert "Player character · Character" in body
    assert "Arden March - Player character · Character - Turn 18" in body
    assert "&middot;" not in body
    assert "&MIDDOT;" not in body
    assert body.find("data-combatant-carousel-jump") > body.find("combat-turn-order-control--next")
    selected_option_match = re.search(r'<option[^>]*value="(\d+)"[^>]*selected="selected"', body)
    assert selected_option_match is not None

    selected_option_id = selected_option_match.group(1)
    selected_card_match = re.search(r'<article[^>]*aria-current="true"[^>]*data-combatant-id="(\d+)"', body)
    assert selected_card_match is not None
    assert selected_option_id == selected_card_match.group(1)


def test_combat_page_carousel_selected_badges_use_hidden_for_non_selected_cards(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )
    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None

    response = client.get(f"/campaigns/linden-pass/combat?combatant={arden.id}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "combatant" in body

    cards = re.findall(
        r'<article[^>]*class="combat-turn-order-row[^"]*"[^>]*>.*?</article>',
        body,
        flags=re.S,
    )
    assert len(cards) >= 2

    non_selected_cards = 0
    selected_cards = 0
    for card in cards:
        is_selected = 'data-combatant-selected="true"' in card
        has_selected_badge = "data-combatant-selected-badge" in card
        has_selected_summary = "data-combatant-selected-summary" in card
        assert has_selected_badge
        assert has_selected_summary

        badge_hidden = "data-combatant-selected-badge hidden" in card
        summary_hidden = "data-combatant-selected-summary hidden" in card
        if is_selected:
            selected_cards += 1
            assert not badge_hidden
            assert not summary_hidden
        else:
            non_selected_cards += 1
            assert badge_hidden
            assert summary_hidden

    assert selected_cards == 1
    assert non_selected_cards >= 1


def test_combat_page_tracks_carousel_intent_for_live_rerender_autoscroll(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        headers=_async_headers(),
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/combat")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert '/static/combat-live.js?v=' in body
    combat_script = _combat_live_script_text()
    assert "let combatantCarouselUserIntentObserved = false;" in combat_script
    assert "const markCombatantCarouselUserIntent = () => {" in combat_script
    assert "const scrollToCurrentTurnCombatantCarouselCard = (scope = liveRoot) => {" in combat_script
    assert "if (combatantCarouselUserIntentObserved) {" in combat_script
    assert "scrollToCurrentTurnCombatantCarouselCard(liveRoot);" in combat_script
    assert "markCombatantCarouselUserIntent();" in combat_script
    assert "if (event.isTrusted) {" in combat_script


def test_combat_page_render_payload_restores_carousel_state_on_user_intent(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        headers=_async_headers(),
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/combat")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert '/static/combat-live.js?v=' in body
    combat_script = _combat_live_script_text()
    assert "const captureCombatantCarouselState = (scope = liveRoot) => {" in combat_script
    assert "const restoreCombatantCarouselState = (scope = liveRoot, carouselStates = []) => {" in combat_script

    render_payload_anchor = combat_script.find(
        'const renderPayload = (payload, { force = false, forceFlash = false } = {}) => {'
    )
    refresh_payload_anchor = combat_script.find("const refreshLiveState = async ({", render_payload_anchor)
    assert render_payload_anchor != -1
    assert refresh_payload_anchor != -1
    assert render_payload_anchor < refresh_payload_anchor
    render_payload_block = combat_script[render_payload_anchor:refresh_payload_anchor]
    assert "const carouselState = captureCombatantCarouselState(liveRoot);" in render_payload_block
    assert "restoreCombatantCarouselState(liveRoot, carouselState);" in render_payload_block
    assert "if (combatantCarouselUserIntentObserved) {" in render_payload_block
    assert "scrollToCurrentTurnCombatantCarouselCard(liveRoot);" in render_payload_block

    capture_helper_anchor = combat_script.find("const captureCombatantCarouselState = (scope = liveRoot) => {")
    restore_helper_anchor = combat_script.find(
        "const restoreCombatantCarouselState = (scope = liveRoot, carouselStates = []) => {",
        capture_helper_anchor,
    )
    next_function_anchor = combat_script.find("const scrollToAnchor = (anchor) => {", restore_helper_anchor)
    assert capture_helper_anchor != -1
    assert restore_helper_anchor != -1
    assert next_function_anchor != -1
    assert capture_helper_anchor < restore_helper_anchor < next_function_anchor

    capture_helper_block = combat_script[capture_helper_anchor:restore_helper_anchor]
    restore_helper_block = combat_script[restore_helper_anchor:next_function_anchor]
    assert "setCombatantCarouselSelectedById" in restore_helper_block
    assert "getCombatantCarouselTrack(carousel)" in restore_helper_block
    assert "track.scrollLeft = Math.min(maxScrollLeft, trackScrollLeft);" in restore_helper_block
    assert "fetch(" not in capture_helper_block
    assert "fetch(" not in restore_helper_block


def test_combat_page_carousel_jump_select_updates_local_inspected_state_without_mutation(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    add_player = client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert add_player.status_code == 200
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/combat")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "data-combatant-carousel-jump-select" in body
    assert "data-combatant-selected-badge" in body
    assert "data-combatant-selected-summary" in body
    assert "combat-turn-order-row--selected" in body
    combat_script = _combat_live_script_text()
    assert 'const setCombatantCarouselCardSelectedState = (card, isSelected) => {' in combat_script
    assert 'const setCombatantCarouselSelectedById = (carousel, combatantId) => {' in combat_script
    assert 'setCombatantCarouselCardSelectedState(card, card === selectedCard);' in combat_script
    assert 'card.setAttribute("aria-current", isSelected ? "true" : "false");' in combat_script

    change_handler_anchor = combat_script.find('liveRoot.addEventListener("change", async (event) => {')
    jump_select_anchor = combat_script.find(
        'if (target.matches("[data-combatant-carousel-jump-select]")) {',
        change_handler_anchor,
    )
    navigation_select_anchor = combat_script.find(
        'if (target.matches("[data-combat-navigation-select]")) {',
        jump_select_anchor,
    )
    assert change_handler_anchor != -1
    assert jump_select_anchor != -1
    assert navigation_select_anchor != -1
    assert change_handler_anchor < jump_select_anchor < navigation_select_anchor

    jump_block = combat_script[jump_select_anchor:navigation_select_anchor]
    assert "const selectedCombatantId = target.value;" in jump_block
    assert "setCombatantCarouselSelectedById(carousel, selectedCombatantId);" in jump_block
    assert "markCombatantCarouselUserIntent();" in jump_block
    assert "focusCombatantCarouselCard(selectedCard);" in jump_block
    assert "fetch(" not in jump_block
    assert "window.history.replaceState" not in jump_block
    assert "syncViewUrls(" not in jump_block
    assert "buildUrl" not in jump_block
    assert "liveRoot.dataset.combatLiveUrl" not in jump_block


def test_combat_page_carousel_controls_scroll_without_state_mutation(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    add_player = client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert add_player.status_code == 200
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/combat")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert '/static/combat-live.js?v=' in body
    combat_script = _combat_live_script_text()

    click_handler_anchor = combat_script.find('liveRoot.addEventListener("click", (event) => {')
    focus_handler_anchor = combat_script.find('liveRoot.addEventListener("focusin", (event) => {')
    assert click_handler_anchor != -1
    assert focus_handler_anchor > click_handler_anchor
    carousel_click_block = combat_script[click_handler_anchor:focus_handler_anchor]

    assert "data-combatant-carousel-prev" in carousel_click_block
    assert "data-combatant-carousel-next" in carousel_click_block
    assert "scrollCombatantCarouselByCard(track, direction);" in carousel_click_block
    assert "event.preventDefault();" in carousel_click_block
    assert "markCombatantCarouselUserIntent();" in carousel_click_block
    assert "fetch(" not in carousel_click_block
    assert "campaign_combat_advance_turn" not in carousel_click_block
    assert "/set-current" not in carousel_click_block


def test_xianxia_combat_routes_show_friendly_unsupported_system_fallback(
    app, client, sign_in, users
):
    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"

    _write_campaign_config(app, _mutate)
    sign_in(users["party"]["email"], users["party"]["password"])

    combat_page = client.get("/campaigns/linden-pass/combat")
    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    controls_page = client.get("/campaigns/linden-pass/combat/dm")
    status_page = client.get("/campaigns/linden-pass/combat/status", follow_redirects=False)

    for response in (combat_page, controls_page):
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "Combat tracker not configured for Xianxia yet" in html
        assert "current combat tracker is" in html
        assert "DND-5E-only" in html
        assert "/campaigns/linden-pass/session" in html
        assert "Add player character" not in html
        assert "Add NPC from Systems" not in html
        assert "data-combat-live-url=" not in html
    assert status_page.status_code == 302
    assert status_page.headers["Location"] == "/campaigns/linden-pass/combat/dm"


def test_combat_route_redirects_dm_and_admin_users_to_dm_workspace_and_preserves_focus(
    app, client, sign_in, users
):
    sign_in(users["party"]["email"], users["party"]["password"])
    player_response = client.get("/campaigns/linden-pass/combat")
    assert player_response.status_code == 200

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    dm_redirect = client.get(
        f"/campaigns/linden-pass/combat?combatant={combatant.id}",
        follow_redirects=False,
    )
    assert dm_redirect.status_code == 302
    assert dm_redirect.headers["Location"] == f"/campaigns/linden-pass/combat/dm?combatant={combatant.id}"

    dm_base_redirect = client.get("/campaigns/linden-pass/combat", follow_redirects=False)
    assert dm_base_redirect.status_code == 302
    assert dm_base_redirect.headers["Location"] == "/campaigns/linden-pass/combat/dm"

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["admin"]["email"], users["admin"]["password"])
    admin_redirect = client.get("/campaigns/linden-pass/combat", follow_redirects=False)
    assert admin_redirect.status_code == 302
    assert admin_redirect.headers["Location"] == "/campaigns/linden-pass/combat/dm"


def test_dm_and_admin_can_open_dm_only_combat_pages_and_players_cannot(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_page = client.get("/campaigns/linden-pass/combat/dm")
    dm_controls_page = client.get("/campaigns/linden-pass/combat/dm?view=controls")
    status_page = client.get("/campaigns/linden-pass/combat/status", follow_redirects=False)

    assert dm_page.status_code == 200
    assert dm_controls_page.status_code == 200
    assert status_page.status_code == 302
    assert status_page.headers["Location"] == "/campaigns/linden-pass/combat/dm"
    dm_html = dm_page.get_data(as_text=True)
    dm_controls_html = dm_controls_page.get_data(as_text=True)
    assert "DM status" in dm_html
    assert "DM encounter subview" in dm_html
    assert 'href="/campaigns/linden-pass/combat/dm"' in dm_html
    assert 'href="/campaigns/linden-pass/combat/dm?view=controls"' in dm_html
    assert "/campaigns/linden-pass/combat/character" not in dm_html
    assert "DM status" in dm_html
    assert "Controls" in dm_html
    assert 'aria-label="Combat pages"' not in dm_html
    assert 'class="page-layout combat-layout combat-layout--workspace"' in dm_html
    assert 'class="page-layout combat-layout combat-layout--workspace"' in dm_controls_html
    assert "Add player character" not in dm_html
    assert "Add NPC from Systems" not in dm_html
    assert "Add custom combatant" not in dm_html
    assert "Add player character" in dm_controls_html
    assert "Add NPC from Systems" in dm_controls_html
    assert "Add custom combatant" in dm_controls_html
    _assert_form_has_priority_field(
        dm_controls_html,
        "/campaigns/linden-pass/combat/player-combatants",
    )
    _assert_form_has_priority_field(
        dm_controls_html,
        "/campaigns/linden-pass/combat/systems-monsters",
    )
    _assert_form_has_priority_field(
        dm_controls_html,
        "/campaigns/linden-pass/combat/npc-combatants",
    )
    if "/campaigns/linden-pass/combat/statblock-combatants" in dm_controls_html:
        _assert_form_has_priority_field(
            dm_controls_html,
            "/campaigns/linden-pass/combat/statblock-combatants",
        )
    assert "Encounter controls" in dm_controls_html
    assert "combat-dm-view=\"controls\"" in dm_controls_html
    assert "Current turn" not in dm_controls_html
    assert "Focus combatant" not in dm_controls_html
    assert 'id="combat-summary"' not in dm_controls_html
    assert 'id="combatant-' not in dm_controls_html
    assert "Open Encounter status" not in dm_controls_html
    assert 'data-combat-controls-root' in dm_controls_html
    assert not re.search(r'<div[^>]*data-combat-summary-root[^>]*>', dm_controls_html)
    assert not re.search(r'<div[^>]*data-combat-tracker-root[^>]*>', dm_controls_html)
    assert 'data-loading="0"' in dm_html
    assert re.search(
        r"<div[^>]*data-combat-status-selection-loading[^>]*>",
        dm_html,
    )
    assert not re.search(
        r"<div[^>]*data-combat-status-selection-loading[^>]*>",
        dm_controls_html,
    )
    assert '/static/combat-live.js?v=' in dm_html
    combat_script = _combat_live_script_text()
    assert "captureSystemsMonsterSearchState" in combat_script
    assert "captureControlsAddMode" in combat_script
    assert "restoreControlsAddMode(controlsAddMode)" in combat_script
    assert 'liveRoot.dataset.loading = "1";' not in combat_script
    live_ui_helper_script = _live_ui_helper_script_text()
    assert "const findMatchingForm = (root, descriptor) =>" in live_ui_helper_script
    assert 'focusState.form = describeForm(root, form);' in live_ui_helper_script
    assert "const fieldRoot = findMatchingForm(root, focusState.form) || root;" in live_ui_helper_script
    assert "window.history.replaceState(null, \"\", nextPageUrl);" in combat_script
    assert "buildLiveHeaders({ allowShortCircuit: false })" in combat_script
    assert "window.location.assign(nextUrl);" not in combat_script
    assert 'data-live-active-interval-ms="500"' in dm_html
    assert 'data-live-idle-interval-ms="3000"' in dm_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    player_dm_page = client.get("/campaigns/linden-pass/combat/dm")
    player_status_page = client.get("/campaigns/linden-pass/combat/status")
    assert player_dm_page.status_code == 403
    assert player_status_page.status_code == 403

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["admin"]["email"], users["admin"]["password"])

    admin_status_page = client.get(
        "/campaigns/linden-pass/combat/status",
        follow_redirects=False,
    )
    assert admin_status_page.status_code == 302
    assert admin_status_page.headers["Location"] == "/campaigns/linden-pass/combat/dm"


def test_dm_controls_uses_single_add_combatant_card_with_mode_selector(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    dm_controls_page = client.get("/campaigns/linden-pass/combat/dm?view=controls")
    assert dm_controls_page.status_code == 200
    dm_controls_html = dm_controls_page.get_data(as_text=True)

    assert dm_controls_html.count('<section class="card sidebar-card">') == 2
    assert '<h2>Add combatant</h2>' in dm_controls_html
    assert "combat-add-combatant-mode-switcher" in dm_controls_html
    assert 'role="radiogroup"' in dm_controls_html
    assert 'aria-label="Add combatant type"' in dm_controls_html
    assert 'name="combat-add-mode"' in dm_controls_html
    assert 'id="combat-add-mode-player"' in dm_controls_html
    assert 'id="combat-add-mode-systems"' in dm_controls_html
    assert 'id="combat-add-mode-dm-content"' in dm_controls_html
    assert 'id="combat-add-mode-custom"' in dm_controls_html
    assert 'value="player"' in dm_controls_html
    assert 'value="systems"' in dm_controls_html
    assert 'value="dm-content"' in dm_controls_html
    assert 'value="custom"' in dm_controls_html
    assert "Add player character" in dm_controls_html
    assert "Add NPC from Systems" in dm_controls_html
    assert "Add NPC from DM Content" in dm_controls_html
    assert "Add custom combatant" in dm_controls_html
    assert dm_controls_html.count('id="combat-add-mode-player"') == 1
    assert dm_controls_html.count('id="combat-add-mode-systems"') == 1
    assert dm_controls_html.count('id="combat-add-mode-dm-content"') == 1
    assert dm_controls_html.count('id="combat-add-mode-custom"') == 1
    assert re.search(r'<div class="combat-add-combatant-mode-panel [^"]*combat-add-combatant-mode-panel--player[^"]*"', dm_controls_html)
    assert re.search(r'<div class="combat-add-combatant-mode-panel [^"]*combat-add-combatant-mode-panel--systems[^"]*"', dm_controls_html)
    assert re.search(r'<div class="combat-add-combatant-mode-panel [^"]*combat-add-combatant-mode-panel--dm-content[^"]*"', dm_controls_html)
    assert re.search(r'<div class="combat-add-combatant-mode-panel [^"]*combat-add-combatant-mode-panel--custom[^"]*"', dm_controls_html)
    assert '<h2>Add player character</h2>' not in dm_controls_html
    assert '<h2>Add NPC from Systems</h2>' not in dm_controls_html
    assert '<h2>Add NPC from DM Content</h2>' not in dm_controls_html
    assert '<h2>Add custom combatant</h2>' not in dm_controls_html


def test_combat_live_state_and_async_updates_return_partials(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    add_player = client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert add_player.status_code == 200
    add_player_payload = add_player.get_json()
    assert add_player_payload["ok"] is True
    assert "Player character added to the combat tracker." in add_player_payload["flash_html"]
    assert "Arden March" in add_player_payload["tracker_html"]
    assert "controls_html" not in add_player_payload

    glenn = _find_combatant(app, character_slug="arden-march")
    assert glenn is not None

    set_current = client.post(
        f"/campaigns/linden-pass/combat/combatants/{glenn.id}/set-current",
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert set_current.status_code == 200
    set_current_payload = set_current.get_json()
    assert set_current_payload["ok"] is True
    assert "Current turn updated." in set_current_payload["flash_html"]
    assert "Current turn" in set_current_payload["summary_html"]
    assert "Arden March" in set_current_payload["summary_html"]

    live_state = client.get(
        "/campaigns/linden-pass/combat/live-state",
        headers=_async_headers(),
    )

    assert live_state.status_code == 200
    live_payload = live_state.get_json()
    assert "Arden March" in live_payload["tracker_html"]
    assert "Current turn" in live_payload["summary_html"]
    assert live_payload["combat_state_token"]


def test_combat_live_state_short_circuits_when_revision_and_view_token_match(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    initial_live_state = client.get(
        "/campaigns/linden-pass/combat/live-state",
        headers=_async_headers(),
    )

    assert initial_live_state.status_code == 200
    initial_payload = initial_live_state.get_json()
    assert initial_payload["changed"] is True
    assert initial_live_state.headers["X-Live-State-Changed"] == "true"
    assert initial_live_state.headers["X-Live-Revision"] == str(initial_payload["live_revision"])
    assert initial_live_state.headers["X-Live-Payload-Bytes"]
    _assert_live_diagnostics_headers(initial_live_state)

    unchanged_live_state = client.get(
        "/campaigns/linden-pass/combat/live-state",
        headers=_live_poll_headers(initial_payload["live_revision"], initial_payload["live_view_token"]),
    )

    assert unchanged_live_state.status_code == 200
    assert unchanged_live_state.get_json() == {
        "changed": False,
        "live_revision": initial_payload["live_revision"],
        "live_view_token": initial_payload["live_view_token"],
    }
    assert unchanged_live_state.headers["X-Live-State-Changed"] == "false"
    _assert_live_diagnostics_headers(unchanged_live_state)

    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None
    client.post(
        f"/campaigns/linden-pass/combat/combatants/{arden.id}/set-current",
        follow_redirects=False,
    )

    refreshed_live_state = client.get(
        "/campaigns/linden-pass/combat/live-state",
        headers=_live_poll_headers(initial_payload["live_revision"], initial_payload["live_view_token"]),
    )

    assert refreshed_live_state.status_code == 200
    refreshed_payload = refreshed_live_state.get_json()
    assert refreshed_payload["changed"] is True
    assert refreshed_payload["live_revision"] > initial_payload["live_revision"]
    assert "Current turn" in refreshed_payload["summary_html"]
    assert refreshed_live_state.headers["X-Live-State-Changed"] == "true"
    _assert_live_diagnostics_headers(refreshed_live_state)


def test_dm_status_live_state_short_circuits_when_revision_and_view_token_match(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    initial_live_state = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={combatant.id}",
        headers=_async_headers(),
    )

    assert initial_live_state.status_code == 200
    initial_payload = initial_live_state.get_json()
    assert initial_payload["changed"] is True
    assert initial_live_state.headers["X-Live-State-Changed"] == "true"
    assert initial_live_state.headers["X-Live-Revision"] == str(initial_payload["live_revision"])
    assert initial_live_state.headers["X-Live-Payload-Bytes"]
    _assert_live_diagnostics_headers(initial_live_state)

    unchanged_live_state = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={combatant.id}",
        headers=_live_poll_headers(initial_payload["live_revision"], initial_payload["live_view_token"]),
    )

    assert unchanged_live_state.status_code == 200
    assert unchanged_live_state.get_json() == {
        "changed": False,
        "live_revision": initial_payload["live_revision"],
        "live_view_token": initial_payload["live_view_token"],
    }
    assert unchanged_live_state.headers["X-Live-State-Changed"] == "false"
    _assert_live_diagnostics_headers(unchanged_live_state)


def test_dm_controls_live_state_short_circuits_when_revision_and_view_token_match(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    initial_live_state = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={combatant.id}&view=controls",
        headers=_async_headers(),
    )

    assert initial_live_state.status_code == 200
    initial_payload = initial_live_state.get_json()
    assert initial_payload["changed"] is True
    assert initial_live_state.headers["X-Live-State-Changed"] == "true"
    assert initial_live_state.headers["X-Live-Revision"] == str(initial_payload["live_revision"])
    assert initial_live_state.headers["X-Live-Payload-Bytes"]
    _assert_live_diagnostics_headers(initial_live_state)

    unchanged_live_state = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={combatant.id}&view=controls",
        headers=_live_poll_headers(initial_payload["live_revision"], initial_payload["live_view_token"]),
    )

    assert unchanged_live_state.status_code == 200
    assert unchanged_live_state.get_json() == {
        "changed": False,
        "live_revision": initial_payload["live_revision"],
        "live_view_token": initial_payload["live_view_token"],
    }
    assert unchanged_live_state.headers["X-Live-State-Changed"] == "false"
    _assert_live_diagnostics_headers(unchanged_live_state)


def test_dm_controls_live_state_omits_status_contract_html(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None

    response = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={arden.id}&view=controls",
        headers=_async_headers(),
    )
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["selected_combatant_id"] == arden.id
    assert "summary_html" not in payload
    assert "tracker_html" not in payload
    assert "tracker_authority_html" not in payload
    assert "tracker_detail_html" not in payload
    assert "controls_html" in payload


def test_combat_character_live_state_short_circuits_when_revision_and_view_token_match(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    initial_live_state = client.get(
        f"/campaigns/linden-pass/combat/character/live-state?combatant={combatant.id}",
        headers=_async_headers(),
    )

    assert initial_live_state.status_code == 200
    initial_payload = initial_live_state.get_json()
    assert initial_payload["changed"] is True
    assert initial_live_state.headers["X-Live-State-Changed"] == "true"
    assert initial_live_state.headers["X-Live-Revision"] == str(initial_payload["live_revision"])
    assert initial_live_state.headers["X-Live-Payload-Bytes"]
    _assert_live_diagnostics_headers(initial_live_state)

    unchanged_live_state = client.get(
        f"/campaigns/linden-pass/combat/character/live-state?combatant={combatant.id}",
        headers=_live_poll_headers(initial_payload["live_revision"], initial_payload["live_view_token"]),
    )

    assert unchanged_live_state.status_code == 200
    assert unchanged_live_state.get_json() == {
        "changed": False,
        "live_revision": initial_payload["live_revision"],
        "live_view_token": initial_payload["live_view_token"],
    }
    assert unchanged_live_state.headers["X-Live-State-Changed"] == "false"
    _assert_live_diagnostics_headers(unchanged_live_state)


def test_dm_can_add_systems_monster_to_combat_tracker(app, client, sign_in, users, tmp_path):
    goblin_entry_key, _ = _import_systems_goblin(app, tmp_path)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    combat_page = client.get("/campaigns/linden-pass/combat/dm?view=controls")
    assert combat_page.status_code == 200
    combat_html = combat_page.get_data(as_text=True)
    assert "Add NPC from Systems" in combat_html
    assert "Type at least 2 letters to search the Systems monster list." in combat_html
    assert "Goblin - MM" not in combat_html

    search_response = client.get(
        "/campaigns/linden-pass/combat/systems-monsters/search?q=gob",
        headers=_async_headers(),
    )

    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload["message"] == "Found 1 matching monster."
    assert len(search_payload["results"]) == 1
    assert search_payload["results"][0]["entry_key"] == goblin_entry_key
    assert search_payload["results"][0]["title"] == "Goblin"
    assert search_payload["results"][0]["source_id"] == "MM"
    assert "HP 7" in search_payload["results"][0]["subtitle"]
    assert search_payload["results"][0]["initiative_bonus"] == "+2"

    response = client.post(
        "/campaigns/linden-pass/combat/systems-monsters",
        data={"entry_key": goblin_entry_key, "combat_view": "dm", "view": "controls"},
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert "NPC combatant added from Systems (MM)." in payload["flash_html"]
    assert "Add NPC from Systems" in payload["controls_html"]
    assert "Turn order priorities" not in payload["controls_html"]
    assert "tracker_html" not in payload

    combatant = _find_combatant(app, name="Goblin")
    assert combatant is not None
    assert combatant.turn_value == 2
    assert combatant.initiative_bonus == 2
    assert combatant.current_hp == 7
    assert combatant.max_hp == 7
    assert combatant.movement_total == 30


def test_dm_combat_dm_page_does_not_eager_load_system_monster_choices(
    app, client, sign_in, users, tmp_path, monkeypatch
):
    _import_systems_goblin(app, tmp_path)

    with app.app_context():
        systems_service = app.extensions["systems_service"]

    def fail_load(*args, **kwargs):
        raise AssertionError("combat page should not eagerly load Systems monster choices")

    monkeypatch.setattr(systems_service, "list_monster_entries_for_campaign", fail_load)
    monkeypatch.setattr(systems_service, "search_monster_entries_for_campaign", fail_load)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/campaigns/linden-pass/combat/dm?view=controls")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Add NPC from Systems" in body
    assert "Search monsters" in body
    assert "Goblin - MM" not in body


def test_dm_page_async_mutations_return_controls_partial_and_non_async_redirects_back_to_dm_page(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    async_response = client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18, "combat_view": "dm", "view": "controls"},
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert async_response.status_code == 200
    async_payload = async_response.get_json()
    assert async_payload["ok"] is True
    assert "Add player character" in async_payload["controls_html"]


def test_async_dm_controls_basic_seeding_preserves_payload_fields_focus_and_attribution(
    app,
    client,
    sign_in,
    users,
):
    baseline_tracker = _get_tracker(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    player_response = client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={
            "character_slug": "arden-march",
            "turn_value": "",
            "initiative_priority": "",
            "combat_view": "dm",
            "view": "controls",
        },
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert player_response.status_code == 200
    player_payload = player_response.get_json()
    player = _find_combatant(app, character_slug="arden-march")
    assert player is not None
    assert player_payload["ok"] is True
    assert player_payload["anchor"] == "combat-tracker"
    assert player_payload["selected_combatant_id"] == player.id
    assert player_payload["page_url"] == (
        f"/campaigns/linden-pass/combat/dm?combatant={player.id}&view=controls"
    )
    assert player_payload["live_url"] == (
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={player.id}&view=controls"
    )
    assert "Player character added to the combat tracker." in player_payload["flash_html"]
    assert 'value="arden-march"' not in player_payload["controls_html"]
    assert "summary_html" not in player_payload
    assert "tracker_html" not in player_payload
    assert player.combatant_type == "player_character"
    assert player.display_name == "Arden March"
    assert player.character_slug == "arden-march"
    assert player.source_kind == "character"
    assert player.source_ref == "arden-march"
    assert player.player_detail_visible is True
    assert player.turn_value == 2
    assert player.initiative_bonus == 2
    assert player.dexterity_modifier == 2
    assert player.initiative_priority == 1
    assert player.current_hp == 38
    assert player.max_hp == 38
    assert player.temp_hp == 0
    assert player.movement_total == 30
    assert player.movement_remaining == 30
    assert player.revision == 1
    assert player.created_by_user_id == users["dm"]["id"]
    assert player.updated_by_user_id == users["dm"]["id"]
    after_player_tracker = _get_tracker(app)
    assert after_player_tracker.revision == baseline_tracker.revision + 1
    assert after_player_tracker.updated_by_user_id == users["dm"]["id"]
    assert player_payload["live_revision"] == after_player_tracker.revision

    npc_response = client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "  Clockwork Hound  ",
            "turn_value": "12",
            "dexterity_modifier": "3",
            "initiative_priority": "2",
            "current_hp": "22",
            "max_hp": "22",
            "temp_hp": "4",
            "movement_total": "40",
            "combat_view": "dm",
            "view": "controls",
            "combatant": player.id,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert npc_response.status_code == 200
    npc_payload = npc_response.get_json()
    npc = _find_combatant(app, name="Clockwork Hound")
    assert npc is not None
    assert npc_payload["ok"] is True
    assert npc_payload["anchor"] == "combat-tracker"
    assert npc_payload["selected_combatant_id"] == player.id
    assert npc_payload["page_url"] == player_payload["page_url"]
    assert npc_payload["live_url"] == player_payload["live_url"]
    assert "NPC combatant added to the combat tracker." in npc_payload["flash_html"]
    assert 'action="/campaigns/linden-pass/combat/npc-combatants"' in npc_payload[
        "controls_html"
    ]
    assert "summary_html" not in npc_payload
    assert "tracker_html" not in npc_payload
    assert npc.combatant_type == "npc"
    assert npc.character_slug is None
    assert npc.source_kind == "manual_npc"
    assert npc.source_ref == ""
    assert npc.player_detail_visible is False
    assert npc.turn_value == 12
    assert npc.initiative_bonus == 0
    assert npc.dexterity_modifier == 3
    assert npc.initiative_priority == 2
    assert npc.current_hp == 22
    assert npc.max_hp == 22
    assert npc.temp_hp == 4
    assert npc.movement_total == 40
    assert npc.movement_remaining == 40
    assert npc.revision == 1
    assert npc.created_by_user_id == users["dm"]["id"]
    assert npc.updated_by_user_id == users["dm"]["id"]
    after_npc_tracker = _get_tracker(app)
    assert after_npc_tracker.revision == after_player_tracker.revision + 1
    assert after_npc_tracker.updated_by_user_id == users["dm"]["id"]
    assert npc_payload["live_revision"] == after_npc_tracker.revision
    assert _combat_dependent_counts(app, [npc.id]) == {
        "campaign_combat_conditions": 0,
        "campaign_combatant_resource_counters": 0,
        "campaign_combatant_resource_notes": 0,
    }


def test_basic_seeding_services_batch_each_tracker_create_transaction(app, users):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        reset_db_query_metrics()
        service.add_player_character(
            "linden-pass",
            character_slug="arden-march",
            created_by_user_id=users["dm"]["id"],
        )
        player_metrics = get_db_query_metrics()
        reset_db_query_metrics()
        service.add_npc_combatant(
            "linden-pass",
            display_name="Transaction Watch",
            turn_value=5,
            current_hp=8,
            max_hp=8,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )
        npc_metrics = get_db_query_metrics()

    assert player_metrics["commit_count"] == 2
    assert player_metrics["rollback_count"] == 0
    assert npc_metrics["commit_count"] == 1
    assert npc_metrics["rollback_count"] == 0


def test_basic_seeding_validation_failures_preserve_tracker_and_combatant_state(
    app,
    client,
    sign_in,
    users,
):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        player = service.add_player_character(
            "linden-pass",
            character_slug="arden-march",
            created_by_user_id=users["dm"]["id"],
        )
    baseline_tracker = _get_tracker(app)
    baseline_combatants = _list_combatants(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])

    invalid_player = client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={
            "character_slug": "not-visible",
            "combat_view": "dm",
            "view": "controls",
            "combatant": player.id,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )
    duplicate_player = client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={
            "character_slug": "arden-march",
            "combat_view": "dm",
            "view": "controls",
            "combatant": player.id,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )
    empty_npc = client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "   ",
            "current_hp": "0",
            "max_hp": "0",
            "combat_view": "dm",
            "view": "controls",
            "combatant": player.id,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )
    invalid_hp_npc = client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "HP Guard",
            "current_hp": "11",
            "max_hp": "10",
            "combat_view": "dm",
            "view": "controls",
            "combatant": player.id,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    expected_errors = (
        (invalid_player, "Choose a valid player character to add to the tracker."),
        (duplicate_player, "That player character is already in the combat tracker."),
        (empty_npc, "NPC name is required."),
        (invalid_hp_npc, "Current HP cannot exceed max HP."),
    )
    for response, message in expected_errors:
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is False
        assert payload["anchor"] == "combat-tracker"
        assert payload["selected_combatant_id"] == player.id
        assert message in payload["flash_html"]
        assert payload["page_url"] == (
            f"/campaigns/linden-pass/combat/dm?combatant={player.id}&view=controls"
        )
    assert _list_combatants(app) == baseline_combatants
    assert _get_tracker(app) == baseline_tracker


def test_basic_seeding_allows_duplicate_manual_npc_names(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    data = {
        "display_name": "Duplicate Watch",
        "turn_value": "4",
        "current_hp": "8",
        "max_hp": "8",
        "movement_total": "30",
    }
    first = client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data=data,
        follow_redirects=False,
    )
    second = client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data=data,
        follow_redirects=False,
    )

    assert first.status_code == 302
    assert second.status_code == 302
    matches = [row for row in _list_combatants(app) if row.display_name == "Duplicate Watch"]
    assert len(matches) == 2
    assert matches[0].source_kind == matches[1].source_kind == "manual_npc"
    assert matches[0].source_ref == matches[1].source_ref == ""


def test_assigned_player_cannot_reach_basic_seeding_services(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]

    def fail_add(*args, **kwargs):
        raise AssertionError("assigned players must not reach basic seeding services")

    monkeypatch.setattr(service, "add_player_character", fail_add)
    monkeypatch.setattr(service, "add_npc_combatant", fail_add)
    sign_in(users["party"]["email"], users["party"]["password"])
    player_response = client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march"},
        follow_redirects=False,
    )
    npc_response = client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={"display_name": "Blocked Watch", "current_hp": 1, "max_hp": 1},
        follow_redirects=False,
    )

    assert player_response.status_code == 403
    assert npc_response.status_code == 403
    assert _list_combatants(app) == []


def test_unsupported_basic_seeding_short_circuits_before_services(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"

    _write_campaign_config(app, _mutate)
    baseline_tracker = _get_tracker(app)
    with app.app_context():
        service = app.extensions["campaign_combat_service"]

    def fail_add(*args, **kwargs):
        raise AssertionError("unsupported combat must not reach basic seeding services")

    monkeypatch.setattr(service, "add_player_character", fail_add)
    monkeypatch.setattr(service, "add_npc_combatant", fail_add)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    responses = (
        client.post(
            "/campaigns/linden-pass/combat/player-combatants",
            data={"character_slug": "arden-march", "combat_view": "dm", "view": "controls"},
            headers=_async_headers(),
            follow_redirects=False,
        ),
        client.post(
            "/campaigns/linden-pass/combat/npc-combatants",
            data={
                "display_name": "Unsupported Watch",
                "current_hp": 1,
                "max_hp": 1,
                "combat_view": "dm",
                "view": "controls",
            },
            headers=_async_headers(),
            follow_redirects=False,
        ),
    )

    for response in responses:
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is False
        assert payload["anchor"] == "combat-tracker"
        assert "Combat tracker support for Xianxia is not available yet." in payload["flash_html"]
    assert _list_combatants(app) == []
    assert _get_tracker(app) == baseline_tracker


def test_basic_seeding_forwards_raw_form_values_and_preserves_injected_validation_failures(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    baseline_tracker = _get_tracker(app)
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
    captured = {}

    def fail_player(*args, **kwargs):
        captured["player"] = (args, kwargs)
        raise campaign_combat_service_module.CampaignCombatValidationError(
            "Injected player seed failure."
        )

    def fail_npc(*args, **kwargs):
        captured["npc"] = (args, kwargs)
        raise campaign_combat_service_module.CampaignCombatValidationError(
            "Injected NPC seed failure."
        )

    monkeypatch.setattr(service, "add_player_character", fail_player)
    monkeypatch.setattr(service, "add_npc_combatant", fail_npc)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    player_response = client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={
            "character_slug": " arden-march ",
            "turn_value": " 17 ",
            "initiative_priority": " 3 ",
            "combat_view": "dm",
            "view": "controls",
        },
        headers=_async_headers(),
        follow_redirects=False,
    )
    npc_response = client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": " Raw Watch ",
            "turn_value": " 9 ",
            "initiative_bonus": "99",
            "dexterity_modifier": " -2 ",
            "initiative_priority": " 4 ",
            "current_hp": " 6 ",
            "max_hp": " 7 ",
            "temp_hp": " 1 ",
            "movement_total": " 25 ",
            "combat_view": "dm",
            "view": "controls",
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert player_response.status_code == 200
    assert player_response.get_json()["ok"] is False
    assert "Injected player seed failure." in player_response.get_json()["flash_html"]
    assert npc_response.status_code == 200
    assert npc_response.get_json()["ok"] is False
    assert "Injected NPC seed failure." in npc_response.get_json()["flash_html"]
    assert captured["player"] == (
        ("linden-pass",),
        {
            "character_slug": " arden-march ",
            "turn_value": " 17 ",
            "initiative_priority": " 3 ",
            "created_by_user_id": users["dm"]["id"],
        },
    )
    assert captured["npc"] == (
        ("linden-pass",),
        {
            "display_name": " Raw Watch ",
            "turn_value": " 9 ",
            "dexterity_modifier": " -2 ",
            "initiative_priority": " 4 ",
            "current_hp": " 6 ",
            "max_hp": " 7 ",
            "temp_hp": " 1 ",
            "movement_total": " 25 ",
            "created_by_user_id": users["dm"]["id"],
        },
    )
    assert _list_combatants(app) == []
    assert _get_tracker(app) == baseline_tracker


def test_basic_seeding_does_not_catch_non_validation_service_faults(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    baseline_tracker = _get_tracker(app)
    with app.app_context():
        service = app.extensions["campaign_combat_service"]

    def fail_unexpected(*args, **kwargs):
        raise RuntimeError("unexpected seed fault")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    monkeypatch.setattr(service, "add_player_character", fail_unexpected)
    with pytest.raises(RuntimeError, match="unexpected seed fault"):
        client.post(
            "/campaigns/linden-pass/combat/player-combatants",
            data={"character_slug": "arden-march"},
            follow_redirects=False,
        )
    monkeypatch.setattr(service, "add_npc_combatant", fail_unexpected)
    with pytest.raises(RuntimeError, match="unexpected seed fault"):
        client.post(
            "/campaigns/linden-pass/combat/npc-combatants",
            data={"display_name": "Fault Watch", "current_hp": 1, "max_hp": 1},
            follow_redirects=False,
        )
    assert _list_combatants(app) == []
    assert _get_tracker(app) == baseline_tracker


def test_basic_seeding_forms_have_csrf_and_csrf_blocks_before_mutation(
    app,
    client,
    sign_in,
    users,
):
    baseline_tracker = _get_tracker(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    app.config["CSRF_ENABLED"] = True
    html = client.get("/campaigns/linden-pass/combat/dm?view=controls").get_data(as_text=True)
    player_form = re.search(
        r'<form\b[^>]*action="/campaigns/linden-pass/combat/player-combatants"[^>]*>(.*?)</form>',
        html,
        re.S,
    )
    npc_form = re.search(
        r'<form\b[^>]*action="/campaigns/linden-pass/combat/npc-combatants"[^>]*>(.*?)</form>',
        html,
        re.S,
    )
    assert player_form is not None
    assert npc_form is not None
    assert player_form.group(1).count('name="_csrf_token"') == 1
    assert npc_form.group(1).count('name="_csrf_token"') == 1

    player_response = client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march"},
        follow_redirects=False,
    )
    npc_response = client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={"display_name": "CSRF Watch", "current_hp": 1, "max_hp": 1},
        follow_redirects=False,
    )
    assert player_response.status_code == 400
    assert npc_response.status_code == 400
    assert _list_combatants(app) == []
    assert _get_tracker(app) == baseline_tracker


def test_dm_controls_view_omits_turn_status_widgets(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    hound = _find_combatant(app, name="Clockwork Hound")
    assert arden is not None
    assert hound is not None

    set_current = client.post(f"/campaigns/linden-pass/combat/combatants/{arden.id}/set-current", follow_redirects=False)
    assert set_current.status_code in {200, 302}

    dm_page = client.get(f"/campaigns/linden-pass/combat/dm?combatant={arden.id}&view=controls")
    assert dm_page.status_code == 200
    dm_page_html = dm_page.get_data(as_text=True)
    assert "Focus combatant" not in dm_page_html
    assert "Open Encounter status" not in dm_page_html
    assert "Save turn value" not in dm_page_html
    assert "Save NPC structure" not in dm_page_html
    assert 'action="/campaigns/linden-pass/combat/advance-turn"' not in dm_page_html

    async_advance_response = client.post(
        "/campaigns/linden-pass/combat/advance-turn",
        data={"combat_view": "dm", "view": "controls", "combatant": arden.id},
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert async_advance_response.status_code == 200
    payload = async_advance_response.get_json()
    assert payload["ok"] is True
    assert payload["selected_combatant_id"] == hound.id
    assert payload["page_url"] == f"/campaigns/linden-pass/combat/dm?combatant={hound.id}&view=controls"
    assert payload["live_url"] == f"/campaigns/linden-pass/combat/dm/live-state?combatant={hound.id}&view=controls"
    assert "summary_html" not in payload
    assert "tracker_html" not in payload
    assert "tracker_authority_html" not in payload
    assert "tracker_detail_html" not in payload
    assert "controls_html" in payload
    assert 'action="/campaigns/linden-pass/combat/advance-turn"' not in payload["controls_html"]


def test_dm_status_async_advance_turn_preserves_selected_focus(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    hound = _find_combatant(app, name="Clockwork Hound")
    assert arden is not None
    assert hound is not None

    client.post(f"/campaigns/linden-pass/combat/combatants/{arden.id}/set-current", follow_redirects=False)

    async_advance_response = client.post(
        "/campaigns/linden-pass/combat/advance-turn",
        data={"combat_view": "dm", "view": "status", "combatant": arden.id},
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert async_advance_response.status_code == 200
    payload = async_advance_response.get_json()
    assert payload["ok"] is True
    assert payload["selected_combatant_id"] == arden.id
    assert payload["page_url"] == f"/campaigns/linden-pass/combat/dm?combatant={arden.id}"
    assert payload["live_url"] == f"/campaigns/linden-pass/combat/dm/live-state?combatant={arden.id}"
    assert f'data-combatant-id="{arden.id}"' in payload["tracker_html"]
    assert f'data-combatant-id="{hound.id}"' in payload["tracker_html"]
    assert "Current turn" in payload["tracker_html"]


def test_dm_advance_turn_with_stale_combatant_still_redirects_to_new_current_turn(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    hound = _find_combatant(app, name="Clockwork Hound")
    assert arden is not None
    assert hound is not None

    client.post(f"/campaigns/linden-pass/combat/combatants/{arden.id}/set-current", follow_redirects=False)

    response = client.post(
        "/campaigns/linden-pass/combat/advance-turn",
        data={"combat_view": "dm", "combatant": arden.id},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/campaigns/linden-pass/combat/dm" in response.headers["Location"]
    assert f"combatant={arden.id}" not in response.headers["Location"]

    dm_page = client.get("/campaigns/linden-pass/combat/dm")
    dm_page_html = dm_page.get_data(as_text=True)
    hound_card = re.search(rf'<article[^>]*data-combatant-id="{hound.id}"[^>]*>', dm_page_html)
    arden_card = re.search(rf'<article[^>]*data-combatant-id="{arden.id}"[^>]*>', dm_page_html)
    assert hound_card is not None
    assert arden_card is not None
    assert 'data-combatant-selected="true"' in hound_card.group(0)
    assert 'data-combatant-selected="true"' not in arden_card.group(0)


def test_dm_turn_update_rejects_stale_combatant_revision(app, client, sign_in, users):
    with app.app_context():
        combatant = app.extensions["campaign_combat_service"].add_npc_combatant(
            "linden-pass",
            display_name="Clockwork Hound",
            turn_value=12,
            current_hp=22,
            max_hp=22,
            movement_total=40,
            created_by_user_id=users["dm"]["id"],
        )

    sign_in(users["dm"]["email"], users["dm"]["password"])
    first_response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/turn",
        data={
            "combat_view": "dm",
            "view": "status",
            "combatant": combatant.id,
            "expected_combatant_revision": combatant.revision,
            "turn_value": 14,
            "initiative_priority": 2,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert first_response.status_code == 200
    assert first_response.get_json()["ok"] is True

    refreshed = _find_combatant(app, name="Clockwork Hound")
    assert refreshed is not None
    assert refreshed.turn_value == 14
    assert refreshed.initiative_priority == 2

    stale_response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/turn",
        data={
            "combat_view": "dm",
            "view": "status",
            "combatant": combatant.id,
            "expected_combatant_revision": combatant.revision,
            "turn_value": 3,
            "initiative_priority": 1,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert stale_response.status_code == 200
    assert stale_response.headers["X-Live-Mutation-Outcome"] == "combatant-revision-conflict"
    stale_payload = stale_response.get_json()
    assert stale_payload["ok"] is False
    assert "This combatant changed in another combat view. Refresh and try again." in stale_payload["flash_html"]

    unchanged = _find_combatant(app, name="Clockwork Hound")
    assert unchanged is not None
    assert unchanged.revision == refreshed.revision
    assert unchanged.turn_value == 14
    assert unchanged.initiative_priority == 2


def test_assigned_player_cannot_use_turn_control_routes(app, client, sign_in, users):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        first = service.add_npc_combatant(
            "linden-pass",
            display_name="First Watch",
            turn_value=18,
            current_hp=20,
            max_hp=20,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )
        second = service.add_npc_combatant(
            "linden-pass",
            display_name="Second Watch",
            turn_value=12,
            current_hp=20,
            max_hp=20,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )
        service.set_current_turn(
            "linden-pass",
            first.id,
            updated_by_user_id=users["dm"]["id"],
        )
        baseline_tracker = service.get_tracker("linden-pass")
        baseline_second = service.get_combatant("linden-pass", second.id)

    sign_in(users["owner"]["email"], users["owner"]["password"])
    responses = (
        client.post("/campaigns/linden-pass/combat/advance-turn", follow_redirects=False),
        client.post(
            f"/campaigns/linden-pass/combat/combatants/{second.id}/set-current",
            follow_redirects=False,
        ),
        client.post(
            f"/campaigns/linden-pass/combat/combatants/{second.id}/turn",
            data={
                "expected_combatant_revision": second.revision,
                "turn_value": 1,
            },
            follow_redirects=False,
        ),
    )
    assert [response.status_code for response in responses] == [403, 403, 403]

    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        unchanged_tracker = service.get_tracker("linden-pass")
        unchanged_second = service.get_combatant("linden-pass", second.id)
    assert unchanged_tracker.current_combatant_id == baseline_tracker.current_combatant_id
    assert unchanged_tracker.round_number == baseline_tracker.round_number
    assert unchanged_tracker.revision == baseline_tracker.revision
    assert unchanged_second == baseline_second


def test_unsupported_async_advance_turn_returns_failed_payload_without_service_call(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"

    _write_campaign_config(app, _mutate)
    with app.app_context():
        service = app.extensions["campaign_combat_service"]

    def fail_advance_turn(*args, **kwargs):
        raise AssertionError("unsupported combat must not call the turn service")

    monkeypatch.setattr(service, "advance_turn", fail_advance_turn)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.post(
        "/campaigns/linden-pass/combat/advance-turn",
        data={"combat_view": "dm", "view": "status"},
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Combat tracker support for Xianxia is not available yet." in payload["flash_html"]


def test_turn_update_preserves_uncaught_malformed_expected_revision(
    app,
    client,
    sign_in,
    users,
):
    with app.app_context():
        combatant = app.extensions["campaign_combat_service"].add_npc_combatant(
            "linden-pass",
            display_name="Revision Probe",
            turn_value=12,
            current_hp=9,
            max_hp=9,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )

    sign_in(users["dm"]["email"], users["dm"]["password"])
    with pytest.raises(ValueError):
        client.post(
            f"/campaigns/linden-pass/combat/combatants/{combatant.id}/turn",
            data={
                "expected_combatant_revision": "not-an-integer",
                "turn_value": 5,
            },
            follow_redirects=False,
        )

    unchanged = _find_combatant(app, name="Revision Probe")
    assert unchanged is not None
    assert unchanged.revision == combatant.revision
    assert unchanged.turn_value == 12


def test_assigned_player_cannot_use_condition_routes(app, client, sign_in, users):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        combatant = service.add_npc_combatant(
            "linden-pass",
            display_name="Condition Guard",
            turn_value=12,
            current_hp=18,
            max_hp=18,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )
        condition = service.add_condition(
            "linden-pass",
            combatant.id,
            name="Grappled",
            duration_text="Until escaped",
            created_by_user_id=users["dm"]["id"],
        )
        baseline_tracker = service.get_tracker("linden-pass")
        baseline_combatant = service.get_combatant("linden-pass", combatant.id)

    sign_in(users["owner"]["email"], users["owner"]["password"])
    responses = (
        client.post(
            f"/campaigns/linden-pass/combat/combatants/{combatant.id}/conditions",
            data={"condition_name": "Blinded"},
            follow_redirects=False,
        ),
        client.post(
            f"/campaigns/linden-pass/combat/conditions/{condition.id}",
            data={"condition_name": "Restrained"},
            follow_redirects=False,
        ),
        client.post(
            f"/campaigns/linden-pass/combat/conditions/{condition.id}/delete",
            follow_redirects=False,
        ),
    )
    assert [response.status_code for response in responses] == [403, 403, 403]

    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        unchanged_tracker = service.get_tracker("linden-pass")
        unchanged_combatant = service.get_combatant("linden-pass", combatant.id)
    assert unchanged_tracker == baseline_tracker
    assert unchanged_combatant == baseline_combatant
    assert _list_conditions(app, combatant.id) == [condition]


def test_condition_validation_failures_preserve_failed_payloads_and_fallback_anchors(
    app,
    client,
    sign_in,
    users,
):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        first = service.add_npc_combatant(
            "linden-pass",
            display_name="First Condition Focus",
            turn_value=12,
            current_hp=18,
            max_hp=18,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )
        requested = service.add_npc_combatant(
            "linden-pass",
            display_name="Requested Condition Focus",
            turn_value=10,
            current_hp=16,
            max_hp=16,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )

    sign_in(users["dm"]["email"], users["dm"]["password"])
    blank_add = client.post(
        f"/campaigns/linden-pass/combat/combatants/{first.id}/conditions",
        data={
            "combat_view": "dm",
            "view": "status",
            "combatant": first.id,
            "condition_name": "  ",
        },
        headers=_async_headers(),
        follow_redirects=False,
    )
    missing_update = client.post(
        "/campaigns/linden-pass/combat/conditions/999999",
        data={
            "combat_view": "dm",
            "view": "status",
            "combatant": requested.id,
            "condition_name": "Restrained",
        },
        headers=_async_headers(),
        follow_redirects=False,
    )
    missing_delete = client.post(
        "/campaigns/linden-pass/combat/conditions/999999/delete",
        data={
            "combat_view": "dm",
            "view": "status",
            "combatant": requested.id,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert blank_add.status_code == 200
    blank_payload = blank_add.get_json()
    assert blank_payload["ok"] is False
    assert blank_payload["anchor"] == f"combatant-{first.id}"
    assert blank_payload["selected_combatant_id"] == first.id
    assert "Condition name is required." in blank_payload["flash_html"]

    assert missing_update.status_code == 200
    update_payload = missing_update.get_json()
    assert update_payload["ok"] is False
    assert update_payload["anchor"] == f"combatant-{requested.id}"
    assert update_payload["selected_combatant_id"] == requested.id
    assert "That condition could not be found." in update_payload["flash_html"]

    assert missing_delete.status_code == 200
    delete_payload = missing_delete.get_json()
    assert delete_payload["ok"] is False
    assert delete_payload["anchor"] == "combat-tracker"
    assert delete_payload["selected_combatant_id"] == requested.id
    assert "That condition could not be found." in delete_payload["flash_html"]
    assert _list_conditions(app, first.id) == []


def test_unsupported_async_condition_add_returns_failed_payload_without_service_call(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"

    _write_campaign_config(app, _mutate)
    with app.app_context():
        service = app.extensions["campaign_combat_service"]

    def fail_add_condition(*args, **kwargs):
        raise AssertionError("unsupported combat must not call the condition service")

    monkeypatch.setattr(service, "add_condition", fail_add_condition)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.post(
        "/campaigns/linden-pass/combat/combatants/999999/conditions",
        data={
            "combat_view": "dm",
            "view": "status",
            "condition_name": "Blinded",
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Combat tracker support for Xianxia is not available yet." in payload["flash_html"]


def test_condition_successes_bump_live_revision_without_changing_combatant_revision(
    app,
    client,
    sign_in,
    users,
):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        combatant = service.add_npc_combatant(
            "linden-pass",
            display_name="Condition Revision Probe",
            turn_value=12,
            current_hp=18,
            max_hp=18,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )
        baseline_tracker = service.get_tracker("linden-pass")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    common_data = {
        "combat_view": "dm",
        "view": "status",
        "combatant": combatant.id,
    }
    add_response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/conditions",
        data={
            **common_data,
            "condition_name": "Grappled",
            "duration_text": "Until escaped",
        },
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert add_response.status_code == 200
    assert add_response.get_json()["ok"] is True

    conditions = _list_conditions(app, combatant.id)
    assert len(conditions) == 1
    assert conditions[0].created_by_user_id == users["dm"]["id"]
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        after_add_tracker = service.get_tracker("linden-pass")
        after_add_combatant = service.get_combatant("linden-pass", combatant.id)
    assert after_add_tracker.revision == baseline_tracker.revision + 1
    assert after_add_tracker.updated_by_user_id == users["dm"]["id"]
    assert add_response.get_json()["live_revision"] == after_add_tracker.revision
    assert after_add_combatant.revision == combatant.revision

    update_response = client.post(
        f"/campaigns/linden-pass/combat/conditions/{conditions[0].id}",
        data={
            **common_data,
            "condition_name": "Restrained",
            "duration_text": "One minute",
        },
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert update_response.status_code == 200
    assert update_response.get_json()["ok"] is True
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        after_update_tracker = service.get_tracker("linden-pass")
        after_update_combatant = service.get_combatant("linden-pass", combatant.id)
    assert after_update_tracker.revision == after_add_tracker.revision + 1
    assert after_update_tracker.updated_by_user_id == users["dm"]["id"]
    assert update_response.get_json()["live_revision"] == after_update_tracker.revision
    assert after_update_combatant.revision == combatant.revision

    refreshed_conditions = _list_conditions(app, combatant.id)
    assert len(refreshed_conditions) == 1
    assert refreshed_conditions[0].name == "Restrained"
    assert refreshed_conditions[0].duration_text == "One minute"
    assert refreshed_conditions[0].created_by_user_id == users["dm"]["id"]

    delete_response = client.post(
        f"/campaigns/linden-pass/combat/conditions/{refreshed_conditions[0].id}/delete",
        data=common_data,
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert delete_response.status_code == 200
    assert delete_response.get_json()["ok"] is True
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        after_delete_tracker = service.get_tracker("linden-pass")
        after_delete_combatant = service.get_combatant("linden-pass", combatant.id)
    assert after_delete_tracker.revision == after_update_tracker.revision + 1
    assert after_delete_tracker.updated_by_user_id is None
    assert delete_response.get_json()["live_revision"] == after_delete_tracker.revision
    assert after_delete_combatant.revision == combatant.revision
    assert _list_conditions(app, combatant.id) == []


def test_condition_success_and_failure_anchors_preserve_existing_asymmetries(
    app,
    client,
    sign_in,
    users,
):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        actual = service.add_npc_combatant(
            "linden-pass",
            display_name="Actual Condition Owner",
            turn_value=12,
            current_hp=18,
            max_hp=18,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )
        requested = service.add_npc_combatant(
            "linden-pass",
            display_name="Requested Condition Owner",
            turn_value=10,
            current_hp=16,
            max_hp=16,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )
        condition = service.add_condition(
            "linden-pass",
            actual.id,
            name="Grappled",
            created_by_user_id=users["dm"]["id"],
        )

    sign_in(users["dm"]["email"], users["dm"]["password"])
    update_success = client.post(
        f"/campaigns/linden-pass/combat/conditions/{condition.id}",
        data={"condition_name": "Restrained"},
        follow_redirects=False,
    )
    update_failure_with_focus = client.post(
        "/campaigns/linden-pass/combat/conditions/999999",
        data={"condition_name": "Restrained", "combatant": requested.id},
        follow_redirects=False,
    )
    update_failure_without_focus = client.post(
        "/campaigns/linden-pass/combat/conditions/999999",
        data={"condition_name": "Restrained"},
        follow_redirects=False,
    )
    delete_success = client.post(
        f"/campaigns/linden-pass/combat/conditions/{condition.id}/delete",
        data={"combatant": requested.id},
        follow_redirects=False,
    )

    assert update_success.status_code == 302
    assert update_success.headers["Location"].endswith(f"#combatant-{actual.id}")
    assert update_failure_with_focus.status_code == 302
    assert update_failure_with_focus.headers["Location"].endswith(
        f"?combatant={requested.id}#combatant-{requested.id}"
    )
    assert update_failure_without_focus.status_code == 302
    assert update_failure_without_focus.headers["Location"].endswith("#combat-tracker")
    assert delete_success.status_code == 302
    assert delete_success.headers["Location"].endswith(
        f"?combatant={requested.id}#combatant-{actual.id}"
    )


def test_async_dm_controls_clear_resets_tracker_and_cascades_dependents(
    app,
    client,
    sign_in,
    users,
):
    first, _ = _add_cleanup_probe_combatant(
        app,
        users,
        display_name="First Cleanup Probe",
        turn_value=18,
    )
    second, _ = _add_cleanup_probe_combatant(
        app,
        users,
        display_name="Second Cleanup Probe",
        turn_value=12,
    )
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        service.set_current_turn(
            "linden-pass",
            first.id,
            updated_by_user_id=users["dm"]["id"],
        )
        baseline_tracker = service.get_tracker("linden-pass")
    assert _combat_dependent_counts(app, [first.id, second.id]) == {
        "campaign_combat_conditions": 2,
        "campaign_combatant_resource_counters": 2,
        "campaign_combatant_resource_notes": 2,
    }

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.post(
        "/campaigns/linden-pass/combat/clear",
        data={
            "combat_view": "dm",
            "view": "controls",
            "combatant": first.id,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["anchor"] == "combat-summary"
    assert payload["selected_combatant_id"] is None
    assert payload["page_url"] == "/campaigns/linden-pass/combat/dm?view=controls"
    assert payload["live_url"] == "/campaigns/linden-pass/combat/dm/live-state?view=controls"
    assert "Combat tracker cleared." in payload["flash_html"]
    assert "controls_html" in payload
    assert "Clear tracker" in payload["controls_html"]
    assert "summary_html" not in payload
    assert "tracker_html" not in payload
    assert _list_combatants(app) == []
    tracker = _get_tracker(app)
    assert tracker.round_number == 1
    assert tracker.current_combatant_id is None
    assert tracker.revision == baseline_tracker.revision + 1
    assert tracker.updated_by_user_id == users["dm"]["id"]
    assert payload["live_revision"] == tracker.revision
    assert _combat_dependent_counts(app, [first.id, second.id]) == {
        "campaign_combat_conditions": 0,
        "campaign_combatant_resource_counters": 0,
        "campaign_combatant_resource_notes": 0,
    }


def test_async_dm_status_delete_falls_back_and_cascades_without_actor_attribution(
    app,
    client,
    sign_in,
    users,
):
    selected, _ = _add_cleanup_probe_combatant(
        app,
        users,
        display_name="Selected Cleanup Probe",
        turn_value=18,
    )
    survivor, _ = _add_cleanup_probe_combatant(
        app,
        users,
        display_name="Surviving Cleanup Probe",
        turn_value=12,
    )
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        service.set_current_turn(
            "linden-pass",
            selected.id,
            updated_by_user_id=users["dm"]["id"],
        )
        baseline_tracker = service.get_tracker("linden-pass")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{selected.id}/delete",
        data={
            "combat_view": "dm",
            "view": "status",
            "combatant": selected.id,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["anchor"] == "combat-tracker"
    assert payload["selected_combatant_id"] == survivor.id
    assert payload["page_url"] == f"/campaigns/linden-pass/combat/dm?combatant={survivor.id}"
    assert payload["live_url"] == f"/campaigns/linden-pass/combat/dm/live-state?combatant={survivor.id}"
    assert "Removed Selected Cleanup Probe from the combat tracker." in payload["flash_html"]
    assert "Surviving Cleanup Probe" in payload["tracker_html"]
    assert "Surviving Cleanup Probe" in payload["tracker_detail_html"]
    assert "Selected Cleanup Probe" not in payload["tracker_html"]
    assert "Selected Cleanup Probe" not in payload["tracker_detail_html"]
    assert _list_combatants(app) == [survivor]
    tracker = _get_tracker(app)
    assert tracker.current_combatant_id is None
    assert tracker.revision == baseline_tracker.revision + 1
    assert tracker.updated_by_user_id is None
    assert payload["live_revision"] == tracker.revision
    assert _combat_dependent_counts(app, [selected.id]) == {
        "campaign_combat_conditions": 0,
        "campaign_combatant_resource_counters": 0,
        "campaign_combatant_resource_notes": 0,
    }
    assert _combat_dependent_counts(app, [survivor.id]) == {
        "campaign_combat_conditions": 1,
        "campaign_combatant_resource_counters": 1,
        "campaign_combatant_resource_notes": 1,
    }


def test_unknown_async_combatant_delete_returns_failed_payload_without_change(
    app,
    client,
    sign_in,
    users,
):
    survivor, condition = _add_cleanup_probe_combatant(
        app,
        users,
        display_name="Unknown Delete Survivor",
        turn_value=12,
    )
    baseline_tracker = _get_tracker(app)
    baseline_counts = _combat_dependent_counts(app, [survivor.id])

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.post(
        "/campaigns/linden-pass/combat/combatants/999999/delete",
        data={
            "combat_view": "dm",
            "view": "status",
            "combatant": survivor.id,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["anchor"] == "combat-tracker"
    assert payload["selected_combatant_id"] == survivor.id
    assert "That combatant could not be found." in payload["flash_html"]
    assert _list_combatants(app) == [survivor]
    assert _list_conditions(app, survivor.id) == [condition]
    assert _get_tracker(app) == baseline_tracker
    assert _combat_dependent_counts(app, [survivor.id]) == baseline_counts


def test_assigned_player_cannot_delete_combatant(app, client, sign_in, users):
    combatant, condition = _add_cleanup_probe_combatant(
        app,
        users,
        display_name="Delete Guard",
        turn_value=12,
    )
    baseline_tracker = _get_tracker(app)
    baseline_counts = _combat_dependent_counts(app, [combatant.id])

    sign_in(users["owner"]["email"], users["owner"]["password"])
    response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/delete",
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert _list_combatants(app) == [combatant]
    assert _list_conditions(app, combatant.id) == [condition]
    assert _get_tracker(app) == baseline_tracker
    assert _combat_dependent_counts(app, [combatant.id]) == baseline_counts


def test_unsupported_cleanup_routes_return_failed_payloads_without_service_calls(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"

    _write_campaign_config(app, _mutate)
    with app.app_context():
        service = app.extensions["campaign_combat_service"]

    def fail_cleanup(*args, **kwargs):
        raise AssertionError("unsupported combat must not call cleanup services")

    monkeypatch.setattr(service, "clear_tracker", fail_cleanup)
    monkeypatch.setattr(service, "delete_combatant", fail_cleanup)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    clear_response = client.post(
        "/campaigns/linden-pass/combat/clear",
        data={"combat_view": "dm", "view": "controls"},
        headers=_async_headers(),
        follow_redirects=False,
    )
    delete_response = client.post(
        "/campaigns/linden-pass/combat/combatants/999999/delete",
        data={"combat_view": "dm", "view": "status"},
        headers=_async_headers(),
        follow_redirects=False,
    )

    for response in (clear_response, delete_response):
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is False
        assert "Combat tracker support for Xianxia is not available yet." in payload["flash_html"]


def test_cleanup_routes_preserve_injected_validation_failures_without_mutation(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    combatant, condition = _add_cleanup_probe_combatant(
        app,
        users,
        display_name="Injected Cleanup Guard",
        turn_value=12,
    )
    baseline_tracker = _get_tracker(app)
    baseline_counts = _combat_dependent_counts(app, [combatant.id])
    with app.app_context():
        service = app.extensions["campaign_combat_service"]

    def fail_clear(*args, **kwargs):
        raise campaign_combat_service_module.CampaignCombatValidationError(
            "Injected clear failure."
        )

    def fail_delete(*args, **kwargs):
        raise campaign_combat_service_module.CampaignCombatValidationError(
            "Injected delete failure."
        )

    monkeypatch.setattr(service, "clear_tracker", fail_clear)
    monkeypatch.setattr(service, "delete_combatant", fail_delete)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    clear_response = client.post(
        "/campaigns/linden-pass/combat/clear",
        data={"combat_view": "dm", "view": "controls", "combatant": combatant.id},
        headers=_async_headers(),
        follow_redirects=False,
    )
    delete_response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/delete",
        data={"combat_view": "dm", "view": "status", "combatant": combatant.id},
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert clear_response.status_code == 200
    clear_payload = clear_response.get_json()
    assert clear_payload["ok"] is False
    assert clear_payload["anchor"] == "combat-summary"
    assert "Injected clear failure." in clear_payload["flash_html"]
    assert delete_response.status_code == 200
    delete_payload = delete_response.get_json()
    assert delete_payload["ok"] is False
    assert delete_payload["anchor"] == "combat-tracker"
    assert "Injected delete failure." in delete_payload["flash_html"]
    assert _list_combatants(app) == [combatant]
    assert _list_conditions(app, combatant.id) == [condition]
    assert _get_tracker(app) == baseline_tracker
    assert _combat_dependent_counts(app, [combatant.id]) == baseline_counts


def test_cleanup_forms_render_csrf_tokens_and_csrf_blocks_before_mutation(
    app,
    client,
    sign_in,
    users,
):
    combatant, condition = _add_cleanup_probe_combatant(
        app,
        users,
        display_name="CSRF Cleanup Guard",
        turn_value=12,
    )
    baseline_tracker = _get_tracker(app)
    baseline_counts = _combat_dependent_counts(app, [combatant.id])

    sign_in(users["dm"]["email"], users["dm"]["password"])
    app.config["CSRF_ENABLED"] = True
    status_html = client.get(
        f"/campaigns/linden-pass/combat/dm?combatant={combatant.id}"
    ).get_data(as_text=True)
    controls_html = client.get(
        "/campaigns/linden-pass/combat/dm?view=controls"
    ).get_data(as_text=True)
    delete_form = re.search(
        rf'<form\b[^>]*action="/campaigns/linden-pass/combat/combatants/{combatant.id}/delete"[^>]*>(.*?)</form>',
        status_html,
        re.S,
    )
    clear_form = re.search(
        r'<form\b[^>]*action="/campaigns/linden-pass/combat/clear"[^>]*>(.*?)</form>',
        controls_html,
        re.S,
    )
    assert delete_form is not None
    assert clear_form is not None
    assert delete_form.group(1).count('name="_csrf_token"') == 1
    assert clear_form.group(1).count('name="_csrf_token"') == 1

    delete_response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/delete",
        follow_redirects=False,
    )
    clear_response = client.post(
        "/campaigns/linden-pass/combat/clear",
        follow_redirects=False,
    )
    assert delete_response.status_code == 400
    assert clear_response.status_code == 400
    assert _list_combatants(app) == [combatant]
    assert _list_conditions(app, combatant.id) == [condition]
    assert _get_tracker(app) == baseline_tracker
    assert _combat_dependent_counts(app, [combatant.id]) == baseline_counts


def test_dm_cleanup_confirmation_renders_proportional_scope_and_real_post_fallbacks(
    app,
    client,
    sign_in,
    users,
):
    combatant, _ = _add_cleanup_probe_combatant(
        app,
        users,
        display_name="Presentation Cleanup Guard",
        turn_value=12,
    )
    sign_in(users["dm"]["email"], users["dm"]["password"])

    status_response = client.get(
        f"/campaigns/linden-pass/combat/dm?combatant={combatant.id}"
    )
    controls_response = client.get(
        f"/campaigns/linden-pass/combat/dm?combatant={combatant.id}&view=controls"
    )
    assert status_response.status_code == 200
    assert controls_response.status_code == 200
    status_html = status_response.get_data(as_text=True)
    controls_html = controls_response.get_data(as_text=True)

    assert 'data-destructive-confirmation-risk="lower"' in status_html
    assert f'id="combat-remove-confirmation-{combatant.id}"' in status_html
    assert "Remove Presentation Cleanup Guard?" in status_html
    assert "this participant and their encounter-only conditions, resource counters, and resource notes" in status_html
    assert "linked character, statblock, Systems entry, and source records remain unchanged" in status_html
    assert 'name="destructive_acknowledgement"' not in status_html

    assert 'data-destructive-confirmation-risk="higher"' in controls_html
    assert 'id="combat-clear-confirmation"' in controls_html
    assert "Clear combat tracker?" in controls_html
    assert "all combatants and their encounter-only conditions, resource counters, and resource notes" in controls_html
    assert "Round resets to 1 and the current turn is cleared." in controls_html
    assert "Character sheets and source records remain unchanged." in controls_html
    assert controls_html.count('name="destructive_acknowledgement"') == 2
    assert controls_html.count("I understand this clears every combatant from this encounter.") == 2

    for html, action in (
        (status_html, f"/campaigns/linden-pass/combat/combatants/{combatant.id}/delete"),
        (controls_html, "/campaigns/linden-pass/combat/clear"),
    ):
        assert html.count(f'action="{action}"') == 2
        assert html.count("The result could not be confirmed. Refresh Combat before repeating this action.") == 1
        assert "<noscript>" in html
        assert "onclick=" not in html
        assert "onsubmit=" not in html

    enhanced_remove_form = re.search(
        rf'<form\b[^>]*action="/campaigns/linden-pass/combat/combatants/{combatant.id}/delete"[^>]*data-destructive-confirmation-form[^>]*>(.*?)</form>',
        status_html,
        re.S,
    )
    enhanced_clear_form = re.search(
        r'<form\b[^>]*action="/campaigns/linden-pass/combat/clear"[^>]*data-destructive-confirmation-form[^>]*>(.*?)</form>',
        controls_html,
        re.S,
    )
    assert enhanced_remove_form is not None
    assert enhanced_clear_form is not None
    assert enhanced_remove_form.group(1).count('name="_csrf_token"') == 1
    assert enhanced_clear_form.group(1).count('name="_csrf_token"') == 1
    assert 'name="combat_view" value="dm"' in enhanced_remove_form.group(1)
    assert 'name="view" value="status"' in enhanced_remove_form.group(1)
    assert 'name="view" value="controls"' in enhanced_clear_form.group(1)


def test_async_combat_resource_update_rejects_stale_combatant_revision(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    combatant = _find_combatant(app, name="Clockwork Hound")
    assert combatant is not None

    first_response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/resources",
        data={
            "combat_view": "status",
            "combatant": combatant.id,
            "expected_combatant_revision": combatant.revision,
            "has_action": "1",
            "has_bonus_action": "1",
            "has_reaction": "1",
            "movement_remaining": 10,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert first_response.status_code == 200
    assert "Combat resources updated." in first_response.get_json()["flash_html"]

    refreshed = _find_combatant(app, name="Clockwork Hound")
    assert refreshed is not None
    assert refreshed.movement_remaining == 10

    stale_response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/resources",
        data={
            "combat_view": "status",
            "combatant": combatant.id,
            "expected_combatant_revision": combatant.revision,
            "has_action": "1",
            "has_bonus_action": "0",
            "has_reaction": "0",
            "movement_remaining": 5,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert stale_response.status_code == 200
    assert stale_response.headers["X-Live-Mutation-Outcome"] == "combatant-revision-conflict"
    stale_payload = stale_response.get_json()
    assert "This combatant changed in another combat view. Refresh and try again." in stale_payload["flash_html"]

    unchanged = _find_combatant(app, name="Clockwork Hound")
    assert unchanged is not None
    assert unchanged.revision == refreshed.revision
    assert unchanged.movement_remaining == 10
    assert unchanged.has_bonus_action is True
    assert unchanged.has_reaction is True

    redirect_response = client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
            "combat_view": "dm",
        },
        follow_redirects=False,
    )

    assert redirect_response.status_code == 302
    assert redirect_response.headers["Location"].endswith("/campaigns/linden-pass/combat/dm#combat-tracker")


def test_dm_pages_split_tactical_status_edits_from_control_authority_actions(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )
    hound = _find_combatant(app, name="Clockwork Hound")
    assert hound is not None
    client.post(
        f"/campaigns/linden-pass/combat/combatants/{hound.id}/conditions",
        data={"condition_name": "Grappled", "duration_text": "Until escaped"},
        follow_redirects=False,
    )

    status_dm_response = client.get(f"/campaigns/linden-pass/combat/dm?combatant={hound.id}")
    controls_response = client.get(
        f"/campaigns/linden-pass/combat/dm?combatant={hound.id}&view=controls"
    )

    assert status_dm_response.status_code == 200
    assert controls_response.status_code == 200

    status_dm_body = status_dm_response.get_data(as_text=True)
    controls_body = controls_response.get_data(as_text=True)

    assert "Status edits" not in status_dm_body
    assert 'id="combat-status-snapshot"' in status_dm_body
    assert 'name="combat_view" value="dm"' in status_dm_body
    assert 'name="view" value="status"' in status_dm_body
    assert 'data-combat-inline-autosubmit' in status_dm_body
    assert 'aria-label="Current HP for Clockwork Hound"' in status_dm_body
    assert 'aria-label="Temp HP for Clockwork Hound"' in status_dm_body
    assert 'aria-label="Remaining movement for Clockwork Hound"' in status_dm_body
    assert "Save HP" not in status_dm_body
    assert "Save temp HP" not in status_dm_body
    assert "Save movement" not in status_dm_body
    assert "Save action economy" not in status_dm_body
    assert "Set current" in status_dm_body
    assert "Add condition" in status_dm_body
    assert "Save condition" in status_dm_body
    assert "Remove" in status_dm_body
    combat_script = _combat_live_script_text()
    assert "hasFocusedFormControl" in combat_script
    assert "queueInlineSubmit" in combat_script
    _assert_expected_combatant_revision_field(status_dm_body, hound.revision, at_least=4)

    assert "Selected combatant authority" in status_dm_body
    assert "Open Encounter status" not in controls_body
    assert "Save turn order" in status_dm_body
    assert "Priority" in status_dm_body
    assert "Selected combatant authority" not in controls_body
    assert "Save turn order" not in controls_body
    assert "Show NPC detail to players" in status_dm_body
    assert "Save NPC structure" in status_dm_body
    _assert_expected_combatant_revision_field(status_dm_body, hound.revision, at_least=3)
    assert "Remove combatant" in status_dm_body
    assert "Save HP" not in controls_body
    assert "Save temp HP" not in controls_body
    assert "Save movement" not in controls_body
    assert "Save action economy" not in controls_body


def test_status_page_async_mutations_return_status_partials_and_keep_selected_target(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )
    hound = _find_combatant(app, name="Clockwork Hound")
    assert hound is not None

    response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{hound.id}/resources",
        data={
            "combat_view": "status",
            "combatant": hound.id,
            "expected_combatant_revision": hound.revision,
            "has_action": "1",
            "movement_remaining": 10,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["selected_combatant_id"] == hound.id
    assert "Combat resources updated." in payload["flash_html"]
    assert "combat-status-snapshot" in payload["detail_html"]
    assert 'name="combat_view" value="status"' in payload["detail_html"]
    assert 'data-combat-inline-autosubmit' in payload["detail_html"]
    assert 'aria-label="Remaining movement for Clockwork Hound"' in payload["detail_html"]
    assert "Save movement" not in payload["detail_html"]
    assert "Turn order" in payload["board_html"]
    refreshed = _find_combatant(app, name="Clockwork Hound")
    assert refreshed is not None
    _assert_expected_combatant_revision_field(payload["detail_html"], refreshed.revision, at_least=4)


def test_dm_status_async_resource_update_returns_dm_status_live_payload(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )
    hound = _find_combatant(app, name="Clockwork Hound")
    assert hound is not None

    response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{hound.id}/resources",
        data={
            "combat_view": "dm",
            "view": "status",
            "combatant": hound.id,
            "expected_combatant_revision": hound.revision,
            "has_action": "1",
            "movement_remaining": 10,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["selected_combatant_id"] == hound.id
    assert payload["page_url"] == f"/campaigns/linden-pass/combat/dm?combatant={hound.id}"
    assert payload["live_url"] == f"/campaigns/linden-pass/combat/dm/live-state?combatant={hound.id}"
    assert "combat-status-snapshot" in payload["tracker_detail_html"]
    assert 'data-combat-inline-autosubmit' in payload["tracker_detail_html"]
    assert 'aria-label="Remaining movement for Clockwork Hound"' in payload["tracker_detail_html"]
    assert "Save movement" not in payload["tracker_detail_html"]
    refreshed_hound = _find_combatant(app, name="Clockwork Hound")
    assert refreshed_hound is not None
    _assert_expected_combatant_revision_field(
        payload["tracker_detail_html"],
        refreshed_hound.revision,
        at_least=3,
    )


def test_dm_status_async_condition_mutations_keep_selected_combatant(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )
    hound = _find_combatant(app, name="Clockwork Hound")
    assert hound is not None

    add_response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{hound.id}/conditions",
        data={
            "combat_view": "dm",
            "view": "status",
            "combatant": hound.id,
            "condition_name": "Grappled",
            "duration_text": "Until escaped",
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert add_response.status_code == 200
    add_payload = add_response.get_json()
    assert add_payload["ok"] is True
    assert add_payload["selected_combatant_id"] == hound.id
    assert "Grappled" in add_payload["tracker_detail_html"]
    assert "Until escaped" in add_payload["tracker_detail_html"]

    conditions = _list_conditions(app, hound.id)
    assert len(conditions) == 1

    update_response = client.post(
        f"/campaigns/linden-pass/combat/conditions/{conditions[0].id}",
        data={
            "combat_view": "dm",
            "view": "status",
            "combatant": hound.id,
            "condition_name": "Restrained",
            "duration_text": "One minute",
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert update_response.status_code == 200
    update_payload = update_response.get_json()
    assert update_payload["ok"] is True
    assert update_payload["selected_combatant_id"] == hound.id
    assert "Restrained" in update_payload["tracker_detail_html"]
    assert "One minute" in update_payload["tracker_detail_html"]
    assert "Grappled" not in update_payload["tracker_detail_html"]

    conditions = _list_conditions(app, hound.id)
    assert len(conditions) == 1

    delete_response = client.post(
        f"/campaigns/linden-pass/combat/conditions/{conditions[0].id}/delete",
        data={
            "combat_view": "dm",
            "view": "status",
            "combatant": hound.id,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert delete_response.status_code == 200
    delete_payload = delete_response.get_json()
    assert delete_payload["ok"] is True
    assert delete_payload["selected_combatant_id"] == hound.id
    assert "No conditions are active on this combatant." in delete_payload["tracker_detail_html"]
    assert _list_conditions(app, hound.id) == []


def test_dm_can_add_player_character_and_npc_combatants_and_turn_order_sorts_high_to_low(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    player_add = client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18, "initiative_priority": 4},
        follow_redirects=False,
    )
    npc_add = client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
            "initiative_priority": 2,
        },
        follow_redirects=False,
    )

    assert player_add.status_code == 302
    assert npc_add.status_code == 302

    combatants = _list_combatants(app)
    assert [combatant.display_name for combatant in combatants] == [
        "Arden March",
        "Clockwork Hound",
    ]
    assert combatants[0].turn_value == 18
    assert combatants[0].initiative_priority == 4
    assert combatants[1].current_hp == 22
    assert combatants[1].movement_total == 40
    assert combatants[1].dexterity_modifier == 0
    assert combatants[1].initiative_priority == 2


def test_turn_order_uses_dexterity_modifier_then_dm_priority_for_ties(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    arden_definition_path = (
        app.config["TEST_CAMPAIGNS_DIR"]
        / "linden-pass"
        / "characters"
        / "arden-march"
        / "definition.yaml"
    )
    arden_payload = yaml.safe_load(arden_definition_path.read_text(encoding="utf-8")) or {}
    arden_payload["stats"]["initiative_bonus"] = 8
    arden_ability_scores = dict(arden_payload["stats"].get("ability_scores") or {})
    arden_ability_scores["dexterity"] = dict(arden_ability_scores.pop("dex"))
    arden_payload["stats"]["ability_scores"] = arden_ability_scores
    arden_definition_path.write_text(yaml.safe_dump(arden_payload, sort_keys=False), encoding="utf-8")

    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 15},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "selene-brook", "turn_value": 15},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Alpha Guard",
            "turn_value": 15,
            "dexterity_modifier": 3,
            "current_hp": 10,
            "max_hp": 10,
            "movement_total": 30,
        },
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Beta Guard",
            "turn_value": 15,
            "dexterity_modifier": 3,
            "initiative_priority": 1,
            "current_hp": 10,
            "max_hp": 10,
            "movement_total": 30,
        },
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Slow Guard",
            "turn_value": 15,
            "dexterity_modifier": 1,
            "current_hp": 10,
            "max_hp": 10,
            "movement_total": 30,
        },
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Zeta Guard",
            "turn_value": 15,
            "dexterity_modifier": 3,
            "current_hp": 10,
            "max_hp": 10,
            "movement_total": 30,
        },
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Gamma Guard",
            "turn_value": 15,
            "dexterity_modifier": 3,
            "current_hp": 10,
            "max_hp": 10,
            "movement_total": 30,
        },
        follow_redirects=False,
    )

    alpha = _find_combatant(app, name="Alpha Guard")
    beta = _find_combatant(app, name="Beta Guard")
    assert alpha is not None
    assert beta is not None

    client.post(
        f"/campaigns/linden-pass/combat/combatants/{alpha.id}/turn",
        data={
            "turn_value": 15,
            "initiative_priority": 2,
            "expected_combatant_revision": alpha.revision,
        },
        follow_redirects=False,
    )
    combatants = _list_combatants(app)
    assert [combatant.display_name for combatant in combatants] == [
        "Beta Guard",
        "Gamma Guard",
        "Selene Brook",
        "Zeta Guard",
        "Alpha Guard",
        "Arden March",
        "Slow Guard",
    ]
    assert _find_combatant(app, character_slug="arden-march").dexterity_modifier == 2
    assert _find_combatant(app, name="Beta Guard").initiative_priority == 1
    assert _find_combatant(app, name="Alpha Guard").initiative_priority == 2

    alpha = _find_combatant(app, name="Alpha Guard")
    assert alpha is not None
    client.post(
        f"/campaigns/linden-pass/combat/combatants/{alpha.id}/turn",
        data={
            "turn_value": 15,
            "initiative_priority": "",
            "expected_combatant_revision": alpha.revision,
        },
        follow_redirects=False,
    )

    combatants = _list_combatants(app)
    assert _find_combatant(app, name="Alpha Guard").initiative_priority == 1
    assert [combatant.display_name for combatant in combatants][:5] == [
        "Alpha Guard",
        "Beta Guard",
        "Gamma Guard",
        "Selene Brook",
        "Zeta Guard",
    ]


def test_dm_content_statblock_seeds_dex_modifier_separately_from_initiative_bonus(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    statblock = _create_dm_statblock(
        app,
        created_by_user_id=users["dm"]["id"],
        filename="alert-guard.md",
        markdown_text="""---
title: Alert Guard
armor_class: 14
hp: 24
speed: 30 ft.
initiative_bonus: 7
---

STR 10 (+0)  DEX 14 (+2)  CON 12 (+1)  INT 10 (+0)  WIS 10 (+0)  CHA 10 (+0)

## Actions

### Spear

+4 to hit, 5 piercing damage.
""",
    )

    response = client.post(
        "/campaigns/linden-pass/combat/statblock-combatants",
        data={"statblock_id": statblock.id},
        follow_redirects=False,
    )

    assert response.status_code == 302
    combatant = _find_combatant(app, name="Alert Guard")
    assert combatant is not None
    assert combatant.turn_value == 7
    assert combatant.initiative_bonus == 7
    assert combatant.dexterity_modifier == 2


def test_dm_can_set_current_turn_and_advance_turn_refreshing_resources(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    glenn = _find_combatant(app, character_slug="arden-march")
    hound = _find_combatant(app, name="Clockwork Hound")
    assert glenn is not None
    assert hound is not None

    client.post(
        f"/campaigns/linden-pass/combat/combatants/{glenn.id}/resources",
        data={
            "movement_remaining": 0,
        },
        follow_redirects=False,
    )

    updated_glenn = _find_combatant(app, character_slug="arden-march")
    assert updated_glenn is not None
    assert updated_glenn.has_action is False
    assert updated_glenn.has_bonus_action is False
    assert updated_glenn.has_reaction is False
    assert updated_glenn.movement_remaining == 0

    set_current = client.post(
        f"/campaigns/linden-pass/combat/combatants/{glenn.id}/set-current",
        follow_redirects=False,
    )
    assert set_current.status_code == 302

    refreshed_glenn = _find_combatant(app, character_slug="arden-march")
    tracker = _get_tracker(app)
    assert refreshed_glenn is not None
    assert refreshed_glenn.has_action is True
    assert refreshed_glenn.has_bonus_action is True
    assert refreshed_glenn.has_reaction is True
    assert refreshed_glenn.movement_remaining == refreshed_glenn.movement_total
    assert tracker.current_combatant_id == glenn.id
    assert tracker.round_number == 1

    first_advance = client.post(
        "/campaigns/linden-pass/combat/advance-turn",
        follow_redirects=False,
    )
    assert first_advance.status_code == 302
    tracker = _get_tracker(app)
    assert tracker.current_combatant_id == hound.id
    assert tracker.round_number == 1

    second_advance = client.post(
        "/campaigns/linden-pass/combat/advance-turn",
        follow_redirects=False,
    )
    assert second_advance.status_code == 302
    tracker = _get_tracker(app)
    assert tracker.current_combatant_id == glenn.id
    assert tracker.round_number == 2


def test_combat_set_current_turn_batches_resource_and_tracker_commit(app, users):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        combatant = service.add_npc_combatant(
            TEST_CAMPAIGN_SLUG,
            display_name="Commit Probe",
            turn_value=12,
            current_hp=9,
            max_hp=9,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )

        reset_db_query_metrics()
        service.set_current_turn(
            TEST_CAMPAIGN_SLUG,
            combatant.id,
            updated_by_user_id=users["dm"]["id"],
        )
        metrics = get_db_query_metrics()

    assert metrics["write_count"] >= 2
    assert metrics["commit_count"] == 1
    assert metrics["rollback_count"] == 0


def test_owner_player_can_update_own_pc_vitals_from_combat_tracker(
    app, client, sign_in, users, get_character
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    combatant = _find_combatant(app, character_slug="arden-march")
    assert record is not None
    assert combatant is not None

    response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/vitals",
        data={
            "expected_revision": record.state_record.revision,
            "current_hp": 35,
            "temp_hp": 4,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    updated_record = get_character("arden-march")
    updated_combatant = _find_combatant(app, character_slug="arden-march")
    assert updated_record.state_record.state["vitals"]["current_hp"] == 35
    assert updated_record.state_record.state["vitals"]["temp_hp"] == 4
    assert updated_combatant is not None
    assert updated_combatant.current_hp == 35
    assert updated_combatant.temp_hp == 4


def test_owner_player_sees_inline_edit_controls_on_owned_tracked_pc(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/combat")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-combat-inline-autosubmit' in body
    assert 'aria-label="Current HP for Arden March"' in body
    assert 'aria-label="Temp HP for Arden March"' in body
    assert 'aria-label="Remaining movement for Arden March"' in body
    assert "Save vitals" not in body
    assert "Save resources" not in body
    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None
    _assert_expected_combatant_revision_field(body, arden.revision, at_least=4)


def test_owner_player_combat_live_state_keeps_combatant_revision_guards_in_workspace_snapshot(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None

    response = client.get(
        f"/campaigns/linden-pass/combat/live-state?combatant={arden.id}",
        headers=_async_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["selected_combatant_id"] == arden.id
    assert "Arden March" in payload["summary_html"]
    _assert_expected_combatant_revision_field(payload["summary_html"], arden.revision, at_least=4)


def test_owner_player_combat_live_state_reuses_player_workspace_sections_when_detail_state_token_unchanged(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    hound = _find_combatant(app, name="Clockwork Hound")
    assert arden is not None
    assert hound is not None

    sign_in(users["owner"]["email"], users["owner"]["password"])

    original_render_template = app_module.render_template
    render_calls = {"combat_player_workspace_sections": 0}

    def _count_player_workspace_sections(template_name, **context):
        if template_name == "_combat_player_workspace_sections.html":
            render_calls["combat_player_workspace_sections"] += 1
        return original_render_template(template_name, **context)

    monkeypatch.setattr(app_module, "render_template", _count_player_workspace_sections)

    initial_live_state = client.get(
        f"/campaigns/linden-pass/combat/live-state?combatant={arden.id}",
        headers=_async_headers(),
    )
    assert initial_live_state.status_code == 200
    initial_payload = initial_live_state.get_json()
    assert initial_payload["changed"] is True
    assert "tracker_html" in initial_payload
    assert "summary_html" in initial_payload
    assert initial_payload["combatant_detail_state_token"]
    initial_summary_html = initial_payload["summary_html"]
    initial_tracker_render_calls = render_calls["combat_player_workspace_sections"]
    assert initial_tracker_render_calls == 1

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        f"/campaigns/linden-pass/combat/combatants/{hound.id}/turn",
        data={
            "expected_combatant_revision": hound.revision,
            "turn_value": 8,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    sign_in(users["owner"]["email"], users["owner"]["password"])
    unchanged_live_state = client.get(
        f"/campaigns/linden-pass/combat/live-state?combatant={arden.id}",
        headers=_live_poll_headers(
            initial_payload["live_revision"],
            initial_payload["live_view_token"],
            initial_payload["combatant_detail_state_token"],
        ),
    )
    assert unchanged_live_state.status_code == 200
    unchanged_payload = unchanged_live_state.get_json()
    assert unchanged_payload["changed"] is True
    assert unchanged_payload["selected_combatant_id"] == arden.id
    assert unchanged_payload["combatant_detail_state_token"] == initial_payload["combatant_detail_state_token"]
    assert "tracker_html" not in unchanged_payload
    assert "summary_html" in unchanged_payload
    assert unchanged_payload["summary_html"] != initial_summary_html
    assert render_calls["combat_player_workspace_sections"] == initial_tracker_render_calls

    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None
    client.post(
        f"/campaigns/linden-pass/combat/combatants/{arden.id}/resources",
        data={
            "expected_combatant_revision": arden.revision,
            "movement_remaining": 8,
            "has_action": "1",
            "has_bonus_action": "1",
            "has_reaction": "1",
        },
        follow_redirects=False,
    )

    changed_detail_live_state = client.get(
        f"/campaigns/linden-pass/combat/live-state?combatant={arden.id}",
        headers=_live_poll_headers(
            unchanged_payload["live_revision"],
            unchanged_payload["live_view_token"],
            unchanged_payload["combatant_detail_state_token"],
        ),
    )
    assert changed_detail_live_state.status_code == 200
    changed_detail_payload = changed_detail_live_state.get_json()
    assert changed_detail_payload["changed"] is True
    assert changed_detail_payload["combatant_detail_state_token"] != unchanged_payload["combatant_detail_state_token"]
    assert "tracker_html" in changed_detail_payload
    assert render_calls["combat_player_workspace_sections"] == initial_tracker_render_calls + 1


def test_dm_combat_dm_live_state_keeps_selected_combatant_revision_guards(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )
    hound = _find_combatant(app, name="Clockwork Hound")
    assert hound is not None

    response = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={hound.id}",
        headers=_async_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["selected_combatant_id"] == hound.id
    assert "Selected combatant authority" in payload["tracker_authority_html"]
    _assert_expected_combatant_revision_field(payload["tracker_detail_html"], hound.revision, at_least=3)
    _assert_expected_combatant_revision_field(payload["tracker_authority_html"], hound.revision, at_least=1)


def test_owner_player_combat_page_uses_character_workspace_layout(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    definition_path = (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / "linden-pass"
        / "characters"
        / "arden-march"
        / "definition.yaml"
    )
    definition_payload = yaml.safe_load(definition_path.read_text(encoding="utf-8")) or {}
    spellcasting = dict(definition_payload.get("spellcasting") or {})
    source_row_id = "feature-spell-source:test-mage-initiate"
    spellcasting["class_rows"] = [
        {
            "class_row_id": "class-row-1",
            "class_name": "Sorcerer",
            "level": 5,
            "spellcasting_ability": "Charisma",
            "spell_save_dc": 15,
            "spell_attack_bonus": 7,
            "spell_mode": "known",
        }
    ]
    spellcasting["source_rows"] = [
        {
            "source_row_id": source_row_id,
            "source_row_kind": "feat",
            "title": "Test Mage Initiate",
        }
    ]
    spellcasting["spells"] = list(spellcasting.get("spells") or []) + [
        {
            "name": "Borrowed Spark",
            "mark": "Known",
            "casting_time": "1 action",
            "range": "Self",
            "duration": "Instantaneous",
            "components": "V",
            "spell_source_row_id": source_row_id,
            "spell_source_row_kind": "feat",
            "spell_source_row_title": "Test Mage Initiate",
            "grant_source_label": "Test Mage Initiate",
        }
    ]
    definition_payload["spellcasting"] = spellcasting
    definition_path.write_text(yaml.safe_dump(definition_payload, sort_keys=False), encoding="utf-8")

    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/combat")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Combat workspace" in body
    assert "Combat sections" in body
    assert "Turn order" in body
    assert 'class="section-list combat-workspace-stack"' in body
    assert 'data-combat-section-toggle="actions"' not in body
    assert 'data-combat-section-toggle="bonus_actions"' not in body
    assert 'data-combat-section-toggle="reactions"' not in body
    assert 'data-combat-section-toggle="attacks"' in body
    assert 'data-combat-section-toggle="spells"' in body
    assert 'data-combat-section-toggle="resources"' in body
    assert "Abilities and Skills" in body
    assert 'class="ability-grid ability-grid--skills"' in body
    assert "ability-skill-list" in body
    assert "<h3>Skills</h3>" not in body
    assert "Selected / inspected" in body
    assert "combat-spellcasting-panel" in body
    assert "combat-spell-slot-row" in body
    assert "spell-slot-editor-list spell-slot-editor-list--compact combat-spell-slot-list" in body
    assert "spell-level-section" in body
    assert body.count("combat-spellcasting-summary") == 1
    assert body.count("Save DC 15") >= 1
    assert body.count("Attack +7") >= 1
    normalized_body = re.sub(r"\s+", " ", body)
    assert normalized_body.count("Charisma spellcasting | Save DC 15 | Attack +7") >= 1
    assert "Test Mage Initiate" in body
    assert "Borrowed Spark" in body
    assert "Current limits" not in body
    assert "Encounter context" not in body


def test_player_combat_workspace_hides_empty_sections_until_they_have_content(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])
    initial_response = client.get("/campaigns/linden-pass/combat")

    assert initial_response.status_code == 200
    initial_body = initial_response.get_data(as_text=True)
    assert 'data-combat-section-toggle="actions"' not in initial_body
    assert 'data-combat-section-toggle="bonus_actions"' not in initial_body
    assert 'data-combat-section-toggle="attacks"' in initial_body

    def _add_bonus_action_feature(payload: dict) -> None:
        features = [dict(feature or {}) for feature in list(payload.get("features") or [])]
        features.append(
            {
                "id": "quickened-test",
                "name": "Quickened Test",
                "category": "class_feature",
                "description_markdown": "Use a spark of training as a bonus action.",
                "activation_type": "bonus_action",
            }
        )
        payload["features"] = features

    _write_character_definition(app, "arden-march", _add_bonus_action_feature)
    changed_response = client.get("/campaigns/linden-pass/combat")

    assert changed_response.status_code == 200
    changed_body = changed_response.get_data(as_text=True)
    assert 'data-combat-section-toggle="bonus_actions"' in changed_body
    assert 'data-combat-section-panel="bonus_actions"' in changed_body
    assert "Quickened Test" in changed_body


def test_owner_player_combat_page_uses_full_width_workspace_layout_and_preserves_live_rerender_state(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )
    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None
    client.post(
        f"/campaigns/linden-pass/combat/combatants/{arden.id}/set-current",
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get(f"/campaigns/linden-pass/combat?combatant={arden.id}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert 'class="page-layout combat-layout combat-layout--workspace"' in body
    assert "data-combat-live-root" in body
    assert 'data-combat-context-root hidden' in body
    assert 'class="sidebar combat-sidebar-stack"' not in body

    summary_root = body.find('data-combat-summary-root')
    carousel = body.find('data-combatant-carousel')
    jump = body.find('data-combatant-carousel-jump')
    tracker_root = body.find('data-combat-tracker-root')
    snapshot = body.find('id="combat-character-snapshot"')
    assert summary_root != -1
    assert carousel != -1
    assert jump != -1
    assert tracker_root != -1
    assert snapshot != -1
    assert summary_root < carousel < jump < snapshot < tracker_root

    assert 'data-combatant-current-turn="' in body
    assert "combat-turn-order-row--current" in body
    assert "combat-turn-order-row--selected" in body
    selected_option_match = re.search(r'<option[^>]*value="(\d+)"[^>]*selected="selected"', body)
    assert selected_option_match is not None

    selected_option_id = selected_option_match.group(1)
    selected_card_match = re.search(
        r'<article[^>]*aria-current="true"[^>]*data-combatant-id="(\d+)"',
        body,
    )
    assert selected_card_match is not None
    assert selected_option_id == selected_card_match.group(1)

    combat_script = _combat_live_script_text()
    jump_select_anchor = combat_script.find('if (target.matches("[data-combatant-carousel-jump-select]"))')
    change_handler_anchor = combat_script.find('liveRoot.addEventListener("change", async (event) => {')
    assert change_handler_anchor != -1
    assert jump_select_anchor != -1
    assert change_handler_anchor < jump_select_anchor

    assert "const getDefaultCombatantCarouselCard" in combat_script
    assert "const scrollToDefaultCombatantCarouselCard" in combat_script
    assert "const captureCombatantCarouselState = (scope = liveRoot) => {" in combat_script
    assert "const restoreCombatantCarouselState = (scope = liveRoot, carouselStates = []) => {" in combat_script
    assert "const workspaceSectionState = combatWorkspaceTools ? combatWorkspaceTools.capture(liveRoot) : \"\";" in combat_script
    assert "combatWorkspaceTools.restore(liveRoot, workspaceSectionState);" in combat_script

    render_payload_anchor = combat_script.find(
        'const renderPayload = (payload, { force = false, forceFlash = false } = {}) => {'
    )
    assert render_payload_anchor != -1
    refresh_payload_anchor = combat_script.find("const refreshLiveState = async ({", render_payload_anchor)
    assert refresh_payload_anchor != -1
    render_payload_block = combat_script[render_payload_anchor:refresh_payload_anchor]
    assert "const carouselState = captureCombatantCarouselState(liveRoot);" in render_payload_block
    assert "restoreCombatantCarouselState(liveRoot, carouselState);" in render_payload_block
    assert "if (combatantCarouselUserIntentObserved) {" in render_payload_block


def test_owner_player_combat_workspace_links_back_to_session_character_when_session_is_active(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    response = client.get("/campaigns/linden-pass/combat")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Session relationship" in body
    assert "Keep Combat for" in body
    assert "Keep Session for" in body
    assert (
        "HP, temp HP, tracked resources, spell slot usage, rests, inventory quantities, "
        "currency, and notes"
    ) in body
    assert '/campaigns/linden-pass/session/character?character=arden-march' in body
    assert '>Open Session Character<' in body
    assert '>Open Session<' in body
    assert "The Session Character link keeps this same sheet selected from the Session feature." in body


def test_owner_player_can_open_combat_character_page_for_assigned_tracked_pc(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    combat_page = client.get("/campaigns/linden-pass/combat")
    response = client.get("/campaigns/linden-pass/combat/character")

    assert combat_page.status_code == 200
    assert response.status_code == 200
    combat_html = combat_page.get_data(as_text=True)
    body = response.get_data(as_text=True)
    assert 'aria-label="Combat pages"' not in combat_html
    assert f'data-combat-live-url="/campaigns/linden-pass/combat/live-state?combatant={combatant.id}"' in combat_html
    assert "Combat Character" in body
    assert "Arden March" in body
    assert "Combat snapshot" in body
    assert "Tracked player characters" in body
    assert 'class="section-list combat-workspace-stack"' in body
    assert "Open full sheet" not in body
    assert 'data-live-active-interval-ms="500"' in body
    assert 'data-live-idle-interval-ms="3000"' in body


def test_dm_combat_character_route_redirects_to_status_for_selected_target(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    response = client.get(
        f"/campaigns/linden-pass/combat/character?combatant={combatant.id}",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/campaigns/linden-pass/combat/status?combatant={combatant.id}"
    )


def test_player_without_owned_tracked_pc_gets_combat_character_empty_state(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    combat_page = client.get("/campaigns/linden-pass/combat")
    response = client.get("/campaigns/linden-pass/combat/character")

    assert combat_page.status_code == 200
    assert response.status_code == 200
    assert "/campaigns/linden-pass/combat/character" not in combat_page.get_data(as_text=True)
    body = response.get_data(as_text=True)
    assert "No tracked player character available" in body


def test_unassigned_player_cannot_open_other_pc_combat_character_page(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.get("/campaigns/linden-pass/combat/character?character=arden-march")

    assert response.status_code == 403


def test_unassigned_player_cannot_update_other_pc_combat_vitals(app, client, sign_in, users, get_character):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "selene-brook", "turn_value": 14},
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    record = get_character("selene-brook")
    combatant = _find_combatant(app, character_slug="selene-brook")
    assert record is not None
    assert combatant is not None

    response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/vitals",
        data={
            "expected_revision": record.state_record.revision,
            "current_hp": 40,
            "temp_hp": 0,
        },
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_owner_player_can_update_own_pc_resources_from_combat_views(
    app, client, sign_in, users, get_character
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    tracker_resources = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/resources",
        data={"movement_remaining": 5},
        follow_redirects=False,
    )

    assert tracker_resources.status_code == 302
    updated_combatant = _find_combatant(app, character_slug="arden-march")
    assert updated_combatant is not None
    assert updated_combatant.has_action is False
    assert updated_combatant.has_bonus_action is False
    assert updated_combatant.has_reaction is False
    assert updated_combatant.movement_remaining == 5

    record = get_character("arden-march")
    resource_response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}/resources/sorcery-points",
        data={"expected_revision": record.state_record.revision, "current": 3},
        follow_redirects=False,
    )

    assert resource_response.status_code == 302
    record = get_character("arden-march")
    resources = {item["id"]: item for item in record.state_record.state["resources"]}
    assert resources["sorcery-points"]["current"] == 3

    spell_response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}/spell-slots/2",
        data={"expected_revision": record.state_record.revision, "used": 2},
        follow_redirects=False,
    )

    assert spell_response.status_code == 302
    record = get_character("arden-march")
    spell_slots = {item["level"]: item for item in record.state_record.state["spell_slots"]}
    assert spell_slots[2]["used"] == 2

    spell_delta_response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}/spell-slots/2",
        data={
            "expected_revision": record.state_record.revision,
            "used": 2,
            "delta_used": 1,
        },
        follow_redirects=False,
    )

    assert spell_delta_response.status_code == 302
    record = get_character("arden-march")
    spell_slots = {item["level"]: item for item in record.state_record.state["spell_slots"]}
    assert spell_slots[2]["used"] == 3


def test_owner_player_async_spell_slot_delta_returns_updated_workspace_html(
    app, client, sign_in, users, get_character
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    page = client.get(f"/campaigns/linden-pass/combat?combatant={combatant.id}")
    assert page.status_code == 200
    assert "combat-spell-slot-row" in page.get_data(as_text=True)

    record = get_character("arden-march")
    response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}/spell-slots/2",
        data={
            "expected_revision": record.state_record.revision,
            "combat_view": "combat",
            "combatant": combatant.id,
            "used": 0,
            "delta_used": 1,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["selected_combatant_id"] == combatant.id
    assert "Spell slot usage updated." in payload["flash_html"]
    assert "combat-spell-slot-row" in payload["tracker_html"]
    _assert_spell_slot_html_state(payload["tracker_html"], used=1, available=2, maximum=3)

    record = get_character("arden-march")
    spell_slots = {item["level"]: item for item in record.state_record.state["spell_slots"]}
    assert spell_slots[2]["used"] == 1


def test_combat_spell_slot_delta_adopts_legacy_unlaned_state_for_class_lane(
    app, client, sign_in, users, get_character
):
    with app.app_context():
        record = app.extensions["character_repository"].get_visible_character(
            "linden-pass",
            "arden-march",
        )
        app.extensions["character_state_service"].update_spell_slots(
            record,
            1,
            expected_revision=record.state_record.revision,
            used=1,
        )

    _convert_arden_spell_slots_to_class_lane(app)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    page = client.get(f"/campaigns/linden-pass/combat?combatant={combatant.id}")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert 'name="slot_lane_id" value="class-row-1-slots"' in body
    _assert_spell_slot_html_state(body, used=1, available=3, maximum=4)

    record = get_character("arden-march")
    response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}/spell-slots/1",
        data={
            "expected_revision": record.state_record.revision,
            "combat_view": "combat",
            "combatant": combatant.id,
            "slot_lane_id": "class-row-1-slots",
            "used": 1,
            "delta_used": 1,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert "Unknown spell slot level" not in payload["flash_html"]
    _assert_spell_slot_html_state(payload["tracker_html"], used=2, available=2, maximum=4)

    record = get_character("arden-march")
    matching_slots = [
        slot
        for slot in record.state_record.state["spell_slots"]
        if int(slot.get("level") or 0) == 1
    ]
    assert matching_slots == [
        {
            "level": 1,
            "max": 4,
            "slot_lane_id": "class-row-1-slots",
            "used": 2,
        }
    ]


def test_owner_player_can_update_equipment_state_from_combat_workspace(
    app, client, sign_in, users, get_character
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    page = client.get(f"/campaigns/linden-pass/combat?combatant={combatant.id}")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "Save equipment state" not in body
    assert (
        f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}"
        "/equipment/quarterstaff-2/state"
    ) in body
    assert 'name="combat_view" value="combat"' in body
    assert 'data-combat-async' in body
    assert 'data-character-autosubmit' in body

    record = get_character("arden-march")
    assert _inventory_item(record, "quarterstaff-2")["is_equipped"] is True

    update_response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}"
        "/equipment/quarterstaff-2/state",
        data={
            "expected_revision": record.state_record.revision,
            "combat_view": "combat",
            "combatant": combatant.id,
            "weapon_wield_mode": "",
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert update_response.status_code == 200
    payload = update_response.get_json()
    assert payload["ok"] is True
    assert payload["selected_combatant_id"] == combatant.id
    assert "Equipment state updated." in payload["flash_html"]
    assert "Save equipment state" not in payload["tracker_html"]
    assert 'data-character-autosubmit' in payload["tracker_html"]

    record = get_character("arden-march")
    updated_item = _inventory_item(record, "quarterstaff-2")
    assert updated_item["is_equipped"] is False
    assert not updated_item.get("weapon_wield_mode")


def test_actual_combat_definition_runner_forwards_exact_publication_objects(
    app, client, sign_in, users, get_character, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None
    prior = get_character("arden-march")
    action_calls = []
    merge_calls = []
    publication_calls = []
    loaded_records = []
    original_action = app_module.build_shared_equipment_state_update_result
    raw_view = inspect.unwrap(
        app.view_functions["campaign_combat_character_equipment_state"]
    )
    view_freevars = dict(
        zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ())
    )
    runner = view_freevars["run_combat_character_definition_mutation"].cell_contents
    runner_freevars = dict(zip(runner.__code__.co_freevars, runner.__closure__ or ()))
    original_merge = app_module.merge_state_with_definition
    original_get_repository = runner_freevars["get_character_repository"].cell_contents

    def record_action(*args, **kwargs):
        result = original_action(*args, **kwargs)
        action_calls.append((args, kwargs, result))
        return result

    def record_merge(*args, **kwargs):
        result = original_merge(*args, **kwargs)
        merge_calls.append((args, kwargs, result))
        return result

    class SpyCoordinator:
        def recover_pending(self, *, limit=8):
            return {"recovered": 0, "conflict": 0, "pending": 0}

        def update(self, *args, **kwargs):
            publication_calls.append((args, kwargs))

    class RecordingRepository:
        def __init__(self, delegate):
            self.delegate = delegate

        def get_visible_character(self, *args, **kwargs):
            record = self.delegate.get_visible_character(*args, **kwargs)
            loaded_records.append(record)
            return record

    def record_get_repository():
        return RecordingRepository(original_get_repository())

    monkeypatch.setattr(
        app_module, "build_shared_equipment_state_update_result", record_action
    )
    monkeypatch.setattr(app_module, "merge_state_with_definition", record_merge)
    monkeypatch.setattr(
        runner_freevars["get_character_repository"],
        "cell_contents",
        record_get_repository,
    )
    monkeypatch.setattr(
        runner_freevars["character_publication_coordinator"],
        "cell_contents",
        SpyCoordinator(),
    )

    response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}"
        "/equipment/quarterstaff-2/state",
        data={
            "expected_revision": prior.state_record.revision,
            "combatant": combatant.id,
            "weapon_wield_mode": "two-handed",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert (
        len(loaded_records)
        == len(action_calls)
        == len(merge_calls)
        == len(publication_calls)
        == 1
    )
    action_args, _action_kwargs, action_result = action_calls[0]
    merge_args, _merge_kwargs, merged_state = merge_calls[0]
    publication_args, publication_kwargs = publication_calls[0]
    assert action_args[1] is loaded_records[0]
    assert publication_args == (
        action_args[1],
        merge_args[0],
        action_result[1],
        merged_state,
    )
    assert publication_kwargs == {
        "expected_revision": action_args[1].state_record.revision,
        "updated_by_user_id": users["dm"]["id"],
    }


def test_combat_definition_runner_recovers_after_postcommit_failure(
    app, client, sign_in, users, get_character, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None
    prior = get_character("arden-march")
    original_coordinator = app.extensions["character_publication_coordinator"]

    def fail_after_commit(event, _operation_id):
        if event == "after_commit":
            raise RuntimeError("combat committed publication fault")

    fault_coordinator = CharacterPublicationCoordinator(
        campaigns_dir=original_coordinator.campaigns_dir,
        database_path=original_coordinator.database_path,
        state_store=original_coordinator.state_store,
        repository=original_coordinator.repository,
        hooks=CharacterReconciliationHooks(on_event=fail_after_commit),
    )
    raw_view = inspect.unwrap(
        app.view_functions["campaign_combat_character_equipment_state"]
    )
    view_freevars = dict(
        zip(raw_view.__code__.co_freevars, raw_view.__closure__ or ())
    )
    runner = view_freevars["run_combat_character_definition_mutation"].cell_contents
    runner_freevars = dict(zip(runner.__code__.co_freevars, runner.__closure__ or ()))
    monkeypatch.setattr(
        runner_freevars["character_publication_coordinator"],
        "cell_contents",
        fault_coordinator,
    )

    with pytest.raises(RuntimeError, match="combat committed publication fault"):
        client.post(
            f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}"
            "/equipment/quarterstaff-2/state",
            data={
                "expected_revision": prior.state_record.revision,
                "combatant": combatant.id,
                "weapon_wield_mode": "two-handed",
            },
            follow_redirects=False,
        )

    with app.app_context():
        row = get_db().execute(
            """
            SELECT state FROM character_reconciliation_operations
            WHERE campaign_slug = 'linden-pass' AND character_slug = 'arden-march'
            """
        ).fetchone()
        assert row is not None and row["state"] == "prepared"
        state = app.extensions["character_state_store"].get_state(
            "linden-pass", "arden-march"
        )
        assert state is not None
        assert state.revision == prior.state_record.revision + 1
        assert app.extensions["character_repository"].get_character(
            "linden-pass", "arden-march"
        ) is None
        assert original_coordinator.recover_key("linden-pass", "arden-march") is True
        recovered = app.extensions["character_repository"].get_character(
            "linden-pass", "arden-march"
        )
        assert recovered is not None
        assert recovered.state_record.revision == prior.state_record.revision + 1


def test_combat_equipment_state_update_generates_weapon_attacks_for_unarmed_only_import(
    app, client, sign_in, users, get_character
):
    def _mutate_definition(payload: dict) -> None:
        payload["source"] = {
            "source_type": "markdown_character_sheet",
            "source_path": "imports://arden-march.md",
            "imported_from": "Arden March.md",
        }
        payload["attacks"] = [
            {
                "id": "unarmed-strike-1",
                "name": "Unarmed Strike",
                "category": "unarmed",
                "attack_bonus": 3,
                "damage": "1 Bludgeoning",
                "notes": "",
            }
        ]
        for item in list(payload.get("equipment_catalog") or []):
            if str(item.get("id") or "").strip() == "light-crossbow-1":
                item["is_equipped"] = False
                item.pop("weapon_wield_mode", None)

    def _mutate_state(payload: dict) -> None:
        for item in list(payload.get("inventory") or []):
            if str(item.get("catalog_ref") or item.get("id") or "").strip() == "light-crossbow-1":
                item["is_equipped"] = False
                item.pop("weapon_wield_mode", None)

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    update_response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}"
        "/equipment/light-crossbow-1/state",
        data={
            "expected_revision": record.state_record.revision,
            "combat_view": "combat",
            "combatant": combatant.id,
            "weapon_wield_mode": "two-handed",
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert update_response.status_code == 200
    payload = update_response.get_json()
    assert payload["ok"] is True
    assert "Light Crossbow" in payload["tracker_html"]
    assert "1d8+2 piercing" in payload["tracker_html"]

    record = get_character("arden-march")
    attacks_by_name = {attack["name"]: attack for attack in list(record.definition.attacks or [])}
    assert attacks_by_name["Light Crossbow"]["equipment_refs"] == ["light-crossbow-1"]
    updated_item = _inventory_item(record, "light-crossbow-1")
    assert updated_item["is_equipped"] is True
    assert updated_item["weapon_wield_mode"] == "two-handed"


def test_arcane_armor_state_gates_guardian_combat_actions(app, client, sign_in, users, get_character):
    def _workspace_panel(html: str, slug: str) -> str:
        match = re.search(
            rf'<section\b[^>]*data-combat-section-panel="{re.escape(slug)}"[\s\S]*?(?=<section\b[^>]*data-combat-section-panel=|</div>\s*$)',
            html,
        )
        assert match is not None
        return match.group(0)

    def _mutate_definition(payload: dict) -> None:
        payload["attacks"] = [
            {
                "id": "guardian-armor-thunder-gauntlets-1",
                "name": "Guardian Armor: Thunder Gauntlets",
                "category": "weapon",
                "attack_bonus": 8,
                "damage": "1d8+5 Thunder",
                "notes": "",
            }
        ]
        payload["features"] = [
            {
                "id": "arcane-armor-1",
                "name": "Arcane Armor",
                "category": "class_feature",
                "description_markdown": "You turn worn armor into Arcane Armor.",
                "activation_type": "action",
            },
            {
                "id": "armor-model-2",
                "name": "Armor Model",
                "category": "class_feature",
                "description_markdown": "Choose Guardian or Infiltrator.",
                "activation_type": "passive",
            },
            {
                "id": "guardian-3",
                "name": "Guardian",
                "category": "class_feature",
                "description_markdown": "You design your armor to be in the front line of conflict.",
                "activation_type": "passive",
            },
            {
                "id": "guardian-thunder-4",
                "name": "Guardian Armor: Thunder Gauntlets",
                "category": "class_feature",
                "description_markdown": "Each gauntlet deals 1d8 thunder damage.",
                "activation_type": "action",
            },
            {
                "id": "guardian-field-5",
                "name": "Guardian Armor: Defensive Field",
                "category": "class_feature",
                "description_markdown": "You gain temporary hit points.",
                "activation_type": "bonus_action",
                "tracker_ref": "guardian-armor-defensive-field",
            },
        ]
        payload["resource_templates"] = [
            {
                "id": "guardian-armor-defensive-field",
                "label": "Defensive Field",
                "category": "class_feature",
                "initial_current": 3,
                "max": 3,
                "reset_on": "long_rest",
                "reset_to": "max",
                "rest_behavior": "confirm_before_reset",
            }
        ]
        for item in list(payload.get("equipment_catalog") or []):
            item["is_equipped"] = False
            item.pop("weapon_wield_mode", None)

    def _mutate_state(payload: dict) -> None:
        payload["feature_states"] = {"arcane_armor": {"enabled": False}}
        payload["resources"] = [
            {
                "id": "guardian-armor-defensive-field",
                "label": "Defensive Field",
                "category": "class_feature",
                "current": 3,
                "max": 3,
                "reset_on": "long_rest",
                "reset_to": "max",
                "rest_behavior": "confirm_before_reset",
                "display_order": 0,
            }
        ]
        for item in list(payload.get("inventory") or []):
            item["is_equipped"] = False
            item.pop("weapon_wield_mode", None)

    _write_character_definition(app, "arden-march", _mutate_definition)
    _write_character_state(app, "arden-march", _mutate_state)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    page = client.get(f"/campaigns/linden-pass/combat?combatant={combatant.id}")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "Save Arcane Armor" not in body
    assert "Arcane Armor enabled" in body
    assert 'data-character-autosubmit' in body
    assert 'data-combat-section-panel="bonus_actions"' not in body
    assert "Guardian Armor: Thunder Gauntlets" not in _workspace_panel(body, "actions")

    record = get_character("arden-march")
    update_response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}"
        "/feature-states/arcane_armor",
        data={
            "expected_revision": record.state_record.revision,
            "combat_view": "combat",
            "combatant": combatant.id,
            "enabled": "1",
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert update_response.status_code == 200
    payload = update_response.get_json()
    assert payload["ok"] is True
    assert "Feature state updated." in payload["flash_html"]
    tracker_html = payload["tracker_html"]
    assert "Guardian Armor: Defensive Field" in _workspace_panel(tracker_html, "bonus_actions")
    assert "Guardian Armor: Thunder Gauntlets" in _workspace_panel(tracker_html, "actions")
    attacks_panel = _workspace_panel(tracker_html, "attacks")
    assert "Guardian Armor: Thunder Gauntlets" in attacks_panel
    assert "1d8+5 Thunder" in attacks_panel

    record = get_character("arden-march")
    assert record.state_record.state["feature_states"]["arcane_armor"]["enabled"] is True


def test_combat_character_inventory_collapses_linked_item_descriptions(app, client, sign_in, users):
    def add_inventory_examples(payload):
        equipment_catalog = list(payload.get("equipment_catalog") or [])
        equipment_catalog.append(
            {
                "id": "stormglass-compass-99",
                "name": "Stormglass Compass",
                "default_quantity": 1,
                "weight": "1 lb.",
                "notes": "Keep the face covered in bright rain.",
                "tags": ["wondrous"],
                "page_ref": {
                    "slug": "items/stormglass-compass",
                    "title": "Stormglass Compass",
                },
            }
        )
        equipment_catalog.append(
            {
                "id": "unlinked-field-token-99",
                "name": "Unlinked Field Token",
                "default_quantity": 1,
                "notes": "Marks the safe route.",
            }
        )
        payload["equipment_catalog"] = equipment_catalog

    _write_character_definition(app, "arden-march", add_inventory_examples)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    dm_page = client.get(f"/campaigns/linden-pass/combat/dm?combatant={combatant.id}")
    assert dm_page.status_code == 200
    compatibility_status_redirect = client.get(
        f"/campaigns/linden-pass/combat/status?combatant={combatant.id}",
        follow_redirects=False,
    )
    assert compatibility_status_redirect.status_code == 302
    assert compatibility_status_redirect.headers["Location"] == (
        f"/campaigns/linden-pass/combat/dm?combatant={combatant.id}"
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])
    player_page = client.get(f"/campaigns/linden-pass/combat?combatant={combatant.id}")
    assert player_page.status_code == 200
    compatibility_character_page = client.get(
        f"/campaigns/linden-pass/combat/character?combatant={combatant.id}"
    )
    assert compatibility_character_page.status_code == 200

    for response in [
        player_page,
        compatibility_character_page,
        dm_page,
    ]:
        body = response.get_data(as_text=True)
        assert "Stormglass Compass" in body
        assert 'href="/campaigns/linden-pass/pages/items/stormglass-compass"' in body
        assert 'data-character-spell-modal-trigger' in body
        assert 'data-character-spell-modal' in body
        assert 'combat-inventory-item-detail-' in body
        assert 'aria-controls="combat-inventory-item-detail-' in body
        assert 'data-presentation-dialog-trigger="combat-inventory-item-detail-' in body
        assert 'aria-labelledby="combat-inventory-item-detail-' in body
        assert 'data-presentation-dialog-initial-focus' in body
        assert 'data-combat-presentation-dialog-scope' in body
        assert '<summary>Item details</summary>' in body
        assert "This brass compass glows pale blue when a storm front shifts closer to the coast." in body
        assert '<details class="item-description-detail" open' not in body
        assert "Unlinked Field Token" in body
        assert "<p>Marks the safe route.</p>" in body
        assert 'class="meta-badge">x' not in body
        assert re.search(r'class="meta-badge">[^<]*\blb\.?', body) is None


def test_combat_character_attacks_panel_keeps_attack_reminders(app, client, sign_in, users):
    def add_attack_reminders(payload):
        payload["attacks"] = [
            {
                "id": "mace-1",
                "name": "Mace",
                "category": "melee weapon",
                "attack_bonus": 5,
                "damage": "1d6+3 bludgeoning",
                "damage_type": "Bludgeoning",
                "notes": "",
            },
            {
                "id": "rapier-1",
                "name": "Rapier",
                "category": "melee weapon",
                "attack_bonus": 5,
                "damage": "1d8+3 piercing",
                "damage_type": "Piercing",
                "notes": "",
            },
        ]
        payload["features"] = [
            {
                "id": "mage-slayer-1",
                "name": "Mage Slayer",
                "category": "feat",
                "source": "PHB",
                "description_markdown": "",
                "systems_ref": {
                    "entry_type": "feat",
                    "slug": "phb-feat-mage-slayer",
                    "title": "Mage Slayer",
                    "source_id": "PHB",
                },
            },
            {
                "id": "crusher-1",
                "name": "Crusher",
                "category": "feat",
                "source": "TCE",
                "description_markdown": "",
                "systems_ref": {
                    "entry_type": "feat",
                    "slug": "tce-feat-crusher",
                    "title": "Crusher",
                    "source_id": "TCE",
                },
            },
        ]

    _write_character_definition(app, "arden-march", add_attack_reminders)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])
    response = client.get(f"/campaigns/linden-pass/combat?combatant={combatant.id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Mage Slayer" in body
    assert "Spellcasting trigger:</strong> When a creature within 5 feet of you casts a spell, you can use your reaction to make a melee weapon attack against it." in body
    assert "Crusher" in body
    assert "Eligible attacks: Mace" in body
    assert "Linked attacks" in body


def test_combat_character_spells_collapse_linked_spell_descriptions(app, client, sign_in, users):
    def link_message_spell(payload):
        spellcasting = dict(payload.get("spellcasting") or {})
        spells = []
        for spell in list(spellcasting.get("spells") or []):
            spell_payload = dict(spell or {})
            if str(spell_payload.get("name") or "").strip() == "Message":
                spell_payload["page_ref"] = {
                    "slug": "spells/message",
                    "title": "Message",
                }
            spells.append(spell_payload)
        spellcasting["spells"] = spells
        payload["spellcasting"] = spellcasting

    _write_character_definition(app, "arden-march", link_message_spell)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    dm_page = client.get(f"/campaigns/linden-pass/combat/dm?combatant={combatant.id}")
    assert dm_page.status_code == 200
    compatibility_status_redirect = client.get(
        f"/campaigns/linden-pass/combat/status?combatant={combatant.id}",
        follow_redirects=False,
    )
    assert compatibility_status_redirect.status_code == 302
    assert compatibility_status_redirect.headers["Location"] == (
        f"/campaigns/linden-pass/combat/dm?combatant={combatant.id}"
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])
    player_page = client.get(f"/campaigns/linden-pass/combat?combatant={combatant.id}")
    assert player_page.status_code == 200
    compatibility_character_page = client.get(
        f"/campaigns/linden-pass/combat/character?combatant={combatant.id}"
    )
    assert compatibility_character_page.status_code == 200

    for response in [
        player_page,
        compatibility_character_page,
        dm_page,
    ]:
        body = response.get_data(as_text=True)
        assert "Message" in body
        assert 'data-character-spell-modal-trigger' in body
        assert 'data-character-spell-modal' in body
        assert 'combat-spell-detail-dialog-' in body
        assert 'data-presentation-dialog-trigger="combat-spell-detail-dialog-' in body
        assert 'aria-labelledby="combat-spell-detail-dialog-' in body
        assert 'data-presentation-dialog-initial-focus' in body
        assert 'data-combat-presentation-dialog-scope' in body
        assert '<summary>Spell details</summary>' in body
        assert "You point toward a creature within range and whisper a short message only it can hear." in body
        assert '<details class="item-description-detail" open' not in body


def test_combat_character_spells_hide_unprepared_spellbook_rows(app, client, sign_in, users):
    def make_wizard_spellbook(payload):
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Wizard 5"
        profile["classes"] = [{"row_id": "class-row-1", "class_name": "Wizard", "level": 5}]
        payload["profile"] = profile
        payload["spellcasting"] = {
            "spellcasting_class": "Wizard",
            "spellcasting_ability": "Intelligence",
            "spell_save_dc": 14,
            "spell_attack_bonus": 6,
            "slot_progression": [{"level": 1, "max_slots": 4}],
            "class_rows": [
                {
                    "class_row_id": "class-row-1",
                    "class_name": "Wizard",
                    "level": 5,
                    "spell_mode": "wizard",
                    "spellcasting_ability": "Intelligence",
                    "spell_save_dc": 14,
                    "spell_attack_bonus": 6,
                }
            ],
            "spells": [
                {
                    "name": "Message",
                    "level": 0,
                    "mark": "Cantrip",
                    "class_row_id": "class-row-1",
                },
                {
                    "name": "Shield",
                    "level": 1,
                    "mark": "Prepared + Spellbook",
                    "class_row_id": "class-row-1",
                },
                {
                    "name": "Magic Missile",
                    "level": 1,
                    "mark": "Spellbook",
                    "class_row_id": "class-row-1",
                },
            ],
        }

    _write_character_definition(app, "arden-march", make_wizard_spellbook)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])
    player_page = client.get(f"/campaigns/linden-pass/combat?combatant={combatant.id}")

    assert player_page.status_code == 200
    body = player_page.get_data(as_text=True)
    assert "Message" in body
    assert "Shield" in body
    assert "Magic Missile" not in body


def test_owner_player_combat_workspace_resource_mutations_redirect_back_to_combat(
    app, client, sign_in, users, get_character
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["owner"]["email"], users["owner"]["password"])

    record = get_character("arden-march")
    resource_response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}/resources/sorcery-points",
        data={
            "expected_revision": record.state_record.revision,
            "current": 3,
            "combat_view": "combat",
        },
        follow_redirects=False,
    )

    assert resource_response.status_code == 302
    assert resource_response.headers["Location"].endswith(
        f"/campaigns/linden-pass/combat?combatant={combatant.id}#combat-character-resources"
    )

    record = get_character("arden-march")
    spell_response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}/spell-slots/2",
        data={
            "expected_revision": record.state_record.revision,
            "used": 2,
            "combat_view": "combat",
        },
        follow_redirects=False,
    )

    assert spell_response.status_code == 302
    assert spell_response.headers["Location"].endswith(
        f"/campaigns/linden-pass/combat?combatant={combatant.id}#combat-character-spell-slots"
    )


def test_unassigned_player_cannot_update_other_pc_combat_resources_or_spell_slots(
    app, client, sign_in, users, get_character
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    combatant = _find_combatant(app, character_slug="arden-march")
    record = get_character("arden-march")
    assert combatant is not None
    assert record is not None

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    tracker_resources = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/resources",
        data={"movement_remaining": 5},
        follow_redirects=False,
    )
    resource_response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}/resources/sorcery-points",
        data={"expected_revision": record.state_record.revision, "current": 3},
        follow_redirects=False,
    )
    spell_response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{combatant.id}/spell-slots/2",
        data={"expected_revision": record.state_record.revision, "used": 2},
        follow_redirects=False,
    )

    assert tracker_resources.status_code == 403
    assert resource_response.status_code == 403
    assert spell_response.status_code == 403


def test_dm_can_manage_npc_vitals_resources_and_conditions(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )
    combatant = _find_combatant(app, name="Clockwork Hound")
    assert combatant is not None

    vitals = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/vitals",
        data={"current_hp": 15, "max_hp": 22, "temp_hp": 3, "movement_total": 50},
        follow_redirects=False,
    )
    resources = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/resources",
        data={
            "has_action": "1",
            "movement_remaining": 10,
        },
        follow_redirects=False,
    )
    add_condition = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/conditions",
        data={"condition_name": "Blinded", "duration_text": "Until end of next turn"},
        follow_redirects=False,
    )

    assert vitals.status_code == 302
    assert resources.status_code == 302
    assert add_condition.status_code == 302

    updated_combatant = _find_combatant(app, name="Clockwork Hound")
    conditions = _list_conditions(app, combatant.id)
    assert updated_combatant is not None
    assert updated_combatant.current_hp == 15
    assert updated_combatant.temp_hp == 3
    assert updated_combatant.movement_total == 50
    assert updated_combatant.has_action is True
    assert updated_combatant.has_bonus_action is False
    assert updated_combatant.has_reaction is False
    assert updated_combatant.movement_remaining == 10
    assert len(conditions) == 1
    assert conditions[0].name == "Blinded"
    assert conditions[0].duration_text == "Until end of next turn"

    update_condition = client.post(
        f"/campaigns/linden-pass/combat/conditions/{conditions[0].id}",
        data={"condition_name": "Restrained", "duration_text": "One minute"},
        follow_redirects=False,
    )
    assert update_condition.status_code == 302

    conditions = _list_conditions(app, combatant.id)
    assert len(conditions) == 1
    assert conditions[0].name == "Restrained"
    assert conditions[0].duration_text == "One minute"

    delete_condition = client.post(
        f"/campaigns/linden-pass/combat/conditions/{conditions[0].id}/delete",
        follow_redirects=False,
    )
    assert delete_condition.status_code == 302
    assert _list_conditions(app, combatant.id) == []


def test_npc_detail_is_hidden_from_players_by_default_and_dm_can_reveal_per_npc(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Brass Sentry",
            "turn_value": 8,
            "current_hp": 18,
            "max_hp": 18,
            "temp_hp": 0,
            "movement_total": 30,
        },
        follow_redirects=False,
    )

    hound = _find_combatant(app, name="Clockwork Hound")
    sentry = _find_combatant(app, name="Brass Sentry")
    assert hound is not None
    assert sentry is not None
    assert hound.player_detail_visible is False
    assert sentry.player_detail_visible is False

    toggle = client.post(
        f"/campaigns/linden-pass/combat/combatants/{hound.id}/player-detail-visibility",
        data={"player_detail_visible": "1", "combat_view": "dm"},
        follow_redirects=False,
    )

    assert toggle.status_code == 302
    updated_hound = _find_combatant(app, name="Clockwork Hound")
    updated_sentry = _find_combatant(app, name="Brass Sentry")
    assert updated_hound is not None
    assert updated_sentry is not None
    assert updated_hound.player_detail_visible is True
    assert updated_sentry.player_detail_visible is False

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.get("/campaigns/linden-pass/combat")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Clockwork Hound" in body
    assert "Brass Sentry" in body
    assert "22 / 22" in body
    assert "40 / 40" in body
    assert "18 / 18" not in body
    assert "30 / 30" not in body
    assert "Detailed NPC vitals and action economy are hidden from player view." in body


def test_player_cannot_toggle_npc_player_detail_visibility(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )
    combatant = _find_combatant(app, name="Clockwork Hound")
    assert combatant is not None
    with app.app_context():
        service = app.extensions["campaign_combat_service"]

    def fail_update(*args, **kwargs):
        raise AssertionError("assigned players must not reach the visibility service")

    monkeypatch.setattr(service, "update_player_detail_visibility", fail_update)

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/player-detail-visibility",
        data={"player_detail_visible": "1", "combat_view": "dm"},
        follow_redirects=False,
    )

    assert response.status_code == 403
    refreshed = _find_combatant(app, name="Clockwork Hound")
    assert refreshed is not None
    assert refreshed.player_detail_visible is False


def test_async_dm_player_detail_visibility_preserves_focus_payload_and_revision_attribution(
    app,
    client,
    sign_in,
    users,
):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        combatant = service.add_npc_combatant(
            "linden-pass",
            display_name="Visibility Watch",
            turn_value=12,
            current_hp=22,
            max_hp=22,
            movement_total=40,
            created_by_user_id=users["dm"]["id"],
        )
        baseline_tracker = service.get_tracker("linden-pass")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/player-detail-visibility",
        data={
            "combat_view": "dm",
            "view": "status",
            "combatant": combatant.id,
            "expected_combatant_revision": combatant.revision,
            "player_detail_visible": "1",
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["anchor"] == f"combatant-{combatant.id}"
    assert payload["selected_combatant_id"] == combatant.id
    assert payload["page_url"] == f"/campaigns/linden-pass/combat/dm?combatant={combatant.id}"
    assert payload["live_url"] == (
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={combatant.id}"
    )
    assert "Player-facing NPC detail updated." in payload["flash_html"]
    assert "Players can currently see this NPC's vitals and action economy." in payload[
        "tracker_authority_html"
    ]

    refreshed = _find_combatant(app, name="Visibility Watch")
    assert refreshed is not None
    tracker = _get_tracker(app)
    assert refreshed.player_detail_visible is True
    assert refreshed.revision == combatant.revision + 1
    assert refreshed.updated_by_user_id == users["dm"]["id"]
    assert tracker.revision == baseline_tracker.revision + 1
    assert tracker.updated_by_user_id == users["dm"]["id"]
    assert payload["live_revision"] == tracker.revision
    _assert_expected_combatant_revision_field(
        payload["tracker_authority_html"],
        refreshed.revision,
    )


def test_async_dm_player_detail_visibility_rejects_stale_revision_without_mutation(
    app,
    client,
    sign_in,
    users,
):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        combatant = service.add_npc_combatant(
            "linden-pass",
            display_name="Stale Visibility Watch",
            turn_value=12,
            current_hp=22,
            max_hp=22,
            movement_total=40,
            created_by_user_id=users["dm"]["id"],
        )

    sign_in(users["dm"]["email"], users["dm"]["password"])
    common_data = {
        "combat_view": "dm",
        "view": "status",
        "combatant": combatant.id,
        "expected_combatant_revision": combatant.revision,
    }
    first_response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/player-detail-visibility",
        data={**common_data, "player_detail_visible": "1"},
        headers=_async_headers(),
        follow_redirects=False,
    )
    assert first_response.status_code == 200
    assert first_response.get_json()["ok"] is True
    after_first = _find_combatant(app, name="Stale Visibility Watch")
    after_first_tracker = _get_tracker(app)
    assert after_first is not None

    stale_response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/player-detail-visibility",
        data={**common_data, "player_detail_visible": "0"},
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert stale_response.status_code == 200
    assert stale_response.headers["X-Live-Mutation-Outcome"] == "combatant-revision-conflict"
    stale_payload = stale_response.get_json()
    assert stale_payload["ok"] is False
    assert stale_payload["anchor"] == f"combatant-{combatant.id}"
    assert stale_payload["selected_combatant_id"] == combatant.id
    assert "This combatant changed in another combat view. Refresh and try again." in stale_payload[
        "flash_html"
    ]
    assert _find_combatant(app, name="Stale Visibility Watch") == after_first
    assert _get_tracker(app) == after_first_tracker


def test_unsupported_player_detail_visibility_returns_failed_payload_without_service_call(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    def _mutate(payload: dict) -> None:
        payload["system"] = "xianxia"
        payload["systems_library"] = "xianxia"

    _write_campaign_config(app, _mutate)
    with app.app_context():
        service = app.extensions["campaign_combat_service"]

    def fail_update(*args, **kwargs):
        raise AssertionError("unsupported combat must not call the visibility service")

    monkeypatch.setattr(service, "update_player_detail_visibility", fail_update)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.post(
        "/campaigns/linden-pass/combat/combatants/999999/player-detail-visibility",
        data={"combat_view": "dm", "view": "status", "combatant": 999999},
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["anchor"] == "combatant-999999"
    assert "Combat tracker support for Xianxia is not available yet." in payload["flash_html"]


@pytest.mark.parametrize(
    ("submitted_value", "expected_visibility"),
    (("1", True), ("true", False), ("on", False), ("", False), (None, False)),
)
def test_player_detail_visibility_uses_only_exact_one_and_preserves_validation_failure(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
    submitted_value,
    expected_visibility,
):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        combatant = service.add_npc_combatant(
            "linden-pass",
            display_name="Visibility Value Probe",
            turn_value=12,
            current_hp=12,
            max_hp=12,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )
        baseline_tracker = service.get_tracker("linden-pass")
    captured = {}

    def fail_update(*args, **kwargs):
        captured.update(kwargs)
        raise campaign_combat_service_module.CampaignCombatValidationError(
            "Injected visibility failure."
        )

    monkeypatch.setattr(service, "update_player_detail_visibility", fail_update)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    data = {
        "combat_view": "dm",
        "view": "status",
        "combatant": combatant.id,
        "expected_combatant_revision": str(combatant.revision),
    }
    if submitted_value is not None:
        data["player_detail_visible"] = submitted_value
    response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/player-detail-visibility",
        data=data,
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["anchor"] == f"combatant-{combatant.id}"
    assert "Injected visibility failure." in payload["flash_html"]
    assert captured == {
        "expected_revision": combatant.revision,
        "player_detail_visible": expected_visibility,
        "updated_by_user_id": users["dm"]["id"],
    }
    assert _find_combatant(app, name="Visibility Value Probe") == combatant
    assert _get_tracker(app) == baseline_tracker


def test_player_detail_visibility_rejects_player_combatant_without_mutation(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    combatant = _find_combatant(app, character_slug="arden-march")
    assert combatant is not None
    baseline_tracker = _get_tracker(app)

    response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/player-detail-visibility",
        data={
            "combat_view": "dm",
            "view": "status",
            "combatant": combatant.id,
            "expected_combatant_revision": combatant.revision,
            "player_detail_visible": "1",
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is False
    assert "Only NPC combatants can toggle player-facing detail visibility." in payload["flash_html"]
    assert _find_combatant(app, character_slug="arden-march") == combatant
    assert _get_tracker(app) == baseline_tracker


def test_player_detail_visibility_form_has_csrf_and_csrf_blocks_before_mutation(
    app,
    client,
    sign_in,
    users,
):
    with app.app_context():
        service = app.extensions["campaign_combat_service"]
        combatant = service.add_npc_combatant(
            "linden-pass",
            display_name="Visibility CSRF Guard",
            turn_value=12,
            current_hp=12,
            max_hp=12,
            movement_total=30,
            created_by_user_id=users["dm"]["id"],
        )
        baseline_tracker = service.get_tracker("linden-pass")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    app.config["CSRF_ENABLED"] = True
    html = client.get(
        f"/campaigns/linden-pass/combat/dm?combatant={combatant.id}"
    ).get_data(as_text=True)
    visibility_form = re.search(
        rf'<form\b[^>]*action="/campaigns/linden-pass/combat/combatants/{combatant.id}/player-detail-visibility"[^>]*>(.*?)</form>',
        html,
        re.S,
    )
    assert visibility_form is not None
    assert visibility_form.group(1).count('name="_csrf_token"') == 1

    response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/player-detail-visibility",
        data={
            "expected_combatant_revision": combatant.revision,
            "player_detail_visible": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert _find_combatant(app, name="Visibility CSRF Guard") == combatant
    assert _get_tracker(app) == baseline_tracker


def test_dm_can_clear_combat_tracker(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    glenn = _find_combatant(app, character_slug="arden-march")
    assert glenn is not None
    client.post(
        f"/campaigns/linden-pass/combat/combatants/{glenn.id}/set-current",
        follow_redirects=False,
    )

    response = client.post(
        "/campaigns/linden-pass/combat/clear",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert _list_combatants(app) == []
    tracker = _get_tracker(app)
    assert tracker.current_combatant_id is None
    assert tracker.round_number == 1


def test_player_cannot_clear_combat_tracker(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.post(
        "/campaigns/linden-pass/combat/clear",
        follow_redirects=False,
    )

    assert response.status_code == 403
    combatant = _find_combatant(app, name="Clockwork Hound")
    assert combatant is not None


def test_init_db_backfills_legacy_combatant_source_identity_and_revision(tmp_path, monkeypatch):
    campaigns_dir = build_test_campaigns_dir(tmp_path)
    monkeypatch.setattr(Config, "CAMPAIGNS_DIR", campaigns_dir)

    db_path = tmp_path / "legacy-player-wiki.sqlite3"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE campaign_combatants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_slug TEXT NOT NULL,
            combatant_type TEXT NOT NULL,
            character_slug TEXT,
            display_name TEXT NOT NULL,
            turn_value INTEGER NOT NULL DEFAULT 0,
            initiative_bonus INTEGER NOT NULL DEFAULT 0,
            current_hp INTEGER NOT NULL DEFAULT 0,
            max_hp INTEGER NOT NULL DEFAULT 0,
            temp_hp INTEGER NOT NULL DEFAULT 0,
            movement_total INTEGER NOT NULL DEFAULT 0,
            movement_remaining INTEGER NOT NULL DEFAULT 0,
            has_action INTEGER NOT NULL DEFAULT 1,
            has_bonus_action INTEGER NOT NULL DEFAULT 1,
            has_reaction INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by_user_id INTEGER,
            updated_by_user_id INTEGER
        );

        INSERT INTO campaign_combatants (
            campaign_slug,
            combatant_type,
            character_slug,
            display_name,
            turn_value,
            initiative_bonus,
            current_hp,
            max_hp,
            temp_hp,
            movement_total,
            movement_remaining,
            has_action,
            has_bonus_action,
            has_reaction,
            created_at,
            updated_at
        )
        VALUES
            ('linden-pass', 'player_character', 'arden-march', 'Arden March', 18, 3, 38, 38, 0, 30, 30, 1, 1, 1, '2026-03-31T12:00:00Z', '2026-03-31T12:00:00Z'),
            ('linden-pass', 'npc', NULL, 'Clockwork Hound', 12, 2, 22, 22, 0, 40, 40, 1, 1, 1, '2026-03-31T12:00:00Z', '2026-03-31T12:00:00Z');
        """
    )
    connection.commit()
    connection.close()

    app = create_app()
    app.config.update(TESTING=True, DB_PATH=db_path)

    with app.app_context():
        init_database()

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT
            display_name,
            character_slug,
            source_kind,
            source_ref,
            revision,
            dexterity_modifier,
            initiative_priority
        FROM campaign_combatants
        ORDER BY id ASC
        """
    ).fetchall()
    connection.close()

    assert [dict(row) for row in rows] == [
        {
            "display_name": "Arden March",
            "character_slug": "arden-march",
            "source_kind": "character",
            "source_ref": "arden-march",
            "revision": 1,
            "dexterity_modifier": 3,
            "initiative_priority": 1,
        },
        {
            "display_name": "Clockwork Hound",
            "character_slug": None,
            "source_kind": "manual_npc",
            "source_ref": "",
            "revision": 1,
            "dexterity_modifier": 2,
            "initiative_priority": 1,
        },
    ]


def test_combat_page_renders_context_panel_and_dm_page_focuses_selected_combatant(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    hound = _find_combatant(app, name="Clockwork Hound")
    assert arden is not None
    assert hound is not None

    client.post(
        f"/campaigns/linden-pass/combat/combatants/{arden.id}/set-current",
        follow_redirects=False,
    )

    combat_page = client.get("/campaigns/linden-pass/combat", follow_redirects=False)
    dm_page = client.get(f"/campaigns/linden-pass/combat/dm?combatant={hound.id}")
    dm_controls_page = client.get(f"/campaigns/linden-pass/combat/dm?combatant={hound.id}&view=controls")

    assert combat_page.status_code == 302
    assert combat_page.headers["Location"] == "/campaigns/linden-pass/combat/dm"
    assert dm_page.status_code == 200
    assert dm_controls_page.status_code == 200
    dm_html = dm_page.get_data(as_text=True)
    dm_controls_html = dm_controls_page.get_data(as_text=True)
    assert "data-combatant-carousel" in dm_html
    assert "combat-turn-order-carousel" in dm_html
    assert 'data-combat-navigation-mode="carousel"' in dm_html
    assert f'href="/campaigns/linden-pass/combat/dm?combatant={hound.id}"' in dm_html
    assert f'href="/campaigns/linden-pass/combat/dm?combatant={hound.id}&amp;view=controls"' in dm_html
    assert "Clockwork Hound" in dm_html
    assert "Arden March" in dm_html
    assert "Current turn" in dm_html
    assert f'data-combatant-id="{hound.id}"' in dm_html
    assert f'data-combatant-id="{arden.id}"' in dm_html
    assert 'name="turn_value"' in dm_html
    assert 'name="initiative_priority"' in dm_html
    carousel_cards = re.findall(
        r'<article[^>]*class="combat-turn-order-row[^"]*"[^>]*>.*?</article>',
        dm_html,
        flags=re.S,
    )
    assert carousel_cards
    assert all("Priority" not in card for card in carousel_cards)
    snapshot = re.search(
        r'<article[^>]*id="combat-status-snapshot"[^>]*>.*?</article>',
        dm_html,
        flags=re.S,
    )
    assert snapshot is not None
    assert "Priority" not in snapshot.group(0)
    assert dm_html.count('id="combat-status-snapshot"') == 1
    assert "Advance turn" in dm_html
    assert "Clear tracker" not in dm_html
    assert "Save turn order" in dm_html
    assert "Remove combatant" in dm_html
    assert "Clear tracker" in dm_controls_html
    assert "Selected combatant authority" not in dm_controls_html
    assert "Save turn value" not in dm_controls_html
    assert "Remove combatant" not in dm_controls_html


def test_dm_live_state_renders_only_selected_combatant_card(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    hound = _find_combatant(app, name="Clockwork Hound")
    assert arden is not None
    assert hound is not None

    response = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={hound.id}",
        headers=_async_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["selected_combatant_id"] == hound.id
    assert 'combat-summary-card--compact' in payload["summary_html"]
    assert f'data-combatant-id="{hound.id}"' in payload["tracker_html"]
    assert f'data-combatant-id="{arden.id}"' in payload["tracker_html"]
    assert 'data-combatant-selected="true"' in payload["tracker_html"]


def test_dm_status_combined_page_script_hydrates_selected_combatant_live_state_and_urls(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    hound = _find_combatant(app, name="Clockwork Hound")
    assert arden is not None
    assert hound is not None

    page = client.get(f"/campaigns/linden-pass/combat/dm?combatant={hound.id}")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert '/static/combat-live.js?v=' in body
    combat_script = _combat_live_script_text()
    assert "const fetchDmStatusCombatant = async (combatantId, { carousel = null } = {}) => {" in combat_script
    assert "const setDmStatusSelectionLoading = (isLoading) => {" in combat_script
    assert "const getPayloadSelectedCombatantId = (payload = {}) => {" in combat_script
    assert "const isStaleDmStatusPayload = (payload = {}) => {" in combat_script
    assert 'if (target.matches("[data-combatant-carousel-jump-select]")) {' in combat_script
    assert "if (isDmStatusLiveRoot && selectedCombatantId) {" in combat_script
    assert "setDmStatusSelectionLoading(true);" in combat_script
    assert "setDmStatusSelectionLoading(false);" in combat_script
    assert "void fetchDmStatusCombatant(selectedCombatantId, { carousel });" in combat_script
    assert "await fetchDmStatusCombatant(selectedCombatantId, { carousel });" in combat_script
    assert 'data-combat-status-selection-loading' in body
    assert 'data-combat-status-detail-content-root' in body
    assert "Loading selected combatant..." in body
    assert 'role="status"' in body
    assert 'aria-live="polite"' in body
    assert 'aria-atomic="true"' in body
    assert (
        'const trackerDetailContentRoot = document.querySelector("[data-combat-status-detail-content-root]");'
        in combat_script
    )
    assert "const trackerDetailTarget = trackerDetailContentRoot || trackerDetailRoot;" in combat_script
    assert "pollUrl = nextPollUrl;" in combat_script
    assert "liveRoot.dataset.selectedCombatantId = normalizedCombatantId;" in combat_script
    assert "if (isStaleDmStatusPayload(payload)) {" in combat_script
    assert 'logLiveDiagnostics("combat-stale", response, payload);' in combat_script
    assert 'data-combat-live-url="/campaigns/linden-pass/combat/dm/live-state?combatant=' in body
    assert f'data-selected-combatant-id="{hound.id}"' in body

    initial_payload = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={hound.id}",
        headers=_async_headers(),
    ).get_json()
    next_payload = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={arden.id}",
        headers=_async_headers(),
    ).get_json()
    assert next_payload["selected_combatant_id"] == arden.id
    assert next_payload["page_url"] == f"/campaigns/linden-pass/combat/dm?combatant={arden.id}"
    assert next_payload["live_url"] == f"/campaigns/linden-pass/combat/dm/live-state?combatant={arden.id}"
    assert initial_payload["selected_combatant_id"] == hound.id


def test_dm_status_live_state_reuses_selected_detail_when_unchanged(
    app, client, sign_in, users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    hound = _find_combatant(app, name="Clockwork Hound")
    assert arden is not None
    assert hound is not None

    response = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={hound.id}",
        headers=_async_headers(),
    )
    assert response.status_code == 200
    initial_payload = response.get_json()
    initial_detail_token = initial_payload["combatant_detail_state_token"]
    assert "tracker_detail_html" in initial_payload

    client.post(
        f"/campaigns/linden-pass/combat/combatants/{arden.id}/resources",
        data={
            "combat_view": "dm",
            "view": "status",
            "combatant": arden.id,
            "has_action": "1",
            "expected_combatant_revision": arden.revision,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    unchanged_poll = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={hound.id}",
        headers=_live_poll_headers(
            initial_payload["live_revision"],
            initial_payload["live_view_token"],
            initial_detail_token,
        ),
    )
    assert unchanged_poll.status_code == 200
    unchanged_payload = unchanged_poll.get_json()
    assert unchanged_payload["changed"] is True
    assert unchanged_payload["selected_combatant_id"] == hound.id
    assert unchanged_payload["combatant_detail_state_token"] == initial_detail_token
    assert "tracker_detail_html" not in unchanged_payload
    assert f'data-combatant-id="{hound.id}"' in unchanged_payload["tracker_html"]

    focus_payload = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={arden.id}",
        headers=_live_poll_headers(
            unchanged_payload["live_revision"],
            unchanged_payload["live_view_token"],
            unchanged_payload["combatant_detail_state_token"],
        ),
    ).get_json()
    assert focus_payload["selected_combatant_id"] == arden.id
    assert "tracker_detail_html" in focus_payload
    assert "Arden March" in focus_payload["tracker_detail_html"]


def test_dm_live_state_does_not_short_circuit_when_focus_changes(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    hound = _find_combatant(app, name="Clockwork Hound")
    assert arden is not None
    assert hound is not None

    initial_live_state = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={arden.id}",
        headers=_async_headers(),
    )

    assert initial_live_state.status_code == 200
    initial_payload = initial_live_state.get_json()
    assert initial_payload["changed"] is True
    assert initial_payload["selected_combatant_id"] == arden.id

    changed_focus_live_state = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={hound.id}",
        headers=_live_poll_headers(initial_payload["live_revision"], initial_payload["live_view_token"]),
    )

    assert changed_focus_live_state.status_code == 200
    changed_focus_payload = changed_focus_live_state.get_json()
    assert changed_focus_payload["changed"] is True
    assert changed_focus_payload["selected_combatant_id"] == hound.id
    assert changed_focus_payload["live_view_token"] != initial_payload["live_view_token"]
    assert f'data-combatant-id="{hound.id}"' in changed_focus_payload["tracker_html"]
    assert f'data-combatant-id="{arden.id}"' in changed_focus_payload["tracker_html"]


def test_non_async_combat_mutations_preserve_explicit_combatant_focus_in_redirects(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )
    hound = _find_combatant(app, name="Clockwork Hound")
    assert hound is not None

    combat_redirect = client.post(
        f"/campaigns/linden-pass/combat/combatants/{hound.id}/resources",
        data={
            "has_action": "1",
            "movement_remaining": 15,
            "combatant": hound.id,
        },
        follow_redirects=False,
    )
    dm_redirect = client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Brass Sentry",
            "turn_value": 8,
            "current_hp": 18,
            "max_hp": 18,
            "temp_hp": 0,
            "movement_total": 30,
            "combat_view": "dm",
            "combatant": hound.id,
        },
        follow_redirects=False,
    )

    assert combat_redirect.status_code == 302
    assert dm_redirect.status_code == 302
    assert "/campaigns/linden-pass/combat?combatant=" in combat_redirect.headers["Location"]
    assert f"combatant={hound.id}" in combat_redirect.headers["Location"]
    assert "/campaigns/linden-pass/combat/dm?combatant=" in dm_redirect.headers["Location"]
    assert f"combatant={hound.id}" in dm_redirect.headers["Location"]


def test_selected_combatant_pages_seed_canonical_focus_urls(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    hound = _find_combatant(app, name="Clockwork Hound")
    assert hound is not None

    combat_response = client.get(
        f"/campaigns/linden-pass/combat?combatant={hound.id}",
        follow_redirects=False,
    )
    controls_response = client.get(f"/campaigns/linden-pass/combat/dm?combatant={hound.id}")
    status_response = client.get(
        f"/campaigns/linden-pass/combat/status?combatant={hound.id}",
        follow_redirects=False,
    )

    assert combat_response.status_code == 302
    assert (
        combat_response.headers["Location"]
        == f"/campaigns/linden-pass/combat/dm?combatant={hound.id}"
    )
    assert controls_response.status_code == 200
    assert status_response.status_code == 302
    assert status_response.headers["Location"] == (
        f"/campaigns/linden-pass/combat/dm?combatant={hound.id}"
    )

    controls_body = controls_response.get_data(as_text=True)
    assert f'data-combat-live-url="/campaigns/linden-pass/combat/dm/live-state?combatant={hound.id}"' in controls_body


def test_dm_status_page_returns_404_for_invalid_explicit_target(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.get("/campaigns/linden-pass/combat/status?combatant=9999")

    assert response.status_code == 404


def test_dm_status_page_renders_only_selected_pc_detail(app, client, sign_in, users, tmp_path):
    goblin_entry_key, _ = _import_systems_goblin(app, tmp_path)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/systems-monsters",
        data={"entry_key": goblin_entry_key},
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None

    response = client.get(f"/campaigns/linden-pass/combat/dm?combatant={arden.id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Encounter status" in body
    assert "Turn order" in body
    assert "Encounter roster" not in body
    assert "combat-turn-order-row--selected" in body
    assert 'class="section-list combat-workspace-stack"' in body
    assert "data-combat-status-detail-root" in body
    assert body.index("data-combat-status-tracker-root") < body.index("data-combat-status-detail-root")
    assert f"/campaigns/linden-pass/combat/dm?combatant={arden.id}" in body
    assert 'id="combat-status-snapshot"' in body
    assert 'class="combat-status-identity-line"' in body
    assert 'aria-label="Combatant details"' in body
    assert "Compact encounter status first" not in body
    assert 'data-combat-inline-autosubmit' in body
    assert 'aria-label="Current HP for Arden March"' in body
    assert "Character sections" in body
    assert 'data-combat-section-group' in body
    assert 'data-combat-section-toggle="actions"' not in body
    assert 'data-combat-section-toggle="resources"' in body
    assert 'data-combat-section-panel="spells"' in body
    assert "Arden March" in body
    assert "Resources" in body
    assert "Scimitar" not in body


def test_dm_status_page_in_default_status_mode_includes_player_workspace_sections(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None

    response = client.get(f"/campaigns/linden-pass/combat/dm?combatant={arden.id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "DM status" in body
    assert 'name="combat_view" value="dm"' in body
    assert 'name="view" value="status"' in body
    assert "Character sections" in body
    assert 'data-combat-section-group' in body
    assert 'data-combat-section-toggle="actions"' not in body
    assert 'data-combat-section-toggle="resources"' in body
    assert 'class="ability-grid ability-grid--skills"' in body
    assert "ability-skill-list" in body
    assert "<h3>Skills</h3>" not in body
    assert f'data-combatant-id="{arden.id}"' in body


def test_dm_status_page_with_selected_systems_monster_includes_npc_workspace_sections(
    app,
    client,
    sign_in,
    users,
    tmp_path,
):
    goblin_entry_key, _ = _import_systems_goblin(app, tmp_path)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/systems-monsters",
        data={"entry_key": goblin_entry_key},
        follow_redirects=False,
    )

    goblin = _find_combatant(app, name="Goblin")
    assert goblin is not None

    response = client.get(f"/campaigns/linden-pass/combat/dm?combatant={goblin.id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "DM status" in body
    assert "NPC sections" in body
    assert "Systems monster detail" in body
    assert 'name="combat_view" value="dm"' in body
    assert 'name="view" value="status"' in body
    assert 'class="combat-status-identity-line"' in body
    assert 'data-combat-section-group' in body
    assert 'data-combat-section-toggle="actions"' in body
    assert 'data-combat-section-toggle="abilities_skills"' in body
    assert "Scimitar" in body


def test_dm_status_page_with_selected_dm_content_monster_includes_npc_workspace_sections(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    statblock = _create_dm_statblock(app, created_by_user_id=users["dm"]["id"])
    client.post(
        "/campaigns/linden-pass/combat/statblock-combatants",
        data={"statblock_id": statblock.id},
        follow_redirects=False,
    )

    brass_hound = _find_combatant(app, name="Brass Hound")
    assert brass_hound is not None

    response = client.get(f"/campaigns/linden-pass/combat/dm?combatant={brass_hound.id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "DM status" in body
    assert "NPC sections" in body
    assert "DM Content statblock detail" in body
    assert 'name="combat_view" value="dm"' in body
    assert 'name="view" value="status"' in body
    assert 'data-combat-section-group' in body
    assert 'data-combat-section-toggle="actions"' in body
    assert "Source file: brass-hound.md" in body
    assert "Bite" in body


def test_status_live_state_renders_player_workspace_sections_for_selected_pc(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None

    response = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={arden.id}",
        headers=_async_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["selected_combatant_id"] == arden.id
    assert "Character sections" in payload["detail_html"]
    assert 'data-combat-section-group' in payload["detail_html"]
    assert 'data-combat-section-toggle="actions"' not in payload["detail_html"]
    assert 'data-combat-section-panel="resources"' in payload["detail_html"]


def test_dm_status_can_update_selected_pc_equipment_state(
    app, client, sign_in, users, get_character
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None

    page = client.get(f"/campaigns/linden-pass/combat/dm?combatant={arden.id}")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "Save equipment state" not in body
    assert (
        f"/campaigns/linden-pass/combat/character/combatants/{arden.id}"
        "/equipment/quarterstaff-2/state"
    ) in body
    assert 'name="combat_view" value="dm"' in body
    assert 'name="view" value="status"' in body
    assert 'data-character-autosubmit' in body

    record = get_character("arden-march")
    assert _inventory_item(record, "quarterstaff-2")["is_equipped"] is True

    update_response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{arden.id}"
        "/equipment/quarterstaff-2/state",
        data={
            "expected_revision": record.state_record.revision,
            "combat_view": "dm",
            "view": "status",
            "combatant": arden.id,
            "weapon_wield_mode": "",
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert update_response.status_code == 200
    payload = update_response.get_json()
    assert payload["ok"] is True
    assert payload["selected_combatant_id"] == arden.id
    assert "Equipment state updated." in payload["flash_html"]
    assert "Save equipment state" not in payload["tracker_detail_html"]
    assert 'data-character-autosubmit' in payload["tracker_detail_html"]
    assert f'data-combat-section-panel="equipment"' in payload["tracker_detail_html"]

    record = get_character("arden-march")
    updated_item = _inventory_item(record, "quarterstaff-2")
    assert updated_item["is_equipped"] is False
    assert not updated_item.get("weapon_wield_mode")


def test_dm_status_renders_and_uses_selected_pc_item_actions(
    app, client, sign_in, users, get_character
):
    _seed_arden_innovators_bolt_item_action(app)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None

    page = client.get(f"/campaigns/linden-pass/combat/dm?combatant={arden.id}")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    item_action_url = (
        f"/campaigns/linden-pass/combat/character/combatants/{arden.id}"
        "/item-actions/innovators-bolt-enchanted-bullet/use"
    )
    assert 'id="character-item-use-actions"' in body
    assert "Enchanted Bullet" in body
    assert 'name="choice_id"' in body
    assert 'name="slot_selection"' in body
    assert item_action_url in body
    assert 'name="combat_view" value="dm"' in body
    assert 'name="view" value="status"' in body
    assert "Incendiary" in body
    assert "Booming" in body
    assert "Smoke" in body
    assert "table-managed" in body

    record = get_character("arden-march")
    starting_revision = record.state_record.revision
    first_level_slot = next(
        item
        for item in record.state_record.state["spell_slots"]
        if int(item.get("level") or 0) == 1
        and not str(item.get("slot_lane_id") or "").strip()
    )
    slot_selection = f"{str(first_level_slot.get('slot_lane_id') or '')}|{first_level_slot['level']}"

    use_response = client.post(
        item_action_url,
        data={
            "expected_revision": starting_revision,
            "combat_view": "dm",
            "view": "status",
            "combatant": arden.id,
            "choice_id": "incendiary",
            "slot_selection": slot_selection,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert use_response.status_code == 200
    payload = use_response.get_json()
    assert payload["ok"] is True
    assert payload["selected_combatant_id"] == arden.id
    assert "Item action used." in payload["flash_html"]
    assert 'id="character-item-use-actions"' in payload["tracker_detail_html"]
    assert "Enchanted Bullet" in payload["tracker_detail_html"]
    assert "Incendiary" in payload["tracker_detail_html"]

    record = get_character("arden-march")
    used_slot = next(
        item
        for item in record.state_record.state["spell_slots"]
        if int(item.get("level") or 0) == 1
        and not str(item.get("slot_lane_id") or "").strip()
    )
    assert used_slot["used"] == int(first_level_slot.get("used") or 0) + 1
    assert record.state_record.revision == starting_revision + 1

    stale_response = client.post(
        item_action_url,
        data={
            "expected_revision": starting_revision,
            "combat_view": "dm",
            "view": "status",
            "combatant": arden.id,
            "choice_id": "incendiary",
            "slot_selection": slot_selection,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert stale_response.status_code == 200
    assert stale_response.headers["X-Live-Mutation-Outcome"] == "character-revision-conflict"
    stale_payload = stale_response.get_json()
    assert stale_payload["ok"] is False
    assert "This sheet changed in another session" in stale_payload["flash_html"]

    record = get_character("arden-march")
    unchanged_slot = next(
        item
        for item in record.state_record.state["spell_slots"]
        if int(item.get("level") or 0) == 1
        and not str(item.get("slot_lane_id") or "").strip()
    )
    assert unchanged_slot["used"] == used_slot["used"]


def test_dm_status_can_update_selected_pc_resources_and_spell_slots(
    app, client, sign_in, users, get_character
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None

    page = client.get(f"/campaigns/linden-pass/combat/dm?combatant={arden.id}")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "combat-resource-state-form" in body
    assert f"/campaigns/linden-pass/combat/character/combatants/{arden.id}/resources/sorcery-points" in body
    assert "combat-spell-slot-row" in body
    assert f"/campaigns/linden-pass/combat/character/combatants/{arden.id}/spell-slots/2" in body
    assert body.count("combat-spellcasting-summary") == 1
    assert body.count("Save DC 15") >= 1
    assert body.count("Attack +7") >= 1
    assert 'name="combat_view" value="dm"' in body
    assert 'name="view" value="status"' in body

    record = get_character("arden-march")
    resource_response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{arden.id}/resources/sorcery-points",
        data={
            "expected_revision": record.state_record.revision,
            "combat_view": "dm",
            "view": "status",
            "combatant": arden.id,
            "current": 3,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert resource_response.status_code == 200
    resource_payload = resource_response.get_json()
    assert resource_payload["ok"] is True
    assert resource_payload["selected_combatant_id"] == arden.id
    assert "Resource updated." in resource_payload["flash_html"]
    assert "combat-resource-state-form" in resource_payload["tracker_detail_html"]

    record = get_character("arden-march")
    resources = {item["id"]: item for item in record.state_record.state["resources"]}
    assert resources["sorcery-points"]["current"] == 3

    spell_response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{arden.id}/spell-slots/2",
        data={
            "expected_revision": record.state_record.revision,
            "combat_view": "dm",
            "view": "status",
            "combatant": arden.id,
            "used": 2,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert spell_response.status_code == 200
    spell_payload = spell_response.get_json()
    assert spell_payload["ok"] is True
    assert spell_payload["selected_combatant_id"] == arden.id
    assert "Spell slot usage updated." in spell_payload["flash_html"]
    assert "combat-spell-slot-row" in spell_payload["tracker_detail_html"]

    record = get_character("arden-march")
    spell_slots = {item["level"]: item for item in record.state_record.state["spell_slots"]}
    assert spell_slots[2]["used"] == 2

    spell_delta_response = client.post(
        f"/campaigns/linden-pass/combat/character/combatants/{arden.id}/spell-slots/2",
        data={
            "expected_revision": record.state_record.revision,
            "combat_view": "dm",
            "view": "status",
            "combatant": arden.id,
            "used": 2,
            "delta_used": 1,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )

    assert spell_delta_response.status_code == 200
    spell_delta_payload = spell_delta_response.get_json()
    assert spell_delta_payload["ok"] is True
    assert spell_delta_payload["selected_combatant_id"] == arden.id
    assert "Spell slot usage updated." in spell_delta_payload["flash_html"]
    assert "combat-spell-slot-row" in spell_delta_payload["tracker_detail_html"]
    _assert_spell_slot_html_state(spell_delta_payload["tracker_detail_html"], used=3, available=0, maximum=3)

    record = get_character("arden-march")
    spell_slots = {item["level"]: item for item in record.state_record.state["spell_slots"]}
    assert spell_slots[2]["used"] == 3


def test_status_live_state_renders_npc_workspace_sections_for_selected_systems_monster(
    app, client, sign_in, users, tmp_path
):
    goblin_entry_key, _ = _import_systems_goblin(app, tmp_path)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/systems-monsters",
        data={"entry_key": goblin_entry_key},
        follow_redirects=False,
    )

    goblin = _find_combatant(app, name="Goblin")
    assert goblin is not None

    response = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={goblin.id}",
        headers=_async_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["selected_combatant_id"] == goblin.id
    assert "NPC sections" in payload["detail_html"]
    assert 'data-combat-section-group' in payload["detail_html"]
    assert 'data-combat-section-toggle="actions"' in payload["detail_html"]
    assert 'data-combat-section-toggle="abilities_skills"' in payload["detail_html"]
    assert 'data-combat-section-toggle="bonus_actions"' not in payload["detail_html"]
    assert 'data-combat-section-toggle="reactions"' not in payload["detail_html"]
    assert 'data-combat-section-toggle="legendary_actions"' not in payload["detail_html"]
    assert 'data-combat-section-toggle="lair_actions"' not in payload["detail_html"]
    assert 'data-combat-section-toggle="traits"' not in payload["detail_html"]
    assert 'data-combat-section-toggle="resources"' not in payload["detail_html"]
    assert 'data-combat-section-panel="actions"' in payload["detail_html"]
    assert 'data-combat-section-panel="traits"' not in payload["detail_html"]


def test_dm_status_page_sidebar_selection_is_wired_for_in_place_detail_swaps(
    app, client, sign_in, users, tmp_path
):
    goblin_entry_key, _ = _import_systems_goblin(app, tmp_path)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/systems-monsters",
        data={"entry_key": goblin_entry_key},
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    goblin = _find_combatant(app, name="Goblin")
    assert arden is not None
    assert goblin is not None

    response = client.get(f"/campaigns/linden-pass/combat/dm?combatant={arden.id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "data-combat-status-select" in body
    assert f'data-combatant-id="{arden.id}"' in body
    assert f'data-combatant-id="{goblin.id}"' in body
    combat_script = _combat_live_script_text()
    assert "const fetchDmStatusCombatant = async" in combat_script
    assert "void fetchDmStatusCombatant(selectedCombatantId, { carousel });" in combat_script
    assert "syncViewUrls(payload);" in combat_script
    assert 'window.history.replaceState(null, "", nextPageUrl);' in combat_script
    assert "const combatWorkspaceTools = window.__playerWikiCombatWorkspace || null;" in combat_script
    assert "combatWorkspaceTools.capture(liveRoot)" in combat_script
    assert "combatWorkspaceTools.restore(" in combat_script


def test_dm_status_page_can_render_systems_monster_detail(app, client, sign_in, users, tmp_path):
    goblin_entry_key, _ = _import_systems_goblin(app, tmp_path)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/systems-monsters",
        data={"entry_key": goblin_entry_key},
        follow_redirects=False,
    )

    goblin = _find_combatant(app, name="Goblin")
    assert goblin is not None

    response = client.get(f"/campaigns/linden-pass/combat/dm?combatant={goblin.id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'id="combat-status-snapshot"' in body
    assert 'class="combat-status-identity-line"' in body
    assert 'aria-label="Combatant details"' in body
    assert "NPC sections" in body
    assert "Systems monster detail" in body
    assert 'data-combat-section-group' in body
    assert 'data-combat-section-toggle="actions"' in body
    assert 'data-combat-section-toggle="abilities_skills"' in body
    assert 'data-combat-section-toggle="bonus_actions"' not in body
    assert 'data-combat-section-toggle="reactions"' not in body
    assert 'data-combat-section-toggle="legendary_actions"' not in body
    assert 'data-combat-section-toggle="lair_actions"' not in body
    assert 'data-combat-section-toggle="traits"' not in body
    assert 'data-combat-section-toggle="resources"' not in body
    assert "Open Systems entry" in body
    assert "Scimitar" in body


def test_dm_status_page_can_render_dm_content_statblock_detail(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    statblock = _create_dm_statblock(app, created_by_user_id=users["dm"]["id"])
    client.post(
        "/campaigns/linden-pass/combat/statblock-combatants",
        data={"statblock_id": statblock.id},
        follow_redirects=False,
    )

    brass_hound = _find_combatant(app, name="Brass Hound")
    assert brass_hound is not None

    response = client.get(f"/campaigns/linden-pass/combat/dm?combatant={brass_hound.id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'id="combat-status-snapshot"' in body
    assert "NPC sections" in body
    assert "DM Content statblock detail" in body
    assert 'data-combat-section-group' in body
    assert 'data-combat-section-toggle="actions"' in body
    assert 'data-combat-section-toggle="bonus_actions"' not in body
    assert 'data-combat-section-toggle="reactions"' not in body
    assert 'data-combat-section-toggle="legendary_actions"' not in body
    assert 'data-combat-section-toggle="lair_actions"' not in body
    assert 'data-combat-section-toggle="traits"' not in body
    assert 'data-combat-section-toggle="resources"' not in body
    assert 'data-combat-section-toggle="abilities_skills"' not in body
    assert "Source file: brass-hound.md" in body
    assert "Bite" in body


def test_dm_statblock_source_changes_preserve_combat_snapshot_and_refresh_dynamic_detail(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    statblock = _create_dm_statblock(
        app,
        created_by_user_id=users["dm"]["id"],
        filename="hex-adept-snapshot.md",
        markdown_text="""---
title: Hex Adept Snapshot
armor_class: 13
hp: 33
speed: 30 ft.
initiative_bonus: 2
---

STR 10 (+0)  DEX 14 (+2)  CON 12 (+1)  INT 10 (+0)  WIS 10 (+0)  CHA 16 (+3)

## Traits

### Innate Spellcasting

3/day each: misty step, charm person.

## Actions

### Ember Bolt

The adept hurls a coal-bright bolt.
""",
    )
    seed_response = client.post(
        "/campaigns/linden-pass/combat/statblock-combatants",
        data={"statblock_id": statblock.id, "initiative_priority": 4},
        follow_redirects=False,
    )
    assert seed_response.status_code == 302

    seeded = _find_combatant(app, name="Hex Adept Snapshot")
    assert seeded is not None
    with app.app_context():
        combat_service = app.extensions["campaign_combat_service"]
        seeded_counters = combat_service.list_resource_counters_by_combatant(
            "linden-pass"
        ).get(seeded.id, [])
        revision_after_seed = combat_service.get_live_revision("linden-pass")
    seeded_snapshot = (
        seeded.display_name,
        seeded.turn_value,
        seeded.initiative_bonus,
        seeded.dexterity_modifier,
        seeded.initiative_priority,
        seeded.current_hp,
        seeded.max_hp,
        seeded.movement_total,
        seeded.movement_remaining,
        seeded.source_kind,
        seeded.source_ref,
        [(counter.label, counter.current_value, counter.max_value) for counter in seeded_counters],
    )
    assert seeded_snapshot == (
        "Hex Adept Snapshot",
        2,
        2,
        2,
        4,
        33,
        33,
        30,
        30,
        "dm_statblock",
        str(statblock.id),
        [("misty step", 3, 3), ("charm person", 3, 3)],
    )

    update_response = client.post(
        f"/campaigns/linden-pass/dm-content/statblocks/{statblock.id}",
        data={
            "subsection": "Ascendants",
            "body_markdown": """---
title: Ascendant Hex Adept
armor_class: 19
hp: 99
speed: 60 ft.
initiative_bonus: 9
---

STR 10 (+0)  DEX 20 (+5)  CON 18 (+4)  INT 10 (+0)  WIS 10 (+0)  CHA 20 (+5)

## Traits

### Innate Spellcasting

1/day: dimension door.

## Actions

### Frost Nova

The adept freezes every nearby foe.
""",
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 302

    retained = _find_combatant(app, name="Hex Adept Snapshot")
    assert retained is not None
    with app.app_context():
        combat_service = app.extensions["campaign_combat_service"]
        retained_counters = combat_service.list_resource_counters_by_combatant(
            "linden-pass"
        ).get(retained.id, [])
        assert combat_service.get_live_revision("linden-pass") == revision_after_seed
    assert (
        retained.display_name,
        retained.turn_value,
        retained.initiative_bonus,
        retained.dexterity_modifier,
        retained.initiative_priority,
        retained.current_hp,
        retained.max_hp,
        retained.movement_total,
        retained.movement_remaining,
        retained.source_kind,
        retained.source_ref,
        [(counter.label, counter.current_value, counter.max_value) for counter in retained_counters],
    ) == seeded_snapshot

    detail_response = client.get(
        f"/campaigns/linden-pass/combat/dm?combatant={retained.id}"
    )
    detail_html = detail_response.get_data(as_text=True)
    assert detail_response.status_code == 200
    assert "Ascendant Hex Adept" in detail_html
    assert "Frost Nova" in detail_html
    assert "Ember Bolt" not in detail_html

    delete_response = client.post(
        f"/campaigns/linden-pass/dm-content/statblocks/{statblock.id}/delete",
        follow_redirects=False,
    )
    assert delete_response.status_code == 302
    after_delete = _find_combatant(app, name="Hex Adept Snapshot")
    assert after_delete is not None
    assert after_delete.source_kind == "dm_statblock"
    assert after_delete.source_ref == str(statblock.id)
    with app.app_context():
        assert (
            app.extensions["campaign_combat_service"].get_live_revision("linden-pass")
            == revision_after_seed
        )

    missing_response = client.get(
        f"/campaigns/linden-pass/combat/dm?combatant={after_delete.id}"
    )
    missing_html = missing_response.get_data(as_text=True)
    assert missing_response.status_code == 200
    assert "Source detail unavailable" in missing_html
    assert "no longer available" in missing_html


def test_dm_status_page_groups_reference_npc_sections_under_reference_tab(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    statblock = _create_dm_statblock(
        app,
        created_by_user_id=users["dm"]["id"],
        filename="mirror-spy.md",
        markdown_text="""---
title: Mirror Spy
armor_class: 14
hp: 27
speed: 30 ft.
initiative_bonus: 3
---

## AT-A-GLANCE (Quick Reference)

A cautious infiltrator who prefers disguise, distance, and retreat routes over fair fights.

## STATBLOCK (5e Format)

Medium humanoid, neutral

## TACTICS (DM Guidance)

Mirror Spy opens from range and only closes when an ally has already pinned the target.

## SCALING NOTES (optional)

Increase hit points to 36 and add one extra reaction each round for a tougher version.

## Notes

Tracks party rumors and tries to escape instead of fighting to the death.

## Changeling

Can alter appearance between encounters to re-enter a scene under a different identity.

## Actions

### Dagger

+5 to hit, 5 piercing damage.
""",
    )
    client.post(
        "/campaigns/linden-pass/combat/statblock-combatants",
        data={"statblock_id": statblock.id},
        follow_redirects=False,
    )

    mirror_spy = _find_combatant(app, name="Mirror Spy")
    assert mirror_spy is not None

    response = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={mirror_spy.id}",
        headers=_async_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["selected_combatant_id"] == mirror_spy.id
    assert 'data-combat-default-section="reference"' in payload["detail_html"]
    assert 'data-combat-section-toggle="reference"' in payload["detail_html"]
    assert 'data-combat-section-panel="reference"' in payload["detail_html"]
    assert 'data-combat-section-toggle="actions"' in payload["detail_html"]
    assert "AT-A-GLANCE (Quick Reference)" in payload["detail_html"]
    assert "STATBLOCK (5e Format)" in payload["detail_html"]
    assert "TACTICS (DM Guidance)" in payload["detail_html"]
    assert "SCALING NOTES (optional)" in payload["detail_html"]
    assert "Notes" in payload["detail_html"]
    assert "Changeling" in payload["detail_html"]
    assert "Dagger" in payload["detail_html"]


def test_dm_status_page_shows_manual_npc_fallback_and_missing_source_fallback(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )
    statblock = _create_dm_statblock(app, created_by_user_id=users["dm"]["id"])
    client.post(
        "/campaigns/linden-pass/combat/statblock-combatants",
        data={"statblock_id": statblock.id},
        follow_redirects=False,
    )

    clockwork_hound = _find_combatant(app, name="Clockwork Hound")
    brass_hound = _find_combatant(app, name="Brass Hound")
    assert clockwork_hound is not None
    assert brass_hound is not None

    manual_response = client.get(f"/campaigns/linden-pass/combat/dm?combatant={clockwork_hound.id}")
    assert manual_response.status_code == 200
    assert "added manually" in manual_response.get_data(as_text=True)

    with app.app_context():
        app.extensions["campaign_dm_content_service"].delete_statblock(TEST_CAMPAIGN_SLUG, statblock.id)

    missing_response = client.get(f"/campaigns/linden-pass/combat/dm?combatant={brass_hound.id}")
    assert missing_response.status_code == 200
    missing_body = missing_response.get_data(as_text=True)
    assert "Source detail unavailable" in missing_body
    assert "no longer available" in missing_body


def test_status_live_state_preserves_selected_target_and_returns_selected_detail(
    app, client, sign_in, users, tmp_path
):
    goblin_entry_key, _ = _import_systems_goblin(app, tmp_path)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/systems-monsters",
        data={"entry_key": goblin_entry_key},
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    goblin = _find_combatant(app, name="Goblin")
    assert arden is not None
    assert goblin is not None

    first_live_state = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={goblin.id}",
        headers=_async_headers(),
    )

    assert first_live_state.status_code == 200
    first_payload = first_live_state.get_json()
    assert first_payload["selected_combatant_id"] == goblin.id
    assert "Turn order" in first_payload["board_html"]
    assert "Encounter roster" not in first_payload["board_html"]
    assert "combat-turn-order-row--selected" in first_payload["board_html"]
    assert f"/campaigns/linden-pass/combat/dm?combatant={goblin.id}" in first_payload["board_html"]
    assert f"/campaigns/linden-pass/combat/status?combatant={goblin.id}" not in first_payload["board_html"]
    assert "Goblin" in first_payload["detail_html"]
    assert "Scimitar" in first_payload["detail_html"]
    assert "Arden March" not in first_payload["detail_html"]

    client.post(
        f"/campaigns/linden-pass/combat/combatants/{arden.id}/set-current",
        follow_redirects=False,
    )
    second_live_state = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={goblin.id}",
        headers=_async_headers(),
    )

    assert second_live_state.status_code == 200
    second_payload = second_live_state.get_json()
    assert second_payload["selected_combatant_id"] == goblin.id
    assert "Turn order" in second_payload["board_html"]
    assert "combat-turn-order-row--selected" in second_payload["board_html"]
    assert "Goblin" in second_payload["detail_html"]
    assert "Scimitar" in second_payload["detail_html"]


def test_status_live_state_short_circuits_for_unchanged_selected_target(
    app, client, sign_in, users, tmp_path
):
    goblin_entry_key, _ = _import_systems_goblin(app, tmp_path)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/systems-monsters",
        data={"entry_key": goblin_entry_key},
        follow_redirects=False,
    )

    goblin = _find_combatant(app, name="Goblin")
    assert goblin is not None

    initial_live_state = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={goblin.id}",
        headers=_async_headers(),
    )

    assert initial_live_state.status_code == 200
    initial_payload = initial_live_state.get_json()
    assert initial_payload["changed"] is True

    unchanged_live_state = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={goblin.id}",
        headers=_live_poll_headers(initial_payload["live_revision"], initial_payload["live_view_token"]),
    )

    assert unchanged_live_state.status_code == 200
    assert unchanged_live_state.get_json() == {
        "changed": False,
        "live_revision": initial_payload["live_revision"],
        "live_view_token": initial_payload["live_view_token"],
    }
    assert unchanged_live_state.headers["X-Live-State-Changed"] == "false"
    _assert_live_diagnostics_headers(initial_live_state)
    _assert_live_diagnostics_headers(unchanged_live_state)


def test_status_live_state_reuses_selected_detail_html_only_when_state_changes(
    app, client, sign_in, users, tmp_path
):
    goblin_entry_key, _ = _import_systems_goblin(app, tmp_path)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/systems-monsters",
        data={"entry_key": goblin_entry_key},
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    goblin = _find_combatant(app, name="Goblin")
    assert arden is not None
    assert goblin is not None

    initial_live_state = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={goblin.id}",
        headers=_async_headers(),
    )
    assert initial_live_state.status_code == 200
    initial_payload = initial_live_state.get_json()
    assert "detail_html" in initial_payload
    initial_detail_token = initial_payload["combatant_detail_state_token"]

    client.post(
        f"/campaigns/linden-pass/combat/combatants/{arden.id}/resources",
        data={
            "combat_view": "status",
            "combatant": arden.id,
            "has_action": "1",
            "expected_combatant_revision": arden.revision,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )
    unchanged_detail_token_poll = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={goblin.id}",
        headers=_live_poll_headers(
            initial_payload["live_revision"],
            initial_payload["live_view_token"],
            initial_detail_token,
        ),
    )
    assert unchanged_detail_token_poll.status_code == 200
    unchanged_payload = unchanged_detail_token_poll.get_json()
    assert unchanged_payload["changed"] is True
    assert unchanged_payload["selected_combatant_id"] == goblin.id
    assert unchanged_payload["combatant_detail_state_token"] == initial_detail_token
    assert "detail_html" not in unchanged_payload
    assert "board_html" in unchanged_payload
    assert f'data-combatant-id="{arden.id}"' in unchanged_payload["board_html"]

    focus_payload_response = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={arden.id}",
        headers=_live_poll_headers(
            unchanged_payload["live_revision"],
            unchanged_payload["live_view_token"],
            unchanged_payload["combatant_detail_state_token"],
        ),
    )
    assert focus_payload_response.status_code == 200
    focus_payload = focus_payload_response.get_json()
    assert focus_payload["selected_combatant_id"] == arden.id
    assert "detail_html" in focus_payload
    focus_detail_token = focus_payload["combatant_detail_state_token"]
    assert focus_detail_token != initial_detail_token
    assert "Arden March" in focus_payload["detail_html"]

    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None
    client.post(
        f"/campaigns/linden-pass/combat/combatants/{arden.id}/resources",
        data={
            "combat_view": "status",
            "combatant": arden.id,
            "movement_remaining": 8,
            "expected_combatant_revision": arden.revision,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )
    tactical_change_payload = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={arden.id}",
        headers=_live_poll_headers(
            focus_payload["live_revision"],
            focus_payload["live_view_token"],
            focus_detail_token,
        ),
    )
    assert tactical_change_payload.status_code == 200
    tactical_payload = tactical_change_payload.get_json()
    assert tactical_payload["combatant_detail_state_token"] != focus_detail_token
    assert "detail_html" in tactical_payload


def test_status_live_state_detail_cache_reuses_rendered_selected_detail_html(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    hound = _find_combatant(app, name="Clockwork Hound")
    assert arden is not None
    assert hound is not None

    app_module._clear_combat_status_detail_html_cache()
    render_calls = {"combat_status_detail": 0}
    original_render_template = app_module.render_template

    def _count_status_detail_render(template_name, **context):
        if template_name == "_combat_status_detail.html":
            render_calls["combat_status_detail"] += 1
        return original_render_template(template_name, **context)

    monkeypatch.setattr(app_module, "render_template", _count_status_detail_render)
    initial_response = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={hound.id}",
        headers=_async_headers(),
    )
    assert initial_response.status_code == 200
    initial_payload = initial_response.get_json()
    initial_detail_html = initial_payload["detail_html"]
    initial_detail_token = initial_payload["combatant_detail_state_token"]
    assert "detail_html" in initial_payload
    assert initial_detail_token
    assert render_calls["combat_status_detail"] == 1

    client.post(
        f"/campaigns/linden-pass/combat/combatants/{arden.id}/resources",
        data={
            "combat_view": "status",
            "combatant": arden.id,
            "has_action": "1",
            "expected_combatant_revision": arden.revision,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )
    render_calls_before_reuse_check = render_calls["combat_status_detail"]

    reused_detail_response = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={hound.id}",
        headers=_async_headers(),
    )
    assert reused_detail_response.status_code == 200
    reused_payload = reused_detail_response.get_json()
    assert reused_payload["detail_html"] == initial_detail_html
    assert reused_payload["combatant_detail_state_token"] == initial_detail_token
    assert "board_html" in reused_payload
    assert render_calls["combat_status_detail"] == render_calls_before_reuse_check


def test_dm_status_live_state_detail_cache_reuses_rendered_selected_detail_html(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    hound = _find_combatant(app, name="Clockwork Hound")
    assert arden is not None
    assert hound is not None

    app_module._clear_combat_status_detail_html_cache()
    render_calls = {"combat_status_detail": 0}
    original_render_template = app_module.render_template

    def _count_status_detail_render(template_name, **context):
        if template_name == "_combat_status_detail.html":
            render_calls["combat_status_detail"] += 1
        return original_render_template(template_name, **context)

    monkeypatch.setattr(app_module, "render_template", _count_status_detail_render)
    initial_response = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={hound.id}",
        headers=_async_headers(),
    )
    assert initial_response.status_code == 200
    initial_payload = initial_response.get_json()
    initial_detail_html = initial_payload["tracker_detail_html"]
    initial_detail_token = initial_payload["combatant_detail_state_token"]
    assert "tracker_detail_html" in initial_payload
    assert render_calls["combat_status_detail"] == 1

    client.post(
        f"/campaigns/linden-pass/combat/combatants/{arden.id}/resources",
        data={
            "combat_view": "dm",
            "view": "status",
            "combatant": arden.id,
            "has_action": "1",
            "expected_combatant_revision": arden.revision,
        },
        headers=_async_headers(),
        follow_redirects=False,
    )
    render_calls_before_reuse_check = render_calls["combat_status_detail"]

    reused_response = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={hound.id}",
        headers=_async_headers(),
    )
    assert reused_response.status_code == 200
    reused_payload = reused_response.get_json()
    assert reused_payload["tracker_detail_html"] == initial_detail_html
    assert reused_payload["combatant_detail_state_token"] == initial_detail_token
    assert "tracker_html" in reused_payload
    assert render_calls["combat_status_detail"] == render_calls_before_reuse_check


def test_combat_surface_live_payloads_report_canonical_focus_urls(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    hound = _find_combatant(app, name="Clockwork Hound")
    assert hound is not None

    combat_payload = client.get(
        f"/campaigns/linden-pass/combat/live-state?combatant={hound.id}",
        headers=_async_headers(),
    ).get_json()
    controls_payload = client.get(
        f"/campaigns/linden-pass/combat/dm/live-state?combatant={hound.id}",
        headers=_async_headers(),
    ).get_json()
    status_payload = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={hound.id}",
        headers=_async_headers(),
    ).get_json()

    assert combat_payload["page_url"] == f"/campaigns/linden-pass/combat?combatant={hound.id}"
    assert combat_payload["live_url"] == f"/campaigns/linden-pass/combat/live-state?combatant={hound.id}"
    assert controls_payload["page_url"] == f"/campaigns/linden-pass/combat/dm?combatant={hound.id}"
    assert controls_payload["live_url"] == f"/campaigns/linden-pass/combat/dm/live-state?combatant={hound.id}"
    assert status_payload["page_url"] == f"/campaigns/linden-pass/combat/dm?combatant={hound.id}"
    assert status_payload["live_url"] == f"/campaigns/linden-pass/combat/status/live-state?combatant={hound.id}"


def test_status_live_state_falls_back_to_remaining_target_when_selected_combatant_disappears(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Clockwork Hound",
            "turn_value": 12,
            "current_hp": 22,
            "max_hp": 22,
            "temp_hp": 0,
            "movement_total": 40,
        },
        follow_redirects=False,
    )

    arden = _find_combatant(app, character_slug="arden-march")
    hound = _find_combatant(app, name="Clockwork Hound")
    assert arden is not None
    assert hound is not None

    delete_response = client.post(
        f"/campaigns/linden-pass/combat/combatants/{hound.id}/delete",
        follow_redirects=False,
    )
    assert delete_response.status_code == 302

    fallback_response = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={hound.id}",
        headers=_async_headers(),
    )

    assert fallback_response.status_code == 200
    fallback_payload = fallback_response.get_json()
    assert fallback_payload["selected_combatant_id"] == arden.id
    assert fallback_payload["page_url"] == f"/campaigns/linden-pass/combat/dm?combatant={arden.id}"
    assert fallback_payload["live_url"] == f"/campaigns/linden-pass/combat/status/live-state?combatant={arden.id}"
    assert "Arden March" in fallback_payload["detail_html"]
    assert "Clockwork Hound" not in fallback_payload["detail_html"]


def test_combat_loading_styles_do_not_dim_live_combat_surfaces():
    css = Path("player_wiki/static/styles.css").read_text(encoding="utf-8")

    assert "combat-live-root][data-loading" not in css
    assert "combat-status-live-root][data-loading" not in css
    assert "combat-character-live-root][data-loading" not in css


def test_combat_styles_include_mobile_tablet_carousel_responsive_hooks():
    css = Path("player_wiki/static/styles.css").read_text(encoding="utf-8")

    assert ".combat-layout--workspace .combat-turn-order-carousel" in css
    assert ".combat-layout--workspace .combat-turn-order-list--carousel .combat-turn-order-row" in css
    assert ".combat-layout--workspace .combat-turn-order-control" in css
    assert ".combat-layout--workspace .combat-turn-order-jump" in css
    assert "@media (max-width: 1100px)" in css
    assert re.search(
        r"@media\s*\(\s*max-width:\s*1100px\s*\)\s*\{[\s\S]*combat-turn-order-carousel",
        css,
        re.M | re.S,
    )
    assert re.search(
        r"@media\s*\(\s*max-width:\s*820px\s*\)\s*\{[\s\S]*combat-layout--workspace",
        css,
        re.M | re.S,
    )


def test_combat_styles_hide_hidden_selected_carousel_indicators():
    css = Path("player_wiki/static/styles.css").read_text(encoding="utf-8")

    assert ".combat-turn-order-list--carousel [data-combatant-selected-badge][hidden]" in css
    assert ".combat-turn-order-list--carousel [data-combatant-selected-summary][hidden]" in css
    assert re.search(
        r"\.combat-turn-order-list--carousel\s+\[data-combatant-selected-badge\]\[hidden\][^{]*\{[^}]*display:\s*none\s*!important",
        css,
        re.S,
    )
    assert re.search(
        r"\.combat-turn-order-list--carousel\s+\[data-combatant-selected-summary\]\[hidden\][^{]*\{[^}]*display:\s*none\s*!important",
        css,
        re.S,
    )


def test_live_state_logs_slow_response_warning_without_live_diagnostics(
    app,
    client,
    sign_in,
    users,
    caplog,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    app.config.update(
        LIVE_DIAGNOSTICS=False,
        LIVE_SLOW_LOG_THRESHOLD_MS=0.01,
    )

    caplog.set_level(logging.WARNING)

    response = client.get(
        "/campaigns/linden-pass/combat/live-state",
        headers=_async_headers(),
    )

    assert response.status_code == 200

    slow_records = [
        record
        for record in caplog.records
        if record.message.startswith("slow_live_response ")
    ]
    assert slow_records

    slow_payload = json.loads(slow_records[-1].message.split(" ", 1)[1])
    assert slow_payload["view"] == "combat"
    assert slow_payload["path"] == "/campaigns/linden-pass/combat/live-state"
    assert slow_payload["changed"] is True
    assert slow_payload["request_time_ms"] >= 0.01


def test_sync_player_character_snapshots_throttles_repeated_refreshes(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    with app.app_context():
        combat_service = app.extensions["campaign_combat_service"]

    combat_service.player_snapshot_sync_interval_seconds = 5.0
    current_time = {"value": 100.0}
    sync_lookup_calls: list[tuple[str, str]] = []
    original_get_visible_character = combat_service.character_repository.get_visible_character

    def count_lookup(campaign_slug: str, character_slug: str):
        sync_lookup_calls.append((campaign_slug, character_slug))
        return original_get_visible_character(campaign_slug, character_slug)

    monkeypatch.setattr(campaign_combat_service_module.time, "monotonic", lambda: current_time["value"])
    monkeypatch.setattr(combat_service.character_repository, "get_visible_character", count_lookup)

    with app.app_context():
        combat_service.sync_player_character_snapshots("linden-pass")
        current_time["value"] = 101.0
        combat_service.sync_player_character_snapshots("linden-pass")
        current_time["value"] = 106.0
        combat_service.sync_player_character_snapshots("linden-pass")

    assert sync_lookup_calls == [
        ("linden-pass", "arden-march"),
        ("linden-pass", "arden-march"),
    ]


def test_combat_live_metadata_uses_nonblocking_player_snapshot_sync(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    with app.app_context():
        combat_service = app.extensions["campaign_combat_service"]

    sync_calls: list[tuple[str, bool]] = []
    original_sync = combat_service.sync_player_character_snapshots

    def track_sync(campaign_slug: str, *, blocking: bool = True):
        sync_calls.append((campaign_slug, blocking))
        return original_sync(campaign_slug, blocking=blocking)

    monkeypatch.setattr(combat_service, "sync_player_character_snapshots", track_sync)

    response = client.get("/campaigns/linden-pass/combat/live-state", headers=_async_headers())
    assert response.status_code == 200
    assert sync_calls == [("linden-pass", False)]


def test_combat_live_requests_sync_player_snapshots_once_per_request(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    arden = _find_combatant(app, character_slug="arden-march")
    assert arden is not None

    with app.app_context():
        combat_service = app.extensions["campaign_combat_service"]

    sync_calls: list[tuple[str, bool]] = []
    original_sync = combat_service.sync_player_character_snapshots

    def count_sync(campaign_slug: str, *, blocking: bool = True):
        sync_calls.append((campaign_slug, blocking))
        return original_sync(campaign_slug, blocking=blocking)

    monkeypatch.setattr(combat_service, "sync_player_character_snapshots", count_sync)

    combat_live_state = client.get(
        "/campaigns/linden-pass/combat/live-state",
        headers=_async_headers(),
    )
    assert combat_live_state.status_code == 200
    assert sync_calls == [("linden-pass", False)]

    sync_calls.clear()

    status_live_state = client.get(
        f"/campaigns/linden-pass/combat/status/live-state?combatant={arden.id}",
        headers=_async_headers(),
    )
    assert status_live_state.status_code == 200
    assert sync_calls == [("linden-pass", False)]


def test_sync_player_character_snapshots_nonblocking_mode_avoids_lookup_when_locked(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    with app.app_context():
        combat_service = app.extensions["campaign_combat_service"]

    combat_service.player_snapshot_sync_interval_seconds = 5.0
    combat_service._player_snapshot_sync_completed_at["linden-pass"] = 0.0

    lookup_calls: list[tuple[str, str]] = []
    original_get_visible_character = combat_service.character_repository.get_visible_character

    def count_lookup(campaign_slug: str, character_slug: str):
        lookup_calls.append((campaign_slug, character_slug))
        return original_get_visible_character(campaign_slug, character_slug)

    class _ContendedLock:
        def __init__(self):
            self.acquire_calls: list[bool] = []

        def acquire(self, blocking: bool = True, timeout: float = -1.0) -> bool:
            self.acquire_calls.append(blocking)
            return False if not blocking else True

        def __enter__(self):
            acquired = self.acquire()
            if not acquired:
                raise AssertionError("Blocking lock acquisition should not happen in nonblocking mode.")
            return self

        def __exit__(self, *args):
            return None

        def release(self):
            return None

    contended_lock = _ContendedLock()
    current_time = {"value": 100.0}

    monkeypatch.setattr(campaign_combat_service_module.time, "monotonic", lambda: current_time["value"])
    monkeypatch.setattr(combat_service.character_repository, "get_visible_character", count_lookup)
    monkeypatch.setattr(combat_service, "_player_snapshot_sync_lock", contended_lock)

    combat_service.sync_player_character_snapshots("linden-pass", blocking=False)

    assert lookup_calls == []
    assert contended_lock.acquire_calls == [False]


def test_combat_live_state_records_pre_lock_snapshot_sync_throttle_metric(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    with app.app_context():
        combat_service = app.extensions["campaign_combat_service"]

    app.config.update(LIVE_DIAGNOSTICS=True)
    combat_service.player_snapshot_sync_interval_seconds = 5.0
    combat_service._player_snapshot_sync_completed_at["linden-pass"] = 100.0

    monkeypatch.setattr(
        campaign_combat_service_module.time,
        "monotonic",
        lambda: 102.0,
    )

    response = client.get("/campaigns/linden-pass/combat/live-state", headers=_async_headers())
    assert response.status_code == 200

    summary = _live_snapshot_sync_summary(response)
    assert summary["snapshot_sync_status"] == "skipped_throttle_pre_lock"
    assert summary["snapshot_sync_ran"] is False
    assert summary["snapshot_sync_changed"] is False
    assert summary["snapshot_sync_lock_acquired"] is False


def test_combat_live_state_records_nonblocking_lock_skip_metric(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    with app.app_context():
        combat_service = app.extensions["campaign_combat_service"]

    app.config.update(LIVE_DIAGNOSTICS=True)
    combat_service.player_snapshot_sync_interval_seconds = 5.0
    combat_service._player_snapshot_sync_completed_at["linden-pass"] = 0.0

    class _ContendedLock:
        def acquire(self, blocking: bool = True, timeout: float = -1.0) -> bool:
            assert not blocking
            return False

        def release(self):
            raise AssertionError("release() should not be called when lock acquisition fails.")

    monkeypatch.setattr(campaign_combat_service_module.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(combat_service, "_player_snapshot_sync_lock", _ContendedLock())

    response = client.get("/campaigns/linden-pass/combat/live-state", headers=_async_headers())
    assert response.status_code == 200

    summary = _live_snapshot_sync_summary(response)
    assert summary["snapshot_sync_status"] == "skipped_lock_busy_nonblocking"
    assert summary["snapshot_sync_ran"] is False
    assert summary["snapshot_sync_lock_acquired"] is False


def test_combat_live_state_records_snapshot_sync_execution_metrics(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )

    with app.app_context():
        combat_service = app.extensions["campaign_combat_service"]

    app.config.update(LIVE_DIAGNOSTICS=True)
    combat_service.player_snapshot_sync_interval_seconds = 5.0
    combat_service._player_snapshot_sync_completed_at["linden-pass"] = 0.0

    perf_counter_calls = {"count": 1000.0}

    def fake_perf_counter() -> float:
        perf_counter_calls["count"] += 1.0
        return perf_counter_calls["count"]

    monkeypatch.setattr(campaign_combat_service_module.time, "perf_counter", fake_perf_counter)
    monkeypatch.setattr(campaign_combat_service_module.time, "monotonic", lambda: 100.0)

    response = client.get("/campaigns/linden-pass/combat/live-state", headers=_async_headers())
    assert response.status_code == 200

    summary = _live_snapshot_sync_summary(response)
    assert summary["snapshot_sync_status"] == "synced"
    assert summary["snapshot_sync_ran"] is True
    assert summary["snapshot_sync_ms"] > 0.0
    assert summary["snapshot_sync_lock_wait_ms"] > 0.0

