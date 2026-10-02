from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import abort, current_app, flash, redirect, request, url_for

from .auth import campaign_scope_access_required


@dataclass(frozen=True)
class CharacterControlsDeleteRouteDependencies:
    load_character_context: Callable[..., tuple[object, object]]
    campaign_supports_character_controls_routes: Callable[..., bool]
    can_manage_campaign_content: Callable[..., bool]
    get_auth_store: Callable[..., object]
    get_current_user: Callable[..., object | None]
    delete_campaign_character_file: Callable[..., object | None]
    redirect_to_character_controls: Callable[..., object]


def _dependencies() -> CharacterControlsDeleteRouteDependencies:
    return current_app.extensions["character_controls_delete_route_dependencies"]


def character_controls_delete(campaign_slug: str, character_slug: str):
    dependencies = _dependencies()
    campaign, record = dependencies.load_character_context(campaign_slug, character_slug)
    if not dependencies.campaign_supports_character_controls_routes(campaign):
        abort(404)
    if not dependencies.can_manage_campaign_content(campaign_slug):
        abort(403)

    confirmation = request.form.get("confirm_character_slug", "").strip()
    if confirmation != character_slug:
        flash(f"Type {character_slug} to confirm deletion.", "error")
        return dependencies.redirect_to_character_controls(campaign_slug, character_slug)

    from .committed_publication import active
    activated = active()
    expected_definition_revision = expected_state_revision = None
    if activated:
        raw_definition = request.form.get("expected_definition_revision", "")
        raw_state = request.form.get("expected_state_revision", "")
        if (not raw_definition.isascii() or not raw_definition.isdecimal()
                or not raw_state.isascii() or not raw_state.isdecimal()
                or len(raw_definition) > 19 or len(raw_state) > 19
                or int(raw_definition) < 1 or int(raw_state) < 1
                or int(raw_definition) > 9223372036854775807
                or int(raw_state) > 9223372036854775807):
            flash("Character deletion confirmation expired. Reload Controls and try again.", "error")
            return dependencies.redirect_to_character_controls(campaign_slug, character_slug)
        expected_definition_revision = int(raw_definition)
        expected_state_revision = int(raw_state)

    store = dependencies.get_auth_store()
    actor = dependencies.get_current_user()
    try:
        deleted = dependencies.delete_campaign_character_file(
            current_app.config["CAMPAIGNS_DIR"],
            campaign_slug,
            character_slug,
            state_store=current_app.extensions["character_state_store"],
            auth_store=store,
            coordinator=current_app.extensions["character_deletion_coordinator"],
            operation_kind="character_controls",
            actor_user_id=actor.id if actor is not None else None,
            audit_source="character_controls",
            expected_definition_revision=expected_definition_revision,
            expected_state_revision=expected_state_revision,
        )
    except ValueError as exc:
        if not activated:
            raise
        flash(str(exc), "error")
        return dependencies.redirect_to_character_controls(campaign_slug, character_slug)
    if deleted is None:
        flash("That character no longer exists.", "error")
        return redirect(url_for("character_roster_view", campaign_slug=campaign.slug))

    flash(f"Deleted character {record.definition.name}.", "success")
    return redirect(url_for("character_roster_view", campaign_slug=campaign.slug))


def register_character_controls_delete_route(
    app: Any,
    *,
    load_character_context: Callable[..., tuple[object, object]],
    campaign_supports_character_controls_routes: Callable[..., bool],
    can_manage_campaign_content: Callable[..., bool],
    get_auth_store: Callable[..., object],
    get_current_user: Callable[..., object | None],
    delete_campaign_character_file: Callable[..., object | None],
    redirect_to_character_controls: Callable[..., object],
) -> None:
    app.extensions[
        "character_controls_delete_route_dependencies"
    ] = CharacterControlsDeleteRouteDependencies(
        load_character_context=load_character_context,
        campaign_supports_character_controls_routes=campaign_supports_character_controls_routes,
        can_manage_campaign_content=can_manage_campaign_content,
        get_auth_store=get_auth_store,
        get_current_user=get_current_user,
        delete_campaign_character_file=delete_campaign_character_file,
        redirect_to_character_controls=redirect_to_character_controls,
    )
    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/controls/delete",
        endpoint="character_controls_delete",
        view_func=campaign_scope_access_required("characters")(
            character_controls_delete
        ),
        methods=("POST",),
    )
