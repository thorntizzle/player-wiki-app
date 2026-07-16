from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import request

from .auth import campaign_scope_access_required


@dataclass(frozen=True)
class CharacterSessionInventoryRouteDependencies:
    is_xianxia_system: Callable[..., bool]
    get_character_state_service: Callable[..., object]
    run_session_mutation: Callable[..., object]


def register_character_session_inventory_route(
    app: Any,
    *,
    dependencies: CharacterSessionInventoryRouteDependencies,
) -> None:
    def character_session_inventory(
        campaign_slug: str,
        character_slug: str,
        item_id: str,
    ):
        def update_inventory(record, expected_revision, user_id):
            if dependencies.is_xianxia_system(record.definition.system):
                return dependencies.get_character_state_service().update_xianxia_inventory_quantity(
                    record,
                    item_id,
                    expected_revision=expected_revision,
                    quantity=request.form.get("quantity"),
                    delta=request.form.get("delta"),
                    updated_by_user_id=user_id,
                )
            return dependencies.get_character_state_service().update_inventory_quantity(
                record,
                item_id,
                expected_revision=expected_revision,
                quantity=request.form.get("quantity"),
                delta=request.form.get("delta"),
                updated_by_user_id=user_id,
            )

        return dependencies.run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="session-inventory",
            success_message="Inventory updated.",
            action=update_inventory,
        )

    scope_required = campaign_scope_access_required("characters")
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/inventory/<item_id>",
        endpoint="character_session_inventory",
        view_func=scope_required(character_session_inventory),
        methods=("POST",),
    )
