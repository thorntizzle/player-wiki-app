from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, current_app, request

from .character_editor import CharacterEditValidationError
from .character_service import CharacterStateValidationError
from .character_store import CharacterStateConflictError


@dataclass(frozen=True)
class CharacterRetrainingApiDependencies:
    api_campaign_scope_access_required: Callable[[str], Callable[[Callable[..., Any]], Callable[..., Any]]]
    api_login_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    load_character_retraining_target: Callable[[str, str], tuple[Any, Any, Any | None]]
    normalize_character_retraining_values: Callable[[dict[str, Any]], dict[str, str]]
    character_retraining_availability: Callable[..., dict[str, Any]]
    serialize_character_retraining_response: Callable[..., Any]
    character_retraining_is_supported: Callable[[dict[str, Any]], bool]
    json_error: Callable[..., Any]
    load_json_object: Callable[[], dict[str, Any]]
    build_character_retraining_context_parts: Callable[..., tuple[Any, ...]]
    load_character_record: Callable[[str, str], Any]
    finalize_character_definition_for_write: Callable[[str, Any], Any]
    get_current_user: Callable[[], Any | None]
    apply_native_character_retraining: Callable[..., tuple[Any, Any, dict[str, int]]]
    merge_state_with_definition: Callable[..., dict[str, Any]]
    character_publication_coordinator: object


def register_character_retraining_api_routes(
    api: Blueprint,
    *,
    dependencies: CharacterRetrainingApiDependencies,
) -> None:
    def character_retraining_read(campaign_slug: str, character_slug: str):
        campaign, record, access_error = dependencies.load_character_retraining_target(
            campaign_slug, character_slug
        )
        if access_error is not None:
            return access_error
        form_values = dependencies.normalize_character_retraining_values(
            dict(request.args)
        )
        readiness = dependencies.character_retraining_availability(
            campaign_slug,
            campaign,
            record,
            form_values=form_values,
        )
        return dependencies.serialize_character_retraining_response(
            campaign_slug, campaign, record, readiness=readiness
        )

    def character_retraining_submit(campaign_slug: str, character_slug: str):
        campaign, record, access_error = dependencies.load_character_retraining_target(
            campaign_slug, character_slug
        )
        if access_error is not None:
            return access_error
        readiness = dependencies.character_retraining_availability(
            campaign_slug, campaign, record
        )
        if not dependencies.character_retraining_is_supported(readiness):
            return dependencies.json_error(
                str(
                    readiness.get("message")
                    or "This character is not ready for retraining."
                ),
                400,
                code="unsupported_campaign_system",
            )
        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.", 401, code="auth_required"
            )

        try:
            payload = dependencies.load_json_object()
            expected_revision = int(payload.get("expected_revision"))
            form_values = dependencies.normalize_character_retraining_values(payload)
            (
                _retraining_context,
                campaign_page_records,
                optionalfeature_catalog,
                spell_catalog,
                item_catalog,
            ) = dependencies.build_character_retraining_context_parts(
                campaign_slug,
                campaign,
                record,
                form_values=form_values,
            )
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
                campaign_slug, definition
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
            return dependencies.json_error(
                "This sheet changed in another session. Refresh and try again.",
                409,
                code="state_conflict",
            )
        except (
            CharacterEditValidationError,
            CharacterStateValidationError,
            TypeError,
            ValueError,
        ) as exc:
            return dependencies.json_error(
                str(exc), 400, code="validation_error"
            )

        refreshed_record = dependencies.load_character_record(
            campaign_slug, character_slug
        )
        refreshed_readiness = dependencies.character_retraining_availability(
            campaign_slug, campaign, refreshed_record
        )
        return dependencies.serialize_character_retraining_response(
            campaign_slug,
            campaign,
            refreshed_record,
            readiness=refreshed_readiness,
            message="Retraining saved.",
        )

    character_retraining_read_view = (
        dependencies.api_campaign_scope_access_required("characters")(
            dependencies.api_login_required(character_retraining_read)
        )
    )
    character_retraining_submit_view = (
        dependencies.api_campaign_scope_access_required("characters")(
            dependencies.api_login_required(character_retraining_submit)
        )
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/retraining",
        endpoint="character_retraining_read",
        view_func=character_retraining_read_view,
        methods=("GET",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/retraining",
        endpoint="character_retraining_submit",
        view_func=character_retraining_submit_view,
        methods=("POST",),
    )
