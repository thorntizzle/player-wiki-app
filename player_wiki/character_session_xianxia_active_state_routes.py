from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import request

from .auth import campaign_scope_access_required


@dataclass(frozen=True)
class CharacterSessionXianxiaActiveStateRouteDependencies:
    run_session_mutation: Callable[..., object]
    get_character_state_service: Callable[..., object]


def register_character_session_xianxia_active_state_route(
    app: Any,
    *,
    dependencies: CharacterSessionXianxiaActiveStateRouteDependencies,
) -> None:
    def character_session_xianxia_active_state(
        campaign_slug: str,
        character_slug: str,
    ):
        def update_active_state(record, expected_revision, user_id):
            return dependencies.get_character_state_service().update_xianxia_active_state(
                record,
                expected_revision=expected_revision,
                active_stance_name=request.form.get("active_stance_name"),
                active_aura_name=request.form.get("active_aura_name"),
                updated_by_user_id=user_id,
            )

        return dependencies.run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="session-active-state",
            success_message="Active Stance and Aura updated.",
            action=update_active_state,
        )

    scope_required = campaign_scope_access_required("characters")
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-active-state",
        endpoint="character_session_xianxia_active_state",
        view_func=scope_required(character_session_xianxia_active_state),
        methods=("POST",),
    )
