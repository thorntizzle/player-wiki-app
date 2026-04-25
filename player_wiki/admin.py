from __future__ import annotations

import csv
import json
import io
from datetime import timedelta
from typing import Any

from flask import Flask, Response, abort, current_app, flash, redirect, render_template, request, url_for

from .auth import admin_required, get_auth_store, get_current_user, get_repository
from .auth_store import AuditEventRecord, AuthStore, UserAccount
from .character_repository import CharacterRepository

EVENT_TITLES = {
    "user_created": "User created",
    "user_invited": "Invite issued",
    "user_activated": "Account activated",
    "user_enabled": "User re-enabled",
    "user_deleted": "User deleted",
    "membership_created": "Membership created",
    "membership_role_changed": "Membership updated",
    "membership_removed": "Membership removed",
    "character_assignment_created": "Character assigned",
    "character_assignment_removed": "Character assignment removed",
    "character_deleted": "Character deleted",
    "password_reset_issued": "Password reset issued",
    "password_reset_completed": "Password reset completed",
    "api_token_issued": "API token issued",
    "api_token_revoked": "API token revoked",
    "user_disabled": "User disabled",
    "campaign_visibility_updated": "Campaign visibility updated",
    "campaign_wiki_page_created": "Wiki page created",
    "campaign_wiki_page_updated": "Wiki page updated",
    "campaign_wiki_page_unpublished": "Wiki page unpublished",
    "campaign_wiki_page_deleted": "Wiki page deleted",
    "campaign_systems_policy_updated": "Systems policy updated",
    "campaign_systems_source_updated": "Systems source updated",
    "campaign_systems_entry_override_updated": "Systems entry override updated",
}

SOURCE_LABELS = {
    "admin_screen": "admin screen",
    "manage.py": "CLI",
    "invite": "invite setup",
    "reset_token": "reset link",
    "campaign_control_panel": "campaign control panel",
    "dm_content_player_wiki": "DM Content player wiki",
    "campaign_systems_control_panel": "systems control panel",
    "character_controls": "character controls",
}

AUDIT_PAGE_SIZE = 10


def register_admin(app: Flask) -> None:
    def get_character_repository() -> CharacterRepository:
        return current_app.extensions["character_repository"]

    def build_local_url(path: str) -> str:
        return f"{current_app.config['BASE_URL'].rstrip('/')}{path}"

    def list_campaign_choices() -> list[dict[str, str]]:
        repository = get_repository()
        return [
            {"slug": campaign.slug, "title": campaign.title}
            for campaign in sorted(repository.campaigns.values(), key=lambda item: item.title.lower())
        ]

    def list_character_choices() -> list[dict[str, str]]:
        choices: list[dict[str, str]] = []
        for campaign in sorted(get_repository().campaigns.values(), key=lambda item: item.title.lower()):
            for record in get_character_repository().list_visible_characters(campaign.slug):
                choices.append(
                    {
                        "campaign_slug": campaign.slug,
                        "character_slug": record.definition.character_slug,
                        "label": f"{campaign.title} | {record.definition.name}",
                        "value": f"{campaign.slug}::{record.definition.character_slug}",
                    }
                )
        return choices

    def list_audit_event_type_choices() -> list[dict[str, str]]:
        return [
            {"value": event_type, "label": EVENT_TITLES.get(event_type, event_type.replace("_", " ").title())}
            for event_type in sorted(EVENT_TITLES)
        ]

    def get_activity_filters(campaign_choices: list[dict[str, str]]) -> dict[str, Any]:
        allowed_campaigns = {item["slug"] for item in campaign_choices}
        allowed_event_types = set(EVENT_TITLES)

        query = request.args.get("audit_q", "").strip()
        event_type = request.args.get("audit_event_type", "").strip()
        campaign_slug = request.args.get("audit_campaign_slug", "").strip()
        raw_page = request.args.get("audit_page", "").strip()

        if event_type not in allowed_event_types:
            event_type = ""
        if campaign_slug not in allowed_campaigns:
            campaign_slug = ""
        try:
            page = max(1, int(raw_page))
        except (TypeError, ValueError):
            page = 1

        return {
            "query": query,
            "event_type": event_type,
            "campaign_slug": campaign_slug,
            "page": page,
        }

    def build_activity_url(
        endpoint: str,
        activity_filters: dict[str, Any],
        *,
        user_id: int | None = None,
        page: int | None = None,
    ) -> str:
        params: dict[str, Any] = {}
        if activity_filters.get("query"):
            params["audit_q"] = activity_filters["query"]
        if activity_filters.get("event_type"):
            params["audit_event_type"] = activity_filters["event_type"]
        if activity_filters.get("campaign_slug"):
            params["audit_campaign_slug"] = activity_filters["campaign_slug"]

        page_value = activity_filters.get("page", 1) if page is None else page
        if isinstance(page_value, int) and page_value > 1:
            params["audit_page"] = page_value

        if user_id is None:
            return url_for(endpoint, **params)
        return url_for(endpoint, user_id=user_id, **params)

    def format_admin_timestamp(value) -> str:
        return value.strftime("%Y-%m-%d %H:%M UTC")

    def build_user_reference(
        *,
        user_id: int | None,
        display_name: str | None,
        email: str | None,
    ) -> dict[str, str] | None:
        if user_id is None or email is None:
            return None

        label = display_name or email
        return {
            "label": label,
            "meta": email if display_name and display_name != email else "",
            "href": url_for("admin_user_detail", user_id=user_id),
        }

    def summarize_audit_event(event: AuditEventRecord) -> str | None:
        detail_bits: list[str] = []
        metadata = event.metadata

        if metadata.get("is_admin") is True:
            detail_bits.append("app admin")

        role = metadata.get("role")
        if isinstance(role, str) and role:
            detail_bits.append(f"role {role}")

        status = metadata.get("status")
        if isinstance(status, str) and status:
            detail_bits.append(f"status {status}")

        scope = metadata.get("scope")
        if isinstance(scope, str) and scope:
            detail_bits.append(f"scope {scope}")

        visibility = metadata.get("visibility")
        if isinstance(visibility, str) and visibility:
            detail_bits.append(f"visibility {visibility}")

        source_id = metadata.get("source_id")
        if isinstance(source_id, str) and source_id:
            detail_bits.append(f"source {source_id}")

        library_slug = metadata.get("library_slug")
        if isinstance(library_slug, str) and library_slug:
            detail_bits.append(f"library {library_slug}")

        entry_key = metadata.get("entry_key")
        if isinstance(entry_key, str) and entry_key:
            detail_bits.append(f"entry {entry_key}")

        email = metadata.get("email")
        if isinstance(email, str) and email:
            detail_bits.append(f"user {email}")

        if metadata.get("is_enabled") is True:
            detail_bits.append("enabled")
        elif metadata.get("is_enabled") is False:
            detail_bits.append("disabled")

        assignment_type = metadata.get("assignment_type")
        if isinstance(assignment_type, str) and assignment_type:
            detail_bits.append(f"assignment {assignment_type}")

        if metadata.get("previous_user_id") is not None:
            detail_bits.append("reassigned")

        source_key = metadata.get("source") or metadata.get("via")
        if isinstance(source_key, str) and source_key:
            source_label = SOURCE_LABELS.get(source_key, source_key.replace("_", " "))
            detail_bits.append(f"via {source_label}")

        return " | ".join(detail_bits) if detail_bits else None

    def present_audit_event(
        event: AuditEventRecord,
        *,
        campaign_lookup: dict[str, str],
    ) -> dict[str, Any]:
        scope_bits: list[str] = []
        if event.campaign_slug:
            scope_bits.append(campaign_lookup.get(event.campaign_slug, event.campaign_slug))
        if event.character_slug:
            scope_bits.append(event.character_slug)

        return {
            "event_type": event.event_type,
            "title": EVENT_TITLES.get(event.event_type, event.event_type.replace("_", " ").title()),
            "timestamp": format_admin_timestamp(event.created_at),
            "actor": build_user_reference(
                user_id=event.actor_user_id,
                display_name=event.actor_display_name,
                email=event.actor_email,
            ),
            "target": build_user_reference(
                user_id=event.target_user_id,
                display_name=event.target_display_name,
                email=event.target_email,
            ),
            "actor_email": event.actor_email or "",
            "target_email": event.target_email or "",
            "campaign_slug": event.campaign_slug or "",
            "character_slug": event.character_slug or "",
            "scope": " / ".join(scope_bits) if scope_bits else "",
            "details": summarize_audit_event(event) or "",
        }

    def build_pagination_context(
        endpoint: str,
        activity_filters: dict[str, Any],
        *,
        total_events: int,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        total_pages = max(1, (total_events + AUDIT_PAGE_SIZE - 1) // AUDIT_PAGE_SIZE)
        current_page = min(int(activity_filters.get("page", 1)), total_pages)

        return {
            "current_page": current_page,
            "page_size": AUDIT_PAGE_SIZE,
            "total_events": total_events,
            "total_pages": total_pages,
            "has_previous": current_page > 1,
            "has_next": current_page < total_pages,
            "previous_url": build_activity_url(
                endpoint,
                {**activity_filters, "page": current_page},
                user_id=user_id,
                page=current_page - 1,
            )
            if current_page > 1
            else "",
            "next_url": build_activity_url(
                endpoint,
                {**activity_filters, "page": current_page},
                user_id=user_id,
                page=current_page + 1,
            )
            if current_page < total_pages
            else "",
        }

    def load_dashboard_audit_context(
        store: AuthStore,
        campaign_lookup: dict[str, str],
        activity_filters: dict[str, Any],
    ) -> dict[str, Any]:
        total_events = store.count_recent_audit_events(
            query=activity_filters["query"] or None,
            event_type=activity_filters["event_type"] or None,
            campaign_slug=activity_filters["campaign_slug"] or None,
        )
        pagination = build_pagination_context(
            "admin_dashboard",
            activity_filters,
            total_events=total_events,
        )
        effective_filters = {**activity_filters, "page": pagination["current_page"]}
        events = store.list_recent_audit_events(
            limit=AUDIT_PAGE_SIZE,
            offset=(pagination["current_page"] - 1) * AUDIT_PAGE_SIZE,
            query=effective_filters["query"] or None,
            event_type=effective_filters["event_type"] or None,
            campaign_slug=effective_filters["campaign_slug"] or None,
        )
        return {
            "activity_filters": effective_filters,
            "pagination": pagination,
            "export_url": build_activity_url("admin_activity_export", effective_filters, page=1),
            "recent_audit_events": [
                present_audit_event(event, campaign_lookup=campaign_lookup)
                for event in events
            ],
        }

    def load_user_audit_context(
        store: AuthStore,
        campaign_lookup: dict[str, str],
        activity_filters: dict[str, Any],
        *,
        user_id: int,
    ) -> dict[str, Any]:
        total_events = store.count_audit_events_for_user(
            user_id,
            query=activity_filters["query"] or None,
            event_type=activity_filters["event_type"] or None,
            campaign_slug=activity_filters["campaign_slug"] or None,
        )
        pagination = build_pagination_context(
            "admin_user_detail",
            activity_filters,
            total_events=total_events,
            user_id=user_id,
        )
        effective_filters = {**activity_filters, "page": pagination["current_page"]}
        events = store.list_audit_events_for_user(
            user_id,
            limit=AUDIT_PAGE_SIZE,
            offset=(pagination["current_page"] - 1) * AUDIT_PAGE_SIZE,
            query=effective_filters["query"] or None,
            event_type=effective_filters["event_type"] or None,
            campaign_slug=effective_filters["campaign_slug"] or None,
        )
        return {
            "activity_filters": effective_filters,
            "pagination": pagination,
            "export_url": build_activity_url(
                "admin_user_activity_export",
                effective_filters,
                user_id=user_id,
                page=1,
            ),
            "recent_audit_events": [
                present_audit_event(event, campaign_lookup=campaign_lookup)
                for event in events
            ],
        }

    def get_membership_form_defaults(
        user: UserAccount,
        campaigns: list[dict[str, str]],
    ) -> dict[str, str]:
        requested_campaign_slug = request.args.get("edit_membership_campaign_slug", "").strip()
        if requested_campaign_slug:
            membership = get_auth_store().get_membership(user.id, requested_campaign_slug, statuses=None)
            if membership is not None:
                return {
                    "campaign_slug": membership.campaign_slug,
                    "role": membership.role,
                    "status": membership.status,
                }

        default_campaign_slug = campaigns[0]["slug"] if campaigns else ""
        return {
            "campaign_slug": default_campaign_slug,
            "role": "player",
            "status": "active",
        }

    def get_assignment_form_defaults(character_choices: list[dict[str, str]]) -> dict[str, str]:
        requested_campaign_slug = request.args.get("edit_assignment_campaign_slug", "").strip()
        requested_character_slug = request.args.get("edit_assignment_character_slug", "").strip()
        requested_ref = ""
        if requested_campaign_slug and requested_character_slug:
            requested_ref = f"{requested_campaign_slug}::{requested_character_slug}"

        available_refs = {item["value"] for item in character_choices}
        if requested_ref and requested_ref in available_refs:
            return {"character_ref": requested_ref}

        default_ref = character_choices[0]["value"] if character_choices else ""
        return {"character_ref": default_ref}

    def get_invite_form_defaults(campaigns: list[dict[str, str]]) -> dict[str, str]:
        default_campaign_slug = campaigns[0]["slug"] if campaigns else ""
        return {
            "user_type": "player" if campaigns else "admin",
            "campaign_slug": default_campaign_slug,
        }

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
        campaign_choices = list_campaign_choices()
        campaign_lookup = {campaign.slug: campaign.title for campaign in repository.campaigns.values()}

        user_cards: list[dict[str, Any]] = []
        for user in users:
            memberships = store.list_memberships_for_user(
                user.id,
                statuses=("active", "invited", "removed"),
            )
            assignments = store.list_character_assignments_for_user(user.id)
            user_cards.append(
                {
                    "id": user.id,
                    "email": user.email,
                    "display_name": user.display_name,
                    "status": user.status,
                    "is_admin": user.is_admin,
                    "membership_summary": [
                        f"{campaign_lookup.get(membership.campaign_slug, membership.campaign_slug)}"
                        f" | {membership.role} ({membership.status})"
                        for membership in memberships
                    ],
                    "assignment_summary": [
                        f"{assignment.campaign_slug}/{assignment.character_slug}" for assignment in assignments
                    ],
                }
            )

        dashboard_audit_context = load_dashboard_audit_context(
            store,
            campaign_lookup,
            get_activity_filters(campaign_choices),
        )

        return {
            "campaign_choices": campaign_choices,
            "invite_form_defaults": get_invite_form_defaults(campaign_choices),
            "audit_event_type_choices": list_audit_event_type_choices(),
            "user_cards": sorted(user_cards, key=lambda item: item["email"]),
            **dashboard_audit_context,
        }

    def build_user_detail_context(user: UserAccount) -> dict[str, Any]:
        store = get_auth_store()
        repository = get_repository()
        campaigns = list_campaign_choices()
        character_choices = list_character_choices()
        campaign_lookup = {campaign.slug: campaign.title for campaign in repository.campaigns.values()}
        memberships = store.list_memberships_for_user(
            user.id,
            statuses=("active", "invited", "removed"),
        )
        assignments = store.list_character_assignments_for_user(user.id)
        current_user = get_current_user()
        user_audit_context = load_user_audit_context(
            store,
            campaign_lookup,
            get_activity_filters(campaigns),
            user_id=user.id,
        )

        return {
            "managed_user": user,
            "campaign_choices": campaigns,
            "character_choices": character_choices,
            "memberships": memberships,
            "assignments": assignments,
            "campaign_lookup": campaign_lookup,
            "audit_event_type_choices": list_audit_event_type_choices(),
            "membership_form_defaults": get_membership_form_defaults(user, campaigns),
            "assignment_form_defaults": get_assignment_form_defaults(character_choices),
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
        campaign_choices = list_campaign_choices()
        campaign_lookup = {campaign.slug: campaign.title for campaign in get_repository().campaigns.values()}
        activity_filters = get_activity_filters(campaign_choices)
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
        campaign_choices = list_campaign_choices()
        campaign_lookup = {campaign.slug: campaign.title for campaign in get_repository().campaigns.values()}
        activity_filters = get_activity_filters(campaign_choices)
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
        flash(f"Assigned {character_slug} in {campaign_slug} to {user.email}.", "success")
        return redirect(url_for("admin_user_detail", user_id=user.id))

    @app.post("/admin/users/<int:user_id>/assignment/remove")
    @admin_required
    def admin_remove_character_assignment(user_id: int):
        user = require_user(user_id)
        store = get_auth_store()
        campaign_slug = request.form.get("campaign_slug", "").strip()
        character_slug = request.form.get("character_slug", "").strip()
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
        flash(f"Cleared assignment for {character_slug} in {campaign_slug}.", "success")
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
