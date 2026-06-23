from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlencode

from .auth_store import AuditEventRecord, AuthStore

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
    "campaign_systems_shared_entry_updated": "Shared Systems entry updated",
}

SOURCE_LABELS = {
    "admin_screen": "admin screen",
    "manage.py": "CLI",
    "invite": "invite setup",
    "reset_token": "reset link",
    "campaign_control_panel": "campaign control panel",
    "dm_content_player_wiki": "DM Content player wiki",
    "campaign_systems_control_panel": "systems control panel",
    "campaign_systems_shared_entry_editor": "shared Systems entry editor",
    "character_controls": "character controls",
}

AUDIT_PAGE_SIZE = 10

ActivityFilters = dict[str, Any]
UserReferenceBuilder = Callable[
    [int | None, str | None, str | None],
    dict[str, str] | None,
]


def list_audit_event_type_choices() -> list[dict[str, str]]:
    return [
        {"value": event_type, "label": EVENT_TITLES.get(event_type, event_type.replace("_", " ").title())}
        for event_type in sorted(EVENT_TITLES)
    ]


def get_activity_filters(
    args: Mapping[str, Any],
    campaign_choices: list[dict[str, str]],
) -> ActivityFilters:
    allowed_campaigns = {item["slug"] for item in campaign_choices}
    allowed_event_types = set(EVENT_TITLES)

    query = str(args.get("audit_q", "") or "").strip()
    event_type = str(args.get("audit_event_type", "") or "").strip()
    campaign_slug = str(args.get("audit_campaign_slug", "") or "").strip()
    raw_page = str(args.get("audit_page", "") or "").strip()

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


def build_activity_params(activity_filters: ActivityFilters, *, page: int | None = None) -> dict[str, Any]:
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
    return params


def build_activity_query_url(path: str, activity_filters: ActivityFilters, *, page: int | None = None) -> str:
    params = build_activity_params(activity_filters, page=page)
    query = urlencode(params)
    return f"{path}?{query}" if query else path


def format_admin_timestamp(value: Any) -> str:
    return value.strftime("%Y-%m-%d %H:%M UTC")


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
    build_user_reference: UserReferenceBuilder,
    include_id: bool = False,
) -> dict[str, Any]:
    scope_bits: list[str] = []
    if event.campaign_slug:
        scope_bits.append(campaign_lookup.get(event.campaign_slug, event.campaign_slug))
    if event.character_slug:
        scope_bits.append(event.character_slug)

    payload = {
        "event_type": event.event_type,
        "title": EVENT_TITLES.get(event.event_type, event.event_type.replace("_", " ").title()),
        "timestamp": format_admin_timestamp(event.created_at),
        "actor": build_user_reference(
            event.actor_user_id,
            event.actor_display_name,
            event.actor_email,
        ),
        "target": build_user_reference(
            event.target_user_id,
            event.target_display_name,
            event.target_email,
        ),
        "actor_email": event.actor_email or "",
        "target_email": event.target_email or "",
        "campaign_slug": event.campaign_slug or "",
        "character_slug": event.character_slug or "",
        "scope": " / ".join(scope_bits) if scope_bits else "",
        "details": summarize_audit_event(event) or "",
    }
    if include_id:
        payload["id"] = event.id
    return payload


def build_pagination_context(
    activity_filters: ActivityFilters,
    *,
    total_events: int,
    build_page_url: Callable[[ActivityFilters, int], str],
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
        "previous_url": build_page_url(activity_filters, current_page - 1) if current_page > 1 else "",
        "next_url": build_page_url(activity_filters, current_page + 1) if current_page < total_pages else "",
    }


def load_dashboard_audit_context(
    store: AuthStore,
    campaign_lookup: dict[str, str],
    activity_filters: ActivityFilters,
    *,
    build_page_url: Callable[[ActivityFilters, int], str],
    build_export_url: Callable[[ActivityFilters], str],
    build_user_reference: UserReferenceBuilder,
    include_event_id: bool = False,
) -> dict[str, Any]:
    total_events = store.count_recent_audit_events(
        query=activity_filters["query"] or None,
        event_type=activity_filters["event_type"] or None,
        campaign_slug=activity_filters["campaign_slug"] or None,
    )
    pagination = build_pagination_context(
        activity_filters,
        total_events=total_events,
        build_page_url=build_page_url,
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
        "export_url": build_export_url(effective_filters),
        "recent_audit_events": [
            present_audit_event(
                event,
                campaign_lookup=campaign_lookup,
                build_user_reference=build_user_reference,
                include_id=include_event_id,
            )
            for event in events
        ],
    }


def load_user_audit_context(
    store: AuthStore,
    campaign_lookup: dict[str, str],
    activity_filters: ActivityFilters,
    *,
    user_id: int,
    build_page_url: Callable[[ActivityFilters, int], str],
    build_export_url: Callable[[ActivityFilters], str],
    build_user_reference: UserReferenceBuilder,
    include_event_id: bool = False,
) -> dict[str, Any]:
    total_events = store.count_audit_events_for_user(
        user_id,
        query=activity_filters["query"] or None,
        event_type=activity_filters["event_type"] or None,
        campaign_slug=activity_filters["campaign_slug"] or None,
    )
    pagination = build_pagination_context(
        activity_filters,
        total_events=total_events,
        build_page_url=build_page_url,
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
        "export_url": build_export_url(effective_filters),
        "recent_audit_events": [
            present_audit_event(
                event,
                campaign_lookup=campaign_lookup,
                build_user_reference=build_user_reference,
                include_id=include_event_id,
            )
            for event in events
        ],
    }
