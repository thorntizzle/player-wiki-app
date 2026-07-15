from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, current_app, request

from .character_builder import CharacterBuildError
from .character_service import CharacterStateValidationError
from .character_store import CharacterStateConflictError


@dataclass(frozen=True)
class CharacterLevelUpApiDependencies:
    api_login_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    load_character_level_up_target: Callable[[str, str], tuple[Any, Any, Any | None]]
    character_level_up_readiness: Callable[[str, Any, Any], dict[str, Any]]
    character_level_up_is_supported: Callable[[dict[str, Any]], bool]
    serialize_character_level_up_response: Callable[..., Any]
    normalize_character_level_up_values: Callable[[dict[str, Any]], dict[str, str]]
    build_character_level_up_context_parts: Callable[..., dict[str, Any]]
    json_error: Callable[..., Any]
    load_json_object: Callable[[], dict[str, Any]]
    load_character_record: Callable[[str, str], Any]
    finalize_character_definition_for_write: Callable[[str, Any], Any]
    get_current_user: Callable[[], Any | None]
    build_native_level_up_character_definition: Callable[..., tuple[Any, Any, int]]
    merge_state_with_definition: Callable[..., dict[str, Any]]
    load_campaign_character_config: Callable[[Any, str], Any]
    write_yaml: Callable[[Any, dict[str, Any]], None]


def register_character_level_up_api_routes(
    api: Blueprint,
    *,
    dependencies: CharacterLevelUpApiDependencies,
) -> None:
    def character_level_up_read(campaign_slug: str, character_slug: str):
        campaign, record, access_error = dependencies.load_character_level_up_target(
            campaign_slug, character_slug
        )
        if access_error is not None:
            return access_error
        readiness = dependencies.character_level_up_readiness(
            campaign_slug, campaign, record
        )
        if not dependencies.character_level_up_is_supported(readiness):
            return dependencies.serialize_character_level_up_response(
                campaign_slug, campaign, record, readiness=readiness
            )
        form_values = dependencies.normalize_character_level_up_values(
            dict(request.args)
        )
        try:
            level_up_context = dependencies.build_character_level_up_context_parts(
                campaign_slug,
                campaign,
                record,
                form_values=form_values,
            )
        except CharacterBuildError as exc:
            readiness = {"status": "unsupported", "message": str(exc)}
            return dependencies.serialize_character_level_up_response(
                campaign_slug, campaign, record, readiness=readiness
            )
        return dependencies.serialize_character_level_up_response(
            campaign_slug,
            campaign,
            record,
            readiness=readiness,
            level_up_context=level_up_context,
        )

    def character_level_up_submit(campaign_slug: str, character_slug: str):
        campaign, record, access_error = dependencies.load_character_level_up_target(
            campaign_slug, character_slug
        )
        if access_error is not None:
            return access_error
        readiness = dependencies.character_level_up_readiness(
            campaign_slug, campaign, record
        )
        if not dependencies.character_level_up_is_supported(readiness):
            return dependencies.json_error(
                str(
                    readiness.get("message")
                    or "This character is not ready for level-up."
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
            form_values = dependencies.normalize_character_level_up_values(payload)
            level_up_context = dependencies.build_character_level_up_context_parts(
                campaign_slug,
                campaign,
                record,
                form_values=form_values,
            )
            target_level = int(level_up_context.get("next_level") or 0)
            definition, import_metadata, hp_gain = (
                dependencies.build_native_level_up_character_definition(
                    campaign_slug,
                    record.definition,
                    level_up_context,
                    form_values,
                    current_import_metadata=record.import_metadata,
                )
            )
            definition = dependencies.finalize_character_definition_for_write(
                campaign_slug, definition
            )
            merged_state = dependencies.merge_state_with_definition(
                definition,
                record.state_record.state,
                hp_delta=hp_gain,
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
        except (
            CharacterBuildError,
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
        refreshed_readiness = dependencies.character_level_up_readiness(
            campaign_slug, campaign, refreshed_record
        )
        refreshed_context = None
        if dependencies.character_level_up_is_supported(refreshed_readiness):
            refreshed_context = dependencies.build_character_level_up_context_parts(
                campaign_slug, campaign, refreshed_record
            )
        return dependencies.serialize_character_level_up_response(
            campaign_slug,
            campaign,
            refreshed_record,
            readiness=refreshed_readiness,
            level_up_context=refreshed_context,
            message=f"{definition.name} advanced to level {target_level}.",
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/level-up",
        endpoint="character_level_up_read",
        view_func=dependencies.api_login_required(character_level_up_read),
        methods=("GET",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/level-up",
        endpoint="character_level_up_submit",
        view_func=dependencies.api_login_required(character_level_up_submit),
        methods=("POST",),
    )
