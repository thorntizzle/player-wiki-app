from __future__ import annotations

import re
from typing import Any

CLASS_LEVEL_NAME_PATTERN = re.compile(r"^(?P<name>[A-Za-z][A-Za-z' -]*?)(?:\s+\d+)?$")
CLASS_LEVEL_NUMBER_PATTERN = re.compile(r"(\d+)")


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _copy_ref(value: Any) -> dict[str, Any]:
    return dict(value or {}) if isinstance(value, dict) else {}


def _coerce_level(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _default_class_row_id(index: int) -> str:
    clean_index = max(int(index or 0), 1)
    return f"class-row-{clean_index}"


def _looks_populated_ref(value: Any) -> bool:
    ref = _copy_ref(value)
    return any(_clean_text(ref.get(field)) for field in ("entry_key", "slug", "title"))


def _name_from_class_level_text(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    first_segment = text.split("/", 1)[0].strip()
    match = CLASS_LEVEL_NAME_PATTERN.match(first_segment)
    if match is not None:
        return _clean_text(match.group("name"))
    return re.sub(r"\s+\d+\s*$", "", first_segment).strip()


def profile_class_rows(profile: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [dict(row or {}) for row in list(dict(profile or {}).get("classes") or []) if isinstance(row, dict)]


def ensure_profile_class_rows(profile: dict[str, Any] | None) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []
    for index, row in enumerate(profile_class_rows(profile), start=1):
        payload = dict(row or {})
        row_id = _clean_text(payload.get("row_id")) or _default_class_row_id(index)
        payload["row_id"] = row_id
        payload["level"] = _coerce_level(payload.get("level"))

        class_ref = _copy_ref(payload.get("systems_ref"))
        if class_ref:
            payload["systems_ref"] = class_ref
            if not _clean_text(payload.get("class_name")):
                payload["class_name"] = _clean_text(class_ref.get("title"))
        else:
            payload.pop("systems_ref", None)
            payload["class_name"] = _clean_text(payload.get("class_name"))

        subclass_ref = _copy_ref(payload.get("subclass_ref"))
        if subclass_ref:
            payload["subclass_ref"] = subclass_ref
            if not _clean_text(payload.get("subclass_name")):
                payload["subclass_name"] = _clean_text(subclass_ref.get("title"))
        else:
            payload.pop("subclass_ref", None)
            payload["subclass_name"] = _clean_text(payload.get("subclass_name"))

        normalized_rows.append(payload)
    return normalized_rows


def profile_class_row_by_id(profile: dict[str, Any] | None, row_id: str) -> dict[str, Any]:
    target_row_id = _clean_text(row_id)
    if not target_row_id:
        return {}
    for row in ensure_profile_class_rows(profile):
        if _clean_text(row.get("row_id")) == target_row_id:
            return dict(row)
    return {}


def profile_primary_class_row(profile: dict[str, Any] | None) -> dict[str, Any]:
    class_rows = ensure_profile_class_rows(profile)
    return dict(class_rows[0] or {}) if class_rows else {}


def profile_primary_class_ref(profile: dict[str, Any] | None) -> dict[str, Any]:
    primary_row = profile_primary_class_row(profile)
    if _looks_populated_ref(primary_row.get("systems_ref")):
        return _copy_ref(primary_row.get("systems_ref"))
    current_profile = dict(profile or {})
    if _looks_populated_ref(current_profile.get("class_ref")):
        return _copy_ref(current_profile.get("class_ref"))
    return {}


def profile_primary_subclass_ref(profile: dict[str, Any] | None) -> dict[str, Any]:
    primary_row = profile_primary_class_row(profile)
    if _looks_populated_ref(primary_row.get("subclass_ref")):
        return _copy_ref(primary_row.get("subclass_ref"))
    current_profile = dict(profile or {})
    if _looks_populated_ref(current_profile.get("subclass_ref")):
        return _copy_ref(current_profile.get("subclass_ref"))
    return {}


def profile_primary_class_name(profile: dict[str, Any] | None) -> str:
    primary_row = profile_primary_class_row(profile)
    class_ref = _copy_ref(primary_row.get("systems_ref"))
    class_name = _clean_text(class_ref.get("title") or primary_row.get("class_name"))
    if class_name:
        return class_name
    current_profile = dict(profile or {})
    profile_class_ref = _copy_ref(current_profile.get("class_ref"))
    class_name = _clean_text(profile_class_ref.get("title"))
    if class_name:
        return class_name
    return _name_from_class_level_text(current_profile.get("class_level_text"))


def profile_primary_subclass_name(profile: dict[str, Any] | None) -> str:
    primary_row = profile_primary_class_row(profile)
    subclass_ref = _copy_ref(primary_row.get("subclass_ref"))
    subclass_name = _clean_text(subclass_ref.get("title") or primary_row.get("subclass_name"))
    if subclass_name:
        return subclass_name
    current_profile = dict(profile or {})
    profile_subclass_ref = _copy_ref(current_profile.get("subclass_ref"))
    return _clean_text(profile_subclass_ref.get("title"))


def profile_total_level(profile: dict[str, Any] | None, *, default: int = 0) -> int:
    class_rows = ensure_profile_class_rows(profile)
    total_level = sum(_coerce_level(row.get("level")) for row in class_rows)
    if total_level > 0:
        return total_level
    class_level_text = _clean_text(dict(profile or {}).get("class_level_text"))
    levels = [_coerce_level(match.group(1)) for match in CLASS_LEVEL_NUMBER_PATTERN.finditer(class_level_text)]
    return sum(levels) if levels else default


def profile_class_level_text(profile: dict[str, Any] | None, *, default: str = "Character") -> str:
    current_profile = dict(profile or {})
    parts: list[str] = []
    for row in ensure_profile_class_rows(current_profile):
        class_ref = _copy_ref(row.get("systems_ref"))
        class_name = _clean_text(class_ref.get("title") or row.get("class_name"))
        class_level = _coerce_level(row.get("level"))
        if class_name and class_level > 0:
            parts.append(f"{class_name} {class_level}")
        elif class_name:
            parts.append(class_name)
        elif class_level > 0:
            parts.append(f"Level {class_level}")
    if parts:
        return " / ".join(parts)

    stored_value = _clean_text(current_profile.get("class_level_text"))
    if stored_value:
        return stored_value

    primary_class_name = profile_primary_class_name(current_profile)
    total_level = profile_total_level(current_profile, default=0)
    if primary_class_name and total_level > 0:
        return f"{primary_class_name} {total_level}"
    if primary_class_name:
        return primary_class_name
    if total_level > 0:
        return f"Level {total_level}"
    return str(default or "Character")


def sync_profile_class_summary(profile: dict[str, Any] | None, *, default: str = "Character") -> dict[str, Any]:
    normalized_profile = dict(profile or {})
    class_rows = ensure_profile_class_rows(normalized_profile)
    if class_rows:
        normalized_profile["classes"] = class_rows
    normalized_profile["class_level_text"] = profile_class_level_text(normalized_profile, default=default)

    primary_class_ref = profile_primary_class_ref(normalized_profile)
    if primary_class_ref:
        normalized_profile["class_ref"] = primary_class_ref

    primary_subclass_ref = profile_primary_subclass_ref(normalized_profile)
    if primary_subclass_ref:
        normalized_profile["subclass_ref"] = primary_subclass_ref

    return normalized_profile
