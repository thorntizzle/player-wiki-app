from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import request

from .auth import campaign_scope_access_required


@dataclass(frozen=True)
class CharacterSessionResourceRouteDependencies:
    run_session_mutation: Callable[..., object]
    get_character_state_service: Callable[..., object]


def register_character_session_resource_route(
    app: Any,
    *,
    dependencies: CharacterSessionResourceRouteDependencies,
) -> None:
    def character_session_resource(
        campaign_slug: str,
        character_slug: str,
        resource_id: str,
    ):
        return dependencies.run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="session-resources",
            success_message="Resource updated.",
            action=lambda record, expected_revision, user_id: dependencies.get_character_state_service().update_resource(
                record,
                resource_id,
                expected_revision=expected_revision,
                current=request.form.get("current"),
                delta=request.form.get("delta"),
                updated_by_user_id=user_id,
            ),
        )

    scope_required = campaign_scope_access_required("characters")
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/resources/<resource_id>",
        endpoint="character_session_resource",
        view_func=scope_required(character_session_resource),
        methods=("POST",),
    )
