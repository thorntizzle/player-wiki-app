from __future__ import annotations

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


def get_default_visibility(scope: str) -> str:
    return DEFAULT_CAMPAIGN_VISIBILITY_BY_SCOPE.get(scope, VISIBILITY_PRIVATE)


def list_visibility_choices(*, include_private: bool) -> list[dict[str, str]]:
    choices = [
        {"value": VISIBILITY_PUBLIC, "label": VISIBILITY_LABELS[VISIBILITY_PUBLIC]},
        {"value": VISIBILITY_PLAYERS, "label": VISIBILITY_LABELS[VISIBILITY_PLAYERS]},
        {"value": VISIBILITY_DM, "label": VISIBILITY_LABELS[VISIBILITY_DM]},
    ]
    if include_private:
        choices.append({"value": VISIBILITY_PRIVATE, "label": VISIBILITY_LABELS[VISIBILITY_PRIVATE]})
    return choices
