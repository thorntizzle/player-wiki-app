from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint, current_app


@dataclass(frozen=True)
class CharacterEquipmentStateApiDependencies:
    api_login_required: Callable[..., object]
    build_character_item_catalog: Callable[..., object]
    run_character_definition_mutation: Callable[..., object]
    build_shared_equipment_state_update_result: Callable[..., object]


def register_character_equipment_state_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterEquipmentStateApiDependencies,
) -> None:
    def character_equipment_state_update(
        campaign_slug: str,
        character_slug: str,
        item_id: str,
    ):
        item_catalog = dependencies.build_character_item_catalog(campaign_slug)
        return dependencies.run_character_definition_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: dependencies.build_shared_equipment_state_update_result(
                campaign_slug,
                record,
                item_id,
                item_catalog=item_catalog,
                systems_service=current_app.extensions["systems_service"],
                values={
                    "is_equipped": bool(payload.get("is_equipped")),
                    "is_attuned": bool(payload.get("is_attuned")),
                    "weapon_wield_mode": payload.get("weapon_wield_mode"),
                },
            ),
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/equipment/<item_id>",
        endpoint="character_equipment_state_update",
        view_func=dependencies.api_login_required(character_equipment_state_update),
        methods=("PATCH",),
    )
