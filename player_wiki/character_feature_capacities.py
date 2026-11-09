"""Nonpersistent capacities and historical roles; no count/reset grants or mutation."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import re

from .systems_feature_capacities import ARTIFICER, INFUSE, TINKERING, SPECS, current_capacity
from .systems_feature_values import source_digest


def _tracker_identity(value):
    return value.strip() if isinstance(value, str) else ""


def historical_counter_candidates(definition):
    """Structural candidates only; this supplies no present qualification.

    Receiving callers use authenticated generations and a sealed source recipe.
    Ordinary issuance must additionally qualify the complete current source.
    """
    payload = definition.to_dict() if hasattr(definition, "to_dict") else definition
    if type(payload) is not dict or payload.get("system") != "DND-5E":
        return {}
    features = [row for row in payload.get("features") or [] if type(row) is dict]
    templates = [row for row in payload.get("resource_templates") or [] if type(row) is dict]
    classes = [row for row in (payload.get("profile") or {}).get("classes") or [] if type(row) is dict]
    result = {}
    for feature in features:
        ref = feature.get("systems_ref")
        key = ref.get("entry_key") if type(ref) is dict else None
        if (type(key) is not str or key not in SPECS or feature.get("page_ref")
                or ref.get("entry_type") != "classfeature" or ref.get("source_id") != "TCE"
                or type(ref.get("slug")) is not str or not ref["slug"]):
            continue
        identity, tracker = feature.get("id"), feature.get("tracker_ref")
        if (type(identity) is not str or not identity or type(tracker) is not str
                or re.fullmatch(r"[a-z0-9_-]{1,120}", tracker) is None
                or sum(row.get("id") == identity for row in features) != 1
                or identity != identity.strip()
                or sum(_tracker_identity(row.get("tracker_ref")) == tracker for row in features) != 1):
            continue
        owners = [row for row in classes if type(row.get("systems_ref")) is dict
                  and row["systems_ref"].get("entry_key") == ARTIFICER and not row.get("page_ref")
                  and row["systems_ref"].get("entry_type") == "class"
                  and row["systems_ref"].get("source_id") == "TCE"
                  and type(row["systems_ref"].get("slug")) is str and row["systems_ref"]["slug"]
                  and type(row.get("row_id")) is str and row["row_id"]
                  and sum(other.get("row_id") == row["row_id"] for other in classes) == 1
                  and feature.get("class_row_id") in (None, "", row["row_id"])
                  and type(row.get("level")) is int and SPECS[key]["level"] <= row["level"] <= 20]
        matching = [row for row in templates if _tracker_identity(row.get("id")) == tracker]
        if (len(owners) != 1 or len(matching) != 1
                or matching[0].get("id") != tracker
                or matching[0].get("class_row_id") not in (None, "", owners[0]["row_id"])
                or any(matching[0].get(name) != value for name, value in (
                    ("reset_on", "other"), ("reset_to", "unchanged"), ("rest_behavior", "manual_only")))):
            continue
        if sum(type(row.get("systems_ref")) is dict and row["systems_ref"].get("entry_key") == key
               and row.get("class_row_id") in (None, "", owners[0]["row_id"]) for row in features) != 1:
            continue
        result[tracker] = {"feature": feature, "class": owners[0], "template": matching[0]}
    return result


def prepare_historical_counter_inputs(definition, state, authority, service):
    """Qualify source roles and bind actual observations, never their use counts."""
    from .character_feature_values import _exact_entry
    from .systems_feature_capacities import declaration
    candidates = historical_counter_candidates(definition)
    caps = presentations(definition, state, authority, service)
    records = []
    if authority is None:
        return records
    for identity in authority.active_item_ids:
        # This is an independent current consumer of a reset pool. Inspect only
        # its admitted target identity, never treat effect grants as metadata.
        bonuses = authority.approved_payload("item", identity).get("resource_template_bonuses", [])
        if any(type(row) is dict and _tracker_identity(row.get("id") or row.get("tracker_id")) in candidates
               for row in bonuses):
            return []
    for tracker, frame in sorted(candidates.items()):
        feature, owner = frame["feature"], frame["class"]
        capacity = caps.get(feature["id"], {})
        observed = [row for row in state.get("resources") or []
                    if type(row) is dict and _tracker_identity(row.get("id")) == tracker]
        if (not capacity.get("available") or not capacity.get("capacity_only")
                or capacity.get("class_row_id") != owner["row_id"] or len(observed) != 1
                or observed[0].get("id") != tracker):
            return []  # A partial role set cannot weaken another unknown input.
        entry = _exact_entry(service, definition.campaign_slug, feature["systems_ref"])
        if entry is None:
            return []
        template_digest = source_digest(frame["template"])
        records.append({"schema_version": 1, "target_id": "resource:" + tracker,
            "feature_id": feature["id"], "class_row_id": owner["row_id"],
            "class_ref": deepcopy(owner["systems_ref"]),
            "prior_template_digest": template_digest, "published_template_digest": template_digest,
            "prior_state_row_digest": source_digest(observed[0]),
            "source_basis_digest": capacity["source_basis_digest"],
            "source_recipe": {"schema_version": 1, "registration": "artificer_simultaneous_capacity@1",
                "source_ref": {name: getattr(entry, name) for name in (
                    "library_slug", "entry_key", "entry_type", "source_id", "slug", "title")},
                "publication_digest": source_digest({"metadata": entry.metadata, "body": entry.body}),
                "owner_rules": declaration(entry.entry_key)}})
    return records


def verify_historical_counter_inputs(prior, candidate, records, *, state=None):
    """Receive non-entitling role descriptors from sealed native proof8 only.

    No current source lookup, numeric maximum or saved usage is inferred here.
    Actual issuer/publisher checks additionally provide their exact prior state.
    """
    from .systems_feature_capacities import declaration
    before, after = historical_counter_candidates(prior), historical_counter_candidates(candidate)
    if (type(records) is not list or not 1 <= len(records) <= 16
            or set(before) != set(after) or len(records) != len(before)):
        raise ValueError("Historical capacity roles are incomplete or ambiguous.")
    fields = {"schema_version", "target_id", "feature_id", "class_row_id", "class_ref",
              "prior_template_digest", "published_template_digest", "prior_state_row_digest",
              "source_basis_digest", "source_recipe"}
    targets = []
    for row in records:
        if (type(row) is not dict or set(row) != fields or type(row["schema_version"]) is not int
                or row["schema_version"] != 1 or type(row["target_id"]) is not str
                or not row["target_id"].startswith("resource:")):
            raise ValueError("Historical capacity descriptor is malformed.")
        tracker = row["target_id"].removeprefix("resource:")
        if tracker not in before:
            raise ValueError("Historical capacity descriptor has no exact owner.")
        old, new = before[tracker], after[tracker]
        feature, owner = old["feature"], old["class"]
        recipe = row["source_recipe"]
        ref = recipe.get("source_ref") if type(recipe) is dict else None
        if (source_digest(old) != source_digest(new)
                or row["feature_id"] != feature["id"] or row["class_row_id"] != owner["row_id"]
                or row["class_ref"] != owner["systems_ref"]
                or any(re.fullmatch(r"[0-9a-f]{64}", row[name]) is None if type(row[name]) is str else True
                       for name in ("prior_template_digest", "published_template_digest", "prior_state_row_digest", "source_basis_digest"))
                or row["prior_template_digest"] != source_digest(old["template"])
                or row["published_template_digest"] != row["prior_template_digest"]
                or type(recipe) is not dict or set(recipe) != {
                    "schema_version", "registration", "source_ref", "publication_digest", "owner_rules"}
                or type(recipe["schema_version"]) is not int or recipe["schema_version"] != 1
                or recipe["registration"] != "artificer_simultaneous_capacity@1"
                or source_digest(recipe["owner_rules"]) != source_digest(declaration(feature["systems_ref"]["entry_key"]))
                or type(recipe["publication_digest"]) is not str
                or re.fullmatch(r"[0-9a-f]{64}", recipe["publication_digest"]) is None
                or type(ref) is not dict or set(ref) != {"library_slug", "entry_key", "entry_type", "source_id", "slug", "title"}
                or any(type(value) is not str or not value for value in ref.values())
                or any(feature["systems_ref"].get(name) != ref[name] for name in (
                    "entry_key", "entry_type", "source_id", "slug"))
                or any(name in feature["systems_ref"] and feature["systems_ref"][name] != ref[name]
                       for name in ("title", "library_slug"))):
            raise ValueError("Historical capacity source or preserved frame changed.")
        if state is not None:
            observed = [item for item in state.get("resources") or []
                        if type(item) is dict and _tracker_identity(item.get("id")) == tracker]
            if (len(observed) != 1 or observed[0].get("id") != tracker
                    or source_digest(observed[0]) != row["prior_state_row_digest"]):
                raise ValueError("Historical capacity observation changed.")
        targets.append(row["target_id"])
    if targets != sorted(set(targets)) or set(targets) != {"resource:" + tracker for tracker in before}:
        raise ValueError("Historical capacity target set is incomplete.")
    return {("resource", target, "owner_reset") for target in targets}


def assignment_kind(feature):
    ref = feature.get("systems_ref")
    return ({TINKERING: "tinkering", INFUSE: "infusions"}.get(ref.get("entry_key"))
            if type(ref) is dict else None)


def resource_roles(definition, state, capacities):
    """Retire only an unambiguous, qualified capacity feature's counter role.

    This is presentation data, never a filtered state or numeric authority. A
    shared tracker stays visible when another feature may still consume it.
    """
    claims = {}
    for feature in definition.features or []:
        if type(feature) is dict and isinstance(feature.get("tracker_ref"), str):
            tracker = feature["tracker_ref"].strip()
            if tracker:
                claims.setdefault(tracker, []).append(feature.get("id"))
    rows = Counter(row.get("id") for row in state.get("resources") or []
                   if type(row) is dict and isinstance(row.get("id"), str))
    retired, warnings = set(), {}
    for feature in definition.features or []:
        if type(feature) is not dict:
            continue
        identity = feature.get("id")
        if not isinstance(identity, str):
            continue
        capacity = capacities.get(identity, {})
        if not (capacity.get("capacity_only") and capacity.get("available")
                and assignment_kind(feature)):
            continue
        tracker = str(feature.get("tracker_ref") or "").strip()
        if not tracker:
            continue
        if claims.get(tracker) == [identity] and rows[tracker] == 1:
            retired.add(tracker)
        elif claims.get(tracker) != [identity] or rows[tracker] > 1:
            warnings[identity] = "Historical tracker ownership is ambiguous; its observations are preserved."
    return {"retired_tracker_ids": sorted(retired), "warnings": warnings}


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
