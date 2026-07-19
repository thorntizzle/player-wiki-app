from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, abort

from .campaign_content_service import CampaignContentError
from .character_editor import CharacterEditValidationError
from .character_service import CharacterStateValidationError
from .character_store import CharacterStateConflictError
from .character_reconciliation import CharacterPublicationConflict


@dataclass(frozen=True)
class CharacterPortraitMutationApiDependencies:
    load_character_record: Callable[..., Any]
    json_error: Callable[..., Any]
    load_json_object: Callable[[], dict[str, Any]]
    validate_character_portrait_payload: Callable[[dict[str, Any]], dict[str, Any]]
    serialize_updated_character: Callable[..., Any]
    finalize_character_definition_for_write: Callable[..., Any]
    has_session_mode_access: Callable[[str, str], bool]
    get_current_user: Callable[[], Any | None]
    get_repository: Callable[[], Any]
    build_character_portrait_asset_ref: Callable[[str, str], str]
    update_character_portrait_profile: Callable[..., Any]
    build_managed_character_import_metadata: Callable[..., Any]
    merge_state_with_definition: Callable[..., dict[str, Any]]
    publish_character_portrait: Callable[..., Any]


def register_character_portrait_mutation_api_routes(
    api: Blueprint,
    *,
    dependencies: CharacterPortraitMutationApiDependencies,
) -> None:
    def character_portrait_upsert(campaign_slug: str, character_slug: str):
        record = dependencies.load_character_record(campaign_slug, character_slug)
        if not dependencies.has_session_mode_access(campaign_slug, character_slug):
            return dependencies.json_error(
                "You do not have permission to update this character from this view.",
                403,
                code="forbidden",
            )

        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.", 401, code="auth_required"
            )

        campaign = dependencies.get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        try:
            payload = dependencies.load_json_object()
            expected_revision = int(payload.get("expected_revision"))
            portrait_payload = dependencies.validate_character_portrait_payload(payload)
            next_asset_ref = dependencies.build_character_portrait_asset_ref(
                character_slug, portrait_payload["filename"]
            )
            definition = dependencies.update_character_portrait_profile(
                record.definition,
                asset_ref=next_asset_ref,
                alt_text=portrait_payload["alt_text"],
                caption=portrait_payload["caption"],
            )
            definition = dependencies.finalize_character_definition_for_write(
                campaign_slug, definition
            )
            import_metadata = dependencies.build_managed_character_import_metadata(
                campaign_slug,
                record.definition.character_slug,
                record.import_metadata,
            )
            merged_state = dependencies.merge_state_with_definition(
                definition, record.state_record.state
            )
            dependencies.publish_character_portrait(
                record,
                definition,
                import_metadata,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
                operation_kind="portrait_upsert",
                desired_asset_ref=next_asset_ref,
                desired_asset_bytes=portrait_payload["data_blob"],
            )
        except (CharacterPublicationConflict, CharacterStateConflictError):
            return dependencies.json_error(
                "This sheet changed in another session. Refresh and try again.",
                409,
                code="state_conflict",
            )
        except (
            CampaignContentError,
            CharacterEditValidationError,
            CharacterStateValidationError,
            TypeError,
            ValueError,
        ) as exc:
            return dependencies.json_error(
                str(exc), 400, code="validation_error"
            )

        return dependencies.serialize_updated_character(
            campaign_slug, character_slug
        )

    def character_portrait_delete(campaign_slug: str, character_slug: str):
        record = dependencies.load_character_record(campaign_slug, character_slug)
        if not dependencies.has_session_mode_access(campaign_slug, character_slug):
            return dependencies.json_error(
                "You do not have permission to update this character from this view.",
                403,
                code="forbidden",
            )

        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.", 401, code="auth_required"
            )

        campaign = dependencies.get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        existing_asset_ref = str(
            (record.definition.profile or {}).get("portrait_asset_ref") or ""
        ).strip()
        if not existing_asset_ref:
            return dependencies.json_error(
                "That character does not currently have a portrait.",
                400,
                code="validation_error",
            )

        try:
            payload = dependencies.load_json_object()
            expected_revision = int(payload.get("expected_revision"))
            definition = dependencies.update_character_portrait_profile(
                record.definition
            )
            definition = dependencies.finalize_character_definition_for_write(
                campaign_slug, definition
            )
            import_metadata = dependencies.build_managed_character_import_metadata(
                campaign_slug,
                record.definition.character_slug,
                record.import_metadata,
            )
            merged_state = dependencies.merge_state_with_definition(
                definition, record.state_record.state
            )
            dependencies.publish_character_portrait(
                record,
                definition,
                import_metadata,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
                operation_kind="portrait_remove",
            )
        except (CharacterPublicationConflict, CharacterStateConflictError):
            return dependencies.json_error(
                "This sheet changed in another session. Refresh and try again.",
                409,
                code="state_conflict",
            )
        except (
            CampaignContentError,
            CharacterEditValidationError,
            CharacterStateValidationError,
            TypeError,
            ValueError,
        ) as exc:
            return dependencies.json_error(
                str(exc), 400, code="validation_error"
            )

        return dependencies.serialize_updated_character(
            campaign_slug, character_slug
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/portrait",
        endpoint="character_portrait_upsert",
        view_func=character_portrait_upsert,
        methods=("PUT",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/portrait",
        endpoint="character_portrait_delete",
        view_func=character_portrait_delete,
        methods=("DELETE",),
    )
