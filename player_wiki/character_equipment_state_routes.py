from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .auth import campaign_scope_access_required


@dataclass(frozen=True)
class CharacterEquipmentStateRouteDependencies:
    build_character_item_catalog: Callable[..., object]
    get_systems_service: Callable[..., object]
    build_equipment_state_form_values: Callable[..., dict[str, object]]
    run_character_definition_mutation: Callable[..., object]
    build_shared_equipment_state_update_result: Callable[..., object]


def register_character_equipment_state_route(
    app: Any,
    *,
    dependencies: CharacterEquipmentStateRouteDependencies,
) -> None:
    def character_equipment_state_update(
        campaign_slug: str, character_slug: str, item_id: str
    ):
        item_catalog = dependencies.build_character_item_catalog(campaign_slug)

        def _action(record):
            return dependencies.build_shared_equipment_state_update_result(
                campaign_slug,
                record,
                item_id,
                item_catalog=item_catalog,
                systems_service=dependencies.get_systems_service(),
                values=dependencies.build_equipment_state_form_values(),
            )

        return dependencies.run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="character-equipment-state",
            success_message="Equipment state updated.",
            action=_action,
        )

    scope_required = campaign_scope_access_required("characters")
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/equipment/<item_id>/state",
        endpoint="character_equipment_state_update",
        view_func=scope_required(character_equipment_state_update),
        methods=("POST",),
    )
