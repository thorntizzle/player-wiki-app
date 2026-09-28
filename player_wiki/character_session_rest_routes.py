from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, request

from .auth import campaign_scope_access_required
from .system_policy import is_dnd_5e_system


@dataclass(frozen=True)
class CharacterSessionRestRouteDependencies:
    load_session_character_context: Callable[..., object]
    campaign_supports_character_session_routes: Callable[..., object]
    redirect_to_character_mode: Callable[..., object]
    ensure_active_session_for_session_character_mutation: Callable[..., object]
    run_session_mutation: Callable[..., object]
    get_character_state_service: Callable[..., object]
    parse_hit_dice_current_values: Callable[..., object]


def register_character_session_rest_route(
    app: Any,
    *,
    dependencies: CharacterSessionRestRouteDependencies,
) -> None:
    def character_session_rest(campaign_slug: str, character_slug: str, rest_type: str):
        loaded_context = dependencies.load_session_character_context(campaign_slug, character_slug)
        campaign = loaded_context.campaign
        if not dependencies.campaign_supports_character_session_routes(campaign):
            abort(404)
        if request.form.get("confirm_rest", "") != "1":
            return dependencies.redirect_to_character_mode(
                campaign_slug,
                character_slug,
                anchor="session-rest",
                loaded_context=loaded_context,
            )

        inactive_session_redirect = dependencies.ensure_active_session_for_session_character_mutation(
            campaign_slug,
            character_slug,
            anchor="session-rest",
            loaded_context=loaded_context,
        )
        if inactive_session_redirect is not None:
            return inactive_session_redirect

        def apply_confirmed_rest(record, expected_revision, user_id):
            adjustments = {}
            if is_dnd_5e_system(campaign.system) and is_dnd_5e_system(record.definition.system):
                adjustments = {
                    "current_hp": request.form.get("current_hp"),
                    "hit_dice_current": dependencies.parse_hit_dice_current_values(),
                }
            return dependencies.get_character_state_service().apply_rest(
                record,
                rest_type,
                expected_revision=expected_revision,
                updated_by_user_id=user_id,
                **adjustments,
            )

        return dependencies.run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="session-rest",
            loaded_context=loaded_context,
            success_message=f"{rest_type.strip().title()} rest applied.",
            action=apply_confirmed_rest,
        )

    scope_required = campaign_scope_access_required("characters", own_character=True)
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/rest/<rest_type>",
        endpoint="character_session_rest",
        view_func=scope_required(character_session_rest),
        methods=("POST",),
    )
