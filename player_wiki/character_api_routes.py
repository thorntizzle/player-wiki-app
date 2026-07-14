from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, abort, jsonify


@dataclass(frozen=True)
class CharacterDetailApiDependencies:
    can_access_campaign_scope: Callable[[str, str], bool]
    has_session_mode_access: Callable[[str, str], bool]
    get_current_user: Callable[[], Any | None]
    json_error: Callable[..., Any]
    load_character_record: Callable[..., Any]
    get_repository: Callable[[], Any]
    serialize_character_record: Callable[..., dict[str, Any]]
    serialize_character_links: Callable[..., dict[str, Any]]


def register_character_detail_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterDetailApiDependencies,
) -> None:
    def character_detail(campaign_slug: str, character_slug: str):
        if not dependencies.can_access_campaign_scope(
            campaign_slug, "characters"
        ) and not dependencies.has_session_mode_access(
            campaign_slug,
            character_slug,
        ):
            if dependencies.get_current_user() is None:
                return dependencies.json_error(
                    "Authentication required.", 401, code="auth_required"
                )
            return dependencies.json_error(
                "You do not have access to this character.",
                403,
                code="forbidden",
            )
        record = dependencies.load_character_record(campaign_slug, character_slug)
        campaign = dependencies.get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)
        return jsonify(
            {
                "ok": True,
                "character": dependencies.serialize_character_record(
                    campaign_slug, record
                ),
                "links": dependencies.serialize_character_links(
                    campaign_slug, campaign, record
                ),
            }
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>",
        endpoint="character_detail",
        view_func=character_detail,
        methods=("GET",),
    )
