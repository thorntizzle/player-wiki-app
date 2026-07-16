from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import request

from .auth import campaign_scope_access_required


@dataclass(frozen=True)
class CharacterSessionCurrencyRouteDependencies:
    run_session_mutation: Callable[..., object]
    get_character_state_service: Callable[..., object]


def register_character_session_currency_route(
    app: Any,
    *,
    dependencies: CharacterSessionCurrencyRouteDependencies,
) -> None:
    def character_session_currency(campaign_slug: str, character_slug: str):
        return dependencies.run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="session-currency",
            success_message="Currency updated.",
            action=lambda record, expected_revision, user_id: dependencies.get_character_state_service().update_currency(
                record,
                expected_revision=expected_revision,
                values={
                    key: request.form.get(key)
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
                delta=request.form.get("delta"),
                updated_by_user_id=user_id,
            ),
        )

    scope_required = campaign_scope_access_required("characters")
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/currency",
        endpoint="character_session_currency",
        view_func=scope_required(character_session_currency),
        methods=("POST",),
    )
