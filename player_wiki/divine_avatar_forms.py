from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any, Callable

from .character_campaign_options import (
    normalize_campaign_mechanic_effects, _normalize_mechanic_effect_kind,
)
from .repository import normalize_lookup
from .system_policy import supports_divine_avatar_forms


DIVINE_AVATAR_FORMS_STATE_KEY = "divine_avatar_forms"
DIVINE_AVATAR_FORMS_SCHEMA_VERSION = 1
DIVINE_AVATAR_MECHANIC_KEY = "divine_avatar_forms"
DIVINE_AVATAR_MECHANIC_VERSION = 1
DIVINE_AVATAR_FORM_GRANT_KIND = "divine_avatar_form_grant"
DIVINE_AVATAR_FORMS_LEGACY_PAGE_REF = "mechanics/divine-avatar-forms"
DIVINE_AVATAR_ACTION_HISTORY_LIMIT = 20

AVATAR_OF_MOURNING_FORM_KEY = "avatar_of_mourning"
AVATAR_OF_MOURNING_FORM_VERSION = 1
AVATAR_OF_MOURNING_MAX_ROUNDS = 10
AVATAR_OF_MOURNING_COOLDOWN_DAYS = 40

DIVINE_AVATAR_ACTION_SUCCESS_MESSAGES = {
    "activate": "Avatar of Mourning activated.",
    "mourning_wave": "Mourning Wave marked used.",
    "strength_of_remembrance": "Strength of Remembrance marked used.",
    "end": "Avatar of Mourning ended; resolve its radiant damage.",
    "cooldown_complete": "Avatar of Mourning's cooldown marked complete.",
    "resolve_end_cost": "Avatar of Mourning's end cost resolved.",
    "correct_end_cost": "Avatar of Mourning's end cost corrected.",
    "correct_mourning_wave": "Mourning Wave use corrected.",
    "correct_strength_of_remembrance": "Strength of Remembrance use corrected.",
    "correct_cooldown_complete": "Avatar of Mourning's cooldown correction applied.",
    "undo_last_action": "The last Divine Avatar Form action was undone.",
    "advance_turn": "Avatar of Mourning advanced one turn.",
}


@dataclass(frozen=True, slots=True)
class DivineAvatarFormAdapter:
    form_key: str
    form_version: int
    label: str
    max_rounds: int
    cooldown_days: int
    normalize_state: Callable[[Any], dict[str, Any]]
    transient_effects: Callable[[], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class DivineAvatarTransition:
    state: dict[str, Any]
    action: str
    form_key: str
    changed: bool


def _coerce_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bounded_int(value: Any, *, minimum: int = 0, maximum: int) -> int:
    return max(minimum, min(maximum, _coerce_int(value)))


def _clean_token(value: Any) -> str:
    return str(value or "").strip()


def _record_invalid_container(
    payload: dict[str, Any],
    key: str,
    value: Any,
    message: str,
) -> None:
    invalid_containers = (
        deepcopy(payload.get("invalid_containers"))
        if isinstance(payload.get("invalid_containers"), dict)
        else {}
    )
    invalid_containers[key] = deepcopy(value)
    payload["invalid_containers"] = invalid_containers
    errors = [
        _clean_token(error)
        for error in list(payload.get("normalization_errors") or [])
        if _clean_token(error)
    ] if isinstance(payload.get("normalization_errors"), list) else []
    if message not in errors:
        errors.append(message)
    payload["normalization_errors"] = errors


def _normalized_version_token(
    payload: dict[str, Any],
    key: str,
    *,
    default: int,
    label: str,
) -> tuple[int, bool]:
    if key not in payload:
        return default, True
    raw_value = payload.get(key)
    parsed_value: int | None = None
    if isinstance(raw_value, int) and not isinstance(raw_value, bool):
        parsed_value = raw_value
    elif isinstance(raw_value, str) and re.fullmatch(r"[0-9]+", raw_value.strip()):
        parsed_value = int(raw_value.strip())
    if parsed_value is None or parsed_value < 0:
        _record_invalid_container(
            payload,
            key,
            raw_value,
            f"{label} must be a nonnegative integer.",
        )
        return default, False
    payload[key] = parsed_value
    return parsed_value, True


def _normalized_page_ref(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("page_ref") or value.get("slug")
    return _clean_token(value).replace("\\", "/").strip("/").casefold()


def _normalize_last_end_cost(value: Any) -> dict[str, Any]:
    payload = deepcopy(value) if isinstance(value, dict) else {}
    if not payload:
        return {}
    rounds = _bounded_int(payload.get("rounds"), maximum=AVATAR_OF_MOURNING_MAX_ROUNDS)
    exhaustion_gained = _bounded_int(
        payload.get("exhaustion_gained", rounds),
        maximum=AVATAR_OF_MOURNING_MAX_ROUNDS,
    )
    before = _bounded_int(payload.get("exhaustion_level_before"), maximum=6)
    after = _bounded_int(
        payload.get("exhaustion_level_after", min(6, before + exhaustion_gained)),
        maximum=6,
    )
    applied = _bounded_int(
        payload.get("exhaustion_applied", max(0, after - before)),
        maximum=6,
    )
    payload.update(
        {
            "rounds": rounds,
            "exhaustion_gained": exhaustion_gained,
            "exhaustion_level_before": before,
            "exhaustion_level_after": after,
            "exhaustion_applied": applied,
            "radiant_damage_dice": _clean_token(payload.get("radiant_damage_dice"))
            or f"{rounds * 5}d12",
            "reason": _clean_token(payload.get("reason")) or "ended",
            "resolution_id": _clean_token(payload.get("resolution_id")),
        }
    )
    if payload.get("radiant_damage_applied") is not None:
        payload["radiant_damage_applied"] = max(
            0, _coerce_int(payload.get("radiant_damage_applied"))
        )
    return payload


def normalize_avatar_of_mourning_state(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        payload = deepcopy(value)
    else:
        payload = {}
        _record_invalid_container(
            payload,
            "state",
            value,
            "Avatar of Mourning state must be an object.",
        )
    raw_schema_version, schema_version_valid = _normalized_version_token(
        payload,
        "schema_version",
        default=0,
        label="schema_version",
    )
    if raw_schema_version > DIVINE_AVATAR_FORMS_SCHEMA_VERSION:
        return payload
    raw_form_version, form_version_valid = _normalized_version_token(
        payload,
        "form_version",
        default=AVATAR_OF_MOURNING_FORM_VERSION,
        label="form_version",
    )
    if raw_form_version > AVATAR_OF_MOURNING_FORM_VERSION:
        return payload
    processed_turn_ids: list[str] = []
    seen_turn_ids: set[str] = set()
    raw_processed_turn_ids = payload.get("processed_turn_ids")
    if raw_processed_turn_ids is None:
        processed_turn_values: list[Any] = []
    elif isinstance(raw_processed_turn_ids, (list, tuple)):
        processed_turn_values = list(raw_processed_turn_ids)
    else:
        _record_invalid_container(
            payload,
            "processed_turn_ids",
            raw_processed_turn_ids,
            "processed_turn_ids must be a list.",
        )
        processed_turn_values = []
    for raw_token in processed_turn_values:
        token = _clean_token(raw_token)
        if token and token not in seen_turn_ids:
            seen_turn_ids.add(token)
            processed_turn_ids.append(token)
    legacy_token = _clean_token(payload.get("last_counted_combat_turn"))
    if legacy_token and legacy_token not in seen_turn_ids:
        processed_turn_ids.append(legacy_token)
    normalized_fields = {
            "rounds_elapsed": _bounded_int(
                payload.get("rounds_elapsed"), maximum=AVATAR_OF_MOURNING_MAX_ROUNDS
            ),
            "mourning_wave_used": bool(payload.get("mourning_wave_used")),
            "strength_of_remembrance_used": bool(
                payload.get("strength_of_remembrance_used")
            ),
            "cooldown_active": bool(payload.get("cooldown_active")),
            "activation_sequence": max(0, _coerce_int(payload.get("activation_sequence"))),
            "end_sequence": max(0, _coerce_int(payload.get("end_sequence"))),
            "processed_turn_ids": processed_turn_ids[-AVATAR_OF_MOURNING_MAX_ROUNDS :],
        }
    if schema_version_valid:
        normalized_fields["schema_version"] = DIVINE_AVATAR_FORMS_SCHEMA_VERSION
    if form_version_valid:
        normalized_fields["form_version"] = AVATAR_OF_MOURNING_FORM_VERSION
    payload.update(normalized_fields)
    payload.pop("last_counted_combat_turn", None)
    combat_revision = _coerce_int(payload.get("last_combat_revision"), default=-1)
    if combat_revision >= 0:
        payload["last_combat_revision"] = combat_revision
    else:
        payload.pop("last_combat_revision", None)
    last_end_cost = _normalize_last_end_cost(payload.get("last_end_cost"))
    if last_end_cost:
        payload["last_end_cost"] = last_end_cost
    else:
        payload.pop("last_end_cost", None)
    return payload


def _mourning_transient_effects() -> dict[str, Any]:
    return {
        "effect_id": "divine_avatar_form:avatar_of_mourning@1",
        "ability_score_overrides": {"wis": 26},
        "stat_adjustments": {"armor_class": 4},
        "spellcasting_adjustments": {"save_dc": 3, "attack_bonus": 3},
    }


DIVINE_AVATAR_FORM_ADAPTERS: dict[tuple[str, int], DivineAvatarFormAdapter] = {
    (AVATAR_OF_MOURNING_FORM_KEY, AVATAR_OF_MOURNING_FORM_VERSION): DivineAvatarFormAdapter(
        form_key=AVATAR_OF_MOURNING_FORM_KEY,
        form_version=AVATAR_OF_MOURNING_FORM_VERSION,
        label="Avatar of Mourning",
        max_rounds=AVATAR_OF_MOURNING_MAX_ROUNDS,
        cooldown_days=AVATAR_OF_MOURNING_COOLDOWN_DAYS,
        normalize_state=normalize_avatar_of_mourning_state,
        transient_effects=_mourning_transient_effects,
    )
}
DIVINE_AVATAR_FORM_SPECS = {
    adapter.form_key: {
        "label": adapter.label,
        "form_version": adapter.form_version,
        "max_rounds": adapter.max_rounds,
        "cooldown_days": adapter.cooldown_days,
    }
    for adapter in DIVINE_AVATAR_FORM_ADAPTERS.values()
}


def normalize_divine_avatar_form_key(value: Any) -> str:
    normalized = normalize_lookup(_clean_token(value))
    for form_key, _version in DIVINE_AVATAR_FORM_ADAPTERS:
        if normalized in {
            normalize_lookup(form_key),
            normalize_lookup(form_key.replace("_", " ")),
        }:
            return form_key
    return ""


def _adapter(form_key: str, form_version: int = 1) -> DivineAvatarFormAdapter | None:
    return DIVINE_AVATAR_FORM_ADAPTERS.get((form_key, form_version))


def normalize_divine_avatar_forms_state(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        payload = deepcopy(value)
    else:
        payload = {}
        _record_invalid_container(
            payload,
            "state",
            value,
            "Divine Avatar Forms state must be an object.",
        )
    raw_schema_version, schema_version_valid = _normalized_version_token(
        payload,
        "schema_version",
        default=0,
        label="schema_version",
    )
    if raw_schema_version > DIVINE_AVATAR_FORMS_SCHEMA_VERSION:
        return payload
    raw_forms_value = payload.get("forms")
    if raw_forms_value is None:
        raw_forms: dict[Any, Any] = {}
    elif isinstance(raw_forms_value, dict):
        raw_forms = dict(raw_forms_value)
    else:
        _record_invalid_container(
            payload,
            "forms",
            raw_forms_value,
            "forms must be an object.",
        )
        raw_forms = {}
    forms: dict[str, Any] = {}
    for raw_key, raw_form in raw_forms.items():
        stored_key = _clean_token(raw_key)
        known_key = normalize_divine_avatar_form_key(stored_key)
        if not known_key:
            forms[stored_key] = deepcopy(raw_form)
            continue
        if isinstance(raw_form, dict):
            form_payload = deepcopy(raw_form)
        else:
            _record_invalid_container(
                payload,
                f"forms.{known_key}",
                raw_form,
                f"{known_key} state must be an object.",
            )
            form_payload = {}
        form_version, form_version_valid = _normalized_version_token(
            form_payload,
            "form_version",
            default=AVATAR_OF_MOURNING_FORM_VERSION,
            label="form_version",
        )
        adapter = _adapter(
            known_key,
            form_version if form_version_valid else AVATAR_OF_MOURNING_FORM_VERSION,
        )
        forms[known_key] = adapter.normalize_state(form_payload) if adapter else form_payload
    active_raw = _clean_token(payload.get("active_form"))
    active_form = normalize_divine_avatar_form_key(active_raw) or active_raw
    normalized_root_fields = {
        "active_form": active_form,
        "forms": forms,
    }
    if schema_version_valid:
        normalized_root_fields["schema_version"] = DIVINE_AVATAR_FORMS_SCHEMA_VERSION
    payload.update(normalized_root_fields)
    payload["transition_sequence"] = max(
        0, _coerce_int(payload.get("transition_sequence"))
    )
    raw_action_history = payload.get("action_history")
    if raw_action_history is None:
        action_history_values: list[Any] = []
    elif isinstance(raw_action_history, (list, tuple)):
        action_history_values = list(raw_action_history)
        if any(not isinstance(row, dict) for row in action_history_values):
            _record_invalid_container(
                payload,
                "action_history",
                raw_action_history,
                "action_history rows must be objects.",
            )
    else:
        _record_invalid_container(
            payload,
            "action_history",
            raw_action_history,
            "action_history must be a list.",
        )
        action_history_values = []
    payload["action_history"] = [
        deepcopy(row) for row in action_history_values if isinstance(row, dict)
    ][-DIVINE_AVATAR_ACTION_HISTORY_LIMIT:]
    if "pending_resolution" in payload:
        if isinstance(payload.get("pending_resolution"), dict):
            pending = deepcopy(payload["pending_resolution"])
            pending.update(_normalize_last_end_cost(pending))
            pending["kind"] = "avatar_form_end_cost"
            pending["status"] = _clean_token(pending.get("status")) or "pending"
            pending["form_key"] = (
                normalize_divine_avatar_form_key(pending.get("form_key"))
                or _clean_token(pending.get("form_key"))
            )
            payload["pending_resolution"] = pending
        else:
            _record_invalid_container(
                payload,
                "pending_resolution",
                payload.get("pending_resolution"),
                "pending_resolution must be an object.",
            )
    if "last_resolution" in payload:
        if isinstance(payload.get("last_resolution"), dict):
            last_resolution = deepcopy(payload["last_resolution"])
            last_resolution.update(_normalize_last_end_cost(last_resolution))
            last_resolution["kind"] = "avatar_form_end_cost"
            last_resolution["status"] = (
                _clean_token(last_resolution.get("status")) or "resolved"
            )
            last_resolution["form_key"] = (
                normalize_divine_avatar_form_key(last_resolution.get("form_key"))
                or _clean_token(last_resolution.get("form_key"))
            )
            payload["last_resolution"] = last_resolution
        else:
            _record_invalid_container(
                payload,
                "last_resolution",
                payload.get("last_resolution"),
                "last_resolution must be an object.",
            )
    for lifecycle_key in ("last_transition", "undo_snapshot"):
        if lifecycle_key in payload and not isinstance(payload.get(lifecycle_key), dict):
            _record_invalid_container(
                payload,
                lifecycle_key,
                payload.get(lifecycle_key),
                f"{lifecycle_key} must be an object.",
            )
    return payload


def _feature_page_ref(feature: dict[str, Any]) -> str:
    campaign_option = dict(feature.get("campaign_option") or {})
    return _normalized_page_ref(feature.get("page_ref") or campaign_option.get("page_ref"))


def _avatar_plain_map(value, limit=64):
    return (type(value) is dict and len(value) <= limit
            and all(type(key) is str for key in value))


def _avatar_empty(value):
    return (value is None or type(value) is str and value == ""
            or type(value) in {dict, list} and len(value) == 0)


def _avatar_feature_source(feature):
    """Structural identity only; current ownership is proved separately."""
    option = feature.get("campaign_option", {})
    if not _avatar_plain_map(option):
        return None
    pages = []
    for value in (feature.get("page_ref"), option.get("page_ref")):
        if _avatar_empty(value):
            continue
        if type(value) is not str:
            return None
        pages.append(_normalized_page_ref(value))
    ref = feature.get("systems_ref")
    if _avatar_empty(ref):
        return (("page", DIVINE_AVATAR_FORMS_LEGACY_PAGE_REF) if pages
                and all(value == DIVINE_AVATAR_FORMS_LEGACY_PAGE_REF for value in pages) else None)
    if pages or not _avatar_plain_map(ref):
        return None
    for field in ("entry_key", "slug", "source_id", "entry_type", "title", "library_slug"):
        value = ref.get(field)
        if value is not None and type(value) is not str:
            return None
    key, slug = ref.get("entry_key"), ref.get("slug")
    if type(key) is str and key.strip():
        return "systems", key.strip()
    if type(slug) is str and slug.strip():
        return "systems_slug", slug.strip()
    return None


def _avatar_declaration_scalar(value):
    kind = type(value)
    return kind is type(None) or kind is bool or kind is int or kind is float or kind is str


def _potential_divine_avatar_effect(row):
    """Declaration only: never normalize the original row or execute its hooks."""
    if type(row) is not dict:
        return not (_avatar_declaration_scalar(row) or type(row) is list or type(row) is tuple)
    if any(type(key) is not str for key in row):
        return True
    for key, value in row.items():
        marker = key.strip()
        if marker in {"mechanic_key", "form_key"}:
            if type(value) is str:
                if ((marker == "mechanic_key" and value == DIVINE_AVATAR_MECHANIC_KEY)
                        or (marker == "form_key" and value == AVATAR_OF_MOURNING_FORM_KEY)):
                    return True
            elif not _avatar_declaration_scalar(value):
                return True
    # Every accepted generic Avatar grant has this normalized kind. Preserve
    # the actual truthy selector precedence; copied kind keys are not selectors.
    for key in ("kind", "effect_kind", "effectKind", "type"):
        value = row.get(key)
        if not _avatar_declaration_scalar(value):
            return True
        if value:
            return (type(value) is str
                    and _normalize_mechanic_effect_kind(value) == DIVINE_AVATAR_FORM_GRANT_KIND)
    return False


def _declares_divine_avatar_feature(feature):
    """Conservative family fence; original strict positive frames stay exact."""
    if type(feature) is not dict:
        return not (_avatar_declaration_scalar(feature) or type(feature) is list or type(feature) is tuple)
    if any(type(key) is not str for key in feature):
        return True
    option = feature.get("campaign_option")
    if type(option) is dict:
        if any(type(key) is not str for key in option):
            return True
    elif (_avatar_declaration_scalar(option) and not option
            or (type(option) is list or type(option) is tuple) and len(option) == 0):
        option = {}
    else:
        # Generic dict(option) may accept convertible carriers. Do not invoke
        # custom iteration/conversion to make an opaque selection favorable.
        return True
    for ref in (feature.get("page_ref"), option.get("page_ref")):
        if type(ref) is dict:
            if any(type(key) is not str for key in ref):
                return True
            values = (ref.get("page_ref"), ref.get("slug"), ref.get("page_slug"))
        else:
            values = (ref,)
        for value in values:
            if type(value) is str:
                if _normalized_page_ref(value).removesuffix(".md") == DIVINE_AVATAR_FORMS_LEGACY_PAGE_REF:
                    return True
            elif not _avatar_declaration_scalar(value):
                return True
    for value in (feature.get("mechanic_effects"), option.get("mechanic_effects")):
        if type(value) is dict:
            if _potential_divine_avatar_effect(value):
                return True
        elif type(value) is list:
            if any(_potential_divine_avatar_effect(row) for row in value):
                return True
        elif not _avatar_declaration_scalar(value) and type(value) is not tuple:
            return True
    return False


def registered_divine_avatar_feature(feature) -> bool:
    """Recognize a closed versioned footprint, never ownership or activation."""
    if not _avatar_plain_map(feature) or type(feature.get("id")) is not str or not feature["id"]:
        return False
    option = feature.get("campaign_option", {})
    if not _avatar_plain_map(option):
        return False
    if "kind" in option and (type(option["kind"]) is not str or option["kind"] != "feature"):
        return False
    if "mechanics_suppressed" in feature and type(feature["mechanics_suppressed"]) is not bool:
        return False
    if _avatar_feature_source(feature) is None:
        return False
    allowed_feature = {"id", "name", "category", "source", "description_markdown", "page_ref",
        "tracker_ref", "class_row_id", "activation_type", "authority_status", "authority_note",
        "mechanics_suppressed", "campaign_option", "mechanic_effects", "systems_ref"}
    allowed_option = {"id", "name", "title", "source", "page_ref", "kind", "option_kind",
        "description_markdown", "label", "mechanic_effects", "summary", "display_name",
        "feature_name", "activation_type", "proficiencies", "overlay_support"}
    if "proficiencies" in option:
        proficiencies = option["proficiencies"]
        if (not _avatar_plain_map(proficiencies, 5)
                or set(proficiencies) - {"armor", "weapons", "tools", "languages", "skills"}
                or any(type(value) is not list or value for value in proficiencies.values())):
            return False
    if "overlay_support" in option and (type(option["overlay_support"]) is not str or option["overlay_support"] != "modeled"):
        return False
    if (any(not _avatar_empty(value) for key, value in feature.items() if key not in allowed_feature)
            or any(not _avatar_empty(value) for key, value in option.items() if key not in allowed_option)):
        return False
    containers = [value for value in (feature.get("mechanic_effects"), option.get("mechanic_effects"))
                  if not _avatar_empty(value)]
    if not containers:
        return False
    expected = {"kind": DIVINE_AVATAR_FORM_GRANT_KIND, "mechanic_key": DIVINE_AVATAR_MECHANIC_KEY,
        "mechanic_version": DIVINE_AVATAR_MECHANIC_VERSION, "form_key": AVATAR_OF_MOURNING_FORM_KEY,
        "form_version": AVATAR_OF_MOURNING_FORM_VERSION}
    for effects in containers:
        if type(effects) is dict:
            effect = effects
        elif type(effects) is list and len(effects) == 1:
            effect = effects[0]
        else:
            return False
        if not _avatar_plain_map(effect, 6):
            return False
        if set(effect) - (set(expected) | {"source"}):
            return False
        if any(type(effect.get(key)) is not type(value) or effect[key] != value for key, value in expected.items()):
            return False
        if "source" in effect and (type(effect["source"]) is not str or effect["source"] != "mechanic_effects"):
            return False
    return True


def _divine_avatar_feature_effect_eligible(feature):
    """Benefit eligibility is separate from the registered dependency footprint."""
    if feature.get("mechanics_suppressed") is True:
        return False
    raw_status = feature.get("authority_status")
    if (raw_status is not None and type(raw_status) is not str
            or type(raw_status) is str and raw_status in {
                "UNKNOWN", "CONFLICT", "NEEDS REPAIR", "NEEDS ATTENTION"}):
        return False
    return True


def _current_divine_avatar_feature_frame(feature, source_authority):
    """Structural current owner/payload proof; not positive effect eligibility."""
    from .character_source_authority import SourceAuthority, AuthorityGrant
    if (type(source_authority) is not SourceAuthority
            or not registered_divine_avatar_feature(feature)
            or source_authority.status_for("feature", feature["id"]) != "VERIFIED"):
        return None
    identity = _avatar_feature_source(feature)
    matching = []
    if type(source_authority.grants) is not tuple:
        return None
    for grant in source_authority.grants:
        if type(grant) is not AuthorityGrant:
            return None
        if grant.kind == "feature" and grant.instance_id == feature["id"]:
            if (grant.source_kind, grant.source_key) != identity:
                return None
            matching.append(grant)
    if not matching:
        return None
    payload = source_authority.approved_payload("feature", feature["id"])
    current = {"id": feature["id"], **payload}
    if identity[0] == "page":
        current["page_ref"] = DIVINE_AVATAR_FORMS_LEGACY_PAGE_REF
    else:
        current["systems_ref"] = feature["systems_ref"]
    if not registered_divine_avatar_feature(current):
        return None
    # Return the typed grant and original identity only, without private prose.
    result = {"id": feature["id"]}
    if identity[0] == "page":
        result["page_ref"] = DIVINE_AVATAR_FORMS_LEGACY_PAGE_REF
    else:
        result["systems_ref"] = deepcopy(feature["systems_ref"])
    if not _avatar_empty(current.get("mechanic_effects")):
        result["mechanic_effects"] = deepcopy(current["mechanic_effects"])
    option = current.get("campaign_option", {})
    if not _avatar_empty(option.get("mechanic_effects")):
        result["campaign_option"] = {"kind": "feature",
            "mechanic_effects": deepcopy(option["mechanic_effects"])}
    return result


def divine_avatar_activation_kind(state) -> str:
    """Classify raw current state; malformed presence never becomes absence."""
    if not _avatar_plain_map(state, 256):
        return "unknown"
    if "feature_states" not in state:
        return "inactive"  # Existing absent-feature-state schema default.
    features = state["feature_states"]
    if not _avatar_plain_map(features, 128):
        return "unknown"
    if DIVINE_AVATAR_FORMS_STATE_KEY not in features:
        return "inactive"
    root = features[DIVINE_AVATAR_FORMS_STATE_KEY]
    if not _avatar_plain_map(root):
        return "unknown"
    if any(not _avatar_empty(value) for key, value in root.items() if key not in {
            "schema_version", "active_form", "forms", "transition_sequence", "action_history",
            "pending_resolution", "last_resolution", "last_transition", "undo_snapshot",
            "normalization_errors", "invalid_containers"}):
        return "unknown"
    if "transition_sequence" in root and (type(root["transition_sequence"]) is not int
            or root["transition_sequence"] < 0):
        return "unknown"
    version = root.get("schema_version", 0)
    if type(version) is not int or version not in {0, DIVINE_AVATAR_FORMS_SCHEMA_VERSION}:
        return "unknown"
    if not _avatar_empty(root.get("normalization_errors")) or not _avatar_empty(root.get("invalid_containers")):
        return "unknown"
    forms = root.get("forms", {})
    if not _avatar_plain_map(forms, len(DIVINE_AVATAR_FORM_ADAPTERS)):
        return "unknown"
    for key, payload in forms.items():
        if key != AVATAR_OF_MOURNING_FORM_KEY or not _avatar_plain_map(payload):
            return "unknown"
        if any(not _avatar_empty(value) for field, value in payload.items() if field not in {
                "schema_version", "form_version", "rounds_elapsed", "activation_sequence",
                "end_sequence", "last_combat_revision", "cooldown_active", "mourning_wave_used",
                "strength_of_remembrance_used", "last_end_cost", "processed_turn_ids",
                "last_counted_combat_turn", "normalization_errors", "invalid_containers"}):
            return "unknown"
        schema, form_version = payload.get("schema_version", 0), payload.get("form_version", 1)
        if (type(schema) is not int or schema not in {0, 1}
                or type(form_version) is not int or form_version != AVATAR_OF_MOURNING_FORM_VERSION
                or not _avatar_empty(payload.get("normalization_errors"))
                or not _avatar_empty(payload.get("invalid_containers"))):
            return "unknown"
        for field in ("rounds_elapsed", "activation_sequence", "end_sequence", "last_combat_revision"):
            if field in payload and (type(payload[field]) is not int or payload[field] < 0):
                return "unknown"
        for field in ("cooldown_active", "mourning_wave_used", "strength_of_remembrance_used"):
            if field in payload and type(payload[field]) is not bool:
                return "unknown"
        for field in ("last_end_cost",):
            if field in payload and not _avatar_plain_map(payload[field]):
                return "unknown"
        if "last_counted_combat_turn" in payload and type(payload["last_counted_combat_turn"]) is not str:
            return "unknown"
        if "processed_turn_ids" in payload and (type(payload["processed_turn_ids"]) is not list
                or any(type(token) is not str for token in payload["processed_turn_ids"])):
            return "unknown"
    for field in ("pending_resolution", "last_resolution", "last_transition", "undo_snapshot"):
        if field in root and not _avatar_plain_map(root[field]):
            return "unknown"
    end_costs = [payload["last_end_cost"] for payload in forms.values() if "last_end_cost" in payload]
    end_costs.extend(root[field] for field in ("pending_resolution", "last_resolution") if field in root)
    for cost in end_costs:
        for field in ("rounds", "exhaustion_gained", "exhaustion_level_before", "exhaustion_level_after",
                      "exhaustion_applied", "radiant_damage_applied"):
            if field in cost and (type(cost[field]) is not int or cost[field] < 0):
                return "unknown"
        for field in ("kind", "status", "form_key", "reason", "resolution_id", "radiant_damage_dice"):
            if field in cost and type(cost[field]) is not str:
                return "unknown"
    if "action_history" in root and (type(root["action_history"]) is not list
            or any(not _avatar_plain_map(row) for row in root["action_history"])):
        return "unknown"
    active = root.get("active_form", "")
    if type(active) is not str or active not in {"", AVATAR_OF_MOURNING_FORM_KEY}:
        return "unknown"
    # Validate lifecycle facts even when the active-form selector is empty.
    # Compatibility normalization must not erase malformed present containers.
    if divine_avatar_state_invariant_errors(state):
        return "unknown"
    if not active:
        return "inactive"
    if active not in forms:
        return "unknown"
    vitals = state.get("vitals")
    exhaustion = state.get("exhaustion_level", 0)
    if (not _avatar_plain_map(vitals) or type(vitals.get("current_hp")) is not int
            or vitals["current_hp"] <= 0 or type(exhaustion) is not int or not 0 <= exhaustion < 6):
        return "unknown"
    return "active"


def qualified_divine_avatar_numeric_effects(definition, state, source_authority):
    """Only current source authority admits the adapter; registration grants nothing."""
    if (not supports_divine_avatar_forms(getattr(definition, "system", None))
            or source_authority is None or divine_avatar_activation_kind(state) != "active"):
        return {}
    candidates = [row for row in definition.features if registered_divine_avatar_feature(row)]
    if len(candidates) != 1:
        return {}
    row = candidates[0]
    if (not _divine_avatar_feature_effect_eligible(row)
            or _current_divine_avatar_feature_frame(row, source_authority) is None):
        return {}
    return deepcopy(_adapter(AVATAR_OF_MOURNING_FORM_KEY, AVATAR_OF_MOURNING_FORM_VERSION).transient_effects())


def _legacy_avatar_selection_rows(definition):
    rows = []
    for row in definition.features:
        if not _avatar_plain_map(row):
            continue
        option = row.get("campaign_option", {})
        if not _avatar_plain_map(option):
            continue
        refs = [value for value in (row.get("page_ref"), option.get("page_ref")) if not _avatar_empty(value)]
        if any(type(value) is str and _normalized_page_ref(value) == DIVINE_AVATAR_FORMS_LEGACY_PAGE_REF for value in refs):
            rows.append(row)
    return rows


def _qualified_legacy_divine_avatar_numeric_effects(definition, state, page_records):
    """Use supplied current eligible pages; an embedded legacy grant is no proof."""
    from .character_source_authority import _eligible_page_records, _current_payload

    if (not supports_divine_avatar_forms(getattr(definition, "system", None))
            or divine_avatar_activation_kind(state) != "active"):
        return {}
    rows = _legacy_avatar_selection_rows(definition)
    if len(rows) != 1:
        return {}
    row = rows[0]
    identity = row.get("id")
    if (type(identity) is not str or not identity
            or sum(type(other) is dict and other.get("id") == identity for other in definition.features) != 1
            or row.get("mechanics_suppressed") is True
            or row.get("authority_status") in {"UNKNOWN", "CONFLICT", "NEEDS REPAIR", "NEEDS ATTENTION"}
            or not _avatar_empty(row.get("systems_ref"))):
        return {}
    option = row.get("campaign_option", {})
    refs = [value for value in (row.get("page_ref"), option.get("page_ref")) if not _avatar_empty(value)]
    if any(type(value) is not str or _normalized_page_ref(value) != DIVINE_AVATAR_FORMS_LEGACY_PAGE_REF for value in refs):
        return {}
    if (any(not _avatar_empty(value) for value in (row.get("mechanic_effects"), option.get("mechanic_effects")))
            and not registered_divine_avatar_feature(row)):
        return {}
    current, reason = _current_payload(campaign_slug=definition.campaign_slug, kind="feature",
        source_kind="page", source_key=DIVINE_AVATAR_FORMS_LEGACY_PAGE_REF,
        systems_service=None, pages=_eligible_page_records(page_records))
    if current is None or reason:
        return {}
    frame = {"id": identity, "page_ref": DIVINE_AVATAR_FORMS_LEGACY_PAGE_REF, **current}
    if not registered_divine_avatar_feature(frame):
        return {}
    selection = deepcopy(row)
    selection["campaign_option"] = {**option,
        "mechanic_effects": deepcopy(frame["campaign_option"]["mechanic_effects"])}
    if not registered_divine_avatar_feature(selection):
        return {}
    return deepcopy(_adapter(AVATAR_OF_MOURNING_FORM_KEY, AVATAR_OF_MOURNING_FORM_VERSION).transient_effects())


def divine_avatar_form_grants(definition: Any) -> list[dict[str, Any]]:
    if not supports_divine_avatar_forms(getattr(definition, "system", None)):
        return []
    grants: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for feature in list(getattr(definition, "features", []) or []):
        if not isinstance(feature, dict):
            continue
        if (feature.get("mechanics_suppressed") is True
                or feature.get("authority_status") in {"UNKNOWN", "CONFLICT", "NEEDS REPAIR", "NEEDS ATTENTION"}):
            continue
        campaign_option = dict(feature.get("campaign_option") or {})
        raw_effects = campaign_option.get("mechanic_effects", feature.get("mechanic_effects"))
        effects = normalize_campaign_mechanic_effects(raw_effects)
        explicit_grants = [
            effect for effect in effects if effect.get("kind") == DIVINE_AVATAR_FORM_GRANT_KIND
        ]
        for effect in explicit_grants:
            if normalize_lookup(effect.get("mechanic_key")) != normalize_lookup(
                DIVINE_AVATAR_MECHANIC_KEY
            ):
                continue
            if _coerce_int(effect.get("mechanic_version"), default=-1) != DIVINE_AVATAR_MECHANIC_VERSION:
                continue
            form_key = normalize_divine_avatar_form_key(effect.get("form_key"))
            form_version = _coerce_int(effect.get("form_version"), default=-1)
            if not form_key or _adapter(form_key, form_version) is None:
                continue
            marker = (form_key, form_version)
            if marker not in seen:
                seen.add(marker)
                grants.append(
                    {
                        "mechanic_key": DIVINE_AVATAR_MECHANIC_KEY,
                        "mechanic_version": DIVINE_AVATAR_MECHANIC_VERSION,
                        "form_key": form_key,
                        "form_version": form_version,
                        "source": "mechanic_effects",
                    }
                )
        if not explicit_grants and _feature_page_ref(feature) == DIVINE_AVATAR_FORMS_LEGACY_PAGE_REF:
            marker = (AVATAR_OF_MOURNING_FORM_KEY, AVATAR_OF_MOURNING_FORM_VERSION)
            if marker not in seen:
                seen.add(marker)
                grants.append(
                    {
                        "mechanic_key": DIVINE_AVATAR_MECHANIC_KEY,
                        "mechanic_version": DIVINE_AVATAR_MECHANIC_VERSION,
                        "form_key": marker[0],
                        "form_version": marker[1],
                        "source": "legacy_page_ref",
                    }
                )
    return grants


def character_has_divine_avatar_forms(definition: Any) -> bool:
    return bool(divine_avatar_form_grants(definition))


def divine_avatar_forms_state_from(state: dict[str, Any]) -> dict[str, Any]:
    raw_feature_states = (state or {}).get("feature_states")
    feature_states = dict(raw_feature_states) if isinstance(raw_feature_states, dict) else {}
    raw_forms_state = (
        feature_states[DIVINE_AVATAR_FORMS_STATE_KEY]
        if DIVINE_AVATAR_FORMS_STATE_KEY in feature_states
        else {}
    )
    return normalize_divine_avatar_forms_state(raw_forms_state)


def divine_avatar_form_state_from(state: dict[str, Any], form_key: str) -> dict[str, Any]:
    normalized_key = normalize_divine_avatar_form_key(form_key)
    if not normalized_key:
        raise ValueError("Choose a supported Divine Avatar Form.")
    forms_state = divine_avatar_forms_state_from(state)
    raw_forms = forms_state.get("forms")
    forms = dict(raw_forms) if isinstance(raw_forms, dict) else {}
    raw_payload = forms.get(normalized_key)
    payload = deepcopy(raw_payload) if isinstance(raw_payload, dict) else {}
    form_version = _coerce_int(payload.get("form_version"), default=1)
    adapter = _adapter(normalized_key, form_version)
    if adapter:
        payload = adapter.normalize_state(payload)
    payload["active"] = bool(forms_state.get("active_form") == normalized_key)
    return payload


def _write_forms_state(state: dict[str, Any], forms_state: dict[str, Any]) -> None:
    feature_states = dict(state.get("feature_states") or {})
    feature_states[DIVINE_AVATAR_FORMS_STATE_KEY] = normalize_divine_avatar_forms_state(forms_state)
    state["feature_states"] = feature_states


def set_divine_avatar_form_state(
    state: dict[str, Any],
    form_key: str,
    payload: dict[str, Any],
    *,
    active: bool | None = None,
) -> None:
    normalized_key = normalize_divine_avatar_form_key(form_key)
    adapter = _adapter(normalized_key)
    if adapter is None:
        raise ValueError("Choose a supported Divine Avatar Form.")
    forms_state = divine_avatar_forms_state_from(state)
    if _coerce_int(forms_state.get("schema_version"), default=1) > DIVINE_AVATAR_FORMS_SCHEMA_VERSION:
        raise ValueError("This Divine Avatar Forms state uses a newer unsupported schema.")
    forms = dict(forms_state.get("forms") or {})
    clean_payload = dict(payload or {})
    clean_payload.pop("active", None)
    forms[normalized_key] = adapter.normalize_state(clean_payload)
    forms_state["forms"] = forms
    if active is True:
        forms_state["active_form"] = normalized_key
    elif active is False and forms_state.get("active_form") == normalized_key:
        forms_state["active_form"] = ""
    _write_forms_state(state, forms_state)


def divine_avatar_state_invariant_errors(
    state: dict[str, Any],
    *,
    allow_active_end_conditions: bool = False,
) -> list[str]:
    forms_state = divine_avatar_forms_state_from(state)
    if _coerce_int(forms_state.get("schema_version"), default=1) > DIVINE_AVATAR_FORMS_SCHEMA_VERSION:
        return ["Divine Avatar Forms state uses a newer unsupported schema."]
    normalization_errors = [
        _clean_token(error)
        for error in list(forms_state.get("normalization_errors") or [])
        if _clean_token(error)
    ] if isinstance(forms_state.get("normalization_errors"), list) else []
    if normalization_errors:
        return [f"Malformed Divine Avatar Forms state: {normalization_errors[0]}"]
    forms = dict(forms_state.get("forms") or {})
    for raw_form_key, raw_payload in forms.items():
        form_key = normalize_divine_avatar_form_key(raw_form_key)
        if not form_key or not isinstance(raw_payload, dict):
            continue
        form_schema = _coerce_int(raw_payload.get("schema_version"), default=1)
        form_version = _coerce_int(raw_payload.get("form_version"), default=1)
        form_normalization_errors = (
            [
                _clean_token(error)
                for error in list(raw_payload.get("normalization_errors") or [])
                if _clean_token(error)
            ]
            if isinstance(raw_payload.get("normalization_errors"), list)
            else []
        )
        if form_normalization_errors:
            return [
                f"Malformed Divine Avatar Form state: {form_normalization_errors[0]}"
            ]
        if form_schema > DIVINE_AVATAR_FORMS_SCHEMA_VERSION or _adapter(form_key, form_version) is None:
            return ["Divine Avatar Form state uses a newer unsupported version."]
    pending = dict(forms_state.get("pending_resolution") or {})
    if pending:
        pending_form = normalize_divine_avatar_form_key(pending.get("form_key"))
        if (
            pending.get("status") != "pending"
            or not pending_form
            or pending_form not in forms
            or not _clean_token(pending.get("resolution_id"))
        ):
            return ["The pending Divine Avatar Form resolution is invalid."]
    last_resolution = dict(forms_state.get("last_resolution") or {})
    if last_resolution:
        resolved_form = normalize_divine_avatar_form_key(last_resolution.get("form_key"))
        if (
            last_resolution.get("status") != "resolved"
            or not resolved_form
            or resolved_form not in forms
            or not _clean_token(last_resolution.get("resolution_id"))
            or last_resolution.get("radiant_damage_applied") is None
        ):
            return ["The recorded Divine Avatar Form resolution is invalid."]
    active_form = _clean_token(forms_state.get("active_form"))
    if not active_form:
        return []
    if pending:
        return ["A Divine Avatar Form cannot be active while an end cost is pending."]
    payload = dict(forms.get(active_form) or {})
    if not payload:
        return ["The active Divine Avatar Form has no state payload."]
    form_version = _coerce_int(payload.get("form_version"), default=1)
    if _adapter(active_form, form_version) is None:
        return ["The active Divine Avatar Form version is unsupported."]
    if bool(payload.get("cooldown_active")):
        return ["A Divine Avatar Form cannot be active while its cooldown is active."]
    if _coerce_int(payload.get("rounds_elapsed")) >= AVATAR_OF_MOURNING_MAX_ROUNDS:
        return ["A Divine Avatar Form cannot remain active after its maximum duration."]
    if (
        not allow_active_end_conditions
        and _coerce_int(dict((state or {}).get("vitals") or {}).get("current_hp")) <= 0
    ):
        return ["A Divine Avatar Form cannot remain active while the character is unconscious."]
    if (
        not allow_active_end_conditions
        and _coerce_int((state or {}).get("exhaustion_level")) >= 6
    ):
        return ["A Divine Avatar Form cannot remain active at fatal exhaustion."]
    return []


def active_divine_avatar_transient_effects(
    definition: Any,
    state: dict[str, Any],
    *, source_authority: Any | None = None,
    page_records: list[Any] | None = None,
) -> dict[str, Any]:
    """Admit the current adapter only with the exact raw authority context."""
    if not supports_divine_avatar_forms(getattr(definition, "system", None)):
        return {}
    if source_authority is None:
        effects = _qualified_legacy_divine_avatar_numeric_effects(definition, state, page_records)
        if (not effects and divine_avatar_activation_kind(state) != "inactive"
                and _legacy_avatar_selection_rows(definition)):
            raise ValueError("Current Divine Avatar mechanics are unavailable; manager source review is required.")
        return effects
    return source_authority._numeric_context(definition, state, formula_scope="current")["effects"]


def project_active_divine_avatar_form(definition: Any, state: dict[str, Any]) -> Any:
    """Compatibility shim; projection is performed by the shared derivation pipeline."""
    return definition


def divine_avatar_action_success_message(action: str) -> str:
    normalized_action = _clean_token(action).replace("-", "_").casefold()
    return DIVINE_AVATAR_ACTION_SUCCESS_MESSAGES.get(
        normalized_action,
        "Divine Avatar Form state updated.",
    )


def _capture_undo_snapshot(state: dict[str, Any], action: str, form_key: str) -> dict[str, Any]:
    prior_forms_state = divine_avatar_forms_state_from(state)
    prior_forms_state.pop("undo_snapshot", None)
    return {
        "action": action,
        "form_key": form_key,
        "forms_state": prior_forms_state,
        "exhaustion_present": "exhaustion_level" in state,
        "exhaustion_level": _bounded_int(state.get("exhaustion_level"), maximum=6),
    }


def _record_transition(
    state: dict[str, Any],
    *,
    action: str,
    form_key: str,
    undo_snapshot: dict[str, Any] | None,
    audit_details: dict[str, Any] | None = None,
) -> None:
    forms_state = divine_avatar_forms_state_from(state)
    transition_sequence = max(
        0, _coerce_int(forms_state.get("transition_sequence"))
    ) + 1
    transition_row = {
        "sequence": transition_sequence,
        "action": action,
        "form_key": form_key,
        **deepcopy(audit_details or {}),
    }
    forms_state["transition_sequence"] = transition_sequence
    forms_state["last_transition"] = deepcopy(transition_row)
    forms_state["action_history"] = [
        *[
            deepcopy(row)
            for row in list(forms_state.get("action_history") or [])
            if isinstance(row, dict)
        ],
        transition_row,
    ][-DIVINE_AVATAR_ACTION_HISTORY_LIMIT:]
    if undo_snapshot is not None:
        forms_state["undo_snapshot"] = deepcopy(undo_snapshot)
    else:
        forms_state.pop("undo_snapshot", None)
    _write_forms_state(state, forms_state)


def _apply_mourning_end(state: dict[str, Any], *, reason: str) -> None:
    form_key = AVATAR_OF_MOURNING_FORM_KEY
    avatar_state = divine_avatar_form_state_from(state, form_key)
    rounds = _bounded_int(
        avatar_state.get("rounds_elapsed"), maximum=AVATAR_OF_MOURNING_MAX_ROUNDS
    )
    before = _bounded_int(state.get("exhaustion_level"), maximum=6)
    after = min(6, before + rounds)
    avatar_state["end_sequence"] = max(0, _coerce_int(avatar_state.get("end_sequence"))) + 1
    resolution_id = (
        f"{form_key}:{max(0, _coerce_int(avatar_state.get('activation_sequence')))}:"
        f"{avatar_state['end_sequence']}"
    )
    end_cost = {
        "rounds": rounds,
        "exhaustion_gained": rounds,
        "exhaustion_level_before": before,
        "exhaustion_level_after": after,
        "exhaustion_applied": after - before,
        "radiant_damage_dice": f"{rounds * 5}d12",
        "reason": _clean_token(reason) or "ended",
        "resolution_id": resolution_id,
    }
    avatar_state.update(
        {
            "cooldown_active": True,
            "processed_turn_ids": [],
            "last_end_cost": end_cost,
        }
    )
    state["exhaustion_level"] = after
    set_divine_avatar_form_state(state, form_key, avatar_state, active=False)
    forms_state = divine_avatar_forms_state_from(state)
    forms_state["pending_resolution"] = {
        **end_cost,
        "kind": "avatar_form_end_cost",
        "form_key": form_key,
        "status": "pending",
    }
    _write_forms_state(state, forms_state)


def end_divine_avatar_form_automatically(
    definition: Any,
    state: dict[str, Any],
    form_key: str,
    *,
    reason: str,
) -> dict[str, Any]:
    next_state = deepcopy(state or {})
    normalized_form_key = normalize_divine_avatar_form_key(form_key)
    if normalized_form_key != AVATAR_OF_MOURNING_FORM_KEY:
        raise ValueError("Choose a supported Divine Avatar Form.")
    grants = {
        (grant["form_key"], grant["form_version"])
        for grant in divine_avatar_form_grants(definition)
    }
    if (normalized_form_key, AVATAR_OF_MOURNING_FORM_VERSION) not in grants:
        raise ValueError("Divine Avatar Forms are not recorded on this character sheet.")
    errors = divine_avatar_state_invariant_errors(
        next_state,
        allow_active_end_conditions=True,
    )
    if errors:
        raise ValueError(errors[0])
    if not divine_avatar_form_state_from(next_state, normalized_form_key).get("active"):
        return next_state
    _apply_mourning_end(next_state, reason=reason)
    post_transition_errors = divine_avatar_state_invariant_errors(next_state)
    if post_transition_errors:
        raise ValueError(post_transition_errors[0])
    _record_transition(
        next_state,
        action="end",
        form_key=normalized_form_key,
        undo_snapshot=None,
    )
    return next_state


def _require_confirmation(action: str, confirmed: bool) -> None:
    if action != "advance_turn" and not confirmed:
        raise ValueError("Confirm this Divine Avatar Form action before applying it.")


def _require_matching_resolution(
    forms_state: dict[str, Any],
    resolution_id: str,
) -> dict[str, Any]:
    pending = dict(forms_state.get("pending_resolution") or {})
    expected_id = _clean_token(pending.get("resolution_id"))
    supplied_id = _clean_token(resolution_id)
    if not expected_id or supplied_id != expected_id:
        raise ValueError("Choose the current pending Divine Avatar Form resolution.")
    return pending


def transition_divine_avatar_form(
    definition: Any,
    state: dict[str, Any],
    form_key: str,
    action: str,
    *,
    combat_turn_token: str = "",
    combat_revision: int | None = None,
    confirmed: bool = False,
    resolution_id: str = "",
    radiant_damage_applied: Any | None = None,
    correction: dict[str, Any] | None = None,
) -> DivineAvatarTransition:
    if not supports_divine_avatar_forms(getattr(definition, "system", None)):
        raise ValueError("Divine Avatar Forms are only supported on D&D 5E character sheets.")
    normalized_form_key = normalize_divine_avatar_form_key(form_key)
    grants = {
        (grant["form_key"], grant["form_version"])
        for grant in divine_avatar_form_grants(definition)
    }
    if (normalized_form_key, AVATAR_OF_MOURNING_FORM_VERSION) not in grants:
        raise ValueError("Divine Avatar Forms are not recorded on this character sheet.")
    normalized_action = _clean_token(action).replace("-", "_").casefold()
    if normalized_action not in DIVINE_AVATAR_ACTION_SUCCESS_MESSAGES:
        raise ValueError("Choose a supported Avatar of Mourning action.")
    _require_confirmation(normalized_action, confirmed)
    errors = divine_avatar_state_invariant_errors(state)
    if errors:
        raise ValueError(errors[0])

    next_state = deepcopy(state or {})
    avatar_state = divine_avatar_form_state_from(next_state, normalized_form_key)
    forms_state = divine_avatar_forms_state_from(next_state)
    if (
        _coerce_int(avatar_state.get("schema_version"), default=1)
        > DIVINE_AVATAR_FORMS_SCHEMA_VERSION
        or _adapter(
            normalized_form_key,
            _coerce_int(avatar_state.get("form_version"), default=1),
        )
        is None
    ):
        raise ValueError("This Divine Avatar Form state uses a newer unsupported version.")
    undo_snapshot = (
        _capture_undo_snapshot(next_state, normalized_action, normalized_form_key)
        if normalized_action == "end"
        else None
    )
    audit_details: dict[str, Any] = {}

    if normalized_action == "activate":
        if avatar_state.get("active"):
            raise ValueError("Avatar of Mourning is already active.")
        if forms_state.get("active_form"):
            raise ValueError("End the active Divine Avatar Form before activating another one.")
        if avatar_state.get("cooldown_active"):
            raise ValueError("Avatar of Mourning cannot be activated during its 40-day cooldown.")
        if forms_state.get("pending_resolution"):
            raise ValueError("Resolve the pending Divine Avatar Form end cost first.")
        if _coerce_int(next_state.get("exhaustion_level")) >= 6:
            raise ValueError("Avatar of Mourning cannot be activated at fatal exhaustion.")
        vitals = dict(next_state.get("vitals") or {})
        current_hp = _coerce_int(vitals.get("current_hp"))
        max_hp = _coerce_int((getattr(definition, "stats", {}) or {}).get("max_hp"))
        if max_hp <= 0 or current_hp <= 0 or current_hp * 2 >= max_hp:
            raise ValueError("Current hit points must be above 0 and less than half the hit point maximum.")
        missing_hp = max(0, max_hp - current_hp)
        vitals["temp_hp"] = max(_coerce_int(vitals.get("temp_hp")), missing_hp * 3)
        next_state["vitals"] = vitals
        next_state["spell_slots"] = [
            {**dict(slot or {}), "used": 0} for slot in list(next_state.get("spell_slots") or [])
        ]
        avatar_state.update(
            {
                "rounds_elapsed": 0,
                "mourning_wave_used": False,
                "strength_of_remembrance_used": False,
                "cooldown_active": False,
                "processed_turn_ids": [],
                "activation_sequence": max(
                    0, _coerce_int(avatar_state.get("activation_sequence"))
                )
                + 1,
            }
        )
        set_divine_avatar_form_state(next_state, normalized_form_key, avatar_state, active=True)
    elif normalized_action in {"mourning_wave", "strength_of_remembrance"}:
        if not avatar_state.get("active"):
            raise ValueError("Activate Avatar of Mourning before using that power.")
        used_key = f"{normalized_action}_used"
        if avatar_state.get(used_key):
            raise ValueError("That Avatar of Mourning power has already been used.")
        avatar_state[used_key] = True
        set_divine_avatar_form_state(next_state, normalized_form_key, avatar_state)
    elif normalized_action in {"correct_mourning_wave", "correct_strength_of_remembrance"}:
        used_key = normalized_action.removeprefix("correct_") + "_used"
        if not avatar_state.get(used_key):
            raise ValueError("That Avatar of Mourning power is not marked used.")
        avatar_state[used_key] = False
        set_divine_avatar_form_state(next_state, normalized_form_key, avatar_state)
    elif normalized_action == "end":
        if not avatar_state.get("active"):
            raise ValueError("Avatar of Mourning is not active.")
        _apply_mourning_end(next_state, reason="dismissed")
        pending_after_end = dict(
            divine_avatar_forms_state_from(next_state).get("pending_resolution") or {}
        )
        if undo_snapshot is not None:
            undo_snapshot["resolution_id"] = _clean_token(
                pending_after_end.get("resolution_id")
            )
            undo_snapshot["exhaustion_level_after"] = _bounded_int(
                pending_after_end.get("exhaustion_level_after"), maximum=6
            )
        audit_details = {
            "resolution_id": _clean_token(pending_after_end.get("resolution_id")),
            "end_cost": _normalize_last_end_cost(pending_after_end),
        }
    elif normalized_action == "cooldown_complete":
        if avatar_state.get("active"):
            raise ValueError("End Avatar of Mourning before completing its cooldown.")
        if not avatar_state.get("cooldown_active"):
            raise ValueError("Avatar of Mourning is not currently recharging.")
        if forms_state.get("pending_resolution"):
            raise ValueError("Resolve the pending Divine Avatar Form end cost first.")
        avatar_state["cooldown_active"] = False
        set_divine_avatar_form_state(next_state, normalized_form_key, avatar_state)
    elif normalized_action == "correct_cooldown_complete":
        last_transition = dict(forms_state.get("last_transition") or {})
        if avatar_state.get("cooldown_active") or last_transition.get("action") != "cooldown_complete":
            raise ValueError("There is no cooldown completion to correct.")
        avatar_state["cooldown_active"] = True
        set_divine_avatar_form_state(next_state, normalized_form_key, avatar_state)
    elif normalized_action == "advance_turn":
        if not avatar_state.get("active"):
            return DivineAvatarTransition(deepcopy(state), normalized_action, normalized_form_key, False)
        turn_token = _clean_token(combat_turn_token)
        processed_turn_ids = list(avatar_state.get("processed_turn_ids") or [])
        if combat_revision is None and not turn_token:
            raise ValueError("Combat turn tracking requires a turn token or combat revision.")
        if combat_revision is not None:
            next_revision = _coerce_int(combat_revision, default=-1)
            if next_revision < 0:
                raise ValueError("Combat revision must be a nonnegative integer.")
            prior_revision = _coerce_int(avatar_state.get("last_combat_revision"), default=-1)
            if next_revision <= prior_revision:
                return DivineAvatarTransition(deepcopy(state), normalized_action, normalized_form_key, False)
            avatar_state["last_combat_revision"] = next_revision
        if turn_token and turn_token in processed_turn_ids:
            if combat_revision is None:
                return DivineAvatarTransition(
                    deepcopy(state), normalized_action, normalized_form_key, False
                )
            set_divine_avatar_form_state(
                next_state, normalized_form_key, avatar_state, active=True
            )
            audit_details = {
                "combat_revision": combat_revision,
                "combat_turn_token": turn_token,
                "counted": False,
            }
            _record_transition(
                next_state,
                action=normalized_action,
                form_key=normalized_form_key,
                undo_snapshot=None,
                audit_details=audit_details,
            )
            return DivineAvatarTransition(
                next_state, normalized_action, normalized_form_key, True
            )
        if turn_token:
            avatar_state["processed_turn_ids"] = [
                *processed_turn_ids,
                turn_token,
            ][-AVATAR_OF_MOURNING_MAX_ROUNDS :]
        audit_details = {
            "combat_revision": combat_revision,
            "combat_turn_token": turn_token,
            "counted": True,
        }
        avatar_state["rounds_elapsed"] = min(
            AVATAR_OF_MOURNING_MAX_ROUNDS,
            _coerce_int(avatar_state.get("rounds_elapsed")) + 1,
        )
        set_divine_avatar_form_state(next_state, normalized_form_key, avatar_state, active=True)
        if avatar_state["rounds_elapsed"] >= AVATAR_OF_MOURNING_MAX_ROUNDS:
            _apply_mourning_end(next_state, reason="duration")
    elif normalized_action == "resolve_end_cost":
        pending = _require_matching_resolution(forms_state, resolution_id)
        if radiant_damage_applied is None:
            raise ValueError("Record the radiant damage applied.")
        applied_damage = _coerce_int(radiant_damage_applied, default=-1)
        if applied_damage < 0:
            raise ValueError("Radiant damage applied must be a nonnegative integer.")
        pending["radiant_damage_applied"] = applied_damage
        pending["status"] = "resolved"
        avatar_state["last_end_cost"] = {
            **dict(avatar_state.get("last_end_cost") or {}),
            "radiant_damage_applied": applied_damage,
        }
        set_divine_avatar_form_state(next_state, normalized_form_key, avatar_state)
        forms_state = divine_avatar_forms_state_from(next_state)
        forms_state["last_resolution"] = pending
        forms_state.pop("pending_resolution", None)
        _write_forms_state(next_state, forms_state)
        audit_details = {
            "resolution_id": _clean_token(pending.get("resolution_id")),
            "radiant_damage_applied": applied_damage,
        }
    elif normalized_action == "correct_end_cost":
        correction_payload = dict(correction or {})
        if not correction_payload:
            raise ValueError("Provide at least one end-cost correction.")
        pending = dict(forms_state.get("pending_resolution") or {})
        last_resolution = dict(forms_state.get("last_resolution") or {})
        if not pending and forms_state.get("active_form"):
            raise ValueError("End the active Divine Avatar Form before correcting a prior resolution.")
        target = pending or last_resolution
        if _clean_token(target.get("resolution_id")) != _clean_token(resolution_id):
            raise ValueError("Choose the matching Divine Avatar Form resolution to correct.")
        cost = _normalize_last_end_cost(avatar_state.get("last_end_cost"))
        prior_cost = deepcopy(cost)
        for key in ("rounds", "exhaustion_gained"):
            if key in correction_payload:
                cost[key] = _bounded_int(
                    correction_payload[key], maximum=AVATAR_OF_MOURNING_MAX_ROUNDS
                )
        if "radiant_damage_dice" in correction_payload:
            dice = _clean_token(correction_payload["radiant_damage_dice"])
            if not re.fullmatch(r"\d+d12", dice, flags=re.IGNORECASE):
                raise ValueError("Radiant damage dice must use Nd12 notation.")
            cost["radiant_damage_dice"] = dice.lower()
        if "reason" in correction_payload:
            reason = _clean_token(correction_payload["reason"])
            if not reason:
                raise ValueError("End-cost reason cannot be blank.")
            cost["reason"] = reason
        if "radiant_damage_applied" in correction_payload:
            if pending:
                raise ValueError("Resolve pending radiant damage before correcting its applied total.")
            applied_damage = _coerce_int(
                correction_payload["radiant_damage_applied"], default=-1
            )
            if applied_damage < 0:
                raise ValueError("Radiant damage applied must be a nonnegative integer.")
            cost["radiant_damage_applied"] = applied_damage
        old_after = _bounded_int(cost.get("exhaustion_level_after"), maximum=6)
        if _bounded_int(next_state.get("exhaustion_level"), maximum=6) != old_after:
            raise ValueError("Exhaustion changed after this end cost; correct it separately first.")
        before = _bounded_int(cost.get("exhaustion_level_before"), maximum=6)
        after = min(6, before + _bounded_int(
            cost.get("exhaustion_gained"), maximum=AVATAR_OF_MOURNING_MAX_ROUNDS
        ))
        cost["exhaustion_level_after"] = after
        cost["exhaustion_applied"] = after - before
        next_state["exhaustion_level"] = after
        avatar_state["last_end_cost"] = cost
        set_divine_avatar_form_state(next_state, normalized_form_key, avatar_state)
        forms_state = divine_avatar_forms_state_from(next_state)
        if pending:
            forms_state["pending_resolution"] = {
                **pending,
                **cost,
                "status": "pending",
                "kind": "avatar_form_end_cost",
                "form_key": normalized_form_key,
            }
        else:
            forms_state["last_resolution"] = {**last_resolution, **cost, "status": "resolved"}
        _write_forms_state(next_state, forms_state)
        audit_details = {
            "resolution_id": _clean_token(target.get("resolution_id")),
            "before": prior_cost,
            "after": deepcopy(cost),
        }
    elif normalized_action == "undo_last_action":
        snapshot = dict(forms_state.get("undo_snapshot") or {})
        if (
            not snapshot
            or snapshot.get("action") != "end"
            or snapshot.get("form_key") != normalized_form_key
        ):
            raise ValueError("There is no Divine Avatar Form action to undo.")
        pending = dict(forms_state.get("pending_resolution") or {})
        if (
            pending.get("status") != "pending"
            or pending.get("radiant_damage_applied") is not None
            or _clean_token(pending.get("resolution_id"))
            != _clean_token(snapshot.get("resolution_id"))
        ):
            raise ValueError("An ended form can only be undone before its damage is resolved.")
        if _bounded_int(next_state.get("exhaustion_level"), maximum=6) != _bounded_int(
            snapshot.get("exhaustion_level_after"), maximum=6
        ):
            raise ValueError("Exhaustion changed after this end; the form cannot be safely undone.")
        current_avatar_state = divine_avatar_form_state_from(next_state, normalized_form_key)
        restored_forms_state = dict(snapshot.get("forms_state") or {})
        restored_forms = dict(restored_forms_state.get("forms") or {})
        restored_avatar_state = dict(restored_forms.get(normalized_form_key) or {})
        restored_avatar_state["end_sequence"] = max(
            _coerce_int(restored_avatar_state.get("end_sequence")),
            _coerce_int(current_avatar_state.get("end_sequence")),
        )
        current_combat_revision = _coerce_int(
            current_avatar_state.get("last_combat_revision"), default=-1
        )
        restored_combat_revision = _coerce_int(
            restored_avatar_state.get("last_combat_revision"), default=-1
        )
        if max(current_combat_revision, restored_combat_revision) >= 0:
            restored_avatar_state["last_combat_revision"] = max(
                current_combat_revision, restored_combat_revision
            )
        restored_forms[normalized_form_key] = restored_avatar_state
        restored_forms_state["forms"] = restored_forms
        restored_forms_state["transition_sequence"] = max(
            _coerce_int(forms_state.get("transition_sequence")),
            _coerce_int(restored_forms_state.get("transition_sequence")),
        )
        restored_forms_state["action_history"] = deepcopy(
            list(forms_state.get("action_history") or [])
        )[-DIVINE_AVATAR_ACTION_HISTORY_LIMIT:]
        _write_forms_state(next_state, restored_forms_state)
        if snapshot.get("exhaustion_present"):
            next_state["exhaustion_level"] = _bounded_int(
                snapshot.get("exhaustion_level"), maximum=6
            )
        else:
            next_state.pop("exhaustion_level", None)
        audit_details = {"resolution_id": _clean_token(pending.get("resolution_id"))}

    post_transition_errors = divine_avatar_state_invariant_errors(next_state)
    if post_transition_errors:
        raise ValueError(post_transition_errors[0])
    _record_transition(
        next_state,
        action=normalized_action,
        form_key=normalized_form_key,
        undo_snapshot=undo_snapshot if normalized_action != "undo_last_action" else None,
        audit_details=audit_details,
    )
    return DivineAvatarTransition(next_state, normalized_action, normalized_form_key, True)


def present_divine_avatar_forms_state(
    definition: Any,
    state: dict[str, Any],
    *,
    external_errors: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    grants = divine_avatar_form_grants(definition)
    display_only = not grants
    feature_states = state.get("feature_states") if type(state) is dict else None
    stored_state_present = (type(feature_states) is dict
                            and DIVINE_AVATAR_FORMS_STATE_KEY in feature_states)
    if display_only and (not supports_divine_avatar_forms(getattr(definition, "system", None))
                         or not stored_state_present):
        return {"available": False}
    forms_state = divine_avatar_forms_state_from(state)
    active_form = _clean_token(forms_state.get("active_form"))
    raw_pending = forms_state.get("pending_resolution")
    pending = dict(raw_pending) if isinstance(raw_pending, dict) and raw_pending else None
    raw_last_resolution_value = forms_state.get("last_resolution")
    raw_last_resolution = (
        dict(raw_last_resolution_value)
        if isinstance(raw_last_resolution_value, dict)
        else {}
    )
    raw_stored_forms = forms_state.get("forms")
    stored_forms = dict(raw_stored_forms) if isinstance(raw_stored_forms, dict) else {}
    last_resolution_form = normalize_divine_avatar_form_key(
        raw_last_resolution.get("form_key")
    )
    last_resolution = (
        raw_last_resolution
        if raw_last_resolution.get("status") == "resolved"
        and last_resolution_form in stored_forms
        and _clean_token(raw_last_resolution.get("resolution_id"))
        and raw_last_resolution.get("radiant_damage_applied") is not None
        else None
    )
    raw_last_transition = forms_state.get("last_transition")
    last_transition = (
        dict(raw_last_transition)
        if isinstance(raw_last_transition, dict) and raw_last_transition
        else None
    )
    intrinsic_state_errors = divine_avatar_state_invariant_errors(state)
    state_errors = [
        *(["The Avatar source is unresolved. Stored tracking and obligations are shown for review only; automatic effects and all Avatar actions are unavailable."]
          if display_only else []),
        *intrinsic_state_errors,
        *[
            _clean_token(error)
            for error in list(external_errors or [])
            if _clean_token(error)
        ],
    ]
    actions_enabled = not display_only and not state_errors
    raw_undo_snapshot = forms_state.get("undo_snapshot")
    undo_snapshot = (
        dict(raw_undo_snapshot) if isinstance(raw_undo_snapshot, dict) else {}
    )
    can_undo = bool(
        actions_enabled
        and undo_snapshot.get("action") == "end"
        and pending
        and pending.get("status") == "pending"
        and pending.get("radiant_damage_applied") is None
        and _clean_token(pending.get("resolution_id"))
        == _clean_token(undo_snapshot.get("resolution_id"))
    )
    presented_forms = []
    form_keys = [grant["form_key"] for grant in grants] if grants else [AVATAR_OF_MOURNING_FORM_KEY]
    for form_key in form_keys:
        if form_key != AVATAR_OF_MOURNING_FORM_KEY:
            continue
        payload = divine_avatar_form_state_from(state, AVATAR_OF_MOURNING_FORM_KEY)
        vitals = dict((state or {}).get("vitals") or {})
        current_hp = _coerce_int(vitals.get("current_hp"))
        max_hp = _coerce_int((getattr(definition, "stats", {}) or {}).get("max_hp"))
        active = bool(payload.get("active"))
        cooldown_active = bool(payload.get("cooldown_active"))
        hp_gate_met = max_hp > 0 and 0 < current_hp * 2 < max_hp
        exhaustion_gate_met = _coerce_int((state or {}).get("exhaustion_level")) < 6
        another_form_active = bool(active_form and not active)
        rounds = _coerce_int(payload.get("rounds_elapsed"))
        presented_forms.append(
            {
                "form_key": AVATAR_OF_MOURNING_FORM_KEY,
                "form_version": AVATAR_OF_MOURNING_FORM_VERSION,
                "label": "Avatar of Mourning",
                "active": active,
                "end_available": bool(not display_only and active and not intrinsic_state_errors),
                "status_label": "Active" if active else ("Recharging" if cooldown_active else "Ready"),
                "cooldown_active": cooldown_active,
                "cooldown_days": AVATAR_OF_MOURNING_COOLDOWN_DAYS,
                "can_complete_cooldown": bool(
                    actions_enabled and cooldown_active and not active and not pending
                ),
                "can_correct_cooldown_complete": bool(
                    actions_enabled
                    and
                    not cooldown_active
                    and last_transition
                    and last_transition.get("action") == "cooldown_complete"
                ),
                "hp_gate_met": hp_gate_met,
                "exhaustion_gate_met": exhaustion_gate_met,
                "activation_available": bool(
                    actions_enabled
                    and not active
                    and not another_form_active
                    and not cooldown_active
                    and not pending
                    and hp_gate_met
                    and exhaustion_gate_met
                ),
                "activation_blocked_reason": (
                    state_errors[0]
                    if state_errors
                    else "Another Divine Avatar Form is active."
                    if another_form_active
                    else "Resolve the pending end cost."
                    if pending
                    else "The form is active."
                    if active
                    else "The 40-day cooldown is still active."
                    if cooldown_active
                    else "Avatar of Mourning cannot be activated at fatal exhaustion."
                    if not exhaustion_gate_met
                    else "Current hit points must be above 0 and less than half the hit point maximum."
                ),
                "rounds_elapsed": rounds,
                "rounds_remaining": max(0, AVATAR_OF_MOURNING_MAX_ROUNDS - rounds),
                "end_exhaustion": rounds,
                "end_damage_dice": f"{rounds * 5}d12",
                "mourning_wave_used": bool(payload.get("mourning_wave_used")),
                "mourning_wave_available": bool(
                    actions_enabled and active and not payload.get("mourning_wave_used")
                ),
                "can_correct_mourning_wave": bool(
                    actions_enabled and payload.get("mourning_wave_used")
                ),
                "strength_of_remembrance_used": bool(payload.get("strength_of_remembrance_used")),
                "strength_of_remembrance_available": bool(
                    actions_enabled
                    and active
                    and not payload.get("strength_of_remembrance_used")
                ),
                "can_correct_strength_of_remembrance": bool(
                    actions_enabled and payload.get("strength_of_remembrance_used")
                ),
                "last_end_cost": dict(payload.get("last_end_cost") or {}),
            }
        )
    active_presented = next(
        (row for row in presented_forms if row.get("form_key") == active_form), None
    )
    return {
        "available": True,
        "display_only": display_only,
        "feature_key": DIVINE_AVATAR_FORMS_STATE_KEY,
        "label": "Divine Avatar Forms",
        "active_form": active_form,
        "active_form_label": _clean_token((active_presented or {}).get("label")),
        "has_active_form": bool(active_presented),
        "forms": presented_forms,
        "exhaustion_level": _bounded_int((state or {}).get("exhaustion_level"), maximum=6),
        "pending_resolution": pending,
        "last_resolution": last_resolution,
        "can_resolve_pending": bool(actions_enabled and pending),
        "can_correct_pending": bool(actions_enabled and pending),
        "can_correct_last_resolution": bool(
            actions_enabled and last_resolution and not active_form and not pending
        ),
        "can_undo_last_action": can_undo,
        "last_transition": last_transition,
        "action_history": deepcopy(list(forms_state.get("action_history") or [])),
        "state_errors": state_errors,
    }
