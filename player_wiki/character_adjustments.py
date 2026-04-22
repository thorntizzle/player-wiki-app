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
ABILITY_SCORE_KEYS = ("str", "dex", "con", "int", "wis", "cha")
ABILITY_SCORE_ALIASES = {
    "str": "str",
    "strength": "str",
    "dex": "dex",
    "dexterity": "dex",
    "con": "con",
    "constitution": "con",
    "int": "int",
    "intelligence": "int",
    "wis": "wis",
    "wisdom": "wis",
    "cha": "cha",
    "charisma": "cha",
}
RECOVERABLE_PENALTY_KIND_MAX_HP = "max_hp"
RECOVERABLE_PENALTY_KIND_ABILITY_SCORE = "ability_score"


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


def normalize_recoverable_penalties(payload: Any) -> list[dict[str, Any]]:
    penalties: list[dict[str, Any]] = []
    for raw_entry in list(payload or []):
        if not isinstance(raw_entry, dict):
            continue
        kind = str(raw_entry.get("kind") or "").strip().lower()
        try:
            amount = int(raw_entry.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        entry = {
            "id": str(raw_entry.get("id") or "").strip(),
            "kind": kind,
            "amount": amount,
            "source": " ".join(str(raw_entry.get("source") or "").split()).strip(),
            "notes": str(raw_entry.get("notes") or "").strip(),
        }
        if kind == RECOVERABLE_PENALTY_KIND_MAX_HP:
            penalties.append(entry)
            continue
        if kind != RECOVERABLE_PENALTY_KIND_ABILITY_SCORE:
            continue
        ability_key = _normalize_ability_score_key(raw_entry.get("ability_key"))
        if not ability_key:
            continue
        entry["ability_key"] = ability_key
        penalties.append(entry)
    return penalties


def apply_stat_adjustments(stats: dict[str, Any], adjustments: Any) -> dict[str, Any]:
    return _apply_manual_stat_adjustments(
        stats,
        normalize_manual_stat_adjustments(adjustments),
        include_metadata=False,
    )


def apply_manual_stat_adjustments(stats: dict[str, Any], adjustments: Any) -> dict[str, Any]:
    return _apply_manual_stat_adjustments(stats, normalize_manual_stat_adjustments(adjustments), include_metadata=True)


def apply_recoverable_stat_penalties(
    stats: dict[str, Any],
    penalties: Any,
    *,
    adjust_ability_scores: bool = True,
) -> dict[str, Any]:
    return _apply_recoverable_stat_penalties(
        stats,
        normalize_recoverable_penalties(penalties),
        include_metadata=True,
        adjust_ability_scores=adjust_ability_scores,
    )


def strip_manual_stat_adjustments(stats: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    base_stats = deepcopy(stats or {})
    adjustments = normalize_manual_stat_adjustments(base_stats.get("manual_adjustments"))
    base_stats.pop("manual_adjustments", None)
    if not adjustments:
        return base_stats, {}
    reverse_adjustments = {key: -value for key, value in adjustments.items()}
    return _apply_manual_stat_adjustments(base_stats, reverse_adjustments, include_metadata=False), adjustments


def strip_recoverable_stat_penalties(
    stats: dict[str, Any],
    *,
    restore_ability_scores: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    base_stats = deepcopy(stats or {})
    penalties = normalize_recoverable_penalties(base_stats.get("recoverable_penalties"))
    base_stats.pop("recoverable_penalties", None)
    if not penalties:
        return base_stats, []
    return (
        _apply_recoverable_stat_penalties(
            base_stats,
            penalties,
            include_metadata=False,
            reverse=True,
            adjust_ability_scores=restore_ability_scores,
        ),
        penalties,
    )


def apply_recoverable_ability_score_penalties(
    ability_scores: dict[str, int],
    penalties: Any,
) -> dict[str, int]:
    adjusted_scores = {
        ability_key: int(ability_scores.get(ability_key) or 0)
        for ability_key in ABILITY_SCORE_KEYS
    }
    for ability_key, total in _recoverable_ability_score_penalty_totals(penalties).items():
        if not total:
            continue
        adjusted_scores[ability_key] = max(adjusted_scores[ability_key] - total, 0)
    return adjusted_scores


def restore_recoverable_ability_score_penalties(
    ability_scores: dict[str, int],
    penalties: Any,
) -> dict[str, int]:
    adjusted_scores = {
        ability_key: int(ability_scores.get(ability_key) or 0)
        for ability_key in ABILITY_SCORE_KEYS
    }
    for ability_key, total in _recoverable_ability_score_penalty_totals(penalties).items():
        if not total:
            continue
        adjusted_scores[ability_key] = max(adjusted_scores[ability_key] + total, 0)
    return adjusted_scores


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


def _apply_recoverable_stat_penalties(
    stats: dict[str, Any],
    penalties: list[dict[str, Any]],
    *,
    include_metadata: bool,
    reverse: bool = False,
    adjust_ability_scores: bool,
) -> dict[str, Any]:
    adjusted = deepcopy(stats or {})
    if not penalties:
        if include_metadata:
            adjusted.pop("recoverable_penalties", None)
        return adjusted

    max_hp_delta = _recoverable_max_hp_penalty_total(penalties)
    if max_hp_delta:
        direction = 1 if reverse else -1
        adjusted["max_hp"] = max(int(adjusted.get("max_hp") or 0) + (direction * max_hp_delta), 0)
    if adjust_ability_scores:
        adjusted["ability_scores"] = _apply_recoverable_ability_score_payloads(
            adjusted.get("ability_scores"),
            penalties,
            reverse=reverse,
        )
    if include_metadata:
        adjusted["recoverable_penalties"] = [dict(entry) for entry in penalties]
    return adjusted


def _recoverable_max_hp_penalty_total(penalties: Any) -> int:
    return sum(
        int(entry.get("amount") or 0)
        for entry in normalize_recoverable_penalties(penalties)
        if str(entry.get("kind") or "").strip() == RECOVERABLE_PENALTY_KIND_MAX_HP
    )


def _recoverable_ability_score_penalty_totals(penalties: Any) -> dict[str, int]:
    totals = {ability_key: 0 for ability_key in ABILITY_SCORE_KEYS}
    for entry in normalize_recoverable_penalties(penalties):
        if str(entry.get("kind") or "").strip() != RECOVERABLE_PENALTY_KIND_ABILITY_SCORE:
            continue
        ability_key = _normalize_ability_score_key(entry.get("ability_key"))
        if not ability_key:
            continue
        totals[ability_key] += int(entry.get("amount") or 0)
    return totals


def _apply_recoverable_ability_score_payloads(
    payload: Any,
    penalties: Any,
    *,
    reverse: bool,
) -> dict[str, Any]:
    adjusted = deepcopy(payload or {})
    totals = _recoverable_ability_score_penalty_totals(penalties)
    if not totals:
        return adjusted
    for key, value in list(adjusted.items()):
        ability_key = _normalize_ability_score_key(key)
        if not ability_key:
            continue
        amount = int(totals.get(ability_key) or 0)
        if not amount:
            continue
        delta = amount if reverse else -amount
        if isinstance(value, dict):
            adjusted[key] = _adjust_ability_score_payload(value, delta)
            continue
        try:
            score = int(value or 0)
        except (TypeError, ValueError):
            continue
        adjusted[key] = max(score + delta, 0)
    return adjusted


def _adjust_ability_score_payload(payload: Any, delta: int) -> dict[str, Any]:
    adjusted = dict(payload or {})
    try:
        current_score = int(adjusted.get("score") or 0)
    except (TypeError, ValueError):
        current_score = 0
    current_modifier = _ability_modifier(current_score)
    updated_score = max(current_score + int(delta or 0), 0)
    updated_modifier = _ability_modifier(updated_score)
    try:
        current_save_bonus = int(adjusted.get("save_bonus"))
    except (TypeError, ValueError):
        current_save_bonus = current_modifier
    adjusted["score"] = updated_score
    adjusted["modifier"] = updated_modifier
    adjusted["save_bonus"] = current_save_bonus + (updated_modifier - current_modifier)
    return adjusted


def _normalize_ability_score_key(value: Any) -> str:
    return ABILITY_SCORE_ALIASES.get(str(value or "").strip().lower(), "")


def _ability_modifier(score: int) -> int:
    return (int(score or 0) - 10) // 2


def _adjust_speed_label(speed_label: str, delta: int) -> str:
    clean_label = str(speed_label or "").strip()
    if not clean_label or not delta:
        return clean_label
    match = re.search(r"(-?\d+)", clean_label)
    if match is None:
        return clean_label
    updated_value = max(int(match.group(1)) + int(delta), 0)
    return clean_label[: match.start(1)] + str(updated_value) + clean_label[match.end(1) :]
