from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, request

from .auth import campaign_scope_access_required


@dataclass(frozen=True)
class CharacterSessionItemActionRouteDependencies:
    load_character_context: Callable[..., object]
    has_session_mode_access: Callable[..., bool]
    campaign_supports_dnd5e_character_spellcasting_tools: Callable[..., bool]
    redirect_unsupported_dnd5e_character_spellcasting_tools: Callable[..., object]
    parse_item_action_slot_selection: Callable[..., tuple[str, int]]
    get_character_state_service: Callable[..., object]
    resolve_projected_item_use_action: Callable[..., dict[str, object]]
    run_session_mutation: Callable[..., object]


def register_character_session_item_action_route(
    app: Any,
    *,
    dependencies: CharacterSessionItemActionRouteDependencies,
) -> None:
    def character_session_item_action_use(
        campaign_slug: str,
        character_slug: str,
        action_id: str,
    ):
        campaign, _ = dependencies.load_character_context(
            campaign_slug,
            character_slug,
        )
        if not dependencies.has_session_mode_access(campaign_slug, character_slug):
            abort(403)
        if not dependencies.campaign_supports_dnd5e_character_spellcasting_tools(
            campaign
        ):
            return dependencies.redirect_unsupported_dnd5e_character_spellcasting_tools(
                campaign_slug,
                character_slug,
            )

        def _action(record, expected_revision, user_id):
            slot_lane_id, slot_level = dependencies.parse_item_action_slot_selection(
                request.form.get("slot_selection")
            )
            if not slot_level:
                slot_level = int(request.form.get("slot_level") or 0)
                slot_lane_id = request.form.get("slot_lane_id", "")
            return dependencies.get_character_state_service().use_spell_slot_item_action(
                record,
                dependencies.resolve_projected_item_use_action(
                    campaign_slug,
                    campaign,
                    record,
                    action_id,
                ),
                choice_id=request.form.get("choice_id", ""),
                slot_level=slot_level,
                slot_lane_id=slot_lane_id,
                expected_revision=expected_revision,
                updated_by_user_id=user_id,
            )

        return dependencies.run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="character-item-use-actions",
            success_message="Item action used.",
            action=_action,
        )

    scope_required = campaign_scope_access_required("characters")
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/item-actions/<action_id>/use",
        endpoint="character_session_item_action_use",
        view_func=scope_required(character_session_item_action_use),
        methods=("POST",),
    )
