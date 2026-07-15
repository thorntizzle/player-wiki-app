from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, current_app, jsonify, request, url_for

from .character_path_safety import CharacterPathSafetyError
from .system_policy import CHARACTER_ROUTE_LANE_XIANXIA


@dataclass(frozen=True)
class CharacterXianxiaManualImportApiDependencies:
    ensure_character_authoring_access: Callable[[str], tuple[Any, Any | None]]
    json_error: Callable[..., Any]
    normalize_character_authoring_values: Callable[[dict[str, Any]], dict[str, Any]]
    serialize_campaign: Callable[[Any], dict[str, Any]]
    serialize_character_authoring_links: Callable[[str, Any], dict[str, str]]
    make_json_safe: Callable[[object], object]
    load_json_object: Callable[[], dict[str, Any]]
    write_new_character_record: Callable[..., Any]
    serialize_character_record: Callable[[str, Any], dict[str, Any]]
    flask_campaign_href: Callable[[str, str], str]
    native_character_create_lane: Callable[[str], str]
    build_xianxia_manual_import_context: Callable[..., dict[str, Any]]
    build_xianxia_manual_import_payload: Callable[[dict[str, Any]], dict[str, Any]]
    build_xianxia_manual_import_character: Callable[..., tuple[Any, Any, Any]]
    validate_character_slug: Callable[[str], str]
    build_xianxia_manual_import_preview: Callable[..., dict[str, Any]]


def register_character_xianxia_manual_import_api_routes(
    api: Blueprint,
    *,
    dependencies: CharacterXianxiaManualImportApiDependencies,
) -> None:
    def character_xianxia_manual_import_context(campaign_slug: str):
        campaign, access_error = dependencies.ensure_character_authoring_access(
            campaign_slug
        )
        if access_error is not None:
            return access_error
        if dependencies.native_character_create_lane(
            getattr(campaign, "system", "")
        ) != CHARACTER_ROUTE_LANE_XIANXIA:
            return dependencies.json_error(
                "Manual Xianxia character import is only available for Xianxia campaigns.",
                400,
                code="unsupported_campaign_system",
            )
        values = dependencies.normalize_character_authoring_values(
            {"values": dict(request.args)}
        )
        return jsonify(
            {
                "ok": True,
                "campaign": dependencies.serialize_campaign(campaign),
                "lane": CHARACTER_ROUTE_LANE_XIANXIA,
                "links": dependencies.serialize_character_authoring_links(
                    campaign_slug, campaign
                ),
                "import_context": dependencies.build_xianxia_manual_import_context(
                    systems_service=current_app.extensions["systems_service"],
                    campaign_slug=campaign_slug,
                    values=values,
                    json_safe=dependencies.make_json_safe,
                ),
            }
        )

    def character_xianxia_manual_import_submit(campaign_slug: str):
        campaign, access_error = dependencies.ensure_character_authoring_access(
            campaign_slug
        )
        if access_error is not None:
            return access_error
        if dependencies.native_character_create_lane(
            getattr(campaign, "system", "")
        ) != CHARACTER_ROUTE_LANE_XIANXIA:
            return dependencies.json_error(
                "Manual Xianxia character import is only available for Xianxia campaigns.",
                400,
                code="unsupported_campaign_system",
            )
        try:
            request_payload = dependencies.load_json_object()
        except ValueError as exc:
            return dependencies.json_error(str(exc), 400, code="invalid_json")

        values = dependencies.normalize_character_authoring_values(request_payload)
        import_context = dependencies.build_xianxia_manual_import_context(
            systems_service=current_app.extensions["systems_service"],
            campaign_slug=campaign_slug,
            values=values,
            json_safe=dependencies.make_json_safe,
        )
        import_payload = dependencies.build_xianxia_manual_import_payload(values)
        try:
            definition, import_metadata, initial_state = (
                dependencies.build_xianxia_manual_import_character(
                    import_payload,
                    campaign_slug=campaign_slug,
                    martial_art_options=list(
                        import_context.get("martial_art_options") or []
                    ),
                )
            )
            dependencies.validate_character_slug(definition.character_slug)
            preview = dependencies.build_xianxia_manual_import_preview(
                definition, initial_state
            )
        except ValueError as exc:
            return dependencies.json_error(str(exc), 400, code="validation_error")

        if not bool(request_payload.get("confirm_import")):
            return jsonify(
                {
                    "ok": True,
                    "message": "Review the imported sheet summary, then confirm to create the character.",
                    "campaign": dependencies.serialize_campaign(campaign),
                    "lane": CHARACTER_ROUTE_LANE_XIANXIA,
                    "links": dependencies.serialize_character_authoring_links(
                        campaign_slug, campaign
                    ),
                    "import_context": dependencies.build_xianxia_manual_import_context(
                        systems_service=current_app.extensions["systems_service"],
                        campaign_slug=campaign_slug,
                        values=values,
                        preview=preview,
                        json_safe=dependencies.make_json_safe,
                    ),
                }
            )

        try:
            record = dependencies.write_new_character_record(
                campaign_slug, definition, import_metadata, initial_state
            )
        except FileExistsError as exc:
            return dependencies.json_error(str(exc), 409, code="character_exists")
        except CharacterPathSafetyError as exc:
            return dependencies.json_error(str(exc), 400, code="validation_error")

        return jsonify(
            {
                "ok": True,
                "message": f"{record.definition.name} imported.",
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
        "/campaigns/<campaign_slug>/characters/import/xianxia-manual",
        endpoint="character_xianxia_manual_import_context",
        view_func=character_xianxia_manual_import_context,
        methods=("GET",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/import/xianxia-manual",
        endpoint="character_xianxia_manual_import_submit",
        view_func=character_xianxia_manual_import_submit,
        methods=("POST",),
    )
