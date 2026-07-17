from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint


@dataclass(frozen=True)
class CharacterXianxiaInventoryItemUpdateApiDependencies:
    api_login_required: Callable[..., object]
    run_character_mutation: Callable[..., object]
    xianxia_inventory_item_payload: Callable[..., dict[str, object]]
    get_character_state_service: Callable[..., object]


def register_character_xianxia_inventory_item_update_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterXianxiaInventoryItemUpdateApiDependencies,
) -> None:
    def character_xianxia_inventory_item_update(
        campaign_slug: str,
        character_slug: str,
        item_id: str,
    ):
        return dependencies.run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: dependencies.get_character_state_service().update_xianxia_inventory_item(
                record,
                item_id,
                dependencies.xianxia_inventory_item_payload(payload),
                expected_revision=int(payload.get("expected_revision")),
                updated_by_user_id=user_id,
            ),
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>",
        endpoint="character_xianxia_inventory_item_update",
        view_func=dependencies.api_login_required(
            character_xianxia_inventory_item_update
        ),
        methods=("PATCH",),
    )
