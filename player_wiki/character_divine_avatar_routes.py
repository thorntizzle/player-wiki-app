from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import request

from .auth import campaign_scope_access_required
from .divine_avatar_forms import divine_avatar_action_success_message


_AVATAR_ACTIONS_REQUIRING_ACKNOWLEDGEMENT = {
    "cooldown_complete",
    "correct_end_cost",
    "end",
    "resolve_end_cost",
    "undo_last_action",
}


def _normalized_action(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _end_cost_correction_from_form() -> dict[str, Any]:
    correction_fields = {
        "rounds": "correction_rounds",
        "exhaustion_gained": "correction_exhaustion_gained",
        "radiant_damage_dice": "correction_radiant_damage_dice",
        "radiant_damage_applied": "correction_radiant_damage_applied",
        "reason": "correction_reason",
    }
    return {
        correction_key: value
        for correction_key, form_field in correction_fields.items()
        if (value := request.form.get(form_field)) is not None and str(value).strip()
    }


@dataclass(frozen=True)
class CharacterDivineAvatarRouteDependencies:
    run_character_state_mutation: Callable[..., object]
    get_character_state_service: Callable[..., object]
    build_proposed_state_validator: Callable[..., object | None] | None = None


def register_character_divine_avatar_route(
    app: Any,
    *,
    dependencies: CharacterDivineAvatarRouteDependencies,
) -> None:
    def character_divine_avatar_form_update(
        campaign_slug: str,
        character_slug: str,
        form_key: str,
        action: str,
    ):
        normalized_action = _normalized_action(action)
        acknowledgement_required = (
            normalized_action in _AVATAR_ACTIONS_REQUIRING_ACKNOWLEDGEMENT
        )
        confirmed = request.form.get("confirmed") == "1" and (
            not acknowledgement_required
            or request.form.get("destructive_acknowledgement") == "1"
        )

        def update_avatar_state(record, expected_revision, user_id):
            validator = (
                dependencies.build_proposed_state_validator(
                    campaign_slug,
                    record,
                    normalized_action,
                )
                if dependencies.build_proposed_state_validator is not None
                else None
            )
            validator_arguments = (
                {"proposed_state_validator": validator}
                if validator is not None
                else {}
            )
            return dependencies.get_character_state_service().update_divine_avatar_form(
                record,
                form_key,
                normalized_action,
                expected_revision=expected_revision,
                confirmed=confirmed,
                resolution_id=request.form.get("resolution_id", ""),
                radiant_damage_applied=request.form.get("radiant_damage_applied"),
                correction=_end_cost_correction_from_form(),
                updated_by_user_id=user_id,
                **validator_arguments,
            )

        return dependencies.run_character_state_mutation(
            campaign_slug,
            character_slug,
            anchor="character-divine-avatar-forms",
            success_message=divine_avatar_action_success_message(normalized_action),
            invalidate_live_views=True,
            action=update_avatar_state,
        )

    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/divine-avatar-forms/<form_key>/<action>",
        endpoint="character_divine_avatar_form_update",
        view_func=campaign_scope_access_required("characters")(
            character_divine_avatar_form_update
        ),
        methods=("POST",),
    )
