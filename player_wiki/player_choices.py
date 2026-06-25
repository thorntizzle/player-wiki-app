from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from .auth_store import AuthStore


def _session_recipient_label(user_id: int, display_name: str, character_names: list[str]) -> str:
    username = display_name.strip() or f"User {user_id}"
    if not character_names:
        return username

    primary_character = character_names[0]
    if len(character_names) > 1:
        primary_character = f"{primary_character} + {len(character_names) - 1}"
    return f"{primary_character} ({username})"


def build_active_player_choices(
    store: AuthStore,
    campaign_slug: str,
    *,
    current_user_id: int | None = None,
    include_current: bool = False,
    label_mode: str = "display_email",
    character_names_by_user_id: Mapping[int, list[str]] | None = None,
) -> list[dict[str, Any]]:
    choices: list[dict[str, Any]] = []
    character_names_by_user_id = character_names_by_user_id or {}
    for user, _membership in store.list_campaign_user_memberships(
        campaign_slug,
        statuses=("active",),
        roles=("player",),
        user_statuses=("active",),
    ):
        if label_mode == "character_with_display_name":
            label = _session_recipient_label(
                int(user.id),
                str(user.display_name or ""),
                [
                    str(character_name).strip()
                    for character_name in list(character_names_by_user_id.get(int(user.id), []))
                    if str(character_name).strip()
                ],
            )
        else:
            label = f"{user.display_name} ({user.email})"
        choice: dict[str, Any] = {
            "user_id": user.id,
            "label": label,
        }
        if include_current:
            choice["is_current"] = bool(current_user_id is not None and user.id == current_user_id)
        choices.append(choice)

    if label_mode == "character_with_display_name":
        label_counts = Counter(str(choice["label"]) for choice in choices)
        for choice in choices:
            if label_counts[str(choice["label"])] > 1:
                choice["label"] = f"{choice['label']} [User {choice['user_id']}]"
    return choices
