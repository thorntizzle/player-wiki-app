from __future__ import annotations

from io import BytesIO


TEST_STATBLOCK_MARKDOWN = b"""AT-A-GLANCE (Quick Reference)
--------------------------------------------------------------------------------
Name: Imperial Signal Operative
Creature Type: Humanoid (aven)
Role/Archetype: Support Caster
Challenge Rating: CR 3
Proficiency Bonus: +2
Speed: 30 ft., fly 40 ft.

STATBLOCK (5e Format)
--------------------------------------------------------------------------------
Armor Class 15 (studded leather)
Hit Points 55 (10d8 + 10)
Speed 30 ft., fly 40 ft.

STR 10 (+0)  DEX 14 (+2)  CON 12 (+1)  INT 16 (+3)  WIS 14 (+2)  CHA 11 (+0)
"""


def _list_statblocks(app):
    with app.app_context():
        return app.extensions["campaign_dm_content_service"].list_statblocks("linden-pass")


def _list_condition_definitions(app):
    with app.app_context():
        return app.extensions["campaign_dm_content_service"].list_condition_definitions("linden-pass")


def _list_combatants(app):
    with app.app_context():
        return app.extensions["campaign_combat_service"].list_combatants("linden-pass")


def _find_combatant(app, *, name: str):
    for combatant in _list_combatants(app):
        if combatant.display_name == name:
            return combatant
    return None


def test_dm_can_open_dm_content_page_and_players_cannot_by_default(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    campaign = client.get("/campaigns/linden-pass")
    dm_page = client.get("/campaigns/linden-pass/dm-content")

    assert campaign.status_code == 200
    campaign_html = campaign.get_data(as_text=True)
    assert "DM Content" in campaign_html
    assert 'href="/campaigns/linden-pass/dm-content"' in campaign_html

    assert dm_page.status_code == 200
    dm_html = dm_page.get_data(as_text=True)
    assert "Statblock library" in dm_html
    assert "Custom conditions" in dm_html
    assert 'name="statblock_file"' in dm_html

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])

    player_campaign = client.get("/campaigns/linden-pass")
    player_page = client.get("/campaigns/linden-pass/dm-content")

    assert 'href="/campaigns/linden-pass/dm-content"' not in player_campaign.get_data(as_text=True)
    assert player_page.status_code == 404


def test_dm_can_upload_statblock_and_use_it_to_seed_an_npc_combatant(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    upload = client.post(
        "/campaigns/linden-pass/dm-content/statblocks",
        data={"statblock_file": (BytesIO(TEST_STATBLOCK_MARKDOWN), "imperial-signal-operative-statblock.md")},
        follow_redirects=True,
    )

    assert upload.status_code == 200
    upload_html = upload.get_data(as_text=True)
    assert "Statblock saved to DM Content." in upload_html
    assert "Imperial Signal Operative" in upload_html
    statblocks = _list_statblocks(app)
    assert len(statblocks) == 1
    assert statblocks[0].title == "Imperial Signal Operative"
    assert statblocks[0].max_hp == 55
    assert statblocks[0].movement_total == 40
    assert statblocks[0].initiative_bonus == 2

    combat_page = client.get("/campaigns/linden-pass/combat/dm")
    combat_html = combat_page.get_data(as_text=True)
    assert combat_page.status_code == 200
    assert "Add NPC from DM Content" in combat_html
    assert "Imperial Signal Operative" in combat_html

    add_to_combat = client.post(
        "/campaigns/linden-pass/combat/statblock-combatants",
        data={"statblock_id": str(statblocks[0].id)},
        follow_redirects=False,
    )
    assert add_to_combat.status_code == 302

    combatant = _find_combatant(app, name="Imperial Signal Operative")
    assert combatant is not None
    assert combatant.max_hp == 55
    assert combatant.current_hp == 55
    assert combatant.movement_total == 40
    assert combatant.initiative_bonus == 2
    assert combatant.turn_value == 2


def test_custom_conditions_flow_from_dm_content_into_combat_picker_and_can_be_deleted(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_condition = client.post(
        "/campaigns/linden-pass/dm-content/conditions",
        data={
            "name": "Marked for Judgment",
            "description_markdown": "The target has disadvantage on Deception checks against inquisitors.",
        },
        follow_redirects=True,
    )

    assert create_condition.status_code == 200
    create_html = create_condition.get_data(as_text=True)
    assert "Custom condition saved to DM Content." in create_html
    assert "Marked for Judgment" in create_html

    definitions = _list_condition_definitions(app)
    assert len(definitions) == 1
    assert definitions[0].name == "Marked for Judgment"

    combat_page = client.get("/campaigns/linden-pass/combat")
    combat_html = combat_page.get_data(as_text=True)
    assert '<option value="Marked for Judgment"></option>' in combat_html

    delete_condition = client.post(
        f"/campaigns/linden-pass/dm-content/conditions/{definitions[0].id}/delete",
        follow_redirects=True,
    )

    assert delete_condition.status_code == 200
    assert "Deleted custom condition Marked for Judgment." in delete_condition.get_data(as_text=True)
    assert _list_condition_definitions(app) == []

    refreshed_combat = client.get("/campaigns/linden-pass/combat")
    assert '<option value="Marked for Judgment"></option>' not in refreshed_combat.get_data(as_text=True)
