from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

MANUAL_STAT_ADJUSTMENT_KEYS = (
    "max_hp",
    "armor_class",
    "initiative_bonus",
    "speed",
    "passive_perception",
    "passive_insight",
    "passive_investigation",
)


def normalize_manual_stat_adjustments(payload: Any) -> dict[str, int]:
    raw_payload = dict(payload or {}) if isinstance(payload, dict) else {}
    adjustments: dict[str, int] = {}
    for key in MANUAL_STAT_ADJUSTMENT_KEYS:
        try:
            value = int(raw_payload.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value:
            adjustments[key] = value
    return adjustments


def apply_stat_adjustments(stats: dict[str, Any], adjustments: Any) -> dict[str, Any]:
    return _apply_manual_stat_adjustments(
        stats,
        normalize_manual_stat_adjustments(adjustments),
        include_metadata=False,
    )


def apply_manual_stat_adjustments(stats: dict[str, Any], adjustments: Any) -> dict[str, Any]:
    return _apply_manual_stat_adjustments(stats, normalize_manual_stat_adjustments(adjustments), include_metadata=True)


def strip_manual_stat_adjustments(stats: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    base_stats = deepcopy(stats or {})
    adjustments = normalize_manual_stat_adjustments(base_stats.get("manual_adjustments"))
    base_stats.pop("manual_adjustments", None)
    if not adjustments:
        return base_stats, {}
    reverse_adjustments = {key: -value for key, value in adjustments.items()}
    return _apply_manual_stat_adjustments(base_stats, reverse_adjustments, include_metadata=False), adjustments


def _apply_manual_stat_adjustments(
    stats: dict[str, Any],
    adjustments: dict[str, int],
    *,
    include_metadata: bool,
) -> dict[str, Any]:
    adjusted = deepcopy(stats or {})
    if not adjustments:
        if include_metadata:
            adjusted.pop("manual_adjustments", None)
        return adjusted

    adjusted["max_hp"] = max(int(adjusted.get("max_hp") or 0) + int(adjustments.get("max_hp") or 0), 1)
    adjusted["armor_class"] = max(int(adjusted.get("armor_class") or 0) + int(adjustments.get("armor_class") or 0), 0)
    adjusted["initiative_bonus"] = int(adjusted.get("initiative_bonus") or 0) + int(adjustments.get("initiative_bonus") or 0)
    adjusted["speed"] = _adjust_speed_label(str(adjusted.get("speed") or ""), int(adjustments.get("speed") or 0))
    adjusted["passive_perception"] = max(
        int(adjusted.get("passive_perception") or 0) + int(adjustments.get("passive_perception") or 0),
        0,
    )
    adjusted["passive_insight"] = max(
        int(adjusted.get("passive_insight") or 0) + int(adjustments.get("passive_insight") or 0),
        0,
    )
    adjusted["passive_investigation"] = max(
        int(adjusted.get("passive_investigation") or 0) + int(adjustments.get("passive_investigation") or 0),
        0,
    )
    if include_metadata:
        adjusted["manual_adjustments"] = dict(adjustments)
    return adjusted


def _adjust_speed_label(speed_label: str, delta: int) -> str:
    clean_label = str(speed_label or "").strip()
    if not clean_label or not delta:
        return clean_label
    match = re.search(r"(-?\d+)", clean_label)
    if match is None:
        return clean_label
    updated_value = max(int(match.group(1)) + int(delta), 0)
    return clean_label[: match.start(1)] + str(updated_value) + clean_label[match.end(1) :]
