from __future__ import annotations

from typing import Any

from .xianxia_advancement import (
    XIANXIA_CONDITIONING_EFFORT_INCREASE,
    XIANXIA_CONDITIONING_HP_INCREASE,
    XIANXIA_CONDITIONING_HP_MAXIMUM,
    XIANXIA_CONDITIONING_INSIGHT_COST,
    XIANXIA_CULTIVATION_ENERGY_INSIGHT_COST,
    XIANXIA_MEDITATION_INSIGHT_COST,
    XIANXIA_TRAINING_ATTRIBUTE_INCREASE,
    XIANXIA_TRAINING_INSIGHT_COST,
    XIANXIA_TRAINING_STANCE_INCREASE,
    XIANXIA_TRAINING_STANCE_MAXIMUM,
    build_xianxia_realm_ascension_context,
    normalize_xianxia_martial_art_rank_key,
    rank_label as xianxia_martial_art_rank_label,
)


def present_xianxia_cultivation_context(
    character: dict[str, object],
    xianxia: dict[str, object],
    *,
    generic_technique_learning_options: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    xianxia_read = dict(character.get("xianxia_read") or {})
    resources = dict(xianxia_read.get("resources") or {})
    insight = dict(resources.get("insight") or {"available": 0, "spent": 0})
    insight_available = int(insight.get("available") or 0)
    energies = []
    for raw_energy in list(resources.get("energies") or []):
        if not isinstance(raw_energy, dict):
            continue
        energy = dict(raw_energy)
        energy["insight_cost"] = XIANXIA_CULTIVATION_ENERGY_INSIGHT_COST
        energy["has_enough_insight"] = insight_available >= XIANXIA_CULTIVATION_ENERGY_INSIGHT_COST
        energy["shortfall"] = max(0, XIANXIA_CULTIVATION_ENERGY_INSIGHT_COST - insight_available)
        energies.append(energy)
    yin_yang = []
    for raw_resource in list(resources.get("yin_yang") or []):
        if not isinstance(raw_resource, dict):
            continue
        resource = dict(raw_resource)
        resource["insight_cost"] = XIANXIA_MEDITATION_INSIGHT_COST
        resource["has_enough_insight"] = insight_available >= XIANXIA_MEDITATION_INSIGHT_COST
        resource["shortfall"] = max(0, XIANXIA_MEDITATION_INSIGHT_COST - insight_available)
        yin_yang.append(resource)
    hp_resource = {}
    for raw_resource in list(resources.get("durability") or []):
        if not isinstance(raw_resource, dict):
            continue
        if str(raw_resource.get("key") or "").strip() == "hp":
            hp_resource = dict(raw_resource)
            break
    hp_maximum = int(hp_resource.get("max") or 0) if hp_resource else 0
    hp_projected_maximum = min(
        XIANXIA_CONDITIONING_HP_MAXIMUM,
        hp_maximum + XIANXIA_CONDITIONING_HP_INCREASE,
    )
    conditioning_hp = {
        "key": "hp",
        "label": "HP",
        "current": int(hp_resource.get("current") or 0) if hp_resource else 0,
        "max": hp_maximum,
        "cap": XIANXIA_CONDITIONING_HP_MAXIMUM,
        "insight_cost": XIANXIA_CONDITIONING_INSIGHT_COST,
        "hp_increase": max(0, hp_projected_maximum - hp_maximum),
        "projected_max": hp_projected_maximum,
        "has_enough_insight": insight_available >= XIANXIA_CONDITIONING_INSIGHT_COST,
        "shortfall": max(0, XIANXIA_CONDITIONING_INSIGHT_COST - insight_available),
        "can_increase": hp_maximum < XIANXIA_CONDITIONING_HP_MAXIMUM,
    }
    conditioning_efforts = []
    for raw_effort in list(xianxia_read.get("efforts") or []):
        if not isinstance(raw_effort, dict):
            continue
        effort = dict(raw_effort)
        effort["insight_cost"] = XIANXIA_CONDITIONING_INSIGHT_COST
        effort["effort_increase"] = XIANXIA_CONDITIONING_EFFORT_INCREASE
        effort["has_enough_insight"] = insight_available >= XIANXIA_CONDITIONING_INSIGHT_COST
        effort["shortfall"] = max(0, XIANXIA_CONDITIONING_INSIGHT_COST - insight_available)
        conditioning_efforts.append(effort)
    stance_resource = {}
    for raw_resource in list(resources.get("durability") or []):
        if not isinstance(raw_resource, dict):
            continue
        if str(raw_resource.get("key") or "").strip() == "stance":
            stance_resource = dict(raw_resource)
            break
    stance_maximum = int(stance_resource.get("max") or 0) if stance_resource else 0
    stance_projected_maximum = min(
        XIANXIA_TRAINING_STANCE_MAXIMUM,
        stance_maximum + XIANXIA_TRAINING_STANCE_INCREASE,
    )
    training_stance = {
        "key": "stance",
        "label": "Stance",
        "current": int(stance_resource.get("current") or 0) if stance_resource else 0,
        "max": stance_maximum,
        "cap": XIANXIA_TRAINING_STANCE_MAXIMUM,
        "insight_cost": XIANXIA_TRAINING_INSIGHT_COST,
        "stance_increase": max(0, stance_projected_maximum - stance_maximum),
        "projected_max": stance_projected_maximum,
        "has_enough_insight": insight_available >= XIANXIA_TRAINING_INSIGHT_COST,
        "shortfall": max(0, XIANXIA_TRAINING_INSIGHT_COST - insight_available),
        "can_increase": stance_maximum < XIANXIA_TRAINING_STANCE_MAXIMUM,
    }
    training_attributes = []
    for raw_attribute in list(xianxia_read.get("attributes") or []):
        if not isinstance(raw_attribute, dict):
            continue
        attribute = dict(raw_attribute)
        attribute["insight_cost"] = XIANXIA_TRAINING_INSIGHT_COST
        attribute["attribute_increase"] = XIANXIA_TRAINING_ATTRIBUTE_INCREASE
        attribute["has_enough_insight"] = insight_available >= XIANXIA_TRAINING_INSIGHT_COST
        attribute["shortfall"] = max(0, XIANXIA_TRAINING_INSIGHT_COST - insight_available)
        training_attributes.append(attribute)
    martial_arts = []
    for index, raw_art in enumerate(list(xianxia_read.get("martial_arts") or [])):
        art = dict(raw_art or {}) if isinstance(raw_art, dict) else {}
        art["index"] = index
        art["advancement"] = _xianxia_martial_art_advancement_context(
            art,
            insight_available=insight_available,
        )
        martial_arts.append(art)
    generic_technique_options = []
    for raw_option in list(generic_technique_learning_options or []):
        if not isinstance(raw_option, dict):
            continue
        option = dict(raw_option)
        insight_cost = int(option.get("insight_cost") or 0)
        option["has_enough_insight"] = insight_cost > 0 and insight_available >= insight_cost
        option["shortfall"] = max(0, insight_cost - insight_available)
        generic_technique_options.append(option)
    history_records = []
    for index, raw_record in enumerate(list(xianxia.get("advancement_history") or []), start=1):
        if not isinstance(raw_record, dict):
            continue
        action = str(raw_record.get("action") or raw_record.get("type") or "advancement").strip()
        details = []
        for key, label in (
            ("amount", "Amount"),
            ("insight_available_before", "Available Insight before"),
            ("insight_available_after", "Available Insight after"),
            ("insight_available_delta", "Available Insight change"),
            ("insight_spent_before", "Spent Insight before"),
            ("insight_spent_after", "Spent Insight after"),
            ("insight_spent_delta", "Spent Insight change"),
            ("downtime", "Downtime"),
            ("target", "Target"),
            ("energy_key", "Energy key"),
            ("energy_maximum_increase", "Energy maximum increase"),
            ("new_energy_maximum", "New Energy maximum"),
            ("yin_yang_key", "Yin/Yang key"),
            ("yin_yang_maximum_increase", "Yin/Yang maximum increase"),
            ("new_yin_yang_maximum", "New Yin/Yang maximum"),
            ("hp_maximum_increase", "HP maximum increase"),
            ("new_hp_maximum", "New HP maximum"),
            ("hp_maximum_cap", "HP maximum cap"),
            ("effort_key", "Effort key"),
            ("effort_point_increase", "Effort point increase"),
            ("new_effort_score", "New Effort score"),
            ("stance_maximum_increase", "Stance maximum increase"),
            ("new_stance_maximum", "New Stance maximum"),
            ("stance_maximum_cap", "Stance maximum cap"),
            ("attribute_key", "Attribute key"),
            ("attribute_point_increase", "Attribute point increase"),
            ("new_attribute_score", "New Attribute score"),
            ("rank", "Rank"),
            ("systems_ref", "Systems ref"),
            ("generic_technique_key", "Generic Technique key"),
            ("insight_cost", "Insight cost"),
            ("teacher_breakthrough_note", "Teacher/breakthrough note"),
            ("legendary_prerequisite_note", "Legendary requirement"),
            ("legendary_quest_note", "Legendary quest/mythic-master note"),
            ("current_realm", "Current Realm"),
            ("target_realm", "Target Realm"),
            ("status", "Status"),
            ("seclusion_time", "Seclusion time"),
            ("rebuild_budget", "Rebuild budget"),
            ("base_rebuild_budget", "Base rebuild budget"),
            ("stat_cap", "Stat cap"),
            ("actions_per_turn", "Actions per turn"),
            ("attributes_before_total", "Attributes before total"),
            ("attributes_after_total", "Attributes after total"),
            ("efforts_before_total", "Efforts before total"),
            ("efforts_after_total", "Efforts after total"),
            ("total_rebuild_points", "Total rebuild points"),
            ("hp_stance_trade_points", "HP/Stance trade points"),
            ("hp_maximum_trade", "HP maximum traded"),
            ("stance_maximum_trade", "Stance maximum traded"),
            ("hp_maximum_before", "HP maximum before"),
            ("hp_maximum_after", "HP maximum after"),
            ("stance_maximum_before", "Stance maximum before"),
            ("stance_maximum_after", "Stance maximum after"),
            ("reset_scope", "Reset scope"),
            ("preserved_scope", "Preserved scope"),
            ("pre_ascension_summary", "Pre-ascension state"),
            ("post_ascension_summary", "Post-ascension state"),
            ("gm_review_note", "GM review note"),
            ("gm_confirmation_note", "GM confirmation note"),
            ("seclusion_notes", "Seclusion notes"),
            ("hp_stance_trade_notes", "HP/Stance trade notes"),
            ("confirmed_realm", "Confirmed Realm"),
            ("confirmed_rebuild_action", "Confirmed rebuild action"),
            ("notes", "Notes"),
        ):
            value = raw_record.get(key)
            if isinstance(value, dict):
                value = value.get("title") or value.get("slug") or value.get("entry_key")
            cleaned = "" if value is None else str(value).strip()
            if cleaned:
                details.append({"label": label, "value": cleaned})
        history_records.append(
            {
                "index": index,
                "action": action.replace("_", " ").title() if action else "Advancement",
                "details": details,
            }
        )

    return {
        "insight": insight,
        "energies": energies,
        "yin_yang": yin_yang,
        "conditioning": {
            "hp": conditioning_hp,
            "efforts": conditioning_efforts,
        },
        "training": {
            "stance": training_stance,
            "attributes": training_attributes,
        },
        "martial_arts": martial_arts,
        "generic_techniques": list(xianxia_read.get("generic_techniques") or []),
        "generic_technique_options": generic_technique_options,
        "realm_ascension": build_xianxia_realm_ascension_context(xianxia),
        "history": history_records,
    }


def update_xianxia_insight_definition(definition: Any, *, available: int, spent: int):
    payload = definition.to_dict()
    xianxia = dict(payload.get("xianxia") or {})
    previous_insight = dict(xianxia.get("insight") or {})
    previous_available = int(previous_insight.get("available") or 0)
    previous_spent = int(previous_insight.get("spent") or 0)
    new_available = int(available)
    new_spent = int(spent)
    xianxia["insight"] = {
        "available": new_available,
        "spent": new_spent,
    }
    if new_available != previous_available or new_spent != previous_spent:
        history = [
            dict(record)
            for record in list(xianxia.get("advancement_history") or [])
            if isinstance(record, dict) and record
        ]
        history.append(
            {
                "action": "insight_counter_adjustment",
                "target": "Insight",
                "insight_available_before": previous_available,
                "insight_available_after": new_available,
                "insight_available_delta": new_available - previous_available,
                "insight_spent_before": previous_spent,
                "insight_spent_after": new_spent,
                "insight_spent_delta": new_spent - previous_spent,
            }
        )
        xianxia["advancement_history"] = history
    payload["xianxia"] = xianxia
    return definition.__class__.from_dict(payload)


def update_xianxia_gathering_insight_definition(
    definition: Any,
    *,
    amount: int,
    downtime: str = "",
    notes: str = "",
):
    gain_amount = int(amount)
    if gain_amount <= 0:
        raise ValueError("Gathered Insight must be at least 1.")

    payload = definition.to_dict()
    xianxia = dict(payload.get("xianxia") or {})
    insight = dict(xianxia.get("insight") or {})
    available = int(insight.get("available") or 0)
    spent = int(insight.get("spent") or 0)
    new_available = available + gain_amount
    xianxia["insight"] = {
        "available": new_available,
        "spent": spent,
    }

    history = [
        dict(record)
        for record in list(xianxia.get("advancement_history") or [])
        if isinstance(record, dict) and record
    ]
    event = {
        "action": "gathering_insight",
        "amount": gain_amount,
        "target": "Insight",
    }
    clean_downtime = " ".join(str(downtime or "").split()).strip()
    if clean_downtime:
        event["downtime"] = clean_downtime
    clean_notes = str(notes or "").strip()
    if clean_notes:
        event["notes"] = clean_notes
    history.append(event)
    xianxia["advancement_history"] = history

    payload["xianxia"] = xianxia
    return definition.__class__.from_dict(payload)


def _xianxia_martial_art_advancement_context(
    art: dict[str, object],
    *,
    insight_available: int,
) -> dict[str, object]:
    rank_progress = dict(art.get("rank_progress") or {})
    steps = [
        dict(step)
        for step in list(rank_progress.get("steps") or [])
        if isinstance(step, dict)
    ]
    next_step = None
    for step in steps:
        if bool(step.get("is_learned")):
            continue
        next_step = step
        break
    if not next_step:
        return {
            "status": "complete",
            "message": "No further structured rank is currently available.",
        }
    if bool(next_step.get("is_incomplete")):
        return {
            "status": "incomplete",
            "message": "The next higher rank is marked as intentional draft content.",
        }

    next_rank_key = normalize_xianxia_martial_art_rank_key(next_step.get("key"))

    insight_cost = int(next_step.get("insight_cost") or 0)
    has_enough_insight = insight_cost > 0 and insight_available >= insight_cost
    return {
        "status": "available",
        "next_rank_key": next_rank_key,
        "next_rank_label": str(
            next_step.get("label") or xianxia_martial_art_rank_label(next_rank_key)
        ),
        "insight_cost": insight_cost,
        "has_enough_insight": has_enough_insight,
        "shortfall": max(0, insight_cost - insight_available),
        "teacher_breakthrough_requirement": str(
            next_step.get("teacher_breakthrough_requirement") or ""
        ).strip(),
        "teacher_breakthrough_note": str(
            next_step.get("teacher_breakthrough_note") or ""
        ).strip(),
        "requires_legendary_note": next_rank_key == "legendary",
        "legendary_prerequisite_note": str(
            next_step.get("legendary_prerequisite_note") or ""
        ).strip(),
    }
