from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint


@dataclass(frozen=True)
class CharacterInventoryApiDependencies:
    api_login_required: Callable[..., object]
    run_character_mutation: Callable[..., object]
    is_xianxia_system: Callable[..., object]
    get_character_state_service: Callable[..., object]


def register_character_inventory_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterInventoryApiDependencies,
) -> None:
    def character_inventory_update(
        campaign_slug: str,
        character_slug: str,
        item_id: str,
    ):
        def update_inventory(record, payload, user_id):
            if dependencies.is_xianxia_system(record.definition.system):
                return dependencies.get_character_state_service().update_xianxia_inventory_quantity(
                    record,
                    item_id,
                    expected_revision=int(payload.get("expected_revision")),
                    quantity=payload.get("quantity"),
                    delta=payload.get("delta"),
                    updated_by_user_id=user_id,
                )
            return dependencies.get_character_state_service().update_inventory_quantity(
                record,
                item_id,
                expected_revision=int(payload.get("expected_revision")),
                quantity=payload.get("quantity"),
                delta=payload.get("delta"),
                updated_by_user_id=user_id,
            )

        return dependencies.run_character_mutation(
            campaign_slug,
            character_slug,
            update_inventory,
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/inventory/<item_id>",
        endpoint="character_inventory_update",
        view_func=dependencies.api_login_required(character_inventory_update),
        methods=("PATCH",),
    )
