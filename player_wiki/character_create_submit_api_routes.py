from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, current_app, jsonify, url_for

from .character_builder import CharacterBuildError
from .character_service import CharacterStateValidationError
from .character_source_repair import (
    SourceRepairError,
    prepare_native_creation_authorizations,
    record_confirmed_native_creation_witness,
)
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
    list_visible_character_page_records: Callable[[str, Any], list[Any]]
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
    get_authenticated_user: Callable[[], Any | None]
    get_current_auth_source: Callable[[], str]
    get_auth_store: Callable[[], Any]


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
        actor_id = None
        if lane == CHARACTER_ROUTE_LANE_DND5E:
            if dependencies.get_current_auth_source() == "view_as":
                return dependencies.json_error("View As cannot create a Character.", 403, code="forbidden")
            actor_id = getattr(dependencies.get_authenticated_user(), "id", None)
            if type(actor_id) is not int or actor_id < 1:
                return dependencies.json_error("Authentication required.", 403, code="forbidden")
        markers = ()
        source_basis_digests = {}
        source_snapshot_digest = ""
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
                campaign_page_records = dependencies.list_builder_campaign_page_records(
                    campaign_slug, campaign
                )
                builder_context = dependencies.build_level_one_builder_context(
                    current_app.extensions["systems_service"],
                    campaign_slug,
                    values,
                    campaign_page_records=campaign_page_records,
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
                    campaign_slug, definition, mode="historical"
                )
                initial_state = dependencies.build_initial_state(definition)
                try:
                    definition, markers, source_basis_digests, source_snapshot_digest = prepare_native_creation_authorizations(
                        definition, initial_state,
                        systems_service=current_app.extensions["systems_service"],
                        campaign_page_records=dependencies.list_visible_character_page_records(
                            campaign_slug, campaign
                        ),
                    )
                except SourceRepairError:
                    from .committed_publication import active
                    if active():
                        raise
                    markers = ()
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
                **({"updated_by_user_id": actor_id} if lane == CHARACTER_ROUTE_LANE_DND5E else {}),
            )
        except CharacterBuildError as exc:
            return dependencies.json_error(str(exc), 400, code="validation_error")
        except FileExistsError as exc:
            return dependencies.json_error(str(exc), 409, code="character_exists")
        except (CharacterStateValidationError, TypeError, ValueError) as exc:
            return dependencies.json_error(str(exc), 400, code="validation_error")

        witnessed = None
        if lane == CHARACTER_ROUTE_LANE_DND5E:
            witnessed = False
            if markers:
                try:
                    def load_current_source_context():
                        current_campaign, access_error = dependencies.ensure_character_authoring_access(
                            campaign_slug
                        )
                        if access_error is not None or current_campaign is None:
                            raise SourceRepairError("Manager authorization changed after creation.")
                        return (
                            current_app.extensions["systems_service"],
                            dependencies.list_visible_character_page_records(campaign_slug, current_campaign),
                        )

                    witnessed = record_confirmed_native_creation_witness(
                        expected_definition=definition,
                        initial_state=initial_state,
                        readback_record=record,
                        markers=markers,
                        source_basis_digests=source_basis_digests,
                        source_snapshot_digest=source_snapshot_digest,
                        load_current_source_context=load_current_source_context,
                        actor_id=actor_id,
                        auth_store=dependencies.get_auth_store(),
                    )
                except Exception:
                    # Creation succeeded; a failed audit must not suggest retry.
                    witnessed = False
        return jsonify(
            {
                "ok": True,
                "message": (
                    f"{record.definition.name} created."
                    if witnessed is not False else
                    f"{record.definition.name} was created. Its baseline needs manager review before automated totals or resources are used; inspect this Character rather than submitting create again."
                ),
                "baseline_verification": (
                    "verified" if witnessed else "needs_repair"
                ) if witnessed is not None else None,
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
