"""Explicit physical tracker ownership carried by reconstruction audit custody."""
from __future__ import annotations

from copy import deepcopy
import json

from .character_skill_adoptions import canonical, digest
from .character_source_repair import SourceRepairError

FRAME = "tracker_associations"
PREFIX = "feature_tracker_association_"
FIELDS = {"schema_version", "tracker_id", "canonical_id", "feature_id", "class_row_id",
          "systems_ref", "family", "member", "prior_feature_json", "prior_template_json", "prior_state_json"}


def stored(definition):
    frame = definition.source.get("native_reconstruction_choices") or {}
    if type(frame) is not dict:
        raise SourceRepairError("Physical tracker history needs a typed reconstruction frame.")
    rows = frame.get(FRAME, [])
    if type(rows) is not list or len(rows) > 64:
        raise SourceRepairError("Tracker association history exceeds its supported bound.")
    seen, members = set(), set()
    for row in rows:
        if (type(row) is not dict or set(row) != FIELDS or type(row["schema_version"]) is not int
                or row["schema_version"] != 1 or type(row["systems_ref"]) is not dict
                or any(type(row[k]) is not str or not 0 < len(row[k]) <= 512 for k in
                       ("tracker_id", "canonical_id", "feature_id", "class_row_id", "family", "member"))):
            raise SourceRepairError("Tracker association has no exact typed ownership.")
        for field in ("prior_feature_json", "prior_template_json", "prior_state_json"):
            value = row[field]
            if type(value) is not str or not 0 < len(value) <= 65536:
                raise SourceRepairError("Tracker observation history is malformed.")
            decoded = json.loads(value)
            if type(decoded) is not dict or canonical(decoded) != value:
                raise SourceRepairError("Tracker observation history must preserve exact object bytes.")
        member = row["class_row_id"], row["canonical_id"]
        if row["tracker_id"] in seen or member in members:
            raise SourceRepairError("A physical tracker or managed pool has more than one association.")
        seen.add(row["tracker_id"])
        members.add(member)
    return tuple(deepcopy(rows))


def physical_id(member, feature, bindings=()):
    """Caller supplies independently qualified bindings, never raw source JSON."""
    canonical_id = str(dict((member or {}).get("tracker") or {}).get("id") or "")
    from .managed_resource_registry import resolve_managed_resource_family_and_member
    family, actual = resolve_managed_resource_family_and_member(feature)
    signature = digest({key: family[key] for key in ("category", "source", "inventory")}) if family else None
    matches = [row for row in bindings if row["canonical_id"] == canonical_id
               and row["feature_id"] == feature.get("id")
               and row["class_row_id"] == feature.get("class_row_id")
               and row["systems_ref"] == feature.get("systems_ref")
               and row["member"] == (member or {}).get("key")
               and row["family"] == signature and actual == member]
    if len(matches) > 1:
        raise SourceRepairError("A managed member has ambiguous physical ownership.")
    return matches[0]["tracker_id"] if matches else canonical_id


def custody(definition, origin, rows):
    return (({"tracker_association_custody": {"campaign_slug": definition.campaign_slug,
        "character_slug": definition.character_slug, "action_id": origin["action_id"],
        "association_digest": digest(list(rows)), "associations": deepcopy(list(rows))}},) if rows else ())


def unique_member(definition, binding):
    from .managed_resource_registry import resolve_managed_resource_family_and_member
    owners = []
    for feature in definition.features:
        if type(feature) is not dict:
            continue
        if feature.get("class_row_id") not in (None, "", binding["class_row_id"]):
            continue
        ref = feature.get("systems_ref")
        if type(ref) is not dict:
            continue
        probe = {**feature, "source": ref.get("source_id")}
        _family, member = resolve_managed_resource_family_and_member(probe)
        if str(dict((member or {}).get("tracker") or {}).get("id") or "") == binding["canonical_id"]:
            owners.append(feature)
    return (len(owners) == 1 and owners[0].get("id") == binding["feature_id"]
            and owners[0].get("tracker_ref") == binding["tracker_id"]
            and not any(type(row) is dict and row.get("id") == binding["canonical_id"] for row in definition.resource_templates))


def qualified(definition, witnesses=()):
    rows = stored(definition)
    if not rows:
        return rows
    origin = definition.source.get("native_reconstruction") or {}
    decoded = [json.loads(row) if isinstance(row, str) else row for row in witnesses]
    if (origin.get("tracker_association_digest") != digest(list(rows))
            or not origin.get("action_id") or custody(definition, origin, rows)[0] not in decoded):
        raise SourceRepairError("Physical tracker association needs independently recovered reconstruction custody.")
    if any(not unique_member(definition, row) for row in rows):
        raise SourceRepairError("Physical tracker association has a duplicate or changed current member.")
    return rows


def choice_fields(definition, state, service, pages, values=None):
    from .character_profile import profile_class_rows
    from .managed_resource_registry import resolve_managed_resource_family_and_member
    from .character_source_authority import (_current_managed_pool_owners, _eligible_page_records,
        _current_payload, _source_identity, _observed_list)
    from .character_builder_equipment import _item_effect_metadata
    from .character_models import CharacterDefinition
    existing = {row["tracker_id"] for row in stored(definition)}
    fields = []
    classes = profile_class_rows(definition.profile)
    if len(classes) != 1:
        return fields
    for feature in definition.features:
        ref = feature.get("systems_ref") if type(feature) is dict else None
        if type(ref) is not dict or not feature.get("tracker_ref"):
            continue
        probe = {**feature, "source": ref.get("source_id")}
        family, member = resolve_managed_resource_family_and_member(probe)
        canonical_id = str(dict((member or {}).get("tracker") or {}).get("id") or "")
        physical = feature["tracker_ref"]
        if not family or not canonical_id or physical == canonical_id or physical in existing:
            continue
        templates = [r for r in definition.resource_templates if r.get("id") == physical]
        observations = [r for r in _observed_list(state.get("resources")) if type(r) is dict and r.get("id") == physical]
        if len(templates) != 1 or len(observations) != 1:
            continue
        if any(r.get("id") == canonical_id for r in definition.resource_templates):
            continue
        # Initial association does not reinterpret item bonuses aimed at a canonical pool.
        blocked_bonus = False
        for item in definition.equipment_catalog:
            if type(item) is not dict:
                continue
            kind, key = _source_identity(item)
            metadata, error = _current_payload(campaign_slug=definition.campaign_slug,
                kind="item", source_kind=kind, source_key=key, systems_service=service,
                pages=_eligible_page_records(pages),
                expected_slug=str(dict(item.get("systems_ref") or {}).get("slug") or ""),
                expected_ref=dict(item.get("systems_ref") or {}))
            if metadata is not None and not error:
                bonuses = _item_effect_metadata({"resource_template_bonuses": metadata.get("resource_template_bonuses", [])}).get("resource_template_bonuses", [])
                if any(row.get("id") in {canonical_id, physical} for row in bonuses):
                    blocked_bonus = True
                    break
        if blocked_bonus:
            fields.append({"name": PREFIX + digest(physical)[:20],
                "label": ref.get("title") or feature.get("name") or physical,
                "tracker_id": physical, "options": [],
                "reason": "Association is unavailable while an item source modifies this resource capacity; the existing tracker and observations are retained."})
            continue
        options = []
        for cls in classes:
            row_id = cls.get("row_id")
            if not row_id or feature.get("class_row_id") not in (None, "", row_id) or templates[0].get("class_row_id") not in (None, "", row_id):
                continue
            row = {"schema_version": 1, "tracker_id": physical, "canonical_id": canonical_id,
                "feature_id": feature["id"], "class_row_id": row_id, "systems_ref": deepcopy(ref),
                "family": digest({key: family[key] for key in ("category", "source", "inventory")}), "member": member["key"],
                "prior_feature_json": canonical(feature), "prior_template_json": canonical(templates[0]),
                "prior_state_json": canonical(observations[0])}
            if not unique_member(definition, row):
                continue
            payload = deepcopy(definition.to_dict())
            for name, identity in (("features", feature["id"]), ("resource_templates", physical)):
                for current in payload[name]:
                    if current.get("id") == identity:
                        current["class_row_id"] = row_id
            from .character_armor_models import (compose as compose_armor, FRAME_KEY as ARMOR_FRAME,
                CHOICE_FIELD, SUMMARY_FIELD, stored as armor_history)
            armor_rows = (compose_armor(definition, service, values) if values and CHOICE_FIELD in values
                          else list(armor_history(definition)))
            frame = payload["source"].setdefault("native_reconstruction_choices", {})
            frame[ARMOR_FRAME] = armor_rows
            if values and CHOICE_FIELD in values:
                # Structural qualification validates the same explicit choices as the form.
                frame["inputs"] = {**dict(frame.get("inputs") or {}),
                    **{key: deepcopy(values[key]) for key in (CHOICE_FIELD, SUMMARY_FIELD) if key in values}}
            staged = CharacterDefinition.from_dict(payload)
            pools = _current_managed_pool_owners(staged, systems_service=service,
                pages=_eligible_page_records(pages), tracker_bindings=(row,))
            tracker = dict(member.get("tracker") or {})
            reset = tracker.get("reset_on")
            compatible = all(templates[0].get(key) == expected for key, expected in {
                "reset_on": reset, "reset_to": tracker.get("reset_to", "max"),
                "rest_behavior": tracker.get("rest_behavior") or ("confirm_before_reset" if reset in {"long_rest", "short_rest"} else "manual_only")}.items())
            formula = dict(tracker.get("max_formula") or {})
            def supported(part):
                return (part.get("kind") in {"fixed", "level", "total_half_level", "proficiency_bonus", "threshold"}
                        or part.get("kind") == "sum" and type(part.get("parts")) is list and all(supported(p) for p in part["parts"]))
            if physical not in pools or not compatible or not supported(formula):
                continue
            from .character_feature_trackers import _resolve_managed_resource_formula_value
            level = pools[physical]["class"]["level"]
            maximum = _resolve_managed_resource_formula_value(formula, ability_scores={},
                current_level=level, total_character_level=level)
            if (type(templates[0].get("max")) is int and templates[0]["max"] != maximum
                    or type(observations[0].get("max")) is int and observations[0]["max"] != maximum
                    or type(observations[0].get("current")) is int and not 0 <= observations[0]["current"] <= maximum):
                continue
            if physical in pools:
                options.append({"value": digest(row), "label": f"Associate with {ref.get('title', ref['entry_key'])} ({row_id})",
                                "record": row})
        if options:
            fields.append({"name": PREFIX + digest(physical)[:20],
                "label": ref.get("title") or feature.get("name") or physical,
                "tracker_id": physical, "options": options})
    return fields


def compose(prior, payload, state, service, pages, inputs):
    rows = list(stored(prior))
    fields = choice_fields(prior, state, service, pages, inputs)
    for field in fields:
        value = inputs.get(field["name"], "keep")
        if value == "keep":
            continue
        matches = [option["record"] for option in field["options"] if option["value"] == value]
        if len(matches) != 1:
            raise SourceRepairError("The physical tracker source or prior observations changed.")
        row = matches[0]
        rows.append(row)
        for name, identity in (("features", row["feature_id"]), ("resource_templates", row["tracker_id"])):
            for current in payload[name]:
                if current.get("id") == identity:
                    current["class_row_id"] = row["class_row_id"]
    if rows:
        payload["source"]["native_reconstruction_choices"][FRAME] = rows


def validate(prior, candidate, state, *, witnesses=(), service=None, pages=()):
    from .character_source_authority import _observed_list
    old, rows = stored(prior), stored(candidate)
    if rows[:len(old)] != old:
        raise SourceRepairError("Physical tracker association history cannot change or disappear.")
    if old:
        qualified(prior, witnesses)
    for row in rows[len(old):]:
        before_feature = [r for r in prior.features if r.get("id") == row["feature_id"]]
        before_template = [r for r in prior.resource_templates if r.get("id") == row["tracker_id"]]
        observation = [r for r in _observed_list(state.get("resources")) if type(r) is dict and r.get("id") == row["tracker_id"]]
        if (len(before_feature) != 1 or len(before_template) != 1 or len(observation) != 1
                or canonical(before_feature[0]) != row["prior_feature_json"]
                or canonical(before_template[0]) != row["prior_template_json"]
                or canonical(observation[0]) != row["prior_state_json"]
                or candidate.source["native_reconstruction_choices"].get("inputs", {}).get(PREFIX + digest(row["tracker_id"])[:20]) != digest(row)):
            raise SourceRepairError("Tracker association lacks its exact prior observations and confirmation.")
        for name, original in (("features", before_feature[0]), ("resource_templates", before_template[0])):
            expected = {**deepcopy(original), "class_row_id": row["class_row_id"]}
            current = [r for r in getattr(candidate, name) if r.get("id") == original["id"]]
            if name == "resource_templates" and len(current) == 1:
                # Normal numeric derivation may replace capacity, never current or metadata.
                expected["max"] = current[0].get("max")
            if current != [expected]:
                raise SourceRepairError("Tracker association changed unowned historical content.")
    if service is not None and rows:
        from .character_source_authority import _current_managed_pool_owners, _eligible_page_records
        pools = _current_managed_pool_owners(candidate, systems_service=service,
            pages=_eligible_page_records(pages), tracker_bindings=rows)
        if any(row["tracker_id"] not in pools for row in rows):
            raise SourceRepairError("Tracker association has no unique current source/class/member owner.")
        available = [option["record"] for field in choice_fields(prior, state, service, pages,
            candidate.source["native_reconstruction_choices"].get("inputs", {})) for option in field["options"]]
        if any(row not in available for row in rows[len(old):]):
            raise SourceRepairError("The physical tracker no longer has compatible current source capacity and recovery.")
    return rows


def validate_transition(prior_record, candidate, proof=None, *, actor_id=None, state=None):
    if stored(prior_record.definition) == stored(candidate):
        return
    from .character_reconstruction_authority import PendingNativeReconstruction
    if type(proof) is not PendingNativeReconstruction or proof.tracker_associations != stored(candidate):
        raise SourceRepairError("Physical tracker association changes require exact reconstruction review.")
    proof.validate_binding(prior_record, candidate, state, actor_id)
