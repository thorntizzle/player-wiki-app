"""Exact reconstructed HP inputs, separate from current/spent play state.

The v1 pool is an explicit physical Hit Die contribution.  It is never
recovered by subtracting bonuses from the displayed HP maximum.  Existing
integer native baselines keep their original meaning.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from typing import Any, Mapping


class HitPointRecipeError(ValueError):
    pass


def _integer(value: Any, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise HitPointRecipeError("The HP recipe contains an invalid whole number.")
    return value


def rational(value: Any) -> Fraction:
    if (not isinstance(value, dict) or set(value) != {"numerator", "denominator"}):
        raise HitPointRecipeError("Enter an exact HP contribution, including its denominator.")
    return Fraction(_integer(value["numerator"], -100000, 100000),
                    _integer(value["denominator"], 1, 1000))


def canonical_recipe(value: Any, *, faces: int | None = None) -> dict[str, Any]:
    fields = {"schema_version", "boundary_level", "reference_constitution",
              "pools", "corrections", "history_start", "retained_history_end", "continuing_effects"}
    if (not isinstance(value, dict) or set(value) != fields
            or type(value.get("schema_version")) is not int or value["schema_version"] != 1):
        raise HitPointRecipeError("The reconstructed HP recipe version is unavailable.")
    boundary = _integer(value["boundary_level"], 1, 20)
    _integer(value["reference_constitution"], 0, 100)
    _integer(value["history_start"], 0, 512)
    _integer(value["retained_history_end"], value["history_start"], 512)
    pools = value["pools"]
    if not isinstance(pools, list) or not 1 <= len(pools) <= 20:
        raise HitPointRecipeError("The HP recipe needs its explicit covered levels.")
    expected = 1
    for row in pools:
        if (not isinstance(row, dict) or set(row) != {
                "from_level", "to_level", "aggregate", "policy", "provenance"}
                or row.get("provenance") not in {"original", "confirmed", "reconstructed"}
                or row.get("policy") not in {"maximum", "accepted_pool", "known_gain"}):
            raise HitPointRecipeError("The HP pool needs its policy and input provenance.")
        first = _integer(row["from_level"], 1, boundary)
        last = _integer(row["to_level"], first, boundary)
        total = rational(row["aggregate"])
        count = last - first + 1
        if first != expected or total < count or (faces is not None and total > faces * count):
            raise HitPointRecipeError("HP pool levels overlap, are missing, or exceed their Hit Dice.")
        if first <= 3 and (last > 3 or row["policy"] != "maximum"):
            raise HitPointRecipeError("Levels one through three must retain the maximum Hit Die policy.")
        if row["policy"] == "maximum" and faces is not None and total != faces * count:
            raise HitPointRecipeError("The maximum Hit Die pool does not match the class.")
        if row["policy"] == "known_gain" and (first != last or total.denominator != 1):
            raise HitPointRecipeError("A known HP gain must describe one actual level.")
        expected = last + 1
    if expected != boundary + 1:
        raise HitPointRecipeError("The HP recipe does not cover its complete boundary.")
    corrections = value["corrections"]
    if not isinstance(corrections, list) or len(corrections) > 16:
        raise HitPointRecipeError("There are too many HP corrections.")
    seen = set()
    for row in corrections:
        if (not isinstance(row, dict) or set(row) != {"id", "amount", "provenance"}
                or not isinstance(row.get("id"), str) or not 1 <= len(row["id"]) <= 160
                or row["id"] in seen
                or row.get("provenance") not in {"original", "confirmed", "reconstructed"}):
            raise HitPointRecipeError("HP corrections need unique identities and provenance.")
        seen.add(row["id"])
        rational(row["amount"])
    effects = value["continuing_effects"]
    if not isinstance(effects, list) or len(effects) > 16:
        raise HitPointRecipeError("The HP recipe needs a bounded continuing-effect ledger.")
    seen.clear()
    for row in effects:
        if (not isinstance(row, dict) or set(row) != {"owner_id", "per_level"}
                or not isinstance(row.get("owner_id"), str) or not 1 <= len(row["owner_id"]) <= 160
                or row["owner_id"] in seen):
            raise HitPointRecipeError("The HP effect ledger has an ambiguous owner.")
        seen.add(row["owner_id"])
        _integer(row["per_level"], -100, 100)
    return deepcopy(value)


def evaluate_recipe(value: Any, history: Any, *, level: int, constitution: int,
                    faces: int | None = None) -> int:
    """Evaluate physical contributions and current CON exactly once.

    The explicitly owned continuing effects are applied once after the
    physical contributions; corrections are one-time physical contributions.
    Only real subsequent level-up events occur after history_start.
    """
    recipe = canonical_recipe(value, faces=faces)
    _integer(level, recipe["boundary_level"], 20)
    _integer(constitution, 0, 100)
    if not isinstance(history, list) or len(history) > 512 or len(history) < recipe["history_start"]:
        raise HitPointRecipeError("The HP recipe's retained history is unavailable.")
    total = sum((rational(row["aggregate"]) for row in recipe["pools"]), Fraction())
    total += sum((rational(row["amount"]) for row in recipe["corrections"]), Fraction())
    current = recipe["boundary_level"]
    modifier = (constitution - 10) // 2
    if modifier < 0 and any(row["policy"] == "accepted_pool" and (
            faces is None or rational(row["aggregate"]) != faces * (row["to_level"] - row["from_level"] + 1))
            for row in recipe["pools"]):
        raise HitPointRecipeError("Negative Constitution needs individual HP contributions before minimum-one arithmetic can be proved.")
    reference_modifier = (recipe["reference_constitution"] - 10) // 2
    total += modifier * recipe["boundary_level"]
    for index, event in enumerate(history[recipe["history_start"]:], start=recipe["history_start"]):
        if not isinstance(event, dict):
            raise HitPointRecipeError("The HP continuation event is malformed.")
        if event.get("kind") != "level_up":
            continue
        if (event.get("from_level") != current or event.get("to_level") != current + 1
                or event.get("target_level") != current + 1):
            raise HitPointRecipeError("The HP continuation is not sequential.")
        if index < recipe["retained_history_end"]:
            if recipe["continuing_effects"]:
                raise HitPointRecipeError(
                    "Retained whole HP gains with continuing effects need explicit included-effect evidence; "
                    "this reconstruction cannot publish that ambiguous combination.")
            # A retained whole gain is not relabeled as an original die roll.
            total += _integer(event.get("max_hp_delta"), 1, 1000) + modifier - reference_modifier
        else:
            total += max(1, _integer(event.get("physical_hp_gain"), 1, faces or 100) + modifier)
        current += 1
    if current != level:
        raise HitPointRecipeError("The HP recipe does not reach the current level.")
    total += sum(row["per_level"] for row in recipe["continuing_effects"]) * level
    if total.denominator != 1 or total < 1:
        raise HitPointRecipeError("The complete HP recipe must produce an exact positive maximum.")
    return total.numerator


def next_level_maximum(value: Any, history: Any, *, level: int, constitution: int,
                       faces: int, physical_hp_gain: int) -> int:
    """One prospective physical event, shared by preview and strict save."""
    _integer(faces, 1, 100)
    _integer(physical_hp_gain, 1, faces)
    _integer(level, 2, 20)
    if not isinstance(history, list):
        raise HitPointRecipeError("The HP recipe's retained history is unavailable.")
    events = deepcopy(history)
    events.append({"kind": "level_up", "from_level": level - 1,
                   "to_level": level, "target_level": level,
                   "physical_hp_gain": physical_hp_gain})
    return evaluate_recipe(value, events, level=level, constitution=constitution, faces=faces)


def recorded_level_maximum(value: Any, history: Any, *, level: int, constitution: int,
                           faces: int, whole_hp_gain: int) -> tuple[int, dict[str, Any]]:
    """Append one known whole increase without manufacturing physical inputs.

    The first supported boundary is deliberately narrower than ordinary native
    advancement: no continuing effects, Constitution change or intervening
    physical event can be hidden inside the recorded whole increment.
    """
    _integer(faces, 1, 100)
    recipe = canonical_recipe(value, faces=faces)
    _integer(whole_hp_gain, 1, 1000)
    _integer(level, 2, 20)
    if (not isinstance(history, list) or recipe["retained_history_end"] != len(history)
            or recipe["continuing_effects"] or constitution != recipe["reference_constitution"]):
        raise HitPointRecipeError(
            "This recorded gain needs unchanged Constitution, no continuing HP effects, "
            "and a complete retained history without later physical events.")
    # Prove that the old recipe reaches precisely the preceding level first.
    evaluate_recipe(recipe, history, level=level - 1, constitution=constitution, faces=faces)
    events = deepcopy(history)
    events.append({"kind": "level_up", "from_level": level - 1,
                   "to_level": level, "target_level": level, "max_hp_delta": whole_hp_gain})
    recipe["retained_history_end"] = len(events)
    return evaluate_recipe(recipe, events, level=level, constitution=constitution, faces=faces), recipe


def recipe_for_source(source: Mapping[str, Any] | None) -> dict[str, Any] | None:
    progression = dict(dict(source or {}).get("native_progression") or {})
    value = progression.get("hp_recipe")
    return canonical_recipe(value) if value is not None else None
