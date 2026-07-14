from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import time
from typing import Any, Callable

from flask import Blueprint, abort, current_app, jsonify, render_template, request, send_file

from .auth import (
    can_access_campaign_scope,
    can_access_campaign_systems_entry,
    can_manage_campaign_session,
    campaign_scope_access_required,
)
from .live_presenter import (
    build_unchanged_live_payload,
    normalize_session_subpage,
    should_short_circuit_live_response,
)
from .session_source_presenter import build_session_article_source_search_results


session = Blueprint("session", __name__)


@dataclass(frozen=True)
class SessionRouteDependencies:
    build_campaign_session_shell_context: Callable[..., dict[str, object]]
    build_session_live_metadata: Callable[[str, str], dict[str, object]]
    build_campaign_session_live_state: Callable[..., dict[str, object]]
    build_live_json_response: Callable[..., Any]
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

    context = _dependencies().build_campaign_session_shell_context(
        campaign_slug,
        active_pane="dm",
    )
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


@session.record_once
def _register_legacy_endpoints(state: Any) -> None:
    registrations = (
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
            "/campaigns/<campaign_slug>/session-article-images/<int:article_id>",
            "campaign_session_article_image",
            campaign_session_article_image,
        ),
    )
    for rule, endpoint, view_func in registrations:
        state.app.add_url_rule(
            rule,
            endpoint=endpoint,
            view_func=view_func,
            methods=("GET",),
        )


def register_session_routes(
    app: Any,
    *,
    build_campaign_session_shell_context: Callable[..., dict[str, object]],
    build_session_live_metadata: Callable[[str, str], dict[str, object]],
    build_campaign_session_live_state: Callable[..., dict[str, object]],
    build_live_json_response: Callable[..., Any],
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
) -> None:
    app.extensions["session_route_dependencies"] = SessionRouteDependencies(
        build_campaign_session_shell_context=build_campaign_session_shell_context,
        build_session_live_metadata=build_session_live_metadata,
        build_campaign_session_live_state=build_campaign_session_live_state,
        build_live_json_response=build_live_json_response,
        load_campaign_context=load_campaign_context,
        get_campaign_session_service=get_campaign_session_service,
        get_campaign_page_store=get_campaign_page_store,
        get_systems_service=get_systems_service,
        can_player_access_campaign_scope=can_player_access_campaign_scope,
        build_player_session_wiki_search_results=build_player_session_wiki_search_results,
        build_player_session_wiki_lookup_preview_context=build_player_session_wiki_lookup_preview_context,
    )
    app.register_blueprint(session)
