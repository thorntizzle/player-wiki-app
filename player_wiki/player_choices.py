from __future__ import annotations

from typing import Any

from .auth_store import AuthStore


def build_active_player_choices(
    store: AuthStore,
    campaign_slug: str,
    *,
    current_user_id: int | None = None,
    include_current: bool = False,
) -> list[dict[str, Any]]:
    choices: list[dict[str, Any]] = []
    for user, _membership in store.list_campaign_user_memberships(
        campaign_slug,
        statuses=("active",),
        roles=("player",),
        user_statuses=("active",),
    ):
        choice: dict[str, Any] = {
            "user_id": user.id,
            "label": f"{user.display_name} ({user.email})",
        }
        if include_current:
            choice["is_current"] = bool(current_user_id is not None and user.id == current_user_id)
        choices.append(choice)
    return choices
