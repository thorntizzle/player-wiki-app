from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from flask import Blueprint, current_app


@dataclass(frozen=True)
class AdminApiDependencies:
    api_login_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    api_admin_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    jsonify: Callable[..., Any]
    abort: Callable[..., Any]
    build_admin_dashboard_context: Callable[[], dict[str, Any]]
    require_admin_target_user: Callable[[int], Any]
    build_admin_user_detail_context: Callable[[Any], dict[str, Any]]
    get_auth_store: Callable[[], Any]
    load_json_object: Callable[[], dict[str, Any]]
    json_error: Callable[..., Any]
    get_repository: Callable[[], Any]
    get_current_user: Callable[[], Any | None]
    build_admin_local_url: Callable[[str], str]
    build_campaign_lookup: Callable[[Any], dict[str, str]]
    get_character_repository: Callable[[], Any]
    serialize_user: Callable[[Any], dict[str, Any]]


def register_admin_api_routes(
    api: Blueprint,
    *,
    dependencies: AdminApiDependencies,
) -> None:
    jsonify = dependencies.jsonify
    abort = dependencies.abort
    build_admin_dashboard_context = dependencies.build_admin_dashboard_context
    require_admin_target_user = dependencies.require_admin_target_user
    build_admin_user_detail_context = dependencies.build_admin_user_detail_context
    get_auth_store = dependencies.get_auth_store
    load_json_object = dependencies.load_json_object
    json_error = dependencies.json_error
    get_repository = dependencies.get_repository
    get_current_user = dependencies.get_current_user
    build_admin_local_url = dependencies.build_admin_local_url
    build_campaign_lookup = dependencies.build_campaign_lookup
    get_character_repository = dependencies.get_character_repository
    serialize_user = dependencies.serialize_user

    def admin_dashboard_api():
        return jsonify(build_admin_dashboard_context())

    def admin_user_detail_api(user_id: int):
        user = require_admin_target_user(user_id)
        return jsonify(build_admin_user_detail_context(user))

    def admin_invite_user_api():
        store = get_auth_store()
        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="validation_error")

        email = str(payload.get("email") or "").strip()
        display_name = str(payload.get("display_name") or "").strip()
        requested_user_type = str(payload.get("user_type") or "").strip().lower()
        campaign_slug = str(payload.get("campaign_slug") or "").strip()

        if not requested_user_type:
            legacy_is_admin = str(payload.get("is_admin") or "").strip()
            if legacy_is_admin == "1":
                requested_user_type = "admin"
            elif legacy_is_admin == "0":
                requested_user_type = "standard"

        if requested_user_type not in {"admin", "dm", "player", "standard"}:
            return json_error("Choose a valid user type.", 400, code="validation_error")
        if requested_user_type in {"dm", "player"} and (
            not campaign_slug or get_repository().get_campaign(campaign_slug) is None
        ):
            return json_error("Choose a valid campaign for DM or Player invites.", 400, code="validation_error")

        make_admin = requested_user_type == "admin"

        if not email or not display_name:
            return json_error("Email and display name are required.", 400, code="validation_error")
        if store.get_user_by_email(email) is not None:
            return json_error(f"User already exists: {email}", 400, code="validation_error")

        actor = get_current_user()
        actor_user_id = actor.id if actor is not None else None
        user = store.create_user(
            email,
            display_name,
            is_admin=make_admin,
            status="invited",
        )
        invite_token = store.issue_invite_token(
            user.id,
            expires_in=timedelta(hours=current_app.config["INVITE_TTL_HOURS"]),
            created_by_user_id=actor_user_id,
        )
        store.write_audit_event(
            event_type="user_created",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            metadata={"is_admin": make_admin, "source": "admin_screen"},
        )
        store.write_audit_event(
            event_type="user_invited",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            metadata={"source": "admin_screen"},
        )
        if requested_user_type in {"dm", "player"}:
            membership = store.upsert_membership(
                user.id,
                campaign_slug,
                role=requested_user_type,
                status="active",
            )
            store.write_audit_event(
                event_type="membership_created",
                actor_user_id=actor_user_id,
                target_user_id=user.id,
                campaign_slug=campaign_slug,
                metadata={
                    "role": membership.role,
                    "status": membership.status,
                    "source": "admin_screen",
                },
            )
        invite_url = build_admin_local_url(f"/invite/{invite_token}")
        detail_context = build_admin_user_detail_context(user)
        detail_context.update(
            {
                "message": f"Invite URL: {invite_url}",
                "invite_url": invite_url,
            }
        )
        return jsonify(detail_context), 201

    def admin_set_membership_api(user_id: int):
        user = require_admin_target_user(user_id)
        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="validation_error")

        store = get_auth_store()
        campaign_slug = str(payload.get("campaign_slug") or "").strip()
        role = str(payload.get("role") or "").strip()
        status = str(payload.get("status") or "").strip()

        if not campaign_slug or get_repository().get_campaign(campaign_slug) is None:
            return json_error("Choose a valid campaign.", 400, code="validation_error")
        if role not in {"dm", "player", "observer"}:
            return json_error("Choose a valid campaign role.", 400, code="validation_error")
        if status not in {"active", "invited", "removed"}:
            return json_error("Choose a valid membership status.", 400, code="validation_error")

        actor = get_current_user()
        actor_user_id = actor.id if actor is not None else None
        previous = store.get_membership(user.id, campaign_slug, statuses=None)
        membership = store.upsert_membership(user.id, campaign_slug, role=role, status=status)
        if previous is None or previous.status == "removed":
            event_type = "membership_created"
        elif membership.status == "removed":
            event_type = "membership_removed"
        else:
            event_type = "membership_role_changed"
        store.write_audit_event(
            event_type=event_type,
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={"role": membership.role, "status": membership.status, "source": "admin_screen"},
        )
        context = build_admin_user_detail_context(user)
        context["message"] = f"Membership updated: {campaign_slug} -> {membership.role} ({membership.status})"
        return jsonify(context)

    def admin_remove_membership_api(user_id: int):
        user = require_admin_target_user(user_id)
        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="validation_error")

        store = get_auth_store()
        campaign_slug = str(payload.get("campaign_slug") or "").strip()
        membership = store.get_membership(user.id, campaign_slug, statuses=None)
        if membership is None:
            return json_error("Choose a valid membership to remove.", 400, code="validation_error")
        if membership.status == "removed":
            return json_error("That membership is already removed.", 400, code="validation_error")

        actor = get_current_user()
        actor_user_id = actor.id if actor is not None else None
        updated_membership = store.upsert_membership(
            user.id,
            membership.campaign_slug,
            role=membership.role,
            status="removed",
        )
        store.write_audit_event(
            event_type="membership_removed",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            campaign_slug=membership.campaign_slug,
            metadata={
                "role": updated_membership.role,
                "status": updated_membership.status,
                "source": "admin_screen",
            },
        )
        context = build_admin_user_detail_context(user)
        context["message"] = f"Removed membership for {membership.campaign_slug}."
        return jsonify(context)

    def admin_assign_character_api(user_id: int):
        user = require_admin_target_user(user_id)
        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="validation_error")

        raw_assignment = str(payload.get("character_ref") or "").strip()
        if not raw_assignment:
            campaign_slug = str(payload.get("campaign_slug") or "").strip()
            character_slug = str(payload.get("character_slug") or "").strip()
            if campaign_slug and character_slug:
                raw_assignment = f"{campaign_slug}::{character_slug}"

        if "::" not in raw_assignment:
            return json_error("Choose a valid character.", 400, code="validation_error")

        campaign_slug, character_slug = raw_assignment.split("::", 1)
        record = get_character_repository().get_visible_character(campaign_slug, character_slug)
        if record is None:
            return json_error("Choose a valid visible character.", 400, code="validation_error")
        campaign_title = build_campaign_lookup(get_repository()).get(campaign_slug, campaign_slug)
        character_label = record.definition.name

        store = get_auth_store()
        membership = store.get_membership(user.id, campaign_slug, statuses=("active",))
        if membership is None or membership.role != "player":
            return json_error(
                "Character owners must have an active player membership in that campaign.",
                400,
                code="validation_error",
            )

        actor = get_current_user()
        actor_user_id = actor.id if actor is not None else None
        previous = store.get_character_assignment(campaign_slug, character_slug)
        assignment = store.upsert_character_assignment(user.id, campaign_slug, character_slug)
        store.write_audit_event(
            event_type="character_assignment_created",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            campaign_slug=campaign_slug,
            character_slug=character_slug,
            metadata={
                "previous_user_id": previous.user_id if previous is not None else None,
                "assignment_type": assignment.assignment_type,
                "source": "admin_screen",
            },
        )
        context = build_admin_user_detail_context(user)
        context["message"] = f"Assigned {character_label} in {campaign_title} to {user.email}."
        return jsonify(context)

    def admin_remove_character_assignment_api(user_id: int):
        user = require_admin_target_user(user_id)
        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="validation_error")

        campaign_slug = str(payload.get("campaign_slug") or "").strip()
        character_slug = str(payload.get("character_slug") or "").strip()
        campaign_title = build_campaign_lookup(get_repository()).get(campaign_slug, campaign_slug)
        record = get_character_repository().get_visible_character(campaign_slug, character_slug)
        character_label = record.definition.name if record is not None else character_slug
        store = get_auth_store()
        assignment = store.get_character_assignment(campaign_slug, character_slug)
        if assignment is None or assignment.user_id != user.id:
            return json_error("Choose a valid character assignment to remove.", 400, code="validation_error")

        actor = get_current_user()
        actor_user_id = actor.id if actor is not None else None
        removed_assignment = store.delete_character_assignment(campaign_slug, character_slug)
        if removed_assignment is None:
            return json_error("That character assignment no longer exists.", 400, code="validation_error")

        store.write_audit_event(
            event_type="character_assignment_removed",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            campaign_slug=campaign_slug,
            character_slug=character_slug,
            metadata={
                "assignment_type": removed_assignment.assignment_type,
                "source": "admin_screen",
            },
        )
        context = build_admin_user_detail_context(user)
        context["message"] = f"Cleared assignment for {character_label} in {campaign_title}."
        return jsonify(context)

    def admin_issue_invite_api(user_id: int):
        user = require_admin_target_user(user_id)
        if user.status != "invited":
            return json_error("Invite links are only available for invited users.", 400, code="validation_error")

        actor = get_current_user()
        actor_user_id = actor.id if actor is not None else None
        store = get_auth_store()
        invite_token = store.issue_invite_token(
            user.id,
            expires_in=timedelta(hours=current_app.config["INVITE_TTL_HOURS"]),
            created_by_user_id=actor_user_id,
        )
        store.write_audit_event(
            event_type="user_invited",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            metadata={"source": "admin_screen"},
        )
        invite_url = build_admin_local_url(f"/invite/{invite_token}")
        context = build_admin_user_detail_context(user)
        context.update({"message": f"Invite URL: {invite_url}", "invite_url": invite_url})
        return jsonify(context)

    def admin_issue_password_reset_api(user_id: int):
        user = require_admin_target_user(user_id)
        if not user.is_active:
            return json_error("Password resets are only available for active users.", 400, code="validation_error")

        actor = get_current_user()
        actor_user_id = actor.id if actor is not None else None
        store = get_auth_store()
        reset_token = store.issue_password_reset_token(
            user.id,
            expires_in=timedelta(hours=current_app.config["RESET_TTL_HOURS"]),
            created_by_user_id=actor_user_id,
        )
        store.write_audit_event(
            event_type="password_reset_issued",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            metadata={"source": "admin_screen"},
        )
        reset_url = build_admin_local_url(f"/reset/{reset_token}")
        context = build_admin_user_detail_context(user)
        context.update({"message": f"Password reset URL: {reset_url}", "reset_url": reset_url})
        return jsonify(context)

    def admin_disable_user_api(user_id: int):
        user = require_admin_target_user(user_id)
        actor = get_current_user()
        if actor is not None and actor.id == user.id:
            return json_error(
                "The admin screen will not disable the account you are currently using.",
                400,
                code="validation_error",
            )

        store = get_auth_store()
        actor_user_id = actor.id if actor is not None else None
        updated_user = store.disable_user(user.id)
        store.revoke_all_user_sessions(user.id)
        store.revoke_all_user_api_tokens(user.id)
        store.write_audit_event(
            event_type="user_disabled",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            metadata={"source": "admin_screen"},
        )
        context = build_admin_user_detail_context(updated_user)
        context["message"] = f"Disabled user {updated_user.email}."
        return jsonify(context)

    def admin_enable_user_api(user_id: int):
        user = require_admin_target_user(user_id)
        if user.status != "disabled":
            return json_error("Only disabled users can be re-enabled.", 400, code="validation_error")

        actor = get_current_user()
        if actor is not None and actor.id == user.id:
            return json_error(
                "The admin screen will not re-enable the account you are currently using.",
                400,
                code="validation_error",
            )

        store = get_auth_store()
        actor_user_id = actor.id if actor is not None else None
        enabled_user = store.enable_user(user.id)
        store.write_audit_event(
            event_type="user_enabled",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            metadata={"status": enabled_user.status, "source": "admin_screen"},
        )
        context = build_admin_user_detail_context(enabled_user)
        if enabled_user.status == "active":
            context["message"] = f"Re-enabled user {enabled_user.email}."
        else:
            context["message"] = (
                f"Re-enabled user {enabled_user.email}. The account is back in invited status."
            )
        return jsonify(context)

    def admin_delete_user_api(user_id: int):
        user = require_admin_target_user(user_id)
        actor = get_current_user()
        if actor is not None and actor.id == user.id:
            return json_error(
                "The admin screen will not delete the account you are currently using.",
                400,
                code="validation_error",
            )

        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="validation_error")
        confirm_email = str(payload.get("confirm_email") or payload.get("confirm_user_email") or "").strip()
        if confirm_email.lower() != user.email.lower():
            return json_error("Type the user's email address to confirm deletion.", 400, code="validation_error")

        store = get_auth_store()
        actor_user_id = actor.id if actor is not None else None
        deleted_user = store.delete_user(user.id)
        if deleted_user is None:
            abort(404)

        store.write_audit_event(
            event_type="user_deleted",
            actor_user_id=actor_user_id,
            metadata={
                "email": deleted_user.email,
                "status": deleted_user.status,
                "is_admin": deleted_user.is_admin,
                "source": "admin_screen",
            },
        )
        context = build_admin_dashboard_context()
        context.update(
            {
                "message": f"Deleted user {deleted_user.email}.",
                "deleted_user": serialize_user(deleted_user),
            }
        )
        return jsonify(context)

    routes = (
        ("/admin", "admin_dashboard_api", admin_dashboard_api, ("GET",)),
        ("/admin/users/<int:user_id>", "admin_user_detail_api", admin_user_detail_api, ("GET",)),
        ("/admin/users/invite", "admin_invite_user_api", admin_invite_user_api, ("POST",)),
        ("/admin/users/<int:user_id>/membership", "admin_set_membership_api", admin_set_membership_api, ("POST",)),
        ("/admin/users/<int:user_id>/membership", "admin_remove_membership_api", admin_remove_membership_api, ("DELETE",)),
        ("/admin/users/<int:user_id>/assignment", "admin_assign_character_api", admin_assign_character_api, ("POST",)),
        ("/admin/users/<int:user_id>/assignment", "admin_remove_character_assignment_api", admin_remove_character_assignment_api, ("DELETE",)),
        ("/admin/users/<int:user_id>/invite", "admin_issue_invite_api", admin_issue_invite_api, ("POST",)),
        ("/admin/users/<int:user_id>/password-reset", "admin_issue_password_reset_api", admin_issue_password_reset_api, ("POST",)),
        ("/admin/users/<int:user_id>/disable", "admin_disable_user_api", admin_disable_user_api, ("POST",)),
        ("/admin/users/<int:user_id>/enable", "admin_enable_user_api", admin_enable_user_api, ("POST",)),
        ("/admin/users/<int:user_id>", "admin_delete_user_api", admin_delete_user_api, ("DELETE",)),
    )
    for rule, endpoint, handler, methods in routes:
        api.add_url_rule(
            rule,
            endpoint=endpoint,
            view_func=dependencies.api_login_required(
                dependencies.api_admin_required(handler)
            ),
            methods=methods,
        )
