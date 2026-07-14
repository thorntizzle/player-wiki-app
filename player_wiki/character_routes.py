from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import current_app, render_template, request

from .auth import campaign_scope_access_required


@dataclass(frozen=True)
class CharacterRouteDependencies:
    build_campaign_session_character_page_context: Callable[..., dict[str, object]]
    build_campaign_session_shell_context: Callable[..., dict[str, object]]


@dataclass(frozen=True)
class CharacterReadRouteDependencies:
    render_character_page: Callable[..., object]


def _dependencies() -> CharacterRouteDependencies:
    return current_app.extensions["character_route_dependencies"]


def _read_dependencies() -> CharacterReadRouteDependencies:
    return current_app.extensions["character_read_route_dependencies"]


@campaign_scope_access_required("session")
def campaign_session_character_view(campaign_slug: str):
    dependencies = _dependencies()
    if request.args.get("fragment") == "1":
        context = dependencies.build_campaign_session_character_page_context(campaign_slug)
        return render_template(
            "_session_character_panel.html",
            **context,
            session_character_fragment=True,
        )
    context = dependencies.build_campaign_session_shell_context(
        campaign_slug,
        active_pane="character",
    )
    return render_template("session_character.html", **context)


@campaign_scope_access_required("characters")
def character_read_view(campaign_slug: str, character_slug: str):
    return _read_dependencies().render_character_page(campaign_slug, character_slug)


def register_character_routes(
    app: Any,
    *,
    build_campaign_session_character_page_context: Callable[..., dict[str, object]],
    build_campaign_session_shell_context: Callable[..., dict[str, object]],
) -> None:
    app.extensions["character_route_dependencies"] = CharacterRouteDependencies(
        build_campaign_session_character_page_context=(
            build_campaign_session_character_page_context
        ),
        build_campaign_session_shell_context=build_campaign_session_shell_context,
    )
    app.add_url_rule(
        "/campaigns/<campaign_slug>/session/character",
        endpoint="campaign_session_character_view",
        view_func=campaign_session_character_view,
        methods=("GET",),
    )


def register_character_read_route(
    app: Any,
    *,
    render_character_page: Callable[..., object],
) -> None:
    app.extensions["character_read_route_dependencies"] = CharacterReadRouteDependencies(
        render_character_page=render_character_page,
    )
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>",
        endpoint="character_read_view",
        view_func=character_read_view,
        methods=("GET",),
    )
