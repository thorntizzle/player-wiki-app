from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, current_app, flash, redirect, request, url_for

from .auth import campaign_scope_access_required
from .character_editor import CharacterEditValidationError
from .character_service import CharacterStateValidationError
from .character_store import CharacterStateConflictError


@dataclass(frozen=True)
class CharacterEditRouteDependencies:
    load_character_context: Callable[..., tuple[object, object]]
    campaign_supports_native_character_tools: Callable[..., bool]
    redirect_unsupported_native_character_tools: Callable[..., object]
    get_systems_service: Callable[..., object]
    list_builder_campaign_page_records: Callable[..., list[object]]
    get_campaign_page_store: Callable[..., object]
    build_character_item_catalog: Callable[..., dict[str, object]]
    render_character_edit_page: Callable[..., object]
    parse_expected_revision: Callable[..., int]
    finalize_character_definition_for_write: Callable[..., object]
    has_session_mode_access: Callable[..., bool]
    native_level_up_readiness: Callable[..., dict[str, object]]
    build_linked_feature_authoring_support: Callable[..., dict[str, object]]
    _build_spell_catalog: Callable[..., dict[str, object]]
    _list_campaign_enabled_entries: Callable[..., list[object]]
    build_native_character_edit_context: Callable[..., dict[str, object]]
    get_current_user: Callable[..., object]
    apply_native_character_edits: Callable[..., tuple[object, object, dict[str, int]]]
    merge_state_with_definition: Callable[..., dict[str, object]]
    character_publication_coordinator: object


def register_character_edit_route(
    app: Any,
    *,
    dependencies: CharacterEditRouteDependencies,
) -> None:
    def character_edit_view(campaign_slug: str, character_slug: str):
        if not dependencies.has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        campaign, record = dependencies.load_character_context(
            campaign_slug, character_slug
        )
        if not dependencies.campaign_supports_native_character_tools(campaign):
            return dependencies.redirect_unsupported_native_character_tools(
                campaign_slug,
                character_slug=character_slug,
            )
        level_up_readiness = dependencies.native_level_up_readiness(
            dependencies.get_systems_service(),
            campaign_slug,
            record.definition,
            campaign_page_records=dependencies.list_builder_campaign_page_records(
                campaign_slug, campaign
            ),
        )
        linked_feature_authoring = (
            dependencies.build_linked_feature_authoring_support(
                record.definition,
                readiness=level_up_readiness,
            )
        )
        campaign_page_records = [
            page_record
            for page_record in dependencies.get_campaign_page_store().list_page_records(
                campaign_slug
            )
            if page_record.page.published
            and page_record.page.reveal_after_session <= campaign.current_session
            and str(page_record.page.section or "").strip() != "Sessions"
        ]
        spell_catalog = dependencies._build_spell_catalog(
            dependencies._list_campaign_enabled_entries(
                current_app.extensions["systems_service"],
                campaign_slug,
                "spell",
            )
        )
        optionalfeature_catalog = {
            str(entry.slug or "").strip(): entry
            for entry in dependencies._list_campaign_enabled_entries(
                current_app.extensions["systems_service"],
                campaign_slug,
                "optionalfeature",
            )
            if str(entry.slug or "").strip()
        }
        item_catalog = dependencies.build_character_item_catalog(campaign_slug)
        form_values = dict(
            request.form if request.method == "POST" else request.args
        )
        edit_context = dependencies.build_native_character_edit_context(
            record.definition,
            campaign_page_records=campaign_page_records,
            form_values=form_values if request.method == "POST" else None,
            state_notes=dict((record.state_record.state or {}).get("notes") or {}),
            optionalfeature_catalog=optionalfeature_catalog,
            spell_catalog=spell_catalog,
            item_catalog=item_catalog,
            linked_feature_authoring_support=linked_feature_authoring,
        )
        edit_context["state_revision"] = record.state_record.revision

        if request.method != "POST":
            return dependencies.render_character_edit_page(
                campaign_slug,
                character_slug,
                edit_context,
                campaign_page_records=campaign_page_records,
            )

        user = dependencies.get_current_user()
        if user is None:
            abort(403)

        try:
            expected_revision = dependencies.parse_expected_revision()
            definition, import_metadata, inventory_quantity_overrides = (
                dependencies.apply_native_character_edits(
                    campaign_slug,
                    record.definition,
                    record.import_metadata,
                    campaign_page_records=campaign_page_records,
                    form_values=form_values,
                    optionalfeature_catalog=optionalfeature_catalog,
                    spell_catalog=spell_catalog,
                    item_catalog=item_catalog,
                    systems_service=current_app.extensions["systems_service"],
                    linked_feature_authoring_support=linked_feature_authoring,
                )
            )
            definition = dependencies.finalize_character_definition_for_write(
                campaign_slug,
                definition,
                campaign=campaign,
            )
            removed_resource_ids: set[str] = set()
            source_type = str(
                (record.definition.source or {}).get("source_type") or ""
            ).strip()
            if source_type and source_type != "native_character_builder":
                previous_resource_ids = {
                    str(template.get("id") or "").strip()
                    for template in list(record.definition.resource_templates or [])
                    if str(template.get("id") or "").strip()
                }
                current_resource_ids = {
                    str(template.get("id") or "").strip()
                    for template in list(definition.resource_templates or [])
                    if str(template.get("id") or "").strip()
                }
                removed_resource_ids = previous_resource_ids - current_resource_ids
            merged_state = dependencies.merge_state_with_definition(
                definition,
                record.state_record.state,
                inventory_quantity_overrides=inventory_quantity_overrides,
                removed_resource_ids=removed_resource_ids,
            )
            if (
                "physical_description_markdown" in form_values
                or "background_markdown" in form_values
            ):
                notes_payload = dict(merged_state.get("notes") or {})
                notes_payload["physical_description_markdown"] = str(
                    form_values.get("physical_description_markdown") or ""
                )
                notes_payload["background_markdown"] = str(
                    form_values.get("background_markdown") or ""
                )
                merged_state["notes"] = notes_payload
            dependencies.character_publication_coordinator.update(
                record,
                definition,
                import_metadata,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
        except CharacterStateConflictError:
            flash(
                "This sheet changed in another session. Refresh the page and try again.",
                "error",
            )
            return dependencies.render_character_edit_page(
                campaign_slug,
                character_slug,
                edit_context,
                campaign_page_records=campaign_page_records,
                status_code=409,
            )
        except (
            CharacterEditValidationError,
            CharacterStateValidationError,
            ValueError,
        ) as exc:
            flash(str(exc), "error")
            return dependencies.render_character_edit_page(
                campaign_slug,
                character_slug,
                edit_context,
                campaign_page_records=campaign_page_records,
                status_code=400,
            )

        flash("Character details updated.", "success")
        return redirect(
            url_for(
                "character_edit_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            )
        )

    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/edit",
        endpoint="character_edit_view",
        view_func=campaign_scope_access_required("characters")(
            character_edit_view
        ),
        methods=("GET", "POST"),
    )
