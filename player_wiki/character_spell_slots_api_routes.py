from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint


@dataclass(frozen=True)
class CharacterSpellSlotsApiDependencies:
    api_login_required: Callable[..., object]
    run_character_mutation: Callable[..., object]
    get_character_state_service: Callable[..., object]


def register_character_spell_slots_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterSpellSlotsApiDependencies,
) -> None:
    def character_spell_slots_update(
        campaign_slug: str,
        character_slug: str,
        level: int,
    ):
        return dependencies.run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: dependencies.get_character_state_service().update_spell_slots(
                record,
                level,
                slot_lane_id=str(payload.get("slot_lane_id") or ""),
                expected_revision=int(payload.get("expected_revision")),
                used=payload.get("used"),
                delta_used=payload.get("delta_used"),
                updated_by_user_id=user_id,
            ),
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/spell-slots/<int:level>",
        endpoint="character_spell_slots_update",
        view_func=dependencies.api_login_required(character_spell_slots_update),
        methods=("PATCH",),
    )
