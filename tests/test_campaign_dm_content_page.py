from __future__ import annotations

from io import BytesIO
import sqlite3

from player_wiki.app import create_app
from player_wiki.config import Config
from player_wiki.db import init_database
from tests.sample_data import build_test_campaigns_dir

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

TEST_UNGROUPED_STATBLOCK_MARKDOWN = b"""AT-A-GLANCE (Quick Reference)
--------------------------------------------------------------------------------
Name: Dock Runner
Creature Type: Humanoid
Role/Archetype: Scout
Challenge Rating: CR 1
Proficiency Bonus: +2
Speed: 30 ft.

STATBLOCK (5e Format)
--------------------------------------------------------------------------------
Armor Class 13 (leather armor)
Hit Points 22 (5d8)
Speed 30 ft.

STR 10 (+0)  DEX 14 (+2)  CON 10 (+0)  INT 11 (+0)  WIS 12 (+1)  CHA 10 (+0)
"""


def _list_statblocks(app):
    with app.app_context():
        return app.extensions["campaign_dm_content_service"].list_statblocks("linden-pass")


def _list_condition_definitions(app):
    with app.app_context():
        return app.extensions["campaign_dm_content_service"].list_condition_definitions("linden-pass")


def _list_session_articles(app):
    with app.app_context():
        return app.extensions["campaign_session_service"].list_articles("linden-pass")


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
    staged_articles_page = client.get("/campaigns/linden-pass/dm-content/staged-articles")
    conditions_page = client.get("/campaigns/linden-pass/dm-content/conditions")

    assert campaign.status_code == 200
    campaign_html = campaign.get_data(as_text=True)
    assert "DM Content" in campaign_html
    assert 'href="/campaigns/linden-pass/dm-content"' in campaign_html

    assert dm_page.status_code == 200
    dm_html = dm_page.get_data(as_text=True)
    assert "Statblock library" in dm_html
    assert "Staged Articles" in dm_html
    assert "Conditions" in dm_html
    assert 'name="statblock_file"' in dm_html
    assert '/campaigns/linden-pass/dm-content/staged-articles' in dm_html
    assert '/campaigns/linden-pass/dm-content/conditions' in dm_html

    assert staged_articles_page.status_code == 200
    staged_html = staged_articles_page.get_data(as_text=True)
    assert "Stage session articles" in staged_html
    assert "Session reveal queue" in staged_html
    assert 'action="/campaigns/linden-pass/dm-content/staged-articles"' in staged_html

    assert conditions_page.status_code == 200
    assert "Custom conditions" in conditions_page.get_data(as_text=True)

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


def test_dm_statblocks_page_groups_subsectioned_entries_like_wiki_sections(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    grouped_upload = client.post(
        "/campaigns/linden-pass/dm-content/statblocks",
        data={
            "subsection": "Malverine Minions",
            "statblock_file": (BytesIO(TEST_STATBLOCK_MARKDOWN), "imperial-signal-operative-statblock.md"),
        },
        follow_redirects=True,
    )

    assert grouped_upload.status_code == 200
    grouped_html = grouped_upload.get_data(as_text=True)
    assert "Malverine Minions" in grouped_html
    assert "1 statblock" in grouped_html
    assert 'data-subsection-controls' in grouped_html

    ungrouped_upload = client.post(
        "/campaigns/linden-pass/dm-content/statblocks",
        data={
            "statblock_file": (BytesIO(TEST_UNGROUPED_STATBLOCK_MARKDOWN), "dock-runner-statblock.md"),
        },
        follow_redirects=True,
    )

    assert ungrouped_upload.status_code == 200

    statblocks = _list_statblocks(app)
    statblock_subsections = {statblock.title: statblock.subsection for statblock in statblocks}
    assert statblock_subsections == {
        "Dock Runner": "",
        "Imperial Signal Operative": "Malverine Minions",
    }

    dm_page = client.get("/campaigns/linden-pass/dm-content")

    assert dm_page.status_code == 200
    dm_html = dm_page.get_data(as_text=True)
    assert "Dock Runner" in dm_html
    assert "Imperial Signal Operative" in dm_html
    assert "Malverine Minions" in dm_html
    assert "1 statblock" in dm_html


def test_init_db_backfills_existing_linden_pass_statblocks_into_malverine_minions_group(
    tmp_path, monkeypatch
):
    campaigns_dir = build_test_campaigns_dir(tmp_path)
    monkeypatch.setattr(Config, "CAMPAIGNS_DIR", campaigns_dir)

    db_path = tmp_path / "legacy-player-wiki.sqlite3"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE campaign_dm_statblocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_slug TEXT NOT NULL,
            title TEXT NOT NULL,
            body_markdown TEXT NOT NULL,
            source_filename TEXT NOT NULL,
            armor_class INTEGER,
            max_hp INTEGER NOT NULL DEFAULT 0,
            speed_text TEXT NOT NULL DEFAULT '',
            movement_total INTEGER NOT NULL DEFAULT 0,
            initiative_bonus INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by_user_id INTEGER,
            updated_by_user_id INTEGER
        );

        INSERT INTO campaign_dm_statblocks (
            campaign_slug,
            title,
            body_markdown,
            source_filename,
            armor_class,
            max_hp,
            speed_text,
            movement_total,
            initiative_bonus,
            created_at,
            updated_at
        )
        VALUES
            (
                'linden-pass',
                'Eyestitched Watcher',
                'Armor Class 14\nHit Points 27\nSpeed 30 ft.',
                'Eyestitched Watcher - Powered-Up Statblock.md',
                14,
                27,
                '30 ft.',
                30,
                2,
                '2026-04-22T12:00:00Z',
                '2026-04-22T12:00:00Z'
            ),
            (
                'linden-pass',
                'Dock Runner',
                'Armor Class 13\nHit Points 22\nSpeed 30 ft.',
                'dock-runner-statblock.md',
                13,
                22,
                '30 ft.',
                30,
                2,
                '2026-04-22T12:00:00Z',
                '2026-04-22T12:00:00Z'
            );
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
        SELECT title, subsection
        FROM campaign_dm_statblocks
        ORDER BY id ASC
        """
    ).fetchall()
    connection.close()

    assert [dict(row) for row in rows] == [
        {"title": "Eyestitched Watcher", "subsection": "Malverine Minions"},
        {"title": "Dock Runner", "subsection": ""},
    ]


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


def test_dm_can_stage_session_article_from_dm_content_and_manage_it_from_session_dm(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_article = client.post(
        "/campaigns/linden-pass/dm-content/staged-articles",
        data={
            "article_mode": "manual",
            "title": "Harbormaster Letter",
            "body_markdown": "The seal is fresh and the paper smells faintly of brine.",
        },
        follow_redirects=True,
    )

    assert create_article.status_code == 200
    create_html = create_article.get_data(as_text=True)
    assert "Staged article added to the session reveal queue." in create_html
    assert "Harbormaster Letter" in create_html
    assert "Open Session DM" in create_html

    articles = _list_session_articles(app)
    assert len(articles) == 1
    assert articles[0].title == "Harbormaster Letter"
    assert not articles[0].is_revealed

    update_article = client.post(
        f"/campaigns/linden-pass/dm-content/staged-articles/{articles[0].id}",
        data={
            "title": "Harbormaster Letter Revised",
            "body_markdown": "The seal is fresh, and the revised copy names the east pier.",
        },
        follow_redirects=True,
    )

    assert update_article.status_code == 200
    update_html = update_article.get_data(as_text=True)
    assert "Staged article updated." in update_html
    assert "Harbormaster Letter Revised" in update_html
    assert "revised copy names the east pier" in update_html
    assert "The seal is fresh and the paper smells faintly of brine." not in update_html

    articles = _list_session_articles(app)
    assert len(articles) == 1
    assert articles[0].title == "Harbormaster Letter Revised"
    assert articles[0].body_markdown == "The seal is fresh, and the revised copy names the east pier."

    session_dm_page = client.get("/campaigns/linden-pass/session/dm")
    session_dm_html = session_dm_page.get_data(as_text=True)
    assert session_dm_page.status_code == 200
    assert "Harbormaster Letter Revised" in session_dm_html
    assert "revised copy names the east pier" in session_dm_html
    assert "Begin a session before revealing this article." in session_dm_html

    delete_article = client.post(
        f"/campaigns/linden-pass/dm-content/staged-articles/{articles[0].id}/delete",
        follow_redirects=True,
    )

    assert delete_article.status_code == 200
    delete_html = delete_article.get_data(as_text=True)
    assert "Staged article deleted from the session reveal queue." in delete_html
    assert _list_session_articles(app) == []
