from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, current_app, flash, redirect, request, url_for

from .auth import campaign_scope_access_required
from .character_builder import CharacterBuildError
from .character_path_safety import CharacterPathSafetyError
from .system_policy import (
    CHARACTER_ROUTE_LANE_DND5E,
    CHARACTER_ROUTE_LANE_XIANXIA,
)
from .xianxia_character_builder import (
    XIANXIA_GM_GRANTED_GENERIC_TECHNIQUE_INPUT,
)


@dataclass(frozen=True)
class CharacterCreateRouteDependencies:
    load_campaign_context: Callable[..., object]
    campaign_supports_native_character_create: Callable[..., bool]
    redirect_unsupported_native_character_tools: Callable[..., object]
    get_systems_service: Callable[..., object]
    render_xianxia_character_create_page: Callable[..., object]
    list_builder_campaign_page_records: Callable[..., list[object]]
    render_character_builder_page: Callable[..., object]
    finalize_character_definition_for_write: Callable[..., object]
    can_manage_campaign_session: Callable[..., bool]
    native_character_create_lane: Callable[..., str]
    native_character_create_unsupported_message: Callable[..., str]
    build_xianxia_character_create_context: Callable[..., dict[str, object]]
    build_xianxia_character_definition: Callable[..., tuple[object, object]]
    build_xianxia_character_initial_state: Callable[..., dict[str, object]]
    validate_character_slug: Callable[..., None]
    load_campaign_character_config: Callable[..., object]
    resolve_character_path: Callable[..., object]
    write_yaml: Callable[..., None]
    build_level_one_builder_context: Callable[..., dict[str, object]]
    build_level_one_character_definition: Callable[..., tuple[object, object]]
    build_initial_state: Callable[..., dict[str, object]]


def register_character_create_route(
    app: Any,
    *,
    dependencies: CharacterCreateRouteDependencies,
) -> None:
    def character_create_view(campaign_slug: str):
        if not dependencies.can_manage_campaign_session(campaign_slug):
            abort(403)

        campaign = dependencies.load_campaign_context(campaign_slug)
        create_lane = dependencies.native_character_create_lane(
            getattr(campaign, "system", "")
        )
        if (
            not dependencies.campaign_supports_native_character_create(campaign)
            or not create_lane
        ):
            return dependencies.redirect_unsupported_native_character_tools(
                campaign_slug,
                message=dependencies.native_character_create_unsupported_message(
                    campaign.system
                ),
            )
        if create_lane == CHARACTER_ROUTE_LANE_XIANXIA:
            form_source = request.form if request.method == "POST" else request.args
            form_values = dict(form_source)
            if hasattr(form_source, "getlist"):
                grant_values = form_source.getlist(
                    XIANXIA_GM_GRANTED_GENERIC_TECHNIQUE_INPUT
                )
                if grant_values:
                    form_values[XIANXIA_GM_GRANTED_GENERIC_TECHNIQUE_INPUT] = (
                        grant_values
                    )
            create_context = dependencies.build_xianxia_character_create_context(
                form_values,
                systems_service=dependencies.get_systems_service(),
                campaign_slug=campaign_slug,
            )
            if request.method != "POST":
                return dependencies.render_xianxia_character_create_page(
                    campaign_slug, create_context
                )

            try:
                definition, import_metadata = (
                    dependencies.build_xianxia_character_definition(
                        campaign_slug,
                        create_context,
                        form_values,
                    )
                )
                initial_state = dependencies.build_xianxia_character_initial_state(
                    definition, form_values
                )
                dependencies.validate_character_slug(definition.character_slug)
            except (CharacterBuildError, CharacterPathSafetyError) as exc:
                flash(str(exc), "error")
                return dependencies.render_xianxia_character_create_page(
                    campaign_slug, create_context, status_code=400
                )

            config = dependencies.load_campaign_character_config(
                current_app.config["CAMPAIGNS_DIR"], campaign_slug
            )
            try:
                character_dir = dependencies.resolve_character_path(
                    config.characters_dir, definition.character_slug
                )
                definition_path = dependencies.resolve_character_path(
                    config.characters_dir,
                    definition.character_slug,
                    "definition.yaml",
                )
                import_path = dependencies.resolve_character_path(
                    config.characters_dir,
                    definition.character_slug,
                    "import.yaml",
                )
            except CharacterPathSafetyError as exc:
                flash(str(exc), "error")
                return dependencies.render_xianxia_character_create_page(
                    campaign_slug, create_context, status_code=400
                )
            if definition_path.exists() or import_path.exists():
                flash(
                    f"A character with slug '{definition.character_slug}' already exists in this campaign.",
                    "error",
                )
                return dependencies.render_xianxia_character_create_page(
                    campaign_slug, create_context, status_code=409
                )

            dependencies.write_yaml(definition_path, definition.to_dict())
            dependencies.write_yaml(import_path, import_metadata.to_dict())
            current_app.extensions[
                "character_state_store"
            ].initialize_state_if_missing(definition, initial_state)
            flash(f"{definition.name} created.", "success")
            return redirect(
                url_for(
                    "character_read_view",
                    campaign_slug=campaign_slug,
                    character_slug=definition.character_slug,
                )
            )
        if create_lane != CHARACTER_ROUTE_LANE_DND5E:
            return dependencies.redirect_unsupported_native_character_tools(
                campaign_slug,
                message=dependencies.native_character_create_unsupported_message(
                    campaign.system
                ),
            )
        campaign_page_records = dependencies.list_builder_campaign_page_records(
            campaign_slug, campaign
        )
        form_values = dict(
            request.form if request.method == "POST" else request.args
        )
        builder_context = dependencies.build_level_one_builder_context(
            dependencies.get_systems_service(),
            campaign_slug,
            form_values,
            campaign_page_records=campaign_page_records,
        )
        builder_ready = bool(
            builder_context.get("class_options")
            and builder_context.get("species_options")
            and builder_context.get("background_options")
        )
        if request.method != "POST":
            return dependencies.render_character_builder_page(
                campaign_slug, builder_context
            )

        if not builder_ready:
            flash(
                "The native character builder needs a supported base class plus enabled Systems species and backgrounds first.",
                "error",
            )
            return dependencies.render_character_builder_page(
                campaign_slug, builder_context, status_code=400
            )

        try:
            definition, import_metadata = (
                dependencies.build_level_one_character_definition(
                    campaign_slug,
                    builder_context,
                    form_values,
                )
            )
            definition = dependencies.finalize_character_definition_for_write(
                campaign_slug,
                definition,
                campaign=campaign,
            )
            dependencies.validate_character_slug(definition.character_slug)
        except (CharacterBuildError, CharacterPathSafetyError) as exc:
            flash(str(exc), "error")
            return dependencies.render_character_builder_page(
                campaign_slug, builder_context, status_code=400
            )

        config = dependencies.load_campaign_character_config(
            current_app.config["CAMPAIGNS_DIR"], campaign_slug
        )
        try:
            character_dir = dependencies.resolve_character_path(
                config.characters_dir, definition.character_slug
            )
            definition_path = dependencies.resolve_character_path(
                config.characters_dir,
                definition.character_slug,
                "definition.yaml",
            )
            import_path = dependencies.resolve_character_path(
                config.characters_dir,
                definition.character_slug,
                "import.yaml",
            )
        except CharacterPathSafetyError as exc:
            flash(str(exc), "error")
            return dependencies.render_character_builder_page(
                campaign_slug, builder_context, status_code=400
            )
        if definition_path.exists() or import_path.exists():
            flash(
                f"A character with slug '{definition.character_slug}' already exists in this campaign.",
                "error",
            )
            return dependencies.render_character_builder_page(
                campaign_slug, builder_context, status_code=409
            )

        dependencies.write_yaml(definition_path, definition.to_dict())
        dependencies.write_yaml(import_path, import_metadata.to_dict())
        current_app.extensions["character_state_store"].initialize_state_if_missing(
            definition, dependencies.build_initial_state(definition)
        )
        flash(f"{definition.name} created.", "success")
        return redirect(
            url_for(
                "character_read_view",
                campaign_slug=campaign_slug,
                character_slug=definition.character_slug,
            )
        )

    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/new",
        endpoint="character_create_view",
        view_func=campaign_scope_access_required("characters")(
            character_create_view
        ),
        methods=("GET", "POST"),
    )
