from __future__ import annotations

from player_wiki.auth_store import AuthStore


def test_admin_can_open_dashboard_and_user_detail(app, client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])

    dashboard = client.get("/admin")
    detail = client.get(f"/admin/users/{users['owner']['id']}")

    assert dashboard.status_code == 200
    dashboard_html = dashboard.get_data(as_text=True)
    assert "Admin dashboard" in dashboard_html
    assert "Invite user" in dashboard_html
    assert 'option value="admin"' in dashboard_html
    assert 'option value="dm"' in dashboard_html
    assert 'option value="player"' in dashboard_html
    assert "Standard user" not in dashboard_html
    assert users["owner"]["email"] in dashboard_html

    assert detail.status_code == 200
    detail_html = detail.get_data(as_text=True)
    assert "Campaign membership" in detail_html
    assert "Character assignment" in detail_html


def test_non_admin_cannot_access_admin_routes(client, sign_in, users):
    sign_in(users["owner"]["email"], users["owner"]["password"])

    dashboard = client.get("/admin")
    detail = client.get(f"/admin/users/{users['owner']['id']}")

    assert dashboard.status_code == 403
    assert detail.status_code == 403


def test_admin_can_invite_user_from_dashboard(app, client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])

    response = client.post(
        "/admin/users/invite",
        data={
            "email": "fresh-invite@example.com",
            "display_name": "Fresh Invite",
            "user_type": "player",
            "campaign_slug": "linden-pass",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Invite URL:" in html
    assert "Fresh Invite" in html

    with app.app_context():
        store = AuthStore()
        user = store.get_user_by_email("fresh-invite@example.com")
        assert user is not None
        assert user.status == "invited"
        assert user.is_admin is False

        membership = store.get_membership(user.id, "linden-pass", statuses=None)
        assert membership is not None
        assert membership.role == "player"
        assert membership.status == "active"


def test_admin_can_invite_admin_from_dashboard_without_campaign_membership(app, client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])

    response = client.post(
        "/admin/users/invite",
        data={
            "email": "fresh-admin@example.com",
            "display_name": "Fresh Admin",
            "user_type": "admin",
            "campaign_slug": "linden-pass",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app.app_context():
        store = AuthStore()
        user = store.get_user_by_email("fresh-admin@example.com")
        assert user is not None
        assert user.status == "invited"
        assert user.is_admin is True
        assert store.get_membership(user.id, "linden-pass", statuses=None) is None


def test_admin_can_set_membership_and_assignment(app, client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])

    response = client.post(
        f"/admin/users/{users['outsider']['id']}/membership",
        data={
            "campaign_slug": "linden-pass",
            "role": "player",
            "status": "active",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    response = client.post(
        f"/admin/users/{users['outsider']['id']}/assignment",
        data={"character_ref": "linden-pass::selene-brook"},
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        store = AuthStore()
        membership = store.get_membership(users["outsider"]["id"], "linden-pass", statuses=("active",))
        assignment = store.get_character_assignment("linden-pass", "selene-brook")
        assert membership is not None
        assert membership.role == "player"
        assert assignment is not None
        assert assignment.user_id == users["outsider"]["id"]


def test_admin_can_issue_password_reset(app, client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])

    response = client.post(
        f"/admin/users/{users['owner']['id']}/password-reset",
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Password reset URL:" in html


def test_admin_can_reenable_disabled_user_and_user_can_sign_back_in(app, client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])

    disable_response = client.post(
        f"/admin/users/{users['owner']['id']}/disable",
        follow_redirects=False,
    )
    assert disable_response.status_code == 302

    enable_response = client.post(
        f"/admin/users/{users['owner']['id']}/enable",
        follow_redirects=True,
    )

    assert enable_response.status_code == 200
    enable_html = enable_response.get_data(as_text=True)
    assert "Re-enabled user owner@example.com." in enable_html

    with app.app_context():
        store = AuthStore()
        user = store.get_user_by_id(users["owner"]["id"])
        events = store.list_recent_audit_events(limit=10)

        assert user is not None
        assert user.status == "active"
        assert any(event.event_type == "user_enabled" for event in events)

    client.post("/sign-out", follow_redirects=False)
    sign_in_response = sign_in(users["owner"]["email"], users["owner"]["password"])
    assert sign_in_response.status_code == 302


def test_admin_can_delete_user_and_clear_direct_account_records(app, client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])

    membership_response = client.post(
        f"/admin/users/{users['outsider']['id']}/membership",
        data={
            "campaign_slug": "linden-pass",
            "role": "player",
            "status": "active",
        },
        follow_redirects=False,
    )
    assert membership_response.status_code == 302

    assignment_response = client.post(
        f"/admin/users/{users['outsider']['id']}/assignment",
        data={"character_ref": "linden-pass::selene-brook"},
        follow_redirects=False,
    )
    assert assignment_response.status_code == 302

    delete_response = client.post(
        f"/admin/users/{users['outsider']['id']}/delete",
        follow_redirects=True,
    )

    assert delete_response.status_code == 200
    delete_html = delete_response.get_data(as_text=True)
    assert "Deleted user outsider@example.com." in delete_html

    deleted_detail = client.get(f"/admin/users/{users['outsider']['id']}")
    assert deleted_detail.status_code == 404

    with app.app_context():
        store = AuthStore()
        user = store.get_user_by_id(users["outsider"]["id"])
        membership = store.get_membership(users["outsider"]["id"], "linden-pass", statuses=None)
        assignment = store.get_character_assignment("linden-pass", "selene-brook")
        events = store.list_recent_audit_events(limit=10)

        assert user is None
        assert membership is None
        assert assignment is None
        assert any(event.event_type == "user_deleted" for event in events)


def test_admin_can_reenable_disabled_invited_user_back_to_invited_status(app, client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])

    invite_response = client.post(
        "/admin/users/invite",
        data={
            "email": "disabled-invite@example.com",
            "display_name": "Disabled Invite",
            "user_type": "standard",
        },
        follow_redirects=False,
    )
    assert invite_response.status_code == 302

    with app.app_context():
        store = AuthStore()
        invited_user = store.get_user_by_email("disabled-invite@example.com")
        assert invited_user is not None
        invited_user_id = invited_user.id

    disable_response = client.post(
        f"/admin/users/{invited_user_id}/disable",
        follow_redirects=False,
    )
    assert disable_response.status_code == 302

    enable_response = client.post(
        f"/admin/users/{invited_user_id}/enable",
        follow_redirects=True,
    )

    assert enable_response.status_code == 200
    enable_html = enable_response.get_data(as_text=True)
    assert "The account is back in invited status." in enable_html
    assert "Generate invite link" in enable_html

    with app.app_context():
        store = AuthStore()
        user = store.get_user_by_id(invited_user_id)

        assert user is not None
        assert user.status == "invited"


def test_admin_dashboard_shows_recent_activity_without_raw_tokens(app, client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])

    response = client.post(
        "/admin/users/invite",
        data={
            "email": "audit-target@example.com",
            "display_name": "Audit Target",
            "is_admin": "0",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    client.get(response.headers["Location"])
    dashboard = client.get("/admin")
    html = dashboard.get_data(as_text=True)

    assert dashboard.status_code == 200
    assert "Recent activity" in html
    assert "Invite issued" in html
    assert "/invite/" not in html

    with app.app_context():
        store = AuthStore()
        events = store.list_recent_audit_events(limit=10)
        invited_event = next(event for event in events if event.event_type == "user_invited")
        assert "invite_url" not in invited_event.metadata


def test_admin_user_detail_shows_recent_activity_for_that_user(client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])

    response = client.post(
        f"/admin/users/{users['outsider']['id']}/membership",
        data={
            "campaign_slug": "linden-pass",
            "role": "player",
            "status": "active",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    client.get(response.headers["Location"])
    detail = client.get(f"/admin/users/{users['outsider']['id']}")
    html = detail.get_data(as_text=True)

    assert detail.status_code == 200
    assert "Recent activity for this user" in html
    assert "Membership created" in html


def test_admin_dashboard_can_filter_recent_activity_by_event_type_and_campaign(client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])

    invite_response = client.post(
        "/admin/users/invite",
        data={
            "email": "filter-target@example.com",
            "display_name": "Filter Target",
            "is_admin": "0",
        },
        follow_redirects=False,
    )
    assert invite_response.status_code == 302

    membership_response = client.post(
        f"/admin/users/{users['outsider']['id']}/membership",
        data={
            "campaign_slug": "linden-pass",
            "role": "player",
            "status": "active",
        },
        follow_redirects=False,
    )
    assert membership_response.status_code == 302

    event_type_filtered = client.get("/admin?audit_event_type=user_invited")
    event_type_html = event_type_filtered.get_data(as_text=True)

    assert event_type_filtered.status_code == 200
    assert 'data-event-type="user_invited"' in event_type_html
    assert 'data-event-type="membership_created"' not in event_type_html

    campaign_filtered = client.get("/admin?audit_campaign_slug=linden-pass")
    campaign_html = campaign_filtered.get_data(as_text=True)

    assert campaign_filtered.status_code == 200
    assert 'data-event-type="membership_created"' in campaign_html
    assert 'data-event-type="user_invited"' not in campaign_html


def test_admin_user_detail_can_filter_recent_activity_by_query(client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])

    membership_response = client.post(
        f"/admin/users/{users['outsider']['id']}/membership",
        data={
            "campaign_slug": "linden-pass",
            "role": "player",
            "status": "active",
        },
        follow_redirects=False,
    )
    assert membership_response.status_code == 302

    assignment_response = client.post(
        f"/admin/users/{users['outsider']['id']}/assignment",
        data={"character_ref": "linden-pass::selene-brook"},
        follow_redirects=False,
    )
    assert assignment_response.status_code == 302

    detail = client.get(f"/admin/users/{users['outsider']['id']}?audit_q=selene-brook")
    html = detail.get_data(as_text=True)

    assert detail.status_code == 200
    assert 'data-event-type="character_assignment_created"' in html
    assert 'data-event-type="membership_created"' not in html


def test_admin_dashboard_activity_supports_pagination_and_csv_export(client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])

    for index in range(12):
        response = client.post(
            "/admin/users/invite",
            data={
                "email": f"page-user-{index:02d}@example.com",
                "display_name": f"Page User {index:02d}",
                "is_admin": "0",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    first_page = client.get("/admin?audit_event_type=user_invited")
    first_html = first_page.get_data(as_text=True)
    second_page = client.get("/admin?audit_event_type=user_invited&audit_page=2")
    second_html = second_page.get_data(as_text=True)
    export_response = client.get("/admin/activity/export.csv?audit_event_type=user_invited")
    export_text = export_response.get_data(as_text=True)

    assert first_page.status_code == 200
    assert 'data-target-email="page-user-11@example.com"' in first_html
    assert 'data-target-email="page-user-00@example.com"' not in first_html
    assert "Page 1 of 2" in first_html

    assert second_page.status_code == 200
    assert 'data-target-email="page-user-00@example.com"' in second_html
    assert 'data-target-email="page-user-11@example.com"' not in second_html
    assert "Page 2 of 2" in second_html

    assert export_response.status_code == 200
    assert export_response.headers["Content-Type"].startswith("text/csv")
    assert "attachment; filename=\"admin-activity-export.csv\"" == export_response.headers["Content-Disposition"]
    assert "event_type,event_title" in export_text
    assert "user_invited,Invite issued" in export_text


def test_admin_user_detail_supports_csv_export_prefill_and_removal_actions(app, client, sign_in, users):
    sign_in(users["admin"]["email"], users["admin"]["password"])

    membership_response = client.post(
        f"/admin/users/{users['outsider']['id']}/membership",
        data={
            "campaign_slug": "linden-pass",
            "role": "player",
            "status": "active",
        },
        follow_redirects=False,
    )
    assert membership_response.status_code == 302

    assignment_response = client.post(
        f"/admin/users/{users['outsider']['id']}/assignment",
        data={"character_ref": "linden-pass::selene-brook"},
        follow_redirects=False,
    )
    assert assignment_response.status_code == 302

    prefill_response = client.get(
        f"/admin/users/{users['outsider']['id']}?edit_membership_campaign_slug=linden-pass"
        "&edit_assignment_campaign_slug=linden-pass&edit_assignment_character_slug=selene-brook"
    )
    prefill_html = prefill_response.get_data(as_text=True)
    export_response = client.get(
        f"/admin/users/{users['outsider']['id']}/activity/export.csv?audit_event_type=character_assignment_created"
    )
    export_text = export_response.get_data(as_text=True)

    assert prefill_response.status_code == 200
    assert 'option value="linden-pass" selected' in prefill_html
    assert 'option value="player" selected' in prefill_html
    assert 'option value="active" selected' in prefill_html
    assert 'option value="linden-pass::selene-brook" selected' in prefill_html

    assert export_response.status_code == 200
    assert "character_assignment_created,Character assigned" in export_text
    assert "membership_created,Membership created" not in export_text

    remove_assignment = client.post(
        f"/admin/users/{users['outsider']['id']}/assignment/remove",
        data={"campaign_slug": "linden-pass", "character_slug": "selene-brook"},
        follow_redirects=False,
    )
    remove_membership = client.post(
        f"/admin/users/{users['outsider']['id']}/membership/remove",
        data={"campaign_slug": "linden-pass"},
        follow_redirects=False,
    )

    assert remove_assignment.status_code == 302
    assert remove_membership.status_code == 302

    with app.app_context():
        store = AuthStore()
        membership = store.get_membership(users["outsider"]["id"], "linden-pass", statuses=None)
        assignment = store.get_character_assignment("linden-pass", "selene-brook")
        events = store.list_audit_events_for_user(users["outsider"]["id"], limit=10)

        assert membership is not None
        assert membership.status == "removed"
        assert assignment is None
        assert any(event.event_type == "character_assignment_removed" for event in events)
        assert any(event.event_type == "membership_removed" for event in events)

