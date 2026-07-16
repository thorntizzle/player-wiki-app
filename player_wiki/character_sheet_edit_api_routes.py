from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint


@dataclass(frozen=True)
class CharacterSheetEditApiDependencies:
    api_campaign_scope_access_required: Callable[..., object]
    api_login_required: Callable[..., object]
    run_character_mutation: Callable[..., object]
    get_character_state_service: Callable[..., object]


def register_character_sheet_edit_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterSheetEditApiDependencies,
) -> None:
    def character_sheet_edit_update(campaign_slug: str, character_slug: str):
        return dependencies.run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: dependencies.get_character_state_service().save_character_sheet_edit(
                record,
                expected_revision=int(payload.get("expected_revision")),
                vitals=payload.get("vitals"),
                resources=payload.get("resources"),
                spell_slots=payload.get("spell_slots"),
                inventory=payload.get("inventory"),
                currency=payload.get("currency"),
                notes=payload.get("notes"),
                personal=payload.get("personal"),
                updated_by_user_id=user_id,
            ),
            forbidden_message="You do not have permission to edit Character page state for this character.",
            conflict_message=(
                "This sheet changed before your batch save finished. Refresh and review the latest sheet before "
                "saving again. Session Character, Combat, or another tab may have changed nearby fields first; "
                "nothing was auto-merged."
            ),
        )

    scope_required = dependencies.api_campaign_scope_access_required("characters")
    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/sheet-edit",
        endpoint="character_sheet_edit_update",
        view_func=scope_required(
            dependencies.api_login_required(character_sheet_edit_update)
        ),
        methods=("PATCH",),
    )
