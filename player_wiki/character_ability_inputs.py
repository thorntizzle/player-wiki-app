"""Durable D&D ability inputs, distinct from the derived sheet values.

An effective zero cannot be inverted through a penalty, and a minimum cannot
be inverted at its floor. Reads retain those values until an authorized editor
confirms the pre-penalty score. Output disagreement is never an author edit.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

KEYS = ("str", "dex", "con", "int", "wis", "cha")
LABELS = dict(zip(KEYS, ("Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma")))
VERSION = 1


class AbilityInputRecoveryRequired(ValueError):
    pass


def score_value(value: Any, default: int = 10) -> int:
    if isinstance(value, dict):
        value = value.get("score")
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def effective_scores(stats: dict[str, Any]) -> dict[str, int]:
    payload = dict(stats.get("ability_scores") or {})
    return {key: score_value(payload.get(key, payload.get(LABELS[key].lower()))) for key in KEYS}


def penalty_totals(stats: dict[str, Any]) -> dict[str, int]:
    from .character_adjustments import _recoverable_ability_score_penalty_totals
    return _recoverable_ability_score_penalty_totals(stats.get("recoverable_penalties"))


def input_records(stats: dict[str, Any]) -> dict[str, dict[str, Any]]:
    payload = stats.get("ability_inputs")
    if not isinstance(payload, dict) or type(payload.get("version")) is not int or payload.get("version") != VERSION:
        return {}
    records = payload.get("scores")
    if not isinstance(records, dict):
        return {}
    result = {}
    for key in KEYS:
        row = records.get(key)
        if not isinstance(row, dict) or not isinstance(row.get("stage"), str) or row.get("stage") not in {"base", "pre_penalty", "unresolved"}:
            continue
        if row["stage"] != "unresolved" and (
            type(row.get("score")) is not int or row["score"] < 0
        ):
            continue
        if type(row.get("fixed_bonus", 0)) is not int:
            continue
        layers = row.get("layers", {"bonus": 0, "minimum": 0})
        if not isinstance(layers, dict) or any(type(layers.get(name, 0)) is not int for name in ("bonus", "minimum")):
            continue
        if layers.get("minimum", 0) < 0 or ("pre_penalty" in row and (type(row["pre_penalty"]) is not int or row["pre_penalty"] < 0)):
            continue
        result[key] = deepcopy(row)
    return result


def write_inputs(stats: dict[str, Any], records: dict[str, dict[str, Any]]) -> None:
    stats["ability_inputs"] = {"version": VERSION, "scores": deepcopy(records)}


def seed_base_inputs(stats: dict[str, Any], scores: dict[str, int], *, provenance: str, fixed_bonuses: dict[str, int] | None = None) -> None:
    write_inputs(stats, {key: {"stage": "base", "score": int(scores[key]), "fixed_bonus": int((fixed_bonuses or {}).get(key, 0)), "provenance": provenance} for key in KEYS})


def resolve_inputs(stats: dict[str, Any], *, bonuses: dict[str, int], minimums: dict[str, int]) -> tuple[dict[str, int], dict[str, dict[str, Any]]]:
    """Resolve pre-penalty scores; return unknown effective values untouched.

    `bonuses` describes the modeled permanent additive layer. An explicit base
    precedes that layer and the minima. A confirmed pre-penalty input includes
    the recorded layers; no earlier base is fabricated through a minimum.
    """
    effective = effective_scores(stats)
    totals = penalty_totals(stats)
    records = input_records(stats)
    pre_penalty = {}
    for key in KEYS:
        bonus, minimum = int(bonuses.get(key, 0)), int(minimums.get(key, 0))
        layers = {"bonus": bonus, "minimum": minimum}
        row = records.get(key)
        if row is None:
            restored = effective[key] + totals[key]
            if (totals[key] and effective[key] == 0) or (minimum and restored <= minimum) or (bonus and restored >= 20):
                row = {"stage": "unresolved", "effective": effective[key], "penalty": totals[key], "layers": layers, "provenance": "legacy_lossy_output", "recovery_stage": "base" if minimum or bonus else "pre_penalty"}
            else:
                base = restored - bonus
                if base < 0:
                    row = {"stage": "unresolved", "effective": effective[key], "penalty": totals[key], "layers": layers, "provenance": "legacy_lossy_output"}
                else:
                    row = {"stage": "base", "score": base, "provenance": "unambiguous_legacy_inverse"}
        if row["stage"] == "base":
            fixed_bonus = int(row.get("fixed_bonus", 0))
            value = row["score"] + fixed_bonus
            if fixed_bonus:
                value = min(value, 20)
            if bonus:
                value = min(value + bonus, 20)
            value = max(value, minimum, 0)
        elif row["stage"] == "pre_penalty":
            previous = row.get("layers", {})
            old_bonus = int(previous.get("bonus", 0))
            old_minimum = int(previous.get("minimum", 0))
            if old_minimum and row["score"] <= old_minimum and previous != layers:
                row = {"stage": "unresolved", "effective": effective[key], "penalty": totals[key], "layers": layers, "provenance": "changed_lossy_layer", "recovery_stage": "base"}
                value = effective[key]
            else:
                value = row["score"] - old_bonus
                if bonus:
                    value = min(value + bonus, 20)
                value = max(value, minimum, 0)
        else:
            value = effective[key]
        row["layers"] = layers if row["stage"] != "pre_penalty" else row.get("layers", layers)
        if row["stage"] != "unresolved":
            row["pre_penalty"] = value
        records[key] = row
        pre_penalty[key] = value
    return pre_penalty, records


def recovery_rows(definition: Any, values: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    stats = dict(definition.stats or {})
    records = input_records(stats)
    totals = penalty_totals(stats)
    scores = effective_scores(stats)
    rows = []
    for key in KEYS:
        row = records.get(key, {})
        if row.get("stage") == "unresolved" or (not row and totals[key] and scores[key] == 0):
            stage = row.get("recovery_stage", "pre_penalty")
            rows.append({"key": key, "label": LABELS[key], "stage": stage, "stage_label": "before ability bonuses and minimums" if stage == "base" else "before recoverable penalties", "effective": scores[key], "penalty": totals[key], "name": f"recover_ability_{key}", "value": str((values or {}).get(f"recover_ability_{key}", ""))})
    return rows


def require_resolved_ability_inputs(definition: Any) -> None:
    if str(getattr(definition, "system", "")).lower() not in {"dnd-5e", "dnd5e", "dnd_5e"}:
        return
    rows = recovery_rows(definition)
    if rows:
        raise AbilityInputRecoveryRequired("Recover original ability scores in Advanced Edit before saving changes that recalculate this character: " + ", ".join(row["label"] for row in rows) + ".")


def recover_inputs(definition: Any, values: dict[str, Any]) -> Any:
    payload = deepcopy(definition.to_dict())
    stats = payload["stats"]
    records = input_records(stats)
    for row in recovery_rows(definition, values):
        raw = str(values.get(row["name"], "")).strip()
        if not raw or not raw.isascii() or not raw.isdecimal():
            raise AbilityInputRecoveryRequired(f"Enter a whole number of zero or more for {row['label']} {row['stage_label']}.")
        score = int(raw)
        old = records.get(row["key"], {})
        records[row["key"]] = {"stage": row["stage"], "score": score, "pre_penalty": score, "layers": deepcopy(old.get("layers", {"bonus": 0, "minimum": 0})), "provenance": "authorized_editor_confirmation"}
    if records:
        write_inputs(stats, records)
    return type(definition).from_dict(payload)


def advance_inputs(stats: dict[str, Any], deltas: dict[str, int], *, fixed_bonuses: dict[str, int] | None = None) -> None:
    """Apply explicit advancement choices to inputs, never the displayed score."""
    records = input_records(stats)
    for key, row in records.items():
        if row["stage"] == "pre_penalty" and int(deltas.get(key, 0)) and int(row.get("layers", {}).get("minimum", 0)) >= row["score"]:
            raise AbilityInputRecoveryRequired(f"Recover {LABELS[key]} before its ability minimum before applying an ability improvement.")
        if row["stage"] != "unresolved":
            row["score"] += int(deltas.get(key, 0))
            fixed_bonus = int((fixed_bonuses or {}).get(key, 0))
            if row["stage"] == "base":
                row["fixed_bonus"] = int(row.get("fixed_bonus", 0)) + fixed_bonus
            elif fixed_bonus:
                row["score"] = min(row["score"] + fixed_bonus, 20)
    if records:
        write_inputs(stats, records)


def advancement_scores(stats: dict[str, Any]) -> dict[str, int]:
    """Ability improvements use permanent abilities before equipment minima."""
    scores = effective_scores(stats)
    for key, row in input_records(stats).items():
        if row["stage"] == "base":
            bonus = int(row.get("fixed_bonus", 0)) + int(row.get("layers", {}).get("bonus", 0))
            scores[key] = min(row["score"] + bonus, 20) if bonus else row["score"]
        elif row["stage"] == "pre_penalty":
            scores[key] = row["score"]
    return scores


def mechanics_changed(previous: Any, desired: Any) -> bool:
    """Content-file writes retain their existing non-deriving storage contract."""
    for name in ('stats', 'skills', 'proficiencies', 'attacks', 'features', 'spellcasting', 'equipment_catalog', 'resource_templates', 'system'):
        if getattr(previous, name) != getattr(desired, name):
            return True
    for key in ('classes', 'class_ref', 'class_name', 'class_level_text', 'subclass_ref', 'species', 'species_ref', 'species_page_ref', 'background', 'background_ref', 'background_page_ref', 'size'):
        if previous.profile.get(key) != desired.profile.get(key):
            return True
    for key in ('native_progression', 'source_type'):
        if previous.source.get(key) != desired.source.get(key):
            return True
    return False
