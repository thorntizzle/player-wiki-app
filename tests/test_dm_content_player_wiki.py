from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from threading import Event

import pytest
import yaml
from PIL import Image

from player_wiki import (
    file_publication,
    publishing_mutations,
    publishing_routes,
    session_article_publisher,
)
from player_wiki.campaign_content_service import CampaignContentError, get_campaign_page_file, write_campaign_page_file
from player_wiki.db import get_db
from player_wiki.player_wiki_reconciliation import ReconciliationHooks
from player_wiki.session_article_publisher import (
    SessionArticlePublishError,
    SessionArticlePublishOptions,
    publish_session_article,
)


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


def _html_article_by_id(html: str, element_id: str) -> str:
    id_offset = html.index(f'id="{element_id}"')
    article_start = html.rfind("<article", 0, id_offset)
    assert article_start >= 0
    article_end = html.index("</article>", id_offset) + len("</article>")
    return html[article_start:article_end]


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


def _mutation_dependencies(app):
    return publishing_mutations.PlayerWikiMutationDependencies(
        page_store=app.extensions["campaign_page_store"],
        session_service=app.extensions["campaign_session_service"],
        character_repository=app.extensions["character_repository"],
        refresh_repository=lambda: app.extensions["repository_store"].refresh(),
        write_audit_event=app.extensions["auth_store"].write_audit_event,
        reconciler=app.extensions["player_wiki_reconciler"],
    )


def test_player_wiki_image_primary_crash_recovers_page_forward(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    reconciler = app.extensions["player_wiki_reconciler"]

    def crash_after_image(event, _operation_id):
        if event == "after_primary_publish":
            raise RuntimeError("characterized image-primary crash")

    reconciler.hooks = ReconciliationHooks(on_event=crash_after_image)
    with pytest.raises(RuntimeError, match="characterized image-primary crash"):
        client.post(
            "/campaigns/linden-pass/dm-content/player-wiki/pages",
            data={
                **_page_form(slug_leaf="orphaned-image"),
                "image_file": (BytesIO(TEST_PNG_BYTES), "orphaned-image.png"),
            },
            follow_redirects=False,
        )

    assert _campaign_asset_path(app, "wiki-pages/notes/orphaned-image.webp").exists()
    assert not _campaign_page_path(app, "notes/orphaned-image").exists()
    with app.app_context():
        row = get_db().execute(
            "SELECT primary_authority, state, desired_markdown FROM player_wiki_reconciliation_operations"
        ).fetchone()
        assert tuple(row[:2]) == ("image", "prepared")
        assert bytes(row["desired_markdown"])
        reconciler.hooks = ReconciliationHooks()
        assert reconciler.recover_pending()["recovered"] == 1
        assert get_db().execute(
            "SELECT COUNT(*) FROM player_wiki_reconciliation_operations"
        ).fetchone()[0] == 0
    assert _campaign_page_path(app, "notes/orphaned-image").exists()


def test_player_wiki_existing_asset_update_crash_recovers_markdown_forward(
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

    reconciler = app.extensions["player_wiki_reconciler"]

    def crash_after_image(event, _operation_id):
        if event == "after_primary_publish":
            raise RuntimeError("characterized update image-primary crash")

    reconciler.hooks = ReconciliationHooks(on_event=crash_after_image)
    replacement_image = BytesIO()
    Image.new("RGB", (2, 2), (0, 0, 255)).save(replacement_image, format="PNG")
    replacement_image.seek(0)
    with pytest.raises(RuntimeError, match="characterized update image-primary crash"):
        client.post(
            "/campaigns/linden-pass/dm-content/player-wiki/pages/notes/overwritten-image",
            data={
                **_page_form(title="Recovered update", slug_leaf="ignored-on-edit"),
                "image_file": (replacement_image, "replacement.png"),
            },
            follow_redirects=False,
        )

    assert asset_path.read_bytes() != original_asset
    assert page_path.read_text(encoding="utf-8") == original_page
    with app.app_context():
        reconciler.hooks = ReconciliationHooks()
        assert reconciler.recover_pending()["recovered"] == 1
    assert "title: Recovered update" in page_path.read_text(encoding="utf-8")


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
    original_replace = file_publication._replace_file
    failed_once = False

    def fail_before_replacing_markdown(source_path, destination_path):
        nonlocal failed_once
        if (
            destination_path == page_path
            and "Should Roll Back" in source_path.read_text(encoding="utf-8")
            and not failed_once
        ):
            failed_once = True
            raise RuntimeError("characterized Markdown write failure")
        return original_replace(source_path, destination_path)

    monkeypatch.setattr(file_publication, "_replace_file", fail_before_replacing_markdown)

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

    monkeypatch.setattr(
        app.extensions["repository_store"],
        "refresh_from_database",
        fail_refresh,
    )
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


def test_audit_failure_rolls_back_sqlite_then_recovers_exactly_once(
    app,
    client,
    sign_in,
    users,
    monkeypatch,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    original_insert = app.extensions["auth_store"].insert_audit_event

    def fail_audit(**kwargs):
        raise RuntimeError("characterized audit failure")

    monkeypatch.setattr(app.extensions["auth_store"], "insert_audit_event", fail_audit)
    with pytest.raises(RuntimeError, match="characterized audit failure"):
        client.post(
            "/campaigns/linden-pass/dm-content/player-wiki/pages",
            data=_page_form(slug_leaf="audit-failure"),
            follow_redirects=False,
        )

    assert _campaign_page_path(app, "notes/audit-failure").exists()
    with app.app_context():
        row = get_db().execute(
            "SELECT state, desired_markdown FROM player_wiki_reconciliation_operations"
        ).fetchone()
        assert row["state"] == "prepared"
        assert bytes(row["desired_markdown"])
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'campaign_wiki_page_created'"
        ).fetchone()[0] == 0
        monkeypatch.setattr(app.extensions["auth_store"], "insert_audit_event", original_insert)
        assert app.extensions["player_wiki_reconciler"].recover_pending()["recovered"] == 1
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'campaign_wiki_page_created'"
        ).fetchone()[0] == 1


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


def test_dm_player_wiki_management_search_retains_query_and_renders_result_states(
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    matching = client.get(
        "/campaigns/linden-pass/dm-content/player-wiki",
        query_string={"q": "Operations Brief"},
    )
    matching_html = matching.get_data(as_text=True)

    assert matching.status_code == 200
    assert 'name="q" value="Operations Brief"' in matching_html
    assert 'id="wiki-page-notes-operations-brief"' in matching_html
    assert "No player wiki pages matched that search." not in matching_html

    no_result = client.get(
        "/campaigns/linden-pass/dm-content/player-wiki",
        query_string={"q": "definitely-not-a-player-wiki-page"},
    )
    no_result_html = no_result.get_data(as_text=True)

    assert no_result.status_code == 200
    assert 'name="q" value="definitely-not-a-player-wiki-page"' in no_result_html
    assert 'id="wiki-page-notes-operations-brief"' not in no_result_html
    assert "No player wiki pages matched that search." in no_result_html


def test_player_wiki_get_forms_keep_native_actions_and_current_deep_links(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    create_action = "/campaigns/linden-pass/dm-content/player-wiki/pages"
    editor_anchor = "#dm-content-player-wiki-editor"
    staged_session_href = (
        "/campaigns/linden-pass/session/dm?dm_view=staged"
        "#session-staged-articles"
    )

    direct_create = client.get(
        "/campaigns/linden-pass/dm-content/player-wiki" + editor_anchor
    )
    direct_create_html = direct_create.get_data(as_text=True)
    assert direct_create.status_code == 200
    assert 'id="dm-content-player-wiki-editor"' in direct_create_html
    assert 'id="dm-content-player-wiki-pages"' in direct_create_html
    assert f'<form method="post" action="{create_action}"' in direct_create_html

    create_response = client.post(
        create_action,
        data=_page_form(slug_leaf="form-identity"),
        follow_redirects=False,
    )
    edit_path = (
        "/campaigns/linden-pass/dm-content/player-wiki/pages/notes/form-identity/edit"
    )
    assert create_response.status_code == 302
    assert create_response.headers["Location"] == edit_path + editor_anchor

    edit_page = client.get(edit_path)
    edit_html = edit_page.get_data(as_text=True)
    update_action = "/campaigns/linden-pass/dm-content/player-wiki/pages/notes/form-identity"
    assert edit_page.status_code == 200
    assert f'<form method="post" action="{update_action}"' in edit_html
    assert (
        'href="/campaigns/linden-pass/dm-content/player-wiki'
        f'{editor_anchor}">New page</a>'
    ) in edit_html
    assert f'href="{edit_path}{editor_anchor}">Edit</a>' in edit_html

    empty_staged_page = client.get("/campaigns/linden-pass/dm-content/staged-articles")
    assert empty_staged_page.status_code == 200
    assert f'href="{staged_session_href}"' not in empty_staged_page.get_data(as_text=True)

    create_article = client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Form Identity Handout",
            "body_markdown": "Review this staged handout before durable publication.",
        },
        follow_redirects=False,
    )
    assert create_article.status_code == 302
    with app.app_context():
        article = app.extensions["campaign_session_service"].list_articles("linden-pass")[0]

    session_prefill_path = (
        "/campaigns/linden-pass/dm-content/player-wiki/session-articles/"
        f"{article.id}/new"
    )
    session_prefill = client.get(session_prefill_path)
    session_prefill_html = session_prefill.get_data(as_text=True)
    assert session_prefill.status_code == 200
    assert 'id="dm-content-player-wiki-editor"' in session_prefill_html
    assert f'<form method="post" action="{create_action}"' in session_prefill_html
    assert 'name="source_session_article_id"' in session_prefill_html
    assert f'value="{article.id}"' in session_prefill_html

    staged_page = client.get("/campaigns/linden-pass/dm-content/staged-articles")
    staged_html = staged_page.get_data(as_text=True)
    assert staged_page.status_code == 200
    assert staged_html.count(f'href="{staged_session_href}"') == 1


def test_player_wiki_browser_has_no_draft_preview_or_force_delete_contract(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["dm"]["email"], users["dm"]["password"])

    route_rules = list(app.url_map.iter_rules())
    assert any(
        rule.endpoint == "campaign_global_search_preview"
        and rule.rule == "/campaigns/<campaign_slug>/global-search/preview"
        for rule in route_rules
    )
    assert not any(
        "player-wiki" in rule.rule and "preview" in rule.rule
        for rule in route_rules
    )

    landing = client.get("/campaigns/linden-pass/dm-content/player-wiki")
    landing_html = landing.get_data(as_text=True)
    assert landing.status_code == 200
    assert "/dm-content/player-wiki/preview" not in landing_html
    assert "Preview player wiki draft" not in landing_html
    assert 'name="force"' not in landing_html
    assert "?force=" not in landing_html


def test_player_wiki_management_shows_delete_only_when_safe_and_ignores_browser_force(
    app,
    client,
    sign_in,
    users,
):
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
            summary="A safe page that links to the field report.",
            body_markdown="Review [[Field Report]] before closing the job.",
        ),
        follow_redirects=False,
    )

    landing = client.get("/campaigns/linden-pass/dm-content/player-wiki")
    landing_html = landing.get_data(as_text=True)
    blocked_card = _html_article_by_id(landing_html, "wiki-page-notes-field-report")
    safe_card = _html_article_by_id(landing_html, "wiki-page-notes-followup-note")

    assert landing.status_code == 200
    assert "Hard delete blocked" in blocked_card
    assert 'name="confirm_delete"' not in blocked_card
    assert "Delete file" not in blocked_card
    assert 'name="confirm_delete" value="1"' in safe_card
    assert "Delete file" in safe_card
    assert 'name="force"' not in safe_card

    forced_browser_delete = client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages/notes/field-report/delete",
        data={"confirm_delete": "1", "force": "true"},
        follow_redirects=True,
    )

    assert forced_browser_delete.status_code == 200
    assert "Hard delete blocked. Unpublish/archive the page or remove:" in (
        forced_browser_delete.get_data(as_text=True)
    )
    assert _campaign_page_path(app, "notes/field-report").exists()


@pytest.mark.parametrize("source_session_article_id", [None, "   "])
def test_content_manager_without_session_access_can_create_ordinary_player_wiki_page(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    source_session_article_id,
):
    set_campaign_visibility("linden-pass", session="private")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    slug_leaf = (
        "ordinary-without-source"
        if source_session_article_id is None
        else "ordinary-with-blank-source"
    )
    form_data = _page_form(slug_leaf=slug_leaf)
    if source_session_article_id is not None:
        form_data["source_session_article_id"] = source_session_article_id

    response = client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages",
        data=form_data,
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert _campaign_page_path(app, f"notes/{slug_leaf}").exists()


def test_promotion_requires_session_manager_before_lookup_or_side_effects(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    monkeypatch,
):
    with app.app_context():
        session_service = app.extensions["campaign_session_service"]
        article = session_service.create_article(
            "linden-pass",
            title="Protected promotion source",
            body_markdown="This article must not be disclosed through promotion.",
            created_by_user_id=users["dm"]["id"],
        )

    set_campaign_visibility("linden-pass", session="private")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    prefill_response = client.get(
        f"/campaigns/linden-pass/dm-content/player-wiki/session-articles/{article.id}/new",
        follow_redirects=False,
    )
    assert prefill_response.status_code == 403
    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign is not None
        revision_before = session_service.get_live_revision("linden-pass")
        articles_before = session_service.list_articles("linden-pass")
        audits_before = app.extensions["auth_store"].list_recent_audit_events(limit=1000)
        page_refs_before = set(campaign.pages)

    def unexpected_call(*args, **kwargs):
        raise AssertionError("promotion denial must precede lookup and mutation dependencies")

    monkeypatch.setattr(session_service, "get_article", unexpected_call)
    monkeypatch.setattr(session_service, "get_article_image", unexpected_call)
    monkeypatch.setattr(session_service, "bump_live_state_revision", unexpected_call)
    monkeypatch.setattr(app.extensions["repository_store"], "refresh", unexpected_call)
    monkeypatch.setattr(
        app.extensions["repository_store"],
        "refresh_from_database",
        unexpected_call,
    )
    monkeypatch.setattr(app.extensions["auth_store"], "write_audit_event", unexpected_call)
    monkeypatch.setattr(publishing_routes, "_capture_player_wiki_image", unexpected_call)
    monkeypatch.setattr(publishing_routes, "create_player_wiki_page", unexpected_call)

    responses = []
    for slug_leaf, source_article_id in (
        ("denied-known-source", str(article.id)),
        ("denied-missing-source", str(article.id + 100_000)),
        ("denied-invalid-source", "not-an-article-id"),
    ):
        response = client.post(
            "/campaigns/linden-pass/dm-content/player-wiki/pages",
            data={
                **_page_form(slug_leaf=slug_leaf),
                "source_session_article_id": source_article_id,
                "image_file": (BytesIO(TEST_PNG_BYTES), f"{slug_leaf}.png"),
            },
            follow_redirects=False,
        )
        responses.append(response)
        assert response.status_code == 403
        assert not _campaign_page_path(app, f"notes/{slug_leaf}").exists()
        assert not _campaign_asset_path(app, f"wiki-pages/notes/{slug_leaf}.webp").exists()

    assert {response.get_data() for response in responses} == {responses[0].get_data()}
    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        assert campaign is not None
        assert set(campaign.pages) == page_refs_before
        for page_ref in (
            "notes/denied-known-source",
            "notes/denied-missing-source",
            "notes/denied-invalid-source",
        ):
            assert get_campaign_page_file(
                campaign,
                page_ref,
                page_store=app.extensions["campaign_page_store"],
            ) is None
        assert session_service.list_articles("linden-pass") == articles_before
        assert session_service.get_live_revision("linden-pass") == revision_before
        assert app.extensions["auth_store"].list_recent_audit_events(limit=1000) == audits_before


def test_csrf_rejection_precedes_promotion_session_authority_check(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    monkeypatch,
):
    set_campaign_visibility("linden-pass", session="private")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    app.config["CSRF_ENABLED"] = True

    def unexpected_lookup(*args, **kwargs):
        raise AssertionError("CSRF denial must precede promotion authorization and lookup")

    monkeypatch.setattr(
        app.extensions["campaign_session_service"],
        "get_article",
        unexpected_lookup,
    )

    response = client.post(
        "/campaigns/linden-pass/dm-content/player-wiki/pages",
        data={
            **_page_form(slug_leaf="csrf-denied-promotion"),
            "source_session_article_id": "12345",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert not _campaign_page_path(app, "notes/csrf-denied-promotion").exists()


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

    session_dm_page = client.get("/campaigns/linden-pass/session/dm?dm_view=staged")
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


def test_convert_vs_editor_same_dest_generic_wins(app, client, sign_in, users, monkeypatch):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Destination Race",
            "body_markdown": "The one-shot candidate must not overwrite the editor winner.",
            "image_file": (BytesIO(TEST_PNG_BYTES), "one-shot.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    paused = Event()
    resume = Event()
    original_prepare = session_article_publisher.prepare_campaign_page_write

    def pause_after_local_absence(*args, **kwargs):
        prepared = original_prepare(*args, **kwargs)
        paused.set()
        assert resume.wait(timeout=5)
        return prepared

    monkeypatch.setattr(
        session_article_publisher,
        "prepare_campaign_page_write",
        pause_after_local_absence,
    )

    def one_shot():
        with app.app_context():
            campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
            article = app.extensions["campaign_session_service"].get_article("linden-pass", 1)
            image = app.extensions["campaign_session_service"].get_article_image("linden-pass", 1)
            assert campaign is not None and article is not None and image is not None
            try:
                publish_session_article(
                    campaign,
                    article,
                    article_image=image,
                    options=SessionArticlePublishOptions(
                        title="Destination Race",
                        slug_leaf="shared-destination",
                        summary="One writer wins.",
                        section="Notes",
                        page_type="note",
                        subsection="",
                        reveal_after_session=campaign.current_session,
                    ),
                    page_store=app.extensions["campaign_page_store"],
                    reconciler=app.extensions["player_wiki_reconciler"],
                )
            except SessionArticlePublishError as exc:
                return str(exc)
            return "unexpected-success"

    with app.app_context():
        revision_before = app.extensions["campaign_session_service"].get_live_revision(
            "linden-pass"
        )
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(one_shot)
        assert paused.wait(timeout=5)
        with app.app_context():
            campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
            assert campaign is not None
            result = publishing_mutations.create_player_wiki_page(
                campaign,
                users["dm"]["id"],
                publishing_mutations.PlayerWikiFormInput(
                    **_page_form(
                        title="Editor Winner",
                        slug_leaf="shared-destination",
                        source_ref="editor:durable-winner",
                        image_alt="The editor winner.",
                    )
                ),
                publishing_mutations.RawPlayerWikiImageInput(
                    filename="editor-winner.png",
                    data_blob=TEST_PNG_BYTES,
                    declared_length=len(TEST_PNG_BYTES),
                ),
                _mutation_dependencies(app),
            )
            assert result.record.page.source_ref == "editor:durable-winner"
        resume.set()
        assert future.result(timeout=5) == (
            "That wiki page slug is already in use. Choose a different slug."
        )

    page_path = _campaign_page_path(app, "notes/shared-destination")
    editor_asset = _campaign_asset_path(app, "wiki-pages/notes/shared-destination.webp")
    one_shot_asset = _campaign_asset_path(
        app,
        "session-articles/article-1-shared-destination.webp",
    )
    raw_text = page_path.read_text(encoding="utf-8")
    assert "title: Editor Winner" in raw_text
    assert "source_ref: editor:durable-winner" in raw_text
    assert_webp_bytes(editor_asset.read_bytes())
    assert not one_shot_asset.exists()
    with app.app_context():
        assert app.extensions["campaign_session_service"].get_live_revision(
            "linden-pass"
        ) == revision_before
        assert get_db().execute(
            "SELECT COUNT(*) FROM player_wiki_reconciliation_operations"
        ).fetchone()[0] == 0
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'campaign_wiki_page_created'"
        ).fetchone()[0] == 1


def test_dest_race_one_shot_wins(app, client, sign_in, users, monkeypatch):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "One Shot Winner",
            "body_markdown": "The durable one-shot snapshot wins this race.",
            "image_file": (BytesIO(TEST_PNG_BYTES), "one-shot-winner.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    paused = Event()
    resume = Event()
    original_prepare = publishing_mutations.prepare_campaign_page_write

    def pause_editor_after_local_absence(*args, **kwargs):
        prepared = original_prepare(*args, **kwargs)
        paused.set()
        assert resume.wait(timeout=5)
        return prepared

    monkeypatch.setattr(
        publishing_mutations,
        "prepare_campaign_page_write",
        pause_editor_after_local_absence,
    )

    def editor_create():
        with app.app_context():
            campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
            assert campaign is not None
            try:
                publishing_mutations.create_player_wiki_page(
                    campaign,
                    users["dm"]["id"],
                    publishing_mutations.PlayerWikiFormInput(
                        **_page_form(
                            title="Editor Loser",
                            slug_leaf="one-wins",
                            source_ref="editor:must-not-win",
                        )
                    ),
                    None,
                    _mutation_dependencies(app),
                )
            except ValueError as exc:
                return str(exc)
            return "unexpected-success"

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(editor_create)
        assert paused.wait(timeout=5)
        with app.app_context():
            campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
            article = app.extensions["campaign_session_service"].get_article("linden-pass", 1)
            image = app.extensions["campaign_session_service"].get_article_image("linden-pass", 1)
            assert campaign is not None and article is not None and image is not None
            publish_session_article(
                campaign,
                article,
                article_image=image,
                options=SessionArticlePublishOptions(
                    title="One Shot Winner",
                    slug_leaf="one-wins",
                    summary="One-shot authority.",
                    section="Notes",
                    page_type="note",
                    subsection="",
                    reveal_after_session=campaign.current_session,
                ),
                page_store=app.extensions["campaign_page_store"],
                reconciler=app.extensions["player_wiki_reconciler"],
            )
        resume.set()
        assert future.result(timeout=5) == (
            "That page slug is already in use. Choose a different slug."
        )

    page_path = _campaign_page_path(app, "notes/one-wins")
    one_shot_asset = _campaign_asset_path(
        app,
        "session-articles/article-1-one-wins.webp",
    )
    raw_text = page_path.read_text(encoding="utf-8")
    assert "title: One Shot Winner" in raw_text
    assert "source_ref: session-article:linden-pass:1" in raw_text
    assert_webp_bytes(one_shot_asset.read_bytes())
    with app.app_context():
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'campaign_wiki_page_created'"
        ).fetchone()[0] == 0
        assert get_db().execute(
            "SELECT COUNT(*) FROM player_wiki_reconciliation_operations"
        ).fetchone()[0] == 0


def test_convert_vs_editor_same_source_editor_wins(app, client, sign_in, users, monkeypatch):
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/session/articles",
        data={
            "title": "Shared Provenance",
            "body_markdown": "Only one durable page may retain this provenance.",
            "image_file": (BytesIO(TEST_PNG_BYTES), "shared-provenance.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    editor_holds_lock = Event()
    resume_editor = Event()
    original_ensure = publishing_mutations.ensure_session_article_conversion_available

    def pause_editor_with_article_lock(*args, **kwargs):
        result = original_ensure(*args, **kwargs)
        editor_holds_lock.set()
        assert resume_editor.wait(timeout=5)
        return result

    monkeypatch.setattr(
        publishing_mutations,
        "ensure_session_article_conversion_available",
        pause_editor_with_article_lock,
    )

    def editor_promotion():
        with app.app_context():
            campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
            assert campaign is not None
            return publishing_mutations.create_player_wiki_page(
                campaign,
                users["dm"]["id"],
                publishing_mutations.PlayerWikiFormInput(
                    **_page_form(
                        title="Editor Provenance Winner",
                        slug_leaf="editor-provenance-winner",
                        source_session_article_id="1",
                    )
                ),
                None,
                _mutation_dependencies(app),
            )

    def one_shot_loser():
        with app.app_context():
            campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
            article = app.extensions["campaign_session_service"].get_article("linden-pass", 1)
            image = app.extensions["campaign_session_service"].get_article_image("linden-pass", 1)
            assert campaign is not None and article is not None and image is not None
            try:
                publish_session_article(
                    campaign,
                    article,
                    article_image=image,
                    options=SessionArticlePublishOptions(
                        title="One Shot Provenance Loser",
                        slug_leaf="one-shot-provenance-loser",
                        summary="Must not publish.",
                        section="Notes",
                        page_type="note",
                        subsection="",
                        reveal_after_session=campaign.current_session,
                    ),
                    page_store=app.extensions["campaign_page_store"],
                    reconciler=app.extensions["player_wiki_reconciler"],
                )
            except SessionArticlePublishError as exc:
                return str(exc)
            return "unexpected-success"

    with ThreadPoolExecutor(max_workers=2) as executor:
        editor_future = executor.submit(editor_promotion)
        assert editor_holds_lock.wait(timeout=5)
        one_shot_future = executor.submit(one_shot_loser)
        resume_editor.set()
        editor_result = editor_future.result(timeout=5)
        assert editor_result.record.page.source_ref == "session-article:linden-pass:1"
        assert one_shot_future.result(timeout=5) == (
            "This session article has already been converted into wiki content."
        )

    assert _campaign_page_path(app, "notes/editor-provenance-winner").exists()
    assert not _campaign_page_path(app, "notes/one-shot-provenance-loser").exists()
    assert_webp_bytes(
        _campaign_asset_path(app, "wiki-pages/notes/editor-provenance-winner.webp").read_bytes()
    )
    assert not _campaign_asset_path(
        app,
        "session-articles/article-1-one-shot-provenance-loser.webp",
    ).exists()
    with app.app_context():
        source_rows = get_db().execute(
            "SELECT page_ref FROM campaign_pages WHERE source_ref = ?",
            ("session-article:linden-pass:1",),
        ).fetchall()
        assert [row["page_ref"] for row in source_rows] == ["notes/editor-provenance-winner"]
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'campaign_wiki_page_created'"
        ).fetchone()[0] == 1
        assert get_db().execute(
            "SELECT COUNT(*) FROM player_wiki_reconciliation_operations"
        ).fetchone()[0] == 0


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
