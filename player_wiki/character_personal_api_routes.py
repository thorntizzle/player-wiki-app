from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint


@dataclass(frozen=True)
class CharacterPersonalApiDependencies:
    api_campaign_scope_access_required: Callable[..., object]
    api_login_required: Callable[..., object]
    run_character_mutation: Callable[..., object]
    get_character_state_service: Callable[..., object]


def register_character_personal_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterPersonalApiDependencies,
) -> None:
    def character_personal_update(campaign_slug: str, character_slug: str):
        return dependencies.run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: dependencies.get_character_state_service().update_personal_details(
                record,
                expected_revision=int(payload.get("expected_revision")),
                physical_description_markdown=str(payload.get("physical_description_markdown") or ""),
                background_markdown=str(payload.get("background_markdown") or ""),
                updated_by_user_id=user_id,
            ),
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/personal",
        endpoint="character_personal_update",
        view_func=dependencies.api_campaign_scope_access_required("characters")(
            dependencies.api_login_required(character_personal_update)
        ),
        methods=("PATCH",),
    )
