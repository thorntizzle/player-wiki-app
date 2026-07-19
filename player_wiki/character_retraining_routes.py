from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, current_app, flash, redirect, request, url_for

from .auth import campaign_scope_access_required
from .character_editor import CharacterEditValidationError
from .character_service import CharacterStateValidationError
from .character_store import CharacterStateConflictError


@dataclass(frozen=True)
class CharacterRetrainingRouteDependencies:
    load_character_context: Callable[..., tuple[object, object]]
    campaign_supports_native_character_tools: Callable[..., bool]
    redirect_unsupported_native_character_tools: Callable[..., object]
    get_systems_service: Callable[..., object]
    list_builder_campaign_page_records: Callable[..., list[object]]
    get_campaign_page_store: Callable[..., object]
    build_character_item_catalog: Callable[..., dict[str, object]]
    render_character_retraining_page: Callable[..., object]
    parse_expected_revision: Callable[..., int]
    finalize_character_definition_for_write: Callable[..., object]
    has_session_mode_access: Callable[..., bool]
    character_advancement_unsupported_message: Callable[..., str]
    native_level_up_readiness: Callable[..., dict[str, object]]
    build_linked_feature_authoring_support: Callable[..., dict[str, object]]
    _build_spell_catalog: Callable[..., dict[str, object]]
    _list_campaign_enabled_entries: Callable[..., list[object]]
    build_native_character_retraining_context: Callable[..., dict[str, object]]
    get_current_user: Callable[..., object]
    apply_native_character_retraining: Callable[
        ..., tuple[object, object, dict[str, int]]
    ]
    merge_state_with_definition: Callable[..., dict[str, object]]
    character_publication_coordinator: object


def register_character_retraining_route(
    app: Any,
    *,
    dependencies: CharacterRetrainingRouteDependencies,
) -> None:
    def character_retraining_view(campaign_slug: str, character_slug: str):
        if not dependencies.has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        campaign, record = dependencies.load_character_context(
            campaign_slug, character_slug
        )
        if not dependencies.campaign_supports_native_character_tools(campaign):
            return dependencies.redirect_unsupported_native_character_tools(
                campaign_slug,
                character_slug=character_slug,
                message=dependencies.character_advancement_unsupported_message(
                    campaign.system
                ),
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
        if not bool(linked_feature_authoring.get("supported")):
            flash(
                str(
                    linked_feature_authoring.get("message")
                    or "This character cannot use retraining yet."
                ),
                "error",
            )
            return redirect(
                url_for(
                    "character_read_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
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
        retraining_context = (
            dependencies.build_native_character_retraining_context(
                record.definition,
                campaign_page_records=campaign_page_records,
                form_values=form_values if request.method == "POST" else None,
                optionalfeature_catalog=optionalfeature_catalog,
                spell_catalog=spell_catalog,
                item_catalog=item_catalog,
            )
        )
        retraining_context["state_revision"] = record.state_record.revision
        if not list(retraining_context.get("feature_rows") or []):
            flash(
                "This character does not currently have any supported structured retraining options.",
                "error",
            )
            return redirect(
                url_for(
                    "character_read_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
            )

        if request.method != "POST":
            return dependencies.render_character_retraining_page(
                campaign_slug,
                character_slug,
                retraining_context,
                campaign_page_records=campaign_page_records,
            )

        user = dependencies.get_current_user()
        if user is None:
            abort(403)

        try:
            expected_revision = dependencies.parse_expected_revision()
            definition, import_metadata, inventory_quantity_overrides = (
                dependencies.apply_native_character_retraining(
                    campaign_slug,
                    record.definition,
                    record.import_metadata,
                    campaign_page_records=campaign_page_records,
                    form_values=form_values,
                    optionalfeature_catalog=optionalfeature_catalog,
                    spell_catalog=spell_catalog,
                    item_catalog=item_catalog,
                    systems_service=current_app.extensions["systems_service"],
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
            return dependencies.render_character_retraining_page(
                campaign_slug,
                character_slug,
                retraining_context,
                campaign_page_records=campaign_page_records,
                status_code=409,
            )
        except (
            CharacterEditValidationError,
            CharacterStateValidationError,
            ValueError,
        ) as exc:
            flash(str(exc), "error")
            return dependencies.render_character_retraining_page(
                campaign_slug,
                character_slug,
                retraining_context,
                campaign_page_records=campaign_page_records,
                status_code=400,
            )

        flash("Retraining saved.", "success")
        return redirect(
            url_for(
                "character_read_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
                page="features",
            )
        )

    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/retraining",
        endpoint="character_retraining_view",
        view_func=campaign_scope_access_required("characters")(
            character_retraining_view
        ),
        methods=("GET", "POST"),
    )
