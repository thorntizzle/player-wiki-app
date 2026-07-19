from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, current_app, jsonify, url_for

from .character_builder import CharacterBuildError
from .character_service import CharacterStateValidationError
from .system_policy import (
    CHARACTER_ROUTE_LANE_DND5E,
    CHARACTER_ROUTE_LANE_XIANXIA,
)


@dataclass(frozen=True)
class CharacterCreateSubmitApiDependencies:
    ensure_character_authoring_access: Callable[[str], tuple[Any, Any | None]]
    load_json_object: Callable[[], dict[str, Any]]
    json_error: Callable[..., Any]
    normalize_character_authoring_values: Callable[[dict[str, Any]], dict[str, Any]]
    list_builder_campaign_page_records: Callable[[str, Any], list[Any]]
    write_new_character_record: Callable[..., Any]
    serialize_character_record: Callable[[str, Any], dict[str, Any]]
    serialize_character_authoring_links: Callable[[str, Any], dict[str, str]]
    flask_campaign_href: Callable[[str, str], str]
    finalize_character_definition_for_write: Callable[[str, Any], Any]
    native_character_create_lane: Callable[[str], str]
    build_xianxia_character_create_context: Callable[..., dict[str, Any]]
    build_xianxia_character_definition: Callable[..., tuple[Any, Any]]
    build_xianxia_character_initial_state: Callable[..., dict[str, Any]]
    build_level_one_builder_context: Callable[..., dict[str, Any]]
    build_level_one_character_definition: Callable[..., tuple[Any, Any]]
    build_initial_state: Callable[[Any], dict[str, Any]]
    native_character_create_unsupported_message: Callable[[str], str]


def register_character_create_submit_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterCreateSubmitApiDependencies,
) -> None:
    def character_create_submit(campaign_slug: str):
        campaign, access_error = dependencies.ensure_character_authoring_access(
            campaign_slug
        )
        if access_error is not None:
            return access_error

        try:
            payload = dependencies.load_json_object()
        except ValueError as exc:
            return dependencies.json_error(str(exc), 400, code="invalid_json")
        values = dependencies.normalize_character_authoring_values(payload)
        lane = dependencies.native_character_create_lane(
            getattr(campaign, "system", "")
        )
        try:
            if lane == CHARACTER_ROUTE_LANE_XIANXIA:
                create_context = dependencies.build_xianxia_character_create_context(
                    values,
                    systems_service=current_app.extensions["systems_service"],
                    campaign_slug=campaign_slug,
                )
                definition, import_metadata = (
                    dependencies.build_xianxia_character_definition(
                        campaign_slug,
                        create_context,
                        values,
                    )
                )
                initial_state = dependencies.build_xianxia_character_initial_state(
                    definition, values
                )
            elif lane == CHARACTER_ROUTE_LANE_DND5E:
                builder_context = dependencies.build_level_one_builder_context(
                    current_app.extensions["systems_service"],
                    campaign_slug,
                    values,
                    campaign_page_records=dependencies.list_builder_campaign_page_records(
                        campaign_slug, campaign
                    ),
                )
                builder_ready = bool(
                    builder_context.get("class_options")
                    and builder_context.get("species_options")
                    and builder_context.get("background_options")
                )
                if not builder_ready:
                    return dependencies.json_error(
                        "The native character builder needs a supported base class plus enabled Systems species and backgrounds first.",
                        400,
                        code="validation_error",
                    )
                definition, import_metadata = (
                    dependencies.build_level_one_character_definition(
                        campaign_slug,
                        builder_context,
                        values,
                    )
                )
                definition = dependencies.finalize_character_definition_for_write(
                    campaign_slug, definition
                )
                initial_state = dependencies.build_initial_state(definition)
            else:
                return dependencies.json_error(
                    dependencies.native_character_create_unsupported_message(
                        getattr(campaign, "system", "")
                    ),
                    400,
                    code="unsupported_campaign_system",
                )
            record = dependencies.write_new_character_record(
                campaign_slug,
                definition,
                import_metadata,
                initial_state,
            )
        except CharacterBuildError as exc:
            return dependencies.json_error(str(exc), 400, code="validation_error")
        except FileExistsError as exc:
            return dependencies.json_error(str(exc), 409, code="character_exists")
        except (CharacterStateValidationError, TypeError, ValueError) as exc:
            return dependencies.json_error(str(exc), 400, code="validation_error")

        return jsonify(
            {
                "ok": True,
                "message": f"{record.definition.name} created.",
                "character": dependencies.serialize_character_record(
                    campaign_slug, record
                ),
                "links": {
                    **dependencies.serialize_character_authoring_links(
                        campaign_slug, campaign
                    ),
                    "character_url": dependencies.flask_campaign_href(
                        campaign_slug,
                        f"characters/{record.definition.character_slug}",
                    ),
                    "flask_character_url": url_for(
                        "character_read_view",
                        campaign_slug=campaign_slug,
                        character_slug=record.definition.character_slug,
                    ),
                },
            }
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/create",
        endpoint="character_create_submit",
        view_func=character_create_submit,
        methods=("POST",),
    )
