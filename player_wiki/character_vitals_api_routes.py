from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint


@dataclass(frozen=True)
class CharacterVitalsApiDependencies:
    api_login_required: Callable[..., object]
    run_character_mutation: Callable[..., object]
    get_character_state_service: Callable[..., object]
    optional_json_hit_dice_current: Callable[..., object]


def register_character_vitals_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterVitalsApiDependencies,
) -> None:
    def character_vitals_update(campaign_slug: str, character_slug: str):
        return dependencies.run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: dependencies.get_character_state_service().update_vitals(
                record,
                expected_revision=int(payload.get("expected_revision")),
                current_hp=payload.get("current_hp"),
                temp_hp=payload.get("temp_hp"),
                current_stance=payload.get("current_stance"),
                temp_stance=payload.get("temp_stance"),
                current_jing=payload.get("current_jing"),
                current_qi=payload.get("current_qi"),
                current_shen=payload.get("current_shen"),
                current_yin=payload.get("current_yin"),
                current_yang=payload.get("current_yang"),
                current_dao=payload.get("current_dao"),
                hit_dice_current=dependencies.optional_json_hit_dice_current(payload),
                hp_delta=payload.get("hp_delta"),
                temp_hp_delta=payload.get("temp_hp_delta"),
                clear_temp_hp=bool(payload.get("clear_temp_hp")),
                updated_by_user_id=user_id,
            ),
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/vitals",
        endpoint="character_vitals_update",
        view_func=dependencies.api_login_required(character_vitals_update),
        methods=("PATCH",),
    )
