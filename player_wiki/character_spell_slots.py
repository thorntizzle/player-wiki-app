from __future__ import annotations

from typing import Any
from copy import deepcopy
from dataclasses import dataclass, field, replace
import hashlib
import json

DEFAULT_SPELL_SLOT_LANE_ID = ""
SLOT_GRANTS_KEY = "spell_slot_grants"
_GRANT_INTENT_SEAL = object()


def slot_value_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def slot_grant_id(source_kind: str, source_key: str, owner: str) -> str:
    return "grant:" + slot_value_digest([source_kind, source_key, owner])[:32]


def parse_spell_slot_selection(value):
    text = str(value or "")
    if len(text) > 256 or text.count("|") != 1:
        raise ValueError("Choose the spell-slot source to spend.")
    pool_id, raw_level = text.split("|", 1)
    if not raw_level.isascii() or not raw_level.isdecimal() or not 1 <= int(raw_level) <= 9:
        raise ValueError("Choose a valid spell-slot level.")
    return pool_id.strip(), int(raw_level)


def _valid_grant(pool: Any) -> bool:
    if (type(pool) is not dict or set(pool) != {"schema_version", "id", "source_kind", "source_key", "owner", "basis", "lifecycle", "slots"}
            or type(pool["schema_version"]) is not int or pool["schema_version"] != 1
            or any(type(pool[k]) is not str or not pool[k] for k in
                ("id", "source_kind", "source_key", "owner", "basis", "lifecycle"))
            or pool["id"] != slot_grant_id(pool["source_kind"], pool["source_key"], pool["owner"])
            or pool["source_kind"] not in {"feature", "item"}
            or type(pool["slots"]) is not list or not pool["slots"]):
        return False
    levels = []
    for slot in pool["slots"]:
        if (type(slot) is not dict or set(slot) != {"level", "max", "used"}
                or any(type(slot[k]) is not int for k in ("level", "max", "used"))
                or not 1 <= slot["level"] <= 9 or not 0 <= slot["used"] <= slot["max"]):
            return False
        levels.append(slot["level"])
    return len(set(levels)) == len(levels)


def _grant_context(authority):
    return json.loads(authority.slot_grant_context_json) if authority is not None and authority.slot_grant_context_json else {
        "providers": [], "raw": []}


def _base_slot_pool_identities(spellcasting, state):
    declared = [lane["id"] for lane in spell_slot_lanes_from_spellcasting(spellcasting)]
    observed = {normalize_spell_slot_lane_id(row.get("slot_lane_id"))
        for row in state.get("spell_slots", []) if isinstance(row, dict)}
    return {"base_pool_ids": sorted(set(declared) | observed),
        "base_conflict_ids": sorted({identity for identity in declared if declared.count(identity) > 1})}


def _is_slot_grant_status(row):
    return (row.reason in {"qualified_slot_contribution", "slot_grant_owner_or_basis_unproven"}
        or row.reason == "slot_pool_identity_conflict" and _valid_grant(row.raw))


def slot_pool_identity_conflicts(authority, *, destination=None, spellcasting=None, state=None):
    """Whole-pool identity, including unqualified observations and other levels.

    Bound raw identities own active decisions. The fallback supplies the same
    read-only rule for legacy readers without a grant authority context.
    """
    context = _grant_context(authority)
    if authority is None or not authority.slot_grant_context_json:
        context = {**context, **_base_slot_pool_identities(spellcasting, state or {}),
            "raw": (state or {}).get(SLOT_GRANTS_KEY, [])}
    raw = context["raw"]
    identities = [pool.get("id") for pool in raw
        if isinstance(pool, dict) and type(pool.get("id")) is str] if type(raw) is list else []
    claimed = set(identities)
    if destination is not None:
        claimed.add(destination)
    base_ids = set(context["base_pool_ids"])
    if authority is not None:
        base_ids.update(row.path[len("spell_slot:"):].rsplit(":", 1)[0]
            for row in authority.resource_statuses if row.path.startswith("spell_slot:")
            and not _is_slot_grant_status(row))
    return frozenset(set(context["base_conflict_ids"])
        | (claimed & base_ids)
        | {identity for identity in identities if identities.count(identity) > 1})


def grant_binding(authority, source_kind, source_key, owner=None):
    matches = [row for row in _grant_context(authority)["providers"]
        if row["source_kind"] == source_kind and row["source_key"] == source_key
        and (owner is None or row["owner"] == owner)]
    if len(matches) != 1:
        return None
    binding = matches[0]
    for path in binding["required_resources"]:
        kind, identifier = path.split(":", 1)
        if not authority.resource_status(kind, identifier).is_effective:
            return None
    return binding


def qualified_slot_grants(authority):
    context = _grant_context(authority)
    raw = context["raw"]
    if type(raw) is not list or any(not _valid_grant(pool) for pool in raw):
        return None
    if len({pool["id"] for pool in raw}) != len(raw):
        return None
    conflicts = slot_pool_identity_conflicts(authority)
    result = []
    for pool in raw:
        binding = grant_binding(authority, pool["source_kind"], pool["source_key"], pool["owner"])
        if (pool["id"] in conflicts or binding is None or any(pool[k] != binding[k] for k in
                ("id", "source_kind", "source_key", "owner", "basis", "lifecycle"))
                or any(slot["level"] not in binding["allowed_levels"] for slot in pool["slots"])):
            result.append((pool, None))
        else:
            result.append((pool, binding))
    return result


def slot_grant_destination_ready(authority, binding):
    if binding is None:
        return False
    current = grant_binding(authority, binding["source_kind"], binding["source_key"], binding["owner"])
    resolved = qualified_slot_grants(authority)
    return (current == binding and resolved is not None
        and binding["id"] not in slot_pool_identity_conflicts(authority, destination=binding["id"])
        and not any(pool["id"] == binding["id"] and source != binding for pool, source in resolved))


def bind_slot_grants(authority, definition, state, systems_service, proved_pools):
    # Providers authenticate real slot grants. Spell-specific free casts are
    # deliberately not a contribution source. Add future providers here only
    # with their own current source qualification and lifecycle contract.
    from .character_flexible_casting import qualify_rule, slot_provider
    rule = qualify_rule(authority, definition, systems_service, proved_pools.get("sorcery-points"))
    context = {**_base_slot_pool_identities(definition.spellcasting, state),
        "providers": [slot_provider(rule)] if rule is not None else [],
        "raw": deepcopy(state.get(SLOT_GRANTS_KEY, []))}
    if not context["providers"] and context["raw"] == []:
        return authority
    encoded = json.dumps(context, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return refresh_slot_grant_statuses(replace(authority, slot_grant_context_json=encoded))


def refresh_slot_grant_statuses(authority):
    from .character_source_authority import EffectiveStatus, VERIFIED, UNKNOWN, CONFLICT
    statuses = [row for row in authority.resource_statuses if not _is_slot_grant_status(row)]
    conflicts = slot_pool_identity_conflicts(authority)
    statuses = [replace(row, status=CONFLICT, effective=None, reason="slot_pool_identity_conflict")
        if row.path.startswith("spell_slot:") and row.path[len("spell_slot:"):].rsplit(":", 1)[0] in conflicts
        else row for row in statuses]
    resolved = qualified_slot_grants(authority)
    if resolved is None:
        raw = _grant_context(authority)["raw"]
        resolved = [(pool, None) for pool in raw if _valid_grant(pool)] if type(raw) is list else []
    for pool, binding in resolved:
        for slot in pool["slots"]:
            path = f"spell_slot:{pool['id']}:{slot['level']}"
            conflict = pool["id"] in conflicts
            effective = {**slot, "source_kind": pool["source_kind"], "source_key": pool["source_key"],
                "owner": pool["owner"], "source_basis_digest": pool["basis"], "lifecycle": pool["lifecycle"]}
            statuses.append(EffectiveStatus(path, CONFLICT if conflict else VERIFIED if binding is not None else UNKNOWN,
                deepcopy(pool), effective if binding is not None and not conflict else None,
                "qualified_slot_contribution" if binding is not None and not conflict else "slot_grant_owner_or_basis_unproven"))
    return replace(authority, resource_statuses=tuple(statuses))


def add_slot_grant_capacity(state, authority, binding, level):
    if not slot_grant_destination_ready(authority, binding) or level not in binding["allowed_levels"]:
        raise ValueError("The selected slot grant needs source or state repair.")
    result = deepcopy(state)
    pools = result.setdefault(SLOT_GRANTS_KEY, [])
    matches = [pool for pool in pools if pool["id"] == binding["id"]]
    if len(matches) > 1:
        raise ValueError("Slot grant identity is ambiguous.")
    if matches:
        pool = matches[0]
        if not any(original["id"] == pool["id"] and source is not None
                   for original, source in qualified_slot_grants(authority)):
            raise ValueError("A changed source cannot inherit existing granted capacity.")
    else:
        pool = {"schema_version": 1, **{key: binding[key] for key in
            ("id", "source_kind", "source_key", "owner", "basis", "lifecycle")}, "slots": []}
        pools.append(pool)
    slots = [slot for slot in pool["slots"] if slot["level"] == level]
    if slots:
        slots[0]["max"] += 1
    else:
        pool["slots"].append({"level": level, "max": 1, "used": 0})
        pool["slots"].sort(key=lambda row: row["level"])
    return result


def spend_slot_contribution(state, spellcasting, authority, pool_id, level, *, count=1):
    if type(count) is not int or count < 1:
        raise ValueError("Choose a positive number of slots to spend.")
    contributions = spell_slot_contributions(spellcasting, state, authority)
    matches = [slot for pool in contributions if pool["id"] == pool_id for slot in pool["slots"] if slot["level"] == level]
    if (len(matches) != 1 or not matches[0]["can_edit"] or matches[0]["available"] < count):
        raise ValueError("No matching qualified spell slots are available.")
    result = deepcopy(state)
    selected_pool = next(pool for pool in contributions if pool["id"] == pool_id)
    if selected_pool["source_kind"] != "class":
        rows = [slot for pool in result.get(SLOT_GRANTS_KEY, []) if pool["id"] == pool_id
            for slot in pool["slots"] if slot["level"] == level]
    else:
        rows = [slot for slot in result.get("spell_slots", []) if normalize_spell_slot_lane_id(slot.get("slot_lane_id")) == pool_id
            and slot.get("level") == level]
        if not rows and pool_id:
            rows = [slot for slot in result.get("spell_slots", []) if not normalize_spell_slot_lane_id(slot.get("slot_lane_id"))
                and slot.get("level") == level]
            if len(rows) == 1:
                rows[0]["slot_lane_id"] = pool_id
    if len(rows) != 1:
        raise ValueError("Spell-slot state is ambiguous. Refresh before spending.")
    rows[0]["used"] += count
    return result


def expire_slot_grants(state, authority):
    result = deepcopy(state)
    resolved = qualified_slot_grants(authority)
    if resolved is None:
        return result
    expired = {pool["id"] for pool, binding in resolved if binding is not None and binding["lifecycle"] == "expires_long_rest"}
    if expired:
        result[SLOT_GRANTS_KEY] = [deepcopy(pool) for pool in state.get(SLOT_GRANTS_KEY, []) if pool["id"] not in expired]
    return result


def require_slot_grants_preserved(prior, result):
    if (prior or {}).get(SLOT_GRANTS_KEY, []) != result.get(SLOT_GRANTS_KEY, []):
        raise ValueError("Slot contributions must be preserved outside their guarded state action.")


@dataclass(frozen=True, slots=True)
class SlotGrantIntent:
    before_digest: str
    after_digest: str
    params_json: str
    seal: object = field(repr=False)


def slot_grant_intent(prior, result, params):
    return SlotGrantIntent(slot_value_digest(prior), slot_value_digest(result),
        json.dumps(params, sort_keys=True, separators=(",", ":")), _GRANT_INTENT_SEAL)


def validate_slot_grant_transition(prior, result, definition, authority, intent):
    if intent is None:
        require_slot_grants_preserved(prior, result)
        return
    if (type(intent) is not SlotGrantIntent or intent.seal is not _GRANT_INTENT_SEAL
            or intent.before_digest != slot_value_digest(prior) or intent.after_digest != slot_value_digest(result)
            or authority is None or authority.state_digest != slot_value_digest(prior)):
        raise ValueError("Slot contribution intent changed before saving.")
    params = json.loads(intent.params_json)
    if params["kind"] == "flexible_casting":
        from .character_flexible_casting import apply_conversion
        expected = apply_conversion(prior, definition, authority, params)
        if expected != result:
            raise ValueError("Flexible Casting must be one exact atomic exchange.")
    elif params["kind"] == "spend":
        expected = spend_slot_contribution(prior, definition.spellcasting, authority,
            params["pool_id"], params["level"], count=params["count"])
        if expected != result:
            raise ValueError("Slot spending changed before saving.")
    elif params["kind"] == "long_rest":
        if expire_slot_grants(prior, authority).get(SLOT_GRANTS_KEY, []) != result.get(SLOT_GRANTS_KEY, []):
            raise ValueError("Long rest may expire only qualified temporary slot contributions.")
    else:
        raise ValueError("Unsupported slot contribution transition.")


def normalize_spell_slot_lane_id(value: Any) -> str:
    return str(value or "").strip()


def normalize_spell_slot_progression(raw_progression: Any) -> list[dict[str, int]]:
    progression: list[dict[str, int]] = []
    for raw_slot in list(raw_progression or []):
        slot = dict(raw_slot or {})
        level = int(slot.get("level") or 0)
        max_slots = int(slot.get("max_slots") or 0)
        if level <= 0:
            continue
        progression.append(
            {
                "level": level,
                "max_slots": max(0, max_slots),
            }
        )
    return progression


def spell_slot_lanes_from_spellcasting(spellcasting: dict[str, Any] | None) -> list[dict[str, Any]]:
    payload = dict(spellcasting or {})
    raw_lanes = [dict(lane or {}) for lane in list(payload.get("slot_lanes") or []) if isinstance(lane, dict)]
    if raw_lanes:
        lanes: list[dict[str, Any]] = []
        for index, raw_lane in enumerate(raw_lanes, start=1):
            lane_id = normalize_spell_slot_lane_id(
                raw_lane.get("id") or raw_lane.get("slot_lane_id") or f"slot-lane-{index}"
            )
            lanes.append(
                {
                    "id": lane_id,
                    "title": str(raw_lane.get("title") or "").strip() or "Spell slots",
                    "shared": bool(raw_lane.get("shared")),
                    "row_ids": [
                        str(row_id).strip()
                        for row_id in list(raw_lane.get("row_ids") or [])
                        if str(row_id).strip()
                    ],
                    "slot_progression": normalize_spell_slot_progression(raw_lane.get("slot_progression")),
                }
            )
        return lanes

    legacy_progression = normalize_spell_slot_progression(payload.get("slot_progression"))
    if not legacy_progression:
        return []
    return [
        {
            "id": DEFAULT_SPELL_SLOT_LANE_ID,
            "title": "Spell slots",
            "shared": False,
            "row_ids": [],
            "slot_progression": legacy_progression,
        }
    ]


def spell_slot_state_entries_from_spellcasting(spellcasting: dict[str, Any] | None) -> list[dict[str, int | str]]:
    entries: list[dict[str, int | str]] = []
    for lane in spell_slot_lanes_from_spellcasting(spellcasting):
        lane_id = normalize_spell_slot_lane_id(lane.get("id"))
        for slot in list(lane.get("slot_progression") or []):
            entry: dict[str, int | str] = {
                "level": int(slot.get("level") or 0),
                "max": int(slot.get("max_slots") or 0),
                "used": 0,
            }
            if lane_id:
                entry["slot_lane_id"] = lane_id
            entries.append(entry)
    return entries


def spell_slot_lane_title_map(spellcasting: dict[str, Any] | None) -> dict[str, str]:
    return {
        normalize_spell_slot_lane_id(lane.get("id")): str(lane.get("title") or "").strip() or "Spell slots"
        for lane in spell_slot_lanes_from_spellcasting(spellcasting)
    }


def spell_slot_contributions(spellcasting, state, authority=None):
    """One read model for source pools; aggregate totals never choose a spender."""
    existing = [row for row in state.get("spell_slots", []) if isinstance(row, dict)]
    conflicts = slot_pool_identity_conflicts(authority, spellcasting=spellcasting, state=state)
    result = []
    for lane in spell_slot_lanes_from_spellcasting(spellcasting):
        lane_id = lane["id"]
        slots = []
        for slot in lane["slot_progression"]:
            level = slot["level"]
            matches = [row for row in existing if row.get("level") == level
                and normalize_spell_slot_lane_id(row.get("slot_lane_id")) == lane_id]
            if not matches and lane_id:
                matches = [row for row in existing if row.get("level") == level and not normalize_spell_slot_lane_id(row.get("slot_lane_id"))]
            raw = matches[0] if len(matches) == 1 else {}
            status = authority.resource_status("spell_slot", f"{lane_id}:{level}") if authority is not None else None
            qualified = len(matches) <= 1 and (status is None or status.is_effective)
            maximum = status.effective.get("max") if status is not None and status.is_effective else slot["max_slots"]
            used = raw.get("used", 0)
            if type(used) is not int:
                qualified, used = False, 0
            qualified = qualified and type(maximum) is int and 0 <= used <= maximum
            label = {1: "1st level", 2: "2nd level", 3: "3rd level"}.get(level, f"{level}th level")
            slots.append({"level": level, "label": label, "slot_lane_id": lane_id, "used": used,
                "max": maximum if qualified else None, "raw_max": raw.get("max", slot["max_slots"]),
                "available": max(0, maximum - used) if qualified else None,
                "authority_status": status.status if status is not None else "VERIFIED", "can_edit": qualified,
                "is_granted": False})
        result.append({"id": lane_id, "title": lane["title"], "shared": lane["shared"], "row_ids": lane["row_ids"],
            "source_kind": "class", "lifecycle": "class_progression", "slots": slots, "needs_repair": False})
    raw_grants = state.get(SLOT_GRANTS_KEY, [])
    if type(raw_grants) is not list or any(not _valid_grant(pool) for pool in raw_grants):
        result.append({"id": "unresolved-slot-grants", "title": "Slot grants need repair", "source_kind": "unknown",
            "lifecycle": "unknown", "shared": False, "row_ids": [], "slots": [], "needs_repair": True})
    else:
        resolved = qualified_slot_grants(authority) or []
        proved = {pool["id"]: (pool, binding) for pool, binding in resolved if binding is not None}
        for pool in raw_grants:
            proof = proved.get(pool["id"])
            binding = proof[1] if proof is not None and proof[0] == pool else None
            slots = []
            for raw in pool["slots"]:
                status = authority.resource_status("spell_slot", f"{pool['id']}:{raw['level']}") if authority is not None else None
                qualified = status is not None and status.is_effective and binding is not None
                effective = status.effective if qualified else None
                slots.append({"level": raw["level"], "label": f"Level {raw['level']}", "slot_lane_id": pool["id"],
                    "used": raw["used"], "max": effective["max"] if qualified else None, "raw_max": raw["max"],
                    "available": effective["max"] - raw["used"] if qualified else None,
                    "authority_status": status.status if status is not None else "UNKNOWN", "can_edit": qualified,
                    "is_granted": True})
            result.append({"id": pool["id"], "title": binding["title"] if binding is not None else "Unqualified slot grant",
                "shared": False, "row_ids": [], "source_kind": pool["source_kind"], "source_key": pool["source_key"],
                "lifecycle": pool["lifecycle"], "slots": slots,
                "needs_repair": binding is None or any(not row["can_edit"] for row in slots)})
    for pool in result:
        if pool["id"] in conflicts:
            pool["needs_repair"] = True
            for slot in pool["slots"]:
                slot.update(can_edit=False, max=None, available=None, authority_status="CONFLICT")
    return result


def spell_slot_totals(contributions):
    unresolved = any(pool.get("needs_repair") and not pool["slots"] for pool in contributions)
    levels = sorted({slot["level"] for pool in contributions for slot in pool["slots"]})
    result = []
    for level in levels:
        rows = [slot for pool in contributions for slot in pool["slots"] if slot["level"] == level]
        qualified = not unresolved and all(row["can_edit"] for row in rows)
        result.append({"level": level, "max": sum(row["max"] for row in rows) if qualified else None,
            "available": sum(row["available"] for row in rows) if qualified else None, "qualified": qualified})
    return result


def spell_slot_options_from_contributions(contributions):
    return [{**slot, "level_label": slot["label"], "lane_title": pool["title"],
        "label": f"{pool['title']}: {slot['label']}", "selection": f"{pool['id']}|{slot['level']}"}
        for pool in contributions for slot in pool["slots"] if slot["can_edit"]]
