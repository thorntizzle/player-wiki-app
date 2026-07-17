from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint


@dataclass(frozen=True)
class CharacterXianxiaActiveStateApiDependencies:
    api_login_required: Callable[..., object]
    run_character_mutation: Callable[..., object]
    get_character_state_service: Callable[..., object]


def register_character_xianxia_active_state_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterXianxiaActiveStateApiDependencies,
) -> None:
    def character_xianxia_active_state_update(
        campaign_slug: str,
        character_slug: str,
    ):
        return dependencies.run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: dependencies.get_character_state_service().update_xianxia_active_state(
                record,
                expected_revision=int(payload.get("expected_revision")),
                active_stance_name=payload.get("active_stance_name"),
                active_aura_name=payload.get("active_aura_name"),
                updated_by_user_id=user_id,
            ),
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-active-state",
        endpoint="character_xianxia_active_state_update",
        view_func=dependencies.api_login_required(character_xianxia_active_state_update),
        methods=("PATCH",),
    )
