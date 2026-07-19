from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, current_app, flash, redirect, request, url_for

from .character_builder import CharacterBuildError
from .character_service import CharacterStateValidationError
from .character_store import CharacterStateConflictError


@dataclass(frozen=True)
class CharacterLevelUpRouteDependencies:
    get_repository: Callable[..., object]
    load_character_context: Callable[..., tuple[object, object]]
    campaign_supports_native_character_advancement: Callable[..., bool]
    redirect_unsupported_native_character_tools: Callable[..., object]
    list_builder_campaign_page_records: Callable[..., list[object]]
    get_systems_service: Callable[..., object]
    character_sheet_return_href: Callable[..., str]
    render_character_level_up_page: Callable[..., object]
    parse_expected_revision: Callable[..., int]
    finalize_character_definition_for_write: Callable[..., object]
    login_required: Callable[..., object]
    has_session_mode_access: Callable[..., bool]
    character_advancement_unsupported_message: Callable[..., str]
    native_level_up_readiness: Callable[..., dict[str, object]]
    can_manage_campaign_session: Callable[..., bool]
    build_native_level_up_context: Callable[..., dict[str, object]]
    get_current_user: Callable[..., object]
    build_native_level_up_character_definition: Callable[
        ..., tuple[object, object, int]
    ]
    merge_state_with_definition: Callable[..., dict[str, object]]
    character_publication_coordinator: object


def register_character_level_up_route(
    app: Any,
    *,
    dependencies: CharacterLevelUpRouteDependencies,
) -> None:
    def character_level_up_view(campaign_slug: str, character_slug: str):
        if dependencies.get_repository().get_campaign(campaign_slug) is None:
            abort(404)
        if not dependencies.has_session_mode_access(campaign_slug, character_slug):
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
        if readiness.get("status") == "repairable":
            flash(
                str(
                    readiness.get("message")
                    or "This imported character needs progression repair first."
                ),
                "error",
            )
            if not dependencies.can_manage_campaign_session(campaign_slug):
                return redirect(
                    dependencies.character_sheet_return_href(
                        campaign_slug, character_slug
                    )
                )
            return redirect(
                url_for(
                    "character_progression_repair_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
            )
        if readiness.get("status") != "ready":
            flash(
                str(
                    readiness.get("message")
                    or "This character is not eligible for the current native level-up flow."
                ),
                "error",
            )
            return redirect(
                dependencies.character_sheet_return_href(
                    campaign_slug, character_slug
                )
            )

        form_values = dict(
            request.form if request.method == "POST" else request.args
        )
        try:
            level_up_context = dependencies.build_native_level_up_context(
                dependencies.get_systems_service(),
                campaign_slug,
                record.definition,
                form_values,
                campaign_page_records=campaign_page_records,
            )
            level_up_context["state_revision"] = record.state_record.revision
        except CharacterBuildError as exc:
            flash(str(exc), "error")
            return redirect(
                url_for(
                    "character_read_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
            )

        if request.method != "POST":
            return dependencies.render_character_level_up_page(
                campaign_slug, character_slug, level_up_context
            )

        user = dependencies.get_current_user()
        if user is None:
            abort(403)

        try:
            expected_revision = dependencies.parse_expected_revision()
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
                campaign_slug,
                definition,
                campaign=campaign,
            )
            merged_state = dependencies.merge_state_with_definition(
                definition,
                record.state_record.state,
                hp_delta=hp_gain,
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
            return dependencies.render_character_level_up_page(
                campaign_slug,
                character_slug,
                level_up_context,
                status_code=409,
            )
        except (
            CharacterBuildError,
            CharacterStateValidationError,
            ValueError,
        ) as exc:
            flash(str(exc), "error")
            return dependencies.render_character_level_up_page(
                campaign_slug,
                character_slug,
                level_up_context,
                status_code=400,
            )

        flash(
            f"{definition.name} advanced to level {int(level_up_context.get('next_level') or 0)}.",
            "success",
        )
        return redirect(
            dependencies.character_sheet_return_href(campaign_slug, character_slug)
        )

    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/level-up",
        endpoint="character_level_up_view",
        view_func=dependencies.login_required(character_level_up_view),
        methods=("GET", "POST"),
    )
