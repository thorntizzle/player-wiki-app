from __future__ import annotations

from typing import Any

from .character_builder_catalogs import (
    _attach_campaign_item_page_support,
    _build_entry_slug_catalog,
    _build_feat_catalog,
    _build_item_catalog,
    _build_mixed_character_options,
    _build_spell_catalog,
    _builder_cache_get,
    _builder_request_page_key,
    _builder_service_cache_identity,
    _builder_static_cache_get,
    _builder_static_revision_key,
    _list_campaign_enabled_entries,
)
from .character_builder_constants import (
    CAMPAIGN_FEATURE_CHOICE_SLOTS,
    CAMPAIGN_ITEM_CHOICE_SLOTS,
    CAMPAIGN_ITEMS_SECTION,
    CAMPAIGN_SESSIONS_SECTION,
    LINKED_CAMPAIGN_PAGE_ALLOWED_KINDS_BY_FIELD_KIND,
    LINKED_CAMPAIGN_PAGE_REQUIRED_SECTION_BY_FIELD_KIND,
)
from .character_builder_foundation import (
    _extract_campaign_page_ref,
    _supports_native_class_entry,
)
from .character_campaign_options import build_campaign_page_character_option

__all__ = [
    "_build_campaign_feature_choice_fields",
    "_build_campaign_item_choice_fields",
    "_build_campaign_page_choice_options",
    "_build_common_builder_static_bundle",
    "_campaign_page_option_allowed_for_linked_field",
]


def _build_common_builder_static_bundle(
    systems_service: Any,
    campaign_slug: str,
    *,
    campaign_page_records: list[Any] | None = None,
) -> dict[str, Any]:
    page_key = _builder_request_page_key(campaign_page_records)
    service_key = _builder_service_cache_identity(systems_service)
    revision_key = _builder_static_revision_key(systems_service, campaign_slug)

    def _build_bundle() -> dict[str, Any]:
        page_records = list(campaign_page_records or [])
        class_entries = _list_campaign_enabled_entries(systems_service, campaign_slug, "class")
        subclass_entries = _list_campaign_enabled_entries(systems_service, campaign_slug, "subclass")
        race_entries = _list_campaign_enabled_entries(systems_service, campaign_slug, "race")
        background_entries = _list_campaign_enabled_entries(systems_service, campaign_slug, "background")
        feat_entries = _list_campaign_enabled_entries(systems_service, campaign_slug, "feat")
        optionalfeature_entries = _list_campaign_enabled_entries(systems_service, campaign_slug, "optionalfeature")
        item_entries = _list_campaign_enabled_entries(systems_service, campaign_slug, "item")
        spell_entries = _list_campaign_enabled_entries(systems_service, campaign_slug, "spell")
        species_options = _build_mixed_character_options(
            race_entries,
            page_records,
            kind="species",
        )
        background_options = _build_mixed_character_options(
            background_entries,
            page_records,
            kind="background",
        )
        feat_options = _build_mixed_character_options(
            feat_entries,
            page_records,
            kind="feat",
        )
        return {
            "class_entries": class_entries,
            "supported_class_entries": [
                entry for entry in class_entries if _supports_native_class_entry(entry)
            ],
            "subclass_entries": subclass_entries,
            "species_options": species_options,
            "background_options": background_options,
            "feat_options": feat_options,
            "feat_catalog": _build_feat_catalog(feat_options),
            "optionalfeature_catalog": _build_entry_slug_catalog(optionalfeature_entries),
            "item_catalog": _attach_campaign_item_page_support(
                _build_item_catalog(item_entries),
                page_records,
            ),
            "spell_catalog": _build_spell_catalog(spell_entries),
            "campaign_feature_options": _build_campaign_page_choice_options(
                page_records,
                include_items=False,
            ),
            "campaign_item_options": _build_campaign_page_choice_options(
                page_records,
                include_items=True,
            ),
        }

    def _build_or_load_static_bundle() -> dict[str, Any]:
        if revision_key is None:
            return _build_bundle()
        return _builder_static_cache_get(
            (
                "builder-static-bundle",
                service_key,
                campaign_slug,
                revision_key,
                page_key,
            ),
            _build_bundle,
        )

    return dict(
        _builder_cache_get(
            ("builder-static-bundle", service_key, campaign_slug, revision_key, page_key),
            _build_or_load_static_bundle,
        )
    )


def _campaign_page_option_allowed_for_linked_field(
    record: Any,
    *,
    field_kind: str,
    campaign_option: dict[str, Any] | None = None,
) -> bool:
    required_section = LINKED_CAMPAIGN_PAGE_REQUIRED_SECTION_BY_FIELD_KIND.get(field_kind)
    if not required_section:
        return False
    page = getattr(record, "page", None)
    if page is None:
        return False
    if str(getattr(page, "section", "") or "").strip() != required_section:
        return False
    option = dict(campaign_option or {}) if isinstance(campaign_option, dict) else {}
    option_kind = str(option.get("kind") or "").strip().lower()
    if not option_kind:
        return True
    return option_kind in LINKED_CAMPAIGN_PAGE_ALLOWED_KINDS_BY_FIELD_KIND.get(field_kind, frozenset())


def _build_campaign_page_choice_options(
    campaign_page_records: list[Any],
    *,
    include_items: bool,
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    seen_page_refs: set[str] = set()
    field_kind = "campaign_page_item" if include_items else "campaign_page_feature"
    for record in list(campaign_page_records or []):
        page_ref = _extract_campaign_page_ref(record)
        page = getattr(record, "page", None)
        if not page_ref or page is None:
            continue
        section = str(getattr(page, "section", "") or "").strip()
        if section == CAMPAIGN_SESSIONS_SECTION:
            continue
        campaign_option = build_campaign_page_character_option(
            record,
            default_kind="item" if section == CAMPAIGN_ITEMS_SECTION else "feature",
        )
        if not _campaign_page_option_allowed_for_linked_field(
            record,
            field_kind=field_kind,
            campaign_option=campaign_option,
        ):
            continue
        if page_ref in seen_page_refs:
            continue
        seen_page_refs.add(page_ref)
        title = str(getattr(page, "title", "") or "").strip() or page_ref
        option_title = str((campaign_option or {}).get("display_name") or title).strip() or title
        subsection = str(getattr(page, "subsection", "") or "").strip()
        summary = str(getattr(page, "summary", "") or "").strip()
        label_parts = [option_title]
        if section:
            label_parts.append(f"{section} / {subsection}" if subsection else section)
        options.append(
            {
                "value": page_ref,
                "label": " | ".join(part for part in label_parts if part),
                "title": option_title,
                "summary": summary,
                "campaign_option": dict(campaign_option or {}),
            }
        )
    return options


def _build_campaign_feature_choice_fields(
    campaign_feature_options: list[dict[str, str]],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    if not campaign_feature_options:
        return []
    fields: list[dict[str, Any]] = []
    for index in range(1, CAMPAIGN_FEATURE_CHOICE_SLOTS + 1):
        field_name = f"campaign_feature_page_ref_{index}"
        fields.append(
            {
                "name": field_name,
                "label": f"Campaign Feature {index}",
                "help_text": "Optional. Link a published Mechanics feature or feat page into the character at creation time.",
                "options": [dict(option) for option in campaign_feature_options],
                "selected": str(values.get(field_name) or "").strip(),
                "group_key": field_name,
                "kind": "campaign_page_feature",
                "required": False,
            }
        )
    return fields


def _build_campaign_item_choice_fields(
    campaign_item_options: list[dict[str, str]],
    values: dict[str, str],
) -> list[dict[str, Any]]:
    if not campaign_item_options:
        return []
    fields: list[dict[str, Any]] = []
    for index in range(1, CAMPAIGN_ITEM_CHOICE_SLOTS + 1):
        field_name = f"campaign_item_page_ref_{index}"
        fields.append(
            {
                "name": field_name,
                "label": f"Campaign Item {index}",
                "help_text": "Optional. Add a published campaign wiki item page to the new character's starting inventory.",
                "options": [dict(option) for option in campaign_item_options],
                "selected": str(values.get(field_name) or "").strip(),
                "group_key": field_name,
                "kind": "campaign_page_item",
                "required": False,
            }
        )
    return fields
