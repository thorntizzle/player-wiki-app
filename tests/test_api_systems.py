from __future__ import annotations

import pytest

from tests.helpers.api_test_helpers import *
from tests.helpers.api_test_helpers import (
    _advanced_editor_values,
    _build_systems_import_archive,
    _build_unsafe_systems_import_archive,
    _configure_xianxia_campaign,
    _find_tracker_combatant,
    _import_systems_goblin,
    _seed_systems_item_entry,
    _seed_systems_spell_entry,
    _systems_ref,
    _valid_xianxia_create_data,
    _valid_xianxia_manual_import_data,
    _write_campaign_config,
    _write_character_definition,
    _write_character_state,
    _write_json,
)
from player_wiki.systems_ingest import SystemsArchiveLimits
from player_wiki.auth import VIEW_AS_SESSION_KEY
from tests.helpers.systems_import_helpers import _build_malformed_utf8_systems_import_archive


def test_api_systems_entry_admin_read_contract_includes_disabled_sources_and_nested_denials(
    client,
    app,
    sign_in,
    users,
):
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        slugs: dict[str, str] = {}
        for label, source_enabled, entry_enabled in (
            ("source_disabled", False, True),
            ("entry_disabled", True, False),
        ):
            source_id = f"API-{label.upper()}"
            entry_slug = f"api-admin-read-{label.replace('_', '-')}"
            entry_key = f"dnd-5e|spell|{source_id.lower()}|{entry_slug}"
            store.upsert_source(
                library_slug,
                source_id,
                title=f"API Admin Read {label}",
                license_class="open_license",
                public_visibility_allowed=True,
                requires_unofficial_notice=False,
            )
            store.upsert_campaign_enabled_source(
                "linden-pass",
                library_slug=library_slug,
                source_id=source_id,
                is_enabled=source_enabled,
                default_visibility="players",
            )
            store.replace_entries_for_source(
                library_slug,
                source_id,
                entries=[
                    {
                        "entry_key": entry_key,
                        "entry_type": "spell",
                        "slug": entry_slug,
                        "title": f"API Admin Read {label}",
                        "search_text": f"api admin read {label}",
                        "player_safe_default": True,
                        "metadata": {},
                        "body": {},
                        "rendered_html": f"<p>API Admin Read {label}.</p>",
                    }
                ],
                entry_types=["spell"],
            )
            if not entry_enabled:
                store.upsert_campaign_entry_override(
                    "linden-pass",
                    library_slug=library_slug,
                    entry_key=entry_key,
                    visibility_override=None,
                    is_enabled_override=False,
                )
            slugs[label] = entry_slug

        custom_entry = service.create_custom_campaign_entry(
            "linden-pass",
            title="Archived API Admin Read Custom Entry",
            entry_type="rule",
            slug_leaf="archived-api-admin-read",
            visibility="players",
            body_markdown="Archived API custom entry body.",
            actor_user_id=users["admin"]["id"],
            can_set_private=True,
        )
        service.archive_custom_campaign_entry(
            "linden-pass",
            custom_entry.slug,
            actor_user_id=users["admin"]["id"],
        )
        slugs["archived_custom"] = custom_entry.slug

    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-entry-read")
    player_token = issue_api_token(app, users["party"]["email"], label="player-entry-read")
    entry_url = lambda slug: f"/api/v1/campaigns/linden-pass/systems/entries/{slug}"

    for entry_slug in slugs.values():
        admin_response = client.get(entry_url(entry_slug), headers=api_headers(admin_token))
        assert admin_response.status_code == 200
        assert admin_response.get_json()["entry"]["slug"] == entry_slug

        player_response = client.get(entry_url(entry_slug), headers=api_headers(player_token))
        assert player_response.status_code == 403
        assert player_response.get_json()["error"]["code"] == "forbidden"

        anonymous_response = client.get(entry_url(entry_slug))
        assert anonymous_response.status_code == 401
        assert anonymous_response.get_json()["error"]["code"] == "auth_required"

    sign_in(users["admin"]["email"], users["admin"]["password"])
    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    for entry_slug in slugs.values():
        view_as_response = client.get(entry_url(entry_slug))
        assert view_as_response.status_code == 403
        assert view_as_response.get_json()["error"]["code"] == "forbidden"

    assert client.get(
        entry_url("missing-admin-read-entry"),
        headers=api_headers(admin_token),
    ).status_code == 404
    assert client.get(
        "/api/v1/campaigns/missing-campaign/systems/entries/missing",
        headers=api_headers(admin_token),
    ).status_code == 404


def test_api_systems_endpoints_follow_source_visibility_and_allow_dm_policy_updates(client, app, users, tmp_path):
    goblin_entry_key, goblin_slug = _import_systems_goblin(app, tmp_path)
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-systems-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-systems-api")

    dm_index = client.get("/api/v1/campaigns/linden-pass/systems", headers=api_headers(dm_token))
    assert dm_index.status_code == 200
    dm_index_payload = dm_index.get_json()
    dm_sources = {item["source_id"] for item in dm_index_payload["sources"]}
    assert "MM" in dm_sources
    assert "has_rules_reference_search" in dm_index_payload
    assert "source_scoped_rules_reference_sources" in dm_index_payload

    dm_search = client.get(
        "/api/v1/campaigns/linden-pass/systems?q=goblin",
        headers=api_headers(dm_token),
    )
    assert dm_search.status_code == 200
    dm_search_payload = dm_search.get_json()
    assert dm_search_payload["query"] == "goblin"
    assert dm_search_payload["search_results"]
    assert dm_search_payload["search_results"][0]["entry_key"] == goblin_entry_key
    assert dm_search_payload["reference_query"] == ""

    player_index = client.get("/api/v1/campaigns/linden-pass/systems", headers=api_headers(player_token))
    assert player_index.status_code == 200
    player_sources = {item["source_id"] for item in player_index.get_json()["sources"]}
    assert "MM" not in player_sources

    blocked_source = client.get(
        "/api/v1/campaigns/linden-pass/systems/sources/MM",
        headers=api_headers(player_token),
    )
    assert blocked_source.status_code == 403

    source_detail = client.get(
        "/api/v1/campaigns/linden-pass/systems/sources/MM",
        headers=api_headers(dm_token),
    )
    assert source_detail.status_code == 200
    source_payload = source_detail.get_json()
    assert source_payload["source"]["source_id"] == "MM"
    assert source_payload["entry_count"] == 1
    assert source_payload["browsable_entry_count"] == 1
    assert source_payload["entry_groups"][0]["entry_type"] == "monster"
    assert source_payload["book_entries"] == []
    assert source_payload["reference_query"] == ""
    assert "has_rules_reference_search" in source_payload

    source_category = client.get(
        "/api/v1/campaigns/linden-pass/systems/sources/MM/types/monster",
        headers=api_headers(dm_token),
    )
    assert source_category.status_code == 200
    category_payload = source_category.get_json()
    assert category_payload["entry_groups"][0]["entry_type"] == "monster"
    assert category_payload["entry_groups"][0]["entry_type_label"] == "Monsters"
    assert category_payload["entry_groups"][0]["count"] == 1
    category_entries = category_payload["entries"]
    assert len(category_entries) == 1
    assert category_entries[0]["entry_key"] == goblin_entry_key
    assert category_entries[0]["title"] == "Goblin"

    entry_detail = client.get(
        f"/api/v1/campaigns/linden-pass/systems/entries/{goblin_slug}",
        headers=api_headers(dm_token),
    )
    assert entry_detail.status_code == 200
    entry_payload = entry_detail.get_json()
    assert entry_payload["entry"]["title"] == "Goblin"
    assert entry_payload["entry"]["entry_type"] == "monster"
    assert "rendered_html" in entry_payload["entry"]
    assert entry_payload["links"]["flask_entry_url"].endswith(f"/systems/entries/{goblin_slug}")
    assert "dm-content/systems" in entry_payload["links"]["dm_content_systems_url"]

    update_sources = client.put(
        "/api/v1/campaigns/linden-pass/systems/sources",
        headers=api_headers(dm_token),
        json={
            "updates": [
                {
                    "source_id": "XGE",
                    "is_enabled": True,
                    "default_visibility": "dm",
                }
            ]
        },
    )
    assert update_sources.status_code == 200
    xge_state = next(
        item for item in update_sources.get_json()["sources"] if item["source_id"] == "XGE"
    )
    assert xge_state["default_visibility"] == "dm"

    with app.app_context():
        state = app.extensions["systems_service"].get_campaign_source_state("linden-pass", "XGE")
        assert state is not None
        assert state.default_visibility == "dm"

        events = AuthStore().list_recent_audit_events(
            event_type="campaign_systems_source_updated",
            campaign_slug="linden-pass",
        )
        assert any(event.metadata.get("source_id") == "XGE" for event in events)


def test_api_dm_content_systems_endpoint_returns_management_payload_and_denies_unauthorized_users(
    client,
    app,
    users,
    tmp_path,
):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-systems-content-api")
    player_token = issue_api_token(app, users["party"]["email"], label="player-systems-content-api")
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-systems-content-api")

    # Seed one import run so import history appears in the management payload.
    archive_bytes = _build_systems_import_archive(tmp_path)
    import_response = client.post(
        "/api/v1/systems/imports/dnd5e",
        headers=api_headers(admin_token),
        json={
            "source_ids": ["MM"],
            "entry_types": ["monster"],
            "archive": {
                "filename": "mm-import.zip",
                "data_base64": base64.b64encode(archive_bytes).decode("ascii"),
            },
        },
    )
    assert import_response.status_code == 200
    import_payload = import_response.get_json()
    assert import_payload["ok"] is True
    import_run_ids = [entry["id"] for entry in import_payload["import_runs"]]

    systems_response = client.get(
        "/api/v1/campaigns/linden-pass/dm-content/systems",
        headers=api_headers(dm_token),
    )
    assert systems_response.status_code == 200
    systems_payload = systems_response.get_json()

    assert isinstance(systems_payload["source_rows"], list)
    assert systems_payload["source_rows"]
    assert any(row["source_id"] == "MM" for row in systems_payload["source_rows"])
    assert systems_payload["custom_entry_type_choices"]
    assert len(systems_payload["custom_entry_visibility_choices"]) == 3
    visibility_values = {item["value"] for item in systems_payload["custom_entry_visibility_choices"]}
    assert {"public", "players", "dm"} <= visibility_values
    assert systems_payload["links"]["flask_systems_lane_url"]
    assert systems_payload["links"]["flask_systems_control_url"]

    import_rows = systems_payload["import_run_rows"]
    assert import_rows
    assert set(import_run_ids).issubset({run["id"] for run in import_rows})
    assert all("source_path" not in run for run in import_rows)
    assert any(item["value"] == "spell" for item in systems_payload["custom_entry_type_choices"])

    blocked_response = client.get(
        "/api/v1/campaigns/linden-pass/dm-content/systems",
        headers=api_headers(player_token),
    )
    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"


def test_api_dm_content_systems_custom_entry_lifecycle_returns_refreshed_system_payload(
    client,
    app,
    users,
):
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-systems-custom-entries-api")

    create_response = client.post(
        "/api/v1/campaigns/linden-pass/systems/custom-entries",
        headers=api_headers(dm_token),
        json={
            "title": "API Spark",
            "entry_type": "spell",
            "slug_leaf": "api-systems-spark",
            "provenance": "API test",
            "visibility": "players",
            "search_metadata": "api systems spark",
            "body_markdown": "## Effect\nA small burst of controlled lightning.",
        },
    )
    assert create_response.status_code == 200
    create_payload = create_response.get_json()
    created_entry = create_payload["entry"]
    assert created_entry["title"] == "API Spark"
    assert created_entry["entry_type"] == "spell"
    assert not created_entry["is_archived"]
    assert "systems" in create_payload
    create_systems_payload = create_payload["systems"]
    create_rows = create_systems_payload["custom_entry_source_rows"]
    assert create_rows
    create_source_row = next(
        row for row in create_rows if row["source_id"] == created_entry["source_id"]
    )
    assert any(entry["slug"] == created_entry["slug"] for entry in create_source_row["entries"])

    update_payload = {
        "title": "API Spark Revised",
        "entry_type": "feat",
        "provenance": "API test revised",
        "visibility": "dm",
        "search_metadata": "api systems spark revised",
        "body_markdown": "## Effect\nA revised burst of controlled lightning.",
    }
    update_response = client.put(
        f"/api/v1/campaigns/linden-pass/systems/custom-entries/{created_entry['slug']}",
        headers=api_headers(dm_token),
        json=update_payload,
    )
    assert update_response.status_code == 200
    updated_entry = update_response.get_json()["entry"]
    assert updated_entry["title"] == update_payload["title"]
    assert updated_entry["entry_type"] == update_payload["entry_type"]
    assert "systems" in update_response.get_json()
    updated_systems_payload = update_response.get_json()["systems"]
    updated_source_row = next(
        row for row in updated_systems_payload["custom_entry_source_rows"] if row["source_id"] == created_entry["source_id"]
    )
    assert any(entry["slug"] == created_entry["slug"] for entry in updated_source_row["entries"])

    archive_response = client.post(
        f"/api/v1/campaigns/linden-pass/systems/custom-entries/{created_entry['slug']}/archive",
        headers=api_headers(dm_token),
    )
    assert archive_response.status_code == 200
    archived_entry = archive_response.get_json()["entry"]
    assert archived_entry["is_archived"] is True
    assert "systems" in archive_response.get_json()
    archived_systems_payload = archive_response.get_json()["systems"]
    archived_source_row = next(
        row for row in archived_systems_payload["custom_entry_source_rows"] if row["source_id"] == created_entry["source_id"]
    )
    archived_row_entry = next(
        entry for entry in archived_source_row["entries"] if entry["slug"] == created_entry["slug"]
    )
    assert archived_row_entry["is_archived"] is True

    restore_response = client.post(
        f"/api/v1/campaigns/linden-pass/systems/custom-entries/{created_entry['slug']}/restore",
        headers=api_headers(dm_token),
    )
    assert restore_response.status_code == 200
    restored_entry = restore_response.get_json()["entry"]
    assert restored_entry["is_archived"] is False
    assert "systems" in restore_response.get_json()
    restored_systems_payload = restore_response.get_json()["systems"]
    restored_source_row = next(
        row for row in restored_systems_payload["custom_entry_source_rows"] if row["source_id"] == created_entry["source_id"]
    )
    restored_row_entry = next(
        entry for entry in restored_source_row["entries"] if entry["slug"] == created_entry["slug"]
    )
    assert restored_row_entry["is_archived"] is False


def test_api_systems_imports_campaign_item_page_as_reviewed_mechanics_entry(
    client,
    app,
    users,
):
    item_path = Path(app.config["TEST_CAMPAIGNS_DIR"]) / "linden-pass" / "content" / "items" / "api-consecrated-huran-blade.md"
    item_path.write_text(
        "\n".join(
            [
                "---",
                "title: API Consecrated Huran Blade",
                "section: Items",
                "page_type: item",
                "source_ref: API test item page",
                "published: true",
                "---",
                "",
                "*Weapon (longsword), uncommon (requires attunement)*",
                "",
                "You gain a +1 bonus to attack and damage rolls made with this magic weapon.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-systems-item-mechanics-api")

    systems_response = client.get(
        "/api/v1/campaigns/linden-pass/dm-content/systems",
        headers=api_headers(dm_token),
    )
    assert systems_response.status_code == 200
    systems_payload = systems_response.get_json()
    item_page_row = next(
        row
        for row in systems_payload["campaign_item_page_rows"]
        if row["page_ref"] == "items/api-consecrated-huran-blade"
    )
    assert item_page_row["has_structured_item"] is False

    import_response = client.post(
        "/api/v1/campaigns/linden-pass/systems/item-mechanics/import",
        headers=api_headers(dm_token),
        json={
            "page_ref": "items/api-consecrated-huran-blade",
            "visibility": "players",
            "item_mechanics_review_status": "approved",
        },
    )
    assert import_response.status_code == 200
    payload = import_response.get_json()
    entry = payload["entry"]
    assert entry["entry_type"] == "item"
    assert entry["linked_published_page_ref"] == "items/api-consecrated-huran-blade"
    assert entry["item_mechanics"]["review_status"] == "approved"
    assert entry["item_mechanics"]["support_state"] == "modeled"
    assert "base_item" in entry["item_mechanics"]["modeled_fields"]
    assert "bonus_weapon" in entry["item_mechanics"]["modeled_fields"]

    refreshed_row = next(
        row
        for row in payload["systems"]["campaign_item_page_rows"]
        if row["page_ref"] == "items/api-consecrated-huran-blade"
    )
    assert refreshed_row["has_structured_item"] is True
    assert refreshed_row["entry_slug"] == entry["slug"]
    assert refreshed_row["item_mechanics"]["review_status"] == "approved"


def test_api_campaign_item_mechanics_import_preserves_item_use_actions(
    client,
    app,
    users,
):
    item_path = Path(app.config["TEST_CAMPAIGNS_DIR"]) / "linden-pass" / "content" / "items" / "api-innovators-bolt.md"
    item_path.write_text(
        "\n".join(
            [
                "---",
                "title: API Innovator's Bolt",
                "section: Items",
                "page_type: item",
                "source_ref: API test item page",
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
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-innovators-bolt-api")

    import_response = client.post(
        "/api/v1/campaigns/linden-pass/systems/item-mechanics/import",
        headers=api_headers(dm_token),
        json={
            "page_ref": "items/api-innovators-bolt",
            "visibility": "players",
            "item_mechanics_review_status": "approved",
            "item_mechanics": approved_innovators_bolt_item_mechanics(),
        },
    )

    assert import_response.status_code == 200
    entry = import_response.get_json()["entry"]
    assert entry["item_mechanics"]["review_status"] == "approved"
    assert "item_use_actions" in entry["item_mechanics"]["modeled_fields"]

    with app.app_context():
        library_slug = app.extensions["systems_service"].get_campaign_library_slug("linden-pass")
        stored_entry = app.extensions["systems_store"].get_entry_by_slug(library_slug, entry["slug"])
    assert stored_entry is not None
    actions = stored_entry.metadata["item_use_actions"]
    assert actions[0]["id"] == "innovators-bolt-enchanted-bullet"
    choices = actions[0]["choices"]
    assert [choice["id"] for choice in choices] == ["incendiary", "booming", "smoke"]
    assert choices[0]["damage_scaling"] == {"per_slot_level": "1d6 fire"}
    assert choices[1]["save"]["ability"] == "con"
    assert choices[2]["damage_scaling"] == {"per_slot_level": "1d6 bludgeoning"}
    assert all("table-managed" in choice["summary"] for choice in choices)
    assert all("condition" not in choice for choice in choices)
    assert all("target_effect" not in choice for choice in choices)
    assert all("area" not in choice for choice in choices)


def test_api_systems_import_endpoints_require_admin_and_record_runs(client, app, users, tmp_path):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-systems-import-api")
    dm_token = issue_api_token(app, users["dm"]["email"], label="dm-systems-import-api")
    archive_bytes = _build_systems_import_archive(tmp_path)
    import_payload = {
        "source_ids": ["MM"],
        "entry_types": ["monster"],
        "archive": {
            "filename": "mm-import.zip",
            "data_base64": base64.b64encode(archive_bytes).decode("ascii"),
        },
    }

    blocked_response = client.post(
        "/api/v1/systems/imports/dnd5e",
        headers=api_headers(dm_token),
        json=import_payload,
    )
    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"

    import_response = client.post(
        "/api/v1/systems/imports/dnd5e",
        headers=api_headers(admin_token),
        json=import_payload,
    )
    assert import_response.status_code == 200
    import_payload = import_response.get_json()
    assert import_payload["ok"] is True

    import_result = import_payload["import_results"][0]
    assert import_result["source_id"] == "MM"
    assert import_result["import_version"] == "mm-import"
    assert import_result["imported_count"] == 1
    assert import_result["imported_by_type"] == {"monster": 1}
    assert import_result["source_files"] == ["data/bestiary/bestiary-mm.json"]

    import_run = import_payload["import_runs"][0]
    assert import_run["status"] == "completed"
    assert import_run["source_id"] == "MM"
    assert import_run["import_version"] == "mm-import"
    assert import_run["source_path"] == "api-upload:mm-import.zip"
    assert import_run["started_by_user_id"] == users["admin"]["id"]
    assert import_run["summary"]["entry_types"] == ["monster"]
    assert import_run["summary"]["imported_count"] == 1
    assert import_run["summary"]["source_files"] == ["data/bestiary/bestiary-mm.json"]

    blocked_runs = client.get("/api/v1/systems/import-runs", headers=api_headers(dm_token))
    assert blocked_runs.status_code == 403
    assert blocked_runs.get_json()["error"]["code"] == "forbidden"

    list_response = client.get("/api/v1/systems/import-runs?source_id=MM", headers=api_headers(admin_token))
    assert list_response.status_code == 200
    listed_run = list_response.get_json()["import_runs"][0]
    assert listed_run["id"] == import_run["id"]
    assert listed_run["summary"]["imported_count"] == 1

    detail_response = client.get(
        f"/api/v1/systems/import-runs/{import_run['id']}",
        headers=api_headers(admin_token),
    )
    assert detail_response.status_code == 200
    assert detail_response.get_json()["import_run"]["id"] == import_run["id"]

    dm_source = client.get(
        "/api/v1/campaigns/linden-pass/systems/sources/MM/types/monster",
        headers=api_headers(dm_token),
    )
    assert dm_source.status_code == 200
    imported_entries = dm_source.get_json()["entries"]
    assert len(imported_entries) == 1
    assert imported_entries[0]["title"] == "Goblin"


def test_api_systems_import_endpoint_rejects_unsafe_archives(client, app, users, tmp_path):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-systems-import-unsafe-api")
    archive_bytes = _build_unsafe_systems_import_archive(tmp_path)

    response = client.post(
        "/api/v1/systems/imports/dnd5e",
        headers=api_headers(admin_token),
        json={
            "source_ids": ["MM"],
            "entry_types": ["monster"],
            "archive": {
                "filename": "unsafe-systems-import.zip",
                "data_base64": base64.b64encode(archive_bytes).decode("ascii"),
            },
        },
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"]["code"] == "validation_error"
    assert "parent-relative paths" in payload["error"]["message"]
    assert "unsafe-systems-import.zip" not in payload["error"]["message"]
    with app.app_context():
        assert app.extensions["systems_store"].list_import_runs(library_slug="DND-5E") == []


def test_api_systems_import_prebounds_base64_before_decoder_and_database_mutation(
    client,
    app,
    users,
    monkeypatch,
):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-systems-import-bound-api")
    app.config["SYSTEMS_ARCHIVE_LIMITS"] = SystemsArchiveLimits(
        max_raw_bytes=3
    )
    decoder_called = False

    def fail_if_called(*args, **kwargs):
        nonlocal decoder_called
        decoder_called = True
        raise AssertionError("oversized base64 must be rejected before decoding")

    monkeypatch.setattr("player_wiki.input_limits.base64.b64decode", fail_if_called)
    response = client.post(
        "/api/v1/systems/imports/dnd5e",
        headers=api_headers(admin_token),
        json={
            "source_ids": ["MM"],
            "entry_types": ["monster"],
            "archive": {
                "filename": "oversized.zip",
                "data_base64": "AAAAAA==",
            },
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"
    assert decoder_called is False
    with app.app_context():
        assert app.extensions["systems_store"].list_import_runs(library_slug="DND-5E") == []


@pytest.mark.parametrize("data_base64", ["Y Q==", "YQ=", "YQ===", "not-base64!"])
def test_api_systems_import_rejects_non_strict_base64_without_mutation(
    client,
    app,
    users,
    data_base64,
):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-systems-import-base64-api")
    response = client.post(
        "/api/v1/systems/imports/dnd5e",
        headers=api_headers(admin_token),
        json={
            "source_ids": ["MM"],
            "entry_types": ["monster"],
            "archive": {"filename": "invalid.zip", "data_base64": data_base64},
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"
    with app.app_context():
        assert app.extensions["systems_store"].list_import_runs(library_slug="DND-5E") == []


def test_api_systems_import_rejects_noncanonical_base64_without_mutation(
    client,
    app,
    users,
):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-systems-import-canonical-api")
    for data_base64 in ("Zh==", "Zm9="):
        response = client.post(
            "/api/v1/systems/imports/dnd5e",
            headers=api_headers(admin_token),
            json={
                "source_ids": ["MM"],
                "entry_types": ["monster"],
                "archive": {"filename": "noncanonical.zip", "data_base64": data_base64},
            },
        )

        assert response.status_code == 400
        payload = response.get_json()
        assert payload["error"]["code"] == "validation_error"
        assert payload["error"]["message"] == (
            "archive data_base64 must be valid base64 and stay at or under 64 MiB."
        )
    with app.app_context():
        assert app.extensions["systems_store"].list_import_runs(library_slug="DND-5E") == []


def test_api_systems_import_rejects_malformed_utf8_without_leak_mutation_or_residue(
    client,
    app,
    users,
    tmp_path,
    monkeypatch,
):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-systems-import-malformed-api")
    temp_root = tmp_path / "systems-temp"
    monkeypatch.setenv("PLAYER_WIKI_TEMP_DIR", str(temp_root))
    response = client.post(
        "/api/v1/systems/imports/dnd5e",
        headers=api_headers(admin_token),
        json={
            "source_ids": ["MM"],
            "entry_types": ["monster"],
            "archive": {
                "filename": "ATTACKER-SENTINEL.zip",
                "data_base64": base64.b64encode(
                    _build_malformed_utf8_systems_import_archive()
                ).decode("ascii"),
            },
        },
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == {
        "code": "validation_error",
        "message": "Import archive must be a valid supported ZIP file.",
    }
    response_text = response.get_data(as_text=True)
    assert "ATTACKER-SENTINEL" not in response_text
    assert "codec" not in response_text
    assert "position" not in response_text
    with app.app_context():
        store = app.extensions["systems_store"]
        assert store.list_import_runs(library_slug="DND-5E") == []
        assert store.list_entries_for_source("DND-5E", "MM", entry_type="monster", limit=None) == []
    assert not temp_root.exists() or list(temp_root.iterdir()) == []


def test_api_systems_import_accepts_archive_at_exact_raw_limit(client, app, users):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-systems-import-exact-api")
    archive_bytes = _build_systems_import_archive(wrapper="source-export")
    app.config["SYSTEMS_ARCHIVE_LIMITS"] = SystemsArchiveLimits(
        max_raw_bytes=len(archive_bytes)
    )
    response = client.post(
        "/api/v1/systems/imports/dnd5e",
        headers=api_headers(admin_token),
        json={
            "source_ids": ["MM"],
            "entry_types": ["monster"],
            "archive": {
                "filename": "exact.zip",
                "data_base64": base64.b64encode(archive_bytes).decode("ascii"),
            },
        },
    )

    assert response.status_code == 200
    assert response.get_json()["ok"] is True
