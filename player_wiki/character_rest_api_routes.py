from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint


@dataclass(frozen=True)
class CharacterRestApiDependencies:
    api_login_required: Callable[..., object]
    run_character_mutation: Callable[..., object]
    get_character_state_service: Callable[..., object]
    optional_json_hit_dice_current: Callable[..., object]


def register_character_rest_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterRestApiDependencies,
) -> None:
    def character_rest_apply(campaign_slug: str, character_slug: str, rest_type: str):
        return dependencies.run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: dependencies.get_character_state_service().apply_rest(
                record,
                rest_type,
                expected_revision=int(payload.get("expected_revision")),
                current_hp=payload.get("current_hp"),
                hit_dice_current=dependencies.optional_json_hit_dice_current(payload),
                updated_by_user_id=user_id,
            ),
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/rest/<rest_type>",
        endpoint="character_rest_apply",
        view_func=dependencies.api_login_required(character_rest_apply),
        methods=("POST",),
    )
