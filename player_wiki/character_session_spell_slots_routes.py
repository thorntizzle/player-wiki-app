from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import request

from .auth import campaign_scope_access_required


@dataclass(frozen=True)
class CharacterSessionSpellSlotsRouteDependencies:
    admit_session_mutation: Callable[..., object]
    campaign_supports_dnd5e_character_spellcasting_tools: Callable[..., bool]
    redirect_unsupported_dnd5e_character_spellcasting_tools: Callable[..., object]
    run_session_mutation: Callable[..., object]
    get_character_state_service: Callable[..., object]


def register_character_session_spell_slots_route(
    app: Any,
    *,
    dependencies: CharacterSessionSpellSlotsRouteDependencies,
) -> None:
    def character_session_spell_slots(
        campaign_slug: str,
        character_slug: str,
        level: int,
    ):
        admission = dependencies.admit_session_mutation(
            campaign_slug,
            character_slug,
        )
        if not dependencies.campaign_supports_dnd5e_character_spellcasting_tools(
            admission.campaign
        ):
            return dependencies.redirect_unsupported_dnd5e_character_spellcasting_tools(
                campaign_slug,
                character_slug,
            )

        return dependencies.run_session_mutation(
            campaign_slug,
            character_slug,
            admission=admission,
            anchor="session-spell-slots",
            success_message="Spell slot usage updated.",
            action=lambda record, expected_revision, user_id: dependencies.get_character_state_service().update_spell_slots(
                record,
                level,
                slot_lane_id=request.form.get("slot_lane_id", ""),
                expected_revision=expected_revision,
                used=request.form.get("used"),
                delta_used=request.form.get("delta_used"),
                updated_by_user_id=user_id,
            ),
        )

    scope_required = campaign_scope_access_required("characters")
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/spell-slots/<int:level>",
        endpoint="character_session_spell_slots",
        view_func=scope_required(character_session_spell_slots),
        methods=("POST",),
    )
