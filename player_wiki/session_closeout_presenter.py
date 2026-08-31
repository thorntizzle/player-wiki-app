from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .session_models import (
    CampaignSessionCloseoutRecord,
    CampaignSessionCloseoutSummary,
    CampaignSessionRecord,
    SESSION_CLOSEOUT_ITEM_CHARACTER_RESTS,
    SESSION_CLOSEOUT_ITEM_ENCOUNTER_DISPOSITION,
    SESSION_CLOSEOUT_ITEM_EXTERNAL_ARCHIVE,
    SESSION_CLOSEOUT_ITEM_REWARDS_AND_BOONS,
    SESSION_CLOSEOUT_ITEM_SESSION_ARTICLE_PUBLICATION,
    SESSION_CLOSEOUT_ITEM_STATUS_COMPLETE,
    SESSION_CLOSEOUT_ITEM_STATUS_NOT_APPLICABLE,
    SESSION_CLOSEOUT_ITEM_STATUS_PENDING,
    SESSION_CLOSEOUT_ITEM_STATUS_TABLE_MANAGED,
    SESSION_CLOSEOUT_ITEM_TABLE_NOTES,
    SESSION_CLOSEOUT_STATUS_COMPLETED,
)
from .session_presenter import format_session_timestamp


SESSION_CLOSEOUT_STATUS_LABELS = {
    SESSION_CLOSEOUT_ITEM_STATUS_PENDING: "Pending",
    SESSION_CLOSEOUT_ITEM_STATUS_COMPLETE: "Completed in the owning workflow",
    SESSION_CLOSEOUT_ITEM_STATUS_NOT_APPLICABLE: "Not applicable",
    SESSION_CLOSEOUT_ITEM_STATUS_TABLE_MANAGED: "Handled at the table or outside the app",
}

_STANDARD_STATUS_OPTIONS = (
    SESSION_CLOSEOUT_ITEM_STATUS_PENDING,
    SESSION_CLOSEOUT_ITEM_STATUS_COMPLETE,
    SESSION_CLOSEOUT_ITEM_STATUS_NOT_APPLICABLE,
    SESSION_CLOSEOUT_ITEM_STATUS_TABLE_MANAGED,
)

_ITEM_PRESENTATION = (
    {
        "key": SESSION_CLOSEOUT_ITEM_TABLE_NOTES,
        "title": "Table notes",
        "description": "Review the stored Session log and record whether the table notes are settled.",
        "owner_kind": "session_log",
    },
    {
        "key": SESSION_CLOSEOUT_ITEM_CHARACTER_RESTS,
        "title": "Character rests",
        "description": "Apply any rests in the Character workflow, then record the closeout result here.",
        "owner_kind": "characters",
    },
    {
        "key": SESSION_CLOSEOUT_ITEM_REWARDS_AND_BOONS,
        "title": "Rewards and boons",
        "description": "Apply rewards or boons in the Character workflow, then record the closeout result here.",
        "owner_kind": "characters",
    },
    {
        "key": SESSION_CLOSEOUT_ITEM_ENCOUNTER_DISPOSITION,
        "title": "Encounter disposition",
        "description": "Finish encounter state in Combat, then record the closeout result here.",
        "owner_kind": "combat",
    },
    {
        "key": SESSION_CLOSEOUT_ITEM_SESSION_ARTICLE_PUBLICATION,
        "title": "Session article publication",
        "description": "Publish or stage Session material in DM Content, then record the closeout result here.",
        "owner_kind": "dm_content",
    },
    {
        "key": SESSION_CLOSEOUT_ITEM_EXTERNAL_ARCHIVE,
        "title": "External archive acknowledgement",
        "description": "Acknowledge archive work performed outside the app without storing an external URL.",
        "owner_kind": "session_log",
    },
)


def is_known_closeout_item_key(value: object) -> bool:
    return str(value or "") in {item["key"] for item in _ITEM_PRESENTATION}


def present_closeout_summaries(
    summaries: list[CampaignSessionCloseoutSummary],
    *,
    detail_url_builder: Callable[[int], str],
) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "session_id": summary.session_id,
            "status_label": (
                "Completed"
                if summary.status == SESSION_CLOSEOUT_STATUS_COMPLETED
                else "Open"
            ),
            "resolved_count": summary.resolved_count,
            "item_count": summary.item_count,
            "updated_at_label": format_session_timestamp(summary.updated_at),
            "action_label": (
                "View closeout"
                if summary.status == SESSION_CLOSEOUT_STATUS_COMPLETED
                else "Resume closeout"
            ),
            "href": detail_url_builder(summary.session_id),
        }
        for summary in summaries
    )


def present_closeout_session(session_record: CampaignSessionRecord) -> dict[str, object]:
    return {
        "id": session_record.id,
        "started_at_label": format_session_timestamp(session_record.started_at),
        "ended_at_label": (
            format_session_timestamp(session_record.ended_at)
            if session_record.ended_at
            else ""
        ),
    }


def present_closeout(
    closeout: CampaignSessionCloseoutRecord,
    *,
    owner_links: Mapping[str, Mapping[str, str]],
    read_only: bool,
    affected_item_key: str = "",
    draft_status: str = "",
    draft_note: str = "",
    item_error: str = "",
    stale_conflict: bool = False,
    lifecycle_error: str = "",
    lifecycle_focus: str = "",
) -> dict[str, object]:
    items_by_key = {item.item_key: item for item in closeout.items}
    presented_items: list[dict[str, object]] = []
    editable = closeout.status != SESSION_CLOSEOUT_STATUS_COMPLETED and not read_only

    for index, definition in enumerate(_ITEM_PRESENTATION, start=1):
        item_key = str(definition["key"])
        record = items_by_key[item_key]
        affected = item_key == affected_item_key
        form_status = draft_status if affected and draft_status else record.status
        form_note = draft_note if affected else record.note
        status_values = (
            (
                SESSION_CLOSEOUT_ITEM_STATUS_PENDING,
                SESSION_CLOSEOUT_ITEM_STATUS_TABLE_MANAGED,
            )
            if item_key == SESSION_CLOSEOUT_ITEM_EXTERNAL_ARCHIVE
            else _STANDARD_STATUS_OPTIONS
        )
        link = dict(owner_links.get(str(definition["owner_kind"]), {}))
        presented_items.append(
            {
                "anchor": f"closeout-item-{index}",
                "key": item_key,
                "title": definition["title"],
                "description": definition["description"],
                "status_label": SESSION_CLOSEOUT_STATUS_LABELS[record.status],
                "saved_status_label": SESSION_CLOSEOUT_STATUS_LABELS[record.status],
                "saved_note": record.note,
                "form_status": form_status,
                "form_note": form_note,
                "status_options": tuple(
                    {
                        "value": value,
                        "label": (
                            "Acknowledged outside the app"
                            if item_key == SESSION_CLOSEOUT_ITEM_EXTERNAL_ARCHIVE
                            and value == SESSION_CLOSEOUT_ITEM_STATUS_TABLE_MANAGED
                            else SESSION_CLOSEOUT_STATUS_LABELS[value]
                        ),
                        "selected": value == form_status,
                    }
                    for value in status_values
                ),
                "editable": editable,
                "owner_href": str(link.get("href") or ""),
                "owner_label": str(link.get("label") or ""),
                "owner_unavailable": str(link.get("unavailable") or ""),
                "error": item_error if affected else "",
                "stale_conflict": bool(stale_conflict and affected),
                "autofocus": bool(affected and item_error),
                "external_archive": item_key == SESSION_CLOSEOUT_ITEM_EXTERNAL_ARCHIVE,
            }
        )

    return {
        "status_label": (
            "Completed"
            if closeout.status == SESSION_CLOSEOUT_STATUS_COMPLETED
            else "Open"
        ),
        "completed": closeout.status == SESSION_CLOSEOUT_STATUS_COMPLETED,
        "revision": closeout.revision,
        "resolved_count": closeout.resolved_count,
        "item_count": len(closeout.items),
        "updated_at_label": format_session_timestamp(closeout.updated_at),
        "items": tuple(presented_items),
        "read_only": read_only,
        "can_complete": editable and closeout.resolved_count == len(closeout.items),
        "can_reopen": closeout.status == SESSION_CLOSEOUT_STATUS_COMPLETED and not read_only,
        "lifecycle_error": lifecycle_error,
        "lifecycle_focus": lifecycle_focus,
    }


def present_session_log_closeout_action(
    closeout: CampaignSessionCloseoutRecord | None,
    *,
    read_only: bool,
    href_builder: Callable[[int], str],
    session_id: int,
) -> dict[str, Any]:
    if closeout is None:
        return {
            "exists": False,
            "show_start": not read_only,
            "read_only": read_only,
        }
    return {
        "exists": True,
        "status": closeout.status,
        "revision": closeout.revision,
        "label": (
            "View closeout"
            if closeout.status == SESSION_CLOSEOUT_STATUS_COMPLETED or read_only
            else "Resume closeout"
        ),
        "href": href_builder(session_id),
        "read_only": read_only,
    }
