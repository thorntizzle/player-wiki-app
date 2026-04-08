from __future__ import annotations

from player_wiki.auth_store import AuthStore


def build_source_form(app, campaign_slug: str = "linden-pass") -> dict[str, str]:
    with app.app_context():
        service = app.extensions["systems_service"]
        rows = service.list_campaign_source_states(campaign_slug)

    data: dict[str, str] = {}
    for row in rows:
        if row.is_enabled:
            data[f"source_{row.source.source_id}_enabled"] = "1"
        data[f"source_{row.source.source_id}_visibility"] = row.default_visibility
    return data


def test_party_member_sees_systems_nav_and_player_visible_sources(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    campaign = client.get("/campaigns/linden-pass")
    systems = client.get("/campaigns/linden-pass/systems")

    assert campaign.status_code == 200
    campaign_body = campaign.get_data(as_text=True)
    assert 'href="/campaigns/linden-pass/systems"' in campaign_body

    assert systems.status_code == 200
    body = systems.get_data(as_text=True)
    assert "RULES" in body
    assert "Character Rules Reference" in body
    assert "PHB" in body
    assert "Player&#39;s Handbook (2014)" in body
    assert "Xanathar&#39;s Guide to Everything" in body
    assert "Wayfarer&#39;s Guide to Eberron" not in body
    assert "DMG" not in body
    assert "MM" not in body


def test_dm_can_open_systems_control_panel_and_visibility_panel_shows_systems_scope(
    client, sign_in, users
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    visibility_panel = client.get("/campaigns/linden-pass/control-panel")
    systems_panel = client.get("/campaigns/linden-pass/systems/control-panel")

    assert visibility_panel.status_code == 200
    visibility_html = visibility_panel.get_data(as_text=True)
    assert "Systems" in visibility_html

    assert systems_panel.status_code == 200
    systems_html = systems_panel.get_data(as_text=True)
    assert "Systems Policy" in systems_html
    assert "Player&#39;s Handbook (2014)" in systems_html
    assert "Dungeon Master&#39;s Guide (2014)" in systems_html
    assert "Wayfarer&#39;s Guide to Eberron" not in systems_html
    assert "Proprietary-source acknowledgement" in systems_html
    assert 'class="checkbox-label"' in systems_html


def test_proprietary_source_cannot_be_made_public(client, sign_in, users, app):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    form_data = build_source_form(app)
    form_data["source_PHB_visibility"] = "public"

    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/sources",
        data=form_data,
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "cannot be made public" in response.get_data(as_text=True)


def test_player_cannot_open_dm_only_source_but_dm_can(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])
    blocked = client.get("/campaigns/linden-pass/systems/sources/DMG")
    assert blocked.status_code == 404

    client.post("/sign-out", follow_redirects=False)
    sign_in(users["dm"]["email"], users["dm"]["password"])
    allowed = client.get("/campaigns/linden-pass/systems/sources/DMG")
    assert allowed.status_code == 200
    assert "Dungeon Master&#39;s Guide (2014)" in allowed.get_data(as_text=True)


def test_dm_can_update_source_visibility_and_audit_event_is_written(client, sign_in, users, app):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    form_data = build_source_form(app)
    form_data["source_XGE_visibility"] = "dm"

    response = client.post(
        "/campaigns/linden-pass/systems/control-panel/sources",
        data=form_data,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Updated systems sources: XGE." in response.get_data(as_text=True)

    with app.app_context():
        service = app.extensions["systems_service"]
        state = service.get_campaign_source_state("linden-pass", "XGE")
        assert state is not None
        assert state.default_visibility == "dm"

        events = AuthStore().list_recent_audit_events(
            event_type="campaign_systems_source_updated",
            campaign_slug="linden-pass",
        )
        assert any(event.metadata.get("source_id") == "XGE" for event in events)


def test_builtin_rules_source_is_seeded_and_browsable_without_import(client, sign_in, users, app):
    with app.app_context():
        service = app.extensions["systems_service"]
        state = service.get_campaign_source_state("linden-pass", "RULES")
        assert state is not None
        assert state.is_enabled is True
        entries = service.list_entries_for_campaign_source(
            "linden-pass",
            "RULES",
            entry_type="rule",
            limit=None,
        )
        titles = {entry.title for entry in entries}
        assert "Ability Scores and Ability Modifiers" in titles
        assert "Spell Attacks and Save DCs" in titles
        attunement_entry = next(
            entry for entry in entries if entry.title == "Equipped Items, Inventory, and Attunement"
        )

    sign_in(users["party"]["email"], users["party"]["password"])

    source_response = client.get("/campaigns/linden-pass/systems/sources/RULES")
    category_response = client.get("/campaigns/linden-pass/systems/sources/RULES/types/rule")
    search_response = client.get("/campaigns/linden-pass/systems/search?q=attunement")
    detail_response = client.get(f"/campaigns/linden-pass/systems/entries/{attunement_entry.slug}")

    assert source_response.status_code == 200
    source_body = source_response.get_data(as_text=True)
    assert "Character Rules Reference" in source_body
    assert "Browse This Source" in source_body
    assert "Rules" in source_body

    assert category_response.status_code == 200
    category_body = category_response.get_data(as_text=True)
    assert "Ability Scores and Ability Modifiers" in category_body
    assert "Armor Class" in category_body
    assert "Equipped Items, Inventory, and Attunement" in category_body

    assert search_response.status_code == 200
    search_body = search_response.get_data(as_text=True)
    assert "Equipped Items, Inventory, and Attunement" in search_body
    assert "RULES | Rules" in search_body

    assert detail_response.status_code == 200
    detail_body = detail_response.get_data(as_text=True)
    assert "attunement is a separate state with a normal limit of 3 items" in detail_body
    assert "Inventory Versus Equipment" in detail_body
