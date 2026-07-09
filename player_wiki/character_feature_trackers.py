from __future__ import annotations

from typing import Any, Callable

from .character_builder_constants import DEFAULT_ABILITY_SCORE
from .managed_resource_registry import resolve_managed_resource_family_and_member
from .repository import normalize_lookup


def _proficiency_bonus_for_level(level: int) -> int:
    clean_level = max(int(level or 1), 1)
    return 2 + ((clean_level - 1) // 4)


def _ability_modifier(score: int) -> int:
    return (int(score) - 10) // 2


def _resource_value_by_level(current_level: int, thresholds: list[tuple[int, int]]) -> int:
    value = 0
    for minimum_level, scaled_value in thresholds:
        if current_level >= minimum_level:
            value = scaled_value
    return value


def _resolve_managed_resource_formula_value(
    formula: dict[str, Any],
    *,
    ability_scores: dict[str, int],
    current_level: int,
) -> int:
    kind = str(formula.get("kind") or "").strip().lower()
    minimum_value = formula.get("minimum")
    value = 0
    if kind == "fixed":
        value = int(formula.get("value") or 0)
    elif kind == "level":
        value = int(current_level) * int(formula.get("multiplier") or 1) + int(formula.get("bonus") or 0)
    elif kind == "proficiency_bonus":
        value = _proficiency_bonus_for_level(current_level) * int(formula.get("multiplier") or 1) + int(formula.get("bonus") or 0)
    elif kind == "ability_modifier":
        ability_key = str(formula.get("ability") or "").strip().lower()
        value = _ability_modifier(ability_scores.get(ability_key, DEFAULT_ABILITY_SCORE)) + int(formula.get("bonus") or 0)
    elif kind == "threshold":
        value = _resource_value_by_level(
            current_level,
            [(int(level), int(scaled_value)) for level, scaled_value in list(formula.get("thresholds") or [])],
        )
    elif kind == "sum":
        value = sum(
            _resolve_managed_resource_formula_value(
                dict(part or {}),
                ability_scores=ability_scores,
                current_level=current_level,
            )
            for part in list(formula.get("parts") or [])
            if isinstance(part, dict)
        )
    if minimum_value not in {"", None}:
        value = max(value, int(minimum_value))
    return max(value, 0)


def apply_managed_resource_member_defaults(feature_payload: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    family, member = resolve_managed_resource_family_and_member(feature_payload)
    if member is None:
        return family, member
    activation_type = str(member.get("activation_type") or "").strip()
    if activation_type:
        feature_payload["activation_type"] = activation_type
    if not str(feature_payload.get("description_markdown") or "").strip():
        description = str(member.get("description_markdown") or "").strip()
        if description:
            feature_payload["description_markdown"] = description
    return family, member


def build_managed_resource_tracker_template(
    member: dict[str, Any],
    feature_payload: dict[str, Any],
    *,
    ability_scores: dict[str, int],
    current_level: int,
    display_order: int,
) -> dict[str, Any] | None:
    tracker = dict(member.get("tracker") or {})
    if not tracker:
        return None
    max_value = _resolve_managed_resource_formula_value(
        dict(tracker.get("max_formula") or {}),
        ability_scores=ability_scores,
        current_level=current_level,
    )
    if max_value <= 0:
        return None
    reset_on = str(tracker.get("reset_on") or "manual").strip() or "manual"
    reset_to = tracker.get("reset_to", "max" if reset_on in {"short_rest", "long_rest"} else "unchanged")
    rest_behavior = str(tracker.get("rest_behavior") or "").strip()
    if not rest_behavior:
        rest_behavior = "confirm_before_reset" if reset_on in {"short_rest", "long_rest"} else "manual_only"
    return {
        "id": str(tracker.get("id") or "").strip(),
        "label": str(tracker.get("label") or feature_payload.get("name") or "").strip(),
        "category": str(feature_payload.get("category") or "class_feature").strip() or "class_feature",
        "initial_current": max_value,
        "max": max_value,
        "reset_on": reset_on,
        "reset_to": reset_to,
        "rest_behavior": rest_behavior,
        "notes": str(tracker.get("notes") or feature_payload.get("name") or "").strip(),
        "display_order": display_order,
        "activation_type": str(tracker.get("activation_type") or member.get("activation_type") or "passive").strip() or "passive",
    }


def feature_has_effect(effect_keys: set[str], *values: str) -> bool:
    return any(normalize_lookup(value) in effect_keys for value in values if str(value or "").strip())


def build_feature_tracker_template(
    feature_payload: dict[str, Any],
    *,
    ability_scores: dict[str, int],
    current_level: int,
    display_order: int,
    managed_resource_member: dict[str, Any] | None = None,
    feat_effect_keys_for_feature: Callable[[dict[str, Any]], list[str]],
) -> dict[str, Any] | None:
    if managed_resource_member is not None:
        managed_template = build_managed_resource_tracker_template(
            dict(managed_resource_member),
            feature_payload,
            ability_scores=ability_scores,
            current_level=current_level,
            display_order=display_order,
        )
        if managed_template is not None:
            if normalize_lookup(str(feature_payload.get("name") or "").strip()) == normalize_lookup("Bardic Inspiration") and current_level >= 5:
                managed_template["reset_on"] = "short_rest"
            return managed_template

    normalized = normalize_lookup(str(feature_payload.get("name") or "").strip())
    effect_keys = {normalize_lookup(value) for value in feat_effect_keys_for_feature(feature_payload) if str(value or "").strip()}
    if feature_has_effect(effect_keys, "Chef"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "chef-treats",
            "label": "Chef Treats",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Chef treats",
            "display_order": display_order,
            "activation_type": "bonus_action",
        }
    if feature_has_effect(effect_keys, "Poisoner"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "poisoner-doses",
            "label": "Poisoner Doses",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Poisoner doses",
            "display_order": display_order,
            "activation_type": "bonus_action",
        }
    if feature_has_effect(effect_keys, "Gift of the Metallic Dragon"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "protective-wings",
            "label": "Protective Wings",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Protective Wings",
            "display_order": display_order,
            "activation_type": "reaction",
        }
    if normalized == normalize_lookup("Gift of the Chromatic Dragon: Chromatic Infusion"):
        return {
            "id": "chromatic-infusion",
            "label": "Chromatic Infusion",
            "category": "feat",
            "initial_current": 1,
            "max": 1,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Chromatic Infusion",
            "display_order": display_order,
            "activation_type": "bonus_action",
        }
    if normalized == normalize_lookup("Gift of the Chromatic Dragon: Reactive Resistance"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "reactive-resistance",
            "label": "Reactive Resistance",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Reactive Resistance",
            "display_order": display_order,
            "activation_type": "reaction",
        }
    if feature_has_effect(effect_keys, "Gift of the Gem Dragon"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "telekinetic-reprisal",
            "label": "Telekinetic Reprisal",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Telekinetic Reprisal",
            "display_order": display_order,
            "activation_type": "reaction",
        }
    if feature_has_effect(effect_keys, "Lucky"):
        return {
            "id": "lucky",
            "label": "Lucky",
            "category": "feat",
            "initial_current": 3,
            "max": 3,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Lucky",
            "display_order": display_order,
            "activation_type": "special",
        }
    if feature_has_effect(effect_keys, "Dragon Fear"):
        return {
            "id": "dragon-fear",
            "label": "Dragon Fear",
            "category": "feat",
            "initial_current": 1,
            "max": 1,
            "reset_on": "short_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Dragon Fear",
            "display_order": display_order,
            "activation_type": "special",
        }
    if feature_has_effect(effect_keys, "Orcish Fury"):
        return {
            "id": "orcish-fury",
            "label": "Orcish Fury",
            "category": "feat",
            "initial_current": 1,
            "max": 1,
            "reset_on": "short_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Orcish Fury",
            "display_order": display_order,
            "activation_type": "special",
        }
    if feature_has_effect(effect_keys, "Second Chance"):
        return {
            "id": "second-chance",
            "label": "Second Chance",
            "category": "feat",
            "initial_current": 1,
            "max": 1,
            "reset_on": "short_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Second Chance",
            "display_order": display_order,
            "activation_type": "reaction",
        }
    if feature_has_effect(effect_keys, "Martial Adept"):
        return {
            "id": "martial-adept",
            "label": "Martial Adept",
            "category": "feat",
            "initial_current": 1,
            "max": 1,
            "reset_on": "short_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Superiority Die (d6)",
            "display_order": display_order,
            "activation_type": "special",
        }
    if feature_has_effect(effect_keys, "Metamagic Adept"):
        return {
            "id": "metamagic-adept",
            "label": "Metamagic Adept Sorcery Points",
            "category": "feat",
            "initial_current": 2,
            "max": 2,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Metamagic Adept Sorcery Points",
            "display_order": display_order,
            "activation_type": "special",
        }
    if feature_has_effect(effect_keys, "Adept of the Red Robes"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "magical-balance",
            "label": "Magical Balance",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Magical Balance",
            "display_order": display_order,
            "activation_type": "special",
        }
    if feature_has_effect(effect_keys, "Agent of Order"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "stasis-strike",
            "label": "Stasis Strike",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Stasis Strike",
            "display_order": display_order,
            "activation_type": "special",
        }
    if feature_has_effect(effect_keys, "Baleful Scion"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "grasp-of-avarice",
            "label": "Grasp of Avarice",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Grasp of Avarice",
            "display_order": display_order,
            "activation_type": "special",
        }
    if feature_has_effect(effect_keys, "Ember of the Fire Giant"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "searing-ignition",
            "label": "Searing Ignition",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Searing Ignition",
            "display_order": display_order,
            "activation_type": "action",
        }
    if feature_has_effect(effect_keys, "Fury of the Frost Giant"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "frigid-retaliation",
            "label": "Frigid Retaliation",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Frigid Retaliation",
            "display_order": display_order,
            "activation_type": "reaction",
        }
    if feature_has_effect(effect_keys, "Guile of the Cloud Giant"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "cloudy-escape",
            "label": "Cloudy Escape",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Cloudy Escape",
            "display_order": display_order,
            "activation_type": "reaction",
        }
    if feature_has_effect(effect_keys, "Keenness of the Stone Giant"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "stone-throw",
            "label": "Stone Throw",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Stone Throw",
            "display_order": display_order,
            "activation_type": "bonus_action",
        }
    if feature_has_effect(effect_keys, "Knight of the Crown"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "commanding-rally",
            "label": "Commanding Rally",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Commanding Rally",
            "display_order": display_order,
            "activation_type": "bonus_action",
        }
    if feature_has_effect(effect_keys, "Knight of the Rose"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "bolstering-rally",
            "label": "Bolstering Rally",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Bolstering Rally",
            "display_order": display_order,
            "activation_type": "bonus_action",
        }
    if feature_has_effect(effect_keys, "Knight of the Sword"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "demoralizing-strike",
            "label": "Demoralizing Strike",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Demoralizing Strike",
            "display_order": display_order,
            "activation_type": "special",
        }
    if feature_has_effect(effect_keys, "Righteous Heritor"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "soothe-pain",
            "label": "Soothe Pain",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Soothe Pain",
            "display_order": display_order,
            "activation_type": "reaction",
        }
    if feature_has_effect(effect_keys, "Soul of the Storm Giant"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "maelstrom-aura",
            "label": "Maelstrom Aura",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Maelstrom Aura",
            "display_order": display_order,
            "activation_type": "bonus_action",
        }
    if feature_has_effect(effect_keys, "Squire of Solamnia"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "precise-strike",
            "label": "Precise Strike",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Precise Strike",
            "display_order": display_order,
            "activation_type": "special",
        }
    if feature_has_effect(effect_keys, "Strike of the Giants"):
        uses = _proficiency_bonus_for_level(current_level)
        return {
            "id": "strike-of-the-giants",
            "label": "Strike of the Giants",
            "category": "feat",
            "initial_current": uses,
            "max": uses,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Strike of the Giants",
            "display_order": display_order,
            "activation_type": "special",
        }
    if feature_has_effect(effect_keys, "Boon of Recovery"):
        return {
            "id": "recover-vitality-dice",
            "label": "Recover Vitality Dice",
            "category": "feat",
            "initial_current": 10,
            "max": 10,
            "reset_on": "long_rest",
            "reset_to": "max",
            "rest_behavior": "confirm_before_reset",
            "notes": "Recover Vitality d10s",
            "display_order": display_order,
            "activation_type": "bonus_action",
        }
    return None

__all__ = [
    "apply_managed_resource_member_defaults",
    "build_feature_tracker_template",
    "build_managed_resource_tracker_template",
    "feature_has_effect",
]
