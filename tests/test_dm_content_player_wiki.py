from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
import yaml
from PIL import Image

from player_wiki import publishing_mutations
from player_wiki.campaign_content_service import CampaignContentError, get_campaign_page_file, write_campaign_page_file


TEST_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xd9\x8f\x9b"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def assert_webp_bytes(data_blob: bytes) -> None:
    assert data_blob[:4] == b"RIFF"
    assert data_blob[8:12] == b"WEBP"


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


def _campaign_asset_path(app, asset_ref: str) -> Path:
    return (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / "linden-pass"
        / "assets"
        / Path(*asset_ref.split("/"))
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


def test_player_wiki_image_can_remain_when_page_write_fails(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    def fail_page_write(*args, **kwargs):
        raise CampaignContentError("characterized page write failure")

    monkeypatch.setattr(publishing_mutations, "write_campaign_page_file", fail_page_write)
    response = client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages",
        data={
            **_page_form(slug_leaf="orphaned-image"),
            "image_file": (BytesIO(TEST_PNG_BYTES), "orphaned-image.png"),
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "characterized page write failure" in response.get_data(as_text=True)
    assert _campaign_asset_path(app, "wiki-pages/notes/orphaned-image.webp").exists()
    assert not _campaign_page_path(app, "notes/orphaned-image").exists()


def test_player_wiki_existing_asset_can_be_overwritten_when_page_update_fails(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    created = client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages",
        data={
            **_page_form(slug_leaf="overwritten-image"),
            "image_file": (BytesIO(TEST_PNG_BYTES), "overwritten-image.png"),
        },
        follow_redirects=False,
    )
    assert created.status_code == 302
    asset_path = _campaign_asset_path(app, "wiki-pages/notes/overwritten-image.webp")
    page_path = _campaign_page_path(app, "notes/overwritten-image")
    original_asset = asset_path.read_bytes()
    original_page = page_path.read_text(encoding="utf-8")

    def fail_page_write(*args, **kwargs):
        raise CampaignContentError("characterized update page write failure")

    monkeypatch.setattr(publishing_mutations, "write_campaign_page_file", fail_page_write)
    replacement_image = BytesIO()
    Image.new("RGB", (2, 2), (0, 0, 255)).save(replacement_image, format="PNG")
    replacement_image.seek(0)
    response = client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages/notes/overwritten-image",
        data={
            **_page_form(title="Unsaved update", slug_leaf="ignored-on-edit"),
            "image_file": (replacement_image, "replacement.png"),
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert asset_path.read_bytes() != original_asset
    assert page_path.read_text(encoding="utf-8") == original_page


def test_page_service_rolls_back_database_and_restores_existing_markdown_on_write_failure(
    app,
    monkeypatch,
):
    original = _write_campaign_page(
        app,
        "notes/rollback-boundary",
        metadata={
            "title": "Rollback Boundary",
            "slug": "notes/rollback-boundary",
            "section": "Notes",
            "type": "note",
            "published": True,
        },
        body_markdown="Original durable body.",
    )
    page_path = _campaign_page_path(app, original.page_ref)
    original_text = page_path.read_text(encoding="utf-8")
    original_write_text = Path.write_text
    failed_once = False

    def fail_after_overwriting_markdown(path, data, *args, **kwargs):
        nonlocal failed_once
        result = original_write_text(path, data, *args, **kwargs)
        if path == page_path and "Should Roll Back" in data and not failed_once:
            failed_once = True
            raise RuntimeError("characterized Markdown write failure")
        return result

    monkeypatch.setattr(Path, "write_text", fail_after_overwriting_markdown)

    with app.app_context():
        repository = app.extensions["repository_store"].get()
        campaign = repository.get_campaign("linden-pass")
        page_store = app.extensions["campaign_page_store"]
        with pytest.raises(RuntimeError, match="characterized Markdown write failure"):
            write_campaign_page_file(
                campaign,
                original.page_ref,
                metadata={**original.metadata, "title": "Should Roll Back"},
                body_markdown="This body must not survive.",
                page_store=page_store,
            )

        restored = get_campaign_page_file(campaign, original.page_ref, page_store=page_store)

    assert page_path.read_text(encoding="utf-8") == original_text
    assert restored is not None
    assert restored.page.title == "Rollback Boundary"
    assert restored.body_markdown == "Original durable body."


def test_repository_refresh_failure_occurs_after_durable_player_wiki_write(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    def fail_refresh():
        raise RuntimeError("characterized repository refresh failure")

    monkeypatch.setattr(app.extensions["repository_store"], "refresh", fail_refresh)
    with pytest.raises(RuntimeError, match="characterized repository refresh failure"):
        client.post(
            "/campaigns/linden-pass/dm-content/player-wiki/pages",
            data=_page_form(slug_leaf="refresh-failure"),
            follow_redirects=False,
        )

    assert _campaign_page_path(app, "notes/refresh-failure").exists()
    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        record = get_campaign_page_file(
            campaign,
            "notes/refresh-failure",
            page_store=app.extensions["campaign_page_store"],
        )
    assert record is not None
    assert record.page.title == "Field Report"


def test_audit_failure_occurs_after_durable_write_and_repository_refresh(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    def fail_audit(**kwargs):
        raise RuntimeError("characterized audit failure")

    monkeypatch.setattr(app.extensions["auth_store"], "write_audit_event", fail_audit)
    with pytest.raises(RuntimeError, match="characterized audit failure"):
        client.post(
            "/campaigns/linden-pass/dm-content/player-wiki/pages",
            data=_page_form(slug_leaf="audit-failure"),
            follow_redirects=False,
        )

    assert _campaign_page_path(app, "notes/audit-failure").exists()
    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign.pages["notes/audit-failure"].title == "Field Report"


def test_dm_content_player_wiki_subpage_is_hidden_from_players(client, sign_in, users):
    sign_in(users["party"]["email"], users["party"]["password"])

    response = client.get("/campaigns/linden-pass/dm-content/player-wiki")

    assert response.status_code == 404


def test_player_wiki_content_api_rejects_deprecated_overview_targets(client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    deprecated_writes = [
        (
            "/api/v1/campaigns/linden-pass/content/pages/overview/deprecated-guide",
            {
                "title": "Deprecated Guide",
                "section": "Overview",
                "type": "page",
                "summary": "This legacy section should no longer be created.",
            },
        ),
        (
            "/api/v1/campaigns/linden-pass/content/pages/notes/deprecated-guide",
            {
                "title": "Deprecated Guide",
                "section": "Notes",
                "type": "overview",
                "summary": "This legacy page type should no longer be created.",
            },
        ),
    ]

    for path, metadata in deprecated_writes:
        response = client.put(
            path,
            json={
                "metadata": metadata,
                "body_markdown": "Legacy overview content.",
            },
        )

        assert response.status_code == 400
        payload = response.get_json()
        assert payload["error"]["code"] == "validation_error"
        assert "Overview wiki pages are deprecated" in payload["error"]["message"]


def test_dm_browser_write_routes_reject_players_when_scopes_are_visible(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
):
    set_campaign_visibility(
        "linden-pass",
        dm_content="players",
        systems="players",
        session="players",
    )
    sign_in(users["party"]["email"], users["party"]["password"])

    visible_dm_content = client.get("/campaigns/linden-pass/dm-content")
    assert visible_dm_content.status_code == 200

    wiki_create = client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages",
        data=_page_form(slug_leaf="blocked-player-wiki-write"),
        follow_redirects=False,
    )
    statblock_upload = client.post(
        "/campaigns/linden-pass/dm-content/statblocks",
        data={
            "statblock_file": (
                BytesIO(b"Armor Class 12\nHit Points 7\nSpeed 30 ft."),
                "blocked.md",
            )
        },
        follow_redirects=False,
    )
    staged_article_create = client.post(
        "/campaigns/linden-pass/dm-content/staged-articles",
        data={
            "article_mode": "manual",
            "title": "Blocked Article",
            "body_markdown": "Players should not be able to stage DM prep.",
        },
        follow_redirects=False,
    )
    condition_create = client.post(
        "/campaigns/linden-pass/dm-content/conditions",
        data={
            "name": "Blocked Condition",
            "description_markdown": "Players should not be able to author DM conditions.",
        },
        follow_redirects=False,
    )
    systems_override = client.post(
        "/campaigns/linden-pass/systems/control-panel/overrides",
        data={
            "return_to": "dm-content-systems",
            "entry_key": "dnd-5e|spell|phb|blocked",
            "visibility_override": "dm",
            "is_enabled_override": "disabled",
        },
        follow_redirects=False,
    )
    custom_systems_entry = client.post(
        "/campaigns/linden-pass/systems/control-panel/custom-entries",
        data={
            "return_to": "dm-content-systems",
            "custom_entry_title": "Blocked Spark",
            "custom_entry_slug": "blocked-spark",
            "custom_entry_type": "spell",
            "custom_entry_visibility": "players",
            "custom_entry_body_markdown": "This should not save.",
        },
        follow_redirects=False,
    )

    assert wiki_create.status_code == 403
    assert statblock_upload.status_code == 403
    assert staged_article_create.status_code == 403
    assert condition_create.status_code == 403
    assert systems_override.status_code == 403
    assert custom_systems_entry.status_code == 403

    assert not _campaign_page_path(app, "notes/blocked-player-wiki-write").exists()
    with app.app_context():
        assert app.extensions["campaign_dm_content_service"].list_statblocks("linden-pass") == []
        assert app.extensions["campaign_dm_content_service"].list_condition_definitions("linden-pass") == []
        assert app.extensions["campaign_session_service"].list_articles("linden-pass") == []
        assert (
            app.extensions["systems_service"].get_custom_campaign_entry_by_slug(
                "linden-pass",
                "custom-linden-pass-blocked-spark",
            )
            is None
        )


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


def test_dm_can_upload_player_wiki_page_image_from_dm_content(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_response = client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages",
        data={
            **_page_form(
                image_alt="Uploaded field report image.",
                image_caption="A browser-uploaded image attached to the field report.",
            ),
            "image_file": (BytesIO(TEST_PNG_BYTES), "field-report.png"),
        },
        follow_redirects=False,
    )

    assert create_response.status_code == 302
    asset_ref = "wiki-pages/notes/field-report.webp"
    asset_path = _campaign_asset_path(app, asset_ref)
    assert_webp_bytes(asset_path.read_bytes())

    page_path = _campaign_page_path(app, "notes/field-report")
    raw_text = page_path.read_text(encoding="utf-8")
    metadata = yaml.safe_load(raw_text.split("---", 2)[1])
    assert metadata["image"] == asset_ref
    assert metadata["image_alt"] == "Uploaded field report image."
    assert metadata["image_caption"] == "A browser-uploaded image attached to the field report."

    published_page = client.get("/campaigns/linden-pass/pages/notes/field-report")
    published_html = published_page.get_data(as_text=True)
    assert published_page.status_code == 200
    assert "/campaigns/linden-pass/assets/wiki-pages/notes/field-report.webp" in published_html
    assert "Uploaded field report image." in published_html
    assert "A browser-uploaded image attached to the field report." in published_html

    asset_response = client.get("/campaigns/linden-pass/assets/wiki-pages/notes/field-report.webp")
    assert asset_response.status_code == 200
    assert_webp_bytes(asset_response.data)


def test_dm_can_promote_session_article_through_player_wiki_editor(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    create_article = client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Courier Seal Editor",
            "body_markdown": "This note should be reviewed in the wiki editor before publication.",
            "image_alt": "A stamped courier seal.",
            "image_caption": "Shown to the party after the reveal.",
            "image_file": (BytesIO(TEST_PNG_BYTES), "courier-seal-editor.png"),
        },
        follow_redirects=False,
    )

    assert create_article.status_code == 302
    with app.app_context():
        article = app.extensions["campaign_session_service"].list_articles("linden-pass")[0]
    editor_path = f"/campaigns/linden-pass/dm-content/player-wiki/session-articles/{article.id}/new"

    staged_page = client.get("/campaigns/linden-pass/dm-content/staged-articles")
    staged_html = staged_page.get_data(as_text=True)
    assert staged_page.status_code == 200
    assert editor_path in staged_html
    assert "Open in Player Wiki editor" in staged_html

    session_dm_page = client.get("/campaigns/linden-pass/session/dm")
    session_dm_html = session_dm_page.get_data(as_text=True)
    assert session_dm_page.status_code == 200
    assert editor_path in session_dm_html

    editor_page = client.get(editor_path)
    editor_html = editor_page.get_data(as_text=True)
    assert editor_page.status_code == 200
    assert "Create wiki page from session article" in editor_html
    assert 'name="source_session_article_id"' in editor_html
    assert f'value="{article.id}"' in editor_html
    assert 'value="session-article:linden-pass:' in editor_html
    assert "Courier Seal Editor" in editor_html
    assert "This note should be reviewed in the wiki editor before publication." in editor_html
    assert "A stamped courier seal." in editor_html

    create_page = client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages",
        data=_page_form(
            title="Courier Seal Editor",
            slug_leaf="courier-seal-editor",
            section="Notes",
            page_type="note",
            subsection="Session Handouts",
            summary="A staged handout reviewed through the Player Wiki editor.",
            aliases="Courier Seal",
            reveal_after_session="2",
            source_ref="session-article:linden-pass:edited-by-form",
            image="",
            image_alt="A stamped courier seal.",
            image_caption="Shown to the party after the reveal.",
            body_markdown="## Description\n\nReviewed copy for the durable player reference.",
            source_session_article_id=str(article.id),
        ),
        follow_redirects=False,
    )

    assert create_page.status_code == 302
    assert "/dm-content/player-wiki/pages/notes/courier-seal-editor/edit" in create_page.headers["Location"]

    asset_ref = "wiki-pages/notes/courier-seal-editor.webp"
    asset_path = _campaign_asset_path(app, asset_ref)
    assert_webp_bytes(asset_path.read_bytes())

    page_path = _campaign_page_path(app, "notes/courier-seal-editor")
    raw_text = page_path.read_text(encoding="utf-8")
    metadata = yaml.safe_load(raw_text.split("---", 2)[1])
    assert metadata["title"] == "Courier Seal Editor"
    assert metadata["source_ref"] == f"session-article:linden-pass:{article.id}"
    assert metadata["image"] == asset_ref
    assert metadata["image_alt"] == "A stamped courier seal."
    assert metadata["image_caption"] == "Shown to the party after the reveal."
    assert "Reviewed copy for the durable player reference." in raw_text

    published_page = client.get("/campaigns/linden-pass/pages/notes/courier-seal-editor")
    assert published_page.status_code == 200
    published_html = published_page.get_data(as_text=True)
    assert "/campaigns/linden-pass/assets/wiki-pages/notes/courier-seal-editor.webp" in published_html
    assert "Reviewed copy for the durable player reference." in published_html

    already_converted = client.get(editor_path, follow_redirects=False)
    assert already_converted.status_code == 302
    assert "/dm-content/player-wiki/pages/notes/courier-seal-editor/edit" in already_converted.headers["Location"]


def test_dm_player_wiki_image_upload_rejects_unsupported_files(app, client, sign_in, users):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    response = client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages",
        data={
            **_page_form(slug_leaf="bad-image"),
            "image_file": (BytesIO(b"not an image"), "bad-image.txt"),
        },
    )

    assert response.status_code == 400
    assert "Wiki page images must be PNG, JPG, GIF, or WEBP files." in response.get_data(as_text=True)
    assert not _campaign_page_path(app, "notes/bad-image").exists()


def test_create_form_validation_precedes_invalid_image_validation_and_write(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    def fail_asset_write(*args, **kwargs):
        pytest.fail("compound-invalid create must not attempt an image write")

    monkeypatch.setattr(publishing_mutations, "write_campaign_asset_file", fail_asset_write)
    response = client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages",
        data={
            **_page_form(
                title="Compound Invalid Create",
                slug_leaf="compound-invalid-create",
                section="Not A Wiki Section",
            ),
            "image_file": (BytesIO(b"not an image"), "invalid.txt"),
        },
        follow_redirects=False,
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 400
    assert "Choose a supported wiki section." in body
    assert "Wiki page images must be PNG, JPG, GIF, or WEBP files." not in body
    assert 'value="Compound Invalid Create"' in body
    assert not _campaign_page_path(app, "notes/compound-invalid-create").exists()


def test_update_form_validation_precedes_invalid_image_validation_and_write(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    created = client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages",
        data=_page_form(slug_leaf="compound-invalid-update"),
        follow_redirects=False,
    )
    assert created.status_code == 302
    page_path = _campaign_page_path(app, "notes/compound-invalid-update")
    original_page = page_path.read_text(encoding="utf-8")

    def fail_asset_write(*args, **kwargs):
        pytest.fail("compound-invalid update must not attempt an image write")

    monkeypatch.setattr(publishing_mutations, "write_campaign_asset_file", fail_asset_write)
    response = client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages/notes/compound-invalid-update",
        data={
            **_page_form(
                title="Compound Invalid Update",
                slug_leaf="ignored-on-edit",
                display_order="not-a-number",
            ),
            "image_file": (BytesIO(b"not an image"), "invalid.txt"),
        },
        follow_redirects=False,
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 400
    assert "Display order must be a whole number." in body
    assert "Wiki page images must be PNG, JPG, GIF, or WEBP files." not in body
    assert 'value="Compound Invalid Update"' in body
    assert page_path.read_text(encoding="utf-8") == original_page


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

    refreshed_page = client.get("/campaigns/linden-pass/pages/notes/field-report")
    refreshed_html = refreshed_page.get_data(as_text=True)
    assert refreshed_page.status_code == 200
    assert "Updated Field Report" in refreshed_html
    assert "Updated browser-authored text." in refreshed_html
    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign is not None
        assert campaign.pages["notes/field-report"].title == "Updated Field Report"

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
