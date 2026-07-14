from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable

from flask import Blueprint, abort, jsonify, request, send_file

from .campaign_session_service import CampaignSessionValidationError


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
