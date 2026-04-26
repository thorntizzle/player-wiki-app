from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .xianxia_character_model import (
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


def normalize_xianxia_effort_key(value: Any) -> str:
    return (
        str(value if value is not None else "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


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
