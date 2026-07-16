from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import request

from .auth import campaign_scope_access_required


@dataclass(frozen=True)
class CharacterFeatureStateRouteDependencies:
    run_character_state_mutation: Callable[..., object]
    get_character_state_service: Callable[..., object]


def register_character_feature_state_route(
    app: Any,
    *,
    dependencies: CharacterFeatureStateRouteDependencies,
) -> None:
    def character_feature_state_update(
        campaign_slug: str, character_slug: str, feature_key: str
    ):
        return dependencies.run_character_state_mutation(
            campaign_slug,
            character_slug,
            anchor="character-equipment-state",
            success_message="Feature state updated.",
            action=lambda record, expected_revision, user_id: (
                dependencies.get_character_state_service().update_feature_state(
                    record,
                    feature_key,
                    expected_revision=expected_revision,
                    enabled=request.form.get("enabled") == "1",
                    updated_by_user_id=user_id,
                )
            ),
        )

    scope_required = campaign_scope_access_required("characters")
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/feature-states/<feature_key>",
        endpoint="character_feature_state_update",
        view_func=scope_required(character_feature_state_update),
        methods=("POST",),
    )
