from __future__ import annotations

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

def test_api_admin_view_as_uses_target_permissions_and_blocks_campaign_writes(client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])

    me_response = client.get("/api/v1/me")
    assert me_response.status_code == 200
    me_payload = me_response.get_json()
    assert me_payload["user"]["email"] == users["admin"]["email"]
    assert me_payload["view_as"]["can_view_as"] is True
    assert me_payload["view_as"]["active_user"] is None
    choice_emails = {choice["email"] for choice in me_payload["view_as"]["user_choices"]}
    assert users["party"]["email"] in choice_emails

    set_response = client.post(
        "/api/v1/me/view-as",
        json={"user_id": users["party"]["id"]},
    )
    assert set_response.status_code == 200
    set_payload = set_response.get_json()
    assert set_payload["view_as"]["active_user"]["email"] == users["party"]["email"]

    me_after = client.get("/api/v1/me")
    assert me_after.status_code == 200
    me_after_payload = me_after.get_json()
    assert me_after_payload["user"]["email"] == users["admin"]["email"]
    assert me_after_payload["view_as"]["active_user"]["email"] == users["party"]["email"]

    campaign_response = client.get("/api/v1/campaigns/linden-pass")
    assert campaign_response.status_code == 200
    campaign_payload = campaign_response.get_json()
    assert campaign_payload["role"] == "player"
    assert campaign_payload["permissions"]["can_manage_dm_content"] is False
    assert campaign_payload["visibility"]["dm_content"]["can_access"] is False

    blocked_dm_content = client.get("/api/v1/campaigns/linden-pass/dm-content")
    assert blocked_dm_content.status_code == 403

    blocked_write = client.post("/api/v1/campaigns/linden-pass/session/start")
    assert blocked_write.status_code == 403
    assert blocked_write.get_json()["error"]["code"] == "view_as_read_only"

    clear_response = client.delete("/api/v1/me/view-as")
    assert clear_response.status_code == 200
    assert clear_response.get_json()["view_as"]["active_user"] is None

    admin_dm_content = client.get("/api/v1/campaigns/linden-pass/dm-content")
    assert admin_dm_content.status_code == 200

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["party"]["email"], users["party"]["password"])
    forbidden_set = client.post(
        "/api/v1/me/view-as",
        json={"user_id": users["admin"]["id"]},
    )
    assert forbidden_set.status_code == 403

    player_me = client.get("/api/v1/me")
    assert player_me.status_code == 200
    assert player_me.get_json()["view_as"]["can_view_as"] is False


def test_api_me_and_campaigns_use_bearer_token_auth(client, app, users):
    token = issue_api_token(app, users["dm"]["email"], label="dm-api")

    me_response = client.get("/api/v1/me", headers=api_headers(token))

    assert me_response.status_code == 200
    me_payload = me_response.get_json()
    assert me_payload["ok"] is True
    assert me_payload["auth_source"] == "api_token"
    assert me_payload["user"]["email"] == users["dm"]["email"]
    assert me_payload["preferences"]["theme_key"] is not None
    assert me_payload["preferences"]["session_chat_order"] is not None
    assert me_payload["preferences"]["frontend_mode"] == "flask"

    campaigns_response = client.get("/api/v1/campaigns", headers=api_headers(token))

    assert campaigns_response.status_code == 200
    campaigns_payload = campaigns_response.get_json()
    assert campaigns_payload["campaigns"][0]["campaign"]["slug"] == "linden-pass"
    assert campaigns_payload["campaigns"][0]["role"] == "dm"

    with app.app_context():
        store = AuthStore()
        token_record = store.get_active_api_token(token)
        assert token_record is not None
        store.revoke_api_token(token_record.id)

    revoked_response = client.get("/api/v1/me", headers=api_headers(token))

    assert revoked_response.status_code == 401
    assert revoked_response.get_json()["error"]["code"] == "auth_required"


def test_api_account_settings_reads_and_updates_user_preferences(client, app, users):
    token = issue_api_token(app, users["party"]["email"], label="account-settings-api")

    settings_response = client.get("/api/v1/me/settings", headers=api_headers(token))

    assert settings_response.status_code == 200
    settings_payload = settings_response.get_json()
    assert settings_payload["ok"] is True
    assert settings_payload["user"]["email"] == users["party"]["email"]
    assert settings_payload["preferences"] == {
        "theme_key": "parchment",
        "session_chat_order": "newest_first",
        "frontend_mode": "flask",
    }
    assert [theme["key"] for theme in settings_payload["theme_presets"]] == [
        "parchment",
        "moonlit",
        "verdant",
        "ember",
    ]
    assert [choice["value"] for choice in settings_payload["session_chat_order_choices"]] == [
        "newest_first",
        "oldest_first",
    ]
    assert "frontend_mode_choices" not in settings_payload

    update_response = client.patch(
        "/api/v1/me/settings",
        headers=api_headers(token),
        json={"theme_key": "moonlit", "session_chat_order": "oldest_first"},
    )

    assert update_response.status_code == 200
    update_payload = update_response.get_json()
    assert update_payload["preferences"] == {
        "theme_key": "moonlit",
        "session_chat_order": "oldest_first",
        "frontend_mode": "flask",
    }

    me_response = client.get("/api/v1/me", headers=api_headers(token))
    assert me_response.status_code == 200
    assert me_response.get_json()["preferences"] == update_payload["preferences"]

    with app.app_context():
        preferences = AuthStore().get_user_preferences(users["party"]["id"])
        assert preferences.theme_key == "moonlit"
        assert preferences.session_chat_order == "oldest_first"
        assert preferences.frontend_mode == "flask"


def test_api_account_settings_rejects_invalid_preferences(client, app, users):
    token = issue_api_token(app, users["party"]["email"], label="account-settings-invalid-api")

    invalid_theme_response = client.patch(
        "/api/v1/me/settings",
        headers=api_headers(token),
        json={"theme_key": "bad-theme", "session_chat_order": "oldest_first"},
    )
    assert invalid_theme_response.status_code == 400
    assert invalid_theme_response.get_json()["error"]["code"] == "validation_error"
    assert invalid_theme_response.get_json()["error"]["message"] == "Choose a valid theme preset."

    invalid_order_response = client.patch(
        "/api/v1/me/settings",
        headers=api_headers(token),
        json={"theme_key": "moonlit", "session_chat_order": "sideways"},
    )
    assert invalid_order_response.status_code == 400
    assert invalid_order_response.get_json()["error"]["code"] == "validation_error"
    assert invalid_order_response.get_json()["error"]["message"] == "Choose a valid live session chat order."

    invalid_frontend_response = client.patch(
        "/api/v1/me/settings",
        headers=api_headers(token),
        json={"frontend_mode": "gen2"},
    )
    assert invalid_frontend_response.status_code == 400
    assert invalid_frontend_response.get_json()["error"]["code"] == "validation_error"
    assert (
        invalid_frontend_response.get_json()["error"]["message"]
        == "Preferred frontend selection is no longer available."
    )

    empty_response = client.patch("/api/v1/me/settings", headers=api_headers(token), json={})
    assert empty_response.status_code == 400
    assert empty_response.get_json()["error"]["message"] == "No account settings were provided."

    with app.app_context():
        preferences = AuthStore().get_user_preferences(users["party"]["id"])
        assert preferences.theme_key == "parchment"
        assert preferences.session_chat_order == "newest_first"
        assert preferences.frontend_mode == "flask"


def test_api_admin_user_management_context_actions_and_permissions(client, app, users):
    admin_token = issue_api_token(app, users["admin"]["email"], label="admin-api")
    owner_token = issue_api_token(app, users["owner"]["email"], label="admin-blocked-api")

    anonymous = client.get("/api/v1/admin")
    blocked = client.get("/api/v1/admin", headers=api_headers(owner_token))
    dashboard = client.get("/api/v1/admin", headers=api_headers(admin_token))

    assert anonymous.status_code == 401
    assert blocked.status_code == 403
    assert dashboard.status_code == 200
    dashboard_payload = dashboard.get_json()
    assert dashboard_payload["ok"] is True
    assert dashboard_payload["links"]["admin_url"] == "/admin"
    assert any(user["email"] == users["owner"]["email"] for user in dashboard_payload["user_cards"])
    assert any(choice["value"] == "user_invited" for choice in dashboard_payload["audit_event_type_choices"])

    invite_response = client.post(
        "/api/v1/admin/users/invite",
        headers=api_headers(admin_token),
        json={
            "email": "flask-admin-api@example.com",
            "display_name": "Flask Admin API",
            "user_type": "standard",
        },
    )
    assert invite_response.status_code == 201
    invite_payload = invite_response.get_json()
    assert invite_payload["managed_user"]["email"] == "flask-admin-api@example.com"
    assert "/invite/" in invite_payload["invite_url"]
    assert "/invite/" in invite_payload["message"]
    created_user_id = invite_payload["managed_user"]["id"]

    detail_response = client.get(f"/api/v1/admin/users/{created_user_id}", headers=api_headers(admin_token))
    detail_payload = detail_response.get_json()
    assert detail_response.status_code == 200
    assert detail_payload["managed_user"]["status"] == "invited"
    assert detail_payload["links"]["user_url"] == f"/admin/users/{created_user_id}"

    membership_response = client.post(
        f"/api/v1/admin/users/{created_user_id}/membership",
        headers=api_headers(admin_token),
        json={
            "campaign_slug": "linden-pass",
            "role": "player",
            "status": "active",
        },
    )
    assert membership_response.status_code == 200
    membership_payload = membership_response.get_json()
    assert any(
        membership["campaign_slug"] == "linden-pass"
        and membership["role"] == "player"
        and membership["status"] == "active"
        for membership in membership_payload["memberships"]
    )

    assignment_response = client.post(
        f"/api/v1/admin/users/{created_user_id}/assignment",
        headers=api_headers(admin_token),
        json={"character_ref": "linden-pass::selene-brook"},
    )
    assert assignment_response.status_code == 200
    assignment_payload = assignment_response.get_json()
    assert any(
        assignment["campaign_slug"] == "linden-pass"
        and assignment["character_slug"] == "selene-brook"
        and assignment["character_label"] == "Selene Brook"
        for assignment in assignment_payload["assignments"]
    )
    assert assignment_payload["message"] == (
        "Assigned Selene Brook in Echoes of the Alloy Coast to flask-admin-api@example.com."
    )

    remove_assignment_response = client.delete(
        f"/api/v1/admin/users/{created_user_id}/assignment",
        headers=api_headers(admin_token),
        json={"campaign_slug": "linden-pass", "character_slug": "selene-brook"},
    )
    assert remove_assignment_response.status_code == 200
    assert not any(
        assignment["campaign_slug"] == "linden-pass"
        and assignment["character_slug"] == "selene-brook"
        for assignment in remove_assignment_response.get_json()["assignments"]
    )

    reassign_response = client.post(
        f"/api/v1/admin/users/{created_user_id}/assignment",
        headers=api_headers(admin_token),
        json={"character_ref": "linden-pass::selene-brook"},
    )
    assert reassign_response.status_code == 200

    remove_membership_response = client.delete(
        f"/api/v1/admin/users/{created_user_id}/membership",
        headers=api_headers(admin_token),
        json={"campaign_slug": "linden-pass"},
    )
    assert remove_membership_response.status_code == 200
    assert any(
        membership["campaign_slug"] == "linden-pass"
        and membership["status"] == "removed"
        for membership in remove_membership_response.get_json()["memberships"]
    )

    filtered_detail = client.get(
        f"/api/v1/admin/users/{created_user_id}?audit_q=selene-brook",
        headers=api_headers(admin_token),
    )
    filtered_payload = filtered_detail.get_json()
    assert filtered_detail.status_code == 200
    assert any(event["event_type"] == "character_assignment_created" for event in filtered_payload["recent_audit_events"])
    assert all("/invite/" not in event.get("details", "") for event in filtered_payload["recent_audit_events"])

    invite_again = client.post(
        f"/api/v1/admin/users/{created_user_id}/invite",
        headers=api_headers(admin_token),
    )
    assert invite_again.status_code == 200
    assert "/invite/" in invite_again.get_json()["invite_url"]

    reset_response = client.post(
        f"/api/v1/admin/users/{users['owner']['id']}/password-reset",
        headers=api_headers(admin_token),
    )
    assert reset_response.status_code == 200
    assert "/reset/" in reset_response.get_json()["reset_url"]

    disable_response = client.post(
        f"/api/v1/admin/users/{users['owner']['id']}/disable",
        headers=api_headers(admin_token),
    )
    assert disable_response.status_code == 200
    assert disable_response.get_json()["managed_user"]["status"] == "disabled"

    enable_response = client.post(
        f"/api/v1/admin/users/{users['owner']['id']}/enable",
        headers=api_headers(admin_token),
    )
    assert enable_response.status_code == 200
    assert enable_response.get_json()["managed_user"]["status"] == "active"

    delete_without_confirmation = client.delete(
        f"/api/v1/admin/users/{created_user_id}",
        headers=api_headers(admin_token),
        json={"confirm_email": ""},
    )
    assert delete_without_confirmation.status_code == 400

    delete_response = client.delete(
        f"/api/v1/admin/users/{created_user_id}",
        headers=api_headers(admin_token),
        json={"confirm_email": "flask-admin-api@example.com"},
    )
    assert delete_response.status_code == 200
    delete_payload = delete_response.get_json()
    assert delete_payload["deleted_user"]["email"] == "flask-admin-api@example.com"
    assert all(user["email"] != "flask-admin-api@example.com" for user in delete_payload["user_cards"])

    with app.app_context():
        store = AuthStore()
        assert store.get_user_by_id(created_user_id) is None
        assert store.get_character_assignment("linden-pass", "selene-brook") is None


def test_api_campaign_help_returns_surface_guidance_for_viewer_access(client, app, users):
    player_token = issue_api_token(app, users["party"]["email"], label="campaign-help-player-api")

    response = client.get("/api/v1/campaigns/linden-pass/help", headers=api_headers(player_token))
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["campaign"]["slug"] == "linden-pass"
    assert payload["viewer_role_label"] == "Player"
    assert payload["campaign_system_label"] == "DND-5E"
    assert payload["links"]["flask_help_url"] == "/campaigns/linden-pass/help"
    assert payload["links"]["help_url"] == "/campaigns/linden-pass/help"

    surface_labels = [surface["label"] for surface in payload["surfaces"]]
    assert "Campaign Home" in surface_labels
    assert "Systems" in surface_labels
    assert "Session" in surface_labels
    assert "Combat" in surface_labels
    assert "DM Content" not in surface_labels
    assert "Control" not in surface_labels
    assert payload["available_surface_labels"] == surface_labels
    assert any("polling instead of websockets" in item for item in payload["cross_cutting_limits"])

    dm_token = issue_api_token(app, users["dm"]["email"], label="campaign-help-dm-api")
    dm_response = client.get("/api/v1/campaigns/linden-pass/help", headers=api_headers(dm_token))
    assert dm_response.status_code == 200
    dm_payload = dm_response.get_json()
    dm_surface_labels = [surface["label"] for surface in dm_payload["surfaces"]]
    assert "DM Content" in dm_surface_labels
    assert "Characters" in dm_surface_labels
    assert "Control" in dm_surface_labels
    dm_content = next(surface for surface in dm_payload["surfaces"] if surface["label"] == "DM Content")
    assert "Browser and API boundary" in [card["title"] for card in dm_content["guidance_cards"]]


def test_api_campaign_control_visibility_requires_manager_and_updates_scopes(client, app, users):
    dm_token = issue_api_token(app, users["dm"]["email"], label="campaign-control-dm-api")
    player_token = issue_api_token(app, users["party"]["email"], label="campaign-control-player-api")

    blocked_response = client.get("/api/v1/campaigns/linden-pass/control", headers=api_headers(player_token))
    assert blocked_response.status_code == 403
    assert blocked_response.get_json()["error"]["code"] == "forbidden"

    control_response = client.get("/api/v1/campaigns/linden-pass/control", headers=api_headers(dm_token))
    assert control_response.status_code == 200
    payload = control_response.get_json()
    assert payload["ok"] is True
    assert payload["campaign"]["slug"] == "linden-pass"
    assert payload["links"]["flask_control_url"] == "/campaigns/linden-pass/control-panel"
    assert payload["links"]["control_url"] == "/campaigns/linden-pass/control-panel"
    rows_by_scope = {row["scope"]: row for row in payload["visibility_rows"]}
    assert rows_by_scope["campaign"]["selected_visibility"] == "public"
    assert rows_by_scope["characters"]["effective_visibility"] == "dm"
    assert payload["can_set_private_visibility"] is False

    private_response = client.patch(
        "/api/v1/campaigns/linden-pass/control/visibility",
        headers=api_headers(dm_token),
        json={"visibility": {"campaign": "private"}},
    )
    assert private_response.status_code == 400
    assert private_response.get_json()["error"]["message"] == "Private visibility is reserved for app admins."

    update_response = client.patch(
        "/api/v1/campaigns/linden-pass/control/visibility",
        headers=api_headers(dm_token),
        json={"visibility": {"campaign": "players", "wiki": "dm", "session": "players"}},
    )
    assert update_response.status_code == 200
    updated = update_response.get_json()
    assert set(updated["changed_scopes"]) == {"Campaign", "Player Wiki"}
    updated_rows = {row["scope"]: row for row in updated["visibility_rows"]}
    assert updated_rows["campaign"]["selected_visibility"] == "players"
    assert updated_rows["wiki"]["selected_visibility"] == "dm"
    assert updated_rows["session"]["effective_visibility"] == "players"
    assert "Updated visibility for" in updated["message"]

    with app.app_context():
        store = AuthStore()
        campaign_setting = store.get_campaign_visibility_setting("linden-pass", "campaign")
        wiki_setting = store.get_campaign_visibility_setting("linden-pass", "wiki")
        assert campaign_setting is not None
        assert campaign_setting.visibility == "players"
        assert wiki_setting is not None
        assert wiki_setting.visibility == "dm"
