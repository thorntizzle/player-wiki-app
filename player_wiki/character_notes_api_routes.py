from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint


@dataclass(frozen=True)
class CharacterNotesApiDependencies:
    api_login_required: Callable[..., object]
    run_character_mutation: Callable[..., object]
    get_character_state_service: Callable[..., object]


def register_character_notes_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterNotesApiDependencies,
) -> None:
    def character_notes_update(campaign_slug: str, character_slug: str):
        return dependencies.run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: dependencies.get_character_state_service().update_player_notes(
                record,
                expected_revision=int(payload.get("expected_revision")),
                notes_markdown=str(payload.get("player_notes_markdown") or ""),
                updated_by_user_id=user_id,
            ),
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/notes",
        endpoint="character_notes_update",
        view_func=dependencies.api_login_required(character_notes_update),
        methods=("PATCH",),
    )
