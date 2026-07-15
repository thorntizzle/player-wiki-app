from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, jsonify, request

from .auth import campaign_scope_access_required
from .system_policy import DND5E_CHARACTER_SPELLCASTING_TOOLS_UNSUPPORTED_MESSAGE


@dataclass(frozen=True)
class CharacterSpellSearchRouteDependencies:
    load_character_context: Callable[..., tuple[object, object]]
    campaign_supports_dnd5e_character_spellcasting_tools: Callable[..., bool]
    load_character_spell_management_support: Callable[..., tuple[object, object]]
    has_session_mode_access: Callable[..., bool]
    search_character_spell_management_options: Callable[..., tuple[list[object], str]]


def register_character_spell_search_route(
    app: Any,
    *,
    dependencies: CharacterSpellSearchRouteDependencies,
) -> None:
    def character_spell_search(campaign_slug: str, character_slug: str):
        campaign, record = dependencies.load_character_context(
            campaign_slug, character_slug
        )
        if not dependencies.has_session_mode_access(campaign_slug, character_slug):
            abort(403)
        if not dependencies.campaign_supports_dnd5e_character_spellcasting_tools(
            campaign
        ):
            return jsonify(
                {
                    "results": [],
                    "message": DND5E_CHARACTER_SPELLCASTING_TOOLS_UNSUPPORTED_MESSAGE,
                }
            ), 404

        spell_catalog, selected_class_rows = (
            dependencies.load_character_spell_management_support(
                campaign_slug,
                record.definition,
            )
        )
        results, message = dependencies.search_character_spell_management_options(
            record.definition,
            spell_catalog=spell_catalog,
            selected_class_rows=selected_class_rows,
            query=request.args.get("q", ""),
            kind=request.args.get("kind", ""),
            target_class_row_id=request.args.get("target_class_row_id", ""),
        )
        return jsonify(
            {
                "results": results,
                "message": message,
            }
        )

    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/spellcasting/spells/search",
        endpoint="character_spell_search",
        view_func=campaign_scope_access_required("characters")(
            character_spell_search
        ),
        methods=("GET",),
    )
