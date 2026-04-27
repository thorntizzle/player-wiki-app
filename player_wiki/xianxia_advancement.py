from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .xianxia_character_model import (
    XIANXIA_ATTRIBUTE_KEYS,
    XIANXIA_ATTRIBUTE_LABELS,
    XIANXIA_EFFORT_KEYS,
    XIANXIA_EFFORT_LABELS,
    XIANXIA_ENERGY_KEYS,
)


XIANXIA_CULTIVATION_ENERGY_INSIGHT_COST = 1
XIANXIA_MEDITATION_INSIGHT_COST = 1
XIANXIA_CONDITIONING_INSIGHT_COST = 1
XIANXIA_CONDITIONING_HP_INCREASE = 10
XIANXIA_CONDITIONING_HP_MAXIMUM = 50
XIANXIA_CONDITIONING_EFFORT_INCREASE = 2
XIANXIA_TRAINING_INSIGHT_COST = 1
XIANXIA_TRAINING_STANCE_INCREASE = 10
XIANXIA_TRAINING_STANCE_MAXIMUM = 50
XIANXIA_TRAINING_ATTRIBUTE_INCREASE = 2
XIANXIA_DIRECT_ADVANCEMENT_GENERIC_TECHNIQUE_KEYS = frozenset(
    {"cultivation", "meditation", "conditioning", "training"}
)
XIANXIA_MARTIAL_ART_RANK_KEYS = (
    "initiate",
    "novice",
    "apprentice",
    "master",
    "legendary",
)
XIANXIA_MARTIAL_ART_RANK_LABELS = {
    "initiate": "Initiate",
    "novice": "Novice",
    "apprentice": "Apprentice",
    "master": "Master",
    "legendary": "Legendary",
}
XIANXIA_ENERGY_LABELS = {
    "jing": "Jing",
    "qi": "Qi",
    "shen": "Shen",
}
XIANXIA_YIN_YANG_KEYS = ("yin", "yang")
XIANXIA_YIN_YANG_LABELS = {
    "yin": "Yin",
    "yang": "Yang",
}
XIANXIA_REALM_ASCENSION_REALMS = ("Mortal", "Immortal", "Divine")
XIANXIA_REALM_ASCENSION_TARGETS = {
    "Mortal": {
        "target_realm": "Immortal",
        "seclusion_time": "1 year",
        "rebuild_budget": 15,
        "stat_cap": 6,
        "actions_per_turn": 3,
        "stat_max_prerequisite": 10,
    },
    "Immortal": {
        "target_realm": "Divine",
        "seclusion_time": "100 years",
        "rebuild_budget": 25,
        "stat_cap": 12,
        "actions_per_turn": 4,
        "stat_max_prerequisite": 15,
    },
}
XIANXIA_REALM_ASCENSION_REBUILD_ACTIONS = {
    "Immortal": "realm_ascension_immortal_rebuild_applied",
    "Divine": "realm_ascension_divine_rebuild_applied",
}
XIANXIA_REALM_ASCENSION_TRADE_UNIT = 10


@dataclass(frozen=True)
class XianxiaRealmAscensionReviewResult:
    definition: Any
    current_realm: str
    target_realm: str
    seclusion_time: str
    rebuild_budget: int
    stat_cap: int
    actions_per_turn: int
    stat_max_prerequisite: dict[str, Any]
    gm_review_note: str
    seclusion_notes: str = ""
    hp_stance_trade_notes: str = ""


@dataclass(frozen=True)
class XianxiaRealmAscensionStatResetResult:
    definition: Any
    current_realm: str
    target_realm: str
    attributes_before_total: int
    efforts_before_total: int
    notes: str = ""


@dataclass(frozen=True)
class XianxiaRealmAscensionImmortalRebuildResult:
    definition: Any
    current_realm: str
    target_realm: str
    rebuild_budget: int
    stat_cap: int
    actions_per_turn: int
    attribute_total: int
    effort_total: int
    total_rebuild_points: int
    notes: str = ""
    hp_maximum_trade: int = 0
    stance_maximum_trade: int = 0
    hp_stance_trade_points: int = 0
    hp_maximum_before: int = 0
    hp_maximum_after: int = 0
    stance_maximum_before: int = 0
    stance_maximum_after: int = 0


@dataclass(frozen=True)
class XianxiaRealmAscensionConfirmationResult:
    definition: Any
    current_realm: str
    target_realm: str
    gm_confirmation_note: str


@dataclass(frozen=True)
class XianxiaMartialArtAdvanceResult:
    definition: Any
    martial_art_name: str
    rank_name: str
    insight_cost: int
    energy_maximum_increases: dict[str, int]
    teacher_breakthrough_requirement: str
    teacher_breakthrough_note: str
    legendary_quest_note: str = ""
    legendary_prerequisite_note: str = ""


@dataclass(frozen=True)
class XianxiaCultivationEnergySpendResult:
    definition: Any
    energy_key: str
    energy_name: str
    insight_cost: int
    new_maximum: int
    notes: str = ""


@dataclass(frozen=True)
class XianxiaMeditationSpendResult:
    definition: Any
    yin_yang_key: str
    yin_yang_name: str
    insight_cost: int
    new_maximum: int
    notes: str = ""


@dataclass(frozen=True)
class XianxiaConditioningSpendResult:
    definition: Any
    target_kind: str
    target_key: str
    target_name: str
    insight_cost: int
    increase: int
    new_value: int
    notes: str = ""


@dataclass(frozen=True)
class XianxiaTrainingSpendResult:
    definition: Any
    target_kind: str
    target_key: str
    target_name: str
    insight_cost: int
    increase: int
    new_value: int
    notes: str = ""


@dataclass(frozen=True)
class XianxiaGenericTechniqueLearnResult:
    definition: Any
    technique_name: str
    insight_cost: int
    systems_ref: dict[str, str]
    notes: str = ""


def build_xianxia_realm_ascension_context(xianxia: dict[str, Any]) -> dict[str, Any]:
    payload = dict(xianxia or {})
    history = payload.get("advancement_history")
    current_realm = normalize_xianxia_realm_label(payload.get("realm"))
    target = _realm_ascension_target_for_current(current_realm)
    latest_review = _latest_realm_ascension_review(history)
    latest_reset = _latest_realm_ascension_stat_reset(history)
    latest_rebuild = _latest_realm_ascension_rebuild(history)
    pending_confirmation_rebuild = _latest_unconfirmed_realm_ascension_rebuild(
        history
    )
    latest_confirmation = _latest_realm_ascension_confirmation(history)
    latest_immortal_rebuild = _latest_realm_ascension_rebuild(
        history,
        target_realm="Immortal",
    )
    latest_divine_rebuild = _latest_realm_ascension_rebuild(
        history,
        target_realm="Divine",
    )
    attributes = _stat_rows(
        payload.get("attributes"),
        XIANXIA_ATTRIBUTE_KEYS,
        XIANXIA_ATTRIBUTE_LABELS,
    )
    efforts = _stat_rows(
        payload.get("efforts"),
        XIANXIA_EFFORT_KEYS,
        XIANXIA_EFFORT_LABELS,
    )
    durability = _durability_maxima(payload.get("durability"))
    stat_prerequisite = _realm_ascension_stat_prerequisite(
        current_realm=current_realm,
        target=target,
        attribute_rows=attributes["rows"],
        effort_rows=efforts["rows"],
    )
    context = {
        "current_realm": current_realm,
        "available": target is not None,
        "target": dict(target or {}),
        "attributes": attributes,
        "efforts": efforts,
        "stat_prerequisite": stat_prerequisite,
        "can_start_review": (
            target is not None
            and bool(stat_prerequisite.get("is_met"))
            and pending_confirmation_rebuild is None
        ),
        "latest_review": latest_review,
        "latest_reset": latest_reset,
        "latest_rebuild": latest_rebuild,
        "pending_confirmation_rebuild": pending_confirmation_rebuild,
        "latest_confirmation": latest_confirmation,
        "latest_immortal_rebuild": latest_immortal_rebuild,
        "latest_divine_rebuild": latest_divine_rebuild,
        "hp_stance_trade": _realm_ascension_trade_context(durability),
    }
    context["can_confirm_rebuild"] = pending_confirmation_rebuild is not None
    if pending_confirmation_rebuild is not None:
        context["confirmation_blocking_message"] = (
            "Confirm the latest Realm rebuild before starting another Realm review."
        )
    context["can_reset_stats"] = _can_reset_realm_ascension_stats(
        latest_review=latest_review,
        latest_reset=latest_reset,
        target=target,
    )
    context["can_apply_rebuild"] = _can_apply_realm_rebuild(
        latest_review=latest_review,
        latest_reset=latest_reset,
        latest_target_rebuild=_latest_realm_ascension_rebuild(
            history,
            target_realm=str((target or {}).get("target_realm") or ""),
        ),
        target=target,
    )
    context["can_apply_immortal_rebuild"] = (
        bool(context["can_apply_rebuild"])
        and str((target or {}).get("target_realm") or "").strip() == "Immortal"
    )
    context["can_apply_divine_rebuild"] = (
        bool(context["can_apply_rebuild"])
        and str((target or {}).get("target_realm") or "").strip() == "Divine"
    )
    if target is None:
        context["message"] = "No further Realm ascension target is defined for this character."
    return context


def start_xianxia_realm_ascension_review_definition(
    definition: Any,
    *,
    target_realm: str,
    gm_review_note: str,
    seclusion_notes: str = "",
    hp_stance_trade_notes: str = "",
) -> XianxiaRealmAscensionReviewResult:
    payload = definition.to_dict()
    xianxia = dict(payload.get("xianxia") or {})
    current_realm = normalize_xianxia_realm_label(xianxia.get("realm"))
    target = _realm_ascension_target_for_current(current_realm)
    if target is None:
        raise ValueError(
            f"{current_realm} characters do not have a further Realm ascension target."
        )

    normalized_target_realm = normalize_xianxia_realm_label(target_realm)
    expected_target_realm = str(target["target_realm"])
    if normalized_target_realm != expected_target_realm:
        raise ValueError(
            f"Realm ascension must move from {current_realm} to {expected_target_realm}."
        )

    stat_prerequisite = _realm_ascension_stat_prerequisite(
        current_realm=current_realm,
        target=target,
        attribute_rows=_stat_rows(
            xianxia.get("attributes"),
            XIANXIA_ATTRIBUTE_KEYS,
            XIANXIA_ATTRIBUTE_LABELS,
        )["rows"],
        effort_rows=_stat_rows(
            xianxia.get("efforts"),
            XIANXIA_EFFORT_KEYS,
            XIANXIA_EFFORT_LABELS,
        )["rows"],
    )
    if not bool(stat_prerequisite.get("is_met")):
        raise ValueError(str(stat_prerequisite["failure_message"]))

    clean_gm_review_note = _clean_note(gm_review_note)
    if not clean_gm_review_note:
        raise ValueError("Record a GM review note before starting Realm ascension review.")
    clean_seclusion_notes = _clean_note(seclusion_notes)
    clean_hp_stance_trade_notes = _clean_note(hp_stance_trade_notes)

    history = [
        dict(record)
        for record in list(xianxia.get("advancement_history") or [])
        if isinstance(record, dict) and record
    ]
    if _latest_unconfirmed_realm_ascension_rebuild(history) is not None:
        raise ValueError(
            "Confirm the latest Realm rebuild before starting another Realm review."
        )
    event = {
        "action": "realm_ascension_review_started",
        "target": expected_target_realm,
        "current_realm": current_realm,
        "target_realm": expected_target_realm,
        "status": "pending_gm_review",
        "seclusion_time": str(target["seclusion_time"]),
        "rebuild_budget": int(target["rebuild_budget"]),
        "stat_cap": int(target["stat_cap"]),
        "actions_per_turn": int(target["actions_per_turn"]),
        "stat_max_prerequisite": {
            "required_score": int(stat_prerequisite["required_score"]),
            "met": True,
            "stat_kind": str(stat_prerequisite["met_by"]["kind"]),
            "stat_key": str(stat_prerequisite["met_by"]["key"]),
            "stat_label": str(stat_prerequisite["met_by"]["label"]),
            "stat_score": int(stat_prerequisite["met_by"]["score"]),
        },
        "gm_review_note": clean_gm_review_note,
    }
    if clean_seclusion_notes:
        event["seclusion_notes"] = clean_seclusion_notes
    if clean_hp_stance_trade_notes:
        event["hp_stance_trade_notes"] = clean_hp_stance_trade_notes
    history.append(event)
    xianxia["advancement_history"] = history
    payload["xianxia"] = xianxia

    return XianxiaRealmAscensionReviewResult(
        definition=definition.__class__.from_dict(payload),
        current_realm=current_realm,
        target_realm=expected_target_realm,
        seclusion_time=str(target["seclusion_time"]),
        rebuild_budget=int(target["rebuild_budget"]),
        stat_cap=int(target["stat_cap"]),
        actions_per_turn=int(target["actions_per_turn"]),
        stat_max_prerequisite=dict(event["stat_max_prerequisite"]),
        gm_review_note=clean_gm_review_note,
        seclusion_notes=clean_seclusion_notes,
        hp_stance_trade_notes=clean_hp_stance_trade_notes,
    )


def confirm_xianxia_realm_ascension_definition(
    definition: Any,
    *,
    target_realm: str,
    gm_confirmation_note: str,
) -> XianxiaRealmAscensionConfirmationResult:
    payload = definition.to_dict()
    xianxia = dict(payload.get("xianxia") or {})
    current_realm = normalize_xianxia_realm_label(xianxia.get("realm"))
    normalized_target_realm = normalize_xianxia_realm_label(target_realm)
    clean_gm_confirmation_note = _clean_note(gm_confirmation_note)
    if not clean_gm_confirmation_note:
        raise ValueError(
            "Record a GM confirmation note before confirming Realm ascension."
        )

    history = [
        dict(record)
        for record in list(xianxia.get("advancement_history") or [])
        if isinstance(record, dict) and record
    ]
    rebuild_index = _latest_unconfirmed_realm_ascension_rebuild_index(
        history,
        target_realm=normalized_target_realm,
    )
    if rebuild_index is None:
        raise ValueError(
            "Apply a pending Realm rebuild before recording GM confirmation."
        )
    rebuild_event = dict(history[rebuild_index])
    confirmed_target_realm = normalize_xianxia_realm_label(
        rebuild_event.get("target_realm") or rebuild_event.get("target")
    )
    if normalized_target_realm and normalized_target_realm != confirmed_target_realm:
        raise ValueError(
            f"GM confirmation target must match the pending {confirmed_target_realm} rebuild."
        )
    if current_realm != confirmed_target_realm:
        raise ValueError(
            f"GM confirmation for {confirmed_target_realm} requires the character "
            f"to already be in the {confirmed_target_realm} Realm."
        )

    rebuild_event["status"] = "confirmed"
    history[rebuild_index] = rebuild_event
    event = {
        "action": "realm_ascension_gm_confirmation_recorded",
        "target": confirmed_target_realm,
        "current_realm": str(rebuild_event.get("current_realm") or "").strip(),
        "target_realm": confirmed_target_realm,
        "confirmed_realm": confirmed_target_realm,
        "status": "confirmed",
        "confirmed_rebuild_action": str(rebuild_event.get("action") or "").strip(),
        "confirmed_rebuild_index": rebuild_index,
        "actions_per_turn": _non_negative_int(
            rebuild_event.get("actions_per_turn"),
            default=0,
        ),
        "attributes_after_total": _non_negative_int(
            rebuild_event.get("attributes_after_total"),
            default=0,
        ),
        "efforts_after_total": _non_negative_int(
            rebuild_event.get("efforts_after_total"),
            default=0,
        ),
        "gm_confirmation_note": clean_gm_confirmation_note,
    }
    post_ascension_summary = str(
        rebuild_event.get("post_ascension_summary") or ""
    ).strip()
    if post_ascension_summary:
        event["post_ascension_summary"] = post_ascension_summary
    history.append(event)
    xianxia["advancement_history"] = history
    payload["xianxia"] = xianxia

    return XianxiaRealmAscensionConfirmationResult(
        definition=definition.__class__.from_dict(payload),
        current_realm=str(rebuild_event.get("current_realm") or "").strip(),
        target_realm=confirmed_target_realm,
        gm_confirmation_note=clean_gm_confirmation_note,
    )


def reset_xianxia_realm_ascension_stats_definition(
    definition: Any,
    *,
    target_realm: str,
    notes: str = "",
) -> XianxiaRealmAscensionStatResetResult:
    payload = definition.to_dict()
    xianxia = dict(payload.get("xianxia") or {})
    current_realm = normalize_xianxia_realm_label(xianxia.get("realm"))
    target = _realm_ascension_target_for_current(current_realm)
    if target is None:
        raise ValueError(
            f"{current_realm} characters do not have a further Realm ascension target."
        )

    normalized_target_realm = normalize_xianxia_realm_label(target_realm)
    expected_target_realm = str(target["target_realm"])
    if normalized_target_realm != expected_target_realm:
        raise ValueError(
            f"Realm ascension must move from {current_realm} to {expected_target_realm}."
        )

    history = [
        dict(record)
        for record in list(xianxia.get("advancement_history") or [])
        if isinstance(record, dict) and record
    ]
    review_index = _latest_realm_ascension_review_index(
        history,
        current_realm=current_realm,
        target_realm=expected_target_realm,
    )
    if review_index is None:
        raise ValueError(
            "Start a pending Realm ascension review before resetting Attributes and Efforts."
        )
    if _has_realm_ascension_stat_reset_after(history, review_index):
        raise ValueError(
            "Attributes and Efforts have already been reset for this Realm ascension review."
        )

    attributes_before = _stat_rows(
        xianxia.get("attributes"),
        XIANXIA_ATTRIBUTE_KEYS,
        XIANXIA_ATTRIBUTE_LABELS,
    )
    efforts_before = _stat_rows(
        xianxia.get("efforts"),
        XIANXIA_EFFORT_KEYS,
        XIANXIA_EFFORT_LABELS,
    )
    pre_ascension_state = _realm_ascension_history_snapshot(xianxia)
    pre_ascension_summary = _realm_ascension_history_snapshot_summary(
        pre_ascension_state
    )
    xianxia["attributes"] = {key: 0 for key in XIANXIA_ATTRIBUTE_KEYS}
    xianxia["efforts"] = {key: 0 for key in XIANXIA_EFFORT_KEYS}

    clean_notes = _clean_note(notes)
    event = {
        "action": "realm_ascension_attributes_efforts_reset",
        "target": expected_target_realm,
        "current_realm": current_realm,
        "target_realm": expected_target_realm,
        "status": "pending_rebuild",
        "attributes_before_total": int(attributes_before["total"]),
        "attributes_after_total": 0,
        "efforts_before_total": int(efforts_before["total"]),
        "efforts_after_total": 0,
        "reset_scope": "Attributes and Efforts",
        "preserved_scope": (
            "Energies, Yin/Yang, HP, Stance, Insight, Martial Arts, "
            "Generic Techniques, variants, approval records, and notes"
        ),
        "pre_ascension_summary": pre_ascension_summary,
        "pre_ascension_state": pre_ascension_state,
    }
    if clean_notes:
        event["notes"] = clean_notes
    history.append(event)
    xianxia["advancement_history"] = history
    payload["xianxia"] = xianxia

    return XianxiaRealmAscensionStatResetResult(
        definition=definition.__class__.from_dict(payload),
        current_realm=current_realm,
        target_realm=expected_target_realm,
        attributes_before_total=int(attributes_before["total"]),
        efforts_before_total=int(efforts_before["total"]),
        notes=clean_notes,
    )


def apply_xianxia_immortal_realm_rebuild_definition(
    definition: Any,
    *,
    target_realm: str,
    attribute_scores: dict[str, Any],
    effort_scores: dict[str, Any],
    hp_maximum_trade: Any = 0,
    stance_maximum_trade: Any = 0,
    notes: str = "",
) -> XianxiaRealmAscensionImmortalRebuildResult:
    return _apply_xianxia_realm_rebuild_definition(
        definition,
        target_realm=target_realm,
        attribute_scores=attribute_scores,
        effort_scores=effort_scores,
        hp_maximum_trade=hp_maximum_trade,
        stance_maximum_trade=stance_maximum_trade,
        notes=notes,
        expected_current_realm="Mortal",
        expected_target_realm="Immortal",
    )


def apply_xianxia_divine_realm_rebuild_definition(
    definition: Any,
    *,
    target_realm: str,
    attribute_scores: dict[str, Any],
    effort_scores: dict[str, Any],
    hp_maximum_trade: Any = 0,
    stance_maximum_trade: Any = 0,
    notes: str = "",
) -> XianxiaRealmAscensionImmortalRebuildResult:
    return _apply_xianxia_realm_rebuild_definition(
        definition,
        target_realm=target_realm,
        attribute_scores=attribute_scores,
        effort_scores=effort_scores,
        hp_maximum_trade=hp_maximum_trade,
        stance_maximum_trade=stance_maximum_trade,
        notes=notes,
        expected_current_realm="Immortal",
        expected_target_realm="Divine",
    )


def _apply_xianxia_realm_rebuild_definition(
    definition: Any,
    *,
    target_realm: str,
    attribute_scores: dict[str, Any],
    effort_scores: dict[str, Any],
    hp_maximum_trade: Any = 0,
    stance_maximum_trade: Any = 0,
    notes: str = "",
    expected_current_realm: str,
    expected_target_realm: str,
) -> XianxiaRealmAscensionImmortalRebuildResult:
    payload = definition.to_dict()
    xianxia = dict(payload.get("xianxia") or {})
    current_realm = normalize_xianxia_realm_label(xianxia.get("realm"))
    target = _realm_ascension_target_for_current(current_realm)
    if target is None:
        raise ValueError(
            f"{current_realm} characters do not have a Realm rebuild target."
        )

    normalized_target_realm = normalize_xianxia_realm_label(target_realm)
    target_realm_for_current = str(target["target_realm"])
    if (
        current_realm != expected_current_realm
        or expected_target_realm != target_realm_for_current
    ):
        raise ValueError(
            f"The {expected_target_realm} rebuild budget applies only to "
            f"{expected_current_realm} to {expected_target_realm} ascension."
        )
    if normalized_target_realm != expected_target_realm:
        raise ValueError(
            f"Realm ascension must move from {current_realm} to {expected_target_realm}."
        )

    history = [
        dict(record)
        for record in list(xianxia.get("advancement_history") or [])
        if isinstance(record, dict) and record
    ]
    review_index = _latest_realm_ascension_review_index(
        history,
        current_realm=current_realm,
        target_realm=expected_target_realm,
    )
    if review_index is None:
        raise ValueError(
            f"Start a pending Realm ascension review before applying the {expected_target_realm} rebuild."
        )
    reset_index = _latest_realm_ascension_stat_reset_index(
        history,
        review_index=review_index,
        target_realm=expected_target_realm,
    )
    if reset_index is None:
        raise ValueError(
            f"Reset Attributes and Efforts before applying the {expected_target_realm} rebuild budget."
        )
    if _has_realm_ascension_rebuild_after(
        history,
        reset_index,
        target_realm=expected_target_realm,
    ):
        raise ValueError(
            f"The {expected_target_realm} rebuild budget has already been applied for this Realm ascension review."
        )
    reset_event = dict(history[reset_index])
    pre_ascension_state = _realm_ascension_snapshot_from_event(reset_event)
    pre_ascension_summary = str(reset_event.get("pre_ascension_summary") or "").strip()

    rebuild_budget = int(target["rebuild_budget"])
    stat_cap = int(target["stat_cap"])
    durability = _durability_maxima(xianxia.get("durability"))
    (
        trade,
        trade_errors,
    ) = _validate_realm_ascension_hp_stance_trade(
        hp_maximum_trade=hp_maximum_trade,
        stance_maximum_trade=stance_maximum_trade,
        hp_maximum_before=durability["hp_max"],
        stance_maximum_before=durability["stance_max"],
    )
    attributes, attribute_total, attribute_errors = _validate_realm_rebuild_scores(
        attribute_scores,
        keys=XIANXIA_ATTRIBUTE_KEYS,
        labels=XIANXIA_ATTRIBUTE_LABELS,
        stat_cap=stat_cap,
        rebuild_label=expected_target_realm,
    )
    efforts, effort_total, effort_errors = _validate_realm_rebuild_scores(
        effort_scores,
        keys=XIANXIA_EFFORT_KEYS,
        labels=XIANXIA_EFFORT_LABELS,
        stat_cap=stat_cap,
        rebuild_label=expected_target_realm,
    )
    total_rebuild_points = attribute_total + effort_total
    trade_bonus_points = int(trade["hp_stance_trade_points"])
    required_rebuild_points = rebuild_budget + trade_bonus_points
    errors = trade_errors + attribute_errors + effort_errors
    if total_rebuild_points != required_rebuild_points:
        errors.append(
            f"{expected_target_realm} rebuild must spend exactly {required_rebuild_points} Attribute/Effort "
            f"points; submitted {total_rebuild_points}."
        )
    if errors:
        raise ValueError("; ".join(errors))

    durability_payload = (
        dict(xianxia.get("durability") or {}) if isinstance(xianxia.get("durability"), dict) else {}
    )
    hp_maximum_after = int(trade["hp_maximum_after"])
    stance_maximum_after = int(trade["stance_maximum_after"])
    durability_payload["hp_max"] = hp_maximum_after
    durability_payload["stance_max"] = stance_maximum_after
    xianxia["durability"] = durability_payload
    xianxia["realm"] = expected_target_realm
    xianxia["actions_per_turn"] = int(target["actions_per_turn"])
    xianxia["attributes"] = attributes
    xianxia["efforts"] = efforts
    post_ascension_state = _realm_ascension_history_snapshot(xianxia)
    post_ascension_summary = _realm_ascension_history_snapshot_summary(
        post_ascension_state
    )

    clean_notes = _clean_note(notes)
    event = {
        "action": XIANXIA_REALM_ASCENSION_REBUILD_ACTIONS[expected_target_realm],
        "target": expected_target_realm,
        "current_realm": current_realm,
        "target_realm": expected_target_realm,
        "status": "applied_pending_final_confirmation",
        "rebuild_budget": required_rebuild_points,
        "stat_cap": stat_cap,
        "actions_per_turn": int(target["actions_per_turn"]),
        "attributes_after_total": attribute_total,
        "efforts_after_total": effort_total,
        "total_rebuild_points": total_rebuild_points,
        "post_ascension_summary": post_ascension_summary,
        "post_ascension_state": post_ascension_state,
    }
    if pre_ascension_state:
        event["pre_ascension_state"] = pre_ascension_state
    if pre_ascension_summary:
        event["pre_ascension_summary"] = pre_ascension_summary
    if trade_bonus_points:
        event.update(
            {
                "hp_stance_trade_points": trade_bonus_points,
                "base_rebuild_budget": rebuild_budget,
                "hp_maximum_trade": int(trade["hp_maximum_trade"]),
                "stance_maximum_trade": int(trade["stance_maximum_trade"]),
                "hp_maximum_before": int(trade["hp_maximum_before"]),
                "hp_maximum_after": hp_maximum_after,
                "stance_maximum_before": int(trade["stance_maximum_before"]),
                "stance_maximum_after": stance_maximum_after,
            }
        )
    if clean_notes:
        event["notes"] = clean_notes
    history.append(event)
    xianxia["advancement_history"] = history
    payload["xianxia"] = xianxia

    return XianxiaRealmAscensionImmortalRebuildResult(
        definition=definition.__class__.from_dict(payload),
        current_realm=current_realm,
        target_realm=expected_target_realm,
        rebuild_budget=required_rebuild_points,
        stat_cap=stat_cap,
        actions_per_turn=int(target["actions_per_turn"]),
        attribute_total=attribute_total,
        effort_total=effort_total,
        total_rebuild_points=total_rebuild_points,
        notes=clean_notes,
        hp_maximum_trade=int(trade["hp_maximum_trade"]),
        stance_maximum_trade=int(trade["stance_maximum_trade"]),
        hp_stance_trade_points=trade_bonus_points,
        hp_maximum_before=int(trade["hp_maximum_before"]),
        hp_maximum_after=hp_maximum_after,
        stance_maximum_before=int(trade["stance_maximum_before"]),
        stance_maximum_after=stance_maximum_after,
    )


def list_xianxia_generic_technique_learning_options(
    definition: Any,
    *,
    campaign_slug: str,
    systems_service: Any,
) -> list[dict[str, Any]]:
    if systems_service is None:
        return []

    payload = definition.to_dict()
    xianxia = dict(payload.get("xianxia") or {})
    known_markers = _known_generic_technique_markers(xianxia.get("generic_techniques"))
    options: list[dict[str, Any]] = []
    entries = systems_service.list_enabled_entries_for_campaign(
        campaign_slug,
        entry_type="generic_technique",
        limit=None,
    )
    for entry in sorted(entries, key=_generic_technique_entry_sort_key):
        option = _generic_technique_record_from_entry(entry)
        if not option:
            continue
        generic_technique_key = normalize_xianxia_generic_technique_key(
            option.get("generic_technique_key")
        )
        if generic_technique_key in XIANXIA_DIRECT_ADVANCEMENT_GENERIC_TECHNIQUE_KEYS:
            continue
        if _generic_technique_record_is_known(option, known_markers):
            continue
        if _non_negative_int(option.get("insight_cost"), default=0) <= 0:
            continue
        options.append(option)
    return options


def learn_xianxia_generic_technique_definition(
    definition: Any,
    *,
    campaign_slug: str,
    systems_service: Any,
    generic_technique_entry_key: str,
    notes: str = "",
) -> XianxiaGenericTechniqueLearnResult:
    entry_key = str(generic_technique_entry_key or "").strip()
    if not entry_key:
        raise ValueError("Choose a Generic Technique to learn.")
    if systems_service is None:
        raise ValueError("Generic Technique catalog is unavailable.")

    entry = systems_service.get_entry_for_campaign(campaign_slug, entry_key)
    option = _generic_technique_record_from_entry(entry)
    if not option:
        raise ValueError("Choose an available Generic Technique to learn.")
    generic_technique_key = normalize_xianxia_generic_technique_key(
        option.get("generic_technique_key")
    )
    if generic_technique_key in XIANXIA_DIRECT_ADVANCEMENT_GENERIC_TECHNIQUE_KEYS:
        raise ValueError(
            f"Use the dedicated {option['name']} spend form for this Insight spend."
        )

    insight_cost = _non_negative_int(option.get("insight_cost"), default=0)
    if insight_cost <= 0:
        raise ValueError(f"{option['name']} does not have a positive Insight cost.")

    payload = definition.to_dict()
    xianxia = dict(payload.get("xianxia") or {})
    generic_techniques = [
        dict(record)
        for record in list(xianxia.get("generic_techniques") or [])
        if isinstance(record, dict)
    ]
    known_markers = _known_generic_technique_markers(generic_techniques)
    if _generic_technique_record_is_known(option, known_markers):
        raise ValueError(f"{option['name']} is already learned.")

    insight = dict(xianxia.get("insight") or {})
    available = _non_negative_int(insight.get("available"), default=0)
    spent = _non_negative_int(insight.get("spent"), default=0)
    if available < insight_cost:
        raise ValueError(
            f"{option['name']} needs {insight_cost} Insight to learn; "
            f"only {available} available."
        )

    clean_notes = _clean_note(notes)
    learned_record = {
        "name": option["name"],
        "systems_ref": dict(option["systems_ref"]),
        "generic_technique_key": generic_technique_key,
        "insight_spent": insight_cost,
        "support_state": str(option.get("support_state") or "").strip(),
        "learnable_without_master": bool(option.get("learnable_without_master")),
        "requires_master": bool(option.get("requires_master")),
    }
    if clean_notes:
        learned_record["notes"] = clean_notes
    generic_techniques.append(learned_record)

    xianxia["generic_techniques"] = generic_techniques
    xianxia["insight"] = {
        "available": available - insight_cost,
        "spent": spent + insight_cost,
    }
    history = [
        dict(record)
        for record in list(xianxia.get("advancement_history") or [])
        if isinstance(record, dict) and record
    ]
    event = {
        "action": "generic_technique_learned",
        "amount": insight_cost,
        "target": option["name"],
        "generic_technique_key": generic_technique_key,
        "systems_ref": dict(option["systems_ref"]),
        "insight_cost": insight_cost,
    }
    if clean_notes:
        event["notes"] = clean_notes
    history.append(event)
    xianxia["advancement_history"] = history
    payload["xianxia"] = xianxia

    return XianxiaGenericTechniqueLearnResult(
        definition=definition.__class__.from_dict(payload),
        technique_name=option["name"],
        insight_cost=insight_cost,
        systems_ref=dict(option["systems_ref"]),
        notes=clean_notes,
    )


def spend_xianxia_cultivation_energy_definition(
    definition: Any,
    *,
    energy_key: str,
    notes: str = "",
) -> XianxiaCultivationEnergySpendResult:
    normalized_energy_key = normalize_xianxia_energy_key(energy_key)
    if normalized_energy_key not in XIANXIA_ENERGY_KEYS:
        raise ValueError("Choose Jing, Qi, or Shen for Cultivation.")

    payload = definition.to_dict()
    xianxia = dict(payload.get("xianxia") or {})
    insight = dict(xianxia.get("insight") or {})
    available = _non_negative_int(insight.get("available"), default=0)
    spent = _non_negative_int(insight.get("spent"), default=0)
    insight_cost = XIANXIA_CULTIVATION_ENERGY_INSIGHT_COST
    energy_name = energy_label(normalized_energy_key)
    if available < insight_cost:
        raise ValueError(
            f"Cultivation needs {insight_cost} Insight to increase {energy_name}; "
            f"only {available} available."
        )

    increases = {key: 0 for key in XIANXIA_ENERGY_KEYS}
    increases[normalized_energy_key] = 1
    energies = _apply_energy_maximum_increases(xianxia.get("energies"), increases)
    new_maximum = _non_negative_int(
        dict(energies.get(normalized_energy_key) or {}).get("max"),
        default=0,
    )
    xianxia["energies"] = energies
    xianxia["insight"] = {
        "available": available - insight_cost,
        "spent": spent + insight_cost,
    }

    history = [
        dict(record)
        for record in list(xianxia.get("advancement_history") or [])
        if isinstance(record, dict) and record
    ]
    clean_notes = _clean_note(notes)
    event = {
        "action": "cultivation_energy_increase",
        "amount": insight_cost,
        "target": energy_name,
        "energy_key": normalized_energy_key,
        "energy_maximum_increase": 1,
        "new_energy_maximum": new_maximum,
    }
    if clean_notes:
        event["notes"] = clean_notes
    history.append(event)
    xianxia["advancement_history"] = history
    payload["xianxia"] = xianxia

    return XianxiaCultivationEnergySpendResult(
        definition=definition.__class__.from_dict(payload),
        energy_key=normalized_energy_key,
        energy_name=energy_name,
        insight_cost=insight_cost,
        new_maximum=new_maximum,
        notes=clean_notes,
    )


def spend_xianxia_meditation_definition(
    definition: Any,
    *,
    yin_yang_key: str,
    notes: str = "",
) -> XianxiaMeditationSpendResult:
    normalized_yin_yang_key = normalize_xianxia_yin_yang_key(yin_yang_key)
    if normalized_yin_yang_key not in XIANXIA_YIN_YANG_KEYS:
        raise ValueError("Choose Yin or Yang for Meditation.")

    payload = definition.to_dict()
    xianxia = dict(payload.get("xianxia") or {})
    insight = dict(xianxia.get("insight") or {})
    available = _non_negative_int(insight.get("available"), default=0)
    spent = _non_negative_int(insight.get("spent"), default=0)
    insight_cost = XIANXIA_MEDITATION_INSIGHT_COST
    yin_yang_name = yin_yang_label(normalized_yin_yang_key)
    if available < insight_cost:
        raise ValueError(
            f"Meditation needs {insight_cost} Insight to increase {yin_yang_name}; "
            f"only {available} available."
        )

    yin_yang = _apply_yin_yang_maximum_increase(
        xianxia.get("yin_yang"),
        normalized_yin_yang_key,
        1,
    )
    new_maximum = _non_negative_int(
        yin_yang.get(f"{normalized_yin_yang_key}_max"),
        default=0,
    )
    xianxia["yin_yang"] = yin_yang
    xianxia["insight"] = {
        "available": available - insight_cost,
        "spent": spent + insight_cost,
    }

    history = [
        dict(record)
        for record in list(xianxia.get("advancement_history") or [])
        if isinstance(record, dict) and record
    ]
    clean_notes = _clean_note(notes)
    event = {
        "action": "meditation_yin_yang_increase",
        "amount": insight_cost,
        "target": yin_yang_name,
        "yin_yang_key": normalized_yin_yang_key,
        "yin_yang_maximum_increase": 1,
        "new_yin_yang_maximum": new_maximum,
    }
    if clean_notes:
        event["notes"] = clean_notes
    history.append(event)
    xianxia["advancement_history"] = history
    payload["xianxia"] = xianxia

    return XianxiaMeditationSpendResult(
        definition=definition.__class__.from_dict(payload),
        yin_yang_key=normalized_yin_yang_key,
        yin_yang_name=yin_yang_name,
        insight_cost=insight_cost,
        new_maximum=new_maximum,
        notes=clean_notes,
    )


def spend_xianxia_conditioning_definition(
    definition: Any,
    *,
    conditioning_target: str,
    effort_key: str = "",
    notes: str = "",
) -> XianxiaConditioningSpendResult:
    target_kind = normalize_xianxia_conditioning_target(conditioning_target)
    if target_kind not in {"hp", "effort"}:
        raise ValueError("Choose HP or an Effort for Conditioning.")

    payload = definition.to_dict()
    xianxia = dict(payload.get("xianxia") or {})
    insight = dict(xianxia.get("insight") or {})
    available = _non_negative_int(insight.get("available"), default=0)
    spent = _non_negative_int(insight.get("spent"), default=0)
    insight_cost = XIANXIA_CONDITIONING_INSIGHT_COST
    if available < insight_cost:
        target_name = "HP" if target_kind == "hp" else effort_label(effort_key)
        raise ValueError(
            f"Conditioning needs {insight_cost} Insight to increase {target_name}; "
            f"only {available} available."
        )

    clean_notes = _clean_note(notes)
    history = [
        dict(record)
        for record in list(xianxia.get("advancement_history") or [])
        if isinstance(record, dict) and record
    ]

    if target_kind == "hp":
        durability = dict(xianxia.get("durability") or {})
        current_hp_max = _non_negative_int(durability.get("hp_max"), default=10)
        if current_hp_max >= XIANXIA_CONDITIONING_HP_MAXIMUM:
            raise ValueError(
                f"Conditioning cannot increase HP above {XIANXIA_CONDITIONING_HP_MAXIMUM}."
            )
        new_hp_max = min(
            XIANXIA_CONDITIONING_HP_MAXIMUM,
            current_hp_max + XIANXIA_CONDITIONING_HP_INCREASE,
        )
        increase = new_hp_max - current_hp_max
        durability["hp_max"] = new_hp_max
        xianxia["durability"] = durability
        event = {
            "action": "conditioning_hp_increase",
            "amount": insight_cost,
            "target": "HP",
            "hp_maximum_increase": increase,
            "new_hp_maximum": new_hp_max,
            "hp_maximum_cap": XIANXIA_CONDITIONING_HP_MAXIMUM,
        }
        target_key = "hp"
        target_name = "HP"
        new_value = new_hp_max
    else:
        normalized_effort_key = normalize_xianxia_effort_key(effort_key)
        if normalized_effort_key not in XIANXIA_EFFORT_KEYS:
            raise ValueError("Choose a valid Effort for Conditioning.")
        efforts = dict(xianxia.get("efforts") or {})
        current_score = _non_negative_int(efforts.get(normalized_effort_key), default=0)
        new_score = current_score + XIANXIA_CONDITIONING_EFFORT_INCREASE
        efforts[normalized_effort_key] = new_score
        xianxia["efforts"] = efforts
        target_key = normalized_effort_key
        target_name = effort_label(normalized_effort_key)
        increase = XIANXIA_CONDITIONING_EFFORT_INCREASE
        new_value = new_score
        event = {
            "action": "conditioning_effort_increase",
            "amount": insight_cost,
            "target": target_name,
            "effort_key": normalized_effort_key,
            "effort_point_increase": increase,
            "new_effort_score": new_score,
        }

    if clean_notes:
        event["notes"] = clean_notes
    history.append(event)
    xianxia["advancement_history"] = history
    xianxia["insight"] = {
        "available": available - insight_cost,
        "spent": spent + insight_cost,
    }
    payload["xianxia"] = xianxia

    return XianxiaConditioningSpendResult(
        definition=definition.__class__.from_dict(payload),
        target_kind=target_kind,
        target_key=target_key,
        target_name=target_name,
        insight_cost=insight_cost,
        increase=increase,
        new_value=new_value,
        notes=clean_notes,
    )


def spend_xianxia_training_definition(
    definition: Any,
    *,
    training_target: str,
    attribute_key: str = "",
    notes: str = "",
) -> XianxiaTrainingSpendResult:
    target_kind = normalize_xianxia_training_target(training_target)
    if target_kind not in {"stance", "attribute"}:
        raise ValueError("Choose Stance or an Attribute for Training.")

    payload = definition.to_dict()
    xianxia = dict(payload.get("xianxia") or {})
    insight = dict(xianxia.get("insight") or {})
    available = _non_negative_int(insight.get("available"), default=0)
    spent = _non_negative_int(insight.get("spent"), default=0)
    insight_cost = XIANXIA_TRAINING_INSIGHT_COST
    if available < insight_cost:
        target_name = "Stance" if target_kind == "stance" else attribute_label(attribute_key)
        raise ValueError(
            f"Training needs {insight_cost} Insight to increase {target_name}; "
            f"only {available} available."
        )

    clean_notes = _clean_note(notes)
    history = [
        dict(record)
        for record in list(xianxia.get("advancement_history") or [])
        if isinstance(record, dict) and record
    ]

    if target_kind == "stance":
        durability = dict(xianxia.get("durability") or {})
        current_stance_max = _non_negative_int(durability.get("stance_max"), default=10)
        if current_stance_max >= XIANXIA_TRAINING_STANCE_MAXIMUM:
            raise ValueError(
                f"Training cannot increase Stance above {XIANXIA_TRAINING_STANCE_MAXIMUM}."
            )
        new_stance_max = min(
            XIANXIA_TRAINING_STANCE_MAXIMUM,
            current_stance_max + XIANXIA_TRAINING_STANCE_INCREASE,
        )
        increase = new_stance_max - current_stance_max
        durability["stance_max"] = new_stance_max
        xianxia["durability"] = durability
        event = {
            "action": "training_stance_increase",
            "amount": insight_cost,
            "target": "Stance",
            "stance_maximum_increase": increase,
            "new_stance_maximum": new_stance_max,
            "stance_maximum_cap": XIANXIA_TRAINING_STANCE_MAXIMUM,
        }
        target_key = "stance"
        target_name = "Stance"
        new_value = new_stance_max
    else:
        normalized_attribute_key = normalize_xianxia_attribute_key(attribute_key)
        if normalized_attribute_key not in XIANXIA_ATTRIBUTE_KEYS:
            raise ValueError("Choose a valid Attribute for Training.")
        attributes = dict(xianxia.get("attributes") or {})
        current_score = _non_negative_int(attributes.get(normalized_attribute_key), default=0)
        new_score = current_score + XIANXIA_TRAINING_ATTRIBUTE_INCREASE
        attributes[normalized_attribute_key] = new_score
        xianxia["attributes"] = attributes
        target_key = normalized_attribute_key
        target_name = attribute_label(normalized_attribute_key)
        increase = XIANXIA_TRAINING_ATTRIBUTE_INCREASE
        new_value = new_score
        event = {
            "action": "training_attribute_increase",
            "amount": insight_cost,
            "target": target_name,
            "attribute_key": normalized_attribute_key,
            "attribute_point_increase": increase,
            "new_attribute_score": new_score,
        }

    if clean_notes:
        event["notes"] = clean_notes
    history.append(event)
    xianxia["advancement_history"] = history
    xianxia["insight"] = {
        "available": available - insight_cost,
        "spent": spent + insight_cost,
    }
    payload["xianxia"] = xianxia

    return XianxiaTrainingSpendResult(
        definition=definition.__class__.from_dict(payload),
        target_kind=target_kind,
        target_key=target_key,
        target_name=target_name,
        insight_cost=insight_cost,
        increase=increase,
        new_value=new_value,
        notes=clean_notes,
    )


def advance_xianxia_martial_art_rank_definition(
    definition: Any,
    *,
    campaign_slug: str,
    systems_service: Any,
    martial_art_index: int,
    target_rank_key: str,
    legendary_quest_note: str = "",
) -> XianxiaMartialArtAdvanceResult:
    payload = definition.to_dict()
    xianxia = dict(payload.get("xianxia") or {})
    martial_arts = [
        dict(record)
        for record in list(xianxia.get("martial_arts") or [])
        if isinstance(record, dict)
    ]
    if martial_art_index < 0 or martial_art_index >= len(martial_arts):
        raise ValueError("Choose a recorded Martial Art to advance.")

    rank_key = normalize_xianxia_martial_art_rank_key(target_rank_key)
    if rank_key not in XIANXIA_MARTIAL_ART_RANK_KEYS:
        raise ValueError("Choose a valid Martial Art rank to advance.")

    martial_art = dict(martial_arts[martial_art_index])
    systems_ref = dict(martial_art.get("systems_ref") or {})
    entry = _xianxia_martial_art_entry_for_record(
        campaign_slug,
        systems_ref=systems_ref,
        systems_service=systems_service,
    )
    martial_art_name = _martial_art_name(martial_art, entry)
    rank_catalog = _xianxia_rank_catalog(entry)
    if not rank_catalog:
        raise ValueError(f"{martial_art_name} does not have structured rank metadata yet.")

    target_record = _rank_record_by_key(rank_catalog).get(rank_key)
    if target_record is None or _xianxia_rank_record_is_incomplete(target_record):
        raise ValueError(
            f"{martial_art_name} does not have an available {rank_label(rank_key)} rank record."
        )

    learned_rank_refs = _learned_rank_refs(martial_art)
    learned_rank_keys = _learned_rank_keys(martial_art, learned_rank_refs)
    if rank_key in learned_rank_keys:
        raise ValueError(f"{martial_art_name} already has {rank_label(rank_key)} recorded.")
    if rank_key == "legendary":
        missing_prior_ranks = _missing_prior_rank_keys(rank_catalog, learned_rank_keys)
        if missing_prior_ranks:
            missing_rank_names = ", ".join(rank_label(key) for key in missing_prior_ranks)
            raise ValueError(
                f"Record {missing_rank_names} for {martial_art_name} before Legendary."
            )

    next_rank = _next_available_rank(rank_catalog, learned_rank_keys)
    if next_rank is None:
        raise ValueError(f"{martial_art_name} has no additional structured rank to advance.")
    next_rank_key = normalize_xianxia_martial_art_rank_key(next_rank.get("rank_key"))
    if next_rank_key != rank_key:
        raise ValueError(
            f"Advance {martial_art_name} to {rank_label(next_rank_key)} "
            f"before {rank_label(rank_key)}."
        )

    insight_cost = _non_negative_int(target_record.get("insight_cost"), default=0)
    if insight_cost <= 0:
        raise ValueError(
            f"{martial_art_name} {rank_label(rank_key)} does not have a positive Insight cost."
        )

    insight = dict(xianxia.get("insight") or {})
    available = _non_negative_int(insight.get("available"), default=0)
    spent = _non_negative_int(insight.get("spent"), default=0)
    if available < insight_cost:
        raise ValueError(
            f"{martial_art_name} needs {insight_cost} Insight to advance to "
            f"{rank_label(rank_key)}; only {available} available."
        )

    energy_maximum_increases = _energy_maximum_increases(target_record)
    if not any(energy_maximum_increases.values()):
        raise ValueError(
            f"{martial_art_name} {rank_label(rank_key)} does not have "
            "rank-granted Jing, Qi, or Shen maximum increases."
        )
    teacher_breakthrough_requirement = _teacher_breakthrough_requirement(target_record)
    teacher_breakthrough_note = _teacher_breakthrough_note(target_record)
    legendary_prerequisite_note = _legendary_prerequisite_note(target_record)
    clean_legendary_quest_note = _clean_note(legendary_quest_note)
    if rank_key == "legendary" and not clean_legendary_quest_note:
        raise ValueError(
            f"Record a quest or mythic-master note before advancing {martial_art_name} "
            "to Legendary."
        )

    rank_ref = str(target_record.get("rank_ref") or "").strip()
    learned_rank_refs = _ensure_recorded_learned_rank_refs(
        learned_rank_refs,
        learned_rank_keys,
        rank_catalog,
    )
    if rank_ref and rank_ref not in learned_rank_refs:
        learned_rank_refs.append(rank_ref)

    martial_art["current_rank_key"] = rank_key
    martial_art["current_rank"] = rank_label(rank_key)
    martial_art["learned_rank_refs"] = learned_rank_refs
    rank_energy_maximum_increases = (
        dict(martial_art.get("rank_energy_maximum_increases") or {})
        if isinstance(martial_art.get("rank_energy_maximum_increases"), dict)
        else {}
    )
    rank_energy_maximum_increases[rank_key] = dict(energy_maximum_increases)
    martial_art["rank_energy_maximum_increases"] = rank_energy_maximum_increases
    if teacher_breakthrough_requirement != "none" or teacher_breakthrough_note:
        rank_teacher_breakthrough_notes = _rank_teacher_breakthrough_notes(martial_art)
        rank_teacher_breakthrough_notes[rank_key] = {
            "requirement": teacher_breakthrough_requirement,
            "note": teacher_breakthrough_note,
        }
        martial_art["rank_teacher_breakthrough_notes"] = rank_teacher_breakthrough_notes
    if rank_key == "legendary":
        rank_legendary_notes = _rank_legendary_prerequisite_notes(martial_art)
        rank_legendary_notes[rank_key] = {
            "requirement": "quest_or_mythic_master",
            "note": clean_legendary_quest_note,
        }
        if legendary_prerequisite_note:
            rank_legendary_notes[rank_key]["prerequisite_note"] = (
                legendary_prerequisite_note
            )
        martial_art["rank_legendary_prerequisite_notes"] = rank_legendary_notes
    martial_art["insight_spent"] = _non_negative_int(
        martial_art.get("insight_spent"),
        default=0,
    ) + insight_cost
    martial_arts[martial_art_index] = martial_art

    xianxia["insight"] = {
        "available": available - insight_cost,
        "spent": spent + insight_cost,
    }
    xianxia["energies"] = _apply_energy_maximum_increases(
        xianxia.get("energies"),
        energy_maximum_increases,
    )
    xianxia["martial_arts"] = martial_arts
    history = [
        dict(record)
        for record in list(xianxia.get("advancement_history") or [])
        if isinstance(record, dict) and record
    ]
    event = {
        "action": "martial_art_rank_advance",
        "amount": insight_cost,
        "target": martial_art_name,
        "rank": rank_label(rank_key),
    }
    if rank_ref:
        event["rank_ref"] = rank_ref
    if systems_ref:
        event["systems_ref"] = systems_ref
    event["energy_maximum_increases"] = dict(energy_maximum_increases)
    if teacher_breakthrough_requirement != "none":
        event["teacher_breakthrough_requirement"] = teacher_breakthrough_requirement
    if teacher_breakthrough_note:
        event["teacher_breakthrough_note"] = teacher_breakthrough_note
    if rank_key == "legendary":
        event["legendary_prerequisite"] = "quest_or_mythic_master"
        event["legendary_quest_note"] = clean_legendary_quest_note
        if legendary_prerequisite_note:
            event["legendary_prerequisite_note"] = legendary_prerequisite_note
    history.append(event)
    xianxia["advancement_history"] = history
    payload["xianxia"] = xianxia

    updated_definition = definition.__class__.from_dict(payload)
    return XianxiaMartialArtAdvanceResult(
        definition=updated_definition,
        martial_art_name=martial_art_name,
        rank_name=rank_label(rank_key),
        insight_cost=insight_cost,
        energy_maximum_increases=energy_maximum_increases,
        teacher_breakthrough_requirement=teacher_breakthrough_requirement,
        teacher_breakthrough_note=teacher_breakthrough_note,
        legendary_quest_note=clean_legendary_quest_note,
        legendary_prerequisite_note=legendary_prerequisite_note,
    )


def normalize_xianxia_martial_art_rank_key(value: Any) -> str:
    return (
        str(value if value is not None else "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def normalize_xianxia_energy_key(value: Any) -> str:
    return (
        str(value if value is not None else "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def normalize_xianxia_yin_yang_key(value: Any) -> str:
    return (
        str(value if value is not None else "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def normalize_xianxia_conditioning_target(value: Any) -> str:
    return (
        str(value if value is not None else "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def normalize_xianxia_training_target(value: Any) -> str:
    return (
        str(value if value is not None else "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def normalize_xianxia_effort_key(value: Any) -> str:
    return (
        str(value if value is not None else "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def normalize_xianxia_attribute_key(value: Any) -> str:
    return (
        str(value if value is not None else "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def normalize_xianxia_generic_technique_key(value: Any) -> str:
    return (
        str(value if value is not None else "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def normalize_xianxia_realm_label(value: Any) -> str:
    cleaned = " ".join(str(value if value is not None else "").split()).strip()
    if not cleaned:
        return "Mortal"
    normalized = cleaned.lower().replace("-", "_").replace(" ", "_")
    labels = {realm.casefold(): realm for realm in XIANXIA_REALM_ASCENSION_REALMS}
    labels.update(
        {realm.lower().replace(" ", "_"): realm for realm in XIANXIA_REALM_ASCENSION_REALMS}
    )
    return labels.get(normalized, cleaned)


def energy_label(energy_key: str) -> str:
    normalized = normalize_xianxia_energy_key(energy_key)
    if normalized in XIANXIA_ENERGY_LABELS:
        return XIANXIA_ENERGY_LABELS[normalized]
    return normalized.replace("_", " ").title() if normalized else "Energy"


def yin_yang_label(yin_yang_key: str) -> str:
    normalized = normalize_xianxia_yin_yang_key(yin_yang_key)
    if normalized in XIANXIA_YIN_YANG_LABELS:
        return XIANXIA_YIN_YANG_LABELS[normalized]
    return normalized.replace("_", " ").title() if normalized else "Yin/Yang"


def effort_label(effort_key: str) -> str:
    normalized = normalize_xianxia_effort_key(effort_key)
    if normalized in XIANXIA_EFFORT_LABELS:
        return XIANXIA_EFFORT_LABELS[normalized]
    return normalized.replace("_", " ").title() if normalized else "Effort"


def attribute_label(attribute_key: str) -> str:
    normalized = normalize_xianxia_attribute_key(attribute_key)
    if normalized in XIANXIA_ATTRIBUTE_LABELS:
        return XIANXIA_ATTRIBUTE_LABELS[normalized]
    return normalized.replace("_", " ").title() if normalized else "Attribute"


def rank_label(rank_key: str) -> str:
    normalized = normalize_xianxia_martial_art_rank_key(rank_key)
    if normalized in XIANXIA_MARTIAL_ART_RANK_LABELS:
        return XIANXIA_MARTIAL_ART_RANK_LABELS[normalized]
    return normalized.replace("_", " ").title() if normalized else "Rank"


def _xianxia_martial_art_entry_for_record(
    campaign_slug: str,
    *,
    systems_ref: dict[str, Any],
    systems_service: Any,
) -> Any | None:
    if systems_service is None:
        return None
    entry_key = str(systems_ref.get("entry_key") or "").strip()
    if entry_key:
        entry = systems_service.get_entry_for_campaign(campaign_slug, entry_key)
        if entry is not None:
            return entry
    slug = str(systems_ref.get("slug") or "").strip()
    if slug:
        return systems_service.get_entry_by_slug_for_campaign(campaign_slug, slug)
    return None


def _generic_technique_record_from_entry(entry: Any | None) -> dict[str, Any]:
    if entry is None or str(getattr(entry, "entry_type", "") or "").strip() != "generic_technique":
        return {}
    metadata = dict(getattr(entry, "metadata", {}) or {})
    body = dict(getattr(entry, "body", {}) or {})
    technique_body = dict(body.get("xianxia_generic_technique") or {})
    systems_ref = _systems_ref_for_entry(entry)
    generic_technique_key = normalize_xianxia_generic_technique_key(
        _first_present_value(
            metadata.get("generic_technique_key"),
            metadata.get("xianxia_generic_technique_key"),
            technique_body.get("key"),
        )
    )
    return {
        "name": str(getattr(entry, "title", "") or "").strip() or "Generic Technique",
        "entry_key": systems_ref.get("entry_key", ""),
        "systems_ref": systems_ref,
        "generic_technique_key": generic_technique_key,
        "insight_cost": _non_negative_int(
            _first_present_value(
                metadata.get("insight_cost"),
                technique_body.get("insight_cost"),
            ),
            default=0,
        ),
        "support_state": str(
            _first_present_value(
                metadata.get("support_state"),
                metadata.get("xianxia_support_state"),
                technique_body.get("support_state"),
                technique_body.get("xianxia_support_state"),
            )
            or ""
        ).strip(),
        "prerequisites": _list_copy(
            _first_present_value(
                metadata.get("prerequisites"),
                technique_body.get("prerequisites"),
            )
        ),
        "resource_costs": _list_copy(
            _first_present_value(
                metadata.get("resource_costs"),
                technique_body.get("resource_costs"),
            )
        ),
        "range_tags": _list_copy(
            _first_present_value(metadata.get("range_tags"), technique_body.get("range_tags"))
        ),
        "effort_tags": _list_copy(
            _first_present_value(metadata.get("effort_tags"), technique_body.get("effort_tags"))
        ),
        "reset_cadence": str(
            _first_present_value(metadata.get("reset_cadence"), technique_body.get("reset_cadence"))
            or ""
        ).strip(),
        "learnable_without_master": _truthy(
            _first_present_value(
                metadata.get("learnable_without_master"),
                technique_body.get("learnable_without_master"),
            )
        ),
        "requires_master": _truthy(
            _first_present_value(
                metadata.get("requires_master"),
                technique_body.get("requires_master"),
            )
        ),
    }


def _generic_technique_entry_sort_key(entry: Any) -> tuple[int, str]:
    metadata = dict(getattr(entry, "metadata", {}) or {})
    body = dict(getattr(entry, "body", {}) or {})
    technique_body = dict(body.get("xianxia_generic_technique") or {})
    raw_order = _first_present_value(
        metadata.get("generic_technique_catalog_order"),
        metadata.get("catalog_order"),
        technique_body.get("catalog_order"),
    )
    try:
        order = int(raw_order)
    except (TypeError, ValueError):
        order = 10_000
    return (order, str(getattr(entry, "title", "") or "").casefold())


def _systems_ref_for_entry(entry: Any) -> dict[str, str]:
    return {
        "library_slug": str(getattr(entry, "library_slug", "") or "").strip(),
        "source_id": str(getattr(entry, "source_id", "") or "").strip(),
        "entry_key": str(getattr(entry, "entry_key", "") or "").strip(),
        "slug": str(getattr(entry, "slug", "") or "").strip(),
        "title": str(getattr(entry, "title", "") or "").strip(),
        "entry_type": str(getattr(entry, "entry_type", "") or "").strip(),
    }


def _known_generic_technique_markers(records: Any) -> dict[str, set[str]]:
    markers = {
        "entry_keys": set(),
        "slugs": set(),
        "keys": set(),
        "names": set(),
    }
    for record in list(records or []):
        payload = dict(record) if isinstance(record, dict) else {"name": record}
        systems_ref = dict(payload.get("systems_ref") or {})
        entry_key = str(systems_ref.get("entry_key") or payload.get("entry_key") or "").strip()
        if entry_key:
            markers["entry_keys"].add(entry_key.casefold())
        slug = str(systems_ref.get("slug") or payload.get("slug") or "").strip()
        if slug:
            markers["slugs"].add(slug.casefold())
        generic_technique_key = normalize_xianxia_generic_technique_key(
            payload.get("generic_technique_key")
            or payload.get("technique_key")
            or systems_ref.get("slug")
        )
        if generic_technique_key:
            markers["keys"].add(generic_technique_key)
        name = str(payload.get("name") or payload.get("title") or systems_ref.get("title") or "").strip()
        if name:
            markers["names"].add(name.casefold())
    return markers


def _generic_technique_record_is_known(
    option: dict[str, Any],
    known_markers: dict[str, set[str]],
) -> bool:
    systems_ref = dict(option.get("systems_ref") or {})
    entry_key = str(systems_ref.get("entry_key") or option.get("entry_key") or "").strip()
    if entry_key and entry_key.casefold() in known_markers["entry_keys"]:
        return True
    slug = str(systems_ref.get("slug") or "").strip()
    if slug and slug.casefold() in known_markers["slugs"]:
        return True
    generic_technique_key = normalize_xianxia_generic_technique_key(
        option.get("generic_technique_key") or slug
    )
    if generic_technique_key and generic_technique_key in known_markers["keys"]:
        return True
    name = str(option.get("name") or "").strip()
    if name and name.casefold() in known_markers["names"]:
        return True
    return False


def _martial_art_name(record: dict[str, Any], entry: Any | None) -> str:
    systems_ref = dict(record.get("systems_ref") or {})
    return (
        str(record.get("name") or "").strip()
        or str(systems_ref.get("title") or "").strip()
        or str(getattr(entry, "title", "") or "").strip()
        or "Martial Art"
    )


def _xianxia_rank_catalog(entry: Any | None) -> list[dict[str, Any]]:
    if entry is None:
        return []
    metadata = dict(getattr(entry, "metadata", {}) or {})
    body = dict(getattr(entry, "body", {}) or {})
    martial_art_body = dict(body.get("xianxia_martial_art") or {})
    present_records = _rank_record_list(
        metadata.get("martial_art_rank_records")
        or metadata.get("xianxia_martial_art_rank_records")
        or martial_art_body.get("rank_records")
        or martial_art_body.get("xianxia_martial_art_rank_records")
    )
    missing_records = _rank_record_list(
        metadata.get("martial_art_missing_rank_records")
        or metadata.get("xianxia_martial_art_missing_rank_records")
        or martial_art_body.get("missing_rank_records")
        or martial_art_body.get("xianxia_martial_art_missing_rank_records")
    )
    return sorted(present_records + missing_records, key=_rank_record_sort_key)


def _rank_record_list(values: Any) -> list[dict[str, Any]]:
    return [dict(record) for record in list(values or []) if isinstance(record, dict)]


def _rank_record_sort_key(record: dict[str, Any]) -> tuple[int, str]:
    rank_key = normalize_xianxia_martial_art_rank_key(record.get("rank_key"))
    try:
        rank_order = int(record.get("rank_order"))
    except (TypeError, ValueError):
        rank_order = (
            XIANXIA_MARTIAL_ART_RANK_KEYS.index(rank_key)
            if rank_key in XIANXIA_MARTIAL_ART_RANK_KEYS
            else 10_000
        )
    return (rank_order, str(record.get("rank_name") or rank_key).casefold())


def _rank_record_by_key(rank_catalog: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        normalize_xianxia_martial_art_rank_key(record.get("rank_key")): record
        for record in rank_catalog
        if normalize_xianxia_martial_art_rank_key(record.get("rank_key"))
    }


def _xianxia_rank_record_is_incomplete(record: dict[str, Any]) -> bool:
    return bool(
        record.get("is_incomplete_rank")
        or record.get("rank_available_in_seed") is False
        or str(record.get("rank_completion_status") or "").strip()
        == "missing_intentional_draft"
        or str(record.get("incomplete_rank_reason") or "").strip()
        == "intentional_draft_content"
    )


def _learned_rank_refs(martial_art: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for value in list(martial_art.get("learned_rank_refs") or []):
        ref = str(value or "").strip()
        if ref and ref not in refs:
            refs.append(ref)
    return refs


def _learned_rank_keys(martial_art: dict[str, Any], learned_rank_refs: list[str]) -> set[str]:
    learned = {
        normalize_xianxia_martial_art_rank_key(str(ref).rsplit(":", 1)[-1])
        for ref in learned_rank_refs
        if str(ref).strip()
    }
    current_rank_key = normalize_xianxia_martial_art_rank_key(
        martial_art.get("current_rank_key")
    )
    if current_rank_key:
        learned.add(current_rank_key)
    return learned


def _next_available_rank(
    rank_catalog: list[dict[str, Any]],
    learned_rank_keys: set[str],
) -> dict[str, Any] | None:
    for record in rank_catalog:
        rank_key = normalize_xianxia_martial_art_rank_key(record.get("rank_key"))
        if not rank_key or rank_key in learned_rank_keys:
            continue
        if _xianxia_rank_record_is_incomplete(record):
            return None
        return record
    return None


def _missing_prior_rank_keys(
    rank_catalog: list[dict[str, Any]],
    learned_rank_keys: set[str],
) -> list[str]:
    available_rank_keys = {
        normalize_xianxia_martial_art_rank_key(record.get("rank_key"))
        for record in rank_catalog
        if not _xianxia_rank_record_is_incomplete(record)
    }
    missing: list[str] = []
    for rank_key in XIANXIA_MARTIAL_ART_RANK_KEYS:
        if rank_key == "legendary":
            break
        if rank_key in available_rank_keys and rank_key not in learned_rank_keys:
            missing.append(rank_key)
    return missing


def _ensure_recorded_learned_rank_refs(
    learned_rank_refs: list[str],
    learned_rank_keys: set[str],
    rank_catalog: list[dict[str, Any]],
) -> list[str]:
    refs = list(learned_rank_refs)
    for record in rank_catalog:
        rank_key = normalize_xianxia_martial_art_rank_key(record.get("rank_key"))
        rank_ref = str(record.get("rank_ref") or "").strip()
        if rank_key in learned_rank_keys and rank_ref and rank_ref not in refs:
            refs.append(rank_ref)
    return refs


def _energy_maximum_increases(rank_record: dict[str, Any]) -> dict[str, int]:
    raw_increases = (
        rank_record.get("energy_maximum_increases")
        or rank_record.get("xianxia_energy_maximum_increases")
        or {}
    )
    increases = dict(raw_increases) if isinstance(raw_increases, dict) else {}
    return {
        key: _non_negative_int(increases.get(key), default=0)
        for key in XIANXIA_ENERGY_KEYS
    }


def _teacher_breakthrough_requirement(rank_record: dict[str, Any]) -> str:
    return (
        normalize_xianxia_martial_art_rank_key(
            rank_record.get("teacher_breakthrough_requirement")
        )
        or "none"
    )


def _teacher_breakthrough_note(rank_record: dict[str, Any]) -> str:
    return _clean_note(rank_record.get("teacher_breakthrough_note"))


def _legendary_prerequisite_note(rank_record: dict[str, Any]) -> str:
    return _clean_note(rank_record.get("legendary_prerequisite_note"))


def _clean_note(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _realm_ascension_target_for_current(current_realm: str) -> dict[str, Any] | None:
    normalized_realm = normalize_xianxia_realm_label(current_realm)
    target = XIANXIA_REALM_ASCENSION_TARGETS.get(normalized_realm)
    if target is None:
        return None
    return {
        "current_realm": normalized_realm,
        **dict(target),
    }


def _latest_realm_ascension_review(records: Any) -> dict[str, Any] | None:
    for record in reversed(list(records or [])):
        if not isinstance(record, dict):
            continue
        if str(record.get("action") or "").strip() != "realm_ascension_review_started":
            continue
        raw_stat_prerequisite = record.get("stat_max_prerequisite")
        stat_prerequisite = (
            dict(raw_stat_prerequisite)
            if isinstance(raw_stat_prerequisite, dict)
            else {}
        )
        return {
            "current_realm": str(record.get("current_realm") or "").strip(),
            "target_realm": str(record.get("target_realm") or record.get("target") or "").strip(),
            "status": str(record.get("status") or "").strip(),
            "seclusion_time": str(record.get("seclusion_time") or "").strip(),
            "rebuild_budget": _non_negative_int(record.get("rebuild_budget"), default=0),
            "stat_cap": _non_negative_int(record.get("stat_cap"), default=0),
            "actions_per_turn": _non_negative_int(record.get("actions_per_turn"), default=0),
            "stat_max_prerequisite": {
                "required_score": _non_negative_int(
                    stat_prerequisite.get("required_score"),
                    default=0,
                ),
                "met": bool(stat_prerequisite.get("met")),
                "stat_kind": str(stat_prerequisite.get("stat_kind") or "").strip(),
                "stat_key": str(stat_prerequisite.get("stat_key") or "").strip(),
                "stat_label": str(stat_prerequisite.get("stat_label") or "").strip(),
                "stat_score": _non_negative_int(
                    stat_prerequisite.get("stat_score"),
                    default=0,
                ),
            },
            "gm_review_note": str(record.get("gm_review_note") or "").strip(),
            "seclusion_notes": str(record.get("seclusion_notes") or "").strip(),
            "hp_stance_trade_notes": str(record.get("hp_stance_trade_notes") or "").strip(),
        }
    return None


def _latest_realm_ascension_stat_reset(records: Any) -> dict[str, Any] | None:
    for record in reversed(list(records or [])):
        if not isinstance(record, dict):
            continue
        if str(record.get("action") or "").strip() != "realm_ascension_attributes_efforts_reset":
            continue
        return {
            "current_realm": str(record.get("current_realm") or "").strip(),
            "target_realm": str(record.get("target_realm") or record.get("target") or "").strip(),
            "status": str(record.get("status") or "").strip(),
            "attributes_before_total": _non_negative_int(
                record.get("attributes_before_total"),
                default=0,
            ),
            "attributes_after_total": _non_negative_int(
                record.get("attributes_after_total"),
                default=0,
            ),
            "efforts_before_total": _non_negative_int(
                record.get("efforts_before_total"),
                default=0,
            ),
            "efforts_after_total": _non_negative_int(
                record.get("efforts_after_total"),
                default=0,
            ),
            "pre_ascension_summary": str(
                record.get("pre_ascension_summary") or ""
            ).strip(),
            "notes": str(record.get("notes") or "").strip(),
        }
    return None


def _latest_realm_ascension_rebuild(
    records: Any,
    *,
    target_realm: str = "",
) -> dict[str, Any] | None:
    normalized_filter = normalize_xianxia_realm_label(target_realm) if target_realm else ""
    rebuild_actions = set(XIANXIA_REALM_ASCENSION_REBUILD_ACTIONS.values())
    for record in reversed(list(records or [])):
        if not isinstance(record, dict):
            continue
        if str(record.get("action") or "").strip() not in rebuild_actions:
            continue
        record_target = normalize_xianxia_realm_label(
            record.get("target_realm") or record.get("target")
        )
        if normalized_filter and record_target != normalized_filter:
            continue
        return {
            "current_realm": str(record.get("current_realm") or "").strip(),
            "target_realm": record_target,
            "status": str(record.get("status") or "").strip(),
            "rebuild_budget": _non_negative_int(record.get("rebuild_budget"), default=0),
            "base_rebuild_budget": _non_negative_int(
                record.get("base_rebuild_budget"),
                default=_non_negative_int(record.get("rebuild_budget"), default=0),
            ),
            "stat_cap": _non_negative_int(record.get("stat_cap"), default=0),
            "actions_per_turn": _non_negative_int(record.get("actions_per_turn"), default=0),
            "attributes_after_total": _non_negative_int(
                record.get("attributes_after_total"),
                default=0,
            ),
            "efforts_after_total": _non_negative_int(
                record.get("efforts_after_total"),
                default=0,
            ),
            "total_rebuild_points": _non_negative_int(
                record.get("total_rebuild_points"),
                default=0,
            ),
            "hp_stance_trade_points": _non_negative_int(
                record.get("hp_stance_trade_points"),
                default=0,
            ),
            "hp_maximum_trade": _non_negative_int(
                record.get("hp_maximum_trade"),
                default=0,
            ),
            "stance_maximum_trade": _non_negative_int(
                record.get("stance_maximum_trade"),
                default=0,
            ),
            "hp_maximum_before": _non_negative_int(
                record.get("hp_maximum_before"),
                default=0,
            ),
            "hp_maximum_after": _non_negative_int(
                record.get("hp_maximum_after"),
                default=0,
            ),
            "stance_maximum_before": _non_negative_int(
                record.get("stance_maximum_before"),
                default=0,
            ),
            "stance_maximum_after": _non_negative_int(
                record.get("stance_maximum_after"),
                default=0,
            ),
            "pre_ascension_summary": str(
                record.get("pre_ascension_summary") or ""
            ).strip(),
            "post_ascension_summary": str(
                record.get("post_ascension_summary") or ""
            ).strip(),
            "notes": str(record.get("notes") or "").strip(),
        }
    return None


def _latest_unconfirmed_realm_ascension_rebuild(
    records: Any,
    *,
    target_realm: str = "",
) -> dict[str, Any] | None:
    history = [
        dict(record)
        for record in list(records or [])
        if isinstance(record, dict) and record
    ]
    index = _latest_unconfirmed_realm_ascension_rebuild_index(
        history,
        target_realm=target_realm,
    )
    if index is None:
        return None
    record = _latest_realm_ascension_rebuild(
        [history[index]],
        target_realm=target_realm,
    )
    if record is not None:
        record["history_index"] = index
    return record


def _latest_realm_ascension_confirmation(
    records: Any,
    *,
    target_realm: str = "",
) -> dict[str, Any] | None:
    normalized_filter = normalize_xianxia_realm_label(target_realm) if target_realm else ""
    for record in reversed(list(records or [])):
        if not isinstance(record, dict):
            continue
        if str(record.get("action") or "").strip() != "realm_ascension_gm_confirmation_recorded":
            continue
        record_target = normalize_xianxia_realm_label(
            record.get("target_realm") or record.get("target")
        )
        if normalized_filter and record_target != normalized_filter:
            continue
        return {
            "current_realm": str(record.get("current_realm") or "").strip(),
            "target_realm": record_target,
            "confirmed_realm": normalize_xianxia_realm_label(
                record.get("confirmed_realm") or record_target
            ),
            "status": str(record.get("status") or "").strip(),
            "confirmed_rebuild_action": str(
                record.get("confirmed_rebuild_action") or ""
            ).strip(),
            "actions_per_turn": _non_negative_int(
                record.get("actions_per_turn"),
                default=0,
            ),
            "attributes_after_total": _non_negative_int(
                record.get("attributes_after_total"),
                default=0,
            ),
            "efforts_after_total": _non_negative_int(
                record.get("efforts_after_total"),
                default=0,
            ),
            "post_ascension_summary": str(
                record.get("post_ascension_summary") or ""
            ).strip(),
            "gm_confirmation_note": str(
                record.get("gm_confirmation_note") or ""
            ).strip(),
        }
    return None


def _can_reset_realm_ascension_stats(
    *,
    latest_review: dict[str, Any] | None,
    latest_reset: dict[str, Any] | None,
    target: dict[str, Any] | None,
) -> bool:
    if not latest_review or not target:
        return False
    if str(latest_review.get("status") or "").strip() != "pending_gm_review":
        return False
    target_realm = str(target.get("target_realm") or "").strip()
    if str(latest_review.get("target_realm") or "").strip() != target_realm:
        return False
    if not latest_reset:
        return True
    return str(latest_reset.get("target_realm") or "").strip() != target_realm


def _can_apply_realm_rebuild(
    *,
    latest_review: dict[str, Any] | None,
    latest_reset: dict[str, Any] | None,
    latest_target_rebuild: dict[str, Any] | None,
    target: dict[str, Any] | None,
) -> bool:
    if not latest_review or not latest_reset or not target:
        return False
    target_realm = str(target.get("target_realm") or "").strip()
    if str(latest_review.get("status") or "").strip() != "pending_gm_review":
        return False
    if str(latest_review.get("target_realm") or "").strip() != target_realm:
        return False
    if str(latest_reset.get("status") or "").strip() != "pending_rebuild":
        return False
    if str(latest_reset.get("target_realm") or "").strip() != target_realm:
        return False
    return latest_target_rebuild is None


def _latest_realm_ascension_review_index(
    history: list[dict[str, Any]],
    *,
    current_realm: str,
    target_realm: str,
) -> int | None:
    for index in range(len(history) - 1, -1, -1):
        record = history[index]
        if str(record.get("action") or "").strip() != "realm_ascension_review_started":
            continue
        if str(record.get("status") or "").strip() != "pending_gm_review":
            continue
        if normalize_xianxia_realm_label(record.get("current_realm")) != current_realm:
            continue
        if normalize_xianxia_realm_label(
            record.get("target_realm") or record.get("target")
        ) != target_realm:
            continue
        return index
    return None


def _latest_unconfirmed_realm_ascension_rebuild_index(
    history: list[dict[str, Any]],
    *,
    target_realm: str = "",
) -> int | None:
    normalized_filter = normalize_xianxia_realm_label(target_realm) if target_realm else ""
    rebuild_actions = set(XIANXIA_REALM_ASCENSION_REBUILD_ACTIONS.values())
    for index in range(len(history) - 1, -1, -1):
        record = history[index]
        if str(record.get("action") or "").strip() not in rebuild_actions:
            continue
        if str(record.get("status") or "").strip() != "applied_pending_final_confirmation":
            continue
        record_target = normalize_xianxia_realm_label(
            record.get("target_realm") or record.get("target")
        )
        if normalized_filter and record_target != normalized_filter:
            continue
        if _has_realm_ascension_confirmation_after(
            history,
            index,
            target_realm=record_target,
        ):
            continue
        return index
    return None


def _has_realm_ascension_confirmation_after(
    history: list[dict[str, Any]],
    rebuild_index: int,
    *,
    target_realm: str,
) -> bool:
    normalized_target = normalize_xianxia_realm_label(target_realm)
    for record in history[rebuild_index + 1 :]:
        if str(record.get("action") or "").strip() != "realm_ascension_gm_confirmation_recorded":
            continue
        if normalize_xianxia_realm_label(
            record.get("target_realm") or record.get("target")
        ) == normalized_target:
            return True
    return False


def _latest_realm_ascension_stat_reset_index(
    history: list[dict[str, Any]],
    *,
    review_index: int,
    target_realm: str,
) -> int | None:
    for index in range(len(history) - 1, review_index, -1):
        record = history[index]
        if str(record.get("action") or "").strip() != "realm_ascension_attributes_efforts_reset":
            continue
        if str(record.get("status") or "").strip() != "pending_rebuild":
            continue
        if normalize_xianxia_realm_label(
            record.get("target_realm") or record.get("target")
        ) != target_realm:
            continue
        return index
    return None


def _has_realm_ascension_stat_reset_after(
    history: list[dict[str, Any]],
    review_index: int,
) -> bool:
    for record in history[review_index + 1 :]:
        if str(record.get("action") or "").strip() == "realm_ascension_attributes_efforts_reset":
            return True
    return False


def _has_realm_ascension_rebuild_after(
    history: list[dict[str, Any]],
    reset_index: int,
    *,
    target_realm: str,
) -> bool:
    expected_action = XIANXIA_REALM_ASCENSION_REBUILD_ACTIONS.get(target_realm)
    for record in history[reset_index + 1 :]:
        if str(record.get("action") or "").strip() == expected_action:
            return True
    return False


def _realm_ascension_stat_prerequisite(
    *,
    current_realm: str,
    target: dict[str, Any] | None,
    attribute_rows: list[dict[str, Any]],
    effort_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_realm = normalize_xianxia_realm_label(current_realm)
    target_realm = str((target or {}).get("target_realm") or "").strip()
    required_score = _non_negative_int(
        (target or {}).get("stat_max_prerequisite"),
        default=0,
    )
    records = [
        {
            "kind": "Attribute",
            "key": str(row.get("key") or "").strip(),
            "label": str(row.get("label") or "").strip(),
            "score": _non_negative_int(row.get("score"), default=0),
        }
        for row in list(attribute_rows or [])
    ] + [
        {
            "kind": "Effort",
            "key": str(row.get("key") or "").strip(),
            "label": str(row.get("label") or "").strip(),
            "score": _non_negative_int(row.get("score"), default=0),
        }
        for row in list(effort_rows or [])
    ]
    records = [record for record in records if record["key"]]
    highest = max(records, key=lambda record: int(record["score"]), default=None)
    eligible_records = [
        record for record in records if int(record["score"]) >= required_score
    ]
    met_by = max(eligible_records, key=lambda record: int(record["score"]), default=None)
    is_met = required_score <= 0 or met_by is not None
    if met_by is None and required_score <= 0 and highest is not None:
        met_by = highest

    highest_label = str(highest["label"]) if highest else "None"
    highest_score = int(highest["score"]) if highest else 0
    target_label = target_realm or "the next Realm"
    requirement_text = (
        f"Requires at least one Attribute or Effort at {required_score} "
        f"before ascending from {normalized_realm} to {target_label}."
    )
    failure_message = (
        f"Realm ascension prerequisite not met: raise at least one Attribute or "
        f"Effort to {required_score} before ascending from {normalized_realm} "
        f"to {target_label}. Current highest Stat is {highest_label} at "
        f"{highest_score}."
    )

    return {
        "required_score": required_score,
        "is_met": is_met,
        "met_by": dict(met_by or {}),
        "highest": dict(highest or {}),
        "highest_label": highest_label,
        "highest_score": highest_score,
        "requirement_text": requirement_text,
        "failure_message": failure_message,
    }


def _validate_realm_rebuild_scores(
    values: dict[str, Any],
    *,
    keys: tuple[str, ...],
    labels: dict[str, str],
    stat_cap: int,
    rebuild_label: str,
) -> tuple[dict[str, int], int, list[str]]:
    raw_values = dict(values or {}) if isinstance(values, dict) else {}
    scores: dict[str, int] = {}
    errors: list[str] = []
    for key in keys:
        label = labels.get(key, key)
        raw_value = raw_values.get(key)
        if raw_value is None or str(raw_value).strip() == "":
            errors.append(f"{label} is required for the {rebuild_label} rebuild.")
            scores[key] = 0
            continue
        try:
            score = int(str(raw_value).strip())
        except ValueError:
            errors.append(f"{label} must be a whole number.")
            scores[key] = 0
            continue
        if score < 0:
            errors.append(f"{label} cannot be negative.")
            scores[key] = 0
            continue
        if score > stat_cap:
            errors.append(f"{label} cannot exceed {stat_cap} for the {rebuild_label} rebuild.")
        scores[key] = score
    return scores, sum(scores.values()), errors


def _validate_realm_ascension_hp_stance_trade(
    *,
    hp_maximum_trade: Any,
    stance_maximum_trade: Any,
    hp_maximum_before: int,
    stance_maximum_before: int,
) -> tuple[dict[str, int], list[str]]:
    errors: list[str] = []
    hp_trade = _validate_realm_trade_amount(
        hp_maximum_trade,
        label="HP maximum trade",
        current_maximum=hp_maximum_before,
        errors=errors,
    )
    stance_trade = _validate_realm_trade_amount(
        stance_maximum_trade,
        label="Stance maximum trade",
        current_maximum=stance_maximum_before,
        errors=errors,
    )
    trade_points = (hp_trade + stance_trade) // XIANXIA_REALM_ASCENSION_TRADE_UNIT
    return (
        {
            "hp_maximum_trade": hp_trade,
            "stance_maximum_trade": stance_trade,
            "hp_stance_trade_points": trade_points,
            "hp_maximum_before": hp_maximum_before,
            "hp_maximum_after": max(0, hp_maximum_before - hp_trade),
            "stance_maximum_before": stance_maximum_before,
            "stance_maximum_after": max(0, stance_maximum_before - stance_trade),
        },
        errors,
    )


def _validate_realm_trade_amount(
    value: Any,
    *,
    label: str,
    current_maximum: int,
    errors: list[str],
) -> int:
    if value is None or str(value).strip() == "":
        return 0
    try:
        amount = int(str(value).strip())
    except ValueError:
        errors.append(f"{label} must be a whole number.")
        return 0
    if amount < 0:
        errors.append(f"{label} cannot be negative.")
        return 0
    if amount % XIANXIA_REALM_ASCENSION_TRADE_UNIT != 0:
        errors.append(
            f"{label} must be 0 or a multiple of {XIANXIA_REALM_ASCENSION_TRADE_UNIT}."
        )
    if amount > current_maximum:
        errors.append(f"{label} cannot exceed the current maximum of {current_maximum}.")
    return amount


def _durability_maxima(value: Any) -> dict[str, int]:
    durability = dict(value or {}) if isinstance(value, dict) else {}
    return {
        "hp_max": _non_negative_int(durability.get("hp_max"), default=10),
        "stance_max": _non_negative_int(durability.get("stance_max"), default=10),
    }


def _realm_ascension_trade_context(durability: dict[str, int]) -> dict[str, int | bool]:
    hp_max = _non_negative_int(durability.get("hp_max"), default=0)
    stance_max = _non_negative_int(durability.get("stance_max"), default=0)
    hp_maximum_trade = (
        hp_max // XIANXIA_REALM_ASCENSION_TRADE_UNIT
    ) * XIANXIA_REALM_ASCENSION_TRADE_UNIT
    stance_maximum_trade = (
        stance_max // XIANXIA_REALM_ASCENSION_TRADE_UNIT
    ) * XIANXIA_REALM_ASCENSION_TRADE_UNIT
    return {
        "unit": XIANXIA_REALM_ASCENSION_TRADE_UNIT,
        "available": hp_maximum_trade > 0 or stance_maximum_trade > 0,
        "hp_max": hp_max,
        "stance_max": stance_max,
        "hp_maximum_trade": hp_maximum_trade,
        "stance_maximum_trade": stance_maximum_trade,
    }


def _realm_ascension_history_snapshot(xianxia: dict[str, Any]) -> dict[str, Any]:
    payload = dict(xianxia or {})
    attributes = {
        key: _non_negative_int(dict(payload.get("attributes") or {}).get(key), default=0)
        for key in XIANXIA_ATTRIBUTE_KEYS
    }
    efforts = {
        key: _non_negative_int(dict(payload.get("efforts") or {}).get(key), default=0)
        for key in XIANXIA_EFFORT_KEYS
    }
    raw_energies = dict(payload.get("energies") or {})
    energies = {
        key: {
            "max": _non_negative_int(
                dict(raw_energies.get(key) or {}).get("max"),
                default=0,
            )
        }
        for key in XIANXIA_ENERGY_KEYS
    }
    raw_yin_yang = dict(payload.get("yin_yang") or {})
    raw_dao = dict(payload.get("dao") or {})
    raw_insight = dict(payload.get("insight") or {})
    raw_durability = dict(payload.get("durability") or {})
    raw_skills = dict(payload.get("skills") or {})
    raw_equipment = dict(payload.get("equipment") or {})
    raw_dao_immolating = dict(payload.get("dao_immolating_techniques") or {})
    return {
        "realm": normalize_xianxia_realm_label(payload.get("realm")),
        "actions_per_turn": _non_negative_int(
            payload.get("actions_per_turn"),
            default=0,
        ),
        "attributes": attributes,
        "attributes_total": sum(attributes.values()),
        "efforts": efforts,
        "efforts_total": sum(efforts.values()),
        "energies": energies,
        "yin_yang": {
            "yin_max": _non_negative_int(raw_yin_yang.get("yin_max"), default=1),
            "yang_max": _non_negative_int(raw_yin_yang.get("yang_max"), default=1),
        },
        "dao": {"max": _non_negative_int(raw_dao.get("max"), default=3)},
        "insight": {
            "available": _non_negative_int(raw_insight.get("available"), default=0),
            "spent": _non_negative_int(raw_insight.get("spent"), default=0),
        },
        "durability": {
            "hp_max": _non_negative_int(raw_durability.get("hp_max"), default=10),
            "stance_max": _non_negative_int(
                raw_durability.get("stance_max"),
                default=10,
            ),
            "manual_armor_bonus": _non_negative_int(
                raw_durability.get("manual_armor_bonus"),
                default=0,
            ),
            "defense": _non_negative_int(raw_durability.get("defense"), default=10),
        },
        "skills": {
            "trained": _clean_string_list(raw_skills.get("trained")),
        },
        "equipment": {
            "necessary_weapons": _copy_record_list(
                raw_equipment.get("necessary_weapons")
            ),
            "necessary_tools": _copy_record_list(raw_equipment.get("necessary_tools")),
        },
        "martial_arts": _copy_record_list(payload.get("martial_arts")),
        "generic_techniques": _copy_record_list(payload.get("generic_techniques")),
        "variants": _copy_record_list(payload.get("variants")),
        "dao_immolating_techniques": {
            "prepared": _copy_record_list(raw_dao_immolating.get("prepared")),
            "use_history": _copy_record_list(raw_dao_immolating.get("use_history")),
        },
        "approval_requests": _copy_record_list(payload.get("approval_requests")),
        "companions": _copy_record_list(payload.get("companions")),
    }


def _realm_ascension_history_snapshot_summary(snapshot: dict[str, Any]) -> str:
    durability = dict(snapshot.get("durability") or {})
    insight = dict(snapshot.get("insight") or {})
    return (
        f"{snapshot.get('realm') or 'Unknown'} Realm, "
        f"{_non_negative_int(snapshot.get('actions_per_turn'), default=0)} actions; "
        f"Attributes {_non_negative_int(snapshot.get('attributes_total'), default=0)}, "
        f"Efforts {_non_negative_int(snapshot.get('efforts_total'), default=0)}; "
        f"HP max {_non_negative_int(durability.get('hp_max'), default=0)}, "
        f"Stance max {_non_negative_int(durability.get('stance_max'), default=0)}; "
        f"Insight {_non_negative_int(insight.get('available'), default=0)} available/"
        f"{_non_negative_int(insight.get('spent'), default=0)} spent; "
        f"Martial Arts {len(list(snapshot.get('martial_arts') or []))}; "
        f"Generic Techniques {len(list(snapshot.get('generic_techniques') or []))}"
    )


def _realm_ascension_snapshot_from_event(record: dict[str, Any]) -> dict[str, Any]:
    snapshot = record.get("pre_ascension_state")
    return deepcopy(snapshot) if isinstance(snapshot, dict) else {}


def _copy_record_list(values: Any) -> list[dict[str, Any]]:
    if isinstance(values, dict):
        values = [values]
    records: list[dict[str, Any]] = []
    for value in list(values or []):
        if isinstance(value, dict) and value:
            records.append(deepcopy(value))
    return records


def _clean_string_list(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    cleaned_values: list[str] = []
    for value in list(values or []):
        cleaned = _clean_note(value)
        if cleaned:
            cleaned_values.append(cleaned)
    return cleaned_values


def _stat_rows(
    values: Any,
    keys: tuple[str, ...],
    labels: dict[str, str],
) -> dict[str, Any]:
    mapping = dict(values or {}) if isinstance(values, dict) else {}
    rows = [
        {
            "key": key,
            "label": labels.get(key, key.replace("_", " ").title()),
            "score": _non_negative_int(mapping.get(key), default=0),
        }
        for key in keys
    ]
    return {
        "rows": rows,
        "total": sum(int(row["score"]) for row in rows),
    }


def _first_present_value(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _list_copy(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [dict(item) if isinstance(item, dict) else item for item in value]
    if value is None or value == "":
        return []
    return [value]


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _rank_teacher_breakthrough_notes(
    record: dict[str, Any],
) -> dict[str, dict[str, str]]:
    raw_notes = record.get("rank_teacher_breakthrough_notes")
    if not isinstance(raw_notes, dict):
        return {}
    normalized: dict[str, dict[str, str]] = {}
    for raw_rank_key, raw_note in raw_notes.items():
        rank_key = normalize_xianxia_martial_art_rank_key(raw_rank_key)
        if not rank_key:
            continue
        if isinstance(raw_note, dict):
            requirement = (
                normalize_xianxia_martial_art_rank_key(raw_note.get("requirement"))
                or "none"
            )
            note = " ".join(str(raw_note.get("note") or "").split()).strip()
        else:
            requirement = "none"
            note = " ".join(str(raw_note or "").split()).strip()
        if requirement != "none" or note:
            normalized[rank_key] = {
                "requirement": requirement,
                "note": note,
            }
    return normalized


def _rank_legendary_prerequisite_notes(
    record: dict[str, Any],
) -> dict[str, dict[str, str]]:
    raw_notes = record.get("rank_legendary_prerequisite_notes")
    if not isinstance(raw_notes, dict):
        return {}
    normalized: dict[str, dict[str, str]] = {}
    for raw_rank_key, raw_note in raw_notes.items():
        rank_key = normalize_xianxia_martial_art_rank_key(raw_rank_key)
        if not rank_key:
            continue
        if isinstance(raw_note, dict):
            requirement = (
                normalize_xianxia_martial_art_rank_key(raw_note.get("requirement"))
                or "quest_or_mythic_master"
            )
            note = _clean_note(raw_note.get("note"))
            prerequisite_note = _clean_note(raw_note.get("prerequisite_note"))
        else:
            requirement = "quest_or_mythic_master"
            note = _clean_note(raw_note)
            prerequisite_note = ""
        if note:
            normalized[rank_key] = {
                "requirement": requirement,
                "note": note,
            }
            if prerequisite_note:
                normalized[rank_key]["prerequisite_note"] = prerequisite_note
    return normalized


def _apply_energy_maximum_increases(
    raw_energies: Any,
    increases: dict[str, int],
) -> dict[str, dict[str, int]]:
    energies = dict(raw_energies or {}) if isinstance(raw_energies, dict) else {}
    updated: dict[str, dict[str, int]] = {}
    for key in XIANXIA_ENERGY_KEYS:
        energy = dict(energies.get(key) or {})
        current_max = _non_negative_int(energy.get("max"), default=0)
        updated[key] = {
            "max": current_max + _non_negative_int(increases.get(key), default=0)
        }
    return updated


def _apply_yin_yang_maximum_increase(
    raw_yin_yang: Any,
    yin_yang_key: str,
    increase: int,
) -> dict[str, int]:
    yin_yang = dict(raw_yin_yang or {}) if isinstance(raw_yin_yang, dict) else {}
    updated = {
        "yin_max": _non_negative_int(yin_yang.get("yin_max"), default=1),
        "yang_max": _non_negative_int(yin_yang.get("yang_max"), default=1),
    }
    max_key = f"{yin_yang_key}_max"
    updated[max_key] = updated[max_key] + _non_negative_int(increase, default=0)
    return updated


def _non_negative_int(value: Any, *, default: int = 0) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, normalized)
