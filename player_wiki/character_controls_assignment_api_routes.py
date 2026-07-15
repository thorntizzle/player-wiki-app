from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint


@dataclass(frozen=True)
class CharacterControlsAssignmentApiDependencies:
    api_login_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    load_character_controls_target: Callable[..., tuple[Any, Any]]
    get_current_user: Callable[[], Any | None]
    json_error: Callable[..., Any]
    load_json_object: Callable[[], dict[str, Any]]
    get_auth_store: Callable[[], Any]
    serialize_character_controls_response: Callable[..., Any]


def register_character_controls_assignment_api_routes(
    api: Blueprint,
    *,
    dependencies: CharacterControlsAssignmentApiDependencies,
) -> None:
    def character_controls_assignment_update(
        campaign_slug: str,
        character_slug: str,
    ):
        campaign, record = dependencies.load_character_controls_target(
            campaign_slug, character_slug
        )
        actor = dependencies.get_current_user()
        if actor is None:
            return dependencies.json_error(
                "Authentication required.", 401, code="auth_required"
            )
        if not actor.is_admin:
            return dependencies.json_error(
                "You do not have permission to assign character owners.",
                403,
                code="forbidden",
            )

        try:
            payload = dependencies.load_json_object()
            target_user_id = int(payload.get("user_id"))
        except (TypeError, ValueError):
            return dependencies.json_error(
                "Choose a valid player to assign.",
                400,
                code="validation_error",
            )

        store = dependencies.get_auth_store()
        target_user = store.get_user_by_id(target_user_id)
        if target_user is None or not target_user.is_active:
            return dependencies.json_error(
                "Choose an active player account to assign.",
                400,
                code="validation_error",
            )

        membership = store.get_membership(
            target_user.id, campaign_slug, statuses=("active",)
        )
        if membership is None or membership.role != "player":
            return dependencies.json_error(
                "Character owners must have an active player membership in that campaign.",
                400,
                code="validation_error",
            )

        previous = store.get_character_assignment(campaign_slug, character_slug)
        assignment = store.upsert_character_assignment(
            target_user.id, campaign_slug, character_slug
        )
        store.write_audit_event(
            event_type="character_assignment_created",
            actor_user_id=actor.id,
            target_user_id=target_user.id,
            campaign_slug=campaign_slug,
            character_slug=character_slug,
            metadata={
                "previous_user_id": previous.user_id if previous is not None else None,
                "assignment_type": assignment.assignment_type,
                "source": "character_controls_api",
            },
        )

        return dependencies.serialize_character_controls_response(
            campaign_slug,
            campaign,
            record,
            message=f"Assigned {character_slug} to {target_user.email}.",
        )

    def character_controls_assignment_delete(
        campaign_slug: str,
        character_slug: str,
    ):
        campaign, record = dependencies.load_character_controls_target(
            campaign_slug, character_slug
        )
        actor = dependencies.get_current_user()
        if actor is None:
            return dependencies.json_error(
                "Authentication required.", 401, code="auth_required"
            )
        if not actor.is_admin:
            return dependencies.json_error(
                "You do not have permission to assign character owners.",
                403,
                code="forbidden",
            )

        store = dependencies.get_auth_store()
        assignment = store.get_character_assignment(campaign_slug, character_slug)
        if assignment is None:
            return dependencies.json_error(
                "That character does not currently have an assigned player.",
                400,
                code="validation_error",
            )

        removed_assignment = store.delete_character_assignment(
            campaign_slug, character_slug
        )
        if removed_assignment is None:
            return dependencies.json_error(
                "That character assignment no longer exists.",
                400,
                code="validation_error",
            )

        store.write_audit_event(
            event_type="character_assignment_removed",
            actor_user_id=actor.id,
            target_user_id=removed_assignment.user_id,
            campaign_slug=campaign_slug,
            character_slug=character_slug,
            metadata={
                "assignment_type": removed_assignment.assignment_type,
                "source": "character_controls_api",
            },
        )

        return dependencies.serialize_character_controls_response(
            campaign_slug,
            campaign,
            record,
            message=f"Cleared assignment for {character_slug}.",
        )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment",
        endpoint="character_controls_assignment_update",
        view_func=dependencies.api_login_required(character_controls_assignment_update),
        methods=("POST",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment",
        endpoint="character_controls_assignment_delete",
        view_func=dependencies.api_login_required(character_controls_assignment_delete),
        methods=("DELETE",),
    )
