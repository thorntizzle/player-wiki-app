from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Callable


def build_live_hash(*parts: object, normalize_parts: bool = False) -> str:
    if normalize_parts:
        normalized_parts = [str(part).strip().lower() for part in parts]
    else:
        normalized_parts = [str(part) for part in parts]
    digest = hashlib.sha1("||".join(normalized_parts).encode("utf-8")).hexdigest()
    return digest[:12]


def normalize_session_subpage(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "dm":
        return "dm"
    return "session"


def build_session_live_view_token(
    campaign_slug: str,
    session_subpage: str,
    *,
    session_chat_order: str,
    can_manage_session: bool,
    can_post_session_messages: bool,
    normalize_hash_parts: bool = False,
) -> str:
    return build_live_hash(
        "session",
        normalize_session_subpage(session_subpage),
        session_chat_order,
        "1" if can_manage_session else "0",
        "1" if can_post_session_messages else "0",
        normalize_parts=normalize_hash_parts,
    )


def build_combat_live_view_token(
    campaign_slug: str,
    combat_subpage: str = "player",
    *,
    selected_combatant_id: int | None = None,
    combat_dm_view: str | None = None,
    can_manage_combat: bool,
    owned_character_slugs: Iterable[str] = (),
    normalize_combat_dm_view: Callable[[str], str] | None = None,
    include_dm_view_part: bool = True,
    normalize_hash_parts: bool = False,
) -> str:
    token_parts: list[object] = [
        "combat",
        combat_subpage,
    ]
    if include_dm_view_part:
        normalized_dm_view = ""
        if combat_subpage == "dm" and normalize_combat_dm_view is not None:
            normalized_dm_view = normalize_combat_dm_view(combat_dm_view or "")
        token_parts.append(normalized_dm_view)
    token_parts.extend(
        [
            "1" if can_manage_combat else "0",
            str(selected_combatant_id or ""),
            *sorted(owned_character_slugs),
        ]
    )
    return build_live_hash(
        *token_parts,
        normalize_parts=normalize_hash_parts,
    )


def build_combat_poll_settings(combat_subpage: str) -> dict[str, int]:
    if combat_subpage == "status":
        return {
            "active_interval_ms": 1500,
            "idle_interval_ms": 4000,
            "idle_threshold_ms": 30000,
        }
    return {
        "active_interval_ms": 500,
        "idle_interval_ms": 3000,
        "idle_threshold_ms": 30000,
    }


def build_session_poll_settings(session_subpage: str) -> dict[str, int]:
    if session_subpage == "dm":
        return {
            "active_interval_ms": 2000,
            "idle_interval_ms": 5000,
            "idle_threshold_ms": 30000,
        }
    return {
        "active_interval_ms": 3000,
        "idle_interval_ms": 6000,
        "idle_threshold_ms": 30000,
    }


def parse_live_revision_header(headers: Mapping[str, str]) -> int | None:
    raw_value = headers.get("X-Live-Revision", "").strip()
    if not raw_value:
        return None
    try:
        parsed_value = int(raw_value)
    except ValueError:
        return None
    return parsed_value if parsed_value >= 0 else None


def parse_live_view_token_header(headers: Mapping[str, str]) -> str:
    return headers.get("X-Live-View-Token", "").strip()


def parse_live_detail_state_token_header(headers: Mapping[str, str]) -> str:
    return headers.get("X-Live-Detail-State-Token", "").strip()


def should_short_circuit_live_response(
    headers: Mapping[str, str],
    *,
    live_revision: int,
    live_view_token: str,
) -> bool:
    requested_revision = parse_live_revision_header(headers)
    requested_view_token = parse_live_view_token_header(headers)
    if requested_revision is None or not requested_view_token:
        return False
    return requested_revision == live_revision and requested_view_token == live_view_token


def should_skip_selected_combatant_detail_render(
    *,
    requested_detail_state_token: str,
    selected_detail_state_token: str,
) -> bool:
    if not requested_detail_state_token:
        return False
    return requested_detail_state_token == selected_detail_state_token


def build_unchanged_live_payload(
    *,
    live_revision: int,
    live_view_token: str,
) -> dict[str, object]:
    return {
        "changed": False,
        "live_revision": live_revision,
        "live_view_token": live_view_token,
    }
