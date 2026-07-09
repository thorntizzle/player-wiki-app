from __future__ import annotations

from copy import deepcopy
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .repository import normalize_lookup, slugify

CAMPAIGN_ITEM_MECHANICS_VERSION = "2026-06-25"

CAMPAIGN_ITEM_REVIEW_DRAFT = "draft"
CAMPAIGN_ITEM_REVIEW_APPROVED = "approved"
CAMPAIGN_ITEM_REVIEW_REFERENCE_ONLY = "reference_only"
CAMPAIGN_ITEM_REVIEW_MANUAL_REVIEW = "manual_review"

CAMPAIGN_ITEM_REVIEW_STATUSES = {
    CAMPAIGN_ITEM_REVIEW_DRAFT,
    CAMPAIGN_ITEM_REVIEW_APPROVED,
    CAMPAIGN_ITEM_REVIEW_REFERENCE_ONLY,
    CAMPAIGN_ITEM_REVIEW_MANUAL_REVIEW,
}

CAMPAIGN_ITEM_SUPPORT_MODELED = "modeled"
CAMPAIGN_ITEM_SUPPORT_REFERENCE_ONLY = "reference_only"
CAMPAIGN_ITEM_SUPPORT_UNSUPPORTED = "unsupported"
CAMPAIGN_ITEM_SUPPORT_NEEDS_IMPLEMENTATION = "needs_implementation"
CAMPAIGN_ITEM_SUPPORT_MANUAL_REVIEW = "manual_review"

CAMPAIGN_ITEM_METADATA_KEYS = (
    "ability_score_minimums",
    "ac",
    "armor_profile",
    "attack_reminder_rules",
    "attunement",
    "base_item",
    "bonus",
    "bonus_ac",
    "bonus_attack_rolls",
    "bonus_damage_rolls",
    "bonus_weapon",
    "bonus_weapon_attack",
    "bonus_weapon_damage",
    "charges",
    "damage",
    "damage_type",
    "defensive_rules",
    "dmg1",
    "dmg2",
    "item_uses",
    "item_use_actions",
    "properties",
    "property",
    "range",
    "rarity",
    "recharge",
    "resource_template_bonuses",
    "spell_support",
    "stealth_disadvantage",
    "strength",
    "type",
    "versatile_damage",
    "weapon_category",
    "weapon_profile",
)

_CLASSIFICATION_RARITY_PATTERN = re.compile(
    r"\b(very rare|legendary|artifact|uncommon|common|rare)\b",
    re.IGNORECASE,
)
_CLASSIFICATION_WEAPON_PATTERN = re.compile(
    r"\bweapon(?:\s*\(([^)]+)\)|\s*,\s*([^,]+))",
    re.IGNORECASE,
)
_CLASSIFICATION_ARMOR_PATTERN = re.compile(
    r"\b(?:armor|shield)(?:\s*\(([^)]+)\)|\s*,\s*([^,]+))?",
    re.IGNORECASE,
)
_BODY_WEAPON_PATTERNS = (
    re.compile(r"\bcan be wielded as (?:an? )?(?:\+\d+\s+)?magic ([a-z][a-z' -]+?)(?: that| which| with|[.,])", re.IGNORECASE),
    re.compile(r"\bcan be used as (?:an? )?(?:\+\d+\s+)?magic ([a-z][a-z' -]+?)(?: that| which| with|[.,])", re.IGNORECASE),
    re.compile(r"\bfunctions as (?:an? )?(?:\+\d+\s+)?magic ([a-z][a-z' -]+?)(?: that| which| with|[.,])", re.IGNORECASE),
)
_SHARED_WEAPON_BONUS_PATTERNS = (
    re.compile(r"\+(\d+)\s+bonus to attack and damage rolls", re.IGNORECASE),
    re.compile(r"\+(\d+)\s+bonus to attack rolls and damage rolls", re.IGNORECASE),
)
_ATTACK_BONUS_PATTERN = re.compile(r"\+(\d+)\s+bonus to attack rolls", re.IGNORECASE)
_DAMAGE_BONUS_PATTERN = re.compile(r"\+(\d+)\s+bonus to damage rolls", re.IGNORECASE)
_ARMOR_BONUS_PATTERN = re.compile(r"\+(\d+)\s+bonus to ac", re.IGNORECASE)
_CAST_SPELL_PATTERN = re.compile(
    r"\bcast\s+([A-Z][A-Za-z' -]+?)(?:\s+once|\s+at will|\s+without|\.|,)",
)
_ONCE_REST_PATTERN = re.compile(r"\bonce per (short|long) rest\b|\bonce .*? finish a (short|long) rest\b", re.IGNORECASE)
_AT_WILL_PATTERN = re.compile(r"\bat will\b", re.IGNORECASE)


@lru_cache(maxsize=1)
def _load_weapon_profiles() -> dict[str, dict[str, Any]]:
    reference_path = Path(__file__).resolve().parent / "data" / "phb_weapon_profiles.json"
    if not reference_path.exists():
        return {}
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return {
        normalize_lookup(str(title or "")): {"title": str(title or "").strip(), **dict(profile or {})}
        for title, profile in payload.items()
        if isinstance(profile, dict) and str(title or "").strip()
    }


@lru_cache(maxsize=1)
def _load_armor_profiles() -> dict[str, dict[str, Any]]:
    reference_path = Path(__file__).resolve().parent / "data" / "phb_armor_profiles.json"
    if not reference_path.exists():
        return {}
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return {
        normalize_lookup(str(title or "")): {"title": str(title or "").strip(), **dict(profile or {})}
        for title, profile in payload.items()
        if isinstance(profile, dict) and str(title or "").strip()
    }


def normalize_campaign_item_review_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.replace("-", "_").replace(" ", "_")
    if normalized in {"approved", "approve", "modeled"}:
        return CAMPAIGN_ITEM_REVIEW_APPROVED
    if normalized in {"reference", "reference_only", "reference-only"}:
        return CAMPAIGN_ITEM_REVIEW_REFERENCE_ONLY
    if normalized in {"manual", "manual_review", "review"}:
        return CAMPAIGN_ITEM_REVIEW_MANUAL_REVIEW
    return CAMPAIGN_ITEM_REVIEW_DRAFT


def campaign_item_mechanics_is_approved(metadata: dict[str, Any] | None) -> bool:
    payload = dict(metadata or {})
    return (
        str(payload.get("campaign_item_mechanics_review_status") or "").strip().lower()
        == CAMPAIGN_ITEM_REVIEW_APPROVED
    )


def is_campaign_item_mechanics_metadata(metadata: dict[str, Any] | None) -> bool:
    payload = dict(metadata or {})
    return bool(
        payload.get("campaign_item_mechanics")
        or payload.get("campaign_item_mechanics_version")
        or payload.get("campaign_item_mechanics_review_status")
    )


def campaign_item_character_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(metadata or {})
    if is_campaign_item_mechanics_metadata(payload) and not campaign_item_mechanics_is_approved(payload):
        return {}
    return {
        key: deepcopy(value)
        for key, value in payload.items()
        if key in CAMPAIGN_ITEM_METADATA_KEYS
    }


def campaign_item_review_for_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    payload = dict(metadata or {})
    review = payload.get("campaign_item_mechanics")
    if isinstance(review, dict):
        return dict(review)
    if not is_campaign_item_mechanics_metadata(payload):
        return None
    return {
        "version": str(payload.get("campaign_item_mechanics_version") or CAMPAIGN_ITEM_MECHANICS_VERSION),
        "review_status": normalize_campaign_item_review_status(
            payload.get("campaign_item_mechanics_review_status")
        ),
        "support_state": str(payload.get("campaign_item_mechanics_support_state") or "").strip(),
        "modeled_fields": [
            key
            for key in CAMPAIGN_ITEM_METADATA_KEYS
            if key in payload and payload.get(key) not in (None, "", [], {})
        ],
        "flags": list(payload.get("campaign_item_mechanics_flags") or []),
        "field_provenance": dict(payload.get("campaign_item_mechanics_field_provenance") or {}),
    }


def build_campaign_item_mechanics_metadata(
    *,
    title: str,
    body_markdown: str,
    explicit_mechanics: dict[str, Any] | None = None,
    source_page_ref: str = "",
    source_page_metadata: dict[str, Any] | None = None,
    review_status: Any = CAMPAIGN_ITEM_REVIEW_DRAFT,
    intake_mode: str = "direct",
) -> dict[str, Any]:
    interpreted_metadata, provenance, flags = interpret_campaign_item_mechanics(
        title=title,
        body_markdown=body_markdown,
    )
    page_metadata = _extract_supported_page_metadata(source_page_metadata)
    explicit_metadata = normalize_explicit_campaign_item_mechanics(explicit_mechanics)

    mechanics_metadata = _merge_item_metadata(interpreted_metadata, page_metadata)
    mechanics_metadata = _merge_item_metadata(mechanics_metadata, explicit_metadata)
    for key in page_metadata:
        provenance.setdefault(key, {"source": "published_page_metadata"})
    for key in explicit_metadata:
        provenance[key] = {"source": "manual_review"}

    normalized_review = normalize_campaign_item_review_status(review_status)
    support_state = _support_state_for_review(normalized_review, mechanics_metadata, flags)
    modeled_fields = [
        key
        for key in CAMPAIGN_ITEM_METADATA_KEYS
        if key in mechanics_metadata and mechanics_metadata.get(key) not in (None, "", [], {})
    ]
    review_payload = {
        "version": CAMPAIGN_ITEM_MECHANICS_VERSION,
        "review_status": normalized_review,
        "support_state": support_state,
        "modeled_fields": modeled_fields,
        "flags": flags,
        "field_provenance": provenance,
        "source_page_ref": str(source_page_ref or "").strip(),
        "intake_mode": str(intake_mode or "direct").strip() or "direct",
    }
    mechanics_metadata.update(
        {
            "campaign_item": True,
            "campaign_item_mechanics_version": CAMPAIGN_ITEM_MECHANICS_VERSION,
            "campaign_item_mechanics_review_status": normalized_review,
            "campaign_item_mechanics_support_state": support_state,
            "campaign_item_mechanics_flags": flags,
            "campaign_item_mechanics_field_provenance": provenance,
            "campaign_item_mechanics": review_payload,
        }
    )
    if source_page_ref:
        mechanics_metadata["linked_published_page_ref"] = str(source_page_ref or "").strip()
        mechanics_metadata["page_ref"] = str(source_page_ref or "").strip()
    return mechanics_metadata


def interpret_campaign_item_mechanics(
    *,
    title: str,
    body_markdown: str,
) -> tuple[dict[str, Any], dict[str, dict[str, str]], list[dict[str, str]]]:
    lines = [str(line or "").strip() for line in str(body_markdown or "").splitlines() if str(line or "").strip()]
    classification_line = _first_classification_line(lines)
    body_text = " ".join(lines)
    metadata: dict[str, Any] = {}
    provenance: dict[str, dict[str, str]] = {}
    flags: list[dict[str, str]] = []

    def set_field(key: str, value: Any, source: str, excerpt: str = "") -> None:
        if value in (None, "", [], {}):
            return
        metadata[key] = deepcopy(value)
        provenance[key] = {"source": source, "excerpt": excerpt[:240]}

    if classification_line:
        rarity_match = _CLASSIFICATION_RARITY_PATTERN.search(classification_line)
        if rarity_match is not None:
            set_field("rarity", rarity_match.group(1).strip().lower(), "classification", classification_line)
        if "requires attunement" in classification_line.lower():
            set_field("attunement", classification_line, "classification", classification_line)
        weapon_match = _CLASSIFICATION_WEAPON_PATTERN.search(classification_line)
        if weapon_match is not None:
            base_weapon = _resolve_weapon_title(weapon_match.group(1) or weapon_match.group(2) or "")
            if base_weapon:
                set_field("base_item", base_weapon, "classification", classification_line)
                _stamp_weapon_profile_fields(metadata, provenance, base_weapon, classification_line)
        armor_match = _CLASSIFICATION_ARMOR_PATTERN.search(classification_line)
        if armor_match is not None and "base_item" not in metadata:
            base_armor = _resolve_armor_title(armor_match.group(1) or armor_match.group(2) or title)
            if base_armor:
                set_field("base_item", base_armor, "classification", classification_line)
                _stamp_armor_profile_fields(metadata, provenance, base_armor, classification_line)

    if "attunement" not in metadata and "requires attunement" in body_text.lower():
        set_field("attunement", "requires attunement", "body", _excerpt_for(body_text, "attunement"))

    if "base_item" not in metadata:
        for pattern in _BODY_WEAPON_PATTERNS:
            match = pattern.search(body_text)
            if match is None:
                continue
            base_weapon = _resolve_weapon_title(match.group(1) or "")
            if base_weapon:
                set_field("base_item", base_weapon, "body", match.group(0))
                _stamp_weapon_profile_fields(metadata, provenance, base_weapon, match.group(0))
                break

    shared_bonus_match = None
    for pattern in _SHARED_WEAPON_BONUS_PATTERNS:
        shared_bonus_match = pattern.search(body_text)
        if shared_bonus_match is not None:
            break
    if shared_bonus_match is not None:
        set_field("bonus_weapon", int(shared_bonus_match.group(1) or 0), "body", shared_bonus_match.group(0))
    else:
        attack_bonus_match = _ATTACK_BONUS_PATTERN.search(body_text)
        if attack_bonus_match is not None:
            set_field("bonus_weapon_attack", int(attack_bonus_match.group(1) or 0), "body", attack_bonus_match.group(0))
        damage_bonus_match = _DAMAGE_BONUS_PATTERN.search(body_text)
        if damage_bonus_match is not None:
            set_field("bonus_weapon_damage", int(damage_bonus_match.group(1) or 0), "body", damage_bonus_match.group(0))

    armor_bonus_match = _ARMOR_BONUS_PATTERN.search(body_text)
    if armor_bonus_match is not None:
        set_field("bonus_ac", int(armor_bonus_match.group(1) or 0), "body", armor_bonus_match.group(0))

    _stamp_spell_support(metadata, provenance, title, body_text)
    special_effect_metadata = campaign_item_special_effect_metadata(title)
    if special_effect_metadata:
        metadata = _merge_item_metadata(metadata, special_effect_metadata)
        for key in special_effect_metadata:
            provenance.setdefault(key, {"source": "curated_item_effect"})

    _append_unsupported_flags(flags, body_text, metadata)
    return metadata, provenance, flags


def normalize_explicit_campaign_item_mechanics(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key in CAMPAIGN_ITEM_METADATA_KEYS:
        if key not in value:
            continue
        raw_value = value.get(key)
        if raw_value in (None, "", [], {}):
            continue
        normalized[key] = _normalize_explicit_value(key, raw_value)
    return normalized


def campaign_item_special_effect_metadata(title: str) -> dict[str, Any]:
    return {}


def _first_classification_line(lines: list[str]) -> str:
    for line in lines:
        if line.startswith("*") and line.endswith("*"):
            return line.strip("*").strip()
    for line in lines:
        if any(marker in line.lower() for marker in ("weapon", "wondrous item", "armor", "shield", "requires attunement")):
            return line.strip("*").strip()
    return lines[0].strip("*").strip() if lines else ""


def _resolve_weapon_title(raw_value: Any) -> str:
    profiles = _load_weapon_profiles()
    for candidate in _name_candidates(raw_value):
        profile = profiles.get(candidate)
        if profile is not None:
            return str(profile.get("title") or "").strip()
    return ""


def _resolve_armor_title(raw_value: Any) -> str:
    profiles = _load_armor_profiles()
    for candidate in _name_candidates(raw_value):
        profile = profiles.get(candidate)
        if profile is not None:
            return str(profile.get("title") or "").strip()
    return ""


def _name_candidates(raw_value: Any) -> list[str]:
    cleaned = str(raw_value or "").strip()
    values = [cleaned]
    if "," in cleaned:
        values.append(" ".join(part.strip() for part in reversed(cleaned.split(",", 1))))
    values.append(cleaned.replace("'", ""))
    values.append(cleaned.replace("-", " "))
    return [normalize_lookup(value) for value in values if normalize_lookup(value)]


def _stamp_weapon_profile_fields(
    metadata: dict[str, Any],
    provenance: dict[str, dict[str, str]],
    base_weapon: str,
    excerpt: str,
) -> None:
    profile = _load_weapon_profiles().get(normalize_lookup(base_weapon))
    if not profile:
        return
    field_map = {
        "weapon_category": "weapon_category",
        "type": "type",
        "dmg1": "damage",
        "damage": "damage",
        "versatile_damage": "versatile_damage",
        "damage_type": "damage_type",
        "range": "range",
        "properties": "properties",
    }
    for target_key, profile_key in field_map.items():
        value = profile.get(profile_key)
        if value in (None, "", [], {}):
            continue
        metadata[target_key] = deepcopy(value)
        provenance[target_key] = {"source": "base_weapon_profile", "excerpt": excerpt[:240]}


def _stamp_armor_profile_fields(
    metadata: dict[str, Any],
    provenance: dict[str, dict[str, str]],
    base_armor: str,
    excerpt: str,
) -> None:
    profile = _load_armor_profiles().get(normalize_lookup(base_armor))
    if not profile:
        return
    type_code = str(profile.get("type") or "").strip().upper()
    if type_code:
        metadata["type"] = type_code
        provenance["type"] = {"source": "base_armor_profile", "excerpt": excerpt[:240]}
    if profile.get("base_ac") not in (None, ""):
        metadata["ac"] = int(profile.get("base_ac") or 0)
        provenance["ac"] = {"source": "base_armor_profile", "excerpt": excerpt[:240]}
    if profile.get("minimum_strength") not in (None, ""):
        metadata["strength"] = int(profile.get("minimum_strength") or 0)
        provenance["strength"] = {"source": "base_armor_profile", "excerpt": excerpt[:240]}
    if profile.get("stealth_disadvantage"):
        metadata["stealth_disadvantage"] = True
        provenance["stealth_disadvantage"] = {"source": "base_armor_profile", "excerpt": excerpt[:240]}


def _stamp_spell_support(
    metadata: dict[str, Any],
    provenance: dict[str, dict[str, str]],
    title: str,
    body_text: str,
) -> None:
    matches = list(_CAST_SPELL_PATTERN.finditer(body_text))
    if not matches:
        return
    grants = []
    for match in matches[:3]:
        spell = str(match.group(1) or "").strip()
        spell = re.sub(r"\s+", " ", spell).strip()
        if not spell:
            continue
        access_type = "at_will" if _AT_WILL_PATTERN.search(_nearby_text(body_text, match.start())) else "free_cast"
        grant: dict[str, Any] = {
            "spell": spell,
            "access_type": access_type,
        }
        rest_match = _ONCE_REST_PATTERN.search(_nearby_text(body_text, match.start()))
        if rest_match is not None:
            grant["access_uses"] = 1
            rest_kind = rest_match.group(1) or rest_match.group(2) or "long"
            grant["access_reset_on"] = f"{rest_kind.lower()}_rest"
        grants.append(grant)
    if not grants:
        return
    ability_key = _infer_spellcasting_ability(body_text)
    source = {
        "id": f"spell-source:item:{slugify(title)}",
        "title": str(title or "").strip(),
        "kind": "item",
    }
    if ability_key:
        source["ability_key"] = ability_key
    metadata["spell_support"] = [{"source": source, "grants": {"_": grants}}]
    provenance["spell_support"] = {"source": "body", "excerpt": body_text[:240]}


def _infer_spellcasting_ability(body_text: str) -> str:
    normalized = body_text.lower()
    if any(token in normalized for token in ("cleric", "druid", "ranger")):
        return "wis"
    if any(token in normalized for token in ("wizard", "artificer")):
        return "int"
    if any(token in normalized for token in ("bard", "paladin", "sorcerer", "warlock")):
        return "cha"
    return ""


def _append_unsupported_flags(
    flags: list[dict[str, str]],
    body_text: str,
    metadata: dict[str, Any],
) -> None:
    checks = [
        ("extra_damage", r"\badditional\s+\d+d\d+\s+\w+\s+damage\b|\bextra\s+\d+d\d+\s+\w+\s+damage\b"),
        ("area_effect", r"\bradius\b|\bwithin \d+ feet\b|\bcreatures? within\b"),
        ("condition_effect", r"\bblinded\b|\bdeafened\b|\bknocked prone\b|\bspeed becomes 0\b|\bdisadvantage\b|\badvantage\b"),
        ("spell_slot_expenditure", r"\bexpend(?:s|ed|ing)?\s+a\s+spell\s+slot\b|\bspend(?:s|ing)?\s+a\s+spell\s+slot\b"),
        ("charges", r"\bcharges?\b|\brecharge\b"),
        ("activation_timing", r"\bbonus action\b|\breaction\b|\bas an action\b"),
    ]
    for code, pattern in checks:
        if re.search(pattern, body_text, re.IGNORECASE):
            flags.append(
                {
                    "code": code,
                    "support_state": CAMPAIGN_ITEM_SUPPORT_NEEDS_IMPLEMENTATION,
                    "message": _flag_message(code),
                }
            )
    if "spell_support" in metadata:
        return
    if "cast " in body_text.lower():
        flags.append(
            {
                "code": "spell_grant_review",
                "support_state": CAMPAIGN_ITEM_SUPPORT_MANUAL_REVIEW,
                "message": "Spell-grant prose was detected but not confidently structured.",
            }
        )


def _flag_message(code: str) -> str:
    return {
        "extra_damage": "Extra damage is visible for review but is not yet added to generated attack damage.",
        "area_effect": "Area or target effects are visible for review but are not automated.",
        "condition_effect": "Condition, advantage, or movement-control effects are visible for review but are not automated.",
        "spell_slot_expenditure": (
            "Spell-slot expenditure is visible for review but is not yet a character-state or UI control."
        ),
        "charges": "Charges and recharge rules are stored for review but are not yet a character-state counter.",
        "activation_timing": "Activation timing is stored for review but is not yet an action-economy control.",
    }.get(code, "This mechanic needs manual review before automation.")


def _support_state_for_review(review_status: str, metadata: dict[str, Any], flags: list[dict[str, str]]) -> str:
    if review_status == CAMPAIGN_ITEM_REVIEW_REFERENCE_ONLY:
        return CAMPAIGN_ITEM_SUPPORT_REFERENCE_ONLY
    if review_status == CAMPAIGN_ITEM_REVIEW_MANUAL_REVIEW:
        return CAMPAIGN_ITEM_SUPPORT_MANUAL_REVIEW
    if review_status != CAMPAIGN_ITEM_REVIEW_APPROVED:
        return CAMPAIGN_ITEM_SUPPORT_MANUAL_REVIEW if metadata else CAMPAIGN_ITEM_SUPPORT_REFERENCE_ONLY
    if not metadata:
        return CAMPAIGN_ITEM_SUPPORT_REFERENCE_ONLY
    if any(str(flag.get("support_state") or "") == CAMPAIGN_ITEM_SUPPORT_NEEDS_IMPLEMENTATION for flag in flags):
        return CAMPAIGN_ITEM_SUPPORT_NEEDS_IMPLEMENTATION
    return CAMPAIGN_ITEM_SUPPORT_MODELED


def _extract_supported_page_metadata(value: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(value or {})
    return {
        key: deepcopy(payload[key])
        for key in CAMPAIGN_ITEM_METADATA_KEYS
        if key in payload and payload[key] not in (None, "", [], {})
    }


def _merge_item_metadata(base: dict[str, Any], extra: dict[str, Any] | None) -> dict[str, Any]:
    merged = deepcopy(dict(base or {}))
    for key, value in dict(extra or {}).items():
        if value in (None, "", [], {}):
            continue
        if key in {
            "spell_support",
            "defensive_rules",
            "resource_template_bonuses",
            "attack_reminder_rules",
            "item_use_actions",
        }:
            merged[key] = [
                dict(item or {}) if isinstance(item, dict) else item
                for item in list(merged.get(key) or [])
            ] + [
                dict(item or {}) if isinstance(item, dict) else item
                for item in list(value or [])
            ]
            continue
        if key == "ability_score_minimums":
            merged[key] = {
                **dict(merged.get(key) or {}),
                **dict(value or {}),
            }
            continue
        merged[key] = deepcopy(value)
    return merged


def _normalize_explicit_value(key: str, value: Any) -> Any:
    if key in {
        "bonus",
        "bonus_ac",
        "bonus_attack_rolls",
        "bonus_damage_rolls",
        "bonus_weapon",
        "bonus_weapon_attack",
        "bonus_weapon_damage",
        "ac",
        "strength",
    }:
        parsed = _optional_int(value)
        return parsed if parsed is not None else value
    if key == "stealth_disadvantage":
        if isinstance(value, bool):
            return value
        return str(value or "").strip().lower() in {"1", "true", "yes", "on", "disadvantage"}
    if key in {"properties", "property"} and isinstance(value, str):
        return [part.strip().upper() for part in re.split(r"[,;/]+", value) if part.strip()]
    return deepcopy(value)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"[-+]?\d+", str(value))
    return int(match.group(0)) if match is not None else None


def _nearby_text(body_text: str, index: int) -> str:
    return body_text[max(0, index - 120) : index + 220]


def _excerpt_for(body_text: str, token: str) -> str:
    index = body_text.lower().find(str(token or "").lower())
    if index < 0:
        return body_text[:240]
    return _nearby_text(body_text, index)
