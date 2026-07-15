from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, jsonify, request


@dataclass(frozen=True)
class CharacterCreateContextApiDependencies:
    ensure_character_authoring_access: Callable[[str], tuple[Any, Any | None]]
    build_character_create_payload: Callable[..., dict[str, Any]]


def register_character_create_context_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterCreateContextApiDependencies,
) -> None:
    def character_create_context(campaign_slug: str):
        campaign, access_error = dependencies.ensure_character_authoring_access(
            campaign_slug
        )
        if access_error is not None:
            return access_error
        return jsonify(
            dependencies.build_character_create_payload(
                campaign_slug,
                campaign,
                dict(request.args),
            )
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/create",
        endpoint="character_create_context",
        view_func=character_create_context,
        methods=("GET",),
    )
