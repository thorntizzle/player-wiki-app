from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import request

from .auth import campaign_scope_access_required


@dataclass(frozen=True)
class CharacterSessionVitalsRouteDependencies:
    run_session_mutation: Callable[..., object]
    get_character_state_service: Callable[..., object]
    parse_hit_dice_current_values: Callable[..., object]


def register_character_session_vitals_route(
    app: Any,
    *,
    dependencies: CharacterSessionVitalsRouteDependencies,
) -> None:
    def character_session_vitals(campaign_slug: str, character_slug: str):
        return dependencies.run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="session-vitals",
            success_message="Vitals updated.",
            action=lambda record, expected_revision, user_id: (
                dependencies.get_character_state_service().update_vitals(
                    record,
                    expected_revision=expected_revision,
                    current_hp=request.form.get("current_hp"),
                    temp_hp=request.form.get("temp_hp"),
                    current_stance=request.form.get("current_stance"),
                    temp_stance=request.form.get("temp_stance"),
                    current_jing=request.form.get("current_jing"),
                    current_qi=request.form.get("current_qi"),
                    current_shen=request.form.get("current_shen"),
                    current_yin=request.form.get("current_yin"),
                    current_yang=request.form.get("current_yang"),
                    current_dao=request.form.get("current_dao"),
                    hit_dice_current=dependencies.parse_hit_dice_current_values(),
                    hp_delta=request.form.get("hp_delta"),
                    temp_hp_delta=request.form.get("temp_hp_delta"),
                    clear_temp_hp=request.form.get("clear_temp_hp") == "1",
                    updated_by_user_id=user_id,
                )
            ),
        )

    scope_required = campaign_scope_access_required("characters")
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/vitals",
        endpoint="character_session_vitals",
        view_func=scope_required(character_session_vitals),
        methods=("POST",),
    )
