from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import request

from .auth import campaign_scope_access_required


@dataclass(frozen=True)
class CharacterSessionXianxiaInventoryRouteDependencies:
    run_session_mutation: Callable[..., object]
    get_character_state_service: Callable[..., object]
    _xianxia_inventory_item_payload_from_form: Callable[..., dict[str, object]]


def register_character_session_xianxia_inventory_routes(
    app: Any,
    *,
    dependencies: CharacterSessionXianxiaInventoryRouteDependencies,
) -> None:
    def character_session_xianxia_inventory_add(
        campaign_slug: str,
        character_slug: str,
    ):
        return dependencies.run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="xianxia-inventory",
            success_message="Inventory item added.",
            action=lambda record, expected_revision, user_id: dependencies.get_character_state_service().add_xianxia_inventory_item(
                record,
                dependencies._xianxia_inventory_item_payload_from_form(),
                expected_revision=expected_revision,
                updated_by_user_id=user_id,
            ),
        )

    def character_session_xianxia_inventory_update(
        campaign_slug: str,
        character_slug: str,
        item_id: str,
    ):
        return dependencies.run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="xianxia-inventory",
            success_message="Inventory item updated.",
            action=lambda record, expected_revision, user_id: dependencies.get_character_state_service().update_xianxia_inventory_item(
                record,
                item_id,
                dependencies._xianxia_inventory_item_payload_from_form(),
                expected_revision=expected_revision,
                updated_by_user_id=user_id,
            ),
        )

    def character_session_xianxia_inventory_remove(
        campaign_slug: str,
        character_slug: str,
        item_id: str,
    ):
        return dependencies.run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="xianxia-inventory",
            success_message="Inventory item removed.",
            action=lambda record, expected_revision, user_id: dependencies.get_character_state_service().remove_xianxia_inventory_item(
                record,
                item_id,
                expected_revision=expected_revision,
                updated_by_user_id=user_id,
            ),
        )

    def character_session_xianxia_inventory_equipped(
        campaign_slug: str,
        character_slug: str,
        item_id: str,
    ):
        return dependencies.run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="xianxia-inventory",
            success_message="Equipment state updated.",
            action=lambda record, expected_revision, user_id: dependencies.get_character_state_service().update_xianxia_inventory_equipped_state(
                record,
                item_id,
                expected_revision=expected_revision,
                is_equipped=request.form.get("is_equipped") == "1",
                updated_by_user_id=user_id,
            ),
        )

    scope_required = campaign_scope_access_required("characters")
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/add",
        endpoint="character_session_xianxia_inventory_add",
        view_func=scope_required(character_session_xianxia_inventory_add),
        methods=("POST",),
    )
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>/update",
        endpoint="character_session_xianxia_inventory_update",
        view_func=scope_required(character_session_xianxia_inventory_update),
        methods=("POST",),
    )
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>/remove",
        endpoint="character_session_xianxia_inventory_remove",
        view_func=scope_required(character_session_xianxia_inventory_remove),
        methods=("POST",),
    )
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>/equipped",
        endpoint="character_session_xianxia_inventory_equipped",
        view_func=scope_required(character_session_xianxia_inventory_equipped),
        methods=("POST",),
    )
