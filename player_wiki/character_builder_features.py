from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any
from flask import has_app_context

from .character_builder_constants import (
    CAMPAIGN_PAGE_SOURCE_ID,
    NATIVE_PROGRESSION_FEATURE_SOURCE_KIND,
    SYSTEMS_OPTION_PREFIX,
)
from .character_builder_foundation import (
    _entry_campaign_option,
    _entry_page_ref,
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
from .character_spell_grants import (
    AcquisitionContext, GrantContractError, feature_acquisition_id, owner_occurrence_id,
)
from .managed_resource_registry import (managed_resource_feature_identity,
    resolve_managed_resource_family_and_member)
from .character_page_companion import blocks_page_companion_heuristics
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
    "_derive_continuation_tracker_templates",
    "_require_known_continuation_resource_observations",
    "_require_preserved_continuation_resource_state",
    "_continuation_pool_ids",
    "_retain_continuation_resource_templates",
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
    class_row_levels: dict[str, int] | None = None,
    defer_trackers: bool = False,
    acquisition_context: AcquisitionContext | None = None,
    acquisition_class_row_id: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    defer_trackers = bool(defer_trackers and _activated_committed_character_mode())
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
        selected_entry = feature_entry.get("entry") or feature_entry.get("systems_entry")
        if isinstance(selected_entry, SystemsEntryRecord):
            from .character_feature_composition import selected_replacement_claim, CLAIM_FIELD
            claim = selected_replacement_claim(selected_entry,
                class_row_id=str(feature_payload.get("class_row_id") or ""))
            if claim is not None:
                feature_payload[CLAIM_FIELD] = claim
        native_acquisition = feature_entry.get("native_acquisition")
        # Page options use synthetic catalogue entries, not Systems publications.
        # Keep their ordinary feature identity and effects without manufacturing
        # a Systems acquisition from that catalogue key.
        if isinstance(native_acquisition, dict) and not feature_payload.get("page_ref"):
            feature_payload["native_acquisition"] = deepcopy(native_acquisition)
            if acquisition_context is not None:
                if not isinstance(acquisition_context, AcquisitionContext):
                    raise GrantContractError("Native acquisition context is unavailable.")
                ref = dict(feature_payload.get("systems_ref") or {})
                rule_id = native_acquisition.get("grant_rule_id")
                slot_id = native_acquisition.get("choice_slot_id")
                if not ref.get("entry_key") or not isinstance(rule_id, str) or not rule_id or not isinstance(slot_id, str) or not slot_id:
                    raise GrantContractError("This feature needs its exact source rule and acquisition slot.")
                owner_row_id = str(feature_payload.get("class_row_id") or acquisition_class_row_id or "")
                acquisition_id = feature_acquisition_id(
                    acquisition_context, source_ref=ref, grant_rule_id=rule_id,
                    choice_slot_id=slot_id, class_row_id=owner_row_id,
                )
                feature_payload["id"] = owner_occurrence_id(
                    acquisition_id=acquisition_id, source_ref=ref,
                    grant_rule_id=rule_id, choice_slot_id=slot_id,
                )
        feature_name = str(feature_payload.get("name") or "").strip()
        feature_identity = _continuation_feature_identity(feature_payload) if defer_trackers else _feature_identity_key(feature_payload)
        if not feature_name or feature_identity in seen_feature_names:
            continue
        seen_feature_names.add(feature_identity)
        features.append(feature_payload)
    if defer_trackers:
        return features, []
    return _apply_tracker_templates_to_feature_payloads(
        features,
        ability_scores=ability_scores,
        current_level=current_level,
        class_row_levels=class_row_levels,
    )

def _feature_identity_key(feature: dict[str, Any]) -> tuple[str, str]:
    ref = dict(feature.get("systems_ref") or {})
    if ref.get("entry_key") and ref.get("source_id"):
        # Exact publication and acquisition are separate from display names.
        # Legacy rows retain their raw IDs; this key asserts no owner custody.
        return (
            json.dumps([
                ref.get("library_slug"), ref.get("entry_type"), ref["source_id"],
                ref["entry_key"], feature.get("native_acquisition"),
                feature.get("id") if "native_acquisition" in feature else None,
            ], sort_keys=True, ensure_ascii=False, separators=(",", ":")),
            str(feature.get("class_row_id") or "").strip(),
        )
    managed_identity = managed_resource_feature_identity(feature)
    if managed_identity is not None:
        return managed_identity
    return (
        normalize_lookup(str(feature.get("name") or "").strip()),
        str(feature.get("class_row_id") or "").strip(),
    )


def _tracker_feature_identity_key(feature: dict[str, Any]) -> tuple[str, str]:
    """Match qualified resource members without merging acquisition owners."""
    # A generated member may cite its parent's publication, or have its own
    # attained source/acquisition. Neither makes it the parent's resource.
    # Proved aliases are reduced by SourceAuthority, never by this key;
    # competing real owners of one member must still fail the tracker guard.
    return managed_resource_feature_identity(feature) or _feature_identity_key(feature)


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
            "activation_type": str(campaign_option.get("activation_type") or "passive").strip() or "passive",
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
            "activation_type": str(campaign_option.get("activation_type") or "passive").strip() or "passive",
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
    *, preserve_source_aliases: bool = False,
) -> list[dict[str, Any]]:
    merged = [dict(feature) for feature in existing_features]
    identity = (_continuation_feature_identity
                if preserve_source_aliases and _activated_committed_character_mode() else _feature_identity_key)
    seen_names = {
        identity(feature)
        for feature in merged
        if str(feature.get("name") or "").strip()
    }
    for feature in new_features:
        feature_name = str(feature.get("name") or "").strip()
        feature_identity = identity(feature)
        if not feature_name or feature_identity in seen_names:
            continue
        seen_names.add(feature_identity)
        merged.append(dict(feature))
    return merged


def _continuation_feature_identity(feature: dict[str, Any]) -> tuple[str, str]:
    """Only the same exact source grant may disappear before qualification."""
    if "native_acquisition" in feature:
        return _feature_identity_key(feature)
    ref = dict(feature.get("systems_ref") or {})
    canonical = {**feature, "source": ref.get("source_id")}
    if managed_resource_feature_identity(canonical) is not None:
        return (json.dumps([ref, normalize_lookup(feature.get("name"))], sort_keys=True),
                str(feature.get("class_row_id") or "").strip())
    return _feature_identity_key(feature)


def _merge_generated_tracker_payloads(
    existing_features: list[dict[str, Any]],
    generated_features: list[dict[str, Any]],
    *, attained_owners: dict[str, frozenset[str]] | None = None,
) -> list[dict[str, Any]]:
    """Expose missing children without adding another owner of a retained member."""
    def member_identity(feature):
        ref = dict(feature.get("systems_ref") or {})
        # Planning relation only: retain raw citations and every real owner.
        # SourceAuthority must subsequently qualify the sources and any aliases.
        probe = {**feature, "source": ref.get("source_id")}
        owners = (attained_owners or {}).get(ref.get("entry_key"), frozenset())
        if not probe.get("class_row_id") and len(owners) == 1:
            probe["class_row_id"] = next(iter(owners))
        return managed_resource_feature_identity(probe)

    retained_members = {identity for feature in existing_features
                        if (identity := member_identity(feature)) is not None}
    missing_children = [feature for feature in generated_features
                        if member_identity(feature) not in retained_members]
    return _merge_feature_payloads(existing_features, missing_children, preserve_source_aliases=True)


def _continuation_pool_ids(features) -> set[str]:
    if not _activated_committed_character_mode():
        return set()
    owners, noncanonical = {}, set()
    for feature in features:
        canonical = {**feature, "source": dict(feature.get("systems_ref") or {}).get("source_id")}
        identity = managed_resource_feature_identity(canonical)
        family, member = resolve_managed_resource_family_and_member(canonical)
        tracker_id = str(dict((member or {}).get("tracker") or {}).get("id") or "")
        if identity and family and tracker_id:
            owners.setdefault(tracker_id, []).append(identity)
            physical_id = str(feature.get("tracker_ref") or "").strip()
            if physical_id and physical_id != tracker_id:
                # Structural preservation only; the authority resolver must
                # independently authenticate this physical association.
                noncanonical.add(physical_id)
            if feature.get("source") != canonical["source"]:
                noncanonical.add(tracker_id)
    return noncanonical | {key for key, rows in owners.items() if len(rows) > 1}


def _require_known_continuation_resource_observations(definition, state) -> None:
    """Refuse before legacy state reconciliation can turn UNKNOWN into zero."""
    from .character_builder_progression import CharacterBuildError
    managed_ids = _continuation_pool_ids(definition.features)
    for row in definition.resource_templates:
        if row.get("id") in managed_ids and "initial_current" in row and (type(row["initial_current"]) is not int or row["initial_current"] < 0):
            raise CharacterBuildError("A retained resource observation needs manager repair before advancement.")
    for row in list((state or {}).get("resources") or []):
        if isinstance(row, dict) and row.get("id") in managed_ids and (type(row.get("current")) is not int or row["current"] < 0):
            raise CharacterBuildError("Resource play state is unknown. Repair it before advancement.")


def _require_preserved_continuation_resource_state(prior, candidate, state, *, allow_new_pools=False) -> None:
    """Refuse a dependent pool transition that the legacy merge would lose."""
    from .character_builder_progression import CharacterBuildError
    from .character_service import build_resource_state
    _require_known_continuation_resource_observations(candidate, state)
    managed_ids = _continuation_pool_ids(candidate.features)
    for resource_id in managed_ids:
        old = [row for row in list((state or {}).get("resources") or [])
               if isinstance(row, dict) and row.get("id") == resource_id]
        templates = [row for row in candidate.resource_templates if row.get("id") == resource_id]
        if not old:
            if not allow_new_pools or any(row.get("id") == resource_id for row in prior.resource_templates):
                raise CharacterBuildError("A retained resource has no current play-state observation. Repair it first.")
            continue
        if len(old) != 1 or len(templates) != 1:
            raise CharacterBuildError("Resource play state needs an exact retained owner before advancement.")
        current = old[0].get("current")
        maximum = templates[0].get("max")
        if (type(current) is not int or current < 0
                or old[0].get("max") is not None and type(old[0]["max"]) is not int
                or maximum is not None and (type(maximum) is not int or current > maximum)):
            raise CharacterBuildError("Advancement would lose a retained resource observation. Repair it first.")
        projected = build_resource_state(templates[0])
        projected["current"] = current
        if any(key not in projected or (key != "max"
                and json.dumps(value, sort_keys=True) != json.dumps(projected[key], sort_keys=True))
               for key, value in old[0].items()):
            raise CharacterBuildError("Advancement would lose retained resource details. Repair them first.")


def _retain_continuation_resource_templates(previous, templates, pool_ids):
    prior = {row.get("id"): row for row in previous}
    retained = deepcopy(templates)
    for row in retained:
        old = prior.get(row.get("id"))
        if old is not None and row.get("id") in pool_ids:
            maximum = row.get("max")
            row.update(deepcopy(old))
            row["max"] = maximum
            if "initial_current" not in old:
                row.pop("initial_current", None)
    return retained


def _derive_continuation_tracker_templates(
    definition, features, *, profile, ability_scores, current_level,
    state, state_revision, systems_service, campaign_page_records,
    verified_manual_actions=(), verified_numeric_actions=(),
):
    """Qualify the complete prospective owner frame before strict derivation.

    Missing links/templates are structural scratch only. Prior template bytes
    remain intact; no scratch capacity or initial count authorizes play state.
    """
    from .character_source_authority import (build_reconciled_source_authority,
        _current_systems_entry, _current_managed_pool_owners, _eligible_page_records)
    from .character_builder_progression import CharacterBuildError

    if not _activated_committed_character_mode():
        return _apply_tracker_templates_to_feature_payloads(features, ability_scores=ability_scores,
            current_level=current_level, class_row_levels=_profile_class_row_level_map(profile))
    from .character_feature_composition import retain_replacement_continuations
    rows = retain_replacement_continuations(
        definition, features, profile=profile, service=systems_service,
    )
    levels = _profile_class_row_level_map(profile)
    attained_owners = {}
    if isinstance(definition.source.get("native_reconstruction_choices"), dict):
        from .character_reconstruction_authority import attained_reconstruction_feature_owners
        planning = CharacterDefinition.from_dict({**definition.to_dict(), "profile": deepcopy(profile)})
        attained_owners = attained_reconstruction_feature_owners(planning, systems_service)
    # Expose registered generated children before qualification, so a direct
    # child source and a parent-derived citation cannot collide later unseen.
    for original in list(rows):
        if not dict(original.get("systems_ref") or {}).get("entry_key") or original.get("page_ref"):
            continue
        probe = deepcopy(original)
        family, member = _apply_managed_resource_member_defaults(probe)
        if family:
            children = _build_additional_feature_tracker_payloads(probe, ability_scores=ability_scores,
                current_level=_feature_tracker_current_level(probe, current_level=current_level, class_row_levels=levels),
                display_order=0, managed_resource_family=family, managed_resource_member=member,
                total_character_level=current_level)
            rows = _merge_generated_tracker_payloads(rows, [child for child, _ in children],
                attained_owners=attained_owners)
    affected_ids = _continuation_pool_ids(rows)
    if not affected_ids:
        try:
            return _apply_tracker_templates_to_feature_payloads(features, ability_scores=ability_scores,
                current_level=current_level, class_row_levels=levels)
        except ValueError as exc:
            raise CharacterBuildError(str(exc)) from exc
    if state is None or type(state_revision) is not int or systems_service is None:
        raise CharacterBuildError("Refresh the Character before deriving advancement resources.")
    templates = deepcopy(list(definition.resource_templates or []))
    ids = [str(row.get("id") or "").strip() for row in rows]
    template_ids = [str(row.get("id") or "").strip() for row in templates]
    if not all(ids) or len(set(ids)) != len(ids) or len(set(template_ids)) != len(template_ids):
        raise CharacterBuildError("Resource feature or template identity needs manager repair.")
    from .character_tracker_associations import qualified as qualified_trackers, physical_id
    tracker_bindings = qualified_trackers(definition, verified_numeric_actions)
    managed_ids = set()
    for row in rows:
        ref = dict(row.get("systems_ref") or {})
        if not ref.get("entry_key") or row.get("page_ref"):
            continue
        canonical = deepcopy(row)
        canonical["source"] = ref.get("source_id")
        family, member = resolve_managed_resource_family_and_member(canonical)
        tracker = dict((member or {}).get("tracker") or {})
        tracker_id = physical_id(member, canonical, tracker_bindings)
        if not family or tracker_id not in affected_ids:
            continue
        entry = _current_systems_entry(definition.campaign_slug, "systems", ref["entry_key"], systems_service)
        if (entry is None or any(str(ref.get(key) or "") != str(getattr(entry, key, ""))
                                for key in ("entry_key", "entry_type", "source_id", "slug"))
                or managed_resource_feature_identity(canonical) is None):
            raise CharacterBuildError("A managed resource source needs repair before advancement.")
        if row.get("tracker_ref") not in (None, "", tracker_id):
            raise CharacterBuildError("A managed resource tracker link needs repair before advancement.")
        row["tracker_ref"] = tracker_id
        managed_ids.add(tracker_id)
        if tracker_id not in template_ids:
            scratch = _build_managed_resource_tracker_template(
                member, canonical, ability_scores=ability_scores,
                current_level=_feature_tracker_current_level(row, current_level=current_level, class_row_levels=levels),
                display_order=len(templates), total_character_level=current_level,
            )
            if scratch is None:
                raise CharacterBuildError("A managed resource scaffold is unavailable.")
            scratch = deepcopy(scratch)
            scratch.pop("activation_type", None)
            scratch["class_row_id"] = row.get("class_row_id")
            templates.append(scratch)
            template_ids.append(tracker_id)
    payload = deepcopy(definition.to_dict())
    payload.update(profile=deepcopy(profile), features=rows, resource_templates=templates)
    candidate = CharacterDefinition.from_dict(payload)
    authority = build_reconciled_source_authority(
        definition=candidate, state=state, state_revision=state_revision,
        systems_service=systems_service, campaign_page_records=campaign_page_records,
        verified_manual_actions=verified_manual_actions, verified_numeric_actions=verified_numeric_actions,
    )
    # Repeat the existing structural qualifier over every owner, including a
    # canonical singleton (which needs no alias entry in SourceAuthority).
    pools = _current_managed_pool_owners(candidate, systems_service=systems_service,
        pages=_eligible_page_records(campaign_page_records),
        verified_class_rows=authority.verified_class_rows, feature_statuses=authority.statuses,
        tracker_bindings=authority.tracker_associations)
    if not managed_ids <= pools.keys():
        raise CharacterBuildError("Managed resource owner closure is incomplete or conflicting.")
    try:
        derived, derived_templates = authority.derive_managed_tracker_templates(
            candidate, rows, build_templates=_apply_tracker_templates_to_feature_payloads,
            ability_scores=ability_scores, current_level=current_level, class_row_levels=levels,
        )
    except ValueError as exc:
        raise CharacterBuildError(str(exc)) from exc
    prior_by_id = {row.get("id"): row for row in definition.resource_templates}
    retained = []
    for template in derived_templates:
        old = prior_by_id.get(template.get("id"))
        if old is not None and template.get("id") in managed_ids:
            # All historical metadata and bootstrap observations survive. Only
            # the independently derived capacity changes in this adapter.
            template = {**deepcopy(template), **deepcopy(old), "max": template.get("max")}
            if "initial_current" not in old:
                template.pop("initial_current", None)
        retained.append(template)
    return derived, retained

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
    template_owners: dict[str, dict[str, Any]] = {}
    activated = _activated_committed_character_mode()
    feature_payloads_by_identity: dict[tuple[str, str], dict[str, Any]] = {}
    for feature_payload in base_features:
        if activated and (
            _unproved_effective_feature(feature_payload)
            or blocks_page_companion_heuristics(feature_payload)
        ):
            # A derived tracker with the same display name cannot enrich a
            # suppressed history row or a proved page-choice projection.
            continue
        feature_identity = _tracker_feature_identity_key(feature_payload)
        if feature_identity[0]:
            if (managed_resource_feature_identity(feature_payload) is not None
                    and feature_identity in feature_payloads_by_identity):
                raise ValueError("A managed resource member has more than one feature owner.")
            feature_payloads_by_identity.setdefault(feature_identity, feature_payload)
    seen_feature_identities = set(feature_payloads_by_identity)
    display_order = 0

    def append_tracker_template(feature_payload: dict[str, Any], tracker_template: dict[str, Any]) -> None:
        nonlocal display_order
        template_tracker_id = str(tracker_template.get("id") or "").strip()
        tracker_id = str(feature_payload.get("tracker_ref") or "").strip() or template_tracker_id
        if tracker_id in template_owners and template_owners[tracker_id] is not feature_payload:
            raise ValueError("A managed resource tracker has more than one feature owner.")
        if tracker_id:
            template_owners[tracker_id] = feature_payload
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
        if activated and _unproved_effective_feature(feature_payload):
            # Keep the historical label in the effective view, but no raw
            # action or tracker can survive into a usable projection.
            feature_payload["activation_type"] = "passive"
            feature_payload.pop("tracker_ref", None)
            updated_features.append(feature_payload)
            continue
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
                total_character_level=current_level,
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
            total_character_level=current_level,
        ):
            feature_identity = _tracker_feature_identity_key(derived_feature_payload)
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
    total_character_level: int | None = None,
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
                total_character_level=total_character_level,
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
    *, preserve_observation_ids: set[str] | None = None,
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
            replacement = dict(new_by_id[template_id])
            if template_id in (preserve_observation_ids or set()):
                replacement = {**deepcopy(replacement), **deepcopy(template), "max": replacement.get("max")}
                if "initial_current" not in template:
                    replacement.pop("initial_current", None)
                merged.append(replacement)
                seen_ids.add(template_id)
                continue
            initial_current = template.get("initial_current")
            maximum = replacement.get("max")
            if (type(initial_current) is int and initial_current >= 0
                    and type(maximum) is int and maximum >= 0
                    and str(template.get("class_row_id") or "").strip()
                    == str(replacement.get("class_row_id") or "").strip()):
                # This is the historical bootstrap observation, not an instruction
                # to refill a pool when its source-derived maximum grows.
                replacement["initial_current"] = min(initial_current, maximum)
            merged.append(replacement)
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
        if blocks_page_companion_heuristics(feature):
            continue
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

def _activated_committed_character_mode() -> bool:
    if not has_app_context():
        return False
    from .committed_publication import active
    return active()


def _unproved_effective_feature(feature_payload: dict[str, Any]) -> bool:
    status = str(feature_payload.get("authority_status") or "").strip().upper()
    return bool(feature_payload.get("mechanics_suppressed") or status and status != "VERIFIED")


def _merge_legacy_detached_action_summary_features(
    normalized_features: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    activated = _activated_committed_character_mode()
    targets_by_description: dict[str, list[dict[str, Any]]] = {}
    for feature_payload in normalized_features:
        if _is_legacy_detached_action_summary_feature(feature_payload):
            continue
        if activated and (
            _unproved_effective_feature(feature_payload)
            or str(feature_payload.get("authority_status") or "").strip()
            or blocks_page_companion_heuristics(feature_payload)
        ):
            continue
        description_key = normalize_lookup(str(feature_payload.get("description_markdown") or ""))
        if description_key:
            targets_by_description.setdefault(description_key, []).append(feature_payload)

    compacted_features: list[dict[str, Any]] = []
    for feature_payload in normalized_features:
        if _is_legacy_detached_action_summary_feature(feature_payload):
            if activated and (
                _unproved_effective_feature(feature_payload)
                or str(feature_payload.get("authority_status") or "").strip()
            ):
                compacted_features.append(feature_payload)
                continue
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
    total_character_level: int | None = None,
) -> dict[str, Any] | None:
    return _build_managed_resource_tracker_template_impl(
        member,
        feature_payload,
        ability_scores=ability_scores,
        current_level=current_level,
        display_order=display_order,
        total_character_level=total_character_level,
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
    total_character_level: int | None = None,
) -> dict[str, Any] | None:
    return _build_feature_tracker_template_impl(
        feature_payload,
        ability_scores=ability_scores,
        current_level=current_level,
        display_order=display_order,
        managed_resource_member=managed_resource_member,
        feat_effect_keys_for_feature=_feat_effect_keys_for_feature,
        total_character_level=total_character_level,
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
