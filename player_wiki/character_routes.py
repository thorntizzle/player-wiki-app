from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, current_app, render_template, request, send_file

from .auth import campaign_scope_access_required
from .campaign_content_service import guess_campaign_asset_media_type


@dataclass(frozen=True)
class CharacterRouteDependencies:
    build_campaign_session_character_page_context: Callable[..., dict[str, object]]
    build_campaign_session_shell_context: Callable[..., dict[str, object]]


@dataclass(frozen=True)
class CharacterReadRouteDependencies:
    render_character_page: Callable[..., object]


@dataclass(frozen=True)
class CharacterPortraitAssetRouteDependencies:
    load_character_context: Callable[..., tuple[object, object]]
    build_character_portrait_context: Callable[..., dict[str, str] | None]
    get_campaign_asset_file: Callable[..., object | None]


def _dependencies() -> CharacterRouteDependencies:
    return current_app.extensions["character_route_dependencies"]


def _read_dependencies() -> CharacterReadRouteDependencies:
    return current_app.extensions["character_read_route_dependencies"]


def _portrait_asset_dependencies() -> CharacterPortraitAssetRouteDependencies:
    return current_app.extensions["character_portrait_asset_route_dependencies"]


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


@campaign_scope_access_required("characters")
def character_portrait_asset(campaign_slug: str, character_slug: str):
    dependencies = _portrait_asset_dependencies()
    campaign, record = dependencies.load_character_context(campaign_slug, character_slug)
    portrait = dependencies.build_character_portrait_context(campaign, record.definition)
    if portrait is None:
        abort(404)
    asset_file = dependencies.get_campaign_asset_file(campaign, portrait["asset_ref"])
    if asset_file is None:
        abort(404)
    return send_file(
        asset_file,
        mimetype=guess_campaign_asset_media_type(asset_file),
        download_name=asset_file.name,
    )


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


def register_character_portrait_asset_route(
    app: Any,
    *,
    load_character_context: Callable[..., tuple[object, object]],
    build_character_portrait_context: Callable[..., dict[str, str] | None],
    get_campaign_asset_file: Callable[..., object | None],
) -> None:
    app.extensions[
        "character_portrait_asset_route_dependencies"
    ] = CharacterPortraitAssetRouteDependencies(
        load_character_context=load_character_context,
        build_character_portrait_context=build_character_portrait_context,
        get_campaign_asset_file=get_campaign_asset_file,
    )
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/portrait",
        endpoint="character_portrait_asset",
        view_func=character_portrait_asset,
        methods=("GET",),
    )
