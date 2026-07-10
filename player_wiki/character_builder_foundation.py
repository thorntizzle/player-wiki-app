from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .character_builder_constants import (
    CAMPAIGN_PAGE_OPTION_PREFIX,
    NATIVE_CLASS_SUPPORT_BLOCKED,
    NATIVE_CLASS_SUPPORT_SUPPORTED,
    NATIVE_SOURCE_MATRIX_SUBCLASS_ENTRY_TYPES,
    PROFILE_ENTRY_MATCH_AMBIGUOUS_FALLBACK_TITLE,
    PROFILE_ENTRY_MATCH_AMBIGUOUS_SYSTEMS_SOURCE_TITLE,
    PROFILE_ENTRY_MATCH_FALLBACK_TITLE,
    PROFILE_ENTRY_MATCH_PAGE_REF,
    PROFILE_ENTRY_MATCH_SYSTEMS_SLUG,
    PROFILE_ENTRY_MATCH_SYSTEMS_SOURCE_TITLE,
    PROFILE_ENTRY_MATCH_UNRESOLVED,
    PROFILE_ENTRY_MATCH_UNRESOLVED_SOURCE_LOCKED,
    SUPPORTED_MULTICLASS_CASTER_PROGRESSIONS,
    SYSTEMS_OPTION_PREFIX,
)
from .character_models import CharacterDefinition
from .character_profile import profile_total_level
from .character_source_matrix import DEFAULT_NATIVE_SOURCE_MATRIX_POLICY, PHB_SOURCE_ID
from .repository import normalize_lookup, slugify
from .systems_models import SystemsEntryRecord

__all__ = [
    "_extract_campaign_page_ref",
    "_systems_ref_slug",
    "_entry_page_ref",
    "_entry_campaign_option",
    "_native_entry_type",
    "_native_source_matrix_label",
    "_native_base_class_identity_supported",
    "_native_non_phb_class_support_policy",
    "_native_subclass_support_policy",
    "_native_source_matrix_support_policy",
    "_supports_native_class_entry",
    "_supports_native_subclass_entry",
    "_progression_has_spellbearing_features",
    "_class_has_base_spellcasting",
    "_class_supports_shared_slot_multiclass",
    "_subclass_supports_shared_slot_multiclass",
    "_evaluate_shared_slot_multiclass_support",
    "_entry_selection_value",
    "_resolve_selected_entry",
    "_entry_option",
    "_entry_option_title",
    "_entry_option_label",
    "_entry_option_slug",
    "_entry_option_source_id",
    "_systems_ref_source_id",
    "_systems_ref_title",
    "_profile_link_source_prefix",
    "_profile_link_subject",
    "_resolve_profile_entry_match",
    "_has_profile_entry_link",
    "_resolve_profile_entry",
    "_resolve_native_character_level",
    "_sanitize_entry_selection_value",
    "_normalize_selected_choice_value",
    "_choice_option",
    "_load_phb_class_progression",
    "_load_phb_subclass_spell_progression",
    "_class_spell_progression",
    "_phb_subclass_spell_progression_lookup_keys",
    "_subclass_spell_progression",
    "_spellcasting_mode_from_progression",
    "_spellcasting_profile_start_level",
    "_spellcasting_profile_is_active_at_level",
    "_effective_spellcasting_profile_for_row",
    "_normalize_caster_progression",
    "_class_caster_progression",
    "_spellcasting_mode_for_class",
]


def _extract_campaign_page_ref(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("page_ref") or payload.get("slug") or "").strip()
    if isinstance(payload, str):
        return str(payload).strip()
    return str(getattr(payload, "page_ref", "") or "").strip()


def _systems_ref_slug(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("slug") or "").strip()


def _entry_page_ref(entry: Any) -> str:
    metadata = dict((getattr(entry, "metadata", None) or {}) if not isinstance(entry, dict) else (entry.get("metadata") or {}))
    return str(
        metadata.get("page_ref")
        or (entry.get("page_ref") if isinstance(entry, dict) else "")
        or ""
    ).strip()


def _entry_campaign_option(entry: Any) -> dict[str, Any]:
    metadata = dict((getattr(entry, "metadata", None) or {}) if not isinstance(entry, dict) else (entry.get("metadata") or {}))
    campaign_option = dict(metadata.get("campaign_option") or {})
    if campaign_option:
        return campaign_option
    if isinstance(entry, dict) and isinstance(entry.get("campaign_option"), dict):
        return dict(entry.get("campaign_option") or {})
    return {}


def _native_entry_type(entry: SystemsEntryRecord | None) -> str:
    if not isinstance(entry, SystemsEntryRecord):
        return ""
    return str(entry.entry_type or "").strip().lower()


def _native_source_matrix_label(source_id: str) -> str:
    return DEFAULT_NATIVE_SOURCE_MATRIX_POLICY.source_label(source_id)


def _native_base_class_identity_supported(
    *,
    class_name: str,
    class_source: str,
) -> bool:
    return DEFAULT_NATIVE_SOURCE_MATRIX_POLICY.supports_base_class_identity(
        class_name=class_name,
        class_source=class_source,
    )


def _native_non_phb_class_support_policy(entry: SystemsEntryRecord | None) -> dict[str, str]:
    if not isinstance(entry, SystemsEntryRecord):
        return {
            "status": NATIVE_CLASS_SUPPORT_BLOCKED,
            "reason": "This class is missing the Systems entry needed for the current native progression flow.",
        }

    source_id = str(entry.source_id or "").strip().upper()
    if source_id == PHB_SOURCE_ID:
        return {"status": NATIVE_CLASS_SUPPORT_SUPPORTED, "reason": ""}

    if _native_base_class_identity_supported(class_name=str(entry.title or "").strip(), class_source=source_id):
        return {"status": NATIVE_CLASS_SUPPORT_SUPPORTED, "reason": ""}

    return {
        "status": NATIVE_CLASS_SUPPORT_BLOCKED,
        "reason": f"This {_native_source_matrix_label(source_id)} class is outside the current native base-class support lane.",
    }


def _native_subclass_support_policy(
    entry: SystemsEntryRecord | None,
    *,
    selected_class: SystemsEntryRecord | None = None,
) -> dict[str, str]:
    if not isinstance(entry, SystemsEntryRecord):
        return {
            "status": NATIVE_CLASS_SUPPORT_BLOCKED,
            "reason": "This subclass is missing the Systems entry needed for the current native progression flow.",
        }

    source_id = str(entry.source_id or "").strip().upper()
    source_label = _native_source_matrix_label(source_id)
    if source_id and not DEFAULT_NATIVE_SOURCE_MATRIX_POLICY.supports_subclass_source(source_id):
        return {
            "status": NATIVE_CLASS_SUPPORT_BLOCKED,
            "reason": f"This {source_label} subclass is outside the current native source matrix.",
        }

    metadata = dict(entry.metadata or {})
    class_name = str(metadata.get("class_name") or "").strip()
    class_source = str(metadata.get("class_source") or "").strip().upper()
    if not class_name and isinstance(selected_class, SystemsEntryRecord):
        class_name = str(selected_class.title or "").strip()
    if not class_source and isinstance(selected_class, SystemsEntryRecord):
        class_source = str(selected_class.source_id or "").strip().upper()

    if not class_name or not class_source:
        return {
            "status": NATIVE_CLASS_SUPPORT_BLOCKED,
            "reason": f"This {source_label} subclass is missing the base-class metadata needed for native progression.",
        }

    if not _native_base_class_identity_supported(class_name=class_name, class_source=class_source):
        return {
            "status": NATIVE_CLASS_SUPPORT_BLOCKED,
            "reason": f"This {source_label} subclass attaches to a base class outside the current native base-class support lane.",
        }

    if isinstance(selected_class, SystemsEntryRecord):
        selected_class_name = normalize_lookup(str(selected_class.title or "").strip())
        if selected_class_name != normalize_lookup(class_name) or str(selected_class.source_id or "").strip().upper() != class_source:
            return {
                "status": NATIVE_CLASS_SUPPORT_BLOCKED,
                "reason": f"This {source_label} subclass does not match the supported base class on this character.",
            }

    return {"status": NATIVE_CLASS_SUPPORT_SUPPORTED, "reason": ""}


def _native_source_matrix_support_policy(
    entry: SystemsEntryRecord | None,
    *,
    selected_class: SystemsEntryRecord | None = None,
) -> dict[str, str]:
    if not isinstance(entry, SystemsEntryRecord):
        return {
            "status": NATIVE_CLASS_SUPPORT_BLOCKED,
            "reason": "This entry is missing the Systems row needed for the current native progression flow.",
        }
    entry_type = _native_entry_type(entry)
    if entry_type == "class":
        return _native_non_phb_class_support_policy(entry)
    if entry_type in NATIVE_SOURCE_MATRIX_SUBCLASS_ENTRY_TYPES:
        return _native_subclass_support_policy(entry, selected_class=selected_class)
    return {"status": NATIVE_CLASS_SUPPORT_SUPPORTED, "reason": ""}


def _supports_native_class_entry(entry: SystemsEntryRecord | None) -> bool:
    if not isinstance(entry, SystemsEntryRecord):
        return False
    policy = _native_source_matrix_support_policy(entry)
    if str(policy.get("status") or "").strip() != NATIVE_CLASS_SUPPORT_SUPPORTED:
        return False
    metadata = dict(entry.metadata or {})
    if not str(entry.title or "").strip() or not metadata.get("hit_die"):
        return False
    if str(entry.source_id or "").strip().upper() == PHB_SOURCE_ID:
        return True
    progression = _class_spell_progression(str(entry.title or "").strip(), selected_class=entry)
    return any(
        progression.get(key)
        for key in (
            "spellcasting_ability",
            "caster_progression",
            "prepared_spells",
            "prepared_spells_change",
            "cantrip_progression",
            "spells_known_progression",
            "spells_known_progression_fixed",
            "prepared_spells_progression",
            "slot_progression",
        )
    )


def _supports_native_subclass_entry(
    entry: SystemsEntryRecord | None,
    *,
    selected_class: SystemsEntryRecord | None = None,
) -> bool:
    policy = _native_source_matrix_support_policy(entry, selected_class=selected_class)
    return str(policy.get("status") or "").strip() == NATIVE_CLASS_SUPPORT_SUPPORTED


def _progression_has_spellbearing_features(progression: list[dict[str, Any]]) -> bool:
    for group in list(progression or []):
        for feature_row in list(group.get("feature_rows") or []):
            label = normalize_lookup(str(feature_row.get("label") or "").strip())
            if any(marker in label for marker in ("spellcasting", "cantrip", "spell ", " spell", "ritual")):
                return True
            entry = feature_row.get("entry")
            if isinstance(entry, SystemsEntryRecord):
                metadata = dict(entry.metadata or {})
                if metadata.get("additional_spells") or metadata.get("spell_support") or metadata.get("spell_manager"):
                    return True
    return False


def _class_has_base_spellcasting(
    selected_class: SystemsEntryRecord | None,
) -> bool:
    if not isinstance(selected_class, SystemsEntryRecord):
        return False
    class_name = str(selected_class.title or "").strip()
    return bool(
        _spellcasting_mode_for_class(class_name, selected_class=selected_class)
        or _class_caster_progression(class_name, selected_class=selected_class)
    )


def _class_supports_shared_slot_multiclass(
    systems_service: Any,
    campaign_slug: str,
    selected_class: SystemsEntryRecord | None,
    *,
    campaign_page_records: list[Any] | None = None,
) -> bool:
    if not _supports_native_class_entry(selected_class):
        return False
    if not isinstance(selected_class, SystemsEntryRecord):
        return False
    caster_progression = _class_caster_progression(selected_class.title, selected_class=selected_class)
    if caster_progression in SUPPORTED_MULTICLASS_CASTER_PROGRESSIONS or caster_progression == "pact":
        return True
    class_progression = _class_progression_for_support_policy(
        systems_service,
        campaign_slug,
        selected_class,
        campaign_page_records=campaign_page_records,
    )
    return not _progression_has_spellbearing_features(class_progression)


def _subclass_supports_shared_slot_multiclass(
    systems_service: Any,
    campaign_slug: str,
    selected_subclass: SystemsEntryRecord | None,
    *,
    selected_class: SystemsEntryRecord | None = None,
    campaign_page_records: list[Any] | None = None,
) -> bool:
    if selected_subclass is None:
        return True
    if not _supports_native_subclass_entry(selected_subclass, selected_class=selected_class):
        return False
    if _class_has_base_spellcasting(selected_class):
        return True
    subclass_spell_profile = _subclass_spell_progression(selected_subclass)
    subclass_spell_mode = _spellcasting_mode_from_progression(subclass_spell_profile)
    subclass_caster_progression = _normalize_caster_progression(subclass_spell_profile.get("caster_progression"))
    if subclass_spell_mode or subclass_caster_progression:
        return (
            subclass_caster_progression in SUPPORTED_MULTICLASS_CASTER_PROGRESSIONS
            or subclass_caster_progression == "pact"
        )
    subclass_progression = _subclass_progression_for_support_policy(
        systems_service,
        campaign_slug,
        selected_subclass,
        campaign_page_records=campaign_page_records,
    )
    return not _progression_has_spellbearing_features(subclass_progression)


def _evaluate_shared_slot_multiclass_support(
    systems_service: Any,
    campaign_slug: str,
    *,
    selected_class: SystemsEntryRecord | None,
    selected_subclass: SystemsEntryRecord | None = None,
    row_level: int = 0,
    campaign_page_records: list[Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(selected_class, SystemsEntryRecord):
        return {
            "supported": False,
            "spellcasting_row": False,
            "reason": "This class row is missing the enabled class link needed for multiclass spellcasting support.",
        }
    if not _supports_native_class_entry(selected_class):
        policy = _native_source_matrix_support_policy(selected_class)
        return {
            "supported": False,
            "spellcasting_row": False,
            "reason": str(policy.get("reason") or "").strip() or f"{selected_class.title} is outside the native support lane.",
        }
    if selected_subclass is not None and not _supports_native_subclass_entry(selected_subclass, selected_class=selected_class):
        policy = _native_source_matrix_support_policy(selected_subclass, selected_class=selected_class)
        return {
            "supported": False,
            "spellcasting_row": False,
            "reason": str(policy.get("reason") or "").strip() or f"{selected_subclass.title} is outside the native support lane.",
        }

    class_name = str(selected_class.title or "").strip()
    class_progression = _class_progression_for_support_policy(
        systems_service,
        campaign_slug,
        selected_class,
        campaign_page_records=campaign_page_records,
    )
    subclass_progression = _subclass_progression_for_support_policy(
        systems_service,
        campaign_slug,
        selected_subclass,
        campaign_page_records=campaign_page_records,
    )
    subclass_spell_profile = _subclass_spell_progression(selected_subclass)
    subclass_spell_mode = _spellcasting_mode_from_progression(subclass_spell_profile)
    subclass_caster_progression = _normalize_caster_progression(subclass_spell_profile.get("caster_progression"))
    subclass_profile_active = (
        bool(subclass_spell_mode or subclass_caster_progression)
        and _spellcasting_profile_is_active_at_level(subclass_spell_profile, row_level)
    )
    spell_mode = _spellcasting_mode_for_class(
        class_name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=row_level,
    )
    caster_progression = _class_caster_progression(
        class_name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=row_level,
    )
    base_spellcasting_row = bool(spell_mode or caster_progression)
    subclass_has_spellbearing = _progression_has_spellbearing_features(subclass_progression)

    if base_spellcasting_row:
        if caster_progression == "pact":
            return {
                "supported": True,
                "spellcasting_row": True,
                "reason": "",
            }
        if caster_progression not in SUPPORTED_MULTICLASS_CASTER_PROGRESSIONS:
            return {
                "supported": False,
                "spellcasting_row": True,
                "reason": f"{selected_class.title} is outside the current multiclass spellcasting lane.",
            }
        return {
            "supported": True,
            "spellcasting_row": True,
            "reason": "",
        }

    if _progression_has_spellbearing_features(class_progression):
        return {
            "supported": False,
            "spellcasting_row": False,
            "reason": f"{selected_class.title} has spell-bearing class features outside the current multiclass spellcasting lane.",
        }
    if selected_subclass is not None and (subclass_has_spellbearing or subclass_spell_mode or subclass_caster_progression):
        if not (subclass_spell_mode or subclass_caster_progression):
            return {
                "supported": False,
                "spellcasting_row": False,
                "reason": (
                    f"{selected_subclass.title} grants subclass-only spellcasting, "
                    "which is not supported in the current multiclass spellcasting lane."
                ),
            }
        if not subclass_profile_active:
            return {
                "supported": True,
                "spellcasting_row": False,
                "reason": "",
            }
        if (
            subclass_caster_progression in SUPPORTED_MULTICLASS_CASTER_PROGRESSIONS
            or subclass_caster_progression == "pact"
        ):
            return {
                "supported": True,
                "spellcasting_row": True,
                "reason": "",
            }
        unsupported_lane = subclass_caster_progression or "an unknown"
        return {
            "supported": False,
            "spellcasting_row": False,
            "reason": (
                f"{selected_subclass.title} uses {unsupported_lane} subclass-only spellcasting progression, "
                "which is not supported in the current multiclass spellcasting lane."
            ),
        }
    return {
        "supported": True,
        "spellcasting_row": False,
        "reason": "",
    }


def _class_progression_for_support_policy(
    systems_service: Any,
    campaign_slug: str,
    selected_class: SystemsEntryRecord | None,
    *,
    campaign_page_records: list[Any] | None = None,
) -> list[dict[str, Any]]:
    if selected_class is None:
        return []
    return list(
        systems_service.build_class_feature_progression_for_class_entry(
            campaign_slug,
            selected_class,
        )
        or []
    )


def _subclass_progression_for_support_policy(
    systems_service: Any,
    campaign_slug: str,
    selected_subclass: SystemsEntryRecord | None,
    *,
    campaign_page_records: list[Any] | None = None,
) -> list[dict[str, Any]]:
    if selected_subclass is None:
        return []
    return list(
        systems_service.build_subclass_feature_progression_for_subclass_entry(
            campaign_slug,
            selected_subclass,
        )
        or []
    )


def _entry_selection_value(entry: Any) -> str:
    page_ref = _entry_page_ref(entry)
    if page_ref:
        return f"{CAMPAIGN_PAGE_OPTION_PREFIX}{page_ref}"
    slug = _entry_option_slug(entry)
    if slug:
        return f"{SYSTEMS_OPTION_PREFIX}{slug}"
    return ""


def _resolve_selected_entry(
    options: list[SystemsEntryRecord],
    selected_slug: str,
) -> SystemsEntryRecord | None:
    cleaned_slug = str(selected_slug or "").strip()
    if cleaned_slug:
        for entry in options:
            if cleaned_slug in {
                entry.slug,
                _entry_selection_value(entry),
                _entry_page_ref(entry),
            }:
                return entry
            if cleaned_slug == f"{SYSTEMS_OPTION_PREFIX}{entry.slug}" and entry.slug:
                return entry
        return None
    return options[0] if options else None


def _entry_option(entry: SystemsEntryRecord) -> dict[str, str]:
    return {
        "slug": entry.slug,
        "value": _entry_selection_value(entry) or entry.slug,
        "title": entry.title,
        "source_id": entry.source_id,
        "page_ref": _entry_page_ref(entry),
        "campaign_option": _entry_campaign_option(entry) or None,
        "label": _entry_option_label(entry),
    }


def _entry_option_title(entry: Any) -> str:
    if isinstance(entry, SystemsEntryRecord):
        return str(entry.title or "").strip()
    if isinstance(entry, dict):
        return str(entry.get("title") or "").strip()
    return ""


def _entry_option_label(entry: Any) -> str:
    title = _entry_option_title(entry)
    if _entry_page_ref(entry):
        return f"{title} (Campaign)" if title else "Campaign"
    source_id = _entry_option_source_id(entry)
    if title and source_id and str(source_id).strip().upper() != PHB_SOURCE_ID:
        return f"{title} ({source_id})"
    return title


def _entry_option_slug(entry: Any) -> str:
    if isinstance(entry, SystemsEntryRecord):
        return str(entry.slug or "").strip()
    if isinstance(entry, dict):
        return str(entry.get("slug") or "").strip()
    return ""


def _entry_option_source_id(entry: Any) -> str:
    if isinstance(entry, SystemsEntryRecord):
        return str(entry.source_id or "").strip()
    if isinstance(entry, dict):
        return str(entry.get("source_id") or "").strip()
    return ""


def _systems_ref_source_id(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("source_id") or "").strip().upper()


def _systems_ref_title(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("title") or "").strip()


def _profile_link_source_prefix(
    *,
    systems_ref: Any = None,
    entry: Any = None,
) -> str:
    source_id = _systems_ref_source_id(systems_ref) or str(_entry_option_source_id(entry) or "").strip().upper()
    if not DEFAULT_NATIVE_SOURCE_MATRIX_POLICY.should_prefix_profile_link_source(source_id):
        return ""
    return f"{source_id} "


def _profile_link_subject(
    label: str,
    *,
    systems_ref: Any = None,
    entry: Any = None,
) -> str:
    clean_label = str(label or "").strip() or "link"
    return f"{_profile_link_source_prefix(systems_ref=systems_ref, entry=entry)}{clean_label}"


def _resolve_profile_entry_match(
    options: list[SystemsEntryRecord],
    systems_ref: Any,
    *,
    page_ref: Any = None,
    fallback_title: str = "",
) -> dict[str, Any]:
    selected_page_ref = _extract_campaign_page_ref(page_ref)
    if selected_page_ref:
        resolved = next((entry for entry in options if _entry_page_ref(entry) == selected_page_ref), None)
        if resolved is not None:
            return {"entry": resolved, "match_mode": PROFILE_ENTRY_MATCH_PAGE_REF, "candidate_count": 1}

    selected_slug = _systems_ref_slug(systems_ref)
    if selected_slug:
        resolved = _resolve_selected_entry(options, selected_slug)
        if resolved is not None:
            return {"entry": resolved, "match_mode": PROFILE_ENTRY_MATCH_SYSTEMS_SLUG, "candidate_count": 1}

    source_locked_title = _systems_ref_title(systems_ref) or str(fallback_title or "").strip()
    normalized_source_locked_title = normalize_lookup(source_locked_title)
    source_id = _systems_ref_source_id(systems_ref)
    if source_id and normalized_source_locked_title:
        candidates = [
            entry
            for entry in options
            if str(entry.source_id or "").strip().upper() == source_id
            and normalize_lookup(entry.title) == normalized_source_locked_title
        ]
        if len(candidates) == 1:
            return {
                "entry": candidates[0],
                "match_mode": PROFILE_ENTRY_MATCH_SYSTEMS_SOURCE_TITLE,
                "candidate_count": 1,
            }
        if candidates:
            return {
                "entry": None,
                "match_mode": PROFILE_ENTRY_MATCH_AMBIGUOUS_SYSTEMS_SOURCE_TITLE,
                "candidate_count": len(candidates),
            }
        return {"entry": None, "match_mode": PROFILE_ENTRY_MATCH_UNRESOLVED_SOURCE_LOCKED, "candidate_count": 0}

    normalized_title = normalize_lookup(source_locked_title)
    if not normalized_title:
        return {"entry": None, "match_mode": PROFILE_ENTRY_MATCH_UNRESOLVED, "candidate_count": 0}
    candidates = [entry for entry in options if normalize_lookup(entry.title) == normalized_title]
    if len(candidates) == 1:
        return {
            "entry": candidates[0],
            "match_mode": PROFILE_ENTRY_MATCH_FALLBACK_TITLE,
            "candidate_count": 1,
        }
    if candidates:
        return {
            "entry": None,
            "match_mode": PROFILE_ENTRY_MATCH_AMBIGUOUS_FALLBACK_TITLE,
            "candidate_count": len(candidates),
        }
    return {"entry": None, "match_mode": PROFILE_ENTRY_MATCH_UNRESOLVED, "candidate_count": 0}


def _has_profile_entry_link(
    systems_ref: Any,
    *,
    page_ref: Any = None,
) -> bool:
    return bool(_systems_ref_slug(systems_ref) or _extract_campaign_page_ref(page_ref))


def _resolve_profile_entry(
    options: list[SystemsEntryRecord],
    systems_ref: Any,
    *,
    page_ref: Any = None,
    fallback_title: str = "",
) -> SystemsEntryRecord | None:
    return _resolve_profile_entry_match(
        options,
        systems_ref,
        page_ref=page_ref,
        fallback_title=fallback_title,
    ).get("entry")


def _resolve_native_character_level(definition: CharacterDefinition) -> int:
    return profile_total_level(definition.profile, default=0)


def _sanitize_entry_selection_value(
    raw_value: Any,
    options: list[SystemsEntryRecord],
) -> str:
    allowed_values = {
        candidate
        for entry in list(options or [])
        for candidate in (
            _entry_selection_value(entry),
            _entry_page_ref(entry),
            _entry_option_slug(entry),
        )
        if str(candidate or "").strip()
    }
    selected_value = _normalize_selected_choice_value(str(raw_value or "").strip(), allowed_values)
    return selected_value if selected_value in allowed_values else ""


def _normalize_selected_choice_value(
    raw_value: str,
    allowed_values: set[str],
) -> str:
    clean_value = str(raw_value or "").strip()
    if not clean_value:
        return ""
    if clean_value in allowed_values:
        return clean_value
    systems_value = f"{SYSTEMS_OPTION_PREFIX}{clean_value}"
    if systems_value in allowed_values:
        return systems_value
    page_value = f"{CAMPAIGN_PAGE_OPTION_PREFIX}{clean_value}"
    if page_value in allowed_values:
        return page_value
    return clean_value


def _choice_option(label: str, value: str) -> dict[str, str]:
    return {"label": label, "value": value}


@lru_cache(maxsize=1)
def _load_phb_class_progression() -> dict[str, dict[str, Any]]:
    reference_path = Path(__file__).resolve().parent / "data" / "phb_class_progression.json"
    if not reference_path.exists():
        return {}
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}

    normalized: dict[str, dict[str, Any]] = {}
    for class_name, raw_progression in payload.items():
        if not isinstance(raw_progression, dict):
            continue
        normalized[str(class_name)] = {
            "spellcasting_ability": str(raw_progression.get("spellcasting_ability") or "").strip(),
            "caster_progression": str(raw_progression.get("caster_progression") or "").strip(),
            "cantrip_progression": [int(value or 0) for value in list(raw_progression.get("cantrip_progression") or [])],
            "spells_known_progression": [
                int(value or 0) for value in list(raw_progression.get("spells_known_progression") or [])
            ],
            "spells_known_progression_fixed": [
                int(value or 0) for value in list(raw_progression.get("spells_known_progression_fixed") or [])
            ],
            "prepared_spells": str(raw_progression.get("prepared_spells") or "").strip(),
            "prepared_spells_progression": [
                int(value or 0) for value in list(raw_progression.get("prepared_spells_progression") or [])
            ],
            "slot_progression": [
                [
                    {
                        "level": int(dict(slot or {}).get("level") or 0),
                        "max_slots": int(dict(slot or {}).get("max_slots") or 0),
                    }
                    for slot in list(level_slots or [])
                    if int(dict(slot or {}).get("level") or 0) > 0 and int(dict(slot or {}).get("max_slots") or 0) > 0
                ]
                for level_slots in list(raw_progression.get("slot_progression") or [])
            ],
        }
    return normalized


@lru_cache(maxsize=1)
def _load_phb_subclass_spell_progression() -> dict[str, dict[str, Any]]:
    reference_path = Path(__file__).resolve().parent / "data" / "phb_subclass_spell_progression.json"
    if not reference_path.exists():
        return {}
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}

    normalized: dict[str, dict[str, Any]] = {}
    for subclass_slug, raw_progression in payload.items():
        if not isinstance(raw_progression, dict):
            continue
        normalized[str(subclass_slug).strip()] = {
            "spellcasting_ability": str(raw_progression.get("spellcasting_ability") or "").strip(),
            "caster_progression": str(raw_progression.get("caster_progression") or "").strip(),
            "spell_list_class_name": str(raw_progression.get("spell_list_class_name") or "").strip(),
            "cantrip_progression": [int(value or 0) for value in list(raw_progression.get("cantrip_progression") or [])],
            "spells_known_progression": [
                int(value or 0) for value in list(raw_progression.get("spells_known_progression") or [])
            ],
            "spells_known_progression_fixed": [
                int(value or 0) for value in list(raw_progression.get("spells_known_progression_fixed") or [])
            ],
            "prepared_spells": str(raw_progression.get("prepared_spells") or "").strip(),
            "prepared_spells_progression": [
                int(value or 0) for value in list(raw_progression.get("prepared_spells_progression") or [])
            ],
            "slot_progression": [
                [
                    {
                        "level": int(dict(slot or {}).get("level") or 0),
                        "max_slots": int(dict(slot or {}).get("max_slots") or 0),
                    }
                    for slot in list(level_slots or [])
                    if int(dict(slot or {}).get("level") or 0) > 0 and int(dict(slot or {}).get("max_slots") or 0) > 0
                ]
                for level_slots in list(raw_progression.get("slot_progression") or [])
            ],
        }
    return normalized


def _class_spell_progression(
    class_name: str,
    *,
    selected_class: SystemsEntryRecord | None = None,
) -> dict[str, Any]:
    progression = dict(_load_phb_class_progression().get(str(class_name or "").strip()) or {})
    if selected_class is None:
        return progression

    metadata = dict(selected_class.metadata or {})
    for key in (
        "spellcasting_ability",
        "caster_progression",
        "spell_list_class_name",
        "prepared_spells",
        "prepared_spells_change",
    ):
        value = str(metadata.get(key) or "").strip()
        if value:
            progression[key] = value
    for key in (
        "cantrip_progression",
        "spells_known_progression",
        "spells_known_progression_fixed",
        "prepared_spells_progression",
    ):
        values = [int(value or 0) for value in list(metadata.get(key) or [])]
        if values:
            progression[key] = values
    slot_rows: list[list[dict[str, Any]]] = []
    for row in list(metadata.get("slot_progression") or []):
        normalized_row: list[dict[str, Any]] = []
        for slot in list(row or []):
            slot_payload = dict(slot or {})
            level = int(slot_payload.get("level") or 0)
            max_slots = int(slot_payload.get("max_slots") or 0)
            if level > 0 and max_slots > 0:
                normalized_row.append({"level": level, "max_slots": max_slots})
        slot_rows.append(normalized_row)
    if slot_rows:
        progression["slot_progression"] = slot_rows
    return progression


def _phb_subclass_spell_progression_lookup_keys(
    selected_subclass: SystemsEntryRecord | None,
) -> list[str]:
    if not isinstance(selected_subclass, SystemsEntryRecord):
        return []
    lookup_keys: list[str] = []

    def _append(candidate: Any) -> None:
        clean_candidate = str(candidate or "").strip()
        if clean_candidate and clean_candidate not in lookup_keys:
            lookup_keys.append(clean_candidate)

    _append(selected_subclass.slug)
    source_id = str(
        selected_subclass.source_id
        or dict(selected_subclass.metadata or {}).get("subclass_source")
        or dict(selected_subclass.metadata or {}).get("class_source")
        or ""
    ).strip()
    title_slug = slugify(str(selected_subclass.title or "").strip())
    if source_id and title_slug:
        _append(f"{source_id.lower()}-subclass-{title_slug}")
    return lookup_keys


def _subclass_spell_progression(
    selected_subclass: SystemsEntryRecord | None,
) -> dict[str, Any]:
    if not isinstance(selected_subclass, SystemsEntryRecord):
        return {}
    progression_reference = _load_phb_subclass_spell_progression()
    progression: dict[str, Any] = {}
    for lookup_key in _phb_subclass_spell_progression_lookup_keys(selected_subclass):
        reference_progression = progression_reference.get(lookup_key)
        if isinstance(reference_progression, dict):
            progression = dict(reference_progression)
            break
    metadata = dict(selected_subclass.metadata or {})
    for key in (
        "spellcasting_ability",
        "caster_progression",
        "spell_list_class_name",
        "prepared_spells",
        "prepared_spells_change",
    ):
        value = str(metadata.get(key) or "").strip()
        if value:
            progression[key] = value
    for key in (
        "cantrip_progression",
        "spells_known_progression",
        "spells_known_progression_fixed",
        "prepared_spells_progression",
    ):
        values = [int(value or 0) for value in list(metadata.get(key) or [])]
        if values:
            progression[key] = values
    slot_rows: list[list[dict[str, Any]]] = []
    for row in list(metadata.get("slot_progression") or []):
        normalized_row: list[dict[str, Any]] = []
        for slot in list(row or []):
            slot_payload = dict(slot or {})
            level = int(slot_payload.get("level") or 0)
            max_slots = int(slot_payload.get("max_slots") or 0)
            if level > 0 and max_slots > 0:
                normalized_row.append({"level": level, "max_slots": max_slots})
        slot_rows.append(normalized_row)
    if slot_rows:
        progression["slot_progression"] = slot_rows
    return progression


def _spellcasting_mode_from_progression(
    progression: dict[str, Any],
) -> str:
    if list(progression.get("spells_known_progression_fixed") or []):
        return "wizard"
    if str(progression.get("prepared_spells") or "").strip() or list(progression.get("prepared_spells_progression") or []):
        return "prepared"
    if list(progression.get("spells_known_progression") or []):
        return "known"
    return ""


def _spellcasting_profile_start_level(
    progression: dict[str, Any],
) -> int:
    candidate_levels: list[int] = []
    for key in (
        "cantrip_progression",
        "spells_known_progression",
        "spells_known_progression_fixed",
        "prepared_spells_progression",
    ):
        values = [max(int(value or 0), 0) for value in list(progression.get(key) or [])]
        candidate_levels.extend(index for index, value in enumerate(values, start=1) if value > 0)
    candidate_levels.extend(
        index
        for index, level_slots in enumerate(list(progression.get("slot_progression") or []), start=1)
        if list(level_slots or [])
    )
    if candidate_levels:
        return min(candidate_levels)
    if str(progression.get("prepared_spells") or "").strip():
        return 1
    return 0


def _spellcasting_profile_is_active_at_level(
    progression: dict[str, Any],
    row_level: int,
) -> bool:
    start_level = _spellcasting_profile_start_level(progression)
    if start_level <= 0:
        return False
    return max(int(row_level or 0), 0) >= start_level


def _effective_spellcasting_profile_for_row(
    class_name: str,
    *,
    selected_class: SystemsEntryRecord | None = None,
    selected_subclass: SystemsEntryRecord | None = None,
    row_level: int = 0,
) -> dict[str, Any]:
    progression = _class_spell_progression(class_name, selected_class=selected_class)
    if _spellcasting_mode_from_progression(progression) or _normalize_caster_progression(progression.get("caster_progression")):
        if not str(progression.get("spell_list_class_name") or "").strip():
            progression["spell_list_class_name"] = str(class_name or "").strip()
        return progression

    subclass_progression = _subclass_spell_progression(selected_subclass)
    if not subclass_progression:
        return {}
    if int(row_level or 0) > 0 and not _spellcasting_profile_is_active_at_level(subclass_progression, row_level):
        return {}
    if not str(subclass_progression.get("spell_list_class_name") or "").strip():
        subclass_progression["spell_list_class_name"] = str(class_name or "").strip()
    return subclass_progression


def _normalize_caster_progression(caster_progression: Any) -> str:
    clean_value = normalize_lookup(str(caster_progression or "").strip())
    if clean_value in {"half", "12", "onehalf"}:
        return "1/2"
    if clean_value in {"third", "13", "onethird"}:
        return "1/3"
    if clean_value in {"artificer", "full", "pact"}:
        return clean_value
    return clean_value


def _class_caster_progression(
    class_name: str,
    *,
    selected_class: SystemsEntryRecord | None = None,
    selected_subclass: SystemsEntryRecord | None = None,
    row_level: int = 0,
) -> str:
    progression = _effective_spellcasting_profile_for_row(
        class_name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=row_level,
    )
    return _normalize_caster_progression(progression.get("caster_progression"))


def _spellcasting_mode_for_class(
    class_name: str,
    *,
    selected_class: SystemsEntryRecord | None = None,
    selected_subclass: SystemsEntryRecord | None = None,
    row_level: int = 0,
) -> str:
    progression = _effective_spellcasting_profile_for_row(
        class_name,
        selected_class=selected_class,
        selected_subclass=selected_subclass,
        row_level=row_level,
    )
    return _spellcasting_mode_from_progression(progression)
