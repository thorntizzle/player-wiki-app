from __future__ import annotations

from .system_policy import system_policy_for_code

CAMPAIGN_VISIBILITY_SCOPES = ("campaign", "wiki", "systems", "session", "combat", "characters", "dm_content")
CAMPAIGN_VISIBILITY_SCOPE_LABELS = {
    "campaign": "Campaign",
    "wiki": "Player Wiki",
    "systems": "Systems",
    "session": "Session",
    "combat": "Combat",
    "characters": "Characters",
    "dm_content": "DM Content",
}

VISIBILITY_PUBLIC = "public"
VISIBILITY_PLAYERS = "players"
VISIBILITY_DM = "dm"
VISIBILITY_PRIVATE = "private"

VISIBILITY_ORDER = {
    VISIBILITY_PUBLIC: 0,
    VISIBILITY_PLAYERS: 1,
    VISIBILITY_DM: 2,
    VISIBILITY_PRIVATE: 3,
}

VISIBILITY_LABELS = {
    VISIBILITY_PUBLIC: "Public",
    VISIBILITY_PLAYERS: "Players",
    VISIBILITY_DM: "DM",
    VISIBILITY_PRIVATE: "Private",
}

DEFAULT_CAMPAIGN_VISIBILITY_BY_SCOPE = {
    "campaign": VISIBILITY_PUBLIC,
    "wiki": VISIBILITY_PUBLIC,
    "systems": VISIBILITY_PLAYERS,
    "session": VISIBILITY_PLAYERS,
    "combat": VISIBILITY_PLAYERS,
    "characters": VISIBILITY_DM,
    "dm_content": VISIBILITY_DM,
}


def build_default_campaign_visibility_by_scope(system_code: object = "") -> dict[str, str]:
    defaults = dict(DEFAULT_CAMPAIGN_VISIBILITY_BY_SCOPE)
    policy = system_policy_for_code(system_code)
    for scope, visibility in policy.default_campaign_visibility_by_scope:
        normalized_scope = str(scope or "").strip().lower()
        normalized_visibility = normalize_visibility_choice(str(visibility or ""))
        if is_valid_visibility_scope(normalized_scope) and is_valid_visibility(normalized_visibility):
            defaults[normalized_scope] = normalized_visibility
    return defaults


def is_valid_visibility_scope(value: str) -> bool:
    return value in CAMPAIGN_VISIBILITY_SCOPES


def is_valid_visibility(value: str) -> bool:
    return value in VISIBILITY_ORDER


def normalize_visibility_choice(value: str) -> str:
    return (value or "").strip().lower()


def most_private_visibility(left: str, right: str) -> str:
    left_visibility = normalize_visibility_choice(left)
    right_visibility = normalize_visibility_choice(right)
    if VISIBILITY_ORDER.get(left_visibility, -1) >= VISIBILITY_ORDER.get(right_visibility, -1):
        return left_visibility
    return right_visibility


def get_default_visibility(scope: str, system_code: object = "") -> str:
    return build_default_campaign_visibility_by_scope(system_code).get(scope, VISIBILITY_PRIVATE)


def list_visibility_choices(*, include_private: bool) -> list[dict[str, str]]:
    choices = [
        {"value": VISIBILITY_PUBLIC, "label": VISIBILITY_LABELS[VISIBILITY_PUBLIC]},
        {"value": VISIBILITY_PLAYERS, "label": VISIBILITY_LABELS[VISIBILITY_PLAYERS]},
        {"value": VISIBILITY_DM, "label": VISIBILITY_LABELS[VISIBILITY_DM]},
    ]
    if include_private:
        choices.append({"value": VISIBILITY_PRIVATE, "label": VISIBILITY_LABELS[VISIBILITY_PRIVATE]})
    return choices
