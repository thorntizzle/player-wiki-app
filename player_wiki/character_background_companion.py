"""Exact, inert projections of a selected Systems background's feature text."""
from __future__ import annotations

from typing import Any


def is_systems_background_companion(feature: Any, profile: Any) -> bool:
    if not isinstance(feature, dict) or not isinstance(profile, dict):
        return False
    ref = feature.get("systems_ref")
    allowed = {"id", "name", "category", "source", "description_markdown",
               "activation_type", "tracker_ref", "systems_ref"}
    return (
        feature.get("category") == "background_feature"
        and all(isinstance(feature.get(key), str) and bool(feature[key].strip())
                for key in ("name", "description_markdown", "source"))
        and isinstance(ref, dict) and bool(ref)
        and ref == profile.get("background_ref")
        and not profile.get("background_page_ref")
        and feature.get("activation_type") == "passive"
        and not feature.get("tracker_ref")
        and all(value in (None, "", [], {}) for key, value in feature.items()
                if key not in allowed)
    )


def systems_background_companion_matches(feature: Any, profile: Any, entry: Any) -> bool:
    """Identify an inert current facet; saved prose is historical, not authority."""
    if not is_systems_background_companion(feature, profile):
        return False
    if getattr(entry, "entry_type", None) != "background":
        return False
    ref = feature["systems_ref"]
    if any(ref.get(key) and ref[key] != getattr(entry, key, None)
           for key in ("entry_key", "slug", "source_id", "entry_type", "title", "library_slug")):
        return False
    if feature.get("source") != getattr(entry, "source_id", None):
        return False
    from .character_parent_facets import linked_companion_facet
    return linked_companion_facet(feature, profile, entry) is not None
