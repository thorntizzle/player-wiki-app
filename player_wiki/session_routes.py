from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable

from flask import Blueprint, abort, current_app, render_template, request

from .auth import can_manage_campaign_session, campaign_scope_access_required
from .live_presenter import (
    build_unchanged_live_payload,
    normalize_session_subpage,
    should_short_circuit_live_response,
)


session = Blueprint("session", __name__)


@dataclass(frozen=True)
class SessionRouteDependencies:
    build_campaign_session_shell_context: Callable[..., dict[str, object]]
    build_session_live_metadata: Callable[[str, str], dict[str, object]]
    build_campaign_session_live_state: Callable[..., dict[str, object]]
    build_live_json_response: Callable[..., Any]


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
) -> None:
    app.extensions["session_route_dependencies"] = SessionRouteDependencies(
        build_campaign_session_shell_context=build_campaign_session_shell_context,
        build_session_live_metadata=build_session_live_metadata,
        build_campaign_session_live_state=build_campaign_session_live_state,
        build_live_json_response=build_live_json_response,
    )
    app.register_blueprint(session)
