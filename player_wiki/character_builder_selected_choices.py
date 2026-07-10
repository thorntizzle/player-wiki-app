from __future__ import annotations

from typing import Any

from .character_builder_constants import LINKED_CAMPAIGN_PAGE_ALLOWED_KINDS_BY_FIELD_KIND

__all__ = [
    "_build_selected_campaign_item_specs",
    "_collect_selected_campaign_feature_entries",
    "_resolve_choice_label",
    "_resolve_choice_option",
    "_selected_campaign_choice_options",
    "_selected_campaign_option_payloads",
]


def _selected_campaign_choice_options(
    *,
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for section in choice_sections:
        for field in list(section.get("fields") or []):
            kind = str(field.get("kind") or "").strip()
            if kind not in {"campaign_page_feature", "campaign_page_item"}:
                continue
            group_key = str(field.get("group_key") or field.get("name") or "").strip()
            for selected_value in list(selected_choices.get(group_key) or []):
                option = _resolve_choice_option(choice_sections, group_key, selected_value)
                if option:
                    option["field_kind"] = kind
                    options.append(option)
    return options


def _selected_campaign_option_payloads(
    *,
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
    extra_option_payloads: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    payloads = [
        dict(option.get("campaign_option") or {})
        for option in _selected_campaign_choice_options(
            choice_sections=choice_sections,
            selected_choices=selected_choices,
        )
        if isinstance(option.get("campaign_option"), dict)
    ]
    payloads.extend(
        dict(payload)
        for payload in list(extra_option_payloads or [])
        if isinstance(payload, dict) and dict(payload)
    )
    return payloads


def _build_selected_campaign_item_specs(
    *,
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for option in _selected_campaign_choice_options(
        choice_sections=choice_sections,
        selected_choices=selected_choices,
    ):
        page_ref = str(option.get("value") or "").strip()
        campaign_option = dict(option.get("campaign_option") or {})
        kind = str(campaign_option.get("kind") or "").strip()
        field_kind = str(option.get("field_kind") or "").strip()
        if kind and kind != "item":
            continue
        if not kind and field_kind != "campaign_page_item":
            continue
        title = str(
            campaign_option.get("item_name")
            or option.get("title")
            or option.get("label")
            or page_ref
        ).strip()
        if not page_ref or not title:
            continue
        specs.append(
            {
                "name": title,
                "quantity": int(campaign_option.get("quantity") or 1),
                "weight": str(campaign_option.get("weight") or "").strip(),
                "notes": str(campaign_option.get("notes") or option.get("summary") or "").strip(),
                "page_ref": page_ref,
                "source_kind": "builder_campaign_page",
                "campaign_option": campaign_option or None,
            }
        )
    return specs


def _collect_selected_campaign_feature_entries(
    *,
    choice_sections: list[dict[str, Any]],
    selected_choices: dict[str, list[str]],
) -> list[dict[str, Any]]:
    feature_entries: list[dict[str, Any]] = []
    for option in _selected_campaign_choice_options(
        choice_sections=choice_sections,
        selected_choices=selected_choices,
    ):
        page_ref = str(option.get("value") or "").strip()
        campaign_option = dict(option.get("campaign_option") or {})
        kind = str(campaign_option.get("kind") or "").strip()
        field_kind = str(option.get("field_kind") or "").strip()
        if kind and kind not in LINKED_CAMPAIGN_PAGE_ALLOWED_KINDS_BY_FIELD_KIND["campaign_page_feature"]:
            continue
        if not kind and field_kind != "campaign_page_feature":
            continue
        title = str(
            campaign_option.get("feat_name")
            or campaign_option.get("feature_name")
            or option.get("title")
            or option.get("label")
            or page_ref
        ).strip()
        if not page_ref or not title:
            continue
        feature_entries.append(
            {
                "kind": "feat" if kind == "feat" else "campaign_page_feature",
                "entry": None,
                "name": title,
                "label": title,
                "title": title,
                "page_ref": page_ref,
                "description_markdown": str(
                    campaign_option.get("description_markdown")
                    or option.get("summary")
                    or ""
                ).strip(),
                "activation_type": str(campaign_option.get("activation_type") or "passive").strip(),
                "campaign_option": campaign_option or None,
            }
        )
    return feature_entries


def _resolve_choice_label(
    choice_sections: list[dict[str, Any]],
    group_key: str,
    selected_value: str,
) -> str:
    option = _resolve_choice_option(choice_sections, group_key, selected_value)
    return str(option.get("label") or "").strip()


def _resolve_choice_option(
    choice_sections: list[dict[str, Any]],
    group_key: str,
    selected_value: str,
) -> dict[str, Any]:
    normalized_value = str(selected_value or "").strip()
    if not normalized_value:
        return {}
    for section in choice_sections:
        for field in list(section.get("fields") or []):
            if str(field.get("group_key") or "") != group_key:
                continue
            for option in list(field.get("options") or []):
                if str(option.get("value") or "").strip() == normalized_value:
                    return dict(option)
    return {}
