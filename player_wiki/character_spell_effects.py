"""Effective DND spell metrics. This module never writes an equipment effect to a definition."""

from copy import deepcopy
from typing import Any

from .repository import normalize_lookup

METRICS = ("spell_attack_bonus", "spell_save_dc")
MISSING_OVERRIDE_AUTHORITY_KEY = "_effective_missing_override_authority"


class _VerifiedMissingOverride:
    def __deepcopy__(self, memo):
        return self


VERIFIED_MISSING_OVERRIDE = _VerifiedMissingOverride()


def _metric_records(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("spell_metric_provenance")
    return dict(raw) if isinstance(raw, dict) else {}


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def metric_provenance(payload: dict[str, Any], metric: str) -> dict[str, Any]:
    raw = _metric_records(payload).get(metric)
    if not isinstance(raw, dict):
        return {"kind": "manual_total"}
    kind = str(raw.get("kind") or "").strip()
    if kind not in {"formula", "manual_total"}:
        return {"kind": "manual_total"}
    result = {"kind": kind}
    # An adjustment or final override needs a concrete, reviewable source identity.
    source = raw.get("source")
    if isinstance(source, str):
        source = source.strip()
    elif isinstance(source, dict):
        source = {str(k): str(v).strip() for k, v in source.items() if str(v).strip()}
    else:
        source = None
    if source:
        result["source"] = source
        for key in ("adjustment", "final_override"):
            value = _integer(raw.get(key))
            if value is not None:
                result[key] = value
    return result


def reconcile_formula_row(
    saved: dict[str, Any] | None, calculated: dict[str, Any], *,
    legacy_delta: int = 0, prefer_calculated_unmarked: bool = False,
) -> dict[str, Any]:
    """Retain legacy offsets while advancing unmarked closed-sheet math."""
    result = dict(calculated)
    prior = dict(saved or {})
    provenance: dict[str, dict[str, Any]] = {}
    for metric in METRICS:
        raw_prior = prior.get(metric)
        prior_provenance = metric_provenance(prior, metric)
        raw_metric_provenance = _metric_records(prior).get(metric)
        if raw_metric_provenance is None and raw_prior is not None:
            if prefer_calculated_unmarked and calculated.get(metric) is not None:
                result[metric] = calculated[metric]
            elif isinstance(raw_prior, bool):
                result[metric] = raw_prior
            else:
                try:
                    result[metric] = int(raw_prior) + legacy_delta
                except (TypeError, ValueError):
                    result[metric] = raw_prior
            # Absence is durable provenance: a later closed-sheet change must
            # still advance this saved value without claiming formula authority.
        elif prior_provenance["kind"] != "formula" and (
            raw_prior is not None or "final_override" in prior_provenance
        ):
            if raw_prior is not None:
                result[metric] = raw_prior
            provenance[metric] = prior_provenance
        else:
            provenance[metric] = (
                prior_provenance if prior_provenance["kind"] == "formula"
                else {"kind": "formula"}
            )
        if isinstance(raw_metric_provenance, dict) and any(
            key in raw_metric_provenance and key not in prior_provenance
            for key in ("adjustment", "final_override")
        ):
            provenance[metric] = deepcopy(raw_metric_provenance)
    if provenance:
        result["spell_metric_provenance"] = provenance
    else:
        result.pop("spell_metric_provenance", None)
    return result


def _approved_effects(item: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    effects: list[dict[str, Any]] = []
    warnings: list[str] = []
    allowed_fields = {
        "effect_id", "spell_attack_bonus", "spell_save_dc",
        "class_row_id", "source_row_id", "class_selector",
    }
    for raw in list(item.get("spellcasting_modifiers") or []):
        if not isinstance(raw, dict):
            warnings.append("unsupported spell modifier metadata")
            continue
        effect_id = str(raw.get("effect_id") or "").strip()
        if set(raw) - allowed_fields:
            warnings.append(f"unknown field for spell modifier {effect_id or 'unknown'}")
            continue
        if not isinstance(raw.get("effect_id"), str) or not effect_id:
            warnings.append("invalid spell modifier identity or scope")
            continue
        if any(
            key in raw and (not isinstance(raw[key], str) or not raw[key].strip())
            for key in ("class_row_id", "source_row_id")
        ):
            warnings.append(f"invalid scope for spell modifier {effect_id}")
            continue
        target_class = str(raw.get("class_row_id") or "").strip()
        target_source = str(raw.get("source_row_id") or "").strip()
        raw_selector = raw.get("class_selector")
        class_selector = dict(raw_selector) if isinstance(raw_selector, dict) else {}
        if "class_selector" in raw and (not isinstance(raw_selector, dict) or not raw_selector):
            warnings.append(f"invalid class selector for spell modifier {effect_id or 'unknown'}")
            continue
        if class_selector:
            if set(class_selector) - {"class_name", "source_id", "entry_key"}:
                warnings.append(f"invalid class selector for spell modifier {effect_id or 'unknown'}")
                continue
            class_name = class_selector.get("class_name")
            source_id = class_selector.get("source_id")
            entry_key = class_selector.get("entry_key")
            if not isinstance(class_name, str) or not class_name.strip() or any(
                key in class_selector and (not isinstance(class_selector[key], str) or not class_selector[key].strip())
                for key in ("source_id", "entry_key")
            ):
                warnings.append(f"invalid class selector for spell modifier {effect_id or 'unknown'}")
                continue
            class_selector = {"class_name": class_name.strip()}
            if source_id is not None:
                class_selector["source_id"] = source_id.strip()
            if entry_key is not None:
                class_selector["entry_key"] = entry_key.strip()
        if sum(bool(value) for value in (target_class, target_source, class_selector)) > 1:
            warnings.append("invalid spell modifier identity or scope")
            continue
        values = {metric: _integer(raw.get(metric)) for metric in METRICS}
        if any(metric in raw and values[metric] is None for metric in METRICS):
            warnings.append(f"invalid value for spell modifier {effect_id}")
            continue
        if not any(value is not None for value in values.values()):
            warnings.append(f"unsupported spell modifier {effect_id}")
            continue
        effects.append({"effect_id": effect_id, "class_row_id": target_class,
                        "source_row_id": target_source, "class_selector": class_selector, **values})
    return effects, warnings


def project_spellcasting_item_effects(
    spellcasting: dict[str, Any], item_effect_entries: list[dict[str, Any]],
    *, transient_adjustments: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    projected = deepcopy(dict(spellcasting or {}))
    projected.pop(MISSING_OVERRIDE_AUTHORITY_KEY, None)
    warnings: list[dict[str, str]] = []
    effects: list[dict[str, Any]] = []
    seen_effects: dict[tuple[str, str], dict[str, Any]] = {}
    conflicted_effect_keys: set[tuple[str, str]] = set()
    for item in item_effect_entries:
        approved, problems = _approved_effects(item)
        name = str(item.get("item_name") or item.get("item_id") or "Item")
        warnings.extend({"code": "spell_item_effect_unsupported", "message": f"{name}: {problem}."}
                        for problem in problems)
        for effect in approved:
            # One effect represented by both a Systems entry and page metadata counts once.
            key = (
                str(item.get("item_id") or "").strip(),
                normalize_lookup(effect["effect_id"]),
            )
            if key in seen_effects:
                if effect != seen_effects[key]:
                    conflicted_effect_keys.add(key)
                    warnings.append({"code": "spell_item_effect_conflict",
                                     "message": f"{name}: conflicting metadata for spell effect {effect['effect_id']}."})
                continue
            seen_effects[key] = effect
            effects.append({**effect, "item_id": key[0], "item_name": name})
    effects = [effect for effect in effects if
               (effect["item_id"], normalize_lookup(effect["effect_id"])) not in conflicted_effect_keys]

    class_rows = [row for row in list(projected.get("class_rows") or []) if isinstance(row, dict)]
    class_ids = {str(row.get("class_row_id") or "") for row in class_rows}
    source_ids = {str(row.get("source_row_id") or "") for row in list(projected.get("source_rows") or []) if isinstance(row, dict)}
    usable_effects: list[dict[str, Any]] = []
    for effect in effects:
        selector = effect.get("class_selector") or {}
        if selector:
            matches = []
            for row in class_rows:
                ref = row.get("class_ref")
                if not isinstance(ref, dict) or not str(ref.get("entry_key") or "").strip():
                    continue
                if normalize_lookup(str(row.get("class_name") or "")) != normalize_lookup(selector["class_name"]):
                    continue
                if normalize_lookup(str(ref.get("title") or "")) != normalize_lookup(selector["class_name"]):
                    continue
                if selector.get("source_id") and str(ref.get("source_id") or "").casefold() != selector["source_id"].casefold():
                    continue
                if selector.get("entry_key") and str(ref.get("entry_key") or "") != selector["entry_key"]:
                    continue
                matches.append(row)
            if len(matches) != 1:
                warnings.append({"code": "spell_item_effect_ambiguous_class_selector",
                                 "message": f"{effect['item_name']}: spell modifier class selector is unknown or ambiguous."})
                continue
            effect = {**effect, "class_row_id": str(matches[0].get("class_row_id") or "")}
            if not effect["class_row_id"]:
                warnings.append({"code": "spell_item_effect_ambiguous_class_selector",
                                 "message": f"{effect['item_name']}: spell modifier class selector has no stable row ID."})
                continue
        if (effect["class_row_id"] and effect["class_row_id"] not in class_ids) or (
            effect["source_row_id"] and effect["source_row_id"] not in source_ids
        ):
            warnings.append({"code": "spell_item_effect_unknown_target",
                             "message": f"{effect['item_name']}: spell modifier targets an unknown row."})
        else:
            usable_effects.append(effect)
    effects = usable_effects
    transient = dict(transient_adjustments or {})

    def project_row(row: dict[str, Any], row_kind: str) -> dict[str, Any]:
        result = dict(row)
        trusted_missing_overrides = result.pop(MISSING_OVERRIDE_AUTHORITY_KEY, None)
        row_id = str(row.get("class_row_id" if row_kind == "class" else "source_row_id") or "").strip()
        notes: list[str] = []
        for metric in METRICS:
            provenance = metric_provenance(row, metric)
            raw_provenance = _metric_records(row).get(metric)
            if isinstance(raw_provenance, dict) and any(
                key in raw_provenance and key not in provenance
                for key in ("adjustment", "final_override")
            ):
                notes.append(f"{metric}: unsupported adjustment or override; not automated")
                warnings.append({"code": "spell_metric_provenance_unsupported",
                                 "message": f"{row_id or 'Spell row'}: unsupported {metric} adjustment or override."})
            base = _integer(row.get(metric))
            missing_override_authorized = (
                isinstance(trusted_missing_overrides, dict)
                and trusted_missing_overrides.get(metric) is VERIFIED_MISSING_OVERRIDE
            )
            if base is None and not (missing_override_authorized and "final_override" in provenance):
                # Historical overrides and items cannot restore a suppressed
                # metric. An exact current manager witness can authorize an
                # override even when the saved base was absent.
                result[metric] = None
                notes.append(f"{metric}: unknown; item bonus not automated")
                continue
            if "final_override" in provenance:
                transient_key = "attack_bonus" if metric == "spell_attack_bonus" else "save_dc"
                transient_value = _integer(transient.get(transient_key)) or 0
                result[metric] = provenance["final_override"] + transient_value
                notes.append(f"{metric}: sourced final override")
                continue
            if provenance["kind"] != "formula":
                notes.append(f"{metric}: manual total; item bonus not automated")
                continue
            matching = [effect for effect in effects if
                        (not effect["class_row_id"] and not effect["source_row_id"])
                        or (row_kind == "class" and effect["class_row_id"] == row_id)
                        or (row_kind == "source" and effect["source_row_id"] == row_id)]
            bonus = sum(effect[metric] or 0 for effect in matching)
            result[metric] = base + provenance.get("adjustment", 0) + bonus
            if provenance.get("adjustment"):
                notes.append(f"{metric}: sourced adjustment {provenance['adjustment']:+d}")
            if bonus:
                notes.append(f"{metric}: item bonus {bonus:+d} from " + ", ".join(
                    effect["item_name"] for effect in matching if effect[metric]))
        if notes:
            result["spell_metric_notes"] = list(dict.fromkeys(notes))
        return result

    for key, kind in (("class_rows", "class"), ("source_rows", "source")):
        projected[key] = [project_row(row, kind) for row in list(projected.get(key) or []) if isinstance(row, dict)]
    class_rows = list(projected.get("class_rows") or [])
    if len(class_rows) == 1:
        for metric in METRICS:
            projected[metric] = class_rows[0].get(metric)
        projected["spell_metric_notes"] = list(class_rows[0].get("spell_metric_notes") or [])
    elif class_rows:
        for metric in METRICS:
            projected[metric] = None
    elif not projected.get("source_rows"):
        projected = project_row(projected, "top")
    return projected, warnings
