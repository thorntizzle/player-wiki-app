"""Closed structured feature proficiency rules shared by every native consumer.

Source declarations describe grants. Acquisition choices and reconstruction
history describe decisions; neither is a substitute for current source custody.
"""
from __future__ import annotations

from copy import deepcopy
import json
from .character_skill_adoptions import canonical, digest

FIELDS = {"skills": "skill_proficiencies", "tools": "tool_proficiencies",
          "armor": "armor_proficiencies", "weapons": "weapon_proficiencies",
          "languages": "language_proficiencies"}
ALL_TOOLS = "allProficientTools"
HISTORY = "automatic_tool_expertise"
PREFIX = "feature_auto_expertise_"
CONDITIONS = "feature_proficiency_conditions"
_PREPARED = object()


def gaming_set_options():
    """The existing finite gaming-tool domain, shared with reconstruction."""
    from .character_builder_constants import COMMON_TOOL_PROFICIENCY_OPTIONS
    from .repository import normalize_lookup
    return [name for name in COMMON_TOOL_PROFICIENCY_OPTIONS if normalize_lookup(name) in {
        "diceset", "dragonchessset", "playingcardset", "threedragonanteset"}]


def normalize_metadata(metadata):
    """Validate present mechanics without manufacturing absent declarations."""
    if type(metadata) is not dict:
        raise ValueError("Feature proficiency metadata must be an object.")
    result = deepcopy(metadata)
    for category, field in (*FIELDS.items(), ("languages", "languages")):
        if field not in result:
            continue
        blocks = result[field]
        if type(blocks) is not list or len(blocks) > 32:
            raise ValueError("Feature proficiency grants need a bounded list.")
        for block in blocks:
            if type(block) is str and 0 < len(block) <= 160:
                continue
            if type(block) is not dict or not block or len(block) > 32:
                raise ValueError("Unsupported feature proficiency grant.")
            for key, value in block.items():
                if type(key) is not str or not 0 < len(key) <= 160:
                    raise ValueError("Invalid feature proficiency name.")
                if key == "ifAlreadyProficient":
                    if (category != "tools" or set(block) != {key} or type(value) is not dict
                            or set(value) != {"proficiency", "replacement"}
                            or type(value["proficiency"]) is not str or not 0 < len(value["proficiency"]) <= 160
                            or value["replacement"] != {"anyArtisansTool": 1}
                            or type(value["replacement"].get("anyArtisansTool")) is not int):
                        raise ValueError("Conditional tool grants require one named proficiency and one artisan replacement.")
                elif key == "choose":
                    if (type(value) is not dict or set(value) - {"from", "count", "amount"}
                            or type(value.get("from")) is not list or not 1 <= len(value["from"]) <= 128
                            or any(type(v) is not str or not 0 < len(v) <= 160 for v in value["from"])
                            or type(value.get("count", 1)) is not int or not 1 <= value.get("count", 1) <= 18
                            or type(value.get("amount", 1)) is not int or value.get("amount", 1) != 1):
                        raise ValueError("Feature choice needs a bounded exact domain.")
                elif key == "anyGamingSet":
                    if (category != "tools" or type(value) is not int
                            or not 1 <= value <= len(gaming_set_options())):
                        raise ValueError("Gaming-set choices need a bounded tool count.")
                elif key in {"any", "anyTool", "anyArtisansTool", "anyStandard"}:
                    if (type(value) is not int or not 1 <= value <= 18
                            or key == "any" and category not in {"skills", "tools", "languages"}
                            or key in {"anyTool", "anyArtisansTool"} and category != "tools"
                            or key == "anyStandard" and category != "languages"):
                        raise ValueError("Feature choice has an unsupported category or count.")
                elif value is not True:
                    raise ValueError("Fixed feature proficiencies must be true.")
    if "expertise" in result:
        blocks = result["expertise"]
        if type(blocks) is not list or len(blocks) > 32:
            raise ValueError("Feature expertise needs a bounded list.")
        for block in blocks:
            if type(block) is not dict or not block:
                raise ValueError("Feature expertise must be structured.")
            for key, value in block.items():
                if key == ALL_TOOLS:
                    if set(block) != {ALL_TOOLS} or value is not True:
                        raise ValueError("Automatic tool expertise is an explicit true capability.")
                elif key == "anyProficientSkill":
                    if type(value) is not int or not 1 <= value <= 18:
                        raise ValueError("Expertise choices need a bounded count.")
                elif type(key) is not str or not key or value is not True:
                    raise ValueError("Unsupported expertise grant.")
    return result


def contract(entry, *, item_catalog=None, strict=True):
    from . import character_builder as builder
    from .character_builder_constants import SKILL_LABELS, COMMON_TOOL_PROFICIENCY_OPTIONS, UNRESTRICTED_LANGUAGE_OPTIONS, STANDARD_LANGUAGE_OPTIONS
    fixed = {category: [] for category in FIELDS}
    slots = []
    if entry.entry_type not in {"classfeature", "subclassfeature"}:
        return fixed, slots
    try:
        metadata = normalize_metadata(dict(entry.metadata or {}))
        domains = {"skills": list(SKILL_LABELS.values()), "tools": list(COMMON_TOOL_PROFICIENCY_OPTIONS),
                   "languages": list(UNRESTRICTED_LANGUAGE_OPTIONS)}
        for category, field in (*FIELDS.items(), ("languages", "languages")):
            for block in metadata.get(field, []):
                if type(block) is str:
                    fixed[category].append(builder._humanize_proficiency_value(block, category=category))
                    continue
                for key, value in block.items():
                    condition = None
                    if key == "ifAlreadyProficient":
                        condition = builder._humanize_proficiency_value(value["proficiency"], category="tools")
                        options, count = [r["value"] for r in builder._tool_proficiency_options(item_catalog or {}, artisan_only=True)], 1
                    elif key == "choose":
                        options, count = value["from"], value.get("count", 1)
                    elif key == "anyArtisansTool":
                        options, count = [r["value"] for r in builder._tool_proficiency_options(item_catalog or {}, artisan_only=True)], value
                    elif key == "anyGamingSet":
                        options, count = gaming_set_options(), value
                    elif key == "anyStandard":
                        options, count = STANDARD_LANGUAGE_OPTIONS, value
                    elif key in {"any", "anyTool"}:
                        if category not in domains:
                            raise ValueError("Unbounded feature proficiency category.")
                        options, count = domains[category], value
                    else:
                        fixed[category].append(builder._humanize_proficiency_value(key, category=category))
                        continue
                    for _ in range(count):
                        slots.append({"category": category,
                            "options": [builder._humanize_proficiency_value(v, category=category) for v in options],
                            **({"condition": condition} if condition else {})})
        return fixed, [{**slot, "feature_index": index} for index, slot in enumerate(slots)]
    except (ValueError, TypeError, KeyError) as exc:
        if strict:
            raise builder.CharacterBuildError(str(exc)) from exc
        return {category: [] for category in FIELDS}, []


def automatic(entry):
    try:
        return entry.entry_type in {"classfeature", "subclassfeature"} and any(
            block == {ALL_TOOLS: True} for block in normalize_metadata(dict(entry.metadata or {})).get("expertise", []))
    except (ValueError, TypeError, KeyError):
        return False


def choice_fields(selections, values, *, item_catalog=None):
    from . import character_builder as builder
    fields = []
    for selection in selections:
        entry, owner = selection.get("entry"), selection.get("instance_key")
        if entry is None or not owner:
            continue
        _fixed, slots = contract(entry, item_catalog=item_catalog)
        for index, slot in enumerate(slots):
            family = f"grant_{slot['category']}_{index}"
            name = builder._feature_field_name(owner, family, 1)
            options = [{"label": value, "value": value} for value in slot["options"]]
            if slot.get("condition"):
                options.insert(0, {"label": "Gain " + slot["condition"] + " (not previously proficient)", "value": "__grant__"})
            fields.append({"name": name, "label": entry.title + " — " + slot["category"],
                "help_text": ("Choose another artisan tool only if already proficient in " + slot["condition"] + "."
                              if slot.get("condition") else "Choose the proficiency granted by this feature."),
                "options": options, "selected": values.get(name, ""),
                "group_key": builder._feature_group_key(owner, family), "kind": "feature_skill"})
    return fields


def native_grants(selections, choices, *, prior=None, item_catalog=None, strict=True):
    from .repository import normalize_lookup
    result = {category: [] for category in FIELDS}
    for selection in selections:
        entry, owner = selection.get("entry"), selection.get("instance_key")
        if entry is None or not owner:
            continue
        fixed, slots = contract(entry, item_catalog=item_catalog, strict=strict)
        selected_here = {category: set() for category in FIELDS}
        for category in FIELDS:
            result[category].extend(fixed[category])
        for index, slot in enumerate(slots):
            selected = choices.get(f"feature:{owner}:grant_{slot['category']}_{index}", [])
            value = selected[0] if type(selected) is list and len(selected) == 1 else None
            condition = slot.get("condition")
            previous = {normalize_lookup(v) for v in (prior or {}).get(slot["category"], [])}
            granted = {normalize_lookup(v) for v in fixed[slot["category"]]} | selected_here[slot["category"]]
            if (condition and value == "__grant__" and normalize_lookup(condition) not in previous
                    and normalize_lookup(condition) not in granted):
                result[slot["category"]].append(condition)
                selected_here[slot["category"]].add(normalize_lookup(condition))
            elif (value in slot["options"] and (not condition or normalize_lookup(condition) in previous)
                  and normalize_lookup(value) not in previous | granted):
                result[slot["category"]].append(value)
                selected_here[slot["category"]].add(normalize_lookup(value))
            elif strict:
                from .character_builder import CharacterBuildError
                raise CharacterBuildError("Confirm the exact feature proficiency choice and its prior acquisition condition.")
    return result


def automatic_history(definition):
    from .character_source_repair import SourceRepairError, _sha256_hex
    import json
    frame = definition.source.get("native_reconstruction_choices") or {}
    if type(frame) is not dict:
        raise SourceRepairError("Automatic expertise needs a typed reconstruction frame.")
    rows = frame.get(HISTORY, [])
    if type(rows) is not list or len(rows) > 32:
        raise SourceRepairError("Automatic expertise history is malformed.")
    owners = set()
    fields = {"owner_id", "class_row_id", "systems_ref", "source_digest", "prior_present", "prior_json"}
    for row in rows:
        if (type(row) is not dict or set(row) != fields or type(row["owner_id"]) is not str
                or not row["owner_id"] or row["owner_id"] in owners
                or type(row["class_row_id"]) is not str or not row["class_row_id"]
                or type(row["systems_ref"]) is not dict or type(row["prior_present"]) is not bool
                or type(row["prior_json"]) is not str or len(row["prior_json"]) > 32768
                or canonical(json.loads(row["prior_json"])) != row["prior_json"]
                or not _sha256_hex(row["source_digest"])):
            raise SourceRepairError("Automatic expertise requires an exact retained observation and source owner.")
        prior = json.loads(row["prior_json"])
        if prior is not None and (type(prior) is not list or len(prior) > 128
                or any(type(value) is not str or len(value) > 512 for value in prior)):
            raise SourceRepairError("Automatic expertise adoption needs a bounded original expertise list.")
        owners.add(row["owner_id"])
    return tuple(deepcopy(rows))


def automatic_fields(definition, service):
    from .character_reconstruction_proficiencies import current_owners
    from .character_builder_equipment import _systems_ref_from_entry
    from .character_profile import profile_class_rows
    previous = {r["owner_id"] for r in automatic_history(definition)}
    features = {r.get("id"): r for r in definition.features}
    from .character_reconstruction_authority import attained_reconstruction_feature_owners
    from .character_armor_models import structural_selectors
    attained = attained_reconstruction_feature_owners(definition, service,
        armor_selectors=structural_selectors(definition, service))
    result = []
    prior = definition.proficiencies.get("tool_expertise")
    if prior is not None and (type(prior) is not list or any(type(value) is not str for value in prior)):
        return result
    for owner, entry in current_owners(definition, service):
        if owner in previous or not automatic(entry) or owner not in features:
            continue
        owners = attained.get(entry.entry_key, ())
        row_id = features[owner].get("class_row_id") or (next(iter(owners)) if len(owners) == 1 else None)
        if not row_id or row_id not in owners:
            continue
        record = {"owner_id": owner, "class_row_id": row_id, "systems_ref": _systems_ref_from_entry(entry),
            "source_digest": digest({"metadata": entry.metadata, "body": entry.body}),
            "prior_present": "tool_expertise" in definition.proficiencies,
            "prior_json": canonical(definition.proficiencies.get("tool_expertise"))}
        result.append({"name": PREFIX + digest(owner)[:20], "label": entry.title,
            "options": [{"value": digest(record), "label": "Adopt automatic expertise for every qualified proficient tool", "record": record}]})
    return result


def compose_automatic(prior, payload, service, inputs):
    from .character_source_repair import SourceRepairError
    rows = list(automatic_history(prior))
    for field in automatic_fields(prior, service):
        value = inputs.get(field["name"], "keep")
        if value == "keep":
            continue
        record = field["options"][0]["record"]
        if value != digest(record):
            raise SourceRepairError("The automatic expertise source or retained observation changed.")
        rows.append(record)
    if rows:
        payload["source"]["native_reconstruction_choices"][HISTORY] = rows
        from .repository import normalize_lookup
        old = list(payload["proficiencies"].get("tool_expertise") or [])
        lookup = {normalize_lookup(value) for value in old}
        old += [value for value in payload["proficiencies"].get("tools", []) if normalize_lookup(value) not in lookup]
        payload["proficiencies"]["tool_expertise"] = old


def automatic_custody(definition, origin, rows):
    return (({"automatic_expertise_custody": {"campaign_slug": definition.campaign_slug,
        "character_slug": definition.character_slug, "action_id": origin["action_id"],
        "adoption_digest": digest(list(rows)), "adoptions": deepcopy(list(rows))}},) if rows else ())


def require_automatic_custody(definition, witnesses):
    import json
    from .character_source_repair import SourceRepairError
    rows = automatic_history(definition)
    if rows:
        origin = definition.source.get("native_reconstruction") or {}
        decoded = [json.loads(value) if isinstance(value, str) else value for value in witnesses]
        if (origin.get("automatic_expertise_digest") != digest(list(rows)) or not origin.get("action_id")
                or automatic_custody(definition, origin, rows)[0] not in decoded):
            raise SourceRepairError("Automatic expertise needs independently recovered adoption custody.")
    return rows


def validate_automatic(prior, candidate, service=None, *, witnesses=(), draft=False):
    from .character_source_repair import SourceRepairError
    old, rows = automatic_history(prior), automatic_history(candidate)
    if rows[:len(old)] != old:
        raise SourceRepairError("Automatic expertise adoption history cannot be replaced or dropped.")
    if not rows:
        return rows
    if old and not draft:
        require_automatic_custody(prior, witnesses)
    inputs = (candidate.source.get("native_reconstruction_choices") or {}).get("inputs", {})
    for row in rows[len(old):]:
        if (row["prior_present"] != ("tool_expertise" in prior.proficiencies)
                or row["prior_json"] != canonical(prior.proficiencies.get("tool_expertise"))
                or inputs.get(PREFIX + digest(row["owner_id"])[:20]) != digest(row)):
            raise SourceRepairError("Automatic expertise lacks its original observation and explicit confirmation.")
    if service is not None:
        from .character_reconstruction_proficiencies import current_owners
        from .character_reconstruction_authority import attained_reconstruction_feature_owners
        from .character_armor_models import structural_selectors
        attained = attained_reconstruction_feature_owners(candidate, service,
            armor_selectors=structural_selectors(candidate, service))
        owners = dict(current_owners(candidate, service))
        for row in rows:
            entry = owners.get(row["owner_id"])
            if (entry is None or not automatic(entry)
                    or row["class_row_id"] not in attained.get(entry.entry_key, ())
                    or not any(feature.get("id") == row["owner_id"] and
                               feature.get("class_row_id") in (None, "", row["class_row_id"]) for feature in candidate.features)
                    or digest({"metadata": entry.metadata, "body": entry.body}) != row["source_digest"]
                    or any(row["systems_ref"].get(k) != getattr(entry, k, None) for k in ("entry_key", "source_id", "entry_type", "slug"))):
                raise SourceRepairError("Automatic expertise no longer matches the current source declaration.")
    return rows


def validate_automatic_transition(prior_record, candidate, proof=None, *, actor_id=None, state=None):
    from .character_reconstruction_authority import PendingNativeReconstruction
    from .character_source_repair import SourceRepairError
    if automatic_history(prior_record.definition) == automatic_history(candidate):
        return
    if type(proof) is not PendingNativeReconstruction or proof.automatic_expertise != automatic_history(candidate):
        raise SourceRepairError("Automatic expertise adoption changes require exact reconstruction review.")
    proof.validate_binding(prior_record, candidate, state, actor_id)


def native_frame(selections, choices, prior, class_row_id, previous=()):
    from .character_builder_equipment import _systems_ref_from_entry
    rows = deepcopy(list(previous))
    identities = {(r["systems_ref"]["entry_key"], r["class_row_id"]) for r in rows}
    for selection in selections:
        entry, owner = selection.get("entry"), selection.get("instance_key")
        if entry is None or entry.entry_type not in {"classfeature", "subclassfeature"}:
            continue
        fixed, slots = contract(entry)
        if not any(fixed.values()) and not slots and not automatic(entry):
            continue
        identity = entry.entry_key, class_row_id
        if identity in identities:
            continue
        rows.append({"systems_ref": _systems_ref_from_entry(entry), "class_row_id": class_row_id,
            "owner_id": owner, "prior": deepcopy(prior),
            "choices": {key: deepcopy(value) for key, value in choices.items() if key.startswith(f"feature:{owner}:grant_")},
            "source_digest": digest({"metadata": entry.metadata, "body": entry.body})})
        identities.add(identity)
    return rows


def current_native_selections(definition, service, *, authority=None):
    """Consume attained feature identities, never a title-based expertise alias."""
    from .character_reconstruction_authority import attained_reconstruction_feature_owners
    from .character_armor_models import structural_selectors
    attained = (attained_reconstruction_feature_owners(definition, service,
        armor_selectors=structural_selectors(definition, service)) if authority is None else {})
    result = []
    for feature in definition.features:
        ref = feature.get("systems_ref") if type(feature) is dict else None
        if type(ref) is not dict or not ref.get("entry_key"):
            continue
        if authority is not None and authority.status_for("feature", feature.get("id")) != "VERIFIED":
            continue
        if authority is None and feature.get("class_row_id") not in attained.get(ref["entry_key"], ()):
            continue
        entry = service.get_entry_for_campaign(definition.campaign_slug, ref["entry_key"])
        if entry is not None and entry.entry_type in {"classfeature", "subclassfeature"} and all(
                ref.get(k) == getattr(entry, k, None) for k in ("entry_key", "source_id", "entry_type", "slug")):
            result.append({"entry": entry, "instance_key": feature["id"]})
    return result


def native_records_for_owner(definition, owner, entry):
    features = [r for r in definition.features if r.get("id") == owner]
    if len(features) != 1:
        return []
    feature = features[0]
    return [r for r in definition.source.get("native_feature_proficiency_choices", [])
            if type(r) is dict and r.get("systems_ref") == feature.get("systems_ref")
            and r.get("class_row_id") == feature.get("class_row_id")
            and r.get("source_digest") == digest({"metadata": entry.metadata, "body": entry.body})]


def retained_native_grants(definition, service):
    """Validate saved decisions; publication witnesses still supply authority."""
    from .character_source_repair import SourceRepairError
    from . import character_builder as builder
    from .character_read_foundation import read_item_catalog_for_definition
    catalog = read_item_catalog_for_definition(definition, systems_service=service, campaign_page_records=[])
    selections = current_native_selections(definition, service)
    by_key = {row["entry"].entry_key: row["entry"] for row in selections}
    frames = definition.source.get("native_feature_proficiency_choices", [])
    if type(frames) is not list or len(frames) > 128:
        raise SourceRepairError("Native feature proficiency acquisition is malformed.")
    result = {category: [] for category in FIELDS}
    seen = set()
    for row in frames:
        if type(row) is not dict or set(row) != {"systems_ref", "class_row_id", "owner_id", "prior", "choices", "source_digest"}:
            raise SourceRepairError("Native feature proficiency acquisition lacks its original input frame.")
        ref = row["systems_ref"]
        entry = by_key.get(ref.get("entry_key")) if type(ref) is dict else None
        identity = ref.get("entry_key"), row["class_row_id"]
        if (entry is None or identity in seen or type(row["prior"]) is not dict or type(row["choices"]) is not dict
                or digest({"metadata": entry.metadata, "body": entry.body}) != row["source_digest"]
                or not any(feature.get("class_row_id") == row["class_row_id"] and
                           dict(feature.get("systems_ref") or {}).get("entry_key") == entry.entry_key for feature in definition.features)):
            raise SourceRepairError("Native feature proficiency acquisition has no current exact member.")
        grants = native_grants([{"entry": entry, "instance_key": row["owner_id"]}], row["choices"], prior=row["prior"], item_catalog=catalog)
        for category in FIELDS:
            result[category].extend(grants[category])
        seen.add(identity)
    # Older native fixed grants do not need a fabricated choice record.
    for selection in selections:
        entry = selection["entry"]
        if any(key == entry.entry_key for key, _row_id in seen):
            continue
        fixed, slots = contract(entry, item_catalog=catalog)
        if slots:
            continue
        for category in FIELDS:
            result[category].extend(fixed[category])
    return result, selections


def conditional_history(definition):
    import json
    from .character_source_repair import SourceRepairError, _sha256_hex
    frame = definition.source.get("native_reconstruction_choices") or {}
    if type(frame) is not dict:
        raise SourceRepairError("Conditional proficiency needs a typed reconstruction frame.")
    rows = frame.get(CONDITIONS, [])
    if type(rows) is not list or len(rows) > 64:
        raise SourceRepairError("Conditional proficiency history is malformed.")
    seen = set()
    for row in rows:
        if (type(row) is not dict or set(row) != {"owner_id", "position", "class_row_id", "systems_ref", "source_digest", "condition", "selected", "prior_proficiencies_json", "prior_owners"}
                or type(row["owner_id"]) is not str or type(row["class_row_id"]) is not str or not row["class_row_id"] or type(row["position"]) is not int
                or not 0 <= row["position"] < 64 or type(row["systems_ref"]) is not dict
                or type(row["prior_owners"]) is not list or len(row["prior_owners"]) > 128
                or any(type(row[key]) is not str for key in ("source_digest", "condition", "selected", "prior_proficiencies_json"))
                or (row["owner_id"], row["position"]) in seen):
            raise SourceRepairError("Conditional proficiency history lacks an exact acquisition branch.")
        seen.add((row["owner_id"], row["position"]))
        if (not _sha256_hex(row["source_digest"]) or len(row["prior_proficiencies_json"]) > 65536
                or type(json.loads(row["prior_proficiencies_json"])) is not dict
                or canonical(json.loads(row["prior_proficiencies_json"])) != row["prior_proficiencies_json"]):
            raise SourceRepairError("Conditional proficiency lost its exact prior observation.")
        for owner in row["prior_owners"]:
            if (type(owner) is not dict or set(owner) != {"owner_id", "systems_ref", "source_digest", "tools", "chronology"}
                    or type(owner["owner_id"]) is not str or not owner["owner_id"]
                    or type(owner["systems_ref"]) is not dict or not _sha256_hex(owner["source_digest"])
                    or type(owner["tools"]) is not list or len(owner["tools"]) > 128
                    or any(type(name) is not str or not 0 < len(name) <= 160 for name in owner["tools"])
                    or owner["chronology"] not in {"starting_parent", "earlier_class_feature"}):
                raise SourceRepairError("Conditional proficiency has malformed prior source evidence.")
    return tuple(deepcopy(rows))


def conditional_custody(definition, origin, rows):
    return (({"feature_proficiency_condition_custody": {"campaign_slug": definition.campaign_slug,
        "character_slug": definition.character_slug, "action_id": origin["action_id"],
        "condition_digest": digest(list(rows)), "conditions": deepcopy(list(rows))}},) if rows else ())


def require_conditional_custody(definition, witnesses):
    import json
    from .character_source_repair import SourceRepairError
    rows = conditional_history(definition)
    if rows:
        origin = definition.source.get("native_reconstruction") or {}
        decoded = [json.loads(v) if isinstance(v, str) else v for v in witnesses]
        if (origin.get("feature_proficiency_condition_digest") != digest(list(rows)) or not origin.get("action_id")
                or conditional_custody(definition, origin, rows)[0] not in decoded):
            raise SourceRepairError("Conditional proficiency requires independently recovered acquisition custody.")
    return rows


def conditional_candidates(prior, candidate, service, *, skip=()):
    from .character_reconstruction_proficiencies import current_owners, grant_contract
    from .character_builder_equipment import _systems_ref_from_entry
    from .repository import normalize_lookup
    from .character_source_repair import SourceRepairError
    owners = current_owners(candidate, service)
    entries = dict(owners)
    from .character_reconstruction_authority import attained_reconstruction_feature_owners
    from .character_armor_models import structural_selectors
    attained = attained_reconstruction_feature_owners(candidate, service, armor_selectors=structural_selectors(candidate, service))
    from . import character_builder as builder
    from .character_read_foundation import read_item_catalog_for_definition
    catalog = read_item_catalog_for_definition(candidate, systems_service=service, campaign_page_records=[])
    _fixed, slots = grant_contract(candidate, owners, item_catalog=catalog)
    choices = candidate.source["native_reconstruction_choices"]["choices"]
    counts, candidates = {}, []
    for slot in slots:
        group = slot["owner"], slot["category"]
        position = counts.get(group, 0)
        counts[group] = position + 1
        if not slot.get("condition"):
            continue
        if (slot["owner"], position) in skip:
            continue
        selected = choices.get(f"reconstruction:{slot['owner']}:{slot['category']}", [])
        selected = selected[position] if type(selected) is list and len(selected) > position else ""
        if str(selected).startswith("__unresolved_"):
            continue
        if selected != "__grant__" and selected not in slot["options"]:
            raise SourceRepairError("Conditional proficiency needs an exact supported branch.")
        entry = entries[slot["owner"]]
        feature = next((r for r in candidate.features if r.get("id") == slot["owner"]), {})
        class_owners = attained.get(entry.entry_key, ())
        row_id = feature.get("class_row_id") or (next(iter(class_owners)) if len(class_owners) == 1 else None)
        if row_id not in class_owners:
            raise SourceRepairError("Conditional proficiency needs an exact attained class owner.")
        evidence = []
        for owner, source in owners:
            if owner == slot["owner"]:
                continue
            # Current possession alone is not acquisition chronology. Starting
            # parents and strictly earlier attained members of this same class
            # are the bounded historical cases supported here.
            earlier = owner in {"class", "species", "background"}
            source_level = source.metadata.get("level")
            target_level = entry.metadata.get("level")
            if not earlier and source.entry_type in {"classfeature", "subclassfeature"}:
                other = next((r for r in candidate.features if r.get("id") == owner), {})
                earlier = (type(source_level) is int and type(target_level) is int and 1 <= source_level < target_level
                    and row_id in attained.get(source.entry_key, ())
                    and other.get("class_row_id") in (None, "", row_id))
            if not earlier:
                continue
            other_fixed, other_slots = grant_contract(candidate, [(owner, source)], item_catalog=catalog)
            names = list(other_fixed["tools"])
            selected_tools = choices.get(f"reconstruction:{owner}:tools", [])
            tool_slots = [s for s in other_slots if s["category"] == "tools"]
            for index, other in enumerate(tool_slots):
                if not other.get("condition") and index < len(selected_tools) and selected_tools[index] in other["options"]:
                    names.append(selected_tools[index])
            if normalize_lookup(slot["condition"]) in {normalize_lookup(v) for v in names}:
                evidence.append({"owner_id": owner, "systems_ref": _systems_ref_from_entry(source),
                    "source_digest": digest({"metadata": source.metadata, "body": source.body}), "tools": names,
                    "chronology": "starting_parent" if owner in {"class", "species", "background"} else "earlier_class_feature"})
        prior_tools = {normalize_lookup(v) for v in prior.proficiencies.get("tools", [])}
        if selected != "__grant__" and (not evidence or normalize_lookup(slot["condition"]) not in prior_tools
                or normalize_lookup(selected) not in prior_tools or normalize_lookup(selected) == normalize_lookup(slot["condition"])):
            raise SourceRepairError("Confirm a retained replacement tool and an independently owned prior prerequisite; otherwise leave this branch unresolved.")
        if selected == "__grant__" and evidence:
            raise SourceRepairError("Another retained source already grants this tool; confirm the replacement branch or leave it unresolved.")
        candidates.append({"owner_id": slot["owner"], "position": position, "class_row_id": row_id, "systems_ref": _systems_ref_from_entry(entry),
            "source_digest": digest({"metadata": entry.metadata, "body": entry.body}), "condition": slot["condition"],
            "selected": selected, "prior_proficiencies_json": canonical(prior.proficiencies), "prior_owners": evidence})
    return candidates


def compose_conditions(prior, payload, service):
    from .character_models import CharacterDefinition
    old = list(conditional_history(prior))
    prior_keys = {(r["owner_id"], r["position"]) for r in old}
    candidates = conditional_candidates(prior, CharacterDefinition.from_dict(payload), service, skip=prior_keys)
    rows = old + [row for row in candidates if (row["owner_id"], row["position"]) not in prior_keys]
    if rows:
        payload["source"]["native_reconstruction_choices"][CONDITIONS] = rows


def validate_conditions(prior, candidate, service=None, *, witnesses=(), draft=False, owners=None, slots=None):
    from .character_source_repair import SourceRepairError
    old, rows = conditional_history(prior), conditional_history(candidate)
    if rows[:len(old)] != old:
        raise SourceRepairError("Conditional proficiency history cannot change or disappear.")
    if not rows and (service is None or slots is not None and not any(slot.get("condition") for slot in slots)):
        return rows
    if old and not draft:
        require_conditional_custody(prior, witnesses)
    choices = (candidate.source.get("native_reconstruction_choices") or {}).get("choices", {})
    for row in rows:
        selected = choices.get(f"reconstruction:{row['owner_id']}:tools", [])
        if type(selected) is not list or len(selected) <= row["position"] or selected[row["position"]] != row["selected"]:
            raise SourceRepairError("Retained conditional acquisition no longer matches its selected branch.")
    for row in rows[len(old):]:
        if row["prior_proficiencies_json"] != canonical(prior.proficiencies):
            raise SourceRepairError("Conditional proficiency lost its prior observation.")
    if service is not None:
        from .character_reconstruction_proficiencies import current_owners, grant_contract
        from .character_reconstruction_authority import attained_reconstruction_feature_owners
        from .character_armor_models import structural_selectors
        attained = attained_reconstruction_feature_owners(candidate, service,
            armor_selectors=structural_selectors(candidate, service))
        owners = dict(current_owners(candidate, service) if owners is None else owners)
        from . import character_builder as builder
        from .character_read_foundation import read_item_catalog_for_definition
        catalog = read_item_catalog_for_definition(candidate, systems_service=service, campaign_page_records=[])
        if slots is None:
            _fixed, slots = grant_contract(candidate, list(owners.items()), item_catalog=catalog)
        counts, contracts = {}, {}
        for slot in slots:
            key = slot["owner"], slot["category"]
            position = counts.get(key, 0)
            counts[key] = position + 1
            if slot.get("condition"):
                contracts[(slot["owner"], position)] = slot
                selected = choices.get(f"reconstruction:{slot['owner']}:tools", [])
                if (position < len(selected) and not str(selected[position]).startswith("__unresolved_")
                        and not any(r["owner_id"] == slot["owner"] and r["position"] == position for r in rows)):
                    native = native_records_for_owner(candidate, slot["owner"], owners[slot["owner"]])
                    if len(native) != 1 or native[0].get("choices", {}).get(
                            f"feature:{native[0]['owner_id']}:grant_tools_{slot['feature_index']}") != [selected[position]]:
                        raise SourceRepairError("A resolved conditional tool slot needs its explicit acquisition history.")
                    native_grants([{"entry": owners[slot["owner"]], "instance_key": native[0]["owner_id"]}],
                        native[0]["choices"], prior=native[0]["prior"], item_catalog=catalog)
        for row in rows:
            entry = owners.get(row["owner_id"])
            slot = contracts.get((row["owner_id"], row["position"]))
            if (entry is None or digest({"metadata": entry.metadata, "body": entry.body}) != row["source_digest"]
                    or row["class_row_id"] not in attained.get(entry.entry_key, ())
                    or slot is None or slot["condition"] != row["condition"]
                    or row["selected"] != "__grant__" and row["selected"] not in slot["options"]
                    or any(row["systems_ref"].get(k) != getattr(entry, k, None) for k in ("entry_key", "source_id", "entry_type", "slug"))):
                raise SourceRepairError("Conditional proficiency source changed.")
        expected = conditional_candidates(prior, candidate, service,
            skip={(r["owner_id"], r["position"]) for r in old}) if len(rows) > len(old) else []
        if any(row not in expected for row in rows[len(old):]):
            raise SourceRepairError("Conditional proficiency lacks its independent prior source evidence.")
    return rows


class _Prepared:
    def __init__(self, definition, *, issuer):
        if issuer is not _PREPARED:
            raise ValueError("Feature grant preparation requires reconstruction.")
        self.definition_digest = digest(definition.to_dict())


def prepare_reconstruction(prior, candidate, service):
    validate_automatic(prior, candidate, service, draft=True)
    validate_conditions(prior, candidate, service, draft=True)
    return _Prepared(candidate, issuer=_PREPARED)


def resolve_reconstruction(definition, service, witnesses, *, prepared=None, owners=None, slots=None):
    is_draft = type(prepared) is _Prepared and prepared.definition_digest == digest(definition.to_dict())
    if not is_draft:
        require_automatic_custody(definition, witnesses)
        require_conditional_custody(definition, witnesses)
    validate_automatic(definition, definition, service, draft=True)
    validate_conditions(definition, definition, service, draft=True, owners=owners, slots=slots)


def validate_condition_transition(prior_record, candidate, proof=None, *, actor_id=None, state=None):
    from .character_reconstruction_authority import PendingNativeReconstruction
    from .character_source_repair import SourceRepairError
    if conditional_history(prior_record.definition) == conditional_history(candidate):
        return
    if type(proof) is not PendingNativeReconstruction or proof.proficiency_conditions != conditional_history(candidate):
        raise SourceRepairError("Conditional proficiency changes require exact reconstruction review.")
    proof.validate_binding(prior_record, candidate, state, actor_id)


def validate_native_transition(prior_record, candidate, proof=None):
    """Acquisition preimages may grow only in the existing sealed native advance."""
    from .character_reconciliation import PendingNativeLevelUpAuthority
    from .character_equipment_activation import definition_digest
    from .character_source_repair import SourceRepairError
    from .character_language_choices import PARENT_FRAME
    before, after = prior_record.definition.source, candidate.source
    if (PARENT_FRAME in before) != (PARENT_FRAME in after) or before.get(PARENT_FRAME) != after.get(PARENT_FRAME):
        raise SourceRepairError("Native parent language acquisition choices cannot change.")
    old = prior_record.definition.source.get("native_feature_proficiency_choices", [])
    new = candidate.source.get("native_feature_proficiency_choices", [])
    if old == new:
        return
    if (type(old) is not list or type(new) is not list or new[:len(old)] != old
            or type(proof) is not PendingNativeLevelUpAuthority
            or proof.prior_definition_digest != definition_digest(prior_record.definition)
            or proof.candidate_definition_digest != definition_digest(candidate)):
        raise SourceRepairError("Native feature acquisition changes require the exact native advancement proof.")


def native_custody(definition, records):
    return {"native_feature_proficiency_custody": {"campaign_slug": definition.campaign_slug,
        "character_slug": definition.character_slug, "acquisition_digest": digest(records),
        "acquisitions": deepcopy(records)}}


def recovered_native_custody(connection, definition, aliases, audit_row, metadata, prior_witnesses):
    """Extend the existing native audit/generation join, without a new ledger."""
    from .character_models import CharacterDefinition
    from .character_native_requalification import _generation
    from .committed_source_store import _decode_mapping
    records = definition.source.get("native_feature_proficiency_choices", [])
    if not records or type(records) is not list or len(records) > 128:
        return ()
    event = audit_row["event_type"]
    if event not in {"character_native_created", "character_native_leveled"}:
        return ()
    decoded = [json.loads(v) if isinstance(v, str) else v for v in prior_witnesses]
    for revision, _file_digest in aliases:
        try:
            if event == "character_native_created":
                if revision != 1:
                    continue
                old, prior = [], None
            else:
                raw = connection.execute("SELECT primary_bytes,actor_user_id FROM committed_source_generations "
                    "WHERE campaign_slug=? AND object_kind='character' AND object_ref=? AND revision=? AND tombstone=0",
                    (definition.campaign_slug, definition.character_slug, revision - 1)).fetchone()
                if raw is None:
                    continue
                original = CharacterDefinition.from_dict(_decode_mapping(raw["primary_bytes"]))
                payload, _ = _generation(connection, definition.campaign_slug, definition.character_slug,
                    digest(original.to_dict()), raw["actor_user_id"], revision=revision - 1)
                prior = CharacterDefinition.from_dict(payload)
                old = prior.source.get("native_feature_proficiency_choices", [])
                if type(old) is not list or records[:len(old)] != old:
                    continue
                if old and native_custody(prior, old) not in decoded:
                    continue
            for row in records[len(old):]:
                if (type(row) is not dict or set(row) != {"systems_ref", "class_row_id", "owner_id", "prior", "choices", "source_digest"}
                        or type(row["prior"]) is not dict or type(row["choices"]) is not dict
                        or type(row["systems_ref"]) is not dict or type(row["source_digest"]) is not str
                        or len(row["source_digest"]) != 64):
                    raise ValueError("Malformed native feature acquisition")
                matching = [f for f in definition.features if f.get("systems_ref") == row["systems_ref"]
                            and f.get("class_row_id") == row["class_row_id"]]
                if len(matching) != 1:
                    raise ValueError("Native acquisition lost its exact feature/class member")
                if prior is not None:
                    if row["prior"] != prior.proficiencies:
                        raise ValueError("Native acquisition changed its actual prior proficiency frame")
                else:
                    # The genuine initial generation contains every baseline
                    # proficiency used before applying these feature grants.
                    observed = {**definition.proficiencies, "skills": [r["name"] for r in definition.skills
                        if r.get("proficiency_level") in {"proficient", "expertise"}]}
                    from .repository import normalize_lookup
                    if any(category not in observed or type(names) is not list
                           or any(type(name) is not str for name in names)
                           or not {normalize_lookup(name) for name in names} <=
                                  {normalize_lookup(name) for name in observed[category]}
                           for category, names in row["prior"].items()):
                        raise ValueError("Native initial acquisition has no matching baseline observations")
            return (native_custody(definition, records),)
        except (ValueError, TypeError, KeyError):
            continue
    return ()


def project_automatic_expertise(authority, definition, service, witnesses, attained):
    """Derive read-only expertise from a witnessed rule and qualified tools."""
    from dataclasses import replace
    from .character_source_authority import EffectiveStatus, VERIFIED
    from .character_source_repair import SourceRepairError
    reconstructed = isinstance(definition.source.get("native_reconstruction_choices"), dict)
    try:
        records = []
        if reconstructed:
            records.extend((row, False) for row in require_automatic_custody(definition, witnesses))
        # Creation/advancement custody joins the actual generation and prior
        # acquisition frame. Later tool grants need not recreate that history.
        acquisition_rows = definition.source.get("native_feature_proficiency_choices", [])
        recovered = any(w == native_custody(definition, acquisition_rows) for w in witnesses) if acquisition_rows else False
        if recovered:
            records.extend((row, True) for row in definition.source.get("native_feature_proficiency_choices", []))
        owners = []
        for record, native_record in records:
            ref = record["systems_ref"]
            entry = service.get_entry_for_campaign(definition.campaign_slug, ref["entry_key"])
            matches = [row for row in definition.features if row.get("systems_ref") == ref
                       and (row.get("id") == record["owner_id"] if not native_record
                            else row.get("class_row_id") == record["class_row_id"])]
            if (entry is None or not automatic(entry) or len(matches) != 1
                    or record["class_row_id"] not in authority.verified_class_rows
                    or record["class_row_id"] not in attained.get(entry.entry_key, ())
                    or authority.status_for("feature", matches[0]["id"]) != VERIFIED
                    or digest({"metadata": entry.metadata, "body": entry.body}) != record["source_digest"]):
                continue
            owners.append(record)
        if not owners:
            return authority
    except (SourceRepairError, TypeError, KeyError, ValueError):
        return authority
    statuses = {row.path: row for row in authority.field_statuses}
    observed = definition.proficiencies.get("tool_expertise")
    raw = {str(value).casefold(): value for value in observed} if type(observed) is list else {}
    tools = definition.proficiencies.get("tools")
    for tool in tools if type(tools) is list else []:
        if type(tool) is not str:
            continue
        proficiency = authority.field_status("proficiencies.tools." + tool.casefold())
        path = "proficiencies.tool_expertise." + tool.casefold()
        if proficiency.is_effective and not authority.field_status(path).is_effective:
            statuses[path] = EffectiveStatus(path, VERIFIED, raw.get(tool.casefold()), tool, "automatic_tool_expertise")
    return replace(authority, field_statuses=tuple(statuses.values()))


# Finite ordinary callback surface omitted by invocation-owned current inputs.
_CURRENT_INPUT_RECIPE = tuple((name, globals()[name]) for name in (
    'gaming_set_options',
    'resolve_reconstruction',
    'automatic',
    'automatic_history',
    'conditional_history',
    'native_records_for_owner',
    'contract',
))
