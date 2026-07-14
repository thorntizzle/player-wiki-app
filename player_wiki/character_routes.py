from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, current_app, render_template, request, send_file

from .auth import campaign_scope_access_required
from .campaign_content_service import guess_campaign_asset_media_type
from .system_policy import CHARACTER_ROUTE_LANE_XIANXIA


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


@dataclass(frozen=True)
class CharacterRosterRouteDependencies:
    get_repository: Callable[..., object]
    campaign_supports_native_character_tools: Callable[..., bool]
    campaign_supports_native_character_create: Callable[..., bool]
    native_character_create_lane: Callable[..., str]
    get_character_repository: Callable[..., object]
    present_character_roster: Callable[..., list[dict[str, object]]]
    can_manage_campaign_session: Callable[..., bool]


def _dependencies() -> CharacterRouteDependencies:
    return current_app.extensions["character_route_dependencies"]


def _read_dependencies() -> CharacterReadRouteDependencies:
    return current_app.extensions["character_read_route_dependencies"]


def _portrait_asset_dependencies() -> CharacterPortraitAssetRouteDependencies:
    return current_app.extensions["character_portrait_asset_route_dependencies"]


def _roster_dependencies() -> CharacterRosterRouteDependencies:
    return current_app.extensions["character_roster_route_dependencies"]


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


@campaign_scope_access_required("characters")
def character_roster_view(campaign_slug: str):
    dependencies = _roster_dependencies()
    repository = dependencies.get_repository()
    campaign = repository.get_campaign(campaign_slug)
    if not campaign:
        abort(404)
    native_character_tools_supported = dependencies.campaign_supports_native_character_tools(
        campaign
    )
    native_character_create_supported = dependencies.campaign_supports_native_character_create(
        campaign
    )
    character_create_lane = dependencies.native_character_create_lane(
        getattr(campaign, "system", "")
    )

    query = request.args.get("q", "").strip()
    character_cards = dependencies.present_character_roster(
        dependencies.get_character_repository().list_visible_characters(campaign_slug)
    )
    if query:
        normalized_query = query.lower()
        character_cards = [
            card
            for card in character_cards
            if normalized_query in str(card.get("search_text") or "")
        ]

    return render_template(
        "character_roster.html",
        campaign=campaign,
        character_cards=character_cards,
        query=query,
        result_count=len(character_cards),
        can_create_characters=(
            dependencies.can_manage_campaign_session(campaign_slug)
            and native_character_create_supported
        ),
        can_import_xianxia_characters=(
            dependencies.can_manage_campaign_session(campaign_slug)
            and character_create_lane == CHARACTER_ROUTE_LANE_XIANXIA
        ),
        native_character_tools_supported=native_character_tools_supported,
        native_character_create_supported=native_character_create_supported,
        character_create_lane=character_create_lane,
        active_nav="characters",
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


def register_character_roster_route(
    app: Any,
    *,
    get_repository: Callable[..., object],
    campaign_supports_native_character_tools: Callable[..., bool],
    campaign_supports_native_character_create: Callable[..., bool],
    native_character_create_lane: Callable[..., str],
    get_character_repository: Callable[..., object],
    present_character_roster: Callable[..., list[dict[str, object]]],
    can_manage_campaign_session: Callable[..., bool],
) -> None:
    app.extensions["character_roster_route_dependencies"] = CharacterRosterRouteDependencies(
        get_repository=get_repository,
        campaign_supports_native_character_tools=campaign_supports_native_character_tools,
        campaign_supports_native_character_create=campaign_supports_native_character_create,
        native_character_create_lane=native_character_create_lane,
        get_character_repository=get_character_repository,
        present_character_roster=present_character_roster,
        can_manage_campaign_session=can_manage_campaign_session,
    )
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters",
        endpoint="character_roster_view",
        view_func=character_roster_view,
        methods=("GET",),
    )
