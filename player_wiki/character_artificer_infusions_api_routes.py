from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint, current_app


@dataclass(frozen=True)
class CharacterArtificerInfusionsApiDependencies:
    api_login_required: Callable[..., object]
    build_character_item_catalog: Callable[..., object]
    run_character_definition_mutation: Callable[..., object]
    apply_artificer_infusion_state_edit: Callable[..., object]


def register_character_artificer_infusions_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterArtificerInfusionsApiDependencies,
) -> None:
    def character_artificer_infusions_update(
        campaign_slug: str,
        character_slug: str,
    ):
        item_catalog = dependencies.build_character_item_catalog(campaign_slug)
        return dependencies.run_character_definition_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: dependencies.apply_artificer_infusion_state_edit(
                campaign_slug,
                record.definition,
                record.import_metadata,
                current_state=record.state_record.state,
                item_catalog=item_catalog,
                systems_service=current_app.extensions["systems_service"],
                active_entries=list(payload.get("active") or []),
            ),
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/artificer-infusions",
        endpoint="character_artificer_infusions_update",
        view_func=dependencies.api_login_required(character_artificer_infusions_update),
        methods=("PATCH",),
    )
