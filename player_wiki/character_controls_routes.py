from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, current_app, flash, request

from .auth import campaign_scope_access_required


@dataclass(frozen=True)
class CharacterControlsAssignmentRouteDependencies:
    load_character_context: Callable[..., tuple[object, object]]
    campaign_supports_character_controls_routes: Callable[..., bool]
    get_current_user: Callable[..., object | None]
    get_auth_store: Callable[..., object]
    redirect_to_character_controls: Callable[..., object]


def _dependencies() -> CharacterControlsAssignmentRouteDependencies:
    return current_app.extensions["character_controls_assignment_route_dependencies"]


def character_controls_assignment(campaign_slug: str, character_slug: str):
    dependencies = _dependencies()
    campaign, _ = dependencies.load_character_context(campaign_slug, character_slug)
    if not dependencies.campaign_supports_character_controls_routes(campaign):
        abort(404)
    actor = dependencies.get_current_user()
    if actor is None or not actor.is_admin:
        abort(403)

    raw_user_id = request.form.get("user_id", "").strip()
    try:
        target_user_id = int(raw_user_id)
    except ValueError:
        flash("Choose a valid player to assign.", "error")
        return dependencies.redirect_to_character_controls(campaign_slug, character_slug)

    store = dependencies.get_auth_store()
    target_user = store.get_user_by_id(target_user_id)
    if target_user is None or not target_user.is_active:
        flash("Choose an active player account to assign.", "error")
        return dependencies.redirect_to_character_controls(campaign_slug, character_slug)

    membership = store.get_membership(target_user.id, campaign_slug, statuses=("active",))
    if membership is None or membership.role != "player":
        flash("Character owners must have an active player membership in that campaign.", "error")
        return dependencies.redirect_to_character_controls(campaign_slug, character_slug)

    previous = store.get_character_assignment(campaign_slug, character_slug)
    assignment = store.upsert_character_assignment(target_user.id, campaign_slug, character_slug)
    store.write_audit_event(
        event_type="character_assignment_created",
        actor_user_id=actor.id,
        target_user_id=target_user.id,
        campaign_slug=campaign_slug,
        character_slug=character_slug,
        metadata={
            "previous_user_id": previous.user_id if previous is not None else None,
            "assignment_type": assignment.assignment_type,
            "source": "character_controls",
        },
    )
    flash(f"Assigned {character_slug} to {target_user.email}.", "success")
    return dependencies.redirect_to_character_controls(campaign_slug, character_slug)


def character_controls_assignment_remove(campaign_slug: str, character_slug: str):
    dependencies = _dependencies()
    campaign, _ = dependencies.load_character_context(campaign_slug, character_slug)
    if not dependencies.campaign_supports_character_controls_routes(campaign):
        abort(404)
    actor = dependencies.get_current_user()
    if actor is None or not actor.is_admin:
        abort(403)

    store = dependencies.get_auth_store()
    assignment = store.get_character_assignment(campaign_slug, character_slug)
    if assignment is None:
        flash("That character does not currently have an assigned player.", "error")
        return dependencies.redirect_to_character_controls(campaign_slug, character_slug)

    removed_assignment = store.delete_character_assignment(campaign_slug, character_slug)
    if removed_assignment is None:
        flash("That character assignment no longer exists.", "error")
        return dependencies.redirect_to_character_controls(campaign_slug, character_slug)

    store.write_audit_event(
        event_type="character_assignment_removed",
        actor_user_id=actor.id,
        target_user_id=removed_assignment.user_id,
        campaign_slug=campaign_slug,
        character_slug=character_slug,
        metadata={
            "assignment_type": removed_assignment.assignment_type,
            "source": "character_controls",
        },
    )
    flash(f"Cleared assignment for {character_slug}.", "success")
    return dependencies.redirect_to_character_controls(campaign_slug, character_slug)


def register_character_controls_assignment_routes(
    app: Any,
    *,
    load_character_context: Callable[..., tuple[object, object]],
    campaign_supports_character_controls_routes: Callable[..., bool],
    get_current_user: Callable[..., object | None],
    get_auth_store: Callable[..., object],
    redirect_to_character_controls: Callable[..., object],
) -> None:
    app.extensions[
        "character_controls_assignment_route_dependencies"
    ] = CharacterControlsAssignmentRouteDependencies(
        load_character_context=load_character_context,
        campaign_supports_character_controls_routes=campaign_supports_character_controls_routes,
        get_current_user=get_current_user,
        get_auth_store=get_auth_store,
        redirect_to_character_controls=redirect_to_character_controls,
    )
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment",
        endpoint="character_controls_assignment",
        view_func=campaign_scope_access_required("characters")(
            character_controls_assignment
        ),
        methods=("POST",),
    )
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment/remove",
        endpoint="character_controls_assignment_remove",
        view_func=campaign_scope_access_required("characters")(
            character_controls_assignment_remove
        ),
        methods=("POST",),
    )
