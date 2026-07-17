from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint


@dataclass(frozen=True)
class CharacterItemActionApiDependencies:
    api_login_required: Callable[..., object]
    run_character_mutation: Callable[..., object]
    parse_item_action_slot_selection: Callable[..., object]
    get_character_state_service: Callable[..., object]
    resolve_projected_item_use_action: Callable[..., object]


def register_character_item_action_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterItemActionApiDependencies,
) -> None:
    def character_item_action_use(
        campaign_slug: str,
        character_slug: str,
        action_id: str,
    ):
        def use_action(record, payload, user_id):
            slot_lane_id = str(payload.get("slot_lane_id") or "")
            slot_level = int(payload.get("slot_level") or 0)
            if payload.get("slot_selection"):
                slot_lane_id, slot_level = dependencies.parse_item_action_slot_selection(
                    payload.get("slot_selection")
                )
            return dependencies.get_character_state_service().use_spell_slot_item_action(
                record,
                dependencies.resolve_projected_item_use_action(
                    campaign_slug,
                    record,
                    action_id,
                ),
                choice_id=str(payload.get("choice_id") or ""),
                slot_level=slot_level,
                slot_lane_id=slot_lane_id,
                expected_revision=int(payload.get("expected_revision")),
                updated_by_user_id=user_id,
            )

        return dependencies.run_character_mutation(
            campaign_slug,
            character_slug,
            use_action,
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "session/item-actions/<action_id>/use",
        endpoint="character_item_action_use",
        view_func=dependencies.api_login_required(character_item_action_use),
        methods=("POST",),
    )
