from __future__ import annotations

import csv
import json
import io
from datetime import timedelta
from typing import Any

from flask import Flask, Response, abort, current_app, flash, redirect, render_template, request, url_for

from .admin_audit import (
    EVENT_TITLES,
    build_activity_params,
    get_activity_filters,
    list_audit_event_type_choices,
    load_dashboard_audit_context,
    load_user_audit_context,
    summarize_audit_event,
)
from .admin_context import (
    build_character_assignment_label_lookup,
    build_campaign_lookup,
    build_user_card_summaries,
    build_user_reference_payload,
    get_assignment_character_label,
    get_assignment_form_defaults,
    get_invite_form_defaults,
    get_membership_form_defaults,
    list_campaign_choices,
    list_character_choices,
)
from .auth import admin_required, get_auth_store, get_current_user, get_repository
from .auth_store import AuditEventRecord, AuthStore, UserAccount
from .character_repository import CharacterRepository


def register_admin(app: Flask) -> None:
    def get_character_repository() -> CharacterRepository:
        return current_app.extensions["character_repository"]

    def build_local_url(path: str) -> str:
        return f"{current_app.config['BASE_URL'].rstrip('/')}{path}"

    def build_activity_url(
        endpoint: str,
        activity_filters: dict[str, Any],
        *,
        user_id: int | None = None,
        page: int | None = None,
    ) -> str:
        params = build_activity_params(activity_filters, page=page)
        if user_id is None:
            return url_for(endpoint, **params)
        return url_for(endpoint, user_id=user_id, **params)

    def build_user_reference(
        user_id: int | None,
        display_name: str | None,
        email: str | None,
    ) -> dict[str, str] | None:
        if user_id is None or email is None:
            return None
        return build_user_reference_payload(
            user_id,
            display_name,
            email,
            href=url_for("admin_user_detail", user_id=user_id),
        )

    def render_audit_csv(
        *,
        filename: str,
        events: list[AuditEventRecord],
        campaign_lookup: dict[str, str],
    ) -> Response:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "created_at_utc",
                "event_type",
                "event_title",
                "actor_email",
                "target_email",
                "campaign_slug",
                "campaign_title",
                "character_slug",
                "details",
                "metadata_json",
            ]
        )
        for event in events:
            writer.writerow(
                [
                    event.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    event.event_type,
                    EVENT_TITLES.get(event.event_type, event.event_type.replace("_", " ").title()),
                    event.actor_email or "",
                    event.target_email or "",
                    event.campaign_slug or "",
                    campaign_lookup.get(event.campaign_slug or "", ""),
                    event.character_slug or "",
                    summarize_audit_event(event) or "",
                    json.dumps(event.metadata or {}, sort_keys=True),
                ]
            )

        response = Response(buffer.getvalue(), mimetype="text/csv")
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def build_dashboard_context() -> dict[str, Any]:
        store = get_auth_store()
        repository = get_repository()
        users = store.list_users()
        campaign_choices = list_campaign_choices(repository)
        character_choices = list_character_choices(repository, get_character_repository())
        assignment_label_lookup = build_character_assignment_label_lookup(character_choices)
        campaign_lookup = build_campaign_lookup(repository)

        dashboard_audit_context = load_dashboard_audit_context(
            store,
            campaign_lookup,
            get_activity_filters(request.args, campaign_choices),
            build_page_url=lambda filters, page: build_activity_url("admin_dashboard", filters, page=page),
            build_export_url=lambda filters: build_activity_url("admin_activity_export", filters, page=1),
            build_user_reference=build_user_reference,
        )

        return {
            "campaign_choices": campaign_choices,
            "invite_form_defaults": get_invite_form_defaults(campaign_choices),
            "audit_event_type_choices": list_audit_event_type_choices(),
            "user_cards": build_user_card_summaries(
                store,
                users,
                campaign_lookup,
                assignment_label_lookup=assignment_label_lookup,
            ),
            **dashboard_audit_context,
        }

    def build_user_detail_context(user: UserAccount) -> dict[str, Any]:
        store = get_auth_store()
        repository = get_repository()
        campaigns = list_campaign_choices(repository)
        character_choices = list_character_choices(repository, get_character_repository())
        assignment_label_lookup = build_character_assignment_label_lookup(character_choices)
        campaign_lookup = build_campaign_lookup(repository)
        memberships = store.list_memberships_for_user(
            user.id,
            statuses=("active", "invited", "removed"),
        )
        assignments = store.list_character_assignments_for_user(user.id)
        current_user = get_current_user()
        user_audit_context = load_user_audit_context(
            store,
            campaign_lookup,
            get_activity_filters(request.args, campaigns),
            user_id=user.id,
            build_page_url=lambda filters, page: build_activity_url(
                "admin_user_detail",
                filters,
                user_id=user.id,
                page=page,
            ),
            build_export_url=lambda filters: build_activity_url(
                "admin_user_activity_export",
                filters,
                user_id=user.id,
                page=1,
            ),
            build_user_reference=build_user_reference,
        )

        return {
            "managed_user": user,
            "campaign_choices": campaigns,
            "character_choices": character_choices,
            "memberships": memberships,
            "assignments": assignments,
            "assignment_character_labels": {
                assignment.id: get_assignment_character_label(assignment, assignment_label_lookup)
                for assignment in assignments
            },
            "campaign_lookup": campaign_lookup,
            "audit_event_type_choices": list_audit_event_type_choices(),
            "membership_form_defaults": get_membership_form_defaults(request.args, store, user.id, campaigns),
            "assignment_form_defaults": get_assignment_form_defaults(request.args, character_choices),
            "can_manage_account": current_user is not None and current_user.id != user.id,
            **user_audit_context,
        }

    def require_user(user_id: int) -> UserAccount:
        user = get_auth_store().get_user_by_id(user_id)
        if user is None:
            abort(404)
        return user

    def list_all_dashboard_audit_events(
        store: AuthStore,
        activity_filters: dict[str, Any],
    ) -> list[AuditEventRecord]:
        total_events = store.count_recent_audit_events(
            query=activity_filters["query"] or None,
            event_type=activity_filters["event_type"] or None,
            campaign_slug=activity_filters["campaign_slug"] or None,
        )
        return store.list_recent_audit_events(
            limit=max(total_events, 1),
            offset=0,
            query=activity_filters["query"] or None,
            event_type=activity_filters["event_type"] or None,
            campaign_slug=activity_filters["campaign_slug"] or None,
        )

    def list_all_user_audit_events(
        store: AuthStore,
        activity_filters: dict[str, Any],
        *,
        user_id: int,
    ) -> list[AuditEventRecord]:
        total_events = store.count_audit_events_for_user(
            user_id,
            query=activity_filters["query"] or None,
            event_type=activity_filters["event_type"] or None,
            campaign_slug=activity_filters["campaign_slug"] or None,
        )
        return store.list_audit_events_for_user(
            user_id,
            limit=max(total_events, 1),
            offset=0,
            query=activity_filters["query"] or None,
            event_type=activity_filters["event_type"] or None,
            campaign_slug=activity_filters["campaign_slug"] or None,
        )

    @app.get("/admin")
    @admin_required
    def admin_dashboard():
        context = build_dashboard_context()
        return render_template("admin_dashboard.html", active_nav="admin", **context)

    @app.get("/admin/activity/export.csv")
    @admin_required
    def admin_activity_export():
        store = get_auth_store()
        repository = get_repository()
        campaign_choices = list_campaign_choices(repository)
        campaign_lookup = build_campaign_lookup(repository)
        activity_filters = get_activity_filters(request.args, campaign_choices)
        events = list_all_dashboard_audit_events(store, activity_filters)
        return render_audit_csv(
            filename="admin-activity-export.csv",
            events=events,
            campaign_lookup=campaign_lookup,
        )

    @app.post("/admin/users/invite")
    @admin_required
    def admin_invite_user():
        store: AuthStore = get_auth_store()
        email = request.form.get("email", "").strip()
        display_name = request.form.get("display_name", "").strip()
        requested_user_type = request.form.get("user_type", "").strip().lower()
        campaign_slug = request.form.get("campaign_slug", "").strip()

        # Keep the old post shape working for existing callers while the UI moves to named invite types.
        if not requested_user_type:
            legacy_is_admin = request.form.get("is_admin", "").strip()
            if legacy_is_admin == "1":
                requested_user_type = "admin"
            elif legacy_is_admin == "0":
                requested_user_type = "standard"

        if requested_user_type not in {"admin", "dm", "player", "standard"}:
            flash("Choose a valid user type.", "error")
            return redirect(url_for("admin_dashboard"))
        if requested_user_type in {"dm", "player"} and (
            not campaign_slug or get_repository().get_campaign(campaign_slug) is None
        ):
            flash("Choose a valid campaign for DM or Player invites.", "error")
            return redirect(url_for("admin_dashboard"))

        make_admin = requested_user_type == "admin"

        if not email or not display_name:
            flash("Email and display name are required.", "error")
            return redirect(url_for("admin_dashboard"))
        if store.get_user_by_email(email) is not None:
            flash(f"User already exists: {email}", "error")
            return redirect(url_for("admin_dashboard"))

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
        flash(f"Invite URL: {build_local_url(f'/invite/{invite_token}')}", "success")
        return redirect(url_for("admin_user_detail", user_id=user.id))

    @app.get("/admin/users/<int:user_id>")
    @admin_required
    def admin_user_detail(user_id: int):
        user = require_user(user_id)
        context = build_user_detail_context(user)
        return render_template("admin_user_detail.html", active_nav="admin", **context)

    @app.get("/admin/users/<int:user_id>/activity/export.csv")
    @admin_required
    def admin_user_activity_export(user_id: int):
        user = require_user(user_id)
        store = get_auth_store()
        repository = get_repository()
        campaign_choices = list_campaign_choices(repository)
        campaign_lookup = build_campaign_lookup(repository)
        activity_filters = get_activity_filters(request.args, campaign_choices)
        events = list_all_user_audit_events(store, activity_filters, user_id=user.id)
        return render_audit_csv(
            filename=f"user-activity-{user.email.replace('@', '_at_')}.csv",
            events=events,
            campaign_lookup=campaign_lookup,
        )

    @app.post("/admin/users/<int:user_id>/membership")
    @admin_required
    def admin_set_membership(user_id: int):
        user = require_user(user_id)
        store = get_auth_store()
        campaign_slug = request.form.get("campaign_slug", "").strip()
        role = request.form.get("role", "").strip()
        status = request.form.get("status", "").strip()

        if not campaign_slug or get_repository().get_campaign(campaign_slug) is None:
            flash("Choose a valid campaign.", "error")
            return redirect(url_for("admin_user_detail", user_id=user.id))
        if role not in {"dm", "player", "observer"}:
            flash("Choose a valid campaign role.", "error")
            return redirect(url_for("admin_user_detail", user_id=user.id))
        if status not in {"active", "invited", "removed"}:
            flash("Choose a valid membership status.", "error")
            return redirect(url_for("admin_user_detail", user_id=user.id))

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
        flash(
            f"Membership updated: {campaign_slug} -> {membership.role} ({membership.status})",
            "success",
        )
        return redirect(url_for("admin_user_detail", user_id=user.id))

    @app.post("/admin/users/<int:user_id>/membership/remove")
    @admin_required
    def admin_remove_membership(user_id: int):
        user = require_user(user_id)
        store = get_auth_store()
        campaign_slug = request.form.get("campaign_slug", "").strip()
        membership = store.get_membership(user.id, campaign_slug, statuses=None)
        if membership is None:
            flash("Choose a valid membership to remove.", "error")
            return redirect(url_for("admin_user_detail", user_id=user.id))
        if membership.status == "removed":
            flash("That membership is already removed.", "error")
            return redirect(url_for("admin_user_detail", user_id=user.id))

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
        flash(f"Removed membership for {membership.campaign_slug}.", "success")
        return redirect(url_for("admin_user_detail", user_id=user.id))

    @app.post("/admin/users/<int:user_id>/assignment")
    @admin_required
    def admin_assign_character(user_id: int):
        user = require_user(user_id)
        store = get_auth_store()
        raw_assignment = request.form.get("character_ref", "").strip()
        if "::" not in raw_assignment:
            flash("Choose a valid character.", "error")
            return redirect(url_for("admin_user_detail", user_id=user.id))

        campaign_slug, character_slug = raw_assignment.split("::", 1)
        record = get_character_repository().get_visible_character(campaign_slug, character_slug)
        if record is None:
            flash("Choose a valid visible character.", "error")
            return redirect(url_for("admin_user_detail", user_id=user.id))
        campaign_title = build_campaign_lookup(get_repository()).get(campaign_slug, campaign_slug)
        character_label = record.definition.name

        membership = store.get_membership(user.id, campaign_slug, statuses=("active",))
        if membership is None or membership.role != "player":
            flash("Character owners must have an active player membership in that campaign.", "error")
            return redirect(url_for("admin_user_detail", user_id=user.id))

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
        flash(f"Assigned {character_label} in {campaign_title} to {user.email}.", "success")
        return redirect(url_for("admin_user_detail", user_id=user.id))

    @app.post("/admin/users/<int:user_id>/assignment/remove")
    @admin_required
    def admin_remove_character_assignment(user_id: int):
        user = require_user(user_id)
        store = get_auth_store()
        campaign_slug = request.form.get("campaign_slug", "").strip()
        character_slug = request.form.get("character_slug", "").strip()
        campaign_title = build_campaign_lookup(get_repository()).get(campaign_slug, campaign_slug)
        record = get_character_repository().get_visible_character(campaign_slug, character_slug)
        character_label = record.definition.name if record is not None else character_slug
        assignment = store.get_character_assignment(campaign_slug, character_slug)
        if assignment is None or assignment.user_id != user.id:
            flash("Choose a valid character assignment to remove.", "error")
            return redirect(url_for("admin_user_detail", user_id=user.id))

        actor = get_current_user()
        actor_user_id = actor.id if actor is not None else None
        removed_assignment = store.delete_character_assignment(campaign_slug, character_slug)
        if removed_assignment is None:
            flash("That character assignment no longer exists.", "error")
            return redirect(url_for("admin_user_detail", user_id=user.id))

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
        flash(f"Cleared assignment for {character_label} in {campaign_title}.", "success")
        return redirect(url_for("admin_user_detail", user_id=user.id))

    @app.post("/admin/users/<int:user_id>/invite")
    @admin_required
    def admin_issue_invite(user_id: int):
        user = require_user(user_id)
        if user.status != "invited":
            flash("Invite links are only available for invited users.", "error")
            return redirect(url_for("admin_user_detail", user_id=user.id))

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
        flash(f"Invite URL: {build_local_url(f'/invite/{invite_token}')}", "success")
        return redirect(url_for("admin_user_detail", user_id=user.id))

    @app.post("/admin/users/<int:user_id>/password-reset")
    @admin_required
    def admin_issue_password_reset(user_id: int):
        user = require_user(user_id)
        if not user.is_active:
            flash("Password resets are only available for active users.", "error")
            return redirect(url_for("admin_user_detail", user_id=user.id))

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
        flash(f"Password reset URL: {build_local_url(f'/reset/{reset_token}')}", "success")
        return redirect(url_for("admin_user_detail", user_id=user.id))

    @app.post("/admin/users/<int:user_id>/disable")
    @admin_required
    def admin_disable_user(user_id: int):
        user = require_user(user_id)
        actor = get_current_user()
        if actor is not None and actor.id == user.id:
            flash("The admin screen will not disable the account you are currently using.", "error")
            return redirect(url_for("admin_user_detail", user_id=user.id))

        store = get_auth_store()
        actor_user_id = actor.id if actor is not None else None
        store.disable_user(user.id)
        store.revoke_all_user_sessions(user.id)
        store.revoke_all_user_api_tokens(user.id)
        store.write_audit_event(
            event_type="user_disabled",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            metadata={"source": "admin_screen"},
        )
        flash(f"Disabled user {user.email}.", "success")
        return redirect(url_for("admin_user_detail", user_id=user.id))

    @app.post("/admin/users/<int:user_id>/enable")
    @admin_required
    def admin_enable_user(user_id: int):
        user = require_user(user_id)
        if user.status != "disabled":
            flash("Only disabled users can be re-enabled.", "error")
            return redirect(url_for("admin_user_detail", user_id=user.id))

        actor = get_current_user()
        if actor is not None and actor.id == user.id:
            flash("The admin screen will not re-enable the account you are currently using.", "error")
            return redirect(url_for("admin_user_detail", user_id=user.id))

        store = get_auth_store()
        actor_user_id = actor.id if actor is not None else None
        enabled_user = store.enable_user(user.id)
        store.write_audit_event(
            event_type="user_enabled",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            metadata={"status": enabled_user.status, "source": "admin_screen"},
        )
        if enabled_user.status == "active":
            flash(f"Re-enabled user {enabled_user.email}.", "success")
        else:
            flash(
                f"Re-enabled user {enabled_user.email}. The account is back in invited status.",
                "success",
            )
        return redirect(url_for("admin_user_detail", user_id=enabled_user.id))

    @app.post("/admin/users/<int:user_id>/delete")
    @admin_required
    def admin_delete_user(user_id: int):
        user = require_user(user_id)
        actor = get_current_user()
        if actor is not None and actor.id == user.id:
            flash("The admin screen will not delete the account you are currently using.", "error")
            return redirect(url_for("admin_user_detail", user_id=user.id))

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
        flash(f"Deleted user {deleted_user.email}.", "success")
        return redirect(url_for("admin_dashboard"))
