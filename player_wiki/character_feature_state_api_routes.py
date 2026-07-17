from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint


@dataclass(frozen=True)
class CharacterFeatureStateApiDependencies:
    api_login_required: Callable[..., object]
    run_character_mutation: Callable[..., object]
    get_character_state_service: Callable[..., object]


def register_character_feature_state_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterFeatureStateApiDependencies,
) -> None:
    def character_feature_state_update(
        campaign_slug: str,
        character_slug: str,
        feature_key: str,
    ):
        return dependencies.run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: dependencies.get_character_state_service().update_feature_state(
                record,
                feature_key,
                expected_revision=int(payload.get("expected_revision")),
                enabled=bool(payload.get("enabled")),
                updated_by_user_id=user_id,
            ),
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/feature-states/<feature_key>",
        endpoint="character_feature_state_update",
        view_func=dependencies.api_login_required(character_feature_state_update),
        methods=("PATCH",),
    )
