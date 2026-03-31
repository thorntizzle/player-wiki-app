from __future__ import annotations

from copy import deepcopy
from typing import Any

from .auth_store import utcnow
from .character_campaign_options import normalize_campaign_character_option
from .repository import slugify
from .systems_models import SystemsEntryRecord

CAMPAIGN_PAGE_SOURCE_ID = "Campaign"
VALID_CAMPAIGN_PROGRESSION_KINDS = {"class", "subclass"}


def build_campaign_page_progression_entries(record: Any) -> list[SystemsEntryRecord]:
    metadata = dict(getattr(record, "metadata", {}) or {})
    raw_progression = metadata.get("character_progression")
    if isinstance(raw_progression, dict):
        raw_items = [raw_progression]
    elif isinstance(raw_progression, list):
        raw_items = [dict(item or {}) for item in raw_progression if isinstance(item, dict)]
    else:
        return []

    page_ref = str(getattr(record, "page_ref", "") or "").strip()
    page = getattr(record, "page", None)
    if not page_ref or page is None:
        return []

    page_title = str(getattr(page, "title", "") or "").strip() or page_ref
    default_description = str(getattr(record, "body_markdown", "") or "").strip() or str(
        getattr(page, "summary", "") or ""
    ).strip()
    entries: list[SystemsEntryRecord] = []
    seen_keys: set[tuple[str, str, str, str, int, str]] = set()
    for index, raw_item in enumerate(raw_items, start=1):
        normalized = _normalize_campaign_progression_item(
            raw_item,
            page_ref=page_ref,
            page_title=page_title,
            default_description=default_description,
        )
        if normalized is None:
            continue
        marker = (
            str(normalized.get("kind") or "").strip(),
            str(normalized.get("class_name") or "").strip().casefold(),
            str(normalized.get("class_source") or "").strip().upper(),
            str(normalized.get("subclass_name") or "").strip().casefold(),
            int(normalized.get("level") or 0),
            str(dict(normalized.get("campaign_option") or {}).get("feature_name") or "").strip().casefold(),
        )
        if marker in seen_keys:
            continue
        seen_keys.add(marker)
        entry = _build_campaign_progression_entry(
            normalized,
            page_ref=page_ref,
            page_title=page_title,
            index=index,
        )
        if entry is not None:
            entries.append(entry)
    return entries


def _normalize_campaign_progression_item(
    payload: dict[str, Any],
    *,
    page_ref: str,
    page_title: str,
    default_description: str,
) -> dict[str, Any] | None:
    target = dict(payload.get("target") or {}) if isinstance(payload.get("target"), dict) else {}
    kind = str(payload.get("kind") or target.get("kind") or "").strip().lower()
    if kind not in VALID_CAMPAIGN_PROGRESSION_KINDS:
        return None

    level = _coerce_positive_int(payload.get("level", target.get("level")))
    if level <= 0:
        return None

    class_name = str(
        payload.get("class_name")
        or payload.get("class")
        or target.get("class_name")
        or target.get("class")
        or ""
    ).strip()
    if not class_name:
        return None

    subclass_name = str(
        payload.get("subclass_name")
        or payload.get("subclass")
        or target.get("subclass_name")
        or target.get("subclass")
        or ""
    ).strip()
    if kind == "subclass" and not subclass_name:
        return None

    raw_option = dict(payload.get("character_option") or {}) if isinstance(payload.get("character_option"), dict) else {}
    if not raw_option:
        raw_option = {
            "kind": "feature",
            "name": payload.get("name") or payload.get("feature_name") or page_title,
            "description_markdown": payload.get("description_markdown") or payload.get("description") or default_description,
            "activation_type": payload.get("activation_type"),
        }
        for key in ("grants", "proficiencies", "stat_adjustments", "spells", "resource"):
            if key in payload:
                raw_option[key] = deepcopy(payload.get(key))
        spell_support = payload.get("spell_support", payload.get("spellSupport"))
        if spell_support is not None:
            raw_option["spell_support"] = deepcopy(spell_support)
    elif "kind" not in raw_option:
        raw_option["kind"] = "feature"
    if "name" not in raw_option and "feature_name" in payload:
        raw_option["name"] = payload.get("feature_name")
    if "description_markdown" not in raw_option and "description" in payload:
        raw_option["description_markdown"] = payload.get("description")

    campaign_option = normalize_campaign_character_option(
        raw_option,
        page_ref=page_ref,
        title=page_title,
        summary=default_description,
        default_kind="feature",
    )
    if campaign_option is None:
        return None

    return {
        "kind": kind,
        "class_name": class_name,
        "class_source": str(payload.get("class_source") or target.get("class_source") or "").strip().upper(),
        "subclass_name": subclass_name,
        "subclass_source": str(payload.get("subclass_source") or target.get("subclass_source") or "").strip().upper(),
        "level": level,
        "campaign_option": campaign_option,
    }


def _build_campaign_progression_entry(
    normalized: dict[str, Any],
    *,
    page_ref: str,
    page_title: str,
    index: int,
) -> SystemsEntryRecord | None:
    kind = str(normalized.get("kind") or "").strip().lower()
    if kind not in VALID_CAMPAIGN_PROGRESSION_KINDS:
        return None

    campaign_option = dict(normalized.get("campaign_option") or {})
    feature_name = str(campaign_option.get("feature_name") or page_title).strip() or page_title
    if not feature_name:
        return None

    entry_type = "classfeature" if kind == "class" else "subclassfeature"
    level = int(normalized.get("level") or 0)
    metadata = {
        "page_ref": page_ref,
        "campaign_option": campaign_option,
        "class_name": str(normalized.get("class_name") or "").strip(),
        "class_source": str(normalized.get("class_source") or "").strip().upper(),
        "level": level,
        "campaign_progression_kind": kind,
    }
    if campaign_option.get("spell_support") is not None:
        metadata["spell_support"] = deepcopy(campaign_option.get("spell_support"))
    subclass_name = str(normalized.get("subclass_name") or "").strip()
    subclass_source = str(normalized.get("subclass_source") or "").strip().upper()
    if subclass_name:
        metadata["subclass_name"] = subclass_name
    if subclass_source:
        metadata["subclass_source"] = subclass_source

    now = utcnow()
    return SystemsEntryRecord(
        id=0,
        library_slug="campaign-pages",
        source_id=CAMPAIGN_PAGE_SOURCE_ID,
        entry_key=f"campaign-page|{entry_type}|{page_ref}|{level}|{index}",
        entry_type=entry_type,
        slug=f"campaign-page-{slugify(page_ref)}-{entry_type}-{level}-{index}",
        title=feature_name,
        source_page="",
        source_path=page_ref,
        search_text=" ".join(
            part
            for part in (
                feature_name,
                str(normalized.get("class_name") or "").strip(),
                str(normalized.get("subclass_name") or "").strip(),
                str(campaign_option.get("description_markdown") or "").strip(),
                page_ref,
            )
            if part
        ).casefold(),
        player_safe_default=True,
        dm_heavy=False,
        metadata=metadata,
        body={"entries": []},
        rendered_html="",
        created_at=now,
        updated_at=now,
    )


def _coerce_positive_int(value: Any) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return 0
    return normalized if normalized > 0 else 0
