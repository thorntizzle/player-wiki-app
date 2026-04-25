from __future__ import annotations

from pathlib import Path

import yaml

from player_wiki.campaign_content_service import write_campaign_page_file


def _page_form(**overrides):
    payload = {
        "title": "Field Report",
        "slug_leaf": "field-report",
        "section": "Notes",
        "page_type": "note",
        "subsection": "Session Handouts",
        "summary": "A player-facing field report created in the browser.",
        "aliases": "Relay Report\nSignal Report",
        "display_order": "10000",
        "reveal_after_session": "0",
        "source_ref": "browser://dm-content/player-wiki",
        "image": "",
        "image_alt": "",
        "image_caption": "",
        "body_markdown": "## Description\n\nThe relay is stable enough for public notes.",
        "published": "1",
    }
    payload.update(overrides)
    return payload


def _campaign_page_path(app, page_ref: str) -> Path:
    return (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / "linden-pass"
        / "content"
        / f"{page_ref}.md"
    )


def _write_campaign_page(app, page_ref: str, *, metadata: dict[str, object], body_markdown: str):
    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign is not None
        record = write_campaign_page_file(
            campaign,
            page_ref,
            metadata=metadata,
            body_markdown=body_markdown,
            page_store=app.extensions["campaign_page_store"],
        )
        app.extensions["repository_store"].refresh()
        return record


def test_dm_content_player_wiki_subpage_is_hidden_from_players(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.get("/campaigns/linden-pass/dm-content/player-wiki")

    assert response.status_code == 404


def test_dm_can_create_player_wiki_page_from_dm_content(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    landing = client.get("/campaigns/linden-pass/dm-content/player-wiki")
    assert landing.status_code == 200
    landing_body = landing.get_data(as_text=True)
    assert "Player Wiki" in landing_body
    assert "Create player wiki page" in landing_body
    assert "Operations Brief" in landing_body

    create_response = client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages",
        data=_page_form(),
        follow_redirects=False,
    )

    assert create_response.status_code == 302
    assert "/dm-content/player-wiki/pages/notes/field-report/edit" in create_response.headers["Location"]

    page_path = _campaign_page_path(app, "notes/field-report")
    assert page_path.exists()
    raw_text = page_path.read_text(encoding="utf-8")
    metadata = yaml.safe_load(raw_text.split("---", 2)[1])
    assert metadata["title"] == "Field Report"
    assert metadata["aliases"] == ["Relay Report", "Signal Report"]
    assert "The relay is stable" in raw_text

    published_page = client.get("/campaigns/linden-pass/pages/notes/field-report")
    assert published_page.status_code == 200
    assert "Field Report" in published_page.get_data(as_text=True)

    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign is not None
        assert campaign.pages["notes/field-report"].title == "Field Report"


def test_dm_can_update_unpublish_and_delete_player_wiki_page(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages",
        data=_page_form(),
        follow_redirects=False,
    )

    update_response = client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages/notes/field-report",
        data=_page_form(
            title="Updated Field Report",
            slug_leaf="ignored-on-edit",
            summary="Updated player-facing summary.",
            body_markdown="## Description\n\nUpdated browser-authored text.",
        ),
        follow_redirects=False,
    )

    assert update_response.status_code == 302
    page_path = _campaign_page_path(app, "notes/field-report")
    raw_text = page_path.read_text(encoding="utf-8")
    assert "Updated Field Report" in raw_text
    assert "Updated browser-authored text." in raw_text
    assert page_path.name == "field-report.md"

    unpublish_response = client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages/notes/field-report/unpublish",
        follow_redirects=True,
    )

    assert unpublish_response.status_code == 200
    assert "Unpublished wiki page Updated Field Report." in unpublish_response.get_data(as_text=True)
    hidden_page = client.get("/campaigns/linden-pass/pages/notes/field-report")
    assert hidden_page.status_code == 404
    assert page_path.exists()

    blocked_delete = client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages/notes/field-report/delete",
        data={},
        follow_redirects=True,
    )

    assert blocked_delete.status_code == 200
    assert "Confirm hard delete before removing a wiki page file." in blocked_delete.get_data(as_text=True)
    assert page_path.exists()

    delete_response = client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages/notes/field-report/delete",
        data={"confirm_delete": "1"},
        follow_redirects=True,
    )

    assert delete_response.status_code == 200
    assert "Deleted wiki page Updated Field Report." in delete_response.get_data(as_text=True)
    assert not page_path.exists()
    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign is not None
        assert "notes/field-report" not in campaign.pages


def test_dm_hard_delete_blocks_player_wiki_page_with_backlinks(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages",
        data=_page_form(),
        follow_redirects=False,
    )
    client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages",
        data=_page_form(
            title="Followup Note",
            slug_leaf="followup-note",
            summary="A note that links back to the field report.",
            body_markdown="## Description\n\nReview [[Field Report]] before closing the job.",
        ),
        follow_redirects=False,
    )

    landing = client.get("/campaigns/linden-pass/dm-content/player-wiki")
    landing_body = landing.get_data(as_text=True)
    assert "Hard delete blocked" in landing_body
    assert "Backlinked from Followup Note." in landing_body

    page_path = _campaign_page_path(app, "notes/field-report")
    delete_response = client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages/notes/field-report/delete",
        data={"confirm_delete": "1"},
        follow_redirects=True,
    )

    assert delete_response.status_code == 200
    delete_body = delete_response.get_data(as_text=True)
    assert "Hard delete blocked. Unpublish/archive the page or remove:" in delete_body
    assert "Backlinked from Followup Note." in delete_body
    assert page_path.exists()


def test_dm_hard_delete_blocks_player_wiki_page_with_character_hooks_and_session_provenance(
    app,
    client,
    sign_in,
    users,
):
    _write_campaign_page(
        app,
        "mechanics/harbor-ritual-book",
        metadata={
            "title": "Harbor Ritual Book",
            "slug": "mechanics/harbor-ritual-book",
            "section": "Mechanics",
            "type": "mechanic",
            "summary": "A campaign mechanic that can feed character tools.",
            "source_ref": "session-article:linden-pass:99",
            "published": True,
            "character_option": {
                "kind": "feature",
                "name": "Harbor Ritual Book",
            },
        },
        body_markdown="## Description\n\nA reference page with character-facing hooks.",
    )
    sign_in(users["dm"]["email"], users["dm"]["password"])

    landing = client.get("/campaigns/linden-pass/dm-content/player-wiki")
    landing_body = landing.get_data(as_text=True)
    assert "Harbor Ritual Book" in landing_body
    assert "Character hooks: character option metadata." in landing_body
    assert "Session provenance: converted session article." in landing_body

    page_path = _campaign_page_path(app, "mechanics/harbor-ritual-book")
    delete_response = client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages/mechanics/harbor-ritual-book/delete",
        data={"confirm_delete": "1"},
        follow_redirects=True,
    )

    assert delete_response.status_code == 200
    delete_body = delete_response.get_data(as_text=True)
    assert "Hard delete blocked. Unpublish/archive the page or remove:" in delete_body
    assert "Character hooks: character option metadata." in delete_body
    assert "Session provenance: converted session article." in delete_body
    assert page_path.exists()
