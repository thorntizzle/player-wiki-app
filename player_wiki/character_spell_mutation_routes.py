from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, request

from .auth import campaign_scope_access_required


@dataclass(frozen=True)
class CharacterSpellMutationRouteDependencies:
    load_character_context: Callable[..., tuple[object, object]]
    campaign_supports_dnd5e_character_spellcasting_tools: Callable[..., bool]
    redirect_unsupported_dnd5e_character_spellcasting_tools: Callable[..., object]
    load_character_spell_management_support: Callable[..., tuple[object, object]]
    get_systems_service: Callable[..., object]
    run_character_definition_mutation: Callable[..., object]
    has_session_mode_access: Callable[..., bool]
    apply_character_spell_management_edit: Callable[..., tuple[object, object]]


def register_character_spell_mutation_routes(
    app: Any,
    *,
    dependencies: CharacterSpellMutationRouteDependencies,
) -> None:
    def character_spell_add(campaign_slug: str, character_slug: str):
        campaign, _ = dependencies.load_character_context(
            campaign_slug, character_slug
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

        def _action(record):
            spell_catalog, selected_class_rows = (
                dependencies.load_character_spell_management_support(
                    campaign_slug,
                    record.definition,
                )
            )
            return dependencies.apply_character_spell_management_edit(
                campaign_slug,
                record.definition,
                record.import_metadata,
                spell_catalog=spell_catalog,
                selected_class_rows=selected_class_rows,
                systems_service=dependencies.get_systems_service(),
                operation="add",
                kind=request.form.get("kind", ""),
                selected_value=request.form.get("selected_value", ""),
                target_class_row_id=request.form.get("target_class_row_id", ""),
            )

        return dependencies.run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="character-spell-manager",
            success_message="Spell list updated.",
            action=_action,
        )

    def character_spell_update(campaign_slug: str, character_slug: str):
        campaign, _ = dependencies.load_character_context(
            campaign_slug, character_slug
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

        def _action(record):
            spell_catalog, selected_class_rows = (
                dependencies.load_character_spell_management_support(
                    campaign_slug,
                    record.definition,
                )
            )
            return dependencies.apply_character_spell_management_edit(
                campaign_slug,
                record.definition,
                record.import_metadata,
                spell_catalog=spell_catalog,
                selected_class_rows=selected_class_rows,
                systems_service=dependencies.get_systems_service(),
                operation="update",
                spell_key=request.form.get("spell_key", ""),
                prepared_value=request.form.get("prepared_value", ""),
                target_class_row_id=request.form.get("target_class_row_id", ""),
            )

        return dependencies.run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="character-spell-manager",
            success_message="Prepared spell selection updated.",
            action=_action,
        )

    def character_spell_remove(campaign_slug: str, character_slug: str):
        campaign, _ = dependencies.load_character_context(
            campaign_slug, character_slug
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

        def _action(record):
            spell_catalog, selected_class_rows = (
                dependencies.load_character_spell_management_support(
                    campaign_slug,
                    record.definition,
                )
            )
            return dependencies.apply_character_spell_management_edit(
                campaign_slug,
                record.definition,
                record.import_metadata,
                spell_catalog=spell_catalog,
                selected_class_rows=selected_class_rows,
                systems_service=dependencies.get_systems_service(),
                operation="remove",
                spell_key=request.form.get("spell_key", ""),
                target_class_row_id=request.form.get("target_class_row_id", ""),
            )

        return dependencies.run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="character-spell-manager",
            success_message="Spell list updated.",
            action=_action,
        )

    route = "/campaigns/<campaign_slug>/characters/<character_slug>/spellcasting"
    character_scope = campaign_scope_access_required("characters")
    app.add_url_rule(
        f"{route}/add",
        endpoint="character_spell_add",
        view_func=character_scope(character_spell_add),
        methods=("POST",),
    )
    app.add_url_rule(
        f"{route}/update",
        endpoint="character_spell_update",
        view_func=character_scope(character_spell_update),
        methods=("POST",),
    )
    app.add_url_rule(
        f"{route}/remove",
        endpoint="character_spell_remove",
        view_func=character_scope(character_spell_remove),
        methods=("POST",),
    )
