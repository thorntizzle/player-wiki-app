from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint


@dataclass(frozen=True)
class CharacterXianxiaInventoryItemRemoveApiDependencies:
    api_login_required: Callable[..., object]
    run_character_mutation: Callable[..., object]
    get_character_state_service: Callable[..., object]


def register_character_xianxia_inventory_item_remove_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterXianxiaInventoryItemRemoveApiDependencies,
) -> None:
    def character_xianxia_inventory_item_remove(
        campaign_slug: str,
        character_slug: str,
        item_id: str,
    ):
        return dependencies.run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: dependencies.get_character_state_service().remove_xianxia_inventory_item(
                record,
                item_id,
                expected_revision=int(payload.get("expected_revision")),
                updated_by_user_id=user_id,
            ),
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>",
        endpoint="character_xianxia_inventory_item_remove",
        view_func=dependencies.api_login_required(
            character_xianxia_inventory_item_remove
        ),
        methods=("DELETE",),
    )
