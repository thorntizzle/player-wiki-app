"""Source-qualified Artificer assignment observations; effects remain table managed.

No read initializes a ledger, and no assignment is copied into legacy item effects.
Only the sealed state transition may change this optional, audited state member.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
import re
from uuid import uuid4

from .character_parent_facets import digest
from .systems_feature_capacities import INFUSE, TINKERING
from .systems_feature_values import source_digest

KEY = "artificer_assignments"
EVENT = "character_artificer_assignment_applied"
_SEAL = object()
_KINDS = ("infusions", "tinkering")
_PREFIX = "dnd-5e|optionalfeature|tce|"
_GOGGLES = "dnd-5e|item|dmg|gogglesofnight"
_HASHES = {
    "enhanceddefense": "3add34c8db8637f7354caba174a52d5dbde6e549b903e32ac91d5b3d4a65dfd0",
    "homunculusservant": "4ed02e1a1a3663fca70beed5ecc66978e0cb63faf32001e61edb4b281ffb2dce",
    "replicatemagicitem": "12fcb4c808361dafe6c218a7f00a4507985707a128601786f8383dde82673f92",
    "repeatingshot": "27f40329ed5a6198efd6676b61910b15ccbd7d942bcfc65fea81b8e61f59f9ae",
    "bootsofthewindingpath": "34d064eb13e0f55ddc91514a4012001a326ef29666e9ee102957a939bb17f837",
    "armorofmagicalstrength": "498a81eb5e86b41ef74f29f29adf8c24e1fd14a9f51f85a70958dfcacd6d8400",
}
_RECIPE_RULES = {
    "enhanceddefense": (["armor", "shield"], False,
        ["While worn (armor) or wielded (shield), +1 AC; +2 at Artificer level 10."]),
    "homunculusservant": (["gem", "crystal"], False,
        ["A gem or crystal worth at least 100 gp becomes the homunculus's heart.",
         "The creature shares your initiative and acts immediately after you; it normally Dodges unless commanded with your bonus action. When you are incapacitated it can choose its action.",
         "Mending restores 2d6 HP. If you or it dies, it vanishes and leaves its heart. No companion or HP record is created here."]),
    "replicatemagicitem": (["goggles"], False,
        ["The selected Goggles of Night result grants darkvision 60 feet while worn, or extends existing darkvision by 60 feet."]),
    "repeatingshot": (["simple_ammunition_weapon", "martial_ammunition_weapon"], True,
        ["+1 to ranged attack and damage rolls; ignores loading. When ammunition is absent, creates one piece for the ranged attack that vanishes after hit or miss."]),
    "bootsofthewindingpath": (["boots"], True,
        ["Requires Artificer level 6. While worn, a bonus action teleports up to 15 feet to a visible unoccupied space occupied earlier this turn."]),
    "armorofmagicalstrength": (["armor"], True,
        ["Six-charge capacity; current charges are not initialized or managed here.",
         "Spend one charge to add the wearer's Intelligence modifier to a Strength check/save, or use a reaction and one charge to prevent being knocked prone. Regains 1d6 expended charges at dawn."]),
}
_TINKERING = [
    {"id": "light", "title": "Light", "rules": ["Bright light 5 feet; dim light an additional 5 feet."]},
    {"id": "message", "title": "Recorded message", "rules": ["A tapped object plays your recording, at most 6 seconds, audible within 10 feet."]},
    {"id": "odor_sound", "title": "Odor or nonverbal sound", "rules": ["Continuously emits an odor or nonverbal sound perceptible within 10 feet."]},
    {"id": "visual", "title": "Static visual effect", "rules": ["A static picture, shapes, or text of at most 25 words appears on one surface."]},
]
_RULES = {
    "infusions": ["At the end of a long rest, touch each nonmagical object of the required kind.",
        "One object per known recipe and one infusion per object. At capacity the oldest infusion ends before the new one applies.",
        "Required self-attunement may occur immediately; later attunement follows the normal process. Attunement observations here do not change equipment state.",
        "An infusion persists indefinitely, ends on giving up its recipe, and expires after the artificer's death after Intelligence-modifier days (minimum one). Contents of a container appear harmlessly when its infusion ends."],
    "tinkering": ["Hold thieves' or artisan's tools, and use an action to touch a Tiny nonmagical object.",
        "One property per object; the maximum is Intelligence modifier (minimum one). At capacity the oldest property ends before the new one applies.",
        "Properties last indefinitely. An action touching an object can end its property."],
}
MANUAL_NOTE = "Assignment records only. Effects, charges, companions, recipient inventories and attunement are resolved at the table. Historical resource counters are unchanged."


def _campaign_deactivation_policy(campaign_slug):
    from .committed_publication import active, config
    if not active():
        return None
    row, settings = config(campaign_slug)
    if settings.get("allow_artificer_infusion_deactivation") is not True:
        return None
    revision, sha256 = row["revision"], row["primary_sha256"]
    if type(revision) is not int or revision < 1 or not _text(sha256, 64) or re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
        raise ValueError("Campaign ruling authority is unavailable.")
    return (revision, sha256)


def _deactivation_requested(params):
    return (type(params) is dict and params.get("kind") == "infusions"
            and params.get("operation") == "end" and params.get("reason") == "campaign_deactivation")


def _require_deactivation_policy(definition, expected):
    from .character_store import source_writer_reserved
    from .db import get_db
    if not source_writer_reserved(get_db()) or expected is None or _campaign_deactivation_policy(definition.campaign_slug) != expected:
        raise ValueError("The campaign deactivation ruling is unavailable or changed; reload before saving.")


def _text(value, maximum=160, *, empty=False):
    return (type(value) is str and len(value) <= maximum and value == value.strip()
            and (empty or bool(value)) and not any(ord(c) < 32 for c in value))


def _keys(value, required, optional=()):
    return type(value) is dict and set(required) <= set(value) and not set(value) - set(required) - set(optional)


def _exact_authority(definition, state, authority):
    from .character_source_authority import numeric_value_digest
    if (definition.system != "DND-5E" or authority is None
            or (authority.original_definition_digest or authority.definition_digest) != numeric_value_digest(definition.to_dict())
            or authority.state_digest != numeric_value_digest(state)
            or type(authority.state_revision) is not int or authority.state_revision < 1):
        raise ValueError("Assignments require current exact character and state authority.")


def _source_context(definition, state, authority, service, kind, *, capacities=None, recipe_view=None):
    from .character_feature_capacities import presentations
    from .character_infusion_recipes import view, _entry
    _exact_authority(definition, state, authority)
    target = INFUSE if kind == "infusions" else TINKERING
    ids = [r.get("id") for r in definition.features if type(r) is dict
           and type(r.get("systems_ref")) is dict and r["systems_ref"].get("entry_key") == target]
    caps = presentations(definition, state, authority, service) if capacities is None else capacities
    capacity = caps.get(ids[0]) if len(ids) == 1 else None
    if not capacity or not capacity.get("available"):
        raise ValueError("The current source, class owner and simultaneous capacity are not qualified.")
    options, known, unsupported = [], [], []
    basis = {"capacity": capacity["source_basis_digest"], "owner": capacity["class_row_id"], "feature": ids[0]}
    if kind == "infusions":
        knowledge = view(definition, state, authority, service) if recipe_view is None else recipe_view
        if not knowledge.get("typed") or not knowledge.get("available"):
            raise ValueError("Assignments require currently qualified typed recipe knowledge.")
        known = knowledge["known"]
        basis["known"] = known
        source_bases = []
        for row in known:
            key = row["systems_ref"]["entry_key"]
            short = key[len(_PREFIX):] if key.startswith(_PREFIX) else ""
            entry = _entry(definition, service, row["systems_ref"], {"optionalfeature"})
            body = {"metadata": entry.metadata, "body": entry.body}
            source_bases.append(body)
            if short not in _HASHES or source_digest(body) != _HASHES[short]:
                unsupported.append(row["name"])
                continue
            if short == "replicatemagicitem":
                result = row.get("selected_item_ref")
                if type(result) is not dict or result.get("entry_key") != _GOGGLES:
                    unsupported.append(row["name"])
                    continue
                item = _entry(definition, service, result, {"item"})
                item_body = {"metadata": item.metadata, "body": item.body}
                source_bases.append(item_body)
                if source_digest(item_body) != "797d52b3b38b1bbc1515f105488c5e1326081e4f145707f83814a819f01fb6b2":
                    unsupported.append(row["name"])
                    continue
            types, attune, rules = _RECIPE_RULES[short]
            options.append({"id": row["infusion_key"], "title": row["name"], "object_kinds": list(types),
                "requires_attunement": attune, "rules": list(rules), "recipe": deepcopy(row),
                "minimum_value_gp": 100 if short == "homunculusservant" else 0})
        basis["sources"] = source_bases
    else:
        options = [{**deepcopy(row), "object_kinds": ["tiny_object"], "requires_attunement": False,
                    "minimum_value_gp": 0} for row in _TINKERING]
    return {"maximum": capacity["maximum"], "source_basis_digest": digest(basis),
            "class_row_id": capacity["class_row_id"], "feature_id": ids[0], "options": options,
            "known": deepcopy(known), "unsupported": unsupported}


def _ledger(state, definition):
    if KEY not in state:
        return None
    frame = state[KEY]
    if (not _keys(frame, {"schema_version", "campaign_slug", "character_slug"}, _KINDS)
            or type(frame["schema_version"]) is not int or frame["schema_version"] != 1
            or frame["campaign_slug"] != definition.campaign_slug or frame["character_slug"] != definition.character_slug):
        raise ValueError("The assignment ledger is malformed or belongs to another character; preserve it for repair.")
    physical, assignments = set(), set()
    for kind in _KINDS:
        if kind not in frame:
            continue
        member = frame[kind]
        if (not _keys(member, {"status", "source_basis_digest", "class_row_id", "feature_id", "next_order", "entries"})
                or member["status"] != "confirmed" or not _text(member["source_basis_digest"], 64)
                or re.fullmatch(r"[0-9a-f]{64}", member["source_basis_digest"]) is None
                or type(member["next_order"]) is not int or not 1 <= member["next_order"] <= 1000000000
                or not _text(member["class_row_id"]) or not _text(member["feature_id"])
                or type(member["entries"]) is not list or len(member["entries"]) > 40):
            raise ValueError("The recorded assignment set needs repair; its observations are preserved.")
        last, choices = 0, set()
        for row in member["entries"]:
            if (not _keys(row, {"assignment_id", "order", "choice_id", "title", "object", "attunement", "details"})
                    or not _text(row["assignment_id"], 32)
                    or re.fullmatch(r"[0-9a-f]{32}", row["assignment_id"]) is None or row["assignment_id"] in assignments
                    or type(row["order"]) is not int or not last < row["order"] < member["next_order"]
                    or not _text(row["choice_id"], 300) or not _text(row["title"], 300)
                    or row["attunement"] not in ("unknown", "none", "self", "other")
                    or not _keys(row["details"], {"property_text", "message_seconds", "visual_type", "visual_text"})
                    or not _text(row["details"]["property_text"], 500, empty=True)
                    or type(row["details"]["message_seconds"]) is not int
                    or not 0 <= row["details"]["message_seconds"] <= 6
                    or row["details"]["visual_type"] not in ("", "text", "picture", "shapes", "mixed")
                    or not _text(row["details"]["visual_text"], 500, empty=True)):
                raise ValueError("Assignment identities, order or properties are malformed; preserve them for repair.")
            obj = row["object"]
            if (not _keys(obj, {"physical_id", "mode", "id", "name", "recipient", "kind", "nonmagical", "value_gp", "inventory_basis"})
                    or obj["mode"] not in ("inventory", "external") or not _text(obj["id"])
                    or obj["physical_id"] != obj["mode"] + ":" + obj["id"]
                    or obj["physical_id"] in physical or not _text(obj["name"])
                    or not _text(obj["recipient"], 240) or not _text(obj["kind"])
                    or obj["nonmagical"] is not True or type(obj["value_gp"]) is not int or obj["value_gp"] < 0
                    or not _text(obj["inventory_basis"], 64, empty=obj["mode"] == "external")):
                raise ValueError("Physical assignment observations are malformed or duplicated; preserve them for repair.")
            if kind == "infusions" and row["choice_id"] in choices:
                raise ValueError("A known infusion cannot occupy two objects.")
            physical.add(obj["physical_id"]); assignments.add(row["assignment_id"])
            choices.add(row["choice_id"]); last = row["order"]
    return frame


def _checkpoint(definition, state, authority):
    from .db import get_db
    try:
        row = get_db().execute("SELECT actor_user_id,metadata_json FROM auth_audit_log WHERE campaign_slug=? AND character_slug=? AND event_type=? ORDER BY id DESC LIMIT 1",
            (definition.campaign_slug, definition.character_slug, EVENT)).fetchone()
    except RuntimeError:
        return False
    if row is None:
        return False
    try:
        data = json.loads(row["metadata_json"])
        return (type(data) is dict and data.get("source") == "artificer_assignment_v1"
            and type(row["actor_user_id"]) is int and row["actor_user_id"] > 0
            and type(data.get("actor_id")) is int and data["actor_id"] == row["actor_user_id"]
            and data.get("campaign_slug") == definition.campaign_slug and data.get("character_slug") == definition.character_slug
            and type(data.get("state_revision")) is int and data["state_revision"] <= authority.state_revision
            and type(data.get("prior_state_revision")) is int and data["prior_state_revision"] >= 1
            and data["state_revision"] == data["prior_state_revision"] + 1
            and data.get("ledger_digest") == digest(data.get("ledger")) == digest(state[KEY]))
    except (ValueError, TypeError, KeyError, AttributeError):
        return False


def _legacy_conflict(definition, state):
    # Malformed nonempty legacy observations also block silent reconciliation.
    return any(type(r) is dict and r.get("active_infusions") not in (None, [])
               for r in [*definition.equipment_catalog, *state.get("inventory", [])])


def _check_observed_kind(metadata, kind):
    """Reject contradictory typed facts; missing facts remain player observations."""
    raw_type = metadata.get("type")
    current_type = raw_type.split("|", 1)[0].strip().upper() if type(raw_type) is str else ""
    armor_types = {"LA", "MA", "HA"}
    weapon_kinds = {"simple_ammunition_weapon", "martial_ammunition_weapon"}
    if kind == "armor":
        if current_type and current_type not in armor_types:
            raise ValueError("The current inventory source does not describe a suit of armor.")
    elif kind == "shield":
        if current_type and current_type != "S":
            raise ValueError("The current inventory source does not describe a shield.")
    elif kind in weapon_kinds:
        if current_type and current_type not in {"M", "R"}:
            raise ValueError("The current inventory source is not a simple or martial weapon.")
        category = metadata.get("weapon_category")
        expected = "simple" if kind == "simple_ammunition_weapon" else "martial"
        if type(category) is str and category.strip() and category.strip().lower() != expected:
            raise ValueError("The observed weapon category contradicts its current source.")
        properties = metadata.get("properties")
        if type(properties) is list and not any(type(p) is str and p.split("|", 1)[0] == "A" for p in properties):
            raise ValueError("The current weapon source lacks the required ammunition property.")
    elif kind in {"boots", "goggles", "gem", "crystal"}:
        if current_type in armor_types | {"S", "M", "R", "A", "AF", "P", "SC", "RD", "WD", "RG"}:
            raise ValueError("The observed object kind contradicts its current inventory source type.")
    if kind == "tiny_object":
        size = metadata.get("size")
        if (type(size) is str and size and size.upper() not in {"T", "TINY"}
                or type(size) is list and size and "T" not in size and "Tiny" not in size):
            raise ValueError("The current source contradicts the observed Tiny object size.")


def _inventory_basis(definition, state, authority, service, identity, object_kind):
    from .character_item_capabilities import _physical_rows
    from .character_feature_values import _exact_entry
    rows = [r for r in state.get("inventory", []) if type(r) is dict and r.get("id") == identity]
    if len(rows) != 1 or type(rows[0].get("quantity")) is not int or rows[0]["quantity"] != 1:
        raise ValueError("Choose one uniquely identified inventory instance with quantity one.")
    physical = [r for r in _physical_rows(authority) if type(r) is dict and r.get("id") == identity]
    row = rows[0]
    reference = row.get("catalog_ref") or identity
    items = [r for r in definition.equipment_catalog if type(r) is dict and r.get("id") == reference]
    if (len(items) != 1 or len(physical) != 1 or physical[0].get("activation_current") is not True
            or authority.status_for("item", reference) != "VERIFIED"
            or (physical[0].get("catalog_ref") or identity) != reference
            or type(physical[0].get("quantity")) is not int or physical[0]["quantity"] != 1):
        raise ValueError("That physical inventory item needs current source and identity qualification.")
    item = items[0]
    if item.get("is_currency_only") or row.get("is_currency_only"):
        raise ValueError("A currency aggregate is not a physical object instance.")
    ref = item.get("systems_ref")
    source = _exact_entry(service, definition.campaign_slug, ref) if type(ref) is dict else None
    if type(ref) is dict and (source is None or not service.is_entry_enabled_for_campaign(definition.campaign_slug, source)):
        raise ValueError("The physical item's exact current source is unavailable.")
    payload = authority.approved_payload("item", reference)
    metadata = source.metadata if source is not None else payload
    from .character_builder_equipment import _metadata_is_magic_item
    if _metadata_is_magic_item(metadata) or item.get("active_infusions") or row.get("active_infusions"):
        raise ValueError("The target already has a recorded magical source or infusion.")
    _check_observed_kind(metadata, object_kind)
    return digest({"id": identity, "catalog_ref": reference, "item": item,
                   "source": {"metadata": source.metadata, "body": source.body} if source else payload})


def _qualified_member(definition, state, authority, service, kind, context, frame):
    if frame is None or kind not in frame:
        if _legacy_conflict(definition, state):
            raise ValueError("Existing legacy infusion observations require reconciliation before confirming an empty ledger.")
        return None
    if not _checkpoint(definition, state, authority):
        raise ValueError("Assignment audit custody is unavailable; recorded observations are preserved.")
    member = frame[kind]
    if any(member[key] != context[key] for key in ("source_basis_digest", "class_row_id", "feature_id")):
        raise ValueError("Assignment source or ownership changed; observations need reconciliation and are preserved.")
    if len(member["entries"]) > context["maximum"]:
        raise ValueError("Recorded assignments exceed the current capacity; preserve them for reconciliation.")
    options = {r["id"]: r for r in context["options"]}
    for row in member["entries"]:
        option = options.get(row["choice_id"])
        if (option is None or row["title"] != option["title"] or row["object"]["kind"] not in option["object_kinds"]
                or row["object"]["value_gp"] < option["minimum_value_gp"]):
            raise ValueError("A recorded assignment no longer has a supported exact recipe or property.")
        obj = row["object"]
        if obj["mode"] == "inventory" and obj["inventory_basis"] != _inventory_basis(definition, state, authority, service, obj["id"], obj["kind"]):
            raise ValueError("An assigned physical inventory item changed; its observation needs reconciliation.")
    return member


def presentation(definition, state, authority, service, *, capacities=None, recipe_view=None):
    result = {"manual_effects": True, "manual_note": MANUAL_NOTE}
    for kind in _KINDS:
        view = {"available": False, "status": "unavailable", "maximum": None, "count": None,
                "entries": [], "options": [], "known": [], "unsupported": [], "rules": list(_RULES[kind]),
                "reason": "", "oldest_id": "", "can_confirm_empty": False,
                "can_deactivate": False, "deactivation_policy": None}
        try:
            if kind == "infusions":
                policy = _campaign_deactivation_policy(definition.campaign_slug)
                view["can_deactivate"] = policy is not None
                if policy is not None:
                    view["deactivation_policy"] = {"revision": policy[0], "sha256": policy[1]}
            context = _source_context(definition, state, authority, service, kind,
                                      capacities=capacities, recipe_view=recipe_view)
            view.update({k: deepcopy(context[k]) for k in (
                "maximum", "options", "known", "unsupported", "feature_id", "class_row_id", "source_basis_digest")})
            frame = _ledger(state, definition)
            if frame is not None and not _checkpoint(definition, state, authority):
                raise ValueError("Assignment audit custody is unavailable; observations remain unchanged.")
            member = _qualified_member(definition, state, authority, service, kind, context, frame)
            view.update(available=True, status="unknown" if member is None else "confirmed",
                        count=None if member is None else len(member["entries"]), can_confirm_empty=member is None)
            if member is not None:
                view["entries"] = deepcopy(member["entries"])
                view["oldest_id"] = member["entries"][0]["assignment_id"] if member["entries"] else ""
            else:
                view["reason"] = "Current assignments are unknown. Confirm a genuinely empty baseline before recording new assignments."
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            view["reason"] = str(error)
        result[kind] = view
    return result


def _validate_params(params):
    if (type(params) is not dict or params.get("kind") not in _KINDS
            or params.get("operation") not in ("confirm_empty", "assign", "end") or params.get("confirm") is not True):
        raise ValueError("Choose and explicitly confirm one supported assignment operation.")
    required = {"kind", "operation", "confirm"}
    optional = set()
    if params["operation"] == "assign":
        required |= {"choice_id", "object_mode", "object_id", "object_name", "recipient", "object_kind", "nonmagical", "attunement", "touch", "replace_oldest"}
        optional = {"value_gp"}
        required |= {"long_rest"} if params["kind"] == "infusions" else {"tools", "action", "tiny", "property_text", "message_seconds"}
        if params["kind"] == "tinkering" and params.get("choice_id") == "visual":
            required |= {"visual_type", "visual_text"}
    elif params["operation"] == "end":
        required |= {"assignment_id", "reason"}
        if params["kind"] == "tinkering":
            required |= {"action", "touch"}
        elif params.get("reason") == "death_duration":
            required |= {"days_elapsed"}
        elif params.get("reason") == "campaign_deactivation":
            required |= {"policy_revision", "policy_sha256"}
    if not _keys(params, required, optional):
        raise ValueError("Assignment fields do not match the selected operation.")


def _apply(state, definition, authority, service, params, assignment_id, policy=None):
    _validate_params(params)
    if _deactivation_requested(params):
        _require_deactivation_policy(definition, policy)
    kind, operation = params["kind"], params["operation"]
    context = _source_context(definition, state, authority, service, kind)
    frame = _ledger(state, definition)
    if frame is not None and not _checkpoint(definition, state, authority):
        raise ValueError("The existing assignment ledger has no matching authenticated audit checkpoint.")
    member = _qualified_member(definition, state, authority, service, kind, context, frame)
    if _legacy_conflict(definition, state):
        raise ValueError("Legacy infusion observations require separate reconciliation; they cannot be overwritten here.")
    result = deepcopy(state)
    ledger = deepcopy(frame) if frame is not None else {"schema_version": 1,
        "campaign_slug": definition.campaign_slug, "character_slug": definition.character_slug}
    if operation == "confirm_empty":
        if member is not None:
            raise ValueError("This assignment set is already confirmed; it cannot be reinitialized.")
        ledger[kind] = {k: context[k] for k in ("source_basis_digest", "class_row_id", "feature_id")}
        ledger[kind].update(status="confirmed", next_order=1, entries=[])
    else:
        if member is None:
            raise ValueError("Current assignments are unknown. Confirm the actual empty baseline first.")
        member = ledger[kind]
        if operation == "end":
            if not _text(params["assignment_id"], 32):
                raise ValueError("Choose one exact recorded assignment.")
            matches = [r for r in member["entries"] if r["assignment_id"] == params["assignment_id"]]
            if len(matches) != 1:
                raise ValueError("The selected assignment is no longer current.")
            reason = params["reason"]
            if kind == "tinkering":
                if reason != "action_touch" or params["action"] is not True or params["touch"] is not True:
                    raise ValueError("Ending this property requires an action and touching the object.")
            elif reason == "knowledge_loss":
                if matches[0]["choice_id"] in {r["infusion_key"] for r in context["known"]}:
                    raise ValueError("This recipe is still known. Changed recipe ownership requires separate reconciliation.")
            elif reason == "death_duration":
                score = authority.field_status("stats.ability_scores.int.score")
                days = max(1, (score.effective - 10) // 2) if score.is_effective and type(score.effective) is int else None
                if days is None or type(params["days_elapsed"]) is not int or not days <= params["days_elapsed"] <= 100000:
                    raise ValueError("Confirm death and at least the qualified Intelligence-modifier number of elapsed days (minimum one).")
            elif reason not in ("item_destroyed", "campaign_deactivation"):
                raise ValueError("Infusions cannot be freely dismissed; record a supported actual ending.")
            member["entries"] = [r for r in member["entries"] if r["assignment_id"] != params["assignment_id"]]
        else:
            if (params["touch"] is not True or params["nonmagical"] is not True
                    or params["object_mode"] not in ("inventory", "external")
                    or not _text(params["object_id"]) or not _text(params["object_name"])
                    or not _text(params["recipient"], 240) or not _text(params["object_kind"])
                    or not _text(params["choice_id"], 300) or not _text(params["replace_oldest"], 32, empty=True)
                    or params["attunement"] not in ("unknown", "none", "self", "other")):
                raise ValueError("Confirm the actual nonmagical physical object, touch, recipient and attunement observation.")
            option = next((r for r in context["options"] if r["id"] == params["choice_id"]), None)
            value = params.get("value_gp", 0)
            if (option is None or params["object_kind"] not in option["object_kinds"]
                    or type(value) is not int or not option["minimum_value_gp"] <= value <= 1000000000):
                raise ValueError("Choose a supported current recipe/property and its exact eligible object kind and value.")
            if not option["requires_attunement"] and params["attunement"] not in ("unknown", "none"):
                raise ValueError("This property does not require attunement.")
            details = {"property_text": "", "message_seconds": 0, "visual_type": "", "visual_text": ""}
            if kind == "infusions":
                if params["long_rest"] is not True:
                    raise ValueError("Record an infusion only after the actual completed long rest and touch.")
            else:
                if any(params[k] is not True for k in ("tools", "action", "tiny")):
                    raise ValueError("Tinkering needs tools in hand, an action, touch and a Tiny nonmagical object.")
                text, seconds = params["property_text"], params["message_seconds"]
                if not _text(text, 500, empty=option["id"] == "light") or type(seconds) is not int:
                    raise ValueError("Describe the actual property and its recording duration.")
                if (option["id"] == "message" and not 1 <= seconds <= 6
                        or option["id"] != "message" and seconds != 0):
                    raise ValueError("Messages are at most six seconds; other properties have no recording duration.")
                details.update(property_text=text, message_seconds=seconds)
                if option["id"] == "visual":
                    visual_type, visual_text = params["visual_type"], params["visual_text"]
                    if visual_type not in ("text", "picture", "shapes", "mixed"):
                        raise ValueError("Choose the actual static visual property type.")
                    has_text = visual_type in ("text", "mixed")
                    if (not _text(visual_text, 500, empty=not has_text)
                            or not has_text and visual_text != "" or len(visual_text.split()) > 25):
                        raise ValueError("Record at most twenty-five actual displayed words; picture/shape descriptions are separate.")
                    details.update(visual_type=visual_type, visual_text=visual_text)
            physical_id = params["object_mode"] + ":" + params["object_id"]
            # Check before replacement: a still-magical object is not a valid new target.
            active = [r for k in _KINDS if k in ledger for r in ledger[k]["entries"]]
            if any(r["object"]["physical_id"] == physical_id for r in active):
                raise ValueError("This physical object already has a recorded magical assignment.")
            if len(member["entries"]) == context["maximum"]:
                if params["replace_oldest"] != member["entries"][0]["assignment_id"]:
                    raise ValueError("At capacity, explicitly confirm the exact oldest assignment that will end.")
                member["entries"].pop(0)
            elif params["replace_oldest"]:
                raise ValueError("No oldest replacement is due below the simultaneous capacity.")
            if kind == "infusions" and any(r["choice_id"] == option["id"] for r in member["entries"]):
                raise ValueError("This known infusion already occupies an object; record its actual ending first.")
            basis = (_inventory_basis(definition, state, authority, service, params["object_id"], params["object_kind"])
                     if params["object_mode"] == "inventory" else "")
            obj = {"physical_id": physical_id, "mode": params["object_mode"], "id": params["object_id"],
                "name": params["object_name"], "recipient": params["recipient"], "kind": params["object_kind"],
                "nonmagical": True, "value_gp": value, "inventory_basis": basis}
            member["entries"].append({"assignment_id": assignment_id, "order": member["next_order"],
                "choice_id": option["id"], "title": option["title"], "object": obj,
                "attunement": params["attunement"], "details": details})
            member["next_order"] += 1
    result[KEY] = ledger
    _ledger(result, definition)
    return result


@dataclass(frozen=True)
class AssignmentIntent:
    before_digest: str
    after_digest: str
    definition_digest: str
    params_json: str
    actor_id: int
    state_revision: int
    assignment_id: str
    deactivation_policy: tuple[int, str] | None
    seal: object = field(repr=False, compare=False)


def prepare_operation(state, definition, authority, service, params, *, actor_id, state_revision):
    if (type(actor_id) is not int or actor_id < 1 or type(state_revision) is not int or state_revision < 1
            or authority is None or authority.state_revision != state_revision):
        raise ValueError("Assignments require an authenticated actor and exact current state revision.")
    assignment_id = uuid4().hex
    policy = _campaign_deactivation_policy(definition.campaign_slug) if _deactivation_requested(params) else None
    if _deactivation_requested(params) and (type(params.get("policy_revision")) is not int
            or type(params.get("policy_sha256")) is not str
            or policy != (params["policy_revision"], params["policy_sha256"])):
        raise ValueError("The campaign deactivation ruling changed; reload before saving.")
    result = _apply(state, definition, authority, service, params, assignment_id, policy)
    return result, AssignmentIntent(digest(state), digest(result), digest(definition.to_dict()),
        json.dumps(params, sort_keys=True, separators=(",", ":"), allow_nan=False), actor_id,
        state_revision, assignment_id, policy, _SEAL)


def require_preserved(prior, after):
    if prior is None:
        prior = {}
    if type(prior) is not dict or type(after) is not dict:
        raise ValueError("Assignment preservation requires exact state objects.")
    if (KEY in prior) != (KEY in after) or digest(prior.get(KEY)) != digest(after.get(KEY)):
        raise ValueError("Artificer assignments must be preserved outside their exact guarded operation.")


def validate_transition(prior, after, definition, authority, intent=None):
    if intent is None:
        require_preserved(prior, after)
        return
    if (type(intent) is not AssignmentIntent or intent.seal is not _SEAL
            or type(intent.actor_id) is not int or intent.actor_id < 1
            or intent.before_digest != digest(prior) or intent.after_digest != digest(after)
            or intent.definition_digest != digest(definition.to_dict())
            or authority is None or intent.state_revision != authority.state_revision):
        raise ValueError("Assignments require their exact sealed actor/character/state transition.")
    from flask import current_app
    service = current_app.extensions["systems_service"]
    params = json.loads(intent.params_json)
    if not _deactivation_requested(params) and intent.deactivation_policy is not None:
        raise ValueError("The assignment ruling does not match its operation.")
    if digest(_apply(prior, definition, authority, service, params, intent.assignment_id, intent.deactivation_policy)) != digest(after):
        raise ValueError("Assignment sources changed or unrelated state was altered.")


def audit_metadata(prior, after, definition, authority, intent, prior_revision, next_revision):
    validate_transition(prior, after, definition, authority, intent)
    if (type(prior_revision) is not int or type(next_revision) is not int
            or prior_revision != intent.state_revision or next_revision != prior_revision + 1):
        raise ValueError("The assignment state revision changed unexpectedly.")
    metadata = {"source": "artificer_assignment_v1", "actor_id": intent.actor_id,
        "campaign_slug": definition.campaign_slug, "character_slug": definition.character_slug,
        "operation": json.loads(intent.params_json)["operation"], "kind": json.loads(intent.params_json)["kind"],
        "prior_state_revision": prior_revision, "state_revision": next_revision,
        "prior_state_digest": intent.before_digest, "state_digest": intent.after_digest,
        "definition_digest": intent.definition_digest, "ledger": deepcopy(after[KEY]),
        "ledger_digest": digest(after[KEY]), "action": json.loads(intent.params_json),
        "effects_resolved": False, "table_managed": True}
    if intent.deactivation_policy is not None:
        metadata["campaign_ruling"] = {"config_revision": intent.deactivation_policy[0],
            "config_sha256": intent.deactivation_policy[1], "allow_artificer_infusion_deactivation": True}
    return metadata
