from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable

from flask import Blueprint, abort, jsonify, request, send_file

from .campaign_session_service import CampaignSessionValidationError
from .session_models import (
    SESSION_ARTICLE_SOURCE_KIND_SYSTEMS,
    build_session_article_page_source_ref,
    build_session_article_systems_source_ref,
    parse_session_article_source_ref,
)


@dataclass(frozen=True)
class SessionApiReadDependencies:
    session_scope_access_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    login_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    get_session_service: Callable[[], Any]
    get_current_user: Callable[[], Any]
    load_json_object: Callable[[], dict[str, Any]]
    get_current_user_preferences: Callable[[], Any]
    build_session_live_view_token: Callable[..., str]
    can_manage_session: Callable[[str], bool]
    can_post_session_messages: Callable[[str], bool]
    should_short_circuit_live_response: Callable[..., bool]
    build_session_payload: Callable[[str], dict[str, Any]]
    json_error: Callable[..., Any]
    get_repository: Callable[[], Any]
    build_session_article_source_search_results: Callable[..., list[dict[str, Any]]]
    get_campaign_page_store: Callable[[], Any]
    get_systems_service: Callable[[], Any]
    can_access_campaign_scope: Callable[[str, str], bool]
    can_access_campaign_systems_entry: Callable[[str, str], bool]
    serialize_session_record: Callable[[Any], dict[str, Any]]
    serialize_session_message: Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class SessionArticleAuthoringDependencies:
    session_scope_access_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    login_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    can_manage_session: Callable[[str], bool]
    get_current_user: Callable[[], Any]
    load_json_object: Callable[[], dict[str, Any]]
    get_session_service: Callable[[], Any]
    get_repository: Callable[[], Any]
    get_campaign_page_store: Callable[[], Any]
    get_systems_service: Callable[[], Any]
    can_access_campaign_scope: Callable[[str, str], bool]
    can_access_campaign_systems_entry: Callable[[str, str], bool]
    get_pullable_session_systems_entry: Callable[..., Any]
    get_pullable_session_wiki_page_record: Callable[..., Any]
    get_campaign_asset_file: Callable[[Any, str], Any]
    guess_campaign_asset_media_type: Callable[[Any], str]
    read_bounded_file: Callable[..., bytes]
    decode_embedded_file: Callable[..., dict[str, Any]]
    get_max_ingress_file_bytes: Callable[[], int]
    serialize_session_article: Callable[..., dict[str, Any]]
    json_error: Callable[..., Any]


@dataclass(frozen=True)
class SessionArticleLifecycleDependencies:
    session_scope_access_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    login_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    can_manage_session: Callable[[str], bool]
    get_current_user: Callable[[], Any]
    get_session_service: Callable[[], Any]
    serialize_session_article: Callable[..., dict[str, Any]]
    serialize_datetime: Callable[[Any], str | None]
    json_error: Callable[..., Any]


def register_session_api_read_routes(
    api: Blueprint,
    *,
    dependencies: SessionApiReadDependencies,
) -> None:
    def session_state(campaign_slug: str):
        session_service = dependencies.get_session_service()
        live_revision = session_service.get_live_revision(campaign_slug)
        current_preferences = dependencies.get_current_user_preferences()
        live_view_token = dependencies.build_session_live_view_token(
            campaign_slug,
            "session",
            session_chat_order=current_preferences.session_chat_order,
            can_manage_session=dependencies.can_manage_session(campaign_slug),
            can_post_session_messages=dependencies.can_post_session_messages(campaign_slug),
            normalize_hash_parts=True,
        )
        if dependencies.should_short_circuit_live_response(
            request.headers,
            live_revision=live_revision,
            live_view_token=live_view_token,
        ):
            return jsonify(
                {
                    "ok": True,
                    "changed": False,
                    "session_revision": live_revision,
                    "session_view_token": live_view_token,
                }
            )

        payload = dependencies.build_session_payload(campaign_slug)
        payload["session_revision"] = live_revision
        payload["session_view_token"] = live_view_token
        return jsonify({"ok": True, **payload})

    def session_article_source_search(campaign_slug: str):
        if not dependencies.can_manage_session(campaign_slug):
            return dependencies.json_error(
                "You do not have permission to manage this session.",
                403,
                code="forbidden",
            )

        query = request.args.get("q", "").strip()
        if len(query) < 2:
            return jsonify(
                {
                    "ok": True,
                    "results": [],
                    "message": "Type at least 2 letters to search published wiki pages and Systems entries.",
                }
            )

        campaign = dependencies.get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)
        results = dependencies.build_session_article_source_search_results(
            campaign=campaign,
            campaign_slug=campaign_slug,
            query=query,
            page_store=dependencies.get_campaign_page_store(),
            systems_service=dependencies.get_systems_service(),
            can_access_systems=dependencies.can_access_campaign_scope(campaign_slug, "systems"),
            can_access_systems_entry=lambda entry_slug: (
                dependencies.can_access_campaign_systems_entry(
                    campaign_slug,
                    entry_slug,
                )
            ),
            limit=30,
        )
        message = (
            "Showing the first 30 matching articles."
            if len(results) == 30
            else (
                f"Found {len(results)} matching article{'s' if len(results) != 1 else ''}."
                if results
                else "No published wiki or Systems articles matched that search."
            )
        )
        return jsonify({"ok": True, "results": results, "message": message})

    def session_article_image(campaign_slug: str, article_id: int):
        session_service = dependencies.get_session_service()
        article = session_service.get_article(campaign_slug, article_id)
        image = session_service.get_article_image(campaign_slug, article_id)
        if article is None or image is None:
            abort(404)

        if not dependencies.can_manage_session(campaign_slug):
            active_session = session_service.get_active_session(campaign_slug)
            if (
                active_session is None
                or not article.is_revealed
                or article.revealed_in_session_id != active_session.id
            ):
                abort(404)

        return send_file(
            BytesIO(image.data_blob),
            mimetype=image.media_type,
            download_name=image.filename,
        )

    def session_log_detail(campaign_slug: str, session_id: int):
        if not dependencies.can_manage_session(campaign_slug):
            return dependencies.json_error(
                "You do not have permission to manage this session.",
                403,
                code="forbidden",
            )

        session_service = dependencies.get_session_service()
        session_record = session_service.get_session_log(campaign_slug, session_id)
        if session_record is None or session_record.is_active:
            abort(404)

        articles = session_service.list_articles(campaign_slug)
        article_lookup = {article.id: article for article in articles}
        article_images = (
            session_service.list_article_images(list(article_lookup))
            if article_lookup
            else {}
        )

        return jsonify(
            {
                "ok": True,
                "session": dependencies.serialize_session_record(session_record),
                "messages": [
                    dependencies.serialize_session_message(
                        campaign_slug,
                        message,
                        article_lookup,
                        article_images,
                    )
                    for message in session_service.list_messages(
                        session_record.id,
                        can_manage_session=True,
                    )
                ],
            }
        )

    def session_start(campaign_slug: str):
        if not dependencies.can_manage_session(campaign_slug):
            return dependencies.json_error(
                "You do not have permission to manage this session.",
                403,
                code="forbidden",
            )

        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.",
                401,
                code="auth_required",
            )

        try:
            session_record = dependencies.get_session_service().begin_session(
                campaign_slug,
                started_by_user_id=user.id,
            )
        except CampaignSessionValidationError as exc:
            return dependencies.json_error(
                str(exc),
                400,
                code="validation_error",
            )

        return jsonify(
            {
                "ok": True,
                "session": dependencies.serialize_session_record(session_record),
            }
        )

    def session_close(campaign_slug: str):
        if not dependencies.can_manage_session(campaign_slug):
            return dependencies.json_error(
                "You do not have permission to manage this session.",
                403,
                code="forbidden",
            )

        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.",
                401,
                code="auth_required",
            )

        try:
            session_record = dependencies.get_session_service().close_session(
                campaign_slug,
                ended_by_user_id=user.id,
            )
        except CampaignSessionValidationError as exc:
            return dependencies.json_error(
                str(exc),
                400,
                code="validation_error",
            )

        return jsonify(
            {
                "ok": True,
                "session": dependencies.serialize_session_record(session_record),
            }
        )

    def session_log_delete(campaign_slug: str, session_id: int):
        if not dependencies.can_manage_session(campaign_slug):
            return dependencies.json_error(
                "You do not have permission to manage this session.",
                403,
                code="forbidden",
            )

        try:
            dependencies.get_session_service().delete_session_log(
                campaign_slug,
                session_id,
            )
        except CampaignSessionValidationError as exc:
            return dependencies.json_error(
                str(exc),
                400,
                code="validation_error",
            )

        return jsonify({"ok": True, "deleted_session_id": session_id})

    def session_message_create(campaign_slug: str):
        if not dependencies.can_post_session_messages(campaign_slug):
            return dependencies.json_error(
                "You do not have permission to post session messages.",
                403,
                code="forbidden",
            )

        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.",
                401,
                code="auth_required",
            )

        try:
            payload = dependencies.load_json_object()
        except ValueError as exc:
            return dependencies.json_error(
                str(exc),
                400,
                code="invalid_json",
            )

        try:
            message = dependencies.get_session_service().post_message(
                campaign_slug,
                body_text=payload.get("body", ""),
                author_display_name=user.display_name,
                author_user_id=user.id,
                recipient_scope=str(payload.get("recipient_scope", "global")),
                recipient_user_id=payload.get("recipient_user_id"),
            )
        except CampaignSessionValidationError as exc:
            return dependencies.json_error(
                str(exc),
                400,
                code="validation_error",
            )

        return jsonify(
            {
                "ok": True,
                "message": dependencies.serialize_session_message(
                    campaign_slug,
                    message,
                    {},
                    {},
                ),
            }
        )

    session_state_view = dependencies.session_scope_access_required(session_state)
    session_article_source_search_view = dependencies.session_scope_access_required(
        dependencies.login_required(session_article_source_search)
    )
    session_article_image_view = dependencies.session_scope_access_required(
        session_article_image
    )
    session_log_detail_view = dependencies.session_scope_access_required(
        dependencies.login_required(session_log_detail)
    )
    session_start_view = dependencies.session_scope_access_required(
        dependencies.login_required(session_start)
    )
    session_close_view = dependencies.session_scope_access_required(
        dependencies.login_required(session_close)
    )
    session_log_delete_view = dependencies.session_scope_access_required(
        dependencies.login_required(session_log_delete)
    )
    session_message_create_view = dependencies.session_scope_access_required(
        dependencies.login_required(session_message_create)
    )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/session",
        endpoint="session_state",
        view_func=session_state_view,
        methods=("GET",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/session/article-sources/search",
        endpoint="session_article_source_search",
        view_func=session_article_source_search_view,
        methods=("GET",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/session/articles/<int:article_id>/image",
        endpoint="session_article_image",
        view_func=session_article_image_view,
        methods=("GET",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/session/logs/<int:session_id>",
        endpoint="session_log_detail",
        view_func=session_log_detail_view,
        methods=("GET",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/session/start",
        endpoint="session_start",
        view_func=session_start_view,
        methods=("POST",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/session/close",
        endpoint="session_close",
        view_func=session_close_view,
        methods=("POST",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/session/logs/<int:session_id>",
        endpoint="session_log_delete",
        view_func=session_log_delete_view,
        methods=("DELETE",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/session/messages",
        endpoint="session_message_create",
        view_func=session_message_create_view,
        methods=("POST",),
    )


def register_session_article_authoring_routes(
    api: Blueprint,
    *,
    dependencies: SessionArticleAuthoringDependencies,
) -> None:
    def session_article_create(campaign_slug: str):
        if not dependencies.can_manage_session(campaign_slug):
            return dependencies.json_error(
                "You do not have permission to manage this session.",
                403,
                code="forbidden",
            )

        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.",
                401,
                code="auth_required",
            )

        try:
            payload = dependencies.load_json_object()
        except ValueError as exc:
            return dependencies.json_error(str(exc), 400, code="invalid_json")

        session_service = dependencies.get_session_service()
        article = None
        mode = str(payload.get("mode") or "manual").strip().lower()
        if mode not in {"manual", "upload", "wiki"}:
            return dependencies.json_error(
                "Article mode must be 'manual', 'upload', or 'wiki'.",
                400,
                code="validation_error",
            )

        try:
            if mode == "upload":
                filename = str(payload.get("filename") or "").strip()
                markdown_text = str(payload.get("markdown_text") or "")
                markdown_upload = session_service.parse_article_markdown_upload(
                    filename=filename,
                    data_blob=markdown_text.encode("utf-8"),
                )
                image_payload = payload.get("referenced_image")
                if markdown_upload.image_reference and image_payload is None:
                    raise CampaignSessionValidationError(
                        "This markdown file references an image. Include referenced_image too."
                    )
                referenced_image_upload = None
                if image_payload is not None:
                    image_file = dependencies.decode_embedded_file(
                        image_payload,
                        label="referenced_image",
                        max_decoded_bytes=dependencies.get_max_ingress_file_bytes(),
                    )
                    referenced_image_upload = session_service.prepare_article_image_upload(
                        filename=image_file["filename"],
                        media_type=image_file["media_type"],
                        data_blob=image_file["data_blob"],
                        alt_text=markdown_upload.image_alt,
                        caption=markdown_upload.image_caption,
                    )
                article = session_service.create_article(
                    campaign_slug,
                    title=markdown_upload.title,
                    body_markdown=markdown_upload.body_markdown,
                    has_content_image=referenced_image_upload is not None,
                    created_by_user_id=user.id,
                )
                if referenced_image_upload is not None:
                    session_service.attach_article_image(
                        campaign_slug,
                        article.id,
                        filename=referenced_image_upload.filename,
                        media_type=referenced_image_upload.media_type,
                        data_blob=referenced_image_upload.data_blob,
                        alt_text=referenced_image_upload.alt_text,
                        caption=referenced_image_upload.caption,
                    )
            elif mode == "wiki":
                campaign = dependencies.get_repository().get_campaign(campaign_slug)
                if campaign is None:
                    abort(404)

                source_kind, source_ref = parse_session_article_source_ref(
                    str(payload.get("source_ref") or payload.get("page_ref") or "")
                )
                if source_kind == SESSION_ARTICLE_SOURCE_KIND_SYSTEMS:
                    entry = dependencies.get_pullable_session_systems_entry(
                        campaign_slug,
                        source_ref,
                        systems_service=dependencies.get_systems_service(),
                        can_access_systems=dependencies.can_access_campaign_scope(
                            campaign_slug,
                            "systems",
                        ),
                        can_access_systems_entry=lambda entry_slug: (
                            dependencies.can_access_campaign_systems_entry(
                                campaign_slug,
                                entry_slug,
                            )
                        ),
                    )
                    if entry is None:
                        raise CampaignSessionValidationError(
                            "Choose a visible published wiki page or Systems entry before pulling it into the session store."
                        )

                    source_body_html = entry.rendered_html.strip() or str(
                        ((entry.body or {}).get("rendered") or {}).get("summary_html") or ""
                    ).strip()
                    if not source_body_html:
                        raise CampaignSessionValidationError(
                            "The selected Systems entry does not have rendered article content to pull into the session store."
                        )

                    article = session_service.create_article(
                        campaign_slug,
                        title=entry.title,
                        body_markdown=source_body_html,
                        source_page_ref=build_session_article_systems_source_ref(entry.slug),
                        created_by_user_id=user.id,
                    )
                else:
                    page_record = dependencies.get_pullable_session_wiki_page_record(
                        campaign,
                        source_ref,
                        page_store=dependencies.get_campaign_page_store(),
                        include_body=True,
                    )
                    if page_record is None:
                        raise CampaignSessionValidationError(
                            "Choose a visible published wiki page or Systems entry before pulling it into the session store."
                        )

                    page_image_upload = None
                    if page_record.page.image_path:
                        image_path = dependencies.get_campaign_asset_file(
                            campaign,
                            page_record.page.image_path,
                        )
                        if image_path is not None:
                            page_image_upload = session_service.prepare_article_image_upload(
                                filename=image_path.name,
                                media_type=dependencies.guess_campaign_asset_media_type(image_path),
                                data_blob=dependencies.read_bounded_file(
                                    image_path,
                                    max_bytes=dependencies.get_max_ingress_file_bytes(),
                                    message="Wiki page images must stay under 8 MB.",
                                ),
                                alt_text=page_record.page.image_alt,
                                caption=page_record.page.image_caption,
                            )

                    source_body_markdown = (
                        page_record.body_markdown.strip()
                        or page_record.page.summary.strip()
                    )
                    if not source_body_markdown and page_image_upload is None:
                        raise CampaignSessionValidationError(
                            "The selected wiki page does not have any body text, summary, or image to pull into the session store."
                        )
                    article = session_service.create_article(
                        campaign_slug,
                        title=page_record.page.title,
                        body_markdown=source_body_markdown,
                        source_page_ref=build_session_article_page_source_ref(
                            page_record.page_ref
                        ),
                        has_content_image=page_image_upload is not None,
                        created_by_user_id=user.id,
                    )
                    if page_image_upload is not None:
                        session_service.attach_article_image(
                            campaign_slug,
                            article.id,
                            filename=page_image_upload.filename,
                            media_type=page_image_upload.media_type,
                            data_blob=page_image_upload.data_blob,
                            alt_text=page_image_upload.alt_text,
                            caption=page_image_upload.caption,
                        )
            else:
                image_payload = payload.get("image")
                manual_image_upload = None
                if image_payload is not None:
                    image_file = dependencies.decode_embedded_file(
                        image_payload,
                        label="image",
                        max_decoded_bytes=dependencies.get_max_ingress_file_bytes(),
                    )
                    manual_image_upload = session_service.prepare_article_image_upload(
                        filename=image_file["filename"],
                        media_type=image_file["media_type"],
                        data_blob=image_file["data_blob"],
                        alt_text=str(image_payload.get("alt_text") or "").strip(),
                        caption=str(image_payload.get("caption") or "").strip(),
                    )
                article = session_service.create_article(
                    campaign_slug,
                    title=payload.get("title", ""),
                    body_markdown=payload.get("body_markdown", ""),
                    has_content_image=manual_image_upload is not None,
                    created_by_user_id=user.id,
                )
                if manual_image_upload is not None:
                    session_service.attach_article_image(
                        campaign_slug,
                        article.id,
                        filename=manual_image_upload.filename,
                        media_type=manual_image_upload.media_type,
                        data_blob=manual_image_upload.data_blob,
                        alt_text=manual_image_upload.alt_text,
                        caption=manual_image_upload.caption,
                    )
        except (CampaignSessionValidationError, ValueError) as exc:
            if article is not None:
                try:
                    session_service.delete_article(campaign_slug, article.id)
                except CampaignSessionValidationError:
                    pass
            return dependencies.json_error(str(exc), 400, code="validation_error")

        article_image = session_service.get_article_image(campaign_slug, article.id)
        return jsonify(
            {
                "ok": True,
                "article": dependencies.serialize_session_article(
                    campaign_slug,
                    article,
                    article_image,
                ),
            }
        )

    def session_article_update(campaign_slug: str, article_id: int):
        if not dependencies.can_manage_session(campaign_slug):
            return dependencies.json_error(
                "You do not have permission to manage this session.",
                403,
                code="forbidden",
            )

        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.",
                401,
                code="auth_required",
            )

        try:
            payload = dependencies.load_json_object()
        except ValueError as exc:
            return dependencies.json_error(str(exc), 400, code="invalid_json")

        session_service = dependencies.get_session_service()
        try:
            image_payload = payload.get("image")
            image_upload = None
            if image_payload is not None:
                image_file = dependencies.decode_embedded_file(
                    image_payload,
                    label="image",
                    max_decoded_bytes=dependencies.get_max_ingress_file_bytes(),
                )
                image_upload = session_service.prepare_article_image_upload(
                    filename=image_file["filename"],
                    media_type=image_file["media_type"],
                    data_blob=image_file["data_blob"],
                    alt_text=str(image_payload.get("alt_text") or "").strip(),
                    caption=str(image_payload.get("caption") or "").strip(),
                )
            existing_image = session_service.get_article_image(campaign_slug, article_id)
            has_image = image_upload is not None or existing_image is not None
            article = session_service.update_article(
                campaign_slug,
                article_id,
                title=str(payload.get("title") or ""),
                body_markdown=str(payload.get("body_markdown") or ""),
                has_content_image=has_image,
                updated_by_user_id=user.id,
            )
            if image_upload is not None:
                session_service.attach_article_image(
                    campaign_slug,
                    article.id,
                    filename=image_upload.filename,
                    media_type=image_upload.media_type,
                    data_blob=image_upload.data_blob,
                    alt_text=image_upload.alt_text,
                    caption=image_upload.caption,
                    updated_by_user_id=user.id,
                )
            elif (
                payload.get("image_alt_text") is not None
                or payload.get("image_caption") is not None
            ):
                session_service.update_article_image_metadata(
                    campaign_slug,
                    article.id,
                    alt_text=str(payload.get("image_alt_text") or ""),
                    caption=str(payload.get("image_caption") or ""),
                    updated_by_user_id=user.id,
                )
        except (CampaignSessionValidationError, ValueError) as exc:
            return dependencies.json_error(str(exc), 400, code="validation_error")

        article_image = session_service.get_article_image(campaign_slug, article.id)
        return jsonify(
            {
                "ok": True,
                "article": dependencies.serialize_session_article(
                    campaign_slug,
                    article,
                    article_image,
                ),
            }
        )

    session_article_create_view = dependencies.session_scope_access_required(
        dependencies.login_required(session_article_create)
    )
    session_article_update_view = dependencies.session_scope_access_required(
        dependencies.login_required(session_article_update)
    )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/session/articles",
        endpoint="session_article_create",
        view_func=session_article_create_view,
        methods=("POST",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/session/articles/<int:article_id>",
        endpoint="session_article_update",
        view_func=session_article_update_view,
        methods=("PUT",),
    )


def register_session_article_lifecycle_routes(
    api: Blueprint,
    *,
    dependencies: SessionArticleLifecycleDependencies,
) -> None:
    def session_article_reveal(campaign_slug: str, article_id: int):
        if not dependencies.can_manage_session(campaign_slug):
            return dependencies.json_error(
                "You do not have permission to manage this session.",
                403,
                code="forbidden",
            )

        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.",
                401,
                code="auth_required",
            )

        try:
            article, message = dependencies.get_session_service().reveal_article(
                campaign_slug,
                article_id,
                revealed_by_user_id=user.id,
                author_display_name=user.display_name,
            )
        except CampaignSessionValidationError as exc:
            return dependencies.json_error(str(exc), 400, code="validation_error")

        article_image = dependencies.get_session_service().get_article_image(
            campaign_slug,
            article.id,
        )
        return jsonify(
            {
                "ok": True,
                "article": dependencies.serialize_session_article(
                    campaign_slug,
                    article,
                    article_image,
                ),
                "message": {
                    "id": message.id,
                    "session_id": message.session_id,
                    "campaign_slug": message.campaign_slug,
                    "message_type": message.message_type,
                    "body_text": message.body_text,
                    "author_user_id": message.author_user_id,
                    "author_display_name": message.author_display_name,
                    "article_id": message.article_id,
                    "created_at": dependencies.serialize_datetime(message.created_at),
                },
            }
        )

    def session_article_delete(campaign_slug: str, article_id: int):
        if not dependencies.can_manage_session(campaign_slug):
            return dependencies.json_error(
                "You do not have permission to manage this session.",
                403,
                code="forbidden",
            )

        try:
            article = dependencies.get_session_service().delete_article(
                campaign_slug,
                article_id,
            )
        except CampaignSessionValidationError as exc:
            return dependencies.json_error(str(exc), 400, code="validation_error")

        return jsonify(
            {
                "ok": True,
                "article": dependencies.serialize_session_article(
                    campaign_slug,
                    article,
                ),
            }
        )

    def session_revealed_articles_clear(campaign_slug: str):
        if not dependencies.can_manage_session(campaign_slug):
            return dependencies.json_error(
                "You do not have permission to manage this session.",
                403,
                code="forbidden",
            )

        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.",
                401,
                code="auth_required",
            )

        try:
            articles = dependencies.get_session_service().delete_revealed_articles(
                campaign_slug,
                updated_by_user_id=user.id,
            )
        except CampaignSessionValidationError as exc:
            return dependencies.json_error(str(exc), 400, code="validation_error")

        return jsonify(
            {
                "ok": True,
                "deleted_articles": [
                    dependencies.serialize_session_article(campaign_slug, article)
                    for article in articles
                ],
                "deleted_article_ids": [article.id for article in articles],
            }
        )

    session_article_reveal_view = dependencies.session_scope_access_required(
        dependencies.login_required(session_article_reveal)
    )
    session_article_delete_view = dependencies.session_scope_access_required(
        dependencies.login_required(session_article_delete)
    )
    session_revealed_articles_clear_view = dependencies.session_scope_access_required(
        dependencies.login_required(session_revealed_articles_clear)
    )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/session/articles/<int:article_id>/reveal",
        endpoint="session_article_reveal",
        view_func=session_article_reveal_view,
        methods=("POST",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/session/articles/<int:article_id>",
        endpoint="session_article_delete",
        view_func=session_article_delete_view,
        methods=("DELETE",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/session/articles/revealed",
        endpoint="session_revealed_articles_clear",
        view_func=session_revealed_articles_clear_view,
        methods=("DELETE",),
    )
