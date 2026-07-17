from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint


@dataclass(frozen=True)
class CharacterXianxiaInventoryAddApiDependencies:
    api_login_required: Callable[..., object]
    run_character_mutation: Callable[..., object]
    xianxia_inventory_item_payload: Callable[..., dict[str, object]]
    get_character_state_service: Callable[..., object]


def register_character_xianxia_inventory_add_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterXianxiaInventoryAddApiDependencies,
) -> None:
    def character_xianxia_inventory_add(
        campaign_slug: str,
        character_slug: str,
    ):
        return dependencies.run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: dependencies.get_character_state_service().add_xianxia_inventory_item(
                record,
                dependencies.xianxia_inventory_item_payload(payload),
                expected_revision=int(payload.get("expected_revision")),
                updated_by_user_id=user_id,
            ),
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory",
        endpoint="character_xianxia_inventory_add",
        view_func=dependencies.api_login_required(character_xianxia_inventory_add),
        methods=("POST",),
    )
