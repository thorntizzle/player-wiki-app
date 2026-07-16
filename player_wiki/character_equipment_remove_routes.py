from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .auth import campaign_scope_access_required


@dataclass(frozen=True)
class CharacterEquipmentRemoveRouteDependencies:
    build_character_item_catalog: Callable[..., object]
    get_systems_service: Callable[..., object]
    run_character_definition_mutation: Callable[..., object]
    apply_equipment_catalog_edit: Callable[..., object]


def register_character_equipment_remove_route(
    app: Any,
    *,
    dependencies: CharacterEquipmentRemoveRouteDependencies,
) -> None:
    def character_equipment_remove(
        campaign_slug: str, character_slug: str, item_id: str
    ):
        item_catalog = dependencies.build_character_item_catalog(campaign_slug)
        return dependencies.run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="character-inventory-manager",
            success_message="Inventory item removed.",
            action=lambda record: dependencies.apply_equipment_catalog_edit(
                campaign_slug,
                record.definition,
                record.import_metadata,
                item_catalog=item_catalog,
                systems_service=dependencies.get_systems_service(),
                remove_item_id=item_id,
            ),
        )

    scope_required = campaign_scope_access_required("characters")
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/"
        "equipment/<item_id>/remove",
        endpoint="character_equipment_remove",
        view_func=scope_required(character_equipment_remove),
        methods=("POST",),
    )
