from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, flash, redirect, request, url_for

from .auth import campaign_scope_access_required, get_current_user, has_session_mode_access
from .character_store import CharacterStateConflictError
from .system_policy import is_xianxia_system


@dataclass(frozen=True)
class CharacterXianxiaDyingRoundsRouteDependencies:
    load_character_context: Callable[..., Any]
    get_character_state_service: Callable[..., Any]
    parse_expected_revision: Callable[[], int]


def register_character_xianxia_dying_rounds_route(
    app: Any, *, dependencies: CharacterXianxiaDyingRoundsRouteDependencies,
) -> None:
    def character_xianxia_dying_rounds(campaign_slug: str, character_slug: str):
        campaign, record = dependencies.load_character_context(campaign_slug, character_slug)
        if not is_xianxia_system(campaign.system) or not is_xianxia_system(record.definition.system):
            abort(404)
        user = get_current_user()
        if user is None or not has_session_mode_access(campaign_slug, character_slug):
            abort(403)
        try:
            if request.form.get("mode") != "read" or any(
                value != "read" for values in (request.form, request.args) for value in values.getlist("mode")
            ) or any(
                value.strip() for values in (request.form, request.args)
                for key in ("return_view", "combat_view") for value in values.getlist(key)
            ):
                raise ValueError("Dying Rounds can only be edited from Character Resources.")
            action = request.form.get("action")
            value = request.form.get("dying_rounds_remaining")
            if action == "clear":
                value = None
            elif action != "save":
                raise ValueError("Choose Save or Clear for Dying Rounds.")
            elif value is None or not value.strip():
                raise ValueError("Enter a whole number from 0 to 6, or use Clear.")
            revision = dependencies.parse_expected_revision()
            dependencies.get_character_state_service().update_xianxia_dying_rounds(
                record, expected_revision=revision, dying_rounds_remaining=value, updated_by_user_id=user.id,
            )
            flash("Dying Rounds cleared." if action == "clear" else "Dying Rounds saved.", "success")
        except CharacterStateConflictError:
            flash("This sheet changed in another session. Refresh the page and try again.", "error")
        except (ValueError, TypeError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("character_read_view", campaign_slug=campaign_slug,
                                character_slug=character_slug, page="resources", _anchor="xianxia-dying-rounds"))

    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/xianxia-dying-rounds",
        endpoint="character_xianxia_dying_rounds",
        view_func=campaign_scope_access_required("characters")(character_xianxia_dying_rounds),
        methods=("POST",),
    )
