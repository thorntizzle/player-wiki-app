from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, flash, request

from .auth import campaign_scope_access_required
from .character_service import CharacterStateValidationError
from .character_store import CharacterStateConflictError


@dataclass(frozen=True)
class CharacterSessionPersonalRouteDependencies:
    load_character_context: Callable[..., object]
    campaign_supports_character_session_routes: Callable[..., object]
    has_session_mode_access: Callable[..., object]
    get_current_user: Callable[..., object]
    is_session_character_return_requested: Callable[..., object]
    campaign_supports_native_character_tools: Callable[..., object]
    session_character_advanced_personal_edit_block_message: str
    session_character_personal_edit_block_message: str
    redirect_to_campaign_session_character: Callable[..., object]
    ensure_active_session_for_session_character_mutation: Callable[..., object]
    parse_expected_revision: Callable[..., object]
    get_character_state_service: Callable[..., object]
    render_session_character_page: Callable[..., object]
    render_character_page: Callable[..., object]
    redirect_to_character_mode: Callable[..., object]


def register_character_session_personal_route(
    app: Any,
    *,
    dependencies: CharacterSessionPersonalRouteDependencies,
) -> None:
    def character_session_personal(campaign_slug: str, character_slug: str):
        campaign, record = dependencies.load_character_context(campaign_slug, character_slug)
        if not dependencies.campaign_supports_character_session_routes(campaign):
            abort(404)
        if not dependencies.has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        user = dependencies.get_current_user()
        if user is None:
            abort(403)

        physical_description_markdown = request.form.get("physical_description_markdown", "")
        background_markdown = request.form.get("background_markdown", "")
        return_to_session_mode = request.form.get("mode", "").strip().lower() == "session"
        if dependencies.is_session_character_return_requested(campaign_slug, character_slug):
            flash(
                dependencies.session_character_advanced_personal_edit_block_message
                if dependencies.campaign_supports_native_character_tools(campaign)
                else dependencies.session_character_personal_edit_block_message,
                "error",
            )
            return dependencies.redirect_to_campaign_session_character(
                campaign_slug,
                character_slug,
                anchor="session-personal-guidance",
            )
        inactive_session_redirect = dependencies.ensure_active_session_for_session_character_mutation(
            campaign_slug,
            character_slug,
            anchor="session-personal",
        )
        if inactive_session_redirect is not None:
            return inactive_session_redirect
        try:
            expected_revision = dependencies.parse_expected_revision()
            dependencies.get_character_state_service().update_personal_details(
                record,
                expected_revision=expected_revision,
                physical_description_markdown=physical_description_markdown,
                background_markdown=background_markdown,
                updated_by_user_id=user.id,
            )
        except CharacterStateConflictError:
            flash("This sheet changed in another session. Refresh the page and try again.", "error")
            if dependencies.is_session_character_return_requested(campaign_slug, character_slug):
                return dependencies.render_session_character_page(
                    campaign_slug,
                    character_slug,
                    physical_description_draft=physical_description_markdown,
                    background_draft=background_markdown,
                    status_code=409,
                )
            return dependencies.render_character_page(
                campaign_slug,
                character_slug,
                physical_description_draft=physical_description_markdown,
                background_draft=background_markdown,
                force_session_mode=return_to_session_mode,
                status_code=409,
            )
        except (CharacterStateValidationError, ValueError) as exc:
            flash(str(exc), "error")
            if dependencies.is_session_character_return_requested(campaign_slug, character_slug):
                return dependencies.render_session_character_page(
                    campaign_slug,
                    character_slug,
                    physical_description_draft=physical_description_markdown,
                    background_draft=background_markdown,
                    status_code=400,
                )
            return dependencies.render_character_page(
                campaign_slug,
                character_slug,
                physical_description_draft=physical_description_markdown,
                background_draft=background_markdown,
                force_session_mode=return_to_session_mode,
                status_code=400,
            )

        flash("Personal details saved.", "success")
        return dependencies.redirect_to_character_mode(
            campaign_slug,
            character_slug,
            anchor="session-personal",
        )

    scope_required = campaign_scope_access_required("characters")
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/personal",
        endpoint="character_session_personal",
        view_func=scope_required(character_session_personal),
        methods=("POST",),
    )
