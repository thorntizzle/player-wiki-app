from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint, abort, request


@dataclass(frozen=True)
class CharacterInventoryApiDependencies:
    api_login_required: Callable[..., object]
    run_character_mutation: Callable[..., object]
    is_xianxia_system: Callable[..., object]
    get_character_state_service: Callable[..., object]
    can_manage_campaign_content: Callable[..., bool]


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
            from .character_item_actions import OPERATION, request_confirmation, validate_json_dispatch
            validate_json_dispatch(payload, request.get_data(cache=True))
            if payload.get("operation") == OPERATION:
                confirmed = request_confirmation(payload, raw_json=request.get_data(cache=True))
                return dependencies.get_character_state_service().use_item_action(
                    record, item_id, expected_revision=payload.get("expected_revision"),
                    confirm_attack=confirmed, updated_by_user_id=user_id)
            from .character_item_actions import REACTION_OPERATION, reaction_values
            if payload.get("operation") == REACTION_OPERATION:
                values = reaction_values(payload, raw_json=request.get_data(cache=True))
                return dependencies.get_character_state_service().use_item_action(
                    record, item_id, expected_revision=payload.get("expected_revision"),
                    reaction_values=values, updated_by_user_id=user_id)
            from .character_item_prepared import OPERATIONS as PREPARED_OPERATIONS, request_values as prepared_values
            if type(payload.get("operation")) is str and payload["operation"] in PREPARED_OPERATIONS:
                values = prepared_values(payload, raw_json=request.get_data(cache=True))
                manager = dependencies.can_manage_campaign_content(campaign_slug)
                if payload["operation"] == "prepared_observe" and not manager:
                    abort(403)
                return dependencies.get_character_state_service().prepared_item_action(
                    record, item_id, operation=payload["operation"], expected_revision=payload.get("expected_revision"),
                    values=values, manager_authorized=manager, updated_by_user_id=user_id)
            from .character_item_casting import OPERATIONS, request_values
            if type(payload.get("operation")) is str and payload["operation"] in OPERATIONS:
                manager = dependencies.can_manage_campaign_content(campaign_slug)
                if payload["operation"] in {"storage_initialize", "storage_external"} and not manager:
                    abort(403)
                return dependencies.get_character_state_service().item_spell_action(
                    record, item_id, operation=payload["operation"], expected_revision=int(payload.get("expected_revision")),
                    values=request_values(payload),
                    manager_authorized=manager,
                    updated_by_user_id=user_id)
            if payload.get("operation") == "item_uses":
                confirm = payload.get("confirm_unrecorded") is True
                manager = dependencies.can_manage_campaign_content(campaign_slug)
                if confirm and not manager:
                    abort(403)
                return dependencies.get_character_state_service().update_item_uses(
                    record, item_id, expected_revision=int(payload.get("expected_revision")),
                    current=payload.get("current"), confirm_unrecorded=confirm,
                    manager_authorized=manager, updated_by_user_id=user_id)
            if payload.get("operation") not in (None, "", "quantity"):
                raise ValueError("Choose a supported inventory operation.")
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
