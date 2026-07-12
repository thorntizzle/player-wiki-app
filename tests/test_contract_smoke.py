from __future__ import annotations

from itertools import product

import pytest

from player_wiki.auth import role_satisfies_visibility
from player_wiki.campaign_visibility import VISIBILITY_ORDER, most_private_visibility
from player_wiki.combat_models import COMBAT_SOURCE_KIND_DM_STATBLOCK
from player_wiki.db import get_db
from tests.sample_data import ASSIGNED_CHARACTER_SLUG, TEST_CAMPAIGN_SLUG, TEST_CAMPAIGN_TITLE


pytestmark = pytest.mark.contract

PUBLIC_WIKI_PATH = "/campaigns/linden-pass/pages/notes/operations-brief"
CHARACTER_API_PATH = f"/api/v1/campaigns/linden-pass/characters/{ASSIGNED_CHARACTER_SLUG}"


def _assert_no_active_markup(rendered_html: str) -> None:
    lowered = rendered_html.lower()
    for forbidden in (
        "<script",
        "<svg",
        "onerror",
        "onload",
        "onclick",
        'href="javascript:',
        "href='javascript:",
        'src="javascript:',
        "src='javascript:",
    ):
        assert forbidden not in lowered


def test_role_visibility_truth_table_and_campaign_privacy_floor() -> None:
    roles = (None, "observer", "outsider", "player", "dm", "admin")
    visibility_states = tuple(VISIBILITY_ORDER)
    expected_allowed_roles = {
        "public": set(roles),
        "players": {"player", "dm"},
        "dm": {"dm"},
        "private": set(),
    }

    for role, visibility in product(roles, visibility_states):
        assert role_satisfies_visibility(role, visibility) is (
            role in expected_allowed_roles[visibility]
        )

    for campaign_visibility, scope_visibility in product(visibility_states, repeat=2):
        expected = max(
            (campaign_visibility, scope_visibility),
            key=VISIBILITY_ORDER.__getitem__,
        )
        assert most_private_visibility(campaign_visibility, scope_visibility) == expected


def test_anonymous_public_auth_and_missing_campaign_contract(client) -> None:
    health = client.get("/healthz")
    liveness = client.get("/livez")
    readiness = client.get("/readyz")
    root = client.get("/", follow_redirects=False)

    assert health.status_code == 200
    assert health.get_json()["status"] == "ok"
    assert liveness.status_code == 200
    assert liveness.get_json() == {"status": "ok"}
    assert readiness.status_code == 200
    assert readiness.get_json()["status"] == "ready"
    assert root.status_code == 302
    assert root.headers["Location"].endswith(f"/campaigns/{TEST_CAMPAIGN_SLUG}")

    for path, expected_text in (
        ("/campaigns", TEST_CAMPAIGN_TITLE),
        (f"/campaigns/{TEST_CAMPAIGN_SLUG}", TEST_CAMPAIGN_TITLE),
        (PUBLIC_WIKI_PATH, "Operations Brief"),
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert expected_text in response.get_data(as_text=True)

    for retired_path in (
        "/app-next",
        "/app-next/",
        "/app-next/assets/app.js",
        "/app-next/campaigns/linden-pass",
    ):
        assert client.get(retired_path).status_code == 404

    browser_auth = client.get("/account", follow_redirects=False)
    assert browser_auth.status_code == 302
    assert "/sign-in?next=/account" in browser_auth.headers["Location"]

    for api_path in ("/api/v1/me", "/api/v1/admin"):
        response = client.get(api_path)
        assert response.status_code == 401
        assert response.get_json()["error"]["code"] == "auth_required"

    assert client.get("/api/v1/campaigns/missing-campaign").status_code == 404


def test_representative_read_routes_and_role_boundaries(
    client,
    sign_in,
    users,
    set_campaign_visibility,
) -> None:
    representative_reads = {
        "campaign": f"/campaigns/{TEST_CAMPAIGN_SLUG}",
        "wiki": PUBLIC_WIKI_PATH,
        "systems": f"/campaigns/{TEST_CAMPAIGN_SLUG}/systems",
        "session": f"/campaigns/{TEST_CAMPAIGN_SLUG}/session",
        "combat": f"/campaigns/{TEST_CAMPAIGN_SLUG}/combat",
        "characters": f"/campaigns/{TEST_CAMPAIGN_SLUG}/characters",
        "dm_content": f"/campaigns/{TEST_CAMPAIGN_SLUG}/dm-content",
    }
    expected_by_actor = {
        "observer": {"campaign": 200, "wiki": 200},
        "outsider": {"campaign": 200, "wiki": 200},
        "owner": {
            "campaign": 200,
            "wiki": 200,
            "systems": 200,
            "session": 200,
            "combat": 200,
        },
        "party": {
            "campaign": 200,
            "wiki": 200,
            "systems": 200,
            "session": 200,
            "combat": 200,
        },
        "dm": {name: 200 for name in representative_reads},
        "admin": {name: 200 for name in representative_reads},
    }

    for actor in ("observer", "outsider", "owner", "party", "dm", "admin"):
        sign_in(users[actor]["email"], users[actor]["password"])
        actor_expected = expected_by_actor[actor]
        for surface, path in representative_reads.items():
            assert client.get(path, follow_redirects=True).status_code == actor_expected.get(surface, 404), (
                actor,
                surface,
            )

    sign_in(users["owner"]["email"], users["owner"]["password"])
    assert client.get(CHARACTER_API_PATH).status_code == 200
    assert client.get(
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/session/character",
        query_string={"character": ASSIGNED_CHARACTER_SLUG},
    ).status_code == 200

    sign_in(users["party"]["email"], users["party"]["password"])
    assert client.get(CHARACTER_API_PATH).status_code == 403
    assert client.get(
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/session/character",
        query_string={"character": ASSIGNED_CHARACTER_SLUG},
    ).status_code == 403

    management_reads = (
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/session/dm",
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/combat/dm",
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/dm-content",
        f"/api/v1/campaigns/{TEST_CAMPAIGN_SLUG}/dm-content",
    )
    for actor in ("dm", "admin"):
        sign_in(users[actor]["email"], users[actor]["password"])
        for path in management_reads:
            assert client.get(path).status_code == 200, (actor, path)

    sign_in(users["party"]["email"], users["party"]["password"])
    for path in management_reads:
        assert client.get(path).status_code in {403, 404}, path
    assert client.get("/admin").status_code == 403
    assert client.get("/api/v1/admin").status_code == 403

    set_campaign_visibility(TEST_CAMPAIGN_SLUG, campaign="private", wiki="public")
    assert client.get(f"/campaigns/{TEST_CAMPAIGN_SLUG}").status_code == 404
    assert client.get(PUBLIC_WIKI_PATH).status_code == 404

    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.get(f"/campaigns/{TEST_CAMPAIGN_SLUG}").status_code == 404

    sign_in(users["admin"]["email"], users["admin"]["password"])
    assert client.get("/admin").status_code == 200
    assert client.get("/api/v1/admin").status_code == 200
    assert client.get(f"/campaigns/{TEST_CAMPAIGN_SLUG}").status_code == 200
    assert client.get(PUBLIC_WIKI_PATH).status_code == 200


def test_global_search_preview_sanitizes_legacy_stored_rich_text(app, client) -> None:
    searchable_marker = "legacy-search-sentinel"
    legacy_body = f"""
## Legacy Search Result

<strong>Allowed search emphasis</strong>

<script>window.searchPwned = true</script>
<img src=x onerror="window.searchPwned = true">
<svg onload="window.searchPwned = true"></svg>
<a href="javascript:window.searchPwned=true" onclick="window.searchPwned=true">danger link</a>

{searchable_marker}
"""

    with app.app_context():
        repository = app.extensions["repository_store"].get()
        campaign = repository.get_campaign(TEST_CAMPAIGN_SLUG)
        assert campaign is not None

        page_store = app.extensions["campaign_page_store"]
        source_record = next(
            record
            for record in page_store.list_page_records(TEST_CAMPAIGN_SLUG)
            if record.page.route_slug == "notes/operations-brief"
        )
        connection = get_db()
        connection.execute(
            """
            UPDATE campaign_pages
            SET body_markdown = ?, searchable_text = searchable_text || ?
            WHERE campaign_slug = ? AND page_ref = ?
            """,
            (legacy_body, f" {searchable_marker}", TEST_CAMPAIGN_SLUG, source_record.page_ref),
        )
        connection.commit()

        page = campaign.get_visible_page("notes/operations-brief")
        assert page is not None
        page.body_markdown = ""
        page.body_html = ""
        page.content_loaded = False
        page.html_loaded = False

        matching_records = page_store.search_page_records(
            TEST_CAMPAIGN_SLUG,
            searchable_marker,
        )
        assert [record.page_ref for record in matching_records] == [source_record.page_ref]

    search_response = client.get(
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/global-search?q={searchable_marker}"
    )
    assert search_response.status_code == 200
    results = search_response.get_json()["results"]
    wiki_result = next(result for result in results if result["kind"] == "wiki")

    preview_response = client.get(
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/global-search/preview",
        query_string={"result_id": wiki_result["result_id"]},
    )
    assert preview_response.status_code == 200
    preview_html = preview_response.get_json()["preview_html"]
    assert "<strong>Allowed search emphasis</strong>" in preview_html
    assert "danger link" in preview_html
    _assert_no_active_markup(preview_html)


def test_combat_status_sanitizes_legacy_dm_statblock_rich_text(app, client, sign_in, users) -> None:
    legacy_body = """
## Legacy Combat Source

<strong>Allowed combat emphasis</strong>

<script>window.combatPwned = true</script>
<img src=x onerror="window.combatPwned = true">
<svg onload="window.combatPwned = true"></svg>
<a href="javascript:window.combatPwned=true" onclick="window.combatPwned=true">danger combat link</a>
"""

    with app.app_context():
        statblock = app.extensions["campaign_dm_content_store"].create_statblock(
            TEST_CAMPAIGN_SLUG,
            title="Legacy Script Hound",
            body_markdown=legacy_body,
            source_filename="legacy-script-hound.md",
            subsection="",
            armor_class=14,
            max_hp=22,
            speed_text="30 ft.",
            movement_total=30,
            initiative_bonus=2,
            created_by_user_id=users["dm"]["id"],
        )
        combatant = app.extensions["campaign_combat_service"].add_npc_combatant(
            TEST_CAMPAIGN_SLUG,
            display_name=statblock.title,
            turn_value=statblock.initiative_bonus,
            initiative_bonus=statblock.initiative_bonus,
            current_hp=statblock.max_hp,
            max_hp=statblock.max_hp,
            movement_total=statblock.movement_total,
            source_kind=COMBAT_SOURCE_KIND_DM_STATBLOCK,
            source_ref=str(statblock.id),
            created_by_user_id=users["dm"]["id"],
        )

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get(
        f"/campaigns/{TEST_CAMPAIGN_SLUG}/combat/status/live-state",
        query_string={"combatant": combatant.id},
    )

    assert response.status_code == 200
    rendered_html = response.get_json()["detail_html"]
    assert "DM Content statblock detail" in rendered_html
    assert "<strong>Allowed combat emphasis</strong>" in rendered_html
    assert "danger combat link" in rendered_html
    _assert_no_active_markup(rendered_html)
