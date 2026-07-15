from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, current_app, flash, redirect, request, url_for

from .auth import campaign_scope_access_required
from .character_builder import CharacterBuildError
from .character_service import CharacterStateValidationError
from .character_store import CharacterStateConflictError


@dataclass(frozen=True)
class CharacterProgressionRepairRouteDependencies:
    load_character_context: Callable[..., tuple[object, object]]
    campaign_supports_native_character_advancement: Callable[..., bool]
    redirect_unsupported_native_character_tools: Callable[..., object]
    list_builder_campaign_page_records: Callable[..., list[object]]
    get_systems_service: Callable[..., object]
    render_character_progression_repair_page: Callable[..., object]
    parse_expected_revision: Callable[..., int]
    finalize_character_definition_for_write: Callable[..., object]
    can_manage_campaign_session: Callable[..., bool]
    character_advancement_unsupported_message: Callable[..., str]
    native_level_up_readiness: Callable[..., dict[str, object]]
    build_imported_progression_repair_context: Callable[..., dict[str, object]]
    get_current_user: Callable[..., object]
    apply_imported_progression_repairs: Callable[..., tuple[object, object]]
    merge_state_with_definition: Callable[..., dict[str, object]]
    load_campaign_character_config: Callable[..., object]
    write_yaml: Callable[..., None]
    character_state_store: object


def register_character_progression_repair_route(
    app: Any,
    *,
    dependencies: CharacterProgressionRepairRouteDependencies,
) -> None:
    def character_progression_repair_view(
        campaign_slug: str, character_slug: str
    ):
        if not dependencies.can_manage_campaign_session(campaign_slug):
            abort(403)

        campaign, record = dependencies.load_character_context(
            campaign_slug, character_slug
        )
        if not dependencies.campaign_supports_native_character_advancement(campaign):
            return dependencies.redirect_unsupported_native_character_tools(
                campaign_slug,
                character_slug=character_slug,
                message=dependencies.character_advancement_unsupported_message(
                    campaign.system
                ),
            )
        campaign_page_records = dependencies.list_builder_campaign_page_records(
            campaign_slug, campaign
        )
        readiness = dependencies.native_level_up_readiness(
            dependencies.get_systems_service(),
            campaign_slug,
            record.definition,
            campaign_page_records=campaign_page_records,
        )
        if readiness.get("status") == "ready":
            flash("This character is already ready for native level-up.", "success")
            return redirect(
                url_for(
                    "character_level_up_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
            )
        if readiness.get("status") == "unsupported":
            flash(
                str(
                    readiness.get("message")
                    or "This character cannot use the current native progression flow."
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

        form_values = dict(
            request.form if request.method == "POST" else request.args
        )
        repair_context = dependencies.build_imported_progression_repair_context(
            dependencies.get_systems_service(),
            campaign_slug,
            record.definition,
            form_values=form_values if request.method == "POST" else None,
            campaign_page_records=campaign_page_records,
        )
        repair_context["state_revision"] = record.state_record.revision

        if request.method != "POST":
            return dependencies.render_character_progression_repair_page(
                campaign_slug, character_slug, repair_context
            )

        user = dependencies.get_current_user()
        if user is None:
            abort(403)

        try:
            expected_revision = dependencies.parse_expected_revision()
            definition, import_metadata = (
                dependencies.apply_imported_progression_repairs(
                    campaign_slug,
                    record.definition,
                    record.import_metadata,
                    repair_context,
                    form_values,
                )
            )
            definition = dependencies.finalize_character_definition_for_write(
                campaign_slug,
                definition,
                campaign=campaign,
            )
            post_repair_readiness = dependencies.native_level_up_readiness(
                dependencies.get_systems_service(),
                campaign_slug,
                definition,
                campaign_page_records=campaign_page_records,
            )
            merged_state = dependencies.merge_state_with_definition(
                definition, record.state_record.state
            )
            dependencies.character_state_store.replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
        except CharacterStateConflictError:
            flash(
                "This sheet changed in another session. Refresh the page and try again.",
                "error",
            )
            return dependencies.render_character_progression_repair_page(
                campaign_slug,
                character_slug,
                repair_context,
                status_code=409,
            )
        except (
            CharacterBuildError,
            CharacterStateValidationError,
            ValueError,
        ) as exc:
            flash(str(exc), "error")
            return dependencies.render_character_progression_repair_page(
                campaign_slug,
                character_slug,
                repair_context,
                status_code=400,
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
        if post_repair_readiness.get("status") == "ready":
            flash(f"{definition.name} is ready for native level-up.", "success")
            return redirect(
                url_for(
                    "character_level_up_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
            )
        if post_repair_readiness.get("status") == "repairable":
            flash(
                "Progression repair saved, but this character still needs a few more linked details before native level-up.",
                "error",
            )
            return redirect(
                url_for(
                    "character_progression_repair_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
            )
        flash(
            str(
                post_repair_readiness.get("message")
                or "This character cannot use the current native progression flow."
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

    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/progression-repair",
        endpoint="character_progression_repair_view",
        view_func=campaign_scope_access_required("characters")(
            character_progression_repair_view
        ),
        methods=("GET", "POST"),
    )
