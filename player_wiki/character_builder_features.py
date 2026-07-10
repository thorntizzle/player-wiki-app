from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .character_builder_constants import (
    CAMPAIGN_PAGE_SOURCE_ID,
    NATIVE_PROGRESSION_FEATURE_SOURCE_KIND,
    SYSTEMS_OPTION_PREFIX,
)
from .character_builder_equipment import (
    _campaign_option_mechanic_effect_rows,
    _dedupe_preserve_order,
    _effect_keys_for_feature,
    _normalize_page_ref_payload,
    _systems_ref_from_entry,
)
from .character_feature_trackers import (
    apply_managed_resource_member_defaults as _apply_managed_resource_member_defaults_impl,
    build_feature_tracker_template as _build_feature_tracker_template_impl,
    build_managed_resource_tracker_template as _build_managed_resource_tracker_template_impl,
    feature_has_effect as _feature_has_effect_impl,
)
from .character_models import CharacterDefinition
from .character_profile import ensure_profile_class_rows
from .character_source_matrix import PHB_SOURCE_ID
from .repository import normalize_lookup, slugify
from .systems_models import SystemsEntryRecord

__all__ = [
    "_entry_page_ref",
    "_entry_campaign_option",
    "_campaign_option_resource_payloads",
    "_feat_effect_keys_for_feature",
    "_build_feature_payloads",
    "_feature_identity_key",
    "_build_feature_payload",
    "_proficiency_bonus_for_level",
    "_merge_feature_payloads",
    "_apply_tracker_templates_to_feature_payloads",
    "_profile_class_row_level_map",
    "_feature_tracker_current_level",
    "_build_additional_feature_tracker_payloads",
    "_build_campaign_option_tracker_template",
    "_resolve_campaign_option_resource_max",
    "_round_scaled_level_value",
    "_merge_resource_templates",
    "_extract_existing_feature_choice_map",
    "_merge_selected_choice_maps",
    "_normalize_feature_payloads",
    "_is_legacy_detached_action_summary_feature",
    "_merge_legacy_detached_action_summary_features",
    "_normalize_resource_template_payloads",
    "_character_feature_category",
    "_apply_managed_resource_member_defaults",
    "_build_managed_resource_tracker_template",
    "_feature_has_effect",
    "_build_feature_tracker_template",
    "_summarize_preview_resource",
]


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

def _campaign_option_resource_payloads(option: dict[str, Any]) -> list[dict[str, Any]]:
    option_payload = dict(option or {}) if isinstance(option, dict) else {}
    resources: list[dict[str, Any]] = []
    explicit_resource = dict(option_payload.get("resource") or {}) if isinstance(option_payload.get("resource"), dict) else {}
    if explicit_resource:
        resources.append(deepcopy(explicit_resource))
    for row in _campaign_option_mechanic_effect_rows(option_payload, kind="resource_template"):
        if explicit_resource and str(row.get("source") or "").strip() == "character_option.resource":
            continue
        resource = dict(row.get("resource") or row.get("template") or {}) if isinstance(row.get("resource") or row.get("template"), dict) else {}
        if not resource:
            resource = {}
            for key in (
                "id",
                "label",
                "category",
                "max",
                "initial_current",
                "reset_on",
                "reset_to",
                "rest_behavior",
                "notes",
                "display_order",
                "scaling",
                "activation_type",
            ):
                raw_value = row.get(key)
                if raw_value is None or raw_value == "":
                    continue
                resource[key] = deepcopy(raw_value)
        if row.get("label") and not resource.get("label"):
            resource["label"] = str(row.get("label") or "").strip()
        if resource:
            resources.append(resource)
    return resources

def _feat_effect_keys_for_feature(feature: dict[str, Any]) -> list[str]:
    return _effect_keys_for_feature(feature)

def _build_feature_payloads(
    feature_entries: list[dict[str, Any]],
    *,
    ability_scores: dict[str, int],
    current_level: int,
    class_row_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    features: list[dict[str, Any]] = []
    seen_feature_names: set[tuple[str, str]] = set()

    for index, feature_entry in enumerate(feature_entries, start=1):
        feature_payload = _build_feature_payload(
            feature_entry,
            index=index,
            class_row_id=class_row_id,
        )
        if feature_payload is None:
            continue
        feature_name = str(feature_payload.get("name") or "").strip()
        normalized_name = normalize_lookup(feature_name)
        row_identity = str(feature_payload.get("class_row_id") or "").strip()
        feature_identity = (normalized_name, row_identity)
        if not feature_name or feature_identity in seen_feature_names:
            continue
        seen_feature_names.add(feature_identity)
        features.append(feature_payload)
    return _apply_tracker_templates_to_feature_payloads(
        features,
        ability_scores=ability_scores,
        current_level=current_level,
    )

def _feature_identity_key(feature: dict[str, Any]) -> tuple[str, str]:
    return (
        normalize_lookup(str(feature.get("name") or "").strip()),
        str(feature.get("class_row_id") or "").strip(),
    )

def _build_feature_payload(
    feature_entry: dict[str, Any],
    *,
    index: int,
    class_row_id: str | None = None,
) -> dict[str, Any] | None:
    entry = feature_entry.get("entry")
    kind = str(feature_entry.get("kind") or "")
    feature_id_prefix = f"{slugify(str(class_row_id or '').strip())}-" if str(class_row_id or "").strip() else ""

    if isinstance(entry, SystemsEntryRecord):
        feature_name = str(entry.title or "").strip()
        page_ref = _entry_page_ref(entry)
        campaign_option = _entry_campaign_option(entry)
        feature_payload = {
            "id": f"{feature_id_prefix}{slugify(feature_name)}-{index}",
            "name": feature_name,
            "category": _character_feature_category(entry.entry_type),
            "source": CAMPAIGN_PAGE_SOURCE_ID if page_ref else entry.source_id,
            "description_markdown": str(campaign_option.get("description_markdown") or "").strip(),
            "activation_type": str(campaign_option.get("activation_type") or "passive").strip() or "passive",
            "tracker_ref": None,
            "systems_ref": None if page_ref else _systems_ref_from_entry(entry),
        }
        if str(class_row_id or "").strip():
            feature_payload["class_row_id"] = str(class_row_id or "").strip()
        if page_ref:
            feature_payload["page_ref"] = page_ref
        if campaign_option:
            feature_payload["campaign_option"] = campaign_option
        spell_manager = dict(feature_entry.get("spell_manager") or {})
        if spell_manager:
            feature_payload["spell_manager"] = spell_manager
        return feature_payload

    if kind == "optionalfeature":
        slug = str(feature_entry.get("slug") or "").strip()
        feature_name = str(feature_entry.get("label") or "").strip()
        if not slug or not feature_name:
            return None
        payload = {
            "id": f"{feature_id_prefix}{slugify(feature_name)}-{index}",
            "name": feature_name,
            "category": "class_feature",
            "source": PHB_SOURCE_ID,
            "source_kind": str(
                feature_entry.get("source_kind") or NATIVE_PROGRESSION_FEATURE_SOURCE_KIND
            ).strip(),
            "description_markdown": "",
            "activation_type": "passive",
            "tracker_ref": None,
            "systems_ref": {
                "entry_key": "",
                "entry_type": "optionalfeature",
                "title": feature_name,
                "slug": slug,
                "source_id": PHB_SOURCE_ID,
            },
        }
        if str(class_row_id or "").strip():
            payload["class_row_id"] = str(class_row_id or "").strip()
        return payload

    if kind == "species_trait":
        feature_name = str(feature_entry.get("label") or "").strip()
        systems_entry = feature_entry.get("systems_entry")
        page_ref = str(feature_entry.get("page_ref") or _entry_page_ref(systems_entry)).strip()
        campaign_option = dict(feature_entry.get("campaign_option") or {})
        if not feature_name or (not isinstance(systems_entry, SystemsEntryRecord) and not page_ref):
            return None
        feature_payload = {
            "id": f"{feature_id_prefix}{slugify(feature_name)}-{index}",
            "name": feature_name,
            "category": "species_trait",
            "source": page_ref or (systems_entry.source_id if isinstance(systems_entry, SystemsEntryRecord) else ""),
            "description_markdown": str(feature_entry.get("description_markdown") or "").strip(),
            "activation_type": "passive",
            "tracker_ref": None,
            "systems_ref": _systems_ref_from_entry(systems_entry) if isinstance(systems_entry, SystemsEntryRecord) else None,
        }
        if str(class_row_id or "").strip():
            feature_payload["class_row_id"] = str(class_row_id or "").strip()
        if page_ref:
            feature_payload["page_ref"] = page_ref
        if campaign_option:
            feature_payload["campaign_option"] = campaign_option
        spell_manager = dict(feature_entry.get("spell_manager") or {})
        if spell_manager:
            feature_payload["spell_manager"] = spell_manager
        return feature_payload

    if kind == "background_feature":
        feature_name = str(feature_entry.get("label") or "").strip()
        systems_entry = feature_entry.get("systems_entry")
        page_ref = str(feature_entry.get("page_ref") or _entry_page_ref(systems_entry)).strip()
        campaign_option = dict(feature_entry.get("campaign_option") or {})
        if not feature_name or (not isinstance(systems_entry, SystemsEntryRecord) and not page_ref):
            return None
        feature_payload = {
            "id": f"{feature_id_prefix}{slugify(feature_name)}-{index}",
            "name": feature_name,
            "category": "background_feature",
            "source": page_ref or (systems_entry.source_id if isinstance(systems_entry, SystemsEntryRecord) else ""),
            "description_markdown": str(feature_entry.get("description_markdown") or "").strip(),
            "activation_type": "passive",
            "tracker_ref": None,
            "systems_ref": _systems_ref_from_entry(systems_entry) if isinstance(systems_entry, SystemsEntryRecord) else None,
        }
        if str(class_row_id or "").strip():
            feature_payload["class_row_id"] = str(class_row_id or "").strip()
        if page_ref:
            feature_payload["page_ref"] = page_ref
        if campaign_option:
            feature_payload["campaign_option"] = campaign_option
        spell_manager = dict(feature_entry.get("spell_manager") or {})
        if spell_manager:
            feature_payload["spell_manager"] = spell_manager
        return feature_payload

    if kind == "feat":
        slug = str(feature_entry.get("slug") or "").strip()
        if slug.startswith(SYSTEMS_OPTION_PREFIX):
            slug = slug[len(SYSTEMS_OPTION_PREFIX):]
        feature_name = str(feature_entry.get("title") or feature_entry.get("label") or "").strip()
        systems_entry = feature_entry.get("systems_entry")
        fallback_source_id = str(feature_entry.get("source_id") or "").strip() or PHB_SOURCE_ID
        page_ref = str(feature_entry.get("page_ref") or _entry_page_ref(systems_entry)).strip()
        campaign_option = dict(feature_entry.get("campaign_option") or _entry_campaign_option(systems_entry) or {})
        if not (slug or page_ref) or not feature_name:
            return None
        feature_payload: dict[str, Any] = {
            "id": f"{feature_id_prefix}{slugify(feature_name)}-{index}",
            "name": feature_name,
            "category": "feat",
            "source": (
                CAMPAIGN_PAGE_SOURCE_ID
                if page_ref
                else (systems_entry.source_id if isinstance(systems_entry, SystemsEntryRecord) else fallback_source_id)
            ),
            "source_kind": str(
                feature_entry.get("source_kind") or NATIVE_PROGRESSION_FEATURE_SOURCE_KIND
            ).strip(),
            "description_markdown": str(campaign_option.get("description_markdown") or "").strip(),
            "activation_type": "passive",
            "tracker_ref": None,
            "systems_ref": (
                None
                if page_ref
                else (
                    _systems_ref_from_entry(systems_entry)
                    if isinstance(systems_entry, SystemsEntryRecord)
                    else {
                        "entry_key": "",
                        "entry_type": "feat",
                        "title": feature_name,
                        "slug": slug,
                        "source_id": fallback_source_id,
                    }
                )
            ),
        }
        if str(class_row_id or "").strip():
            feature_payload["class_row_id"] = str(class_row_id or "").strip()
        if page_ref:
            feature_payload["page_ref"] = page_ref
        if campaign_option:
            feature_payload["campaign_option"] = campaign_option
        spell_manager = dict(feature_entry.get("spell_manager") or {})
        if spell_manager:
            feature_payload["spell_manager"] = spell_manager
        return feature_payload

    if kind == "campaign_page_feature":
        feature_name = str(feature_entry.get("label") or feature_entry.get("name") or "").strip()
        page_ref = str(feature_entry.get("page_ref") or "").strip()
        if not feature_name or not page_ref:
            return None
        payload = {
            "id": f"{feature_id_prefix}{slugify(feature_name)}-{index}",
            "name": feature_name,
            "category": "custom_feature",
            "source": "Campaign",
            "description_markdown": str(feature_entry.get("description_markdown") or "").strip(),
            "activation_type": str(feature_entry.get("activation_type") or "passive").strip() or "passive",
            "tracker_ref": None,
            "page_ref": page_ref,
            "campaign_option": dict(feature_entry.get("campaign_option") or {}) or None,
        }
        if str(class_row_id or "").strip():
            payload["class_row_id"] = str(class_row_id or "").strip()
        spell_manager = dict(feature_entry.get("spell_manager") or {})
        if spell_manager:
            payload["spell_manager"] = spell_manager
        return payload

    return None

def _proficiency_bonus_for_level(level: int) -> int:
    clean_level = max(int(level or 1), 1)
    return 2 + ((clean_level - 1) // 4)

def _merge_feature_payloads(
    existing_features: list[dict[str, Any]],
    new_features: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = [dict(feature) for feature in existing_features]
    seen_names = {
        (
            normalize_lookup(str(feature.get("name") or "").strip()),
            str(feature.get("class_row_id") or "").strip(),
        )
        for feature in merged
        if str(feature.get("name") or "").strip()
    }
    for feature in new_features:
        feature_name = str(feature.get("name") or "").strip()
        normalized_name = normalize_lookup(feature_name)
        feature_identity = (normalized_name, str(feature.get("class_row_id") or "").strip())
        if not feature_name or feature_identity in seen_names:
            continue
        seen_names.add(feature_identity)
        merged.append(dict(feature))
    return merged

def _apply_tracker_templates_to_feature_payloads(
    features: list[dict[str, Any]],
    *,
    ability_scores: dict[str, int],
    current_level: int,
    class_row_levels: dict[str, int] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    base_features = [dict(feature or {}) for feature in list(features or [])]
    updated_features: list[dict[str, Any]] = []
    resource_templates: list[dict[str, Any]] = []
    seen_template_ids: set[str] = set()
    feature_payloads_by_identity: dict[tuple[str, str], dict[str, Any]] = {}
    for feature_payload in base_features:
        feature_identity = _feature_identity_key(feature_payload)
        if feature_identity[0]:
            feature_payloads_by_identity.setdefault(feature_identity, feature_payload)
    seen_feature_identities = {
        feature_identity
        for feature_identity in (_feature_identity_key(feature) for feature in base_features)
        if feature_identity[0]
    }
    display_order = 0

    def append_tracker_template(feature_payload: dict[str, Any], tracker_template: dict[str, Any]) -> None:
        nonlocal display_order
        template_tracker_id = str(tracker_template.get("id") or "").strip()
        tracker_id = str(feature_payload.get("tracker_ref") or "").strip() or template_tracker_id
        if tracker_id:
            feature_payload["tracker_ref"] = tracker_id
        feature_payload["activation_type"] = str(
            tracker_template.get("activation_type") or feature_payload.get("activation_type") or "passive"
        )
        normalized_tracker = dict(tracker_template)
        normalized_tracker.pop("activation_type", None)
        if tracker_id:
            normalized_tracker["id"] = tracker_id
        if str(feature_payload.get("class_row_id") or "").strip():
            normalized_tracker["class_row_id"] = str(feature_payload.get("class_row_id") or "").strip()
        if not tracker_id or tracker_id not in seen_template_ids:
            resource_templates.append(normalized_tracker)
            if tracker_id:
                seen_template_ids.add(tracker_id)
            display_order += 1

    for feature_payload in base_features:
        managed_resource_family, managed_resource_member = _apply_managed_resource_member_defaults(feature_payload)
        feature_current_level = _feature_tracker_current_level(
            feature_payload,
            current_level=current_level,
            class_row_levels=class_row_levels,
        )
        tracker_template = _build_campaign_option_tracker_template(
            feature_payload,
            display_order=display_order,
            current_level=feature_current_level,
        )
        if tracker_template is None:
            tracker_template = _build_feature_tracker_template(
                feature_payload,
                ability_scores=ability_scores,
                current_level=feature_current_level,
                display_order=display_order,
                managed_resource_member=managed_resource_member,
            )
        if tracker_template is not None:
            append_tracker_template(feature_payload, tracker_template)
        updated_features.append(feature_payload)
        for derived_feature_payload, derived_tracker_template in _build_additional_feature_tracker_payloads(
            feature_payload,
            ability_scores=ability_scores,
            current_level=feature_current_level,
            display_order=display_order,
            managed_resource_family=managed_resource_family,
            managed_resource_member=managed_resource_member,
        ):
            feature_identity = _feature_identity_key(derived_feature_payload)
            if feature_identity[0] and feature_identity in seen_feature_identities:
                existing_feature_payload = feature_payloads_by_identity.get(feature_identity)
                if existing_feature_payload is not None:
                    if not str(existing_feature_payload.get("description_markdown") or "").strip():
                        description_markdown = str(derived_feature_payload.get("description_markdown") or "").strip()
                        if description_markdown:
                            existing_feature_payload["description_markdown"] = description_markdown
                    if not existing_feature_payload.get("systems_ref") and derived_feature_payload.get("systems_ref"):
                        existing_feature_payload["systems_ref"] = dict(derived_feature_payload.get("systems_ref") or {})
                    if not existing_feature_payload.get("page_ref") and derived_feature_payload.get("page_ref"):
                        existing_feature_payload["page_ref"] = derived_feature_payload.get("page_ref")
                if derived_tracker_template is not None:
                    append_tracker_template(existing_feature_payload or dict(derived_feature_payload), derived_tracker_template)
                continue
            if derived_tracker_template is not None:
                append_tracker_template(derived_feature_payload, derived_tracker_template)
            updated_features.append(derived_feature_payload)
            if feature_identity[0]:
                seen_feature_identities.add(feature_identity)
                feature_payloads_by_identity[feature_identity] = derived_feature_payload

    return updated_features, resource_templates

def _profile_class_row_level_map(profile: dict[str, Any] | None) -> dict[str, int]:
    row_levels: dict[str, int] = {}
    for row in ensure_profile_class_rows(profile):
        row_id = str(row.get("row_id") or "").strip()
        if not row_id:
            continue
        row_levels[row_id] = max(int(row.get("level") or 0), 0)
    return row_levels

def _feature_tracker_current_level(
    feature_payload: dict[str, Any],
    *,
    current_level: int,
    class_row_levels: dict[str, int] | None = None,
) -> int:
    class_row_id = str(feature_payload.get("class_row_id") or "").strip()
    if class_row_id:
        row_level = int(dict(class_row_levels or {}).get(class_row_id) or 0)
        if row_level > 0:
            return row_level
    return current_level

def _build_additional_feature_tracker_payloads(
    feature_payload: dict[str, Any],
    *,
    ability_scores: dict[str, int],
    current_level: int,
    display_order: int,
    managed_resource_family: dict[str, Any] | None = None,
    managed_resource_member: dict[str, Any] | None = None,
) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    managed_resource_family = dict(managed_resource_family or {})
    managed_resource_member = dict(managed_resource_member or {})
    feature_id = str(feature_payload.get("id") or slugify(str(feature_payload.get("name") or "feature"))).strip() or "feature"
    shared_payload = {
        "category": str(feature_payload.get("category") or "class_feature").strip() or "class_feature",
        "source": str(feature_payload.get("source") or "").strip(),
        "systems_ref": dict(feature_payload.get("systems_ref") or {}) or None,
        "page_ref": str(feature_payload.get("page_ref") or "").strip() or None,
    }
    class_row_id = str(feature_payload.get("class_row_id") or "").strip()

    def build_derived_feature(
        *,
        suffix: str,
        name: str,
        description_markdown: str,
        activation_type: str,
    ) -> dict[str, Any]:
        payload = {
            "id": f"{feature_id}-{suffix}",
            "name": name,
            "category": shared_payload["category"],
            "source": shared_payload["source"],
            "description_markdown": description_markdown,
            "activation_type": activation_type,
            "tracker_ref": None,
        }
        if class_row_id:
            payload["class_row_id"] = class_row_id
        if shared_payload["systems_ref"] is not None:
            payload["systems_ref"] = dict(shared_payload["systems_ref"])
        if shared_payload["page_ref"]:
            payload["page_ref"] = shared_payload["page_ref"]
        return payload

    if managed_resource_family and str(managed_resource_member.get("key") or "").strip() == str(dict(managed_resource_family.get("primary") or {}).get("key") or "").strip():
        derived_payloads: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
        for member in list(managed_resource_family.get("members") or []):
            if not bool(member.get("generate_from_primary")):
                continue
            member_key = str(member.get("key") or slugify(str(member.get("name") or "member"))).strip() or "member"
            derived_feature_payload = build_derived_feature(
                suffix=member_key,
                name=str(member.get("name") or "").strip(),
                description_markdown=str(member.get("description_markdown") or "").strip(),
                activation_type=str(member.get("activation_type") or "passive").strip() or "passive",
            )
            derived_tracker_template = _build_managed_resource_tracker_template(
                dict(member),
                derived_feature_payload,
                ability_scores=ability_scores,
                current_level=current_level,
                display_order=display_order + len(derived_payloads),
            )
            derived_payloads.append((derived_feature_payload, derived_tracker_template))
        if derived_payloads:
            return derived_payloads

    category = normalize_lookup(str(feature_payload.get("category") or "").strip())
    systems_ref = dict(feature_payload.get("systems_ref") or {})
    entry_type = normalize_lookup(str(systems_ref.get("entry_type") or "").strip())
    if category != normalize_lookup("feat") and entry_type != normalize_lookup("feat"):
        return []
    effect_keys = {
        normalize_lookup(value)
        for value in _feat_effect_keys_for_feature(feature_payload)
        if str(value or "").strip()
    }
    if not _feature_has_effect(effect_keys, "Gift of the Chromatic Dragon"):
        return []
    shared_payload["category"] = str(feature_payload.get("category") or "feat").strip() or "feat"
    derived_payloads: list[tuple[dict[str, Any], dict[str, Any] | None]] = []

    chromatic_infusion_feature = build_derived_feature(
        suffix="chromatic-infusion",
        name="Gift of the Chromatic Dragon: Chromatic Infusion",
        description_markdown="Bonus action to infuse a simple or martial weapon for 1 minute; once per long rest.",
        activation_type="bonus_action",
    )
    derived_payloads.append(
        (
            chromatic_infusion_feature,
            {
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
            },
        )
    )

    reactive_resistance_uses = _proficiency_bonus_for_level(current_level)
    reactive_resistance_feature = build_derived_feature(
        suffix="reactive-resistance",
        name="Gift of the Chromatic Dragon: Reactive Resistance",
        description_markdown=(
            "Reaction to gain resistance against acid, cold, fire, lightning, or poison damage; "
            "uses equal to proficiency bonus per long rest."
        ),
        activation_type="reaction",
    )
    derived_payloads.append(
        (
            reactive_resistance_feature,
            {
                "id": "reactive-resistance",
                "label": "Reactive Resistance",
                "category": "feat",
                "initial_current": reactive_resistance_uses,
                "max": reactive_resistance_uses,
                "reset_on": "long_rest",
                "reset_to": "max",
                "rest_behavior": "confirm_before_reset",
                "notes": "Reactive Resistance",
                "display_order": display_order + 1,
                "activation_type": "reaction",
            },
        )
    )
    return derived_payloads

def _build_campaign_option_tracker_template(
    feature_payload: dict[str, Any],
    *,
    display_order: int,
    current_level: int,
) -> dict[str, Any] | None:
    option = dict(feature_payload.get("campaign_option") or {})
    resource = next(iter(_campaign_option_resource_payloads(option)), {})
    max_value = _resolve_campaign_option_resource_max(resource, current_level=current_level)
    if max_value <= 0:
        return None
    tracker_id = str(feature_payload.get("tracker_ref") or "").strip() or f"campaign-option-tracker:{feature_payload.get('id')}"
    reset_on = str(resource.get("reset_on") or "manual").strip().lower()
    tracker_template = {
        "id": tracker_id,
        "label": str(resource.get("label") or feature_payload.get("name") or "").strip(),
        "category": "custom_feature",
        "initial_current": max_value,
        "max": max_value,
        "reset_on": reset_on,
        "reset_to": "max" if reset_on in {"short_rest", "long_rest"} else "unchanged",
        "rest_behavior": "confirm_before_reset" if reset_on in {"short_rest", "long_rest"} else "manual_only",
        "notes": str(feature_payload.get("name") or "").strip(),
        "display_order": display_order,
        "activation_type": str(feature_payload.get("activation_type") or "passive").strip() or "passive",
    }
    if isinstance(resource.get("scaling"), dict) and resource.get("scaling"):
        tracker_template["scaling"] = deepcopy(resource.get("scaling"))
    return tracker_template

def _resolve_campaign_option_resource_max(
    resource: dict[str, Any],
    *,
    current_level: int,
) -> int:
    max_value = int(resource.get("max") or 0)
    scaling = dict(resource.get("scaling") or {})
    if not scaling:
        return max_value
    mode = str(scaling.get("mode") or "").strip().lower()
    scaled_value = 0
    if mode == "level":
        scaled_value = max(int(current_level or 0), 0)
    elif mode == "half_level":
        scaled_value = _round_scaled_level_value(
            int(current_level or 0) / 2,
            round_mode=str(scaling.get("round") or "down").strip().lower() or "down",
        )
    elif mode == "proficiency_bonus":
        scaled_value = _proficiency_bonus_for_level(max(int(current_level or 0), 1))
    elif mode == "thresholds":
        for threshold in list(scaling.get("thresholds") or []):
            threshold_payload = dict(threshold or {}) if isinstance(threshold, dict) else {}
            minimum_level = int(threshold_payload.get("level") or 0)
            threshold_value = int(threshold_payload.get("value") or 0)
            if minimum_level > 0 and threshold_value > 0 and current_level >= minimum_level:
                scaled_value = threshold_value
    minimum_value = int(scaling.get("minimum") or 0)
    maximum_value = int(scaling.get("maximum") or 0)
    if minimum_value > 0:
        scaled_value = max(scaled_value, minimum_value)
    if maximum_value > 0:
        scaled_value = min(scaled_value, maximum_value)
    if scaled_value <= 0:
        return max_value
    return scaled_value

def _round_scaled_level_value(value: float, *, round_mode: str) -> int:
    if round_mode == "up":
        return int(-(-value // 1))
    if round_mode == "nearest":
        return int(round(value))
    return int(value // 1)

def _merge_resource_templates(
    existing_templates: list[dict[str, Any]],
    new_templates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    new_by_id = {
        str(template.get("id") or "").strip(): dict(template)
        for template in new_templates
        if str(template.get("id") or "").strip()
    }
    seen_ids: set[str] = set()
    for template in new_templates:
        template_id = str(template.get("id") or "").strip()
        if not template_id:
            merged.append(dict(template))
    for template in existing_templates:
        template_id = str(template.get("id") or "").strip()
        if template_id and template_id in new_by_id:
            merged.append(dict(new_by_id[template_id]))
            seen_ids.add(template_id)
            continue
        merged.append(dict(template))
        if template_id:
            seen_ids.add(template_id)
    for template in new_templates:
        template_id = str(template.get("id") or "").strip()
        if not template_id or template_id in seen_ids:
            continue
        merged.append(dict(template))
        seen_ids.add(template_id)
    return merged

def _extract_existing_feature_choice_map(definition: CharacterDefinition) -> dict[str, list[str]]:
    values: list[str] = []
    for feature in list(definition.features or []):
        feature_name = str(feature.get("name") or "").strip()
        if feature_name:
            values.append(feature_name)
        systems_ref = dict(feature.get("systems_ref") or {})
        feature_slug = str(systems_ref.get("slug") or "").strip()
        if feature_slug:
            values.append(feature_slug)
    return {"existing_features": _dedupe_preserve_order(values)}

def _merge_selected_choice_maps(*choice_maps: dict[str, list[str]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for choice_map in choice_maps:
        for key, values in choice_map.items():
            merged.setdefault(str(key), [])
            merged[key] = _dedupe_preserve_order(merged[key] + [str(value).strip() for value in values if str(value).strip()])
    return merged

def _normalize_feature_payloads(
    feature_payloads: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    normalized_features: list[dict[str, Any]] = []
    for feature_payload in list(feature_payloads or []):
        payload = dict(feature_payload or {})
        name = str(payload.get("name") or "").strip()
        if not name:
            continue
        payload["name"] = name
        payload["id"] = str(payload.get("id") or "").strip() or f"{slugify(name)}-{len(normalized_features) + 1}"
        payload["category"] = str(payload.get("category") or "").strip() or "class_feature"
        payload["source"] = str(payload.get("source") or "").strip()
        payload["description_markdown"] = str(payload.get("description_markdown") or "").strip()
        payload["activation_type"] = str(payload.get("activation_type") or "passive").strip() or "passive"
        class_row_id = str(payload.get("class_row_id") or "").strip()
        if class_row_id:
            payload["class_row_id"] = class_row_id
        else:
            payload.pop("class_row_id", None)
        tracker_ref = str(payload.get("tracker_ref") or "").strip()
        if tracker_ref:
            payload["tracker_ref"] = tracker_ref
        else:
            payload.pop("tracker_ref", None)
        systems_ref = dict(payload.get("systems_ref") or {})
        if systems_ref:
            payload["systems_ref"] = systems_ref
        else:
            payload.pop("systems_ref", None)
        normalized_page_ref = _normalize_page_ref_payload(payload.get("page_ref"))
        if normalized_page_ref is not None:
            payload["page_ref"] = normalized_page_ref
        else:
            payload.pop("page_ref", None)
        campaign_option = dict(payload.get("campaign_option") or {})
        if campaign_option:
            payload["campaign_option"] = campaign_option
        else:
            payload.pop("campaign_option", None)
        spell_manager = dict(payload.get("spell_manager") or {})
        if spell_manager:
            payload["spell_manager"] = spell_manager
        else:
            payload.pop("spell_manager", None)
        normalized_features.append(payload)
    return _merge_legacy_detached_action_summary_features(normalized_features)

def _is_legacy_detached_action_summary_feature(feature_payload: dict[str, Any]) -> bool:
    name = str(feature_payload.get("name") or "").strip()
    if not name:
        return False
    if str(feature_payload.get("description_markdown") or "").strip():
        return False
    if str(feature_payload.get("source") or "").strip():
        return False
    if feature_payload.get("systems_ref") or feature_payload.get("page_ref"):
        return False
    if feature_payload.get("campaign_option") or feature_payload.get("spell_manager"):
        return False
    token_count = len(re.findall(r"[A-Za-z0-9]+", name))
    return token_count >= 12 or len(name) >= 80 or name[-1:] in {".", "!", "?"}

def _merge_legacy_detached_action_summary_features(
    normalized_features: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    targets_by_description: dict[str, list[dict[str, Any]]] = {}
    for feature_payload in normalized_features:
        if _is_legacy_detached_action_summary_feature(feature_payload):
            continue
        description_key = normalize_lookup(str(feature_payload.get("description_markdown") or ""))
        if description_key:
            targets_by_description.setdefault(description_key, []).append(feature_payload)

    compacted_features: list[dict[str, Any]] = []
    for feature_payload in normalized_features:
        if _is_legacy_detached_action_summary_feature(feature_payload):
            summary_key = normalize_lookup(str(feature_payload.get("name") or ""))
            targets = targets_by_description.get(summary_key) or []
            if len(targets) == 1:
                target = targets[0]
                incoming_activation = str(feature_payload.get("activation_type") or "").strip().lower()
                target_activation = str(target.get("activation_type") or "").strip().lower()
                if incoming_activation and incoming_activation != "passive" and target_activation in {"", "passive"}:
                    target["activation_type"] = incoming_activation
                tracker_ref = str(feature_payload.get("tracker_ref") or "").strip()
                if tracker_ref and not str(target.get("tracker_ref") or "").strip():
                    target["tracker_ref"] = tracker_ref
                continue
        compacted_features.append(feature_payload)
    return compacted_features

def _normalize_resource_template_payloads(
    resource_templates: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    normalized_templates: list[dict[str, Any]] = []
    index_by_key: dict[str, int] = {}
    for template in list(resource_templates or []):
        payload = dict(template or {})
        template_id = str(payload.get("id") or "").strip()
        label = str(payload.get("label") or "").strip()
        if not template_id and not label:
            continue
        payload["id"] = template_id or f"resource-{slugify(label or 'template')}-{len(normalized_templates) + 1}"
        payload["label"] = label or payload["id"]
        payload["category"] = str(payload.get("category") or "custom_progress").strip() or "custom_progress"
        max_value = payload.get("max")
        payload["max"] = int(max_value) if max_value not in {"", None} else None
        initial_current = payload.get("initial_current")
        payload["initial_current"] = (
            int(initial_current)
            if initial_current not in {"", None}
            else payload.get("max")
        )
        payload["reset_on"] = str(payload.get("reset_on") or "manual").strip() or "manual"
        payload["reset_to"] = str(payload.get("reset_to") or "unchanged").strip() or "unchanged"
        payload["rest_behavior"] = str(payload.get("rest_behavior") or "manual_only").strip() or "manual_only"
        payload["notes"] = str(payload.get("notes") or "").strip()
        payload["display_order"] = int(payload.get("display_order") or 0)
        class_row_id = str(payload.get("class_row_id") or "").strip()
        if class_row_id:
            payload["class_row_id"] = class_row_id
        else:
            payload.pop("class_row_id", None)
        merge_key = payload["id"]
        existing_index = index_by_key.get(merge_key)
        if existing_index is None:
            index_by_key[merge_key] = len(normalized_templates)
            normalized_templates.append(payload)
            continue
        normalized_templates[existing_index] = payload
    return normalized_templates

def _character_feature_category(entry_type: str) -> str:
    if entry_type == "feat":
        return "feat"
    if entry_type == "race":
        return "species_trait"
    if entry_type == "background":
        return "background_feature"
    return "class_feature"

def _apply_managed_resource_member_defaults(feature_payload: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    return _apply_managed_resource_member_defaults_impl(feature_payload)

def _build_managed_resource_tracker_template(
    member: dict[str, Any],
    feature_payload: dict[str, Any],
    *,
    ability_scores: dict[str, int],
    current_level: int,
    display_order: int,
) -> dict[str, Any] | None:
    return _build_managed_resource_tracker_template_impl(
        member,
        feature_payload,
        ability_scores=ability_scores,
        current_level=current_level,
        display_order=display_order,
    )

def _feature_has_effect(effect_keys: set[str], *values: str) -> bool:
    return _feature_has_effect_impl(effect_keys, *values)

def _build_feature_tracker_template(
    feature_payload: dict[str, Any],
    *,
    ability_scores: dict[str, int],
    current_level: int,
    display_order: int,
    managed_resource_member: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    return _build_feature_tracker_template_impl(
        feature_payload,
        ability_scores=ability_scores,
        current_level=current_level,
        display_order=display_order,
        managed_resource_member=managed_resource_member,
        feat_effect_keys_for_feature=_feat_effect_keys_for_feature,
    )

def _summarize_preview_resource(template: dict[str, Any]) -> str:
    label = str(template.get("label") or "").strip()
    if not label:
        return ""
    max_value = template.get("max")
    current_value = template.get("initial_current", max_value if max_value is not None else 0)
    summary = f"{label}: {int(current_value or 0)}"
    if max_value is not None:
        summary = f"{label}: {int(current_value or 0)} / {int(max_value or 0)}"
    reset_on = str(template.get("reset_on") or "").strip()
    if reset_on == "short_rest":
        return f"{summary} (Short Rest)"
    if reset_on == "long_rest":
        return f"{summary} (Long Rest)"
    return summary
