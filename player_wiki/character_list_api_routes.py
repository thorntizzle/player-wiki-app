from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, abort, jsonify, request


@dataclass(frozen=True)
class CharacterListApiDependencies:
    get_repository: Callable[[], Any]
    can_access_campaign_scope: Callable[[str, str], bool]
    get_owned_character_slugs: Callable[[str], set[str]]
    get_current_user: Callable[[], Any | None]
    json_error: Callable[..., Any]
    get_character_repository: Callable[[], Any]
    serialize_character_summary: Callable[..., dict[str, Any]]
    serialize_campaign: Callable[..., dict[str, Any]]
    serialize_character_roster_tools: Callable[..., dict[str, Any]]
    serialize_character_roster_links: Callable[..., dict[str, Any]]


def register_character_list_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterListApiDependencies,
) -> None:
    def character_list(campaign_slug: str):
        campaign = dependencies.get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        can_access_character_roster = dependencies.can_access_campaign_scope(
            campaign_slug, "characters"
        )
        owned_character_slugs = dependencies.get_owned_character_slugs(campaign_slug)
        if not can_access_character_roster and not owned_character_slugs:
            if dependencies.get_current_user() is None:
                return dependencies.json_error(
                    "Authentication required.", 401, code="auth_required"
                )
            return dependencies.json_error(
                "You do not have access to campaign characters.",
                403,
                code="forbidden",
            )

        records = dependencies.get_character_repository().list_visible_characters(
            campaign_slug
        )
        if not can_access_character_roster:
            records = [
                record
                for record in records
                if record.definition.character_slug in owned_character_slugs
            ]
        query = request.args.get("q", "").strip()
        character_cards = [
            dependencies.serialize_character_summary(campaign, record)
            for record in records
        ]
        if query:
            normalized_query = query.lower()
            character_cards = [
                card
                for card in character_cards
                if normalized_query in str(card.get("search_text") or "")
            ]
        return jsonify(
            {
                "ok": True,
                "campaign": dependencies.serialize_campaign(campaign),
                "characters": character_cards,
                "query": query,
                "result_count": len(character_cards),
                "tools": dependencies.serialize_character_roster_tools(
                    campaign_slug, campaign
                ),
                "links": dependencies.serialize_character_roster_links(
                    campaign_slug, campaign
                ),
            }
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters",
        endpoint="character_list",
        view_func=character_list,
        methods=("GET",),
    )
