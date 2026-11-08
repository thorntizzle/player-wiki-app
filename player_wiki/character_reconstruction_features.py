"""Explicit source adoption for retained reference-only registered features.

Selection never publishes a page or supplies a grant. Normal current source
authority must independently qualify the prospective catalog association.
"""
from copy import deepcopy
import hashlib
import json

from .character_source_repair import SourceRepairError

FRAME = "feature_source_mappings"
ORIGIN = "feature_source_mapping_digest"


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _rows(definition):
    rows = definition.features
    if type(rows) is not list:
        raise SourceRepairError("Feature source adoption needs retained owners.")
    result = {}
    for row in rows:
        if type(row) is not dict or type(row.get("id")) is not str or not row["id"] or row["id"] in result:
            raise SourceRepairError("Feature source adoption needs unique retained identities.")
        result[row["id"]] = row
    return result


def _legacy_reference(row):
    from .divine_avatar_forms import (
        _closed_divine_avatar_selection, _avatar_feature_source,
        DIVINE_AVATAR_FORMS_LEGACY_PAGE_REF,
    )
    return (_closed_divine_avatar_selection(row, allow_reference=True)
            and _avatar_feature_source(row) == ("page", DIVINE_AVATAR_FORMS_LEGACY_PAGE_REF)
            and not row.get("mechanic_effects")
            and not (row.get("campaign_option") or {}).get("mechanic_effects"))


def _candidates(definition, row, service):
    from .character_source_authority import _FEATURE_EFFECT_FIELDS, _current_systems_entry
    from .character_builder_equipment import _systems_ref_from_entry
    from .divine_avatar_forms import registered_divine_avatar_feature
    from .character_reconstruction_authority import digest
    loader = getattr(service, "list_enabled_entries_for_campaign", None)
    if not _legacy_reference(row) or not callable(loader):
        return []
    result = {}
    for observed in loader(definition.campaign_slug, entry_type="feature"):
        current = _current_systems_entry(definition.campaign_slug, "systems", observed.entry_key, service)
        if current is None or current.entry_type != "feature":
            continue
        ref = _systems_ref_from_entry(current)
        effects = {key: deepcopy(current.metadata[key]) for key in _FEATURE_EFFECT_FIELDS if key in current.metadata}
        if not registered_divine_avatar_feature({"id": row["id"], "systems_ref": ref, **effects}):
            continue
        result[current.entry_key] = {"systems_ref": ref,
            "review_source_digest": digest({"metadata": current.metadata, "body": current.body})}
        if len(result) > 32:
            raise SourceRepairError("Feature source choices exceed the bounded registered family.")
    return list(result.values())


def choice_fields(definition, service, values):
    result = []
    for identity, row in _rows(definition).items():
        if not _legacy_reference(row):
            continue
        name = "feature_source_link_" + hashlib.sha256(identity.encode()).hexdigest()
        options = [{"value": "retain_unqualified", "label": "Retain historical reference without a current grant"}]
        options += [{"value": item["systems_ref"]["entry_key"],
                     "label": item["systems_ref"]["title"] + " (" + item["systems_ref"]["source_id"] + ")"}
                    for item in _candidates(definition, row, service)]
        result.append({"name": name, "feature_id": identity, "label": row.get("name") or identity,
                       "options": options, "value": values.get(name, "retain_unqualified")})
    return result


def mapped_feature(mapping):
    row = json.loads(mapping["prior_feature_json"])
    row.pop("page_ref", None)
    if row.get("campaign_option"):
        row["campaign_option"].pop("page_ref", None)
    row["systems_ref"] = deepcopy(mapping["systems_ref"])
    return row


def stored(definition):
    frame = definition.source.get("native_reconstruction_choices") or {}
    if type(frame) is not dict:
        raise SourceRepairError("Retained feature source history needs a reconstruction frame.")
    values = frame.get(FRAME, [])
    if type(values) is not list or len(values) > 32:
        raise SourceRepairError("Retained feature source mappings are malformed.")
    seen = set()
    for row in values:
        if (type(row) is not dict or set(row) != {"schema_version", "feature_id", "prior_feature_json", "systems_ref", "review_source_digest"}
                or type(row["schema_version"]) is not int or row["schema_version"] != 1
                or type(row["feature_id"]) is not str or not row["feature_id"] or row["feature_id"] in seen
                or type(row["prior_feature_json"]) is not str or len(row["prior_feature_json"]) > 65536
                or type(row["systems_ref"]) is not dict or row["systems_ref"].get("entry_type") != "feature"
                or type(row["review_source_digest"]) is not str or len(row["review_source_digest"]) != 64
                or any(char not in "0123456789abcdef" for char in row["review_source_digest"])):
            raise SourceRepairError("Retained feature source evidence has an invalid shape.")
        prior = json.loads(row["prior_feature_json"])
        if (not _legacy_reference(prior) or prior["id"] != row["feature_id"]
                or _json(prior) != row["prior_feature_json"]):
            raise SourceRepairError("Retained feature source evidence changed its original reference.")
        seen.add(row["feature_id"])
    return values


def compose(prior, payload, service, values):
    mappings = deepcopy(stored(prior))
    rows = {row["id"]: row for row in payload["features"]}
    for field in choice_fields(prior, service, values):
        selected = values.get(field["name"], "retain_unqualified")
        if selected not in {item["value"] for item in field["options"]}:
            raise SourceRepairError("Select one current feature source or retain its historical reference.")
        if selected == "retain_unqualified":
            continue
        old = _rows(prior)[field["feature_id"]]
        matches = [item for item in _candidates(prior, old, service) if item["systems_ref"]["entry_key"] == selected]
        if len(matches) != 1:
            raise SourceRepairError("The selected current feature source is unavailable or ambiguous.")
        mapping = {"schema_version": 1, "feature_id": field["feature_id"],
                   "prior_feature_json": _json(old), **deepcopy(matches[0])}
        rows[field["feature_id"]].clear()
        rows[field["feature_id"]].update(mapped_feature(mapping))
        mappings.append(mapping)
    payload["source"]["native_reconstruction_choices"][FRAME] = mappings


def reference_owner_ids(definition):
    """Historical family evidence can fence missing effects, never grant them."""
    try:
        mappings = stored(definition)
        if not mappings:
            return frozenset()
        owners = _rows(definition)
        for mapping in mappings:
            row = owners.get(mapping["feature_id"])
            if row is not None and row.get("systems_ref") != mapping["systems_ref"]:
                return None  # An unexplained replacement cannot hide its family.
        return frozenset(row["feature_id"] for row in mappings if row["feature_id"] in owners)
    except (ValueError, TypeError, KeyError):
        return None


def validate(prior, candidate, service=None):
    old, new = _rows(prior), _rows(candidate)
    before, after = stored(prior), stored(candidate)
    if after[:len(before)] != before:
        raise SourceRepairError("Existing feature source history cannot be rewritten or removed.")
    for mapping in after:
        identity = mapping["feature_id"]
        if identity not in old or identity not in new:
            raise SourceRepairError("Feature source adoption changed its retained owner or content.")
        if mapping not in before:
            if new[identity] != mapped_feature(mapping):
                raise SourceRepairError("Feature source adoption changed more than its source link.")
            if _json(old[identity]) != mapping["prior_feature_json"]:
                raise SourceRepairError("Feature source adoption no longer matches its exact prior row.")
            if service is not None and mapping["systems_ref"] not in [item["systems_ref"] for item in _candidates(prior, old[identity], service)
                    if item["review_source_digest"] == mapping["review_source_digest"]]:
                raise SourceRepairError("The reviewed registered feature source changed.")
        elif new[identity] != old[identity]:
            raise SourceRepairError("Reconstruction cannot rewrite an already adopted feature.")
    return tuple(deepcopy(after))
