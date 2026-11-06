"""Authenticate inert retained projections of the selected subclass container."""
from __future__ import annotations


def selected_subclass_companion_matches(feature, profile, entry, service, campaign):
    from .character_profile import profile_class_rows

    if not isinstance(feature, dict) or not isinstance(profile, dict):
        return False
    allowed = {"id", "name", "category", "source", "description_markdown",
               "activation_type", "tracker_ref", "systems_ref"}
    if (getattr(entry, "entry_type", None) != "subclass"
            or feature.get("category") != "class_feature"
            or feature.get("name") != entry.title
            or feature.get("activation_type") != "passive"
            or feature.get("description_markdown") not in (None, "")
            or feature.get("tracker_ref")
            or feature.get("source") not in (None, "", entry.source_id)
            or any(value not in (None, "", [], {}) for key, value in feature.items() if key not in allowed)):
        return False
    ref = feature.get("systems_ref")
    if not isinstance(ref, dict) or ref.get("entry_key") != entry.entry_key:
        return False
    if any(ref.get(key) and ref[key] != getattr(entry, key, None)
           for key in ("entry_key", "slug", "source_id", "entry_type", "title", "library_slug")):
        return False
    matches = []
    for row in profile_class_rows(profile):
        selected = row.get("subclass_ref")
        parent = row.get("systems_ref")
        if not isinstance(selected, dict) or selected.get("entry_key") != entry.entry_key or not isinstance(parent, dict):
            continue
        if any(selected.get(key) and selected[key] != getattr(entry, key, None)
               for key in ("entry_key", "slug", "source_id", "entry_type", "title", "library_slug")):
            return False
        cls = service.get_entry_for_campaign(campaign, parent.get("entry_key", ""))
        if (cls is None or cls.entry_type != "class"
                or any(parent.get(key) and parent[key] != getattr(cls, key, None)
                       for key in ("entry_key", "slug", "source_id", "entry_type"))
                or entry.metadata.get("class_name") != cls.title
                or entry.metadata.get("class_source") != cls.source_id):
            return False
        matches.append(row)
    return len(matches) == 1
