"""Exact current Armor Model choices; historical rows and play state stay intact.

Only reconstruction can author this selection. Serialized intent is not custody;
the existing confirmed reconstruction audit supplies its independent witness.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

from .character_source_repair import SourceRepairError

CLASS = "dnd-5e|class|tce|artificer"
SUBCLASS = "dnd-5e|subclass|tce|armorer-artificer-tce"
PREFIX = "dnd-5e|subclassfeature|tce|"
SUFFIX = "-artificer-tce-armorer-tce-3"
MODEL = PREFIX + "armormodel" + SUFFIX
ARCANE = PREFIX + "arcanearmor" + SUFFIX
GAUNTLETS = PREFIX + "thundergauntlets" + SUFFIX
FIELD = PREFIX + "defensivefield" + SUFFIX
SUMMARY = PREFIX + "guardian-artificer-tce-armorer-tce-15"
INFILTRATOR_ENHANCEMENT = PREFIX + "infiltrator-artificer-tce-armorer-tce-15"
CHILDREN = (GAUNTLETS, FIELD)
GUARDIAN_MEMBERS = frozenset((*CHILDREN, SUMMARY))
ELECTIVE_CHILDREN = frozenset((*CHILDREN, SUMMARY, INFILTRATOR_ENHANCEMENT, *(PREFIX + name + SUFFIX for name in
    ("lightninglauncher", "poweredsteps", "dampeningfield"))))
PATH = ("entries", 4, "entries", 0)
FRAME_KEY = "armor_model_choices"
CHOICE_FIELD = "feature_armor_model"
SUMMARY_FIELD = "feature_armor_model_summary"
UNRESOLVED = "__unresolved_armor_model__"
# Bounded source adapters recognize these exact published rules, not a label.
# A changed rule remains visible but cannot silently reuse this implementation.
RULE_HASHES = {
    MODEL: "ef6b098b09c7f3fe241b295b15e3d3458606636458fab5440321b87b16445d51",
    ARCANE: "9bc56feb38585b1903c159c9aec256488c307ce21ab66b10888c913818d20f6e",
    GAUNTLETS: "2ea068440ea58253773555ad98cc27437aa021abbc480eb983a48b7d569153a6",
    FIELD: "8243e43e24de3486f676b8bf26c5288e4fc0953bc6b00865e2b60121e7a522db",
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def supported_rule(entry):
    if entry is None or entry.entry_key not in RULE_HASHES or entry.entry_type != "subclassfeature":
        return False
    metadata = entry.metadata
    return (type(metadata) is dict and set(metadata) == {"class_name", "class_source", "subclass_name", "subclass_source", "level"}
        and all(metadata.get(key) == value for key, value in {
        "class_name": "Artificer", "class_source": "TCE", "subclass_name": "Armorer",
        "subclass_source": "TCE", "level": 3}.items())
        and type(metadata.get("level")) is int
        and sha256(json.dumps(entry.body, sort_keys=True, allow_nan=False).encode()).hexdigest()
        == RULE_HASHES[entry.entry_key])


def model_member_allowed(entry, selected_feature_branches=None):
    """One disposition for source walks and native feature generators.

    Unselected catalogs may display these entries, but cannot call them grants.
    Only the authenticated attained collector supplies a selected branch.
    """
    key = getattr(entry, "entry_key", None)
    return (key not in ELECTIVE_CHILDREN or
            (key in GUARDIAN_MEMBERS and (selected_feature_branches or {}).get(MODEL) == list(PATH)))


def _entry(definition, service, key):
    entry = service.get_entry_for_campaign(definition.campaign_slug, key)
    enabled = getattr(service, "is_entry_enabled_for_campaign", None)
    if entry is None or not callable(enabled) or not enabled(definition.campaign_slug, entry):
        return None
    return entry


def current_contract(definition, service):
    from .character_profile import profile_class_rows
    from .character_builder_equipment import _systems_ref_from_entry
    rows = [row for row in profile_class_rows(definition.profile)
            if dict(row.get("systems_ref") or {}).get("entry_key") == CLASS
            and dict(row.get("subclass_ref") or {}).get("entry_key") == SUBCLASS]
    if len(rows) != 1 or type(rows[0].get("level")) is not int or not 3 <= rows[0]["level"] <= 20:
        return None
    row = rows[0]
    cls, sub = _entry(definition, service, CLASS), _entry(definition, service, SUBCLASS)
    if (cls is None or sub is None or row.get("systems_ref") != _systems_ref_from_entry(cls)
            or row.get("subclass_ref") != _systems_ref_from_entry(sub)
            or sub.metadata.get("class_name") != cls.title or sub.metadata.get("class_source") != cls.source_id):
        return None
    rules = [_entry(definition, service, key) for key in (MODEL, ARCANE, *CHILDREN)]
    if not all(supported_rule(entry) for entry in rules):
        return None
    return {"schema_version": 1, "class_row_id": row["row_id"],
        "class_ref": _systems_ref_from_entry(cls), "subclass_ref": _systems_ref_from_entry(sub),
        "systems_ref": _systems_ref_from_entry(rules[0]), "branch_path": list(PATH),
        "contract_digest": digest([{"key": entry.entry_key, "metadata": entry.metadata,
                                     "body": entry.body} for entry in rules]),
        "children": list(CHILDREN)}


def _summary(row):
    allowed = {"id", "name", "category", "source", "description_markdown", "activation_type",
               "tracker_ref", "systems_ref", "class_row_id"}
    return (type(row) is dict and type(row.get("id")) is str and bool(row["id"])
        and dict(row.get("systems_ref") or {}).get("entry_key") == SUMMARY
        and row.get("activation_type") in (None, "", "passive") and not row.get("tracker_ref")
        and all(value in (None, "", [], {}) for key, value in row.items() if key not in allowed))


def choice_fields(definition, service, values):
    contract = current_contract(definition, service)
    if contract is None:
        return []
    summaries = [row for row in definition.features if _summary(row)
                 and row.get("class_row_id") in (None, "", contract["class_row_id"])]
    return [{"name": CHOICE_FIELD, "label": "Retained Armor Model", "kind": "armor_model",
        "help_text": "Confirm the current source branch; this does not change armor or perform a rest.",
        "group_key": "armor_model:selection", "selected": values.get(CHOICE_FIELD, UNRESOLVED),
        "options": [{"label": "Unresolved; no model benefit", "value": UNRESOLVED},
                    {"label": "Guardian — TCE Armor Model (level 3)", "value": digest(contract)}]},
        {"name": SUMMARY_FIELD, "label": "Historical model summary", "kind": "armor_model",
         "help_text": "Associate the exact historical row without changing its content or granting its level 15 citation.",
         "group_key": "armor_model:summary", "selected": values.get(SUMMARY_FIELD, UNRESOLVED),
         "options": [{"label": "No historical summary association", "value": UNRESOLVED},
                     *[{"label": str(row.get("name") or "Summary") + " (" + row["id"] + ")",
                        "value": row["id"]} for row in summaries]]}]


def compose(definition, service, values):
    contract = current_contract(definition, service)
    selected = values.get(CHOICE_FIELD, UNRESOLVED)
    if selected == UNRESOLVED:
        if values.get(SUMMARY_FIELD, UNRESOLVED) != UNRESOLVED or stored(definition):
            raise SourceRepairError("Retain the authenticated Armor Model before associating its summary.")
        return []
    if contract is None or selected != digest(contract):
        raise SourceRepairError("Confirm one exact current Armor Model branch.")
    identity = values.get(SUMMARY_FIELD, UNRESOLVED)
    rows = [row for row in definition.features if row.get("id") == identity]
    if identity != UNRESOLVED and (len(rows) != 1 or not _summary(rows[0])
            or rows[0].get("class_row_id") not in (None, "", contract["class_row_id"])):
        raise SourceRepairError("The historical model summary is ambiguous or has independent mechanics.")
    result = [{**contract, "summary_id": "" if identity == UNRESOLVED else identity,
               "prior_feature_json": "" if identity == UNRESOLVED else canonical(rows[0])}]
    if stored(definition) and stored(definition) != tuple(result):
        raise SourceRepairError("Reconstruction cannot switch a retained Armor Model.")
    return result


def stored(definition):
    frame = definition.source.get("native_reconstruction_choices") or {}
    if type(frame) is not dict:
        raise SourceRepairError("Armor Model choices require a typed reconstruction frame.")
    rows = frame.get(FRAME_KEY, [])
    fields = {"schema_version", "class_row_id", "class_ref", "subclass_ref", "systems_ref",
              "branch_path", "contract_digest", "children", "summary_id", "prior_feature_json"}
    if type(rows) is not list or len(rows) > 1:
        raise SourceRepairError("Armor Model evidence has an unsupported shape.")
    for row in rows:
        if (type(row) is not dict or set(row) != fields or type(row["schema_version"]) is not int
                or row["schema_version"] != 1 or row["branch_path"] != list(PATH)
                or row["children"] != list(CHILDREN) or type(row["class_row_id"]) is not str
                or not row["class_row_id"] or type(row["contract_digest"]) is not str
                or len(row["contract_digest"]) != 64 or type(row["summary_id"]) is not str
                or type(row["prior_feature_json"]) is not str):
            raise SourceRepairError("Armor Model evidence is malformed.")
        for field, key in (("class_ref", CLASS), ("subclass_ref", SUBCLASS), ("systems_ref", MODEL)):
            if type(row[field]) is not dict or row[field].get("entry_key") != key:
                raise SourceRepairError("Armor Model evidence has a different source owner.")
        contract = {key: value for key, value in row.items() if key not in {"summary_id", "prior_feature_json"}}
        inputs = frame.get("inputs") or {}
        if (inputs.get(CHOICE_FIELD) != digest(contract)
                or inputs.get(SUMMARY_FIELD, UNRESOLVED) != (row["summary_id"] or UNRESOLVED)):
            raise SourceRepairError("Armor Model evidence lacks its explicit choice.")
        matches = [feature for feature in definition.features if feature.get("id") == row["summary_id"]]
        if row["summary_id"]:
            if len(matches) != 1 or not _summary(matches[0]) or canonical(matches[0]) != row["prior_feature_json"]:
                raise SourceRepairError("Armor Model history changed.")
        elif row["prior_feature_json"]:
            raise SourceRepairError("Armor Model history has no exact owner.")
    return tuple(deepcopy(rows))


def validate(prior, candidate, service=None):
    rows = stored(candidate)
    old = stored(prior)
    if old and old != rows:
        raise SourceRepairError("Retained Armor Model custody cannot be replaced.")
    for row in rows:
        if row["summary_id"] and [canonical(feature) for feature in prior.features
                if feature.get("id") == row["summary_id"]] != [row["prior_feature_json"]]:
            raise SourceRepairError("The Armor Model summary is not the original retained row.")
        if service is not None and current_contract(candidate, service) != {
                key: value for key, value in row.items() if key not in {"summary_id", "prior_feature_json"}}:
            raise SourceRepairError("The selected Armor Model sources changed or are unavailable.")
    return rows


def custody(definition, origin, rows):
    return (({"armor_model_custody": {"campaign_slug": definition.campaign_slug,
        "character_slug": definition.character_slug, "action_id": origin["action_id"],
        "selection_digest": digest(list(rows)), "choices": deepcopy(list(rows))}},) if rows else ())


def qualified(definition, service, witnesses):
    try:
        rows = validate(definition, definition, service)
        origin = definition.source.get("native_reconstruction") or {}
        if not rows or origin.get("armor_model_digest") != digest(list(rows)):
            return ()
        decoded = [json.loads(value) if isinstance(value, str) else value for value in witnesses]
        return rows if custody(definition, origin, rows)[0] in decoded else ()
    except (AttributeError, KeyError, TypeError, ValueError):
        return ()


def selectors(definition, service, witnesses=None):
    """No caller can promote retained intent into a selected source edge."""
    return {MODEL: list(PATH)} if qualified(definition, service, witnesses or ()) else {}


def structural_selectors(definition, service):
    """Non-entitling source structure for candidate ownership preparation only."""
    try:
        return {MODEL: list(PATH)} if validate(definition, definition, service) else {}
    except (AttributeError, KeyError, TypeError, ValueError):
        return {}


def historical_ids(definition):
    return frozenset(row["summary_id"] for row in stored(definition) if row["summary_id"])


def merge_continuation(definition, new_features):
    """An inert historical citation never consumes a later mechanical grant."""
    from .character_builder_features import _merge_feature_payloads
    summaries = historical_ids(definition)
    from .character_feature_history import declared_ids
    summaries = summaries | declared_ids(definition)
    original = list(definition.features or [])
    incoming = deepcopy(new_features)
    for row in incoming:
        if row.get("id") in summaries:
            row["id"] = "armor-model-enhancement:" + digest({"source": row.get("systems_ref"),
                "owner": row.get("class_row_id")})[:24]
    merged = _merge_feature_payloads([row for row in original if row.get("id") not in summaries],
                                   incoming, preserve_source_aliases=True)
    for index, row in enumerate(original):
        if row.get("id") in summaries:
            merged.insert(index, deepcopy(row))
    return merged


def projection(definition, state, authority, service, item_catalog):
    """Read-only wearing/hand proof and current numeric alternatives."""
    from .character_equipment_activation import analyze_activation, effective_definition
    from .character_builder_equipment import _resolve_armor_profile, _resolve_weapon_profile
    from .character_profile import profile_class_rows
    claims = [row for row in definition.features if isinstance(row, dict)
              and dict(row.get("systems_ref") or {}).get("entry_key") == ARCANE]
    enabled = dict(state.get("feature_states") or {}).get("arcane_armor", {})
    enabled = enabled.get("enabled") if isinstance(enabled, dict) else None
    enabled = enabled if type(enabled) is bool else None
    frame = {"available": bool(claims), "feature_key": "arcane_armor", "label": "Arcane Armor",
        "enabled": enabled, "status_label": "Enabled" if enabled is True else "Disabled" if enabled is False else "Unknown",
        "hands": {hand: {"status": "unknown", "reason": "Current equipment ownership is unproved."}
                  for hand in ("main-hand", "off-hand")},
        "hands_free": False, "hands_label": "Hand availability unknown",
        "thunder_gauntlets_available": False, "defensive_field_available": False,
        "feature_availability": {}, "attacks": [], "summary_presentations": {}}
    if authority is None or service is None:
        return frame
    # The ordinary read producer binds the activation-reconciled definition;
    # writer factories additionally retain its raw digest. Authenticate the
    # same overlay here rather than comparing raw flags with an overlay hash.
    reconciled, _warnings = effective_definition(definition, state)
    original_digest = getattr(authority, "original_definition_digest", "")
    if (authority.definition_digest != digest(reconciled.to_dict())
            or authority.state_digest != digest(state)
            or original_digest and original_digest != digest(definition.to_dict())):
        frame["reason"] = "The current armor proof belongs to a different Character observation."
        return frame
    choices = qualified(definition, service, authority.verified_numeric_actions)
    if not choices:
        frame["reason"] = "The current Armor Model selection needs source verification."
        return frame
    choice = choices[0]
    owner = choice["class_row_id"]
    if owner not in authority.verified_class_rows:
        return frame
    if choice["summary_id"]:
        from .character_parent_facets import _markdown
        current_model = _entry(definition, service, MODEL)
        rule_text = [_markdown(current_model.body["entries"][4]["entries"][0]["entries"]),
                     _markdown(current_model.body["entries"][2])]
        for key in CHILDREN:
            child = _entry(definition, service, key)
            rule_text.append("### " + child.title + "\n\n" + _markdown(child.body.get("entries")))
        frame["summary_presentations"][choice["summary_id"]] = {
            "systems_ref": deepcopy(choice["systems_ref"]), "parent_summary": True,
            "description_markdown": "\n\n".join(rule_text)}
    features = {}
    for key in (MODEL, ARCANE, *CHILDREN):
        matches = [row for row in definition.features if isinstance(row, dict)
                   and dict(row.get("systems_ref") or {}).get("entry_key") == key
                   and row.get("class_row_id") in (None, "", owner)]
        if len(matches) != 1 or authority.status_for("feature", matches[0].get("id")) != "VERIFIED":
            frame["reason"] = "A selected model feature has missing or ambiguous current ownership."
            return frame
        features[key] = matches[0]
    analysis = analyze_activation(definition, state)
    inventory = state.get("inventory")
    physical = [row for row in definition.equipment_catalog if isinstance(row, dict) and not row.get("is_currency_only")]
    equipment = {row.get("id"): row for row in physical}
    currency = {row.get("id") for row in definition.equipment_catalog if isinstance(row, dict) and row.get("is_currency_only")}
    suits, known, suit_uncertain = [], True, False
    try:
        bound_rows = [json.loads(row) for row in authority.equipment_hand_rows or ()]
        keys = ("id", "catalog_ref", "quantity", "is_equipped", "is_attuned", "weapon_wield_mode", "charges_current", "charges_max")
        if [{key: row.get(key) for key in keys} for row in inventory] != [
                {key: row.get(key) for key in keys} for row in bound_rows]:
            known = False
    except (AttributeError, TypeError, ValueError):
        known = False
    hands = {hand: {"status": "clear", "reason": "No currently equipped object occupies this hand."}
             for hand in frame["hands"]}
    def uncertain(reason):
        for hand in hands:
            hands[hand] = {"status": "unknown", "reason": reason}
    if (analysis["blocked"] or analysis["warnings"] or type(inventory) is not list
            or len(equipment) != len(physical) or not known):
        known = False
    else:
        seen = set()
        for row in inventory:
            if isinstance(row, dict) and row.get("id") in currency:
                continue
            if (type(row) is not dict or not row.get("id") or row.get("id") in seen
                    or row.get("id") != row.get("catalog_ref") or row.get("id") not in equipment
                    or type(row.get("quantity")) is not int or row["quantity"] < 0
                    or type(row.get("is_equipped")) is not bool):
                known = False
                break
            seen.add(row["id"])
            if not row["is_equipped"]:
                continue
            if row["quantity"] != 1:
                uncertain("An equipped physical stack has ambiguous hand placement.")
                suit_uncertain = True
                continue
            item = {**equipment[row["id"]], **row}
            ref = equipment[row["id"]].get("systems_ref")
            entry = (_entry(definition, service, ref.get("entry_key")) if isinstance(ref, dict) else None)
            if entry is None or authority.status_for("item", row["id"]) != "VERIFIED":
                uncertain("An equipped object's current source or physical qualification is unavailable.")
                # A known source weapon cannot be a second suit; hand uncertainty
                # remains separate from Defensive Field's wearing prerequisite.
                if entry is None or str(entry.metadata.get("type") or "").split("|")[0] not in {"M", "R", "S", "W", "WD", "RD", "ST", "RG", "INS", "AT", "GS"}:
                    suit_uncertain = True
                continue
            armor = _resolve_armor_profile(item, item_catalog or {}, entry=entry,
                metadata=entry.metadata, trusted_source_kind="systems_key")
            weapon = _resolve_weapon_profile(item, item_catalog or {}, entry=entry,
                metadata=entry.metadata, trusted_source_kind="systems_key")
            mode = row.get("weapon_wield_mode")
            if armor is not None and not armor.get("is_shield"):
                if mode not in (None, ""):
                    known = False
                    break
                suits.append(row["id"])
                continue
            if str(entry.metadata.get("type") or "").split("|")[0] == "RG" and mode in (None, ""):
                continue  # A current source ring is worn, not a held object.
            if weapon is None or mode not in {"main-hand", "off-hand", "two-handed"}:
                uncertain("An equipped held object has no supported exact hand placement.")
                continue
            from .character_builder_equipment import describe_equipment_state_support
            support = describe_equipment_state_support(item, item_catalog=item_catalog, entry=entry,
                                                       trusted_source=("systems_key", entry.entry_key))
            if mode not in support.get("weapon_wield_modes", []):
                uncertain("The equipped weapon's hand mode is incompatible with its current source.")
                continue
            occupied = tuple(hands) if mode == "two-handed" else (mode,)
            if any(hands[hand]["status"] == "occupied" for hand in occupied):
                uncertain("Equipped hand assignments conflict.")
                continue
            for hand in occupied:
                if hands[hand]["status"] != "clear":
                    hands[hand] = {"status": "unknown", "reason": hands[hand]["reason"]}
                else:
                    hands[hand] = {"status": "occupied", "reason": "Occupied by " + str(item.get("name") or row["id"])}
        if seen != set(equipment):
            known = False
    if known:
        frame["hands"] = hands
    wearing = known and not suit_uncertain and len(suits) == 1 and enabled is True
    armor_reason = ("" if wearing else "Current enabled Arcane Armor and one exact equipped suit are required.")
    frame["defensive_field_available"] = wearing
    frame["hands_free"] = any(row["status"] == "clear" for row in frame["hands"].values())
    frame["hands_label"] = "; ".join(hand + ": " + row["status"] for hand, row in frame["hands"].items())
    frame["thunder_gauntlets_available"] = wearing and frame["hands_free"]
    frame["feature_availability"] = {
        features[FIELD]["id"]: {"available": wearing, "reason": armor_reason},
        features[GAUNTLETS]["id"]: {"available": frame["thunder_gauntlets_available"],
            "reason": armor_reason or ("" if frame["hands_free"] else "No hand is proved clear.")}}
    levels = [row["level"] for row in profile_class_rows(definition.profile) if row.get("row_id") == owner]
    frame["defensive_field_temp_hp"] = levels[0] if len(levels) == 1 else None
    pb = authority.field_status("stats.proficiency_bonus")
    for hand, occupancy in frame["hands"].items():
        for ability in ("str", "int"):
            score = authority.field_status(f"stats.ability_scores.{ability}.score")
            if not score.is_effective or type(score.effective) is not int or not pb.is_effective or type(pb.effective) is not int:
                continue
            modifier = (score.effective - 10) // 2
            attack = {"id": "armor-model:" + owner + ":" + hand + ":" + ability,
                "name": "Thunder Gauntlet (" + hand + ", " + ability.upper() + ")",
                "systems_ref": deepcopy(features[GAUNTLETS]["systems_ref"]),
                "class_row_id": owner, "category": "melee", "attack_bonus": modifier + pb.effective,
                "damage": "1d8" + (f"{modifier:+d}" if modifier else ""), "damage_type": "thunder",
                "authority_ability_dependencies": [ability], "authority_requires_proficiency_bonus": True,
                "authority_weapon_proficiencies": ["Simple Weapons", "Simple"],
                "notes": "Requires this hand to be empty. Choose Strength or Intelligence for the attack and damage rolls.",
                "armor_model_hand": hand, "armor_model_feature_id": features[GAUNTLETS]["id"]}
            if authority.attack_inputs_effective(attack, definition):
                available = wearing and occupancy["status"] == "clear"
                frame["attacks"].append({"attack": attack, "name": attack["name"], "linked_item_refs": [],
                    "is_equipped": available, "hidden": False, "hidden_reason": "",
                    "available": available, "availability_reason": armor_reason or ("" if available else occupancy["reason"])})
    return frame
