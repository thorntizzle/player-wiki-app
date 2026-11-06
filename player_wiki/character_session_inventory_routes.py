from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import request, abort

from .auth import campaign_scope_access_required


@dataclass(frozen=True)
class CharacterSessionInventoryRouteDependencies:
    is_xianxia_system: Callable[..., bool]
    get_character_state_service: Callable[..., object]
    run_session_mutation: Callable[..., object]
    can_manage_campaign_content: Callable[..., bool]


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
            from .character_item_actions import OPERATION, request_confirmation
            if OPERATION in request.form.getlist("operation"):
                confirmed = request_confirmation(request.form, html=True)
                return dependencies.get_character_state_service().use_item_action(
                    record, item_id, expected_revision=expected_revision,
                    confirm_attack=confirmed, updated_by_user_id=user_id)
            from .character_item_actions import REACTION_OPERATION, reaction_values
            if REACTION_OPERATION in request.form.getlist("operation"):
                values = reaction_values(request.form, html=True)
                return dependencies.get_character_state_service().use_item_action(
                    record, item_id, expected_revision=expected_revision,
                    reaction_values=values, updated_by_user_id=user_id)
            from .character_item_prepared import OPERATIONS as PREPARED_OPERATIONS, request_values as prepared_values
            if any(value in PREPARED_OPERATIONS for value in request.form.getlist("operation")):
                values = prepared_values(request.form, html=True)
                manager = dependencies.can_manage_campaign_content(campaign_slug)
                if request.form["operation"] == "prepared_observe" and not manager:
                    abort(403)
                return dependencies.get_character_state_service().prepared_item_action(
                    record, item_id, operation=request.form["operation"], expected_revision=expected_revision,
                    values=values, manager_authorized=manager, updated_by_user_id=user_id)
            from .character_item_casting import OPERATIONS, request_values
            if request.form.get("operation") in OPERATIONS:
                manager = dependencies.can_manage_campaign_content(campaign_slug)
                if request.form["operation"] in {"storage_initialize", "storage_external"} and not manager:
                    abort(403)
                return dependencies.get_character_state_service().item_spell_action(
                    record, item_id, operation=request.form["operation"], expected_revision=expected_revision,
                    values=request_values(request.form, html=True),
                    manager_authorized=manager,
                    updated_by_user_id=user_id)
            if request.form.get("operation") == "item_uses":
                confirm = request.form.get("confirm_unrecorded") == "yes"
                manager = dependencies.can_manage_campaign_content(campaign_slug)
                if confirm and not manager:
                    abort(403)
                return dependencies.get_character_state_service().update_item_uses(
                    record, item_id, expected_revision=expected_revision,
                    current=request.form.get("current"), confirm_unrecorded=confirm,
                    manager_authorized=manager, updated_by_user_id=user_id)
            if request.form.get("operation") not in (None, "", "quantity"):
                raise ValueError("Choose a supported inventory operation.")
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
            success_message=("Recorded the choice of 10 instead of the attack d20 and spent one item use. Resolve modifiers and the hit at the table."
                if request.form.get("operation") == "item_attack_d20" else
                "Recorded the reaction and spent one item use. Resolve the trigger and turn effects at the table."
                if request.form.get("operation") == "item_triggered_reaction" else "Inventory updated."),
            action=update_inventory,
        )

    scope_required = campaign_scope_access_required("characters", own_character=True)
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/inventory/<item_id>",
        endpoint="character_session_inventory",
        view_func=scope_required(character_session_inventory),
        methods=("POST",),
    )
