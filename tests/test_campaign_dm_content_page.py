from __future__ import annotations

from tests.helpers.systems_import_helpers import (
    _build_malformed_utf8_systems_import_archive,
    _build_systems_import_archive,
)
from io import BytesIO
import sqlite3
from uuid import uuid4

import pytest
import yaml

from player_wiki.app import create_app
from player_wiki.campaign_visibility import VISIBILITY_DM, VISIBILITY_PLAYERS
from player_wiki.config import Config
from player_wiki.db import init_database
from player_wiki.auth_store import AuthStore
from player_wiki.system_policy import XIANXIA_SYSTEM_CODE
from player_wiki.systems_ingest import SystemsArchiveLimits
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

UPDATED_STATBLOCK_MARKDOWN = """# Imperial Signal Lieutenant

Armor Class 16 (studded leather, shield)
Hit Points 64 (12d8 + 12)
Speed 30 ft., fly 45 ft.

STR 10 (+0)  DEX 16 (+3)  CON 12 (+1)  INT 16 (+3)  WIS 14 (+2)  CHA 11 (+0)
"""

TEST_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xd9\x8f\x9b"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


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


def _list_conditions(app, combatant_id: int):
    with app.app_context():
        return app.extensions["campaign_combat_service"].list_conditions_by_combatant(
            "linden-pass"
        ).get(combatant_id, [])


def _build_systems_source_form(app) -> dict[str, str]:
    with app.app_context():
        rows = app.extensions["systems_service"].list_campaign_source_states("linden-pass")

    data: dict[str, str] = {}
    for row in rows:
        if row.is_enabled:
            data[f"source_{row.source.source_id}_enabled"] = "1"
        data[f"source_{row.source.source_id}_visibility"] = row.default_visibility
    return data


def _find_combatant(app, *, name: str):
    for combatant in _list_combatants(app):
        if combatant.display_name == name:
            return combatant
    return None


def test_dm_can_open_dm_content_page_and_players_cannot_by_default(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    campaign = client.get("/campaigns/linden-pass")
    dm_page = client.get("/campaigns/linden-pass/dm-content")
    systems_page = client.get("/campaigns/linden-pass/dm-content/systems")
    staged_articles_page = client.get("/campaigns/linden-pass/dm-content/staged-articles")
    conditions_page = client.get("/campaigns/linden-pass/dm-content/conditions")

    assert campaign.status_code == 200
    campaign_html = campaign.get_data(as_text=True)
    assert "DM Content" in campaign_html
    assert 'href="/campaigns/linden-pass/dm-content"' in campaign_html

    assert dm_page.status_code == 200
    dm_html = dm_page.get_data(as_text=True)
    assert "Statblock library" in dm_html
    assert "Systems" in dm_html
    assert "Staged Articles" in dm_html
    assert "Conditions" in dm_html
    assert 'name="statblock_file"' in dm_html
    assert '/campaigns/linden-pass/dm-content/systems' in dm_html
    assert '/campaigns/linden-pass/dm-content/staged-articles' in dm_html
    assert '/campaigns/linden-pass/dm-content/conditions' in dm_html

    assert systems_page.status_code == 200
    systems_html = systems_page.get_data(as_text=True)
    assert "Source Enablement" in systems_html
    assert "Entry Overrides" in systems_html
    assert "Custom Entries" in systems_html
    assert "Import-Run History" in systems_html

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


def test_dm_content_systems_page_separates_systems_lanes_and_returns_after_source_update(
    app, client, sign_in, users
):
    source_id = f"CSTM-{uuid4().hex[:8].upper()}"
    entry_key = f"dnd-5e|spell|{source_id.lower()}|harbor-spark"

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        store.upsert_source(
            library_slug,
            source_id,
            title="Harbor Custom Systems",
            license_class="custom_campaign",
        )
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug=library_slug,
            source_id=source_id,
            is_enabled=True,
            default_visibility="dm",
        )
        store.replace_entries_for_source(
            library_slug,
            source_id,
            entries=[
                {
                    "entry_key": entry_key,
                    "entry_type": "spell",
                    "slug": "harbor-spark",
                    "title": "Harbor Spark",
                    "search_text": "harbor spark",
                    "player_safe_default": True,
                    "metadata": {},
                    "body": {},
                }
            ],
            entry_types=["spell"],
        )
        store.upsert_campaign_entry_override(
            "linden-pass",
            library_slug=library_slug,
            entry_key=entry_key,
            visibility_override="dm",
            is_enabled_override=False,
        )
        import_run = store.create_import_run(
            library_slug=library_slug,
            source_id="MM",
            import_version="browser-review",
            source_path=r"C:\private\source\mm.zip",
            summary={},
        )
        store.complete_import_run(
            import_run.id,
            summary={
                "imported_count": 42,
                "imported_by_type": {"monster": 42},
                "source_files": ["data/bestiary/bestiary-mm.json"],
            },
        )

    sign_in(users["dm"]["email"], users["dm"]["password"])
    page = client.get("/campaigns/linden-pass/dm-content/systems")

    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "Source Enablement" in body
    assert "Entry Overrides" in body
    assert "Custom Entries" in body
    assert "Import-Run History" in body
    assert "Harbor Custom Systems" in body
    assert "Harbor Spark" in body
    assert "MM import #" in body
    assert "42 entries" in body
    assert r"C:\private\source\mm.zip" not in body
    assert 'name="return_to" value="dm-content-systems"' in body

    form_data = _build_systems_source_form(app)
    form_data["return_to"] = "dm-content-systems"
    form_data[f"source_{source_id}_visibility"] = "players"
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/sources",
        data=form_data,
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/campaigns/linden-pass/dm-content/systems" in response.headers["Location"]
    assert "#systems-source-enablement" in response.headers["Location"]

    with app.app_context():
        state = app.extensions["systems_service"].get_campaign_source_state("linden-pass", source_id)
        assert state is not None
        assert state.default_visibility == "players"


def test_admin_can_import_dnd5e_systems_source_from_dm_content_systems(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    dm_page = client.get("/campaigns/linden-pass/dm-content/systems")
    dm_body = dm_page.get_data(as_text=True)
    assert dm_page.status_code == 200
    assert "Shared Source Imports" in dm_body
    assert "Shared-source ZIP imports are limited to app admins" in dm_body
    assert 'name="systems_import_archive"' not in dm_body

    blocked_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/imports/dnd5e",
        data={"source_ids": ["MM"]},
        follow_redirects=False,
    )
    assert blocked_response.status_code == 403

    sign_in(users["admin"]["email"], users["admin"]["password"])
    admin_page = client.get("/campaigns/linden-pass/dm-content/systems")
    admin_body = admin_page.get_data(as_text=True)
    assert admin_page.status_code == 200
    assert 'name="systems_import_archive"' in admin_body
    assert 'action="/campaigns/linden-pass/systems/control-panel/imports/dnd5e"' in admin_body
    assert "Import selected sources" in admin_body

    archive_bytes = _build_systems_import_archive()
    app.config["SYSTEMS_ARCHIVE_LIMITS"] = SystemsArchiveLimits(
        max_raw_bytes=len(archive_bytes)
    )
    import_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/imports/dnd5e",
        data={
            "return_to": "dm-content-systems",
            "source_ids": ["MM"],
            "entry_types": ["monster"],
            "import_version": "browser-mm-import",
            "systems_import_archive": (BytesIO(archive_bytes), "browser-mm-import.zip"),
        },
        follow_redirects=False,
    )

    assert import_response.status_code == 302
    assert "/campaigns/linden-pass/dm-content/systems" in import_response.headers["Location"]
    assert "#systems-import-history" in import_response.headers["Location"]

    with app.app_context():
        store = app.extensions["systems_store"]
        entries = store.list_entries_for_source("DND-5E", "MM", entry_type="monster", limit=None)
        assert any(entry.title == "Goblin" for entry in entries)
        import_run = store.list_import_runs(library_slug="DND-5E", source_id="MM", limit=1)[0]
        assert import_run.status == "completed"
        assert import_run.import_version == "browser-mm-import"
        assert import_run.source_path == "browser-upload:browser-mm-import.zip"
        assert import_run.started_by_user_id == users["admin"]["id"]
        assert import_run.summary["imported_count"] == 1
        assert import_run.summary["imported_by_type"] == {"monster": 1}
        assert import_run.summary["source_files"] == ["data/bestiary/bestiary-mm.json"]
        events = AuthStore().list_recent_audit_events(
            event_type="systems_dnd5e_source_imported",
            campaign_slug="linden-pass",
        )
        assert any(event.metadata.get("import_run_ids") == [import_run.id] for event in events)

    review_page = client.get("/campaigns/linden-pass/dm-content/systems")
    review_body = review_page.get_data(as_text=True)
    assert review_page.status_code == 200
    assert "MM import #" in review_body
    assert "browser-mm-import" in review_body
    assert "1 entries" in review_body
    assert "Monsters: 1" in review_body
    assert "data/bestiary/bestiary-mm.json" in review_body
    assert "browser-upload:browser-mm-import.zip" not in review_body


def test_browser_systems_import_rejects_actual_plus_one_when_length_hint_is_missing(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    archive_bytes = _build_systems_import_archive()
    app.config["SYSTEMS_ARCHIVE_LIMITS"] = SystemsArchiveLimits(
        max_raw_bytes=len(archive_bytes)
    )
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/imports/dnd5e",
        data={
            "return_to": "dm-content-systems",
            "source_ids": ["MM"],
            "entry_types": ["monster"],
            "systems_import_archive": (
                BytesIO(archive_bytes + b"x"),
                "oversized-browser-import.zip",
            ),
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "at or under 64 MiB" in response.get_data(as_text=True)
    assert "oversized-browser-import.zip" not in response.get_data(as_text=True)
    with app.app_context():
        assert app.extensions["systems_store"].list_import_runs(library_slug="DND-5E") == []
        events = AuthStore().list_recent_audit_events(
            event_type="systems_dnd5e_source_imported",
            campaign_slug="linden-pass",
        )
        assert events == []


def test_browser_systems_import_rejects_malformed_utf8_without_leak_mutation_or_residue(
    app,
    client,
    sign_in,
    users,
    tmp_path,
    monkeypatch,
):
    sign_in(users["admin"]["email"], users["admin"]["password"])
    temp_root = tmp_path / "systems-temp"
    monkeypatch.setenv("PLAYER_WIKI_TEMP_DIR", str(temp_root))
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/imports/dnd5e",
        data={
            "return_to": "dm-content-systems",
            "source_ids": ["MM"],
            "entry_types": ["monster"],
            "systems_import_archive": (
                BytesIO(_build_malformed_utf8_systems_import_archive()),
                "ATTACKER-SENTINEL.zip",
            ),
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    response_text = response.get_data(as_text=True)
    assert "Import archive must be a valid supported ZIP file." in response_text
    assert "ATTACKER-SENTINEL" not in response_text
    assert "codec" not in response_text
    assert "position 0" not in response_text
    assert "can't decode" not in response_text
    with app.app_context():
        store = app.extensions["systems_store"]
        assert store.list_import_runs(library_slug="DND-5E") == []
        assert store.list_entries_for_source("DND-5E", "MM", entry_type="monster", limit=None) == []
        events = AuthStore().list_recent_audit_events(
            event_type="systems_dnd5e_source_imported",
            campaign_slug="linden-pass",
        )
        assert events == []
    assert not temp_root.exists() or list(temp_root.iterdir()) == []


def test_dm_content_systems_page_can_create_edit_archive_and_restore_custom_entries(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        data={
            "return_to": "dm-content-systems",
            "custom_entry_title": "Harbor Spark",
            "custom_entry_slug": "harbor-spark",
            "custom_entry_type": "spell",
            "custom_entry_visibility": "players",
            "custom_entry_provenance": "Linden Pass table notes",
            "custom_entry_search_metadata": "storm dock signal",
            "custom_entry_body_markdown": "## Effect\nLightning gathers around the harbor bells.",
        },
        follow_redirects=False,
    )

    assert create_response.status_code == 302
    assert "/campaigns/linden-pass/dm-content/systems" in create_response.headers["Location"]
    assert "#systems-custom-entry-custom-linden-pass-harbor-spark" in create_response.headers["Location"]

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        entry = service.get_custom_campaign_entry_by_slug("linden-pass", "custom-linden-pass-harbor-spark")
        assert entry is not None
        assert entry.title == "Harbor Spark"
        assert entry.entry_type == "spell"
        assert entry.source_id == "CUSTOM-LINDEN-PASS"
        assert entry.source_path == "Linden Pass table notes"
        assert "storm dock signal" in entry.search_text
        assert "<h2>Effect</h2>" in entry.rendered_html
        source_state = service.get_campaign_source_state("linden-pass", "CUSTOM-LINDEN-PASS")
        assert source_state is not None
        assert source_state.default_visibility == VISIBILITY_PLAYERS
        override = store.get_campaign_entry_override("linden-pass", entry.entry_key)
        assert override is not None
        assert override.visibility_override == "players"
        assert override.is_enabled_override is None
        assert service.is_entry_enabled_for_campaign("linden-pass", entry) is True

    detail_response = client.get("/campaigns/linden-pass/systems/entries/custom-linden-pass-harbor-spark")
    detail_body = detail_response.get_data(as_text=True)
    assert detail_response.status_code == 200
    assert "Harbor Spark" in detail_body
    assert "Lightning gathers around the harbor bells." in detail_body

    edit_response = client.get(
        "/campaigns/linden-pass/systems/control-panel/custom-entries/custom-linden-pass-harbor-spark/edit"
        "?return_to=dm-content-systems"
    )
    edit_body = edit_response.get_data(as_text=True)
    assert edit_response.status_code == 200
    assert 'value="Harbor Spark"' in edit_body
    assert 'name="return_to" value="dm-content-systems"' in edit_body

    update_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries/custom-linden-pass-harbor-spark",
        data={
            "return_to": "dm-content-systems",
            "custom_entry_title": "Harbor Spark Revised",
            "custom_entry_type": "rule",
            "custom_entry_visibility": "dm",
            "custom_entry_provenance": "Revised table notes",
            "custom_entry_search_metadata": "updated signal",
            "custom_entry_body_markdown": "Updated custom body.",
        },
        follow_redirects=False,
    )

    assert update_response.status_code == 302
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        entry = service.get_custom_campaign_entry_by_slug("linden-pass", "custom-linden-pass-harbor-spark")
        assert entry is not None
        assert entry.title == "Harbor Spark Revised"
        assert entry.entry_type == "rule"
        assert entry.source_path == "Revised table notes"
        assert "updated signal" in entry.search_text
        assert "Updated custom body." in entry.rendered_html
        override = store.get_campaign_entry_override("linden-pass", entry.entry_key)
        assert override is not None
        assert override.visibility_override == "dm"
        original_entry_id = entry.id
        original_entry_key = entry.entry_key

    archive_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries/custom-linden-pass-harbor-spark/archive",
        data={"return_to": "dm-content-systems"},
        follow_redirects=False,
    )

    assert archive_response.status_code == 302
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        entry = service.get_custom_campaign_entry_by_slug("linden-pass", "custom-linden-pass-harbor-spark")
        assert entry is not None
        assert entry.id == original_entry_id
        assert entry.entry_key == original_entry_key
        override = store.get_campaign_entry_override("linden-pass", entry.entry_key)
        assert override is not None
        assert override.visibility_override == "dm"
        assert override.is_enabled_override is False
        assert service.is_entry_enabled_for_campaign("linden-pass", entry) is False

    restore_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries/custom-linden-pass-harbor-spark/restore",
        data={"return_to": "dm-content-systems"},
        follow_redirects=False,
    )

    assert restore_response.status_code == 302
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        entry = service.get_custom_campaign_entry_by_slug("linden-pass", "custom-linden-pass-harbor-spark")
        assert entry is not None
        assert entry.id == original_entry_id
        assert entry.entry_key == original_entry_key
        override = store.get_campaign_entry_override("linden-pass", entry.entry_key)
        assert override is not None
        assert override.visibility_override == "dm"
        assert override.is_enabled_override is None
        assert service.is_entry_enabled_for_campaign("linden-pass", entry) is True


def test_custom_entry_validation_rerenders_dm_content_with_submitted_form_values(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        data={
            "return_to": "dm-content-systems",
            "custom_entry_title": "",
            "custom_entry_slug": "",
            "custom_entry_type": "spell",
            "custom_entry_visibility": VISIBILITY_DM,
            "custom_entry_provenance": "Retained table provenance",
            "custom_entry_search_metadata": "retained search terms",
            "custom_entry_body_markdown": "Retained invalid custom body.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "Choose a URL slug or title before saving a custom Systems entry." in body
    assert 'name="return_to" value="dm-content-systems"' in body
    assert '<option value="spell" selected' in body
    assert '<option value="dm" selected' in body
    assert "Retained table provenance" in body
    assert "retained search terms" in body
    assert "Retained invalid custom body." in body

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        source = store.get_source(library_slug, "CUSTOM-LINDEN-PASS")
        policy = store.get_campaign_policy("linden-pass")
        enabled_source = store.get_campaign_enabled_source(
            "linden-pass",
            "CUSTOM-LINDEN-PASS",
        )
        assert source is not None
        assert policy is not None and policy.updated_by_user_id == users["dm"]["id"]
        assert enabled_source is not None
        assert enabled_source.updated_by_user_id == users["dm"]["id"]
        assert service.get_custom_campaign_entry_by_slug(
            "linden-pass",
            "custom-linden-pass-retained-invalid-custom-body",
        ) is None
        assert not AuthStore().list_recent_audit_events(
            event_type="campaign_systems_custom_entry_created",
            campaign_slug="linden-pass",
        )


def test_xianxia_empty_custom_entry_create_rerenders_default_form_values(
    app, client, sign_in, users
):
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    payload["system"] = "xianxia"
    payload["systems_library"] = "xianxia"
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with app.app_context():
        app.extensions["repository_store"].refresh()
        app.extensions["systems_service"].ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        follow_redirects=False,
    )

    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "Choose a URL slug or title before saving a custom Systems entry." in body
    assert '<option value="rule" selected' in body
    custom_visibility_index = body.index('select name="custom_entry_visibility"')
    custom_visibility_block = body[custom_visibility_index: custom_visibility_index + 500]
    assert '<option value="dm" selected' in custom_visibility_block
    assert '<option value="players" selected' not in custom_visibility_block


def test_empty_custom_entry_update_rerenders_existing_fields_and_fixed_slug(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    create_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        data={
            "custom_entry_title": "Existing Spark",
            "custom_entry_slug": "existing-spark",
            "custom_entry_type": "spell",
            "custom_entry_visibility": VISIBILITY_DM,
            "custom_entry_provenance": "Existing provenance",
            "custom_entry_search_metadata": "existing search metadata",
            "custom_entry_body_markdown": "Existing body markdown.",
        },
    )
    assert create_response.status_code == 302

    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries/"
        "custom-linden-pass-existing-spark",
        follow_redirects=False,
    )

    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "Custom Systems entries need a title." in body
    assert 'value="Existing Spark"' in body
    assert 'value="custom-linden-pass-existing-spark" disabled' in body
    assert 'name="custom_entry_slug"' not in body
    assert '<option value="spell" selected' in body
    custom_visibility_index = body.index('select name="custom_entry_visibility"')
    custom_visibility_block = body[custom_visibility_index: custom_visibility_index + 500]
    assert '<option value="dm" selected' in custom_visibility_block
    assert "Existing provenance" in body
    assert "existing search metadata" in body
    assert "Existing body markdown." in body

    with app.app_context():
        entry = app.extensions["systems_service"].get_custom_campaign_entry_by_slug(
            "linden-pass",
            "custom-linden-pass-existing-spark",
        )
        assert entry is not None
        assert entry.title == "Existing Spark"
        assert entry.entry_type == "spell"


@pytest.mark.parametrize("visibility_field", [{}, {"custom_entry_visibility": "outsiders"}])
def test_custom_entry_direct_missing_or_invalid_visibility_falls_back_to_players(
    app, client, sign_in, users, visibility_field
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    slug_leaf = f"visibility-{uuid4().hex[:8]}"
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        data={
            "custom_entry_title": "Visibility Fallback",
            "custom_entry_slug": slug_leaf,
            "custom_entry_type": "rule",
            "custom_entry_body_markdown": "Visibility fallback body.",
            **visibility_field,
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        entry = service.get_custom_campaign_entry_by_slug(
            "linden-pass",
            f"custom-linden-pass-{slug_leaf}",
        )
        assert entry is not None
        override = store.get_campaign_entry_override("linden-pass", entry.entry_key)
        assert override is not None
        assert override.visibility_override == VISIBILITY_PLAYERS


@pytest.mark.parametrize("entry_type_field", [{}, {"custom_entry_type": "!!!"}])
def test_custom_entry_direct_missing_or_invalid_entry_type_rerenders_400(
    app, client, sign_in, users, entry_type_field
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    slug_leaf = f"invalid-type-{uuid4().hex[:8]}"
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        data={
            "custom_entry_title": "Invalid Type",
            "custom_entry_slug": slug_leaf,
            "custom_entry_visibility": VISIBILITY_PLAYERS,
            "custom_entry_body_markdown": "Invalid type body.",
            **entry_type_field,
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Choose an entry type before saving this custom Systems entry." in response.get_data(
        as_text=True
    )
    with app.app_context():
        assert app.extensions["systems_service"].get_custom_campaign_entry_by_slug(
            "linden-pass",
            f"custom-linden-pass-{slug_leaf}",
        ) is None


def test_custom_entry_markdown_is_sanitized_once_at_the_service_boundary(
    app, client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        data={
            "custom_entry_title": "Sanitized Spark",
            "custom_entry_slug": "sanitized-spark",
            "custom_entry_type": "rule",
            "custom_entry_visibility": VISIBILITY_PLAYERS,
            "custom_entry_body_markdown": (
                "## Safe heading\n\n"
                "<script>alert(1)</script>\n\n"
                "Inline `<b>literal</b>`.\n\n"
                "[unsafe](javascript:alert(2))"
            ),
        },
    )

    assert response.status_code == 302
    with app.app_context():
        entry = app.extensions["systems_service"].get_custom_campaign_entry_by_slug(
            "linden-pass",
            "custom-linden-pass-sanitized-spark",
        )
        assert entry is not None
        stored_markdown = entry.body["markdown"]
        assert stored_markdown == entry.metadata["body_markdown"]
        assert "## Safe heading" in stored_markdown
        assert "`<b>literal</b>`" in stored_markdown
        assert "<script" not in stored_markdown.casefold()
        assert "<h2>Safe heading</h2>" in entry.rendered_html
        assert "&lt;b&gt;literal&lt;/b&gt;" in entry.rendered_html
        assert "<script" not in entry.rendered_html.casefold()
        assert "javascript:" not in entry.rendered_html.casefold()


def test_custom_entry_control_panel_surface_preserves_edit_and_prg_anchors(
    client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    create_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        data={
            "custom_entry_title": "Control Spark",
            "custom_entry_slug": "control-spark",
            "custom_entry_type": "rule",
            "custom_entry_visibility": VISIBILITY_PLAYERS,
            "custom_entry_body_markdown": "Control surface body.",
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    assert create_response.headers["Location"].endswith(
        "/campaigns/linden-pass/systems/control-panel"
        "#systems-custom-entry-custom-linden-pass-control-spark"
    )

    edit_response = client.get(
        "/campaigns/linden-pass/systems/control-panel/custom-entries/"
        "custom-linden-pass-control-spark/edit"
    )
    assert edit_response.status_code == 200
    edit_body = edit_response.get_data(as_text=True)
    assert "Systems Settings" in edit_body
    assert 'value="Control Spark"' in edit_body
    assert 'name="return_to" value="dm-content-systems"' not in edit_body

    update_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries/"
        "custom-linden-pass-control-spark",
        data={
            "custom_entry_title": "Control Spark Updated",
            "custom_entry_type": "rule",
            "custom_entry_visibility": VISIBILITY_PLAYERS,
            "custom_entry_body_markdown": "Updated control surface body.",
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 302
    assert update_response.headers["Location"].endswith(
        "/campaigns/linden-pass/systems/control-panel"
        "#systems-custom-entry-custom-linden-pass-control-spark"
    )


def test_missing_custom_entry_edit_update_archive_and_restore_keep_legacy_failures(
    client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    base_path = "/campaigns/linden-pass/systems/control-panel/custom-entries/missing-entry"
    assert client.get(f"{base_path}/edit").status_code == 404
    assert client.post(base_path).status_code == 404
    for action in ("archive", "restore"):
        response = client.post(
            f"{base_path}/{action}",
            data={"return_to": "dm-content-systems"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/campaigns/linden-pass/dm-content/systems" in response.headers["Location"]
        assert "#systems-custom-entries" in response.headers["Location"]


@pytest.mark.parametrize("operation", ["create", "update", "archive", "restore"])
def test_custom_entry_mutation_remains_durable_when_post_commit_audit_fails(
    app, client, sign_in, users, monkeypatch, operation
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    entry_slug = "custom-linden-pass-fault-seed"
    base_form = {
        "return_to": "dm-content-systems",
        "custom_entry_title": "Fault Seed",
        "custom_entry_slug": "fault-seed",
        "custom_entry_type": "rule",
        "custom_entry_visibility": VISIBILITY_PLAYERS,
        "custom_entry_provenance": "Fault characterization",
        "custom_entry_search_metadata": "fault seed",
        "custom_entry_body_markdown": "Fault seed body.",
    }

    if operation != "create":
        seed_response = client.post(
            "/campaigns/linden-pass/systems/control-panel/custom-entries",
            data=base_form,
        )
        assert seed_response.status_code == 302
    if operation == "restore":
        archive_response = client.post(
            f"/campaigns/linden-pass/systems/control-panel/custom-entries/{entry_slug}/archive",
        )
        assert archive_response.status_code == 302

    def fail_audit(**_kwargs):
        raise RuntimeError("custom entry audit unavailable")

    monkeypatch.setattr(app.extensions["auth_store"], "write_audit_event", fail_audit)
    if operation == "create":
        path = "/campaigns/linden-pass/systems/control-panel/custom-entries"
        data = base_form
    elif operation == "update":
        path = f"/campaigns/linden-pass/systems/control-panel/custom-entries/{entry_slug}"
        data = {
            **base_form,
            "custom_entry_title": "Fault Seed Updated",
            "custom_entry_body_markdown": "Updated before audit failure.",
        }
    else:
        path = (
            f"/campaigns/linden-pass/systems/control-panel/custom-entries/{entry_slug}/"
            f"{operation}"
        )
        data = {"return_to": "dm-content-systems"}

    with pytest.raises(RuntimeError, match="custom entry audit unavailable"):
        client.post(path, data=data)

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        entry = service.get_custom_campaign_entry_by_slug("linden-pass", entry_slug)
        assert entry is not None
        override = store.get_campaign_entry_override("linden-pass", entry.entry_key)
        assert override is not None
        if operation == "update":
            assert entry.title == "Fault Seed Updated"
            assert "Updated before audit failure." in entry.rendered_html
        elif operation == "archive":
            assert override.is_enabled_override is False
        elif operation == "restore":
            assert override.is_enabled_override is None


def test_xianxia_dm_content_systems_page_can_create_custom_martial_art_entries(
    app, client, sign_in, users
):
    campaign_path = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "campaign.yaml"
    payload = yaml.safe_load(campaign_path.read_text(encoding="utf-8")) or {}
    payload["system"] = "xianxia"
    payload["systems_library"] = "xianxia"
    campaign_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with app.app_context():
        app.extensions["repository_store"].refresh()
        app.extensions["systems_service"].ensure_builtin_library_seeded(XIANXIA_SYSTEM_CODE)

    sign_in(users["dm"]["email"], users["dm"]["password"])
    management_page = client.get("/campaigns/linden-pass/dm-content/systems")
    management_body = management_page.get_data(as_text=True)

    assert management_page.status_code == 200
    assert '<option value="martial_art"' in management_body
    assert "Martial Arts" in management_body
    custom_visibility_index = management_body.index('select name="custom_entry_visibility"')
    custom_visibility_block = management_body[custom_visibility_index: custom_visibility_index + 500]
    assert '<option value="dm" selected' in custom_visibility_block
    assert '<option value="players" selected' not in custom_visibility_block

    create_response = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        data={
            "return_to": "dm-content-systems",
            "custom_entry_title": "Jade Meteor Palm",
            "custom_entry_slug": "jade-meteor-palm",
            "custom_entry_type": "martial_art",
            "custom_entry_visibility": VISIBILITY_DM,
            "custom_entry_provenance": "GM table custom art",
            "custom_entry_search_metadata": "starter option jade meteor",
            "custom_entry_body_markdown": (
                "## Ranks\n"
                "Initiate: Jade energy gathers in the palm.\n\n"
                "Novice: The strike falls like a meteor."
            ),
        },
        follow_redirects=False,
    )

    assert create_response.status_code == 302
    assert "/campaigns/linden-pass/dm-content/systems" in create_response.headers["Location"]
    assert "#systems-custom-entry-custom-linden-pass-jade-meteor-palm" in create_response.headers["Location"]

    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        entry = service.get_custom_campaign_entry_by_slug(
            "linden-pass",
            "custom-linden-pass-jade-meteor-palm",
        )
        assert entry is not None
        assert entry.entry_type == "martial_art"
        assert entry.source_id == "CUSTOM-LINDEN-PASS"
        assert entry.metadata["xianxia_entry_facets"] == ["martial_art"]
        assert entry.metadata["xianxia_entry_facet_labels"] == ["Martial Art"]
        assert entry.metadata["catalog_role"] == "parent"
        assert entry.metadata["xianxia_custom_martial_art"] is True
        assert entry.metadata["rank_records_status"] == "gm_authored_custom_markdown"
        assert entry.body["xianxia_martial_art"]["catalog_role"] == "parent"
        assert entry.body["xianxia_martial_art"]["rank_records"] == []
        assert entry.body["xianxia_martial_art"]["parent_note"].startswith(
            "GM-created custom Martial Art"
        )
        source_state = service.get_campaign_source_state("linden-pass", "CUSTOM-LINDEN-PASS")
        assert source_state is not None
        assert source_state.default_visibility == VISIBILITY_DM
        override = store.get_campaign_entry_override("linden-pass", entry.entry_key)
        assert override is not None
        assert override.visibility_override == VISIBILITY_DM
        assert override.is_enabled_override is None
        assert service.is_entry_enabled_for_campaign("linden-pass", entry) is True

    category_response = client.get(
        "/campaigns/linden-pass/systems/sources/CUSTOM-LINDEN-PASS/types/martial_art"
    )
    category_body = category_response.get_data(as_text=True)
    assert category_response.status_code == 200
    assert "Echoes of the Alloy Coast Custom Systems: Martial Arts" in category_body
    assert "Jade Meteor Palm" in category_body
    assert "Showing all 1 martial arts in this source." in category_body

    search_response = client.get("/campaigns/linden-pass/systems?q=meteor")
    search_body = search_response.get_data(as_text=True)
    assert search_response.status_code == 200
    assert "Jade Meteor Palm" in search_body
    assert "CUSTOM-LINDEN-PASS" in search_body

    detail_response = client.get(
        "/campaigns/linden-pass/systems/entries/custom-linden-pass-jade-meteor-palm"
    )
    detail_body = detail_response.get_data(as_text=True)
    assert detail_response.status_code == 200
    assert "Jade Meteor Palm" in detail_body
    assert "Campaign-owned custom entry." in detail_body
    assert "Jade energy gathers in the palm." in detail_body


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

    combat_page = client.get("/campaigns/linden-pass/combat/dm?view=controls")
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
    assert combatant.dexterity_modifier == 2
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


def test_dm_can_update_statblock_source_and_combat_parser_fields(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    upload = client.post(
        "/campaigns/linden-pass/dm-content/statblocks",
        data={"statblock_file": (BytesIO(TEST_STATBLOCK_MARKDOWN), "imperial-signal-operative-statblock.md")},
        follow_redirects=True,
    )
    assert upload.status_code == 200

    statblock = _list_statblocks(app)[0]
    update = client.post(
        f"/campaigns/linden-pass/dm-content/statblocks/{statblock.id}",
        data={
            "subsection": "Signal Officers",
            "body_markdown": UPDATED_STATBLOCK_MARKDOWN,
        },
        follow_redirects=True,
    )

    assert update.status_code == 200
    update_html = update.get_data(as_text=True)
    assert "Statblock Imperial Signal Lieutenant updated." in update_html
    assert "Parsed combat fields: AC 16, HP 64, Speed 30 ft., fly 45 ft. (45 ft. movement), Init +3." in update_html
    assert "Signal Officers" in update_html
    assert 'name="body_markdown"' in update_html
    assert "Hit Points 64" in update_html

    statblocks = _list_statblocks(app)
    assert len(statblocks) == 1
    updated_statblock = statblocks[0]
    assert updated_statblock.title == "Imperial Signal Lieutenant"
    assert updated_statblock.subsection == "Signal Officers"
    assert updated_statblock.max_hp == 64
    assert updated_statblock.movement_total == 45
    assert updated_statblock.initiative_bonus == 3

    add_to_combat = client.post(
        "/campaigns/linden-pass/combat/statblock-combatants",
        data={"statblock_id": str(updated_statblock.id)},
        follow_redirects=False,
    )
    assert add_to_combat.status_code == 302

    combatant = _find_combatant(app, name="Imperial Signal Lieutenant")
    assert combatant is not None
    assert combatant.max_hp == 64
    assert combatant.current_hp == 64
    assert combatant.movement_total == 45
    assert combatant.initiative_bonus == 3
    assert combatant.dexterity_modifier == 3
    assert combatant.turn_value == 3


def test_dm_statblock_update_keeps_submitted_body_visible_after_parser_error(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    upload = client.post(
        "/campaigns/linden-pass/dm-content/statblocks",
        data={"statblock_file": (BytesIO(TEST_STATBLOCK_MARKDOWN), "imperial-signal-operative-statblock.md")},
        follow_redirects=True,
    )
    assert upload.status_code == 200

    statblock = _list_statblocks(app)[0]
    update = client.post(
        f"/campaigns/linden-pass/dm-content/statblocks/{statblock.id}",
        data={
            "subsection": "Broken Drafts",
            "body_markdown": "# Broken Draft\n\nArmor Class 12\nSpeed 30 ft.\n",
        },
        follow_redirects=False,
    )

    assert update.status_code == 400
    update_html = update.get_data(as_text=True)
    assert "The uploaded statblock needs a Hit Points value." in update_html
    assert "Broken Drafts" in update_html
    assert "Broken Draft" in update_html

    unchanged = _list_statblocks(app)[0]
    assert unchanged.title == "Imperial Signal Operative"
    assert unchanged.max_hp == 55


def test_dm_statblock_update_remains_durable_when_post_commit_audit_fails(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/dm-content/statblocks",
        data={"statblock_file": (BytesIO(TEST_STATBLOCK_MARKDOWN), "operative.md")},
    )
    statblock = _list_statblocks(app)[0]

    def fail_audit(**_kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(app.extensions["auth_store"], "write_audit_event", fail_audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        client.post(
            f"/campaigns/linden-pass/dm-content/statblocks/{statblock.id}",
            data={"subsection": "Signal Officers", "body_markdown": UPDATED_STATBLOCK_MARKDOWN},
        )

    updated = _list_statblocks(app)[0]
    assert updated.title == "Imperial Signal Lieutenant"
    assert updated.subsection == "Signal Officers"
    assert updated.max_hp == 64


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

    client.post(
        "/campaigns/linden-pass/combat/npc-combatants",
        data={
            "display_name": "Tide Witness",
            "turn_value": 10,
            "current_hp": 20,
            "max_hp": 20,
            "movement_total": 30,
        },
        follow_redirects=False,
    )
    combatant = _find_combatant(app, name="Tide Witness")
    assert combatant is not None
    client.post(
        f"/campaigns/linden-pass/combat/combatants/{combatant.id}/conditions",
        data={"condition_name": "Marked for Judgment", "duration_text": "Until next dawn"},
        follow_redirects=False,
    )
    active_condition = _list_conditions(app, combatant.id)[0]
    with app.app_context():
        revision_after_active_condition = app.extensions[
            "campaign_combat_service"
        ].get_live_revision("linden-pass")

    update_condition = client.post(
        f"/campaigns/linden-pass/dm-content/conditions/{definitions[0].id}",
        data={
            "name": "Judged by the Tide",
            "description_markdown": "The target leaves glowing footprints until the next dawn.",
        },
        follow_redirects=True,
    )

    assert update_condition.status_code == 200
    update_html = update_condition.get_data(as_text=True)
    assert "Custom condition Judged by the Tide updated." in update_html
    assert "Judged by the Tide" in update_html
    assert "leaves glowing footprints" in update_html
    assert 'action="/campaigns/linden-pass/dm-content/conditions/' in update_html

    definitions = _list_condition_definitions(app)
    assert len(definitions) == 1
    assert definitions[0].name == "Judged by the Tide"
    assert definitions[0].description_markdown == "The target leaves glowing footprints until the next dawn."

    retained_after_rename = _list_conditions(app, combatant.id)
    assert len(retained_after_rename) == 1
    assert retained_after_rename[0].id == active_condition.id
    assert retained_after_rename[0].name == "Marked for Judgment"
    assert retained_after_rename[0].duration_text == "Until next dawn"
    with app.app_context():
        assert (
            app.extensions["campaign_combat_service"].get_live_revision("linden-pass")
            == revision_after_active_condition
        )

    combat_page = client.get("/campaigns/linden-pass/combat/dm")
    combat_html = combat_page.get_data(as_text=True)
    assert '<option value="Judged by the Tide"></option>' in combat_html
    assert '<option value="Marked for Judgment"></option>' not in combat_html

    delete_condition = client.post(
        f"/campaigns/linden-pass/dm-content/conditions/{definitions[0].id}/delete",
        follow_redirects=True,
    )

    assert delete_condition.status_code == 200
    assert "Deleted custom condition Judged by the Tide." in delete_condition.get_data(as_text=True)
    assert _list_condition_definitions(app) == []

    retained_after_delete = _list_conditions(app, combatant.id)
    assert len(retained_after_delete) == 1
    assert retained_after_delete[0].id == active_condition.id
    assert retained_after_delete[0].name == "Marked for Judgment"
    assert retained_after_delete[0].duration_text == "Until next dawn"
    with app.app_context():
        assert (
            app.extensions["campaign_combat_service"].get_live_revision("linden-pass")
            == revision_after_active_condition
        )

    refreshed_combat = client.get(
        f"/campaigns/linden-pass/combat/dm?combatant={combatant.id}"
    )
    refreshed_combat_html = refreshed_combat.get_data(as_text=True)
    assert '<option value="Judged by the Tide"></option>' not in refreshed_combat_html
    assert '<option value="Marked for Judgment"></option>' not in refreshed_combat_html
    assert "Marked for Judgment" in refreshed_combat_html
    assert "Until next dawn" in refreshed_combat_html


def test_condition_update_remains_durable_when_post_commit_audit_fails(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/dm-content/conditions",
        data={"name": "Marked", "description_markdown": "Initial description."},
    )
    definition = _list_condition_definitions(app)[0]

    def fail_audit(**_kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(app.extensions["auth_store"], "write_audit_event", fail_audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        client.post(
            f"/campaigns/linden-pass/dm-content/conditions/{definition.id}",
            data={"name": "Renamed", "description_markdown": "Updated description."},
        )

    updated = _list_condition_definitions(app)[0]
    assert updated.name == "Renamed"
    assert updated.description_markdown == "Updated description."


def test_dm_content_create_and_delete_skip_audit_refresh_and_combat_revision(
    app, client, sign_in, users, monkeypatch
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    with app.app_context():
        original_revision = app.extensions["campaign_combat_service"].get_live_revision(
            "linden-pass"
        )

    audit_calls = []
    monkeypatch.setattr(
        app.extensions["auth_store"],
        "write_audit_event",
        lambda **kwargs: audit_calls.append(kwargs),
    )

    def fail_refresh():
        raise AssertionError("DM Content SQLite mutations must not refresh the wiki repository")

    monkeypatch.setattr(app.extensions["repository_store"], "refresh", fail_refresh)

    statblock_create = client.post(
        "/campaigns/linden-pass/dm-content/statblocks",
        data={"statblock_file": (BytesIO(TEST_STATBLOCK_MARKDOWN), "operative.md")},
        follow_redirects=False,
    )
    condition_create = client.post(
        "/campaigns/linden-pass/dm-content/conditions",
        data={"name": "Marked", "description_markdown": "A future picker option."},
        follow_redirects=False,
    )
    statblock = _list_statblocks(app)[0]
    condition = _list_condition_definitions(app)[0]
    statblock_delete = client.post(
        f"/campaigns/linden-pass/dm-content/statblocks/{statblock.id}/delete",
        follow_redirects=False,
    )
    condition_delete = client.post(
        f"/campaigns/linden-pass/dm-content/conditions/{condition.id}/delete",
        follow_redirects=False,
    )

    assert [
        statblock_create.status_code,
        condition_create.status_code,
        statblock_delete.status_code,
        condition_delete.status_code,
    ] == [302, 302, 302, 302]
    assert audit_calls == []
    assert _list_statblocks(app) == []
    assert _list_condition_definitions(app) == []
    with app.app_context():
        assert (
            app.extensions["campaign_combat_service"].get_live_revision("linden-pass")
            == original_revision
        )


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


def test_dm_can_stage_image_only_session_article_from_dm_content(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_article = client.post(
        "/campaigns/linden-pass/dm-content/staged-articles",
        data={
            "article_mode": "manual",
            "title": "Harbor Signal Sketch",
            "body_markdown": "",
            "image_alt": "A sketch of signal flags over the harbor.",
            "image_caption": "The sketch was shown without added body text.",
            "image_file": (BytesIO(TEST_PNG_BYTES), "harbor-signal.png"),
        },
        follow_redirects=True,
    )

    assert create_article.status_code == 200
    create_html = create_article.get_data(as_text=True)
    assert "Staged article added to the session reveal queue." in create_html
    assert "Harbor Signal Sketch" in create_html
    assert "The sketch was shown without added body text." in create_html

    articles = _list_session_articles(app)
    assert len(articles) == 1
    assert articles[0].title == "Harbor Signal Sketch"
    assert articles[0].body_markdown == ""
    assert not articles[0].is_revealed

    with app.app_context():
        image = app.extensions["campaign_session_service"].get_article_image("linden-pass", articles[0].id)

    assert image is not None
    assert image.filename == "harbor-signal.png"
    assert image.alt_text == "A sketch of signal flags over the harbor."
    assert image.caption == "The sketch was shown without added body text."
