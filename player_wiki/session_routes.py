from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import time
from typing import Any, Callable

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from .auth import (
    can_access_campaign_scope,
    can_access_campaign_systems_entry,
    can_manage_campaign_session,
    can_post_campaign_session_messages,
    campaign_scope_access_required,
    get_current_user,
)
from .live_presenter import (
    build_unchanged_live_payload,
    normalize_session_subpage,
    should_short_circuit_live_response,
)
from .campaign_session_service import CampaignSessionValidationError
from .session_article_publisher import SessionArticlePublishError
from .session_models import SESSION_ARTICLE_SOURCE_KIND_SYSTEMS
from .session_source_presenter import build_session_article_source_search_results
from .session_presenter import present_session_messages, present_session_record


session = Blueprint("session", __name__)


SESSION_DM_VIEW_KEYS = (
    "tools",
    "staged",
    "revealed",
    "article-store",
    "logs",
)


@dataclass(frozen=True)
class SessionRouteDependencies:
    build_campaign_session_shell_context: Callable[..., dict[str, object]]
    build_session_live_metadata: Callable[[str, str], dict[str, object]]
    build_campaign_session_live_state: Callable[..., dict[str, object]]
    build_live_json_response: Callable[..., Any]
    build_session_article_convert_context: Callable[..., dict[str, object]]
    normalize_publish_options: Callable[..., Any]
    publish_session_article: Callable[..., Any]
    get_player_wiki_reconciler: Callable[[], Any]
    normalize_session_article_form_mode: Callable[[str], str]
    create_session_article_from_request: Callable[..., Any]
    update_session_article_from_request: Callable[..., Any]
    load_campaign_context: Callable[[str], Any]
    get_campaign_session_service: Callable[[], Any]
    get_campaign_page_store: Callable[[], Any]
    get_systems_service: Callable[[], Any]
    can_player_access_campaign_scope: Callable[[str, str], bool]
    build_player_session_wiki_search_results: Callable[..., list[dict[str, str]]]
    build_player_session_wiki_lookup_preview_context: Callable[
        [str, str],
        dict[str, object] | None,
    ]
    respond_to_campaign_session_mutation: Callable[..., Any]
    redirect_to_campaign_session_dm: Callable[..., Any]


def _dependencies() -> SessionRouteDependencies:
    return current_app.extensions["session_route_dependencies"]


@campaign_scope_access_required("session")
def campaign_session_view(campaign_slug: str):
    context = _dependencies().build_campaign_session_shell_context(
        campaign_slug,
        active_pane="session",
    )
    return render_template("session.html", **context)


@campaign_scope_access_required("session")
def campaign_session_dm_view(campaign_slug: str):
    if not can_manage_campaign_session(campaign_slug):
        abort(403)

    requested_dm_view = str(request.args.get("dm_view") or "").strip()
    if requested_dm_view not in SESSION_DM_VIEW_KEYS:
        return _dependencies().redirect_to_campaign_session_dm(
            campaign_slug,
            dm_view="tools",
            article_mode=request.args.get("article_mode"),
        )

    context = _dependencies().build_campaign_session_shell_context(
        campaign_slug,
        active_pane="dm",
        dm_view=requested_dm_view,
    )
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        if requested_dm_view == "tools":
            return render_template("_session_dm_tools.html", **context)
        if requested_dm_view == "revealed":
            return render_template("_session_revealed_articles_card.html", **context)
        if requested_dm_view == "logs":
            return render_template("_session_logs_card.html", **context)
    return render_template("session_dm.html", **context)


@campaign_scope_access_required("session")
def campaign_session_live_state(campaign_slug: str):
    dependencies = _dependencies()
    session_subpage = normalize_session_subpage(request.args.get("view", "session"))
    if session_subpage == "dm" and not can_manage_campaign_session(campaign_slug):
        abort(403)
    state_check_started_at = time.perf_counter()
    live_metadata = dependencies.build_session_live_metadata(campaign_slug, session_subpage)
    state_check_ms = (time.perf_counter() - state_check_started_at) * 1000
    if should_short_circuit_live_response(
        request.headers,
        live_revision=int(live_metadata["live_revision"] or 0),
        live_view_token=str(live_metadata["live_view_token"] or ""),
    ):
        return dependencies.build_live_json_response(
            build_unchanged_live_payload(
                live_revision=int(live_metadata["live_revision"] or 0),
                live_view_token=str(live_metadata["live_view_token"] or ""),
            ),
            view_name="session",
            changed=False,
            live_revision=int(live_metadata["live_revision"] or 0),
            state_check_ms=state_check_ms,
            render_ms=0.0,
        )

    render_started_at = time.perf_counter()
    payload = dependencies.build_campaign_session_live_state(
        campaign_slug,
        session_subpage=session_subpage,
        live_revision=int(live_metadata["live_revision"] or 0),
        live_view_token=str(live_metadata["live_view_token"] or ""),
    )
    render_ms = (time.perf_counter() - render_started_at) * 1000
    return dependencies.build_live_json_response(
        payload,
        view_name=f"session-{session_subpage}",
        changed=True,
        live_revision=int(live_metadata["live_revision"] or 0),
        state_check_ms=state_check_ms,
        render_ms=render_ms,
    )


@campaign_scope_access_required("session")
def campaign_session_search_article_sources(campaign_slug: str):
    if not can_manage_campaign_session(campaign_slug):
        abort(403)

    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify(
            {
                "results": [],
                "message": "Type at least 2 letters to search published wiki pages and Systems entries.",
            }
        )

    dependencies = _dependencies()
    campaign = dependencies.load_campaign_context(campaign_slug)
    results = build_session_article_source_search_results(
        campaign=campaign,
        campaign_slug=campaign_slug,
        query=query,
        page_store=dependencies.get_campaign_page_store(),
        systems_service=dependencies.get_systems_service(),
        can_access_systems=can_access_campaign_scope(campaign_slug, "systems"),
        can_access_systems_entry=lambda entry_slug: can_access_campaign_systems_entry(
            campaign_slug,
            entry_slug,
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
    return jsonify({"results": results, "message": message})


@campaign_scope_access_required("session")
def campaign_session_wiki_lookup_search(campaign_slug: str):
    dependencies = _dependencies()
    if not dependencies.can_player_access_campaign_scope(campaign_slug, "wiki"):
        return jsonify(
            {
                "results": [],
                "message": "No player-visible wiki articles are available right now.",
            }
        )

    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify(
            {
                "results": [],
                "message": "Type at least 2 letters to search player-visible wiki articles.",
            }
        )

    results = dependencies.build_player_session_wiki_search_results(
        campaign_slug,
        query,
        limit=30,
    )
    message = (
        "Showing the first 30 matching wiki articles."
        if len(results) == 30
        else (
            f"Found {len(results)} matching article{'s' if len(results) != 1 else ''}."
            if results
            else "No player-visible wiki articles matched that search."
        )
    )
    return jsonify({"results": results, "message": message})


@campaign_scope_access_required("session")
def campaign_session_wiki_lookup_preview(campaign_slug: str):
    page_ref = request.args.get("page_ref", "").strip()
    if not page_ref:
        return jsonify(
            {
                "preview_html": render_template(
                    "_session_wiki_lookup_preview.html",
                    lookup_page=None,
                )
            }
        )

    preview_context = _dependencies().build_player_session_wiki_lookup_preview_context(
        campaign_slug,
        page_ref,
    )
    if preview_context is None:
        return (
            jsonify(
                {
                    "preview_html": render_template(
                        "_session_wiki_lookup_preview.html",
                        lookup_page=None,
                        lookup_unavailable_message="That article is not currently visible to players.",
                    )
                }
            ),
            404,
        )

    return jsonify(
        {
            "preview_html": render_template(
                "_session_wiki_lookup_preview.html",
                **preview_context,
            )
        }
    )


@campaign_scope_access_required("session")
def campaign_session_convert_article_view(campaign_slug: str, article_id: int):
    if not can_manage_campaign_session(campaign_slug):
        abort(403)

    context = _dependencies().build_session_article_convert_context(campaign_slug, article_id)
    return render_template("session_article_convert.html", **context)


@campaign_scope_access_required("session")
def campaign_session_convert_article_submit(campaign_slug: str, article_id: int):
    if not can_manage_campaign_session(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    dependencies = _dependencies()
    campaign = dependencies.load_campaign_context(campaign_slug)
    session_service = dependencies.get_campaign_session_service()
    article = session_service.get_article(campaign_slug, article_id)
    if article is None:
        abort(404)
    article_image = session_service.get_article_image(campaign_slug, article_id)

    form_data = {
        "title": request.form.get("title", ""),
        "slug_leaf": request.form.get("slug_leaf", ""),
        "summary": request.form.get("summary", ""),
        "section": request.form.get("section", ""),
        "page_type": request.form.get("page_type", ""),
        "subsection": request.form.get("subsection", ""),
        "reveal_after_session": request.form.get("reveal_after_session", ""),
    }

    try:
        options = dependencies.normalize_publish_options(**form_data)
        result = dependencies.publish_session_article(
            campaign,
            article,
            article_image=article_image,
            options=options,
            page_store=dependencies.get_campaign_page_store(),
            reconciler=dependencies.get_player_wiki_reconciler(),
        )
    except SessionArticlePublishError as exc:
        flash(str(exc), "error")
        context = dependencies.build_session_article_convert_context(
            campaign_slug,
            article_id,
            form_data=form_data,
        )
        return render_template("session_article_convert.html", **context), 400

    session_service.bump_live_state_revision(campaign_slug, updated_by_user_id=user.id)
    if options.reveal_after_session <= campaign.current_session:
        flash("Session article converted into published wiki content.", "success")
        return redirect(
            url_for(
                "page_view",
                campaign_slug=campaign_slug,
                page_slug=result.route_slug,
            )
        )

    flash(
        f"Session article converted into published wiki content. It will appear once the campaign reaches session {options.reveal_after_session}.",
        "success",
    )
    return redirect(
        url_for(
            "campaign_session_convert_article_view",
            campaign_slug=campaign_slug,
            article_id=article_id,
        )
    )


@campaign_scope_access_required("session")
def campaign_session_reveal_article(campaign_slug: str, article_id: int):
    if not can_manage_campaign_session(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    dependencies = _dependencies()
    mutation_succeeded = False
    try:
        dependencies.get_campaign_session_service().reveal_article(
            campaign_slug,
            article_id,
            revealed_by_user_id=user.id,
            author_display_name=user.display_name,
        )
    except CampaignSessionValidationError as exc:
        flash(str(exc), "error")
    else:
        flash("Session article revealed on the player Session page and saved to the chat history.", "success")
        mutation_succeeded = True

    return dependencies.respond_to_campaign_session_mutation(
        campaign_slug,
        mutation_succeeded=mutation_succeeded,
        anchor="session-revealed-articles",
        dm_view="revealed",
        redirect_to_dm=True,
    )


@campaign_scope_access_required("session")
def campaign_session_delete_article(campaign_slug: str, article_id: int):
    if not can_manage_campaign_session(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    dependencies = _dependencies()
    try:
        deleted_article = dependencies.get_campaign_session_service().delete_article(
            campaign_slug,
            article_id,
            updated_by_user_id=user.id,
        )
    except CampaignSessionValidationError as exc:
        flash(str(exc), "error")
        return dependencies.respond_to_campaign_session_mutation(
            campaign_slug,
            mutation_succeeded=False,
            anchor="session-article-store",
            dm_view="article-store",
            redirect_to_dm=True,
        )

    if deleted_article.is_revealed:
        flash("Session article deleted. Related reveal entries were removed from chat and logs.", "success")
        return dependencies.respond_to_campaign_session_mutation(
            campaign_slug,
            mutation_succeeded=True,
            anchor="session-revealed-articles",
            dm_view="revealed",
            redirect_to_dm=True,
        )

    flash("Session article deleted.", "success")
    return dependencies.respond_to_campaign_session_mutation(
        campaign_slug,
        mutation_succeeded=True,
        anchor="session-staged-articles",
        dm_view="staged",
        redirect_to_dm=True,
    )


@campaign_scope_access_required("session")
def campaign_session_clear_revealed_articles(campaign_slug: str):
    if not can_manage_campaign_session(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    dependencies = _dependencies()
    try:
        deleted_articles = dependencies.get_campaign_session_service().delete_revealed_articles(
            campaign_slug,
            updated_by_user_id=user.id,
        )
    except CampaignSessionValidationError as exc:
        flash(str(exc), "error")
        return dependencies.respond_to_campaign_session_mutation(
            campaign_slug,
            mutation_succeeded=False,
            anchor="session-revealed-articles",
            dm_view="revealed",
            redirect_to_dm=True,
        )

    deletion_count = len(deleted_articles)
    if deletion_count:
        article_label = "article" if deletion_count == 1 else "articles"
        flash(f"Cleared {deletion_count} revealed session {article_label}.", "success")
    else:
        flash("There are no revealed session articles to clear.", "success")
    return dependencies.respond_to_campaign_session_mutation(
        campaign_slug,
        mutation_succeeded=True,
        anchor="session-revealed-articles",
        dm_view="revealed",
        redirect_to_dm=True,
    )


@campaign_scope_access_required("session")
def campaign_session_log_view(campaign_slug: str, session_id: int):
    if not can_manage_campaign_session(campaign_slug):
        abort(403)

    dependencies = _dependencies()
    campaign = dependencies.load_campaign_context(campaign_slug)
    session_record = dependencies.get_campaign_session_service().get_session_log(
        campaign_slug,
        session_id,
    )
    if session_record is None or session_record.is_active:
        abort(404)

    session_service = dependencies.get_campaign_session_service()
    all_articles = session_service.list_articles(campaign_slug)
    article_images = session_service.list_article_images([article.id for article in all_articles])
    messages = session_service.list_messages(
        session_record.id,
        viewer_user_id=int(get_current_user().id) if get_current_user() else None,
        can_manage_session=True,
    )

    return render_template(
        "session_log.html",
        campaign=campaign,
        session_log=present_session_record(session_record, message_count=len(messages)),
        session_messages=present_session_messages(
            campaign,
            messages,
            all_articles,
            article_images,
            image_url_builder=lambda article_id: url_for(
                "campaign_session_article_image",
                campaign_slug=campaign.slug,
                article_id=article_id,
            ),
        ),
        active_nav="session",
    )


@campaign_scope_access_required("session")
def campaign_session_article_image(campaign_slug: str, article_id: int):
    dependencies = _dependencies()
    dependencies.load_campaign_context(campaign_slug)
    session_service = dependencies.get_campaign_session_service()
    article = session_service.get_article(campaign_slug, article_id)
    image = session_service.get_article_image(campaign_slug, article_id)
    if article is None or image is None:
        abort(404)

    if not can_manage_campaign_session(campaign_slug):
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


@campaign_scope_access_required("session")
def campaign_session_create_article(campaign_slug: str):
    if not can_manage_campaign_session(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    dependencies = _dependencies()
    article_mode = dependencies.normalize_session_article_form_mode(
        request.form.get("article_mode", "manual")
    )
    source_kind = ""
    mutation_succeeded = False
    try:
        _, article_mode, source_kind = dependencies.create_session_article_from_request(
            campaign_slug,
            created_by_user_id=user.id,
        )
    except CampaignSessionValidationError as exc:
        flash(str(exc), "error")
    else:
        if article_mode == "wiki":
            if source_kind == SESSION_ARTICLE_SOURCE_KIND_SYSTEMS:
                flash("Systems entry pulled into the session store.", "success")
            else:
                flash("Published wiki page pulled into the session store.", "success")
        else:
            flash("Session article saved to the session store.", "success")
        mutation_succeeded = True

    return dependencies.respond_to_campaign_session_mutation(
        campaign_slug,
        mutation_succeeded=mutation_succeeded,
        anchor="session-article-store",
        article_mode=article_mode,
        dm_view="article-store",
        redirect_to_dm=True,
    )


@campaign_scope_access_required("session")
def campaign_session_update_article(campaign_slug: str, article_id: int):
    if not can_manage_campaign_session(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    dependencies = _dependencies()
    mutation_succeeded = False
    try:
        dependencies.update_session_article_from_request(
            campaign_slug,
            article_id,
            updated_by_user_id=user.id,
        )
    except CampaignSessionValidationError as exc:
        flash(str(exc), "error")
    else:
        flash("Session article updated.", "success")
        mutation_succeeded = True

    return dependencies.respond_to_campaign_session_mutation(
        campaign_slug,
        mutation_succeeded=mutation_succeeded,
        anchor="session-staged-articles",
        dm_view="staged",
        redirect_to_dm=True,
    )


@campaign_scope_access_required("session")
def campaign_session_post_message(campaign_slug: str):
    if not can_post_campaign_session_messages(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    dependencies = _dependencies()
    mutation_succeeded = False
    try:
        recipient_scope = request.form.get("recipient_scope", "global")
        recipient_user_id = request.form.get("recipient_user_id") or None
        dependencies.get_campaign_session_service().post_message(
            campaign_slug,
            body_text=request.form.get("body", ""),
            author_display_name=user.display_name,
            author_user_id=user.id,
            recipient_scope=str(recipient_scope or "").strip().lower(),
            recipient_user_id=recipient_user_id,
        )
    except CampaignSessionValidationError as exc:
        flash(str(exc), "error")
    else:
        flash("Message posted.", "success")
        mutation_succeeded = True

    return dependencies.respond_to_campaign_session_mutation(
        campaign_slug,
        mutation_succeeded=mutation_succeeded,
        anchor="session-chat-compose",
    )


@campaign_scope_access_required("session")
def campaign_session_start(campaign_slug: str):
    if not can_manage_campaign_session(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    dependencies = _dependencies()
    mutation_succeeded = False
    try:
        dependencies.get_campaign_session_service().begin_session(
            campaign_slug,
            started_by_user_id=user.id,
        )
    except CampaignSessionValidationError as exc:
        flash(str(exc), "error")
    else:
        flash("Session started. Players can now use the Session page chat.", "success")
        mutation_succeeded = True

    return dependencies.respond_to_campaign_session_mutation(
        campaign_slug,
        mutation_succeeded=mutation_succeeded,
        anchor="session-controls",
        dm_view="tools",
        redirect_to_dm=True,
    )


@campaign_scope_access_required("session")
def campaign_session_close(campaign_slug: str):
    if not can_manage_campaign_session(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    dependencies = _dependencies()
    try:
        closed_session = dependencies.get_campaign_session_service().close_session(
            campaign_slug,
            ended_by_user_id=user.id,
        )
    except CampaignSessionValidationError as exc:
        flash(str(exc), "error")
        return dependencies.redirect_to_campaign_session_dm(
            campaign_slug,
            anchor="session-controls",
            dm_view="tools",
        )

    flash("Session closed. The chat contents are now stored as a chat log.", "success")
    return redirect(
        url_for(
            "campaign_session_log_view",
            campaign_slug=campaign_slug,
            session_id=closed_session.id,
        )
    )


@campaign_scope_access_required("session")
def campaign_session_log_delete(campaign_slug: str, session_id: int):
    if not can_manage_campaign_session(campaign_slug):
        abort(403)

    user = get_current_user()
    if user is None:
        abort(403)

    dependencies = _dependencies()
    try:
        dependencies.get_campaign_session_service().delete_session_log(
            campaign_slug,
            session_id,
            updated_by_user_id=user.id,
        )
    except CampaignSessionValidationError as exc:
        flash(str(exc), "error")
    else:
        flash("Chat log deleted.", "success")

    return dependencies.redirect_to_campaign_session_dm(
        campaign_slug,
        anchor="session-chat-logs",
        dm_view="logs",
    )


@session.record_once
def _register_legacy_endpoints(state: Any) -> None:
    get_registrations = (
        (
            "/campaigns/<campaign_slug>/session",
            "campaign_session_view",
            campaign_session_view,
        ),
        (
            "/campaigns/<campaign_slug>/session/dm",
            "campaign_session_dm_view",
            campaign_session_dm_view,
        ),
        (
            "/campaigns/<campaign_slug>/session/live-state",
            "campaign_session_live_state",
            campaign_session_live_state,
        ),
        (
            "/campaigns/<campaign_slug>/session/article-sources/search",
            "campaign_session_search_article_sources",
            campaign_session_search_article_sources,
        ),
        (
            "/campaigns/<campaign_slug>/session/wiki-lookup/search",
            "campaign_session_wiki_lookup_search",
            campaign_session_wiki_lookup_search,
        ),
        (
            "/campaigns/<campaign_slug>/session/wiki-lookup/preview",
            "campaign_session_wiki_lookup_preview",
            campaign_session_wiki_lookup_preview,
        ),
        (
            "/campaigns/<campaign_slug>/session/articles/<int:article_id>/convert",
            "campaign_session_convert_article_view",
            campaign_session_convert_article_view,
        ),
        (
            "/campaigns/<campaign_slug>/session/logs/<int:session_id>",
            "campaign_session_log_view",
            campaign_session_log_view,
        ),
        (
            "/campaigns/<campaign_slug>/session-article-images/<int:article_id>",
            "campaign_session_article_image",
            campaign_session_article_image,
        ),
    )
    for rule, endpoint, view_func in get_registrations:
        state.app.add_url_rule(
            rule,
            endpoint=endpoint,
            view_func=view_func,
            methods=("GET",),
        )
    post_registrations = (
        (
            "/campaigns/<campaign_slug>/session/articles",
            "campaign_session_create_article",
            campaign_session_create_article,
        ),
        (
            "/campaigns/<campaign_slug>/session/articles/<int:article_id>",
            "campaign_session_update_article",
            campaign_session_update_article,
        ),
        (
            "/campaigns/<campaign_slug>/session/articles/<int:article_id>/convert",
            "campaign_session_convert_article_submit",
            campaign_session_convert_article_submit,
        ),
        (
            "/campaigns/<campaign_slug>/session/articles/<int:article_id>/reveal",
            "campaign_session_reveal_article",
            campaign_session_reveal_article,
        ),
        (
            "/campaigns/<campaign_slug>/session/articles/<int:article_id>/delete",
            "campaign_session_delete_article",
            campaign_session_delete_article,
        ),
        (
            "/campaigns/<campaign_slug>/session/articles/clear-revealed",
            "campaign_session_clear_revealed_articles",
            campaign_session_clear_revealed_articles,
        ),
        (
            "/campaigns/<campaign_slug>/session/messages",
            "campaign_session_post_message",
            campaign_session_post_message,
        ),
        (
            "/campaigns/<campaign_slug>/session/start",
            "campaign_session_start",
            campaign_session_start,
        ),
        (
            "/campaigns/<campaign_slug>/session/close",
            "campaign_session_close",
            campaign_session_close,
        ),
        (
            "/campaigns/<campaign_slug>/session/logs/<int:session_id>/delete",
            "campaign_session_log_delete",
            campaign_session_log_delete,
        ),
    )
    for rule, endpoint, view_func in post_registrations:
        state.app.add_url_rule(
            rule,
            endpoint=endpoint,
            view_func=view_func,
            methods=("POST",),
        )


def register_session_routes(
    app: Any,
    *,
    build_campaign_session_shell_context: Callable[..., dict[str, object]],
    build_session_live_metadata: Callable[[str, str], dict[str, object]],
    build_campaign_session_live_state: Callable[..., dict[str, object]],
    build_live_json_response: Callable[..., Any],
    build_session_article_convert_context: Callable[..., dict[str, object]],
    normalize_publish_options: Callable[..., Any],
    publish_session_article: Callable[..., Any],
    get_player_wiki_reconciler: Callable[[], Any],
    normalize_session_article_form_mode: Callable[[str], str],
    create_session_article_from_request: Callable[..., Any],
    update_session_article_from_request: Callable[..., Any],
    load_campaign_context: Callable[[str], Any],
    get_campaign_session_service: Callable[[], Any],
    get_campaign_page_store: Callable[[], Any],
    get_systems_service: Callable[[], Any],
    can_player_access_campaign_scope: Callable[[str, str], bool],
    build_player_session_wiki_search_results: Callable[..., list[dict[str, str]]],
    build_player_session_wiki_lookup_preview_context: Callable[
        [str, str],
        dict[str, object] | None,
    ],
    respond_to_campaign_session_mutation: Callable[..., Any],
    redirect_to_campaign_session_dm: Callable[..., Any],
) -> None:
    app.extensions["session_route_dependencies"] = SessionRouteDependencies(
        build_campaign_session_shell_context=build_campaign_session_shell_context,
        build_session_live_metadata=build_session_live_metadata,
        build_campaign_session_live_state=build_campaign_session_live_state,
        build_live_json_response=build_live_json_response,
        build_session_article_convert_context=build_session_article_convert_context,
        normalize_publish_options=normalize_publish_options,
        publish_session_article=publish_session_article,
        get_player_wiki_reconciler=get_player_wiki_reconciler,
        normalize_session_article_form_mode=normalize_session_article_form_mode,
        create_session_article_from_request=create_session_article_from_request,
        update_session_article_from_request=update_session_article_from_request,
        load_campaign_context=load_campaign_context,
        get_campaign_session_service=get_campaign_session_service,
        get_campaign_page_store=get_campaign_page_store,
        get_systems_service=get_systems_service,
        can_player_access_campaign_scope=can_player_access_campaign_scope,
        build_player_session_wiki_search_results=build_player_session_wiki_search_results,
        build_player_session_wiki_lookup_preview_context=build_player_session_wiki_lookup_preview_context,
        respond_to_campaign_session_mutation=respond_to_campaign_session_mutation,
        redirect_to_campaign_session_dm=redirect_to_campaign_session_dm,
    )
    app.register_blueprint(session)
