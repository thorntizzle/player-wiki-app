"""Keep page-choice display rows out of legacy name-based mechanics.

This classifier only *removes* heuristic authority. Committed publication
separately proves the complete row against the current page option before it
can become a Character definition. It never grants mechanics to a raw claim.
"""
from __future__ import annotations

from typing import Any
from flask import has_app_context


def _page_ref(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("page_ref") or value.get("slug") or value.get("page_slug")
    if not isinstance(value, str):
        return ""
    return value.strip().replace("\\", "/").strip("/").removesuffix(".md").casefold()


def is_page_choice_shape(feature: Any) -> bool:
    if not isinstance(feature, dict):
        return False
    category = str(feature.get("category") or feature.get("kind") or "").strip()
    subject = {"species_trait": "species", "background_feature": "background"}.get(category)
    page_ref = _page_ref(feature.get("page_ref"))
    if subject is None or not page_ref:
        return False
    if feature.get("systems_ref"):
        return False
    option = feature.get("campaign_option")
    if option and (not isinstance(option, dict) or option.get("kind") != subject or
                   _page_ref(option.get("page_ref")) != page_ref):
        return False
    return True


def blocks_page_companion_heuristics(feature: Any) -> bool:
    if not is_page_choice_shape(feature):
        return False
    # Closed-mode import and legacy character interpretation remains intact.
    if not has_app_context():
        return False
    from .committed_publication import active
    return active()
