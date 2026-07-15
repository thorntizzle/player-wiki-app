from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, current_app

from .character_service import CharacterStateValidationError
from .character_store import CharacterStateConflictError


@dataclass(frozen=True)
class CharacterCultivationApiDependencies:
    api_campaign_scope_access_required: Callable[[str], Callable[[Callable[..., Any]], Callable[..., Any]]]
    api_login_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    load_character_cultivation_target: Callable[[str, str], tuple[Any, Any, Any | None]]
    serialize_character_cultivation_response: Callable[..., Any]
    character_cultivation_is_supported: Callable[[Any, Any], bool]
    json_error: Callable[..., Any]
    load_json_object: Callable[[], dict[str, Any]]
    apply_xianxia_cultivation_action: Callable[..., tuple[Any, str, str]]
    load_character_record: Callable[[str, str], Any]
    finalize_character_definition_for_write: Callable[[str, Any], Any]
    get_current_user: Callable[[], Any | None]
    build_managed_character_import_metadata: Callable[..., Any]
    merge_state_with_definition: Callable[..., dict[str, Any]]
    load_campaign_character_config: Callable[[Any, str], Any]
    write_yaml: Callable[[Any, dict[str, Any]], None]


def register_character_cultivation_api_routes(
    api: Blueprint,
    *,
    dependencies: CharacterCultivationApiDependencies,
) -> None:
    def character_cultivation_read(campaign_slug: str, character_slug: str):
        campaign, record, access_error = dependencies.load_character_cultivation_target(
            campaign_slug, character_slug
        )
        if access_error is not None:
            return access_error
        return dependencies.serialize_character_cultivation_response(
            campaign_slug, campaign, record
        )

    def character_cultivation_action(campaign_slug: str, character_slug: str):
        campaign, record, access_error = dependencies.load_character_cultivation_target(
            campaign_slug, character_slug
        )
        if access_error is not None:
            return access_error
        if not dependencies.character_cultivation_is_supported(campaign, record):
            return dependencies.json_error(
                "Cultivation is only available for Xianxia character sheets.",
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
            definition, success_message, anchor = (
                dependencies.apply_xianxia_cultivation_action(
                    campaign_slug,
                    record,
                    payload,
                )
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
                definition,
                record.state_record.state,
            )
            current_app.extensions["character_state_store"].replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
            config = dependencies.load_campaign_character_config(
                current_app.config["CAMPAIGNS_DIR"], campaign_slug
            )
            character_dir = config.characters_dir / character_slug
            dependencies.write_yaml(
                character_dir / "definition.yaml", definition.to_dict()
            )
            dependencies.write_yaml(
                character_dir / "import.yaml", import_metadata.to_dict()
            )
        except CharacterStateConflictError:
            return dependencies.json_error(
                "This sheet changed in another session. Refresh and try again.",
                409,
                code="state_conflict",
            )
        except (CharacterStateValidationError, TypeError, ValueError) as exc:
            return dependencies.json_error(
                str(exc), 400, code="validation_error"
            )

        refreshed_record = dependencies.load_character_record(
            campaign_slug, character_slug
        )
        return dependencies.serialize_character_cultivation_response(
            campaign_slug,
            campaign,
            refreshed_record,
            message=success_message,
            anchor=anchor,
        )

    character_cultivation_read_view = (
        dependencies.api_campaign_scope_access_required("characters")(
            dependencies.api_login_required(character_cultivation_read)
        )
    )
    character_cultivation_action_view = (
        dependencies.api_campaign_scope_access_required("characters")(
            dependencies.api_login_required(character_cultivation_action)
        )
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/cultivation",
        endpoint="character_cultivation_read",
        view_func=character_cultivation_read_view,
        methods=("GET",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/cultivation",
        endpoint="character_cultivation_action",
        view_func=character_cultivation_action_view,
        methods=("POST",),
    )
