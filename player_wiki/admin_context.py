from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def list_campaign_choices(repository: Any) -> list[dict[str, str]]:
    return [
        {"slug": campaign.slug, "title": campaign.title}
        for campaign in sorted(repository.campaigns.values(), key=lambda item: item.title.lower())
    ]


def list_character_choices(repository: Any, character_repository: Any) -> list[dict[str, str]]:
    choices: list[dict[str, str]] = []
    for campaign in sorted(repository.campaigns.values(), key=lambda item: item.title.lower()):
        for record in character_repository.list_visible_characters(campaign.slug):
            choices.append(
                {
                    "campaign_slug": campaign.slug,
                    "character_slug": record.definition.character_slug,
                    "label": f"{campaign.title} | {record.definition.name}",
                    "value": f"{campaign.slug}::{record.definition.character_slug}",
                }
            )
    return choices


def get_membership_form_defaults(
    args: Mapping[str, Any],
    store: Any,
    user_id: int,
    campaigns: list[dict[str, str]],
) -> dict[str, str]:
    requested_campaign_slug = str(args.get("edit_membership_campaign_slug", "") or "").strip()
    if requested_campaign_slug:
        membership = store.get_membership(user_id, requested_campaign_slug, statuses=None)
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


def get_assignment_form_defaults(
    args: Mapping[str, Any],
    character_choices: list[dict[str, str]],
) -> dict[str, str]:
    requested_campaign_slug = str(args.get("edit_assignment_campaign_slug", "") or "").strip()
    requested_character_slug = str(args.get("edit_assignment_character_slug", "") or "").strip()
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
