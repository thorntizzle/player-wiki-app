from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, flash, request

from .auth import campaign_scope_access_required
from .character_service import CharacterStateValidationError
from .character_store import CharacterStateConflictError


@dataclass(frozen=True)
class CharacterSessionNotesRouteDependencies:
    load_character_context: Callable[..., object]
    campaign_supports_character_session_routes: Callable[..., object]
    has_session_mode_access: Callable[..., object]
    get_current_user: Callable[..., object]
    ensure_active_session_for_session_character_mutation: Callable[..., object]
    parse_expected_revision: Callable[..., object]
    get_character_state_service: Callable[..., object]
    is_session_character_return_requested: Callable[..., object]
    render_session_character_page: Callable[..., object]
    render_character_page: Callable[..., object]
    redirect_to_character_mode: Callable[..., object]


def register_character_session_notes_route(
    app: Any,
    *,
    dependencies: CharacterSessionNotesRouteDependencies,
) -> None:
    def character_session_notes(campaign_slug: str, character_slug: str):
        campaign, record = dependencies.load_character_context(campaign_slug, character_slug)
        if not dependencies.campaign_supports_character_session_routes(campaign):
            abort(404)
        if not dependencies.has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        user = dependencies.get_current_user()
        if user is None:
            abort(403)

        notes_markdown = request.form.get("player_notes_markdown", "")
        return_to_session_mode = request.form.get("mode", "").strip().lower() == "session"
        inactive_session_redirect = dependencies.ensure_active_session_for_session_character_mutation(
            campaign_slug,
            character_slug,
            anchor="session-notes",
        )
        if inactive_session_redirect is not None:
            return inactive_session_redirect
        try:
            expected_revision = dependencies.parse_expected_revision()
            dependencies.get_character_state_service().update_player_notes(
                record,
                expected_revision=expected_revision,
                notes_markdown=notes_markdown,
                updated_by_user_id=user.id,
            )
        except CharacterStateConflictError:
            flash("This sheet changed in another session. Refresh the page and try again.", "error")
            if dependencies.is_session_character_return_requested(campaign_slug, character_slug):
                return dependencies.render_session_character_page(
                    campaign_slug,
                    character_slug,
                    notes_draft=notes_markdown,
                    status_code=409,
                )
            return dependencies.render_character_page(
                campaign_slug,
                character_slug,
                notes_draft=notes_markdown,
                force_session_mode=return_to_session_mode,
                status_code=409,
            )
        except (CharacterStateValidationError, ValueError) as exc:
            flash(str(exc), "error")
            if dependencies.is_session_character_return_requested(campaign_slug, character_slug):
                return dependencies.render_session_character_page(
                    campaign_slug,
                    character_slug,
                    notes_draft=notes_markdown,
                    status_code=400,
                )
            return dependencies.render_character_page(
                campaign_slug,
                character_slug,
                notes_draft=notes_markdown,
                force_session_mode=return_to_session_mode,
                status_code=400,
            )

        flash("Note saved.", "success")
        return dependencies.redirect_to_character_mode(
            campaign_slug,
            character_slug,
            anchor="session-notes",
        )

    scope_required = campaign_scope_access_required("characters")
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/session/notes",
        endpoint="character_session_notes",
        view_func=scope_required(character_session_notes),
        methods=("POST",),
    )
