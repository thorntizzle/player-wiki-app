from __future__ import annotations

import re
from typing import Any


_MARTIAL_ART_STYLE_EQUIPMENT_HINTS = (
    (("jian sword",), "weapon", "Jian"),
    (("bo and spear", "staff and spear"), "weapon", "Bo staff or spear"),
    (("saber sword", "sabre sword"), "weapon", "Saber"),
    (("dagger",), "weapon", "Daggers"),
    (("sword martial art",), "weapon", "Sword"),
    (("instrument",), "tool", "Musical instrument"),
    (("puppet",), "tool", "Puppet"),
)

_TRAINED_SKILL_TOOL_HINTS = (
    (("fishing", "fish"), "Fishing rod, spear, or net"),
    (("calligraphy", "scribe", "painting", "brushwork"), "Calligraphy brush"),
    (("tea ceremony", "tea making", "tea-making"), "Tea set"),
    (("medicine", "first aid", "healing", "herbalism", "herbalist"), "Medical kit or herbalism tools"),
    (("alchemy",), "Alchemy tools"),
    (("cooking", "cook", "culinary"), "Cooking tools"),
    (("smithing", "smith", "metalwork"), "Smithing tools"),
    (("carpentry", "woodcarving", "woodwork"), "Carpentry or woodcarving tools"),
    (("weaving", "tailoring", "sewing"), "Weaver's tools or sewing kit"),
    (("music", "musician", "instrument"), "Musical instrument"),
    (("navigation", "navigator", "sailing"), "Navigator's tools"),
    (("lockpicking", "lock picking", "thieves tools", "thieves' tools"), "Thieves' tools"),
)


def infer_xianxia_required_equipment(
    *,
    martial_arts: list[dict[str, Any]] | None = None,
    trained_skills: list[str] | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Infer only necessary Xianxia creation weapons/tools from structured picks."""

    weapons: list[dict[str, str]] = []
    tools: list[dict[str, str]] = []
    seen_weapons: set[str] = set()
    seen_tools: set[str] = set()

    for martial_art in list(martial_arts or []):
        if not isinstance(martial_art, dict):
            continue
        title = _clean_text(martial_art.get("title") or martial_art.get("name"))
        style = _clean_text(
            martial_art.get("martial_art_style")
            or martial_art.get("style")
            or martial_art.get("xianxia_martial_art_style")
        )
        if not title or not style:
            continue
        inferred = _infer_from_martial_art_style(style)
        if inferred is None:
            continue
        category, name = inferred
        reason = f"Required by {title}"
        if category == "weapon":
            _append_equipment_record(weapons, seen_weapons, name=name, reason=reason)
        else:
            _append_equipment_record(tools, seen_tools, name=name, reason=reason)

    for skill_name in list(trained_skills or []):
        skill = _clean_text(skill_name)
        if not skill:
            continue
        tool_name = _infer_tool_from_trained_skill(skill)
        if tool_name:
            _append_equipment_record(
                tools,
                seen_tools,
                name=tool_name,
                reason=f"Required for {skill}",
            )

    return {"necessary_weapons": weapons, "necessary_tools": tools}


def _infer_from_martial_art_style(style: str) -> tuple[str, str] | None:
    for phrases, category, equipment_name in _MARTIAL_ART_STYLE_EQUIPMENT_HINTS:
        if any(_contains_phrase(style, phrase) for phrase in phrases):
            return category, equipment_name
    return None


def _infer_tool_from_trained_skill(skill: str) -> str:
    for phrases, tool_name in _TRAINED_SKILL_TOOL_HINTS:
        if any(_contains_phrase(skill, phrase) for phrase in phrases):
            return tool_name
    return ""


def _append_equipment_record(
    records: list[dict[str, str]],
    seen: set[str],
    *,
    name: str,
    reason: str,
) -> None:
    cleaned_name = _clean_text(name)
    if not cleaned_name:
        return
    marker = _search_text(cleaned_name)
    if marker in seen:
        return
    seen.add(marker)
    record = {"name": cleaned_name}
    cleaned_reason = _clean_text(reason)
    if cleaned_reason:
        record["reason"] = cleaned_reason
    records.append(record)


def _contains_phrase(value: str, phrase: str) -> bool:
    haystack = f" {_search_text(value)} "
    needle = f" {_search_text(phrase)} "
    return needle in haystack


def _search_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9']+", " ", str(value or "").casefold()).strip()


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()
