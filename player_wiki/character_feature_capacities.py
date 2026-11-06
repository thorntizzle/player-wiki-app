"""Read-only feature capacities. No counter qualification, defaults or mutation."""
from __future__ import annotations

from collections import Counter

from .systems_feature_capacities import ARTIFICER, SPECS, current_capacity
from .systems_feature_values import source_digest


def presentations(definition, state, authority, service):
    from .character_feature_values import _exact_entry
    from .character_source_authority import numeric_value_digest
    if definition.system != "DND-5E" or authority is None or service is None:
        return {}
    if ((authority.original_definition_digest or authority.definition_digest) != numeric_value_digest(definition.to_dict())
            or authority.state_digest != numeric_value_digest(state)):
        return {}
    rows = list(definition.profile.get("classes") or [])
    counts = Counter(row.get("row_id") for row in rows if type(row) is dict and type(row.get("row_id")) is str)
    classes = {row["row_id"]: row for row in rows if type(row) is dict and type(row.get("row_id")) is str
               and counts[row["row_id"]] == 1}
    features = [row for row in definition.features if type(row) is dict]
    ids = Counter(row.get("id") for row in features if type(row.get("id")) is str)
    result, attained = {}, {}
    for feature in features:
        ref = feature.get("systems_ref")
        key = ref.get("entry_key") if type(ref) is dict else None
        spec = SPECS.get(key) if type(key) is str else None
        identity, owner_id = feature.get("id"), feature.get("class_row_id")
        if spec is None or type(identity) is not str or ids[identity] != 1:
            continue
        view = {"label": spec["label"], "available": False, "display": "Unavailable",
                "reason": "Capacity ownership is not qualified.", "representative_id": identity,
                "capacity_only": True}
        try:
            owner = classes.get(owner_id) if type(owner_id) is str else None
            if owner_id in (None, ""):
                # This proves a current deterministic association, without
                # inventing an acquisition date or rewriting the retained row.
                possible = [row for row in classes.values() if type(row.get("systems_ref")) is dict
                            and row["systems_ref"].get("entry_key") == ARTIFICER
                            and row["row_id"] in authority.verified_class_rows]
                if len(possible) == 1:
                    owner = possible[0]
                    owner_id = owner["row_id"]
            matches = [row for row in features if type(row.get("systems_ref")) is dict
                       and row["systems_ref"].get("entry_key") == key
                       and row.get("class_row_id") in (None, "", owner_id)]
            if (feature.get("page_ref") or owner is None or owner.get("page_ref")
                    or owner_id not in authority.verified_class_rows
                    or len(matches) != 1 or authority.status_for("feature", identity) != "VERIFIED"):
                raise ValueError("Capacity needs one qualified feature and its exact class owner.")
            entry = _exact_entry(service, definition.campaign_slug, ref)
            cls = _exact_entry(service, definition.campaign_slug, owner.get("systems_ref"))
            enabled = getattr(service, "is_entry_enabled_for_campaign", None)
            if (entry is None or cls is None or not callable(enabled)
                    or not enabled(definition.campaign_slug, entry) or not enabled(definition.campaign_slug, cls)):
                raise ValueError("Current capacity source or owner is unavailable.")
            scores = {}
            ability = spec["formula"].get("ability")
            if ability:
                status = authority.field_status(f"stats.ability_scores.{ability}.score")
                if not status.is_effective or type(status.effective) is not int:
                    raise ValueError("Capacity needs a qualified current ability score.")
                scores[ability] = status.effective
            maximum = current_capacity(entry, cls, owner.get("level"), ability_scores=scores)
            if owner_id not in attained:
                loader = getattr(service, "collect_attained_deterministic_feature_entries", None)
                if not callable(loader):
                    raise ValueError("Current class feature progression is unavailable.")
                attained[owner_id] = {e.entry_key for e in loader(definition.campaign_slug, cls,
                                                                 attained_level=owner["level"])}
            if key not in attained[owner_id]:
                raise ValueError("This feature is not a current attained grant of its owning class.")
            view.update(available=True, display=str(maximum), maximum=maximum, reason="",
                        class_row_id=owner_id, class_level=owner["level"],
                        source_basis_digest=source_digest({"class": {"metadata": cls.metadata, "body": cls.body},
                            "feature": {"metadata": entry.metadata, "body": entry.body}, "abilities": scores}))
        except (ValueError, TypeError, KeyError) as error:
            view["reason"] = str(error)
        result[identity] = view
    return result
