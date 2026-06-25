from __future__ import annotations

import re
from typing import Any

from .repository import normalize_lookup, slugify

ARTIFICER_INFUSIONS_FEATURE_NAME = "Artificer Infusions"
ARTIFICER_INFUSIONS_FEATURE_KEY = normalize_lookup(ARTIFICER_INFUSIONS_FEATURE_NAME)
ENHANCED_DEFENSE_INFUSION_KEY = "enhanced-defense"

KNOWN_ARTIFICER_INFUSION_TITLES = {
    "arcane propulsion armor",
    "armor of magical strength",
    "boots of the winding path",
    "enhanced arcane focus",
    "enhanced defense",
    "enhanced weapon",
    "helm of awareness",
    "homunculus servant",
    "mind sharpener",
    "radiant weapon",
    "repeating shot",
    "replicate magic item",
    "repulsion shield",
    "resistant armor",
    "returning weapon",
    "spell-refueling ring",
}

ARTIFICER_INFUSION_KNOWN_CAPACITY_BY_LEVEL = (
    (18, 12),
    (14, 10),
    (10, 8),
    (6, 6),
    (2, 4),
)

ARTIFICER_INFUSION_ACTIVE_CAPACITY_BY_LEVEL = (
    (18, 6),
    (14, 5),
    (10, 4),
    (6, 3),
    (2, 2),
)


def artificer_level_from_definition(definition: Any) -> int:
    profile = dict(getattr(definition, "profile", {}) or {})
    total = 0
    for row in list(profile.get("classes") or []):
        payload = dict(row or {})
        class_name = str(payload.get("class_name") or "").strip()
        class_ref = dict(payload.get("class_ref") or payload.get("systems_ref") or {})
        ref_title = str(class_ref.get("title") or "").strip()
        ref_slug = str(class_ref.get("slug") or "").strip()
        if normalize_lookup(class_name) != "artificer" and normalize_lookup(ref_title) != "artificer":
            if "artificer" not in normalize_lookup(ref_slug):
                continue
        try:
            total += max(int(payload.get("level") or 0), 0)
        except (TypeError, ValueError):
            continue
    if total:
        return total
    class_level_text = str(profile.get("class_level_text") or "").strip()
    match = re.search(r"\bArtificer\s+(\d+)\b", class_level_text, flags=re.IGNORECASE)
    if match is None:
        return 0
    try:
        return max(int(match.group(1)), 0)
    except (TypeError, ValueError):
        return 0


def artificer_infusion_known_capacity(artificer_level: int) -> int:
    return _capacity_for_level(artificer_level, ARTIFICER_INFUSION_KNOWN_CAPACITY_BY_LEVEL)


def artificer_infusion_active_capacity(artificer_level: int) -> int:
    return _capacity_for_level(artificer_level, ARTIFICER_INFUSION_ACTIVE_CAPACITY_BY_LEVEL)


def _capacity_for_level(level: int, table: tuple[tuple[int, int], ...]) -> int:
    try:
        resolved_level = int(level or 0)
    except (TypeError, ValueError):
        resolved_level = 0
    for minimum_level, capacity in table:
        if resolved_level >= minimum_level:
            return capacity
    return 0


def artificer_infusion_key(name: Any) -> str:
    return slugify(str(name or "").strip())


def active_infusion_payload(name: Any, *, feature_id: Any = "") -> dict[str, Any]:
    clean_name = str(name or "").strip()
    key = artificer_infusion_key(clean_name)
    payload = {
        "infusion_key": key,
        "name": clean_name,
    }
    clean_feature_id = str(feature_id or "").strip()
    if clean_feature_id:
        payload["source_feature_id"] = clean_feature_id
    effect_key = artificer_infusion_effect_key(key)
    if effect_key:
        payload["effect_key"] = effect_key
    return payload


def normalize_active_infusions(value: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_entry in list(value or []):
        if not isinstance(raw_entry, dict):
            continue
        name = str(raw_entry.get("name") or "").strip()
        key = str(raw_entry.get("infusion_key") or raw_entry.get("key") or "").strip()
        if not key and name:
            key = artificer_infusion_key(name)
        if not key or key in seen:
            continue
        seen.add(key)
        payload = {
            "infusion_key": key,
            "name": name or _title_from_key(key),
        }
        source_feature_id = str(raw_entry.get("source_feature_id") or "").strip()
        if source_feature_id:
            payload["source_feature_id"] = source_feature_id
        effect_key = artificer_infusion_effect_key(key)
        if effect_key:
            payload["effect_key"] = effect_key
        normalized.append(payload)
    return normalized


def item_active_infusions(item: dict[str, Any]) -> list[dict[str, Any]]:
    return normalize_active_infusions(dict(item or {}).get("active_infusions"))


def item_has_active_infusion(item: dict[str, Any], infusion_key: str) -> bool:
    normalized_key = str(infusion_key or "").strip()
    return any(entry.get("infusion_key") == normalized_key for entry in item_active_infusions(item))


def active_infusion_armor_class_bonus(item: dict[str, Any]) -> int:
    return 1 if item_has_active_infusion(item, ENHANCED_DEFENSE_INFUSION_KEY) else 0


def artificer_infusion_effect_key(infusion_key: Any) -> str:
    if str(infusion_key or "").strip() == ENHANCED_DEFENSE_INFUSION_KEY:
        return "enhanced_defense"
    return ""


def known_artificer_infusions(definition: Any) -> list[dict[str, Any]]:
    features = [dict(feature or {}) for feature in list(getattr(definition, "features", []) or [])]
    parent_ids = {
        str(feature.get("id") or "").strip()
        for feature in features
        if normalize_lookup(feature.get("name")) == ARTIFICER_INFUSIONS_FEATURE_KEY
        if str(feature.get("id") or "").strip()
    }
    known: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    def add_known(name: Any, *, feature_id: Any = "") -> None:
        clean_name = str(name or "").strip()
        key = artificer_infusion_key(clean_name)
        if not clean_name or not key or key in seen_keys:
            return
        seen_keys.add(key)
        known.append(active_infusion_payload(clean_name, feature_id=feature_id))

    for feature in features:
        feature_name = str(feature.get("name") or "").strip()
        normalized_name = normalize_lookup(feature_name)
        if normalized_name == ARTIFICER_INFUSIONS_FEATURE_KEY:
            for summary_name in _known_infusion_names_from_summary(feature.get("description_markdown")):
                add_known(summary_name)
            continue
        parent_id = str(
            feature.get("native_edit_parent_feature_id")
            or feature.get("parent_feature_id")
            or ""
        ).strip()
        base_name = _base_infusion_name(feature_name)
        if parent_id in parent_ids or normalize_lookup(base_name) in KNOWN_ARTIFICER_INFUSION_TITLES:
            add_known(feature_name, feature_id=feature.get("id"))
    return known


def has_artificer_infusion_feature(definition: Any) -> bool:
    return any(
        normalize_lookup(dict(feature or {}).get("name")) == ARTIFICER_INFUSIONS_FEATURE_KEY
        for feature in list(getattr(definition, "features", []) or [])
    )


def _known_infusion_names_from_summary(value: Any) -> list[str]:
    text = str(value or "")
    if not text:
        return []
    match = re.search(
        r"known infusions at artificer level\s+\d+\s*:\s*(.+?)(?:\n\n|\r\n\r\n|$)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        return []
    return [
        part.strip(" .")
        for part in re.split(r"\s+-\s+", match.group(1).strip())
        if part.strip(" .")
    ]


def _base_infusion_name(value: Any) -> str:
    clean_value = str(value or "").strip()
    if normalize_lookup(clean_value).startswith("replicate magic item"):
        return "Replicate Magic Item"
    return clean_value


def _title_from_key(key: str) -> str:
    return " ".join(part.capitalize() for part in str(key or "").replace("-", " ").split())
