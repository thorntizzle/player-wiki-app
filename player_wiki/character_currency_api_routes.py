from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint


@dataclass(frozen=True)
class CharacterCurrencyApiDependencies:
    api_login_required: Callable[..., object]
    run_character_mutation: Callable[..., object]
    get_character_state_service: Callable[..., object]


def register_character_currency_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterCurrencyApiDependencies,
) -> None:
    def character_currency_update(campaign_slug: str, character_slug: str):
        return dependencies.run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: dependencies.get_character_state_service().update_currency(
                record,
                expected_revision=int(payload.get("expected_revision")),
                values={
                    key: payload.get(key)
                    for key in (
                        "cp",
                        "sp",
                        "ep",
                        "gp",
                        "pp",
                        "coin",
                        "supply",
                        "spirit_stones",
                    )
                },
                updated_by_user_id=user_id,
            ),
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/currency",
        endpoint="character_currency_update",
        view_func=dependencies.api_login_required(character_currency_update),
        methods=("PATCH",),
    )
