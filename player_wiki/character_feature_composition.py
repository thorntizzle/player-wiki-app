"""Current, source-bound replacement of one attained feature's mechanics.

Canonical attainment and retained observations are never edited here. This
module performs no writes, grants no imported totals and owns no transaction.
Only the finite registered rule is executable; its roll procedure stays an
explicit source reference rather than an invented automatic state transition.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json

REGISTERED_WILD_GRANT = "wild_magic_modification@1/wild_die@1"
REPLACEMENT_KIND = "feature_replacement_grant"
WILD_MECHANIC = "wild_magic_modification"
LEGACY_WILD_PAGE = "mechanics/wild-magic-modification"
SORCERER_KEY = "dnd-5e|class|phb|sorcerer"
WILD_SUBCLASS_KEY = "dnd-5e|subclass|phb|wildmagic-sorcerer-phb"
SURGE_KEY = "dnd-5e|subclassfeature|phb|wildmagicsurge-sorcerer-phb-wild-phb-1"
TIDES_KEY = "dnd-5e|subclassfeature|phb|tidesofchaos-sorcerer-phb-wild-phb-1"
BEND_LUCK_KEY = "dnd-5e|subclassfeature|phb|bendluck-sorcerer-phb-wild-phb-6"
CLAIM_FIELD = "feature_replacement_claim"
_BODY_METADATA = frozenset({"custom_campaign_slug", "provenance", "search_metadata",
    "body_format", "body_markdown", "updated_by_user_id", "mechanic_effects"})


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value):
    return sha256(_json(value).encode("utf-8")).hexdigest()


def wild_replacement_effect():
    return {"kind": REPLACEMENT_KIND, "mechanic_key": WILD_MECHANIC,
            "mechanic_version": 1, "replacement_key": "wild_die", "replacement_version": 1,
            "operation": "replace", "affected_rule_facet": "feature_mechanics",
            "base_rule_ref": {"library_slug": "DND-5E", "entry_type": "subclassfeature",
                              "source_id": "PHB", "entry_key": SURGE_KEY},
            "owner_rule": {"class_entry_key": SORCERER_KEY, "subclass_entry_key": WILD_SUBCLASS_KEY},
            "baseline_carry_forward": {"retained_entry_keys": [TIDES_KEY, BEND_LUCK_KEY]},
            "resource": {"id": "wild-die", "die_faces": 6,
                "maximum": {"scope": "total_character_level", "mode": "half_level", "round": "down"},
                "reset_on": "long_rest", "reset_to": "max"}}


def _token(value):
    return "".join(char for char in value.casefold() if char.isalnum()) if type(value) is str else ""


def declares_replacement(value):
    """Conservative recognition only; aliases never authorize a rule."""
    pending, visited = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        visited += 1
        if visited > 256 or depth > 12:
            return False  # A large unrelated payload is not a Wild declaration.
        if type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is dict:
            if any(_token(item.get(key)) in {"wildmagicmodification", "wilddie"}
                    for key in ("mechanic_key", "mechanicKey", "replacement_key", "replacementKey")):
                return True
            pending.extend((child, depth + 1) for child in item.values() if type(child) in {dict, list})
    return False


def strict_wild_effects(value):
    # Canonical JSON preserves bool/int and every container/type distinction.
    if type(value) is not list or len(value) != 1 or type(value[0]) is not dict:
        return False
    try:
        return _json(value) == _json([wild_replacement_effect()])
    except (TypeError, ValueError):
        return False


def wild_source_metadata(metadata, campaign_slug):
    valid = (type(metadata) is dict and set(metadata) <= _BODY_METADATA
            and metadata.get("custom_campaign_slug") == campaign_slug
            and strict_wild_effects(metadata.get("mechanic_effects")))
    if not valid:
        return False
    try:
        _json(metadata)
    except (TypeError, ValueError):
        return False
    return True


def wild_resource_registration(feature):
    """Recognize a typed candidate/effective payload, never prove its source."""
    if type(feature) is not dict:
        return None
    effects = feature.get("mechanic_effects")
    claim = _claim(feature)
    if not strict_wild_effects(effects) and claim is not None:
        ref = feature.get("systems_ref")
        declared_ref = claim.get("source_ref")
        if (type(ref) is not dict or type(declared_ref) is not dict
                or any(ref.get(key) != declared_ref.get(key) for key in
                       ("entry_key", "entry_type", "source_id", "slug"))):
            return None
        effects = [claim.get("declaration")]
    if not strict_wild_effects(effects):
        return None
    ref = feature.get("systems_ref")
    if (type(ref) is not dict or any(type(ref.get(key)) is not str or not ref[key]
            for key in ("entry_key", "entry_type", "source_id", "slug"))
            or ref["entry_type"] != "feature"):
        return None
    return {"source_id": ref["source_id"], "slug": ref["slug"],
            "category": feature.get("category") if feature.get("category") in {
                "feat", "class_feature", "subclass_feature"} else "class_feature"}


def selected_replacement_claim(entry, *, class_row_id=""):
    """Called only by existing explicit source selection/adoption writers.

    This retained registration is a non-entitling intent/source claim. Current
    eligible metadata, class ownership and recipe proof remain independent.
    """
    metadata = entry.metadata
    if not declares_replacement(metadata):
        return None
    campaign = metadata.get("custom_campaign_slug") if type(metadata) is dict else None
    if (type(campaign) is not str or not campaign or entry.entry_type != "feature"
            or not wild_source_metadata(metadata, campaign)
            or type(class_row_id) is not str):
        raise ValueError("The selected registered replacement needs current source repair.")
    return {"schema_version": 1, "source_ref": _identity(entry),
            "declaration": wild_replacement_effect(), "class_row_id": class_row_id}


def _claim(row):
    if CLAIM_FIELD not in row:
        return None
    # The retained field is reserved for this registered family. Malformation
    # is negative evidence, never an implicit request to re-enable the base.
    claim = row[CLAIM_FIELD]
    return claim if type(claim) is dict else {}


def _claim_matches(row, claim, entry):
    if (type(claim) is not dict or set(claim) != {"schema_version", "source_ref", "declaration", "class_row_id"}
            or type(claim.get("schema_version")) is not int or claim["schema_version"] != 1
            or type(claim.get("class_row_id")) is not str
            or not strict_wild_effects([claim.get("declaration")])
            or type(claim.get("source_ref")) is not dict or entry is None
            or claim["source_ref"] != _identity(entry)):
        return False
    return (row.get("class_row_id") in (None, "", claim["class_row_id"])
            or claim["class_row_id"] == "" and type(row.get("class_row_id")) is str)


def _page(row):
    value = row.get("page_ref")
    if type(value) is dict:
        value = value.get("slug") or value.get("page_ref")
    return value.strip() if type(value) is str else ""


def _identity(entry):
    return {key: getattr(entry, key) for key in ("library_slug", "entry_key", "entry_type", "source_id", "slug", "title")}


def _publication(entry):
    try:
        digest = _digest({"metadata": entry.metadata, "body": entry.body})
    except (TypeError, ValueError):
        digest = None
    try:
        metadata_digest = _digest(entry.metadata)
    except (TypeError, ValueError):
        metadata_digest = None
    return {"identity": _identity(entry), "rules_digest": digest, "metadata_digest": metadata_digest}


def _reader(service):
    # A builder facade is deliberately cache-incapable, but the actual phase
    # view still supplies explicit nonbootstrap semantic reads.
    if not callable(getattr(service, "get_entry_for_character_read", None)):
        phase = getattr(service, "source_read_phase", None)
        if phase is not None:
            service = phase.systems_view()
    return service


def _entry(service, campaign, ref, *, kind=None):
    if type(ref) is not dict or any(type(ref.get(key)) is not str or not ref[key]
            for key in ("entry_key", "entry_type", "source_id", "slug")):
        return None
    getter = getattr(_reader(service), "get_entry_for_character_read", None)
    if not callable(getter):
        return None
    entry = getter(campaign, ref["entry_key"])
    if (entry is None or kind is not None and entry.entry_type != kind
            or entry.library_slug != "DND-5E"
            or any(ref[key] != getattr(entry, key) for key in ("entry_key", "entry_type", "source_id", "slug"))
            or any(ref.get(key) not in (None, "") and ref[key] != getattr(entry, key)
                   for key in ("library_slug", "title"))):
        return None
    return entry


@dataclass(frozen=True, slots=True)
class FeatureComposition:
    replaced_ids: frozenset[str] = frozenset()
    withheld_ids: frozenset[str] = frozenset()
    qualified_ids: frozenset[str] = frozenset()
    unresolved_ids: frozenset[str] = frozenset()
    disabled_owners: frozenset[tuple[str, str]] = frozenset()
    resource_owners: tuple[str, ...] = ()
    identity_json: str = "{}"
    selection_json: str = ""

    def matches_definition(self, definition):
        # Compare the complete mechanical selection domain, not the old
        # subset. New claims, duplicate rows and new level contributors matter;
        # names, descriptions, notes, stats and derived totals do not.
        from .character_profile import profile_class_rows
        return (bool(self.selection_json) and self.selection_json == _json(
            _composition_selection(definition.features, profile_class_rows(definition.profile))))

    def resource_owner(self, feature_id):
        rows = [json.loads(row) for row in self.resource_owners]
        matches = [row for row in rows if row["feature_id"] == feature_id]
        return matches[0] if len(matches) == 1 else None


def _selection_identity(row):
    return {"id": row.get("id"), "systems_ref": deepcopy(row.get("systems_ref")), "page_ref": deepcopy(row.get("page_ref")),
        "class_row_id": row.get("class_row_id"), "mechanics_suppressed": row.get("mechanics_suppressed"),
        "claim": [CLAIM_FIELD in row, deepcopy(row.get(CLAIM_FIELD))]}


def _composition_selection(features, class_rows):
    return {"classes": deepcopy(class_rows), "features": [
        _selection_identity(row) if type(row) is dict else deepcopy(row) for row in features]}


def _compose(*, claims, owner_facts, targets, definition_features, class_rows):
    """Pure composition of current detached facts; never fetch or mutate."""
    replaced, withheld, qualified, unresolved, disabled, resources = set(), set(), set(), set(), set(), []
    class_row_ids = [row.get("row_id") for row in class_rows]
    selection = _composition_selection(definition_features, class_rows)
    ids = Counter(row.get("id") for row in definition_features if type(row) is dict and type(row.get("id")) is str)
    row_ids = [owner["class_row"]["row_id"] for owner in owner_facts]
    unresolved.update(claim["id"] for claim in claims)
    for owner in owner_facts:
        row_id = owner["class_row"]["row_id"]
        associated = [claim for claim in claims if claim["owner_selector"] in ("", row_id)]
        if not associated:
            continue
        base_rows = [target for target in targets if target["class_row_id"] == row_id]
        candidate = associated[0] if len(associated) == 1 else None
        compatible = [item for item in owner_facts
                      if candidate is not None and candidate["owner_selector"] in ("", item["class_row"]["row_id"])]
        valid = (candidate is not None and candidate["qualified"] is True
            and len(compatible) == 1 and len(row_ids) == len(set(row_ids))
            and all(count == 1 for count in ids.values())
            and all(type(identity) is str and identity for identity in class_row_ids)
            and len(class_row_ids) == len(set(class_row_ids))
            and ids.get(candidate["id"]) == 1 and len(base_rows) <= 1
            and all(target["qualified"] and ids.get(target["id"]) == 1 for target in base_rows))
        disabled.add((row_id, SURGE_KEY))
        for target in base_rows:
            (replaced if valid else withheld).add(target["id"])
        if valid:
            claim = candidate
            qualified.add(claim["id"])
            unresolved.discard(claim["id"])
            resources.append(_json({"feature_id": claim["id"], "class_row_id": row_id,
                "source": claim["publication"], "declaration": wild_replacement_effect(),
                "owner": owner, "resource_id": "wild-die"}))
    for target in targets:
        if any(claim["owner_selector"] in ("", target["class_row_id"]) for claim in claims):
            if target["id"] not in replaced:
                withheld.add(target["id"])
            disabled.add((target["class_row_id"], SURGE_KEY))
    identity = {"schema_version": 1, "claims": claims, "owners": owner_facts, "targets": targets,
                "replaced": sorted(replaced), "withheld": sorted(withheld), "qualified": sorted(qualified),
                "selection": selection}
    return FeatureComposition(frozenset(replaced), frozenset(withheld), frozenset(qualified),
        frozenset(unresolved), frozenset(disabled), tuple(resources), _json(identity), _json(selection))


def resolve_feature_composition(definition, service, *, current_payloads=None,
                                feature_statuses=None, verified_class_rows=None):
    """Resolve exact current facts once per existing read phase, then compose.

    Explicit source selection retains a non-entitling registration claim. It
    survives source unavailability and ordinary normalization, but supplies no
    positive effects without the exact currently eligible registered source.
    """
    from .character_profile import profile_class_rows
    features = [row for row in definition.features if type(row) is dict]
    if len(features) > 512:
        raise ValueError("Feature composition exceeds the supported bounds.")
    statuses = {(row.kind, row.instance_id): row.status for row in feature_statuses or ()}
    classes = profile_class_rows(definition.profile)
    class_ids = [row.get("row_id") for row in classes]
    claims = []
    for row in features:
        identity = row.get("id")
        if type(identity) is not str or not identity:
            continue
        entry = _entry(service, definition.campaign_slug, row.get("systems_ref"), kind="feature")
        metadata = entry.metadata if entry is not None else None
        claim = _claim(row)
        legacy = _page(row) == LEGACY_WILD_PAGE
        declared = (declares_replacement(metadata) or claim is not None
                    or declares_replacement(row.get("mechanic_effects")))
        if not legacy and not declared:
            continue
        supplied = current_payloads.get(identity) if current_payloads is not None else metadata
        publication = _publication(entry) if entry is not None else None
        valid = (entry is not None and publication["rules_digest"] is not None and not row.get("mechanics_suppressed")
            and wild_source_metadata(metadata, definition.campaign_slug)
            and _claim_matches(row, claim, entry)
            and type(supplied) is dict and _json(supplied) == _json(metadata)
            and (feature_statuses is None or statuses.get(("feature", identity)) == "VERIFIED"))
        raw_owner = row.get("class_row_id")
        claimed_owner = claim.get("class_row_id") if claim is not None else None
        if any(value not in (None, "") and (type(value) is not str or value not in class_ids)
               for value in (raw_owner, claimed_owner)):
            raise ValueError("A retained replacement owner is malformed or no longer selected; use source repair.")
        # A conflicting declaration cannot redirect negative suppression away
        # from the row's actual owner. It also cannot qualify positive effects.
        selector = raw_owner or claimed_owner or ""
        claims.append({"id": identity, "class_row_id": row.get("class_row_id"), "owner_selector": selector,
                       "qualified": bool(valid), "legacy_page": _page(row), "publication": publication,
                       "selection": _selection_identity(row)})
    if not claims:
        # Preserve the unaffected public authority identity, while an empty
        # frame still refuses reuse over a newly introduced selection.
        return FeatureComposition(selection_json=_json(_composition_selection(definition.features, classes)))
    owner_facts, targets = [], []
    for row in classes:
        row_id, level = row.get("row_id"), row.get("level")
        if type(row_id) is not str or not row_id or type(level) is not int or not 1 <= level <= 20:
            continue
        cls = _entry(service, definition.campaign_slug, row.get("systems_ref"), kind="class")
        sub = _entry(service, definition.campaign_slug, row.get("subclass_ref"), kind="subclass")
        raw_owner = (type(row.get("systems_ref")) is dict and row["systems_ref"].get("entry_key") == SORCERER_KEY
                     and type(row.get("subclass_ref")) is dict and row["subclass_ref"].get("entry_key") == WILD_SUBCLASS_KEY)
        for feature in features:
            ref = feature.get("systems_ref")
            if (raw_owner and type(ref) is dict and ref.get("entry_key") == SURGE_KEY
                    and feature.get("class_row_id") in (None, "", row_id)
                    and type(feature.get("id")) is str and feature["id"]):
                target_entry = _entry(service, definition.campaign_slug, ref, kind="subclassfeature")
                targets.append({"id": feature["id"], "class_row_id": row_id, "source_ref": deepcopy(ref),
                    "qualified": (target_entry is not None
                        and feature.get("class_row_id") in (None, "", row_id))})
        if (cls is None or sub is None or cls.entry_key != SORCERER_KEY or sub.entry_key != WILD_SUBCLASS_KEY
                or sub.metadata.get("class_name") != cls.title or sub.metadata.get("class_source") != cls.source_id
                or verified_class_rows is not None and row_id not in verified_class_rows):
            continue
        collector = getattr(_reader(service), "collect_attained_deterministic_feature_entries", None)
        if not callable(collector):
            continue
        attained = collector(definition.campaign_slug, sub, attained_level=level)
        matching = [entry for entry in attained if entry.entry_key == SURGE_KEY]
        if len(matching) != 1 or matching[0].entry_type != "subclassfeature":
            continue
        surge = matching[0]
        if (surge.metadata.get("class_name") != "Sorcerer" or surge.metadata.get("class_source") != "PHB"
                or surge.metadata.get("subclass_name") != "Wild" or surge.metadata.get("subclass_source") != "PHB"
                or type(surge.metadata.get("level")) is not int or surge.metadata["level"] != 1):
            continue
        publications = (_publication(cls), _publication(sub), _publication(surge))
        if any(value["rules_digest"] is None for value in publications):
            continue
        owner_facts.append({"class_row": deepcopy(row), "class": publications[0],
            "subclass": publications[1], "replaced_publication": publications[2]})
    return _compose(claims=claims, owner_facts=owner_facts, targets=targets, definition_features=features,
                    class_rows=classes)


def retain_replacement_continuations(prior, features, *, profile, service):
    """Keep an attained replacement target instead of regenerating its slot.

    This only removes a new, plain deterministic class-feature payload. It
    neither edits historical rows nor merges acquisition identities. Ambiguous
    sources, owners, extra observations and multiple new occurrences remain in
    the candidate for the ordinary strict composition checks to reject.
    """
    from .character_profile import profile_class_rows

    identities = [row.get("id") for row in features if type(row) is dict]
    if (len(identities) != len(features)
            or any(type(value) is not str or not value for value in identities)
            or len(identities) != len(set(identities))):
        return deepcopy(features)
    composition = resolve_feature_composition(prior, service)
    if not composition.qualified_ids:
        return deepcopy(features)
    facts = json.loads(composition.identity_json)
    classes = profile_class_rows(profile)
    class_ids = [row.get("row_id") for row in classes]
    if (any(type(value) is not str or not value for value in class_ids)
            or len(class_ids) != len(set(class_ids))):
        return deepcopy(features)
    prior_ids = {row["id"] for row in prior.features
                 if type(row) is dict and type(row.get("id")) is str}
    generated_fields = {"id", "name", "category", "source", "description_markdown",
                        "activation_type", "tracker_ref", "systems_ref", "class_row_id",
                        "native_acquisition"}
    omitted = set()
    for target in facts["targets"]:
        identity, owner_id = target["id"], target["class_row_id"]
        if (identity not in composition.replaced_ids or not target["qualified"]
                or sum(row["id"] == identity for row in facts["targets"]) != 1):
            continue
        old = [row for row in prior.features if type(row) is dict and row.get("id") == identity]
        retained = [row for row in features if type(row) is dict and row.get("id") == identity]
        owners = [row for row in facts["owners"] if row["class_row"]["row_id"] == owner_id]
        future = [row for row in classes if row.get("row_id") == owner_id]
        if (len(old) != 1 or len(retained) != 1 or _json(old[0]) != _json(retained[0])
                or len(owners) != 1 or len(future) != 1):
            continue
        owner, next_owner = owners[0], future[0]
        level = next_owner.get("level")
        if type(level) is not int or not owner["class_row"]["level"] <= level <= 20:
            continue
        matching_owners = [row for row in classes
            if type(row.get("systems_ref")) is dict and type(row.get("subclass_ref")) is dict
            and row["systems_ref"].get("entry_key") == owner["class"]["identity"]["entry_key"]
            and row["subclass_ref"].get("entry_key") == owner["subclass"]["identity"]["entry_key"]]
        if len(matching_owners) != 1:
            continue
        cls = _entry(service, prior.campaign_slug, next_owner.get("systems_ref"), kind="class")
        sub = _entry(service, prior.campaign_slug, next_owner.get("subclass_ref"), kind="subclass")
        if (cls is None or sub is None or _publication(cls) != owner["class"]
                or _publication(sub) != owner["subclass"]):
            continue
        # Count malformed aliases too; a valid generated row cannot hide one.
        aliases = [row for row in features if type(row) is dict and row.get("id") != identity
                   and type(row.get("systems_ref")) is dict
                   and row["systems_ref"].get("entry_key") == target["source_ref"]["entry_key"]
                   and row.get("class_row_id") in (None, "", owner_id)]
        if len(aliases) != 1:
            continue
        row = aliases[0]
        entry = _entry(service, prior.campaign_slug, row.get("systems_ref"), kind="subclassfeature")
        key = target["source_ref"]["entry_key"]
        if (set(row) != generated_fields or type(row.get("id")) is not str or not row["id"]
                or row["id"] in prior_ids or row.get("class_row_id") != owner_id
                or entry is None or _publication(entry) != owner["replaced_publication"]
                or row.get("name") != entry.title or row.get("source") != entry.source_id
                or row.get("category") != "class_feature" or row.get("activation_type") != "passive"
                or row.get("description_markdown") != "" or row.get("tracker_ref") is not None
                or row.get("native_acquisition") != {"grant_rule_id": key, "choice_slot_id": key}):
            continue
        omitted.add(row["id"])
    return [deepcopy(row) for row in features if type(row) is not dict
            or type(row.get("id")) is not str or row["id"] not in omitted]


def registered_owner_payload(composition, feature_id, current, *, definition):
    """Source-owned metadata used by existing managed template/basis consumers."""
    if type(composition) is not FeatureComposition or not composition.matches_definition(definition):
        return None
    owner = composition.resource_owner(feature_id)
    if owner is None or type(current) is not dict or not strict_wild_effects(current.get("mechanic_effects")):
        return None
    from .character_profile import profile_class_rows
    rows = [row for row in profile_class_rows(definition.profile) if row.get("row_id") == owner["class_row_id"]]
    features = [row for row in definition.features if type(row) is dict and row.get("id") == feature_id]
    if (len(rows) != 1 or len(features) != 1 or _json(rows[0]) != _json(owner["owner"]["class_row"])
            or _digest(current) != owner["source"]["metadata_digest"]
            or type(features[0].get("systems_ref")) is not dict
            or any(features[0]["systems_ref"].get(key) != owner["source"]["identity"][key]
                for key in ("entry_key", "entry_type", "source_id", "slug"))
            or features[0].get("class_row_id") not in (None, "", owner["class_row_id"])):
        return None
    result = deepcopy(current)
    result.update(class_name="Sorcerer", class_source="PHB", subclass_name="Wild", subclass_source="PHB", level=1)
    return result


def replacement_summary(effects):
    """Descriptive support summary only; this never authorizes mechanics."""
    if type(effects) is not list:
        return None
    compared = deepcopy(effects)
    for row in compared:
        if type(row) is dict and row.get("source") == "mechanic_effects":
            row.pop("source")
    if not strict_wild_effects(compared):
        return None
    effect = wild_replacement_effect()
    return {key: deepcopy(effect[key]) for key in (
        "operation", "affected_rule_facet", "base_rule_ref", "owner_rule", "baseline_carry_forward")}


def replacement_option(metadata):
    if type(metadata) is not dict:
        return None
    summary = replacement_summary(metadata.get("mechanic_effects"))
    if summary is None:
        return None
    return {"base_rule_refs": [summary["base_rule_ref"]],
            "mechanic_effects": deepcopy(metadata["mechanic_effects"]), "overlay_support": "modeled"}


def apply_effective_composition(features, composition):
    """Ephemeral view; never use this as persisted replacement history."""
    rows = deepcopy(features)
    if type(composition) is not FeatureComposition:
        return rows
    for row in rows:
        identity = row.get("id") if type(row) is dict else None
        if identity in composition.replaced_ids | composition.withheld_ids | composition.unresolved_ids:
            for key in ("campaign_option", "spell_manager", "spell_source_authorization", "additional_spells",
                        "spell_support", "mechanic_effects", "modeled_effects", "tracker_ref"):
                row.pop(key, None)
            row["mechanics_suppressed"] = True
            row.pop(CLAIM_FIELD, None)  # Raw claim remains in the retained model.
            row["authority_status"] = "REPLACED" if identity in composition.replaced_ids else "NEEDS REPAIR"
            row["authority_replacement"] = "Current qualified replacement" if identity in composition.replaced_ids else "Replacement source needs repair"
    return rows


def _restore_observation(result, original, raw_features):
    """Insert a dropped raw row before its next surviving original neighbor."""
    after = False
    for row in raw_features:
        if row is original:
            after = True
            continue
        if after and type(row) is dict:
            positions = [index for index, current in enumerate(result)
                if type(current) is dict and current.get("id") == row.get("id")]
            if positions:
                result.insert(positions[0], deepcopy(original))
                return
    result.append(deepcopy(original))


def retain_replaced_observations(raw_features, derived_features, composition):
    """Keep exact old rows in authoring; effective suppression is recomputed."""
    if type(composition) is not FeatureComposition:
        return derived_features
    disabled = composition.replaced_ids | composition.withheld_ids
    if any(type(row) is dict and (type(row.get("id")) is not str or not row["id"])
            for row in [*raw_features, *derived_features]):
        raise ValueError("Feature observations need exact text identities.")
    originals = {row["id"]: row for row in raw_features if type(row) is dict}
    counts = Counter(row["id"] for row in raw_features if type(row) is dict)
    if any(counts[identity] != 1 for identity in disabled):
        raise ValueError("Replaced feature observations are ambiguous.")
    result = [deepcopy(originals[row["id"]]) if type(row) is dict and row.get("id") in disabled
              and row["id"] in originals else deepcopy(row) for row in derived_features]
    found = Counter(row.get("id") for row in result if type(row) is dict)
    if any(found[identity] > 1 for identity in disabled):
        raise ValueError("Derived replaced feature observations are ambiguous.")
    # A connected rebuild cannot erase the retained history merely because its
    # source is now mechanically inert. Preserve the exact original rows.
    for row in raw_features:
        if type(row) is dict and row.get("id") in disabled and not found[row["id"]]:
            _restore_observation(result, row, raw_features)
    return result


def retain_replacement_claims(raw_features, derived_features):
    """A normalizer may neither erase nor bless a retained registration claim."""
    originals = [row for row in raw_features if type(row) is dict and CLAIM_FIELD in row]
    ids = [row.get("id") for row in originals]
    if any(type(identity) is not str or not identity for identity in ids) or len(ids) != len(set(ids)):
        raise ValueError("Retained replacement registrations are ambiguous.")
    if any(type(row) is dict and (type(row.get("id")) is not str or not row["id"])
            for row in derived_features):
        raise ValueError("Derived replacement registrations need exact text identities.")
    result = deepcopy(derived_features)
    for original in originals:
        matches = [row for row in result if type(row) is dict and row.get("id") == original["id"]]
        if len(matches) > 1:
            raise ValueError("Derived replacement registrations are ambiguous.")
        if not matches:
            _restore_observation(result, original, raw_features)
        else:
            matches[0][CLAIM_FIELD] = deepcopy(original[CLAIM_FIELD])
    return result


def validate_retained_replacement_transition(prior, candidate, *, relink_target="", owner_annotations=None):
    """An ordinary receiver cannot silently clear or rewrite retained intent."""
    if type(relink_target) is not str:
        raise ValueError("Replacement relink identity is malformed.")
    annotations = {} if owner_annotations is None else owner_annotations
    if type(annotations) is not dict or any(type(key) is not str or type(value) is not str
            or not key or not value for key, value in annotations.items()):
        raise ValueError("Replacement owner annotation is malformed.")
    for original in prior.features:
        if type(original) is not dict or CLAIM_FIELD not in original:
            continue
        identity = original.get("id")
        if type(identity) is not str or not identity:
            raise ValueError("Retained replacement identity needs source repair.")
        old = [row for row in prior.features if type(row) is dict and row.get("id") == identity]
        rows = [row for row in candidate.features if type(row) is dict and row.get("id") == identity]
        if len(old) != 1 or len(rows) != 1:
            raise ValueError("Retained replacement observations cannot be silently removed.")
        expected = _selection_identity(original)
        if identity in annotations:
            if original.get("class_row_id") not in (None, "", annotations[identity]):
                raise ValueError("A retained replacement has a conflicting authenticated owner.")
            expected["class_row_id"] = annotations[identity]
        if identity != relink_target and _json(expected) != _json(_selection_identity(rows[0])):
            raise ValueError("A retained replacement binding needs explicit reviewed Source Repair relink.")
