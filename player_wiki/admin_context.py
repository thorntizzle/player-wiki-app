from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


def build_campaign_lookup(repository: Any) -> dict[str, str]:
    return {campaign.slug: campaign.title for campaign in repository.campaigns.values()}


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


def build_user_reference_payload(
    user_id: int | None,
    display_name: str | None,
    email: str | None,
    *,
    href: str,
    flask_href: str | None = None,
) -> dict[str, str] | None:
    if user_id is None or email is None:
        return None

    label = display_name or email
    payload = {
        "label": label,
        "meta": email if display_name and display_name != email else "",
        "href": href,
    }
    if flask_href is not None:
        payload["flask_href"] = flask_href
    return payload


def build_user_card_summaries(
    store: Any,
    users: list[Any],
    campaign_lookup: dict[str, str],
    *,
    build_links: Callable[[Any], Mapping[str, str]] | None = None,
) -> list[dict[str, Any]]:
    user_cards: list[dict[str, Any]] = []
    for user in users:
        memberships = store.list_memberships_for_user(
            user.id,
            statuses=("active", "invited", "removed"),
        )
        assignments = store.list_character_assignments_for_user(user.id)
        card: dict[str, Any] = {
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
        if build_links is not None:
            card.update(dict(build_links(user)))
        user_cards.append(card)

    return sorted(user_cards, key=lambda item: item["email"])
