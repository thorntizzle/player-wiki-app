"""Nonpersistent values for already-qualified, source-owned features.

This view acquires nothing, changes no resource, and never enters a save payload.
Raw acquisition rows remain intact; only explicitly registered improvements of
the same facet and owning class share a current presentation.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy

from .systems_feature_values import (
    current_contract, family_spec, source_digest, value_for_level, value_label,
)


_IDENTITY_FIELDS = frozenset({"library_slug", "source_id", "entry_key", "entry_type", "slug", "title"})


def is_current_family_member(feature_id, presentation):
    """Use the same representative decision for details and section counts."""
    return not (presentation.get("available") is True
                and presentation.get("representative_id") != feature_id)


def _exact_entry(service, campaign_slug, ref):
    if (type(ref) is not dict or not {"entry_key", "entry_type", "source_id", "slug"} <= set(ref)
            or not set(ref) <= _IDENTITY_FIELDS or any(not isinstance(v, str) or not v for v in ref.values())):
        return None
    entry = service.get_entry_for_campaign(campaign_slug, ref["entry_key"])
    if entry is None or any(getattr(entry, k, None) != v for k, v in ref.items()):
        return None
    return entry


def evaluate_family(members, owner_entry, class_level):
    """Evaluate genuine normalized publications, independent of HTML/state.

    Caller must first prove each acquisition and its exact current owner. This
    function does not resolve siblings from a library or create an entitlement.
    """
    if not members:
        raise ValueError("No acquired feature member is available.")
    entries = [m["entry"] for m in members]
    if len({e.entry_key for e in entries}) != len(entries):
        raise ValueError("Duplicate feature acquisitions need owner review.")
    contracts = [current_contract(e) for e in entries]
    if any(c is None for c in contracts):
        raise ValueError("Feature family is unsupported.")
    frame = lambda c: tuple(c[k] for k in ("family", "owner", "facet", "evolution", "scope"))
    if len({frame(c) for c in contracts}) != 1:
        raise ValueError("Feature family ownership or evolution conflicts.")
    if type(class_level) is not int or not 1 <= class_level <= 20 or any(c["level"] > class_level for c in contracts):
        raise ValueError("Feature member is not attained by its owning class.")
    index = max(range(len(contracts)), key=lambda i: contracts[i]["level"])
    selected = contracts[index]
    value = value_for_level(selected, owner_entry, class_level)
    spec = family_spec(entries[index].entry_key)
    return {"available": True, "reason": "", "family": selected["family"], "facet": selected["facet"],
            "class_level": class_level, "label": spec["label"], "value": value, "display": value_label(value),
            "representative_id": members[index]["id"], "member_ids": [m["id"] for m in members],
            "source_entry_keys": [e.entry_key for e in entries], "owner_entry_key": owner_entry.entry_key}


def build_feature_value_presentations(definition, state, authority, systems_service):
    if authority is None or systems_service is None or definition.system != "DND-5E":
        return {}
    # Do not reuse a status list belonging to a different definition or state.
    from .character_source_authority import numeric_value_digest
    original = authority.original_definition_digest or authority.definition_digest
    if original != numeric_value_digest(definition.to_dict()) or authority.state_digest != numeric_value_digest(state):
        return {}
    rows = list(definition.profile.get("classes") or [])
    row_counts = Counter(r.get("row_id") for r in rows if type(r) is dict and isinstance(r.get("row_id"), str))
    by_row = {r["row_id"]: r for r in rows if type(r) is dict and isinstance(r.get("row_id"), str) and row_counts[r["row_id"]] == 1}
    feature_counts = Counter(f.get("id") for f in definition.features if type(f) is dict and isinstance(f.get("id"), str))
    groups, result = {}, {}
    for feature in definition.features:
        if type(feature) is not dict:
            continue
        identity = feature.get("id")
        ref = feature.get("systems_ref")
        spec = family_spec(ref.get("entry_key")) if type(ref) is dict else None
        if (not spec or not isinstance(identity, str) or not identity or feature_counts[identity] != 1
                or feature.get("page_ref") or authority.status_for("feature", identity) != "VERIFIED"):
            continue
        row_id = feature.get("class_row_id")
        row_id = row_id if isinstance(row_id, str) else None
        key = (spec["family"], spec["facet"], row_id)
        groups.setdefault(key, []).append((feature, spec))
    for (_, _, row_id), acquired in groups.items():
        try:
            if not isinstance(row_id, str) or not row_id or row_id not in authority.verified_class_rows:
                raise ValueError("Scaling needs an explicit verified owning class row.")
            row = by_row.get(row_id)
            if row is None or row.get("page_ref"):
                raise ValueError("The owning class is ambiguous or unavailable.")
            owner = _exact_entry(systems_service, definition.campaign_slug, row.get("systems_ref"))
            if owner is None or any(owner.entry_key != spec["owner"] for _, spec in acquired):
                raise ValueError("The current owning class publication does not match.")
            members = []
            for feature, _ in acquired:
                entry = _exact_entry(systems_service, definition.campaign_slug, feature["systems_ref"])
                if entry is None:
                    raise ValueError("The current feature publication is unavailable.")
                members.append({"id": feature["id"], "entry": entry})
            view = evaluate_family(members, owner, row.get("level"))
            view["class_row_id"] = row_id
            # The frame is diagnostic source identity, never a numeric witness.
            view["source_basis_digest"] = source_digest({
                "class_row": row, "class": {"key": owner.entry_key, "metadata": owner.metadata, "body": owner.body},
                "members": [{"key": m["entry"].entry_key, "metadata": m["entry"].metadata,
                             "body": m["entry"].body} for m in members]})
        except (ValueError, TypeError) as error:
            view = {"available": False, "reason": str(error), "family": acquired[0][1]["family"],
                    "facet": acquired[0][1]["facet"], "label": acquired[0][1]["label"], "display": "Unavailable"}
        for feature, _ in acquired:
            result[feature["id"]] = deepcopy(view)
    from .character_feature_capacities import presentations as capacity_presentations
    result.update(capacity_presentations(definition, state, authority, systems_service))
    return result
