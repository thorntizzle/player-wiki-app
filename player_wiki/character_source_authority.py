"""Read-only, exact-link authority for one reconciled DND character projection.

Historical definition rows are evidence of a selection, never evidence that the
selected source is still available.  This module deliberately has no database
access: the caller supplies independently verified manager audit witnesses.
"""

from __future__ import annotations

from .character_catalog_operations import native_catalog, catalog_index, catalog_rows, catalog_field
from .character_read_foundation import build_read_spell_catalog, read_enabled_spell_entries


from copy import deepcopy
from collections import Counter
from dataclasses import dataclass, replace
import hashlib
import json
from typing import Any
from uuid import uuid4

from .campaign_item_mechanics import (
    campaign_item_mechanics_is_approved,
    is_campaign_item_mechanics_metadata,
)
from .character_campaign_options import build_campaign_page_character_option
from .character_models import CharacterDefinition
from .character_page_companion import is_page_choice_shape
from .character_profile import profile_class_rows
from .character_spell_effects import MISSING_OVERRIDE_AUTHORITY_KEY, VERIFIED_MISSING_OVERRIDE
from .system_policy import is_dnd_5e_system
from .character_armor_models import structural_selectors as _armor_structure


def _spell_entries_catalog(entries):
    return entries if native_catalog(entries) is not None else {"entries": entries}



_NATIVE_CHARACTER_TO_DICT = CharacterDefinition.to_dict


VERIFIED = "VERIFIED"
NEEDS_REPAIR = "NEEDS REPAIR"
NEEDS_ATTENTION = "NEEDS ATTENTION"
MANUAL = "MANUAL"
UNKNOWN = "UNKNOWN"
CONFLICT = "CONFLICT"
REPLACED = "REPLACED"


def _observed_list(value):
    """Opaque retained state is not a list of numeric owner observations."""
    return value if isinstance(value, list) else []


def _observed_pools(state):
    value = state.get("hit_dice")
    return _observed_list(value.get("pools")) if isinstance(value, dict) else []
_METRICS = frozenset({"availability", "spell_attack_bonus", "spell_save_dc"})
_ITEM_EFFECT_FIELDS = frozenset({
    "ability_score_minimums", "attack_reminder_rules", "bonus", "bonus_ac",
    "bonus_attack_rolls", "bonus_damage_rolls", "bonus_weapon",
    "bonus_weapon_attack", "bonus_weapon_damage", "weapon_extra_damage", "defensive_rules",
    "item_use_actions", "item_uses", "item_capabilities", "resource_template_bonuses",
    "spell_support", "spellcasting_modifiers", "spell_property_modifiers", "campaign_option",
})
_FEATURE_EFFECT_FIELDS = frozenset({
    "campaign_option", "spell_manager", "spell_source_authorization",
    "additional_spells", "spell_support", "mechanic_effects", "modeled_effects",
})
NATIVE_BASELINE_FIELDS = frozenset({
    "stats.armor_class", "stats.initiative_bonus", "stats.speed", "stats.passive_perception",
    "stats.passive_insight", "stats.passive_investigation",
    "stats.carrying_capacity", "stats.push_drag_lift",
})


def _unqualified_native_aggregate_adjustments(stats: dict[str, Any]) -> frozenset[str]:
    """Retain unsupported raw inputs even if normalization later drops them."""
    adjustments = stats.get("manual_adjustments", {})
    if not isinstance(adjustments, dict):
        return NATIVE_BASELINE_FIELDS
    allowed = {"max_hp", *(path.removeprefix("stats.") for path in NATIVE_BASELINE_FIELDS)}
    if any(key not in allowed for key in adjustments):
        return NATIVE_BASELINE_FIELDS
    return frozenset(path for path in NATIVE_BASELINE_FIELDS
                     if type(adjustments.get(path.removeprefix("stats."), 0)) is not int
                     or adjustments.get(path.removeprefix("stats."), 0) != 0)


class NativeAdvancementValidationError(ValueError):
    """A native producer failed validation before any publication was attempted."""


@dataclass(frozen=True, slots=True)
class NativeAdvancementIntent:
    """Request-local result of the strict builder, never a submitted witness."""

    prior_digest: str
    candidate_digest: str
    candidate_without_authorizations_digest: str
    restored_resource_currents: tuple[tuple[str, int], ...] = ()
    ability_inputs_json: str = ""
    retained_import_digest: str | None = None

    @classmethod
    def from_validated(cls, prior_definition, candidate_definition, *, restored_resource_currents=(),
                       retained_import_metadata=None):
        from .character_equipment_activation import definition_digest

        prior_rows = profile_class_rows(prior_definition.profile)
        rows = profile_class_rows(candidate_definition.profile)
        if not rows or any(type(row.get("level")) is not int or row["level"] < 1
                           for row in [*prior_rows, *rows]):
            raise NativeAdvancementValidationError("This advancement could not be validated. Review its choices.")
        prior_level = sum(row.get("level", 0) for row in prior_rows)
        level = sum(row.get("level", 0) for row in rows)
        if (level != prior_level + 1 or level > 20
                or candidate_definition.stats.get("proficiency_bonus") != 2 + (level - 1) // 4):
            raise NativeAdvancementValidationError("This advancement could not be validated. Review its choices.")
        if (not isinstance(restored_resource_currents, tuple)
                or any(not isinstance(row, tuple) or len(row) != 2
                       or not isinstance(row[0], str) or not row[0] or type(row[1]) is not int
                       for row in restored_resource_currents)
                or len({row[0] for row in restored_resource_currents}) != len(restored_resource_currents)):
            raise NativeAdvancementValidationError("This restoration could not be validated. Review its choices.")
        for tracker_id, current in restored_resource_currents:
            old = [row for row in prior_definition.resource_templates if row.get("id") == tracker_id]
            new = [row for row in candidate_definition.resource_templates if row.get("id") == tracker_id]
            if (old or len(new) != 1 or type(new[0].get("max")) is not int
                    or not 0 <= current <= new[0]["max"] or new[0].get("initial_current") != current):
                raise NativeAdvancementValidationError("This restoration could not be validated. Review its choices.")
        prior_progression = prior_definition.source.get("native_progression")
        progression = candidate_definition.source.get("native_progression")
        prior_history = prior_progression.get("history", []) if type(prior_progression) is dict else None
        history = progression.get("history", []) if type(progression) is dict else None
        recorded = (type(prior_history) is list and type(history) is list and len(history) == len(prior_history) + 1
                    and type(history[-1]) is dict and "recorded_advancement" in history[-1])
        retained_import_digest = None
        if recorded or retained_import_metadata is not None:
            from .character_models import CharacterImportMetadata
            from .character_recorded_advancement import parse_recorded
            if (not recorded or history[:-1] != prior_history
                    or type(retained_import_metadata) is not CharacterImportMetadata):
                raise NativeAdvancementValidationError("The completed advancement lost its retained import metadata.")
            note = history[-1]["recorded_advancement"]
            if (type(note) is not dict or set(note) != {"schema_version", "kind", "evidence"}
                    or type(note["schema_version"]) is not int or note["schema_version"] != 1
                    or note["kind"] != "completed_whole_hp"):
                raise NativeAdvancementValidationError("The completed advancement evidence is malformed.")
            parse_recorded({"advancement_record_type": "completed", "advancement_recorded_at": history[-1].get("at"),
                            "advancement_evidence": note["evidence"]}, allowed=True)
            retained_import_digest = numeric_value_digest(retained_import_metadata.to_dict())
        payload = deepcopy(candidate_definition.to_dict())
        payload["source"].pop("source_authorizations", None)
        return cls(definition_digest(prior_definition), definition_digest(candidate_definition),
                   definition_digest(CharacterDefinition.from_dict(payload)), restored_resource_currents,
                   _canonical(candidate_definition.stats.get("ability_inputs")), retained_import_digest)

    def matches(self, prior_definition, candidate_definition):
        from .character_equipment_activation import definition_digest

        return (self.prior_digest == definition_digest(prior_definition)
                and self.candidate_digest == definition_digest(candidate_definition))

    def matches_resource_readback(self, prior_definition, candidate_definition):
        from .character_equipment_activation import definition_digest
        payload = deepcopy(candidate_definition.to_dict())
        payload["source"].pop("source_authorizations", None)
        return (self.prior_digest == definition_digest(prior_definition)
                and self.candidate_without_authorizations_digest
                == definition_digest(CharacterDefinition.from_dict(payload)))


def native_baseline_target(kind: str, path: str, metric: str) -> bool:
    return isinstance(path, str) and ((kind == "field" and metric == "final" and path in NATIVE_BASELINE_FIELDS) or (
        kind == "proficiency" and metric == "grant"
        and path.startswith(("skills.", "proficiencies."))))


def native_advancement_input_target(kind: str, path: str, metric: str) -> bool:
    """Explicit ability inputs and class-level PB renewed by the strict producer."""
    return (kind == "field" and metric == "base" and path in {
        f"stats.ability_scores.{ability}.score"
        for ability in ("str", "dex", "con", "int", "wis", "cha")
    }) or (kind, path, metric) == ("field", "stats.proficiency_bonus", "final")


def _native_baseline_bases(definition, state, *, systems_service, statuses,
                           verified_class_rows, source_snapshot_digest, pages, feature_composition=None):
    """Bind native producer attestations to current owners and target inputs.

    These digests grant nothing without an independently confirmed create or
    level-up audit witness. Current/spent values and user notes are excluded.
    """
    active_items = {row.get("id") for row in definition.equipment_catalog
                    if isinstance(row, dict) and row.get("is_equipped")}
    reconstructed = isinstance(dict(definition.source or {}).get("native_reconstruction_choices"), dict)
    if (dict(definition.source or {}).get("source_type") != "native_character_builder"
            or not source_snapshot_digest
            or any(row.status != VERIFIED for row in statuses if row.kind != "item"
                   and not (row.kind == "feature" and (reconstructed or row.status == REPLACED
                       and feature_composition is not None and feature_composition.matches_definition(definition)
                       and row.instance_id in feature_composition.replaced_ids)))
            or {row.get("row_id") for row in profile_class_rows(definition.profile)}
               != set(verified_class_rows)):
        return {}
    profile = dict(definition.profile or {})
    sources = []
    for subject, types in (("species", {"race", "subrace"}), ("background", {"background"})):
        ref = profile.get(f"{subject}_ref")
        if not isinstance(ref, dict) or not ref or profile.get(f"{subject}_page_ref"):
            return {}
        kind, key = _source_identity({"systems_ref": ref})
        entry = _current_systems_entry(definition.campaign_slug, kind, key, systems_service)
        if (entry is None or entry.entry_type not in types
                or any(ref.get(field) and ref[field] != getattr(entry, field, None)
                       for field in ("entry_key", "slug", "source_id", "entry_type", "title", "library_slug"))):
            return {}
        sources.append({"ref": ref, "metadata": entry.metadata, "body": entry.body})
    # Builder/read facades carry different cache-subset decorations. Their
    # durable Systems revision is the same semantic source identity.
    revision_loader = getattr(systems_service, "get_durable_revision", None)
    revision = revision_loader() if callable(revision_loader) else None
    if not isinstance(revision, str) or not revision:
        return {}
    linked_pages = {_source_identity(row)[1] for row in definition.features
                    if isinstance(row, dict) and _source_identity(row)[0] == "page"}
    page_inputs = [{
        "ref": ref,
        "section": _field(_field(record, "page"), "section"),
        "published": _field(_field(record, "page"), "published"),
        "reveal_after_session": _field(_field(record, "page"), "reveal_after_session"),
        "updated_at": _text(_field(record, "updated_at")),
        "committed_revision": _field(_field(record, "page"), "committed_revision"),
        "metadata": _field(record, "metadata"),
    } for ref in sorted(linked_pages) for record in pages.get(ref, [])]
    context = {"systems_revision": revision, "sources": sources,
               "classes": profile.get("classes"),
               "features": definition.features, "pages": page_inputs,
               "ability_inputs": dict(definition.stats or {}).get("ability_inputs")}
    if definition.source.get("native_feature_proficiency_choices"):
        context["feature_proficiency_acquisitions"] = deepcopy(definition.source["native_feature_proficiency_choices"])
    from .character_language_choices import current_parent_languages, PARENT_FRAME
    parent_language_invalid = False
    if not reconstructed and (PARENT_FRAME in definition.source or any(
            isinstance(block, dict) and "ifAlreadyProficient" in block
            for block in sources[1]["metadata"].get("language_proficiencies") or [])):
        try:
            current_parent_languages(definition, systems_service)
        except (ValueError, TypeError, KeyError):
            parent_language_invalid = True
    if PARENT_FRAME in definition.source:
        context["parent_language_acquisitions"] = deepcopy(definition.source[PARENT_FRAME])
    if reconstructed:
        context.pop("systems_revision")
        owners = {}
        refs = [row.get(field) for row in profile_class_rows(profile)
                for field in ("systems_ref", "subclass_ref")]
        refs += [row.get("systems_ref") for row in definition.features if isinstance(row, dict)]
        for ref in refs:
            if not isinstance(ref, dict) or not ref.get("entry_key"):
                continue
            entry = _current_systems_entry(definition.campaign_slug, "systems", ref["entry_key"], systems_service)
            owners[ref["entry_key"]] = ({"metadata": entry.metadata, "body": entry.body}
                                        if entry is not None else None)
        context["linked_current_owners"] = owners
    item_inputs = []
    for row in definition.equipment_catalog:
        if not isinstance(row, dict):
            continue
        source_kind, source_key = _source_identity(row)
        current, _ = _current_payload(
            campaign_slug=definition.campaign_slug, kind="item",
            source_kind=source_kind, source_key=source_key, systems_service=systems_service,
            pages=pages, expected_ref=dict(row.get("systems_ref") or {}),
        )
        item_inputs.append((row, current or {}))
    equipment_qualified = all(row.status == VERIFIED for row in statuses
                             if row.kind == "item" and row.instance_id in active_items)
    ability_dependencies = {
        # Supported initiative effects may add any feature-selected ability.
        "stats.initiative_bonus": {"str", "dex", "con", "int", "wis", "cha"},
        "stats.passive_perception": {"wis"}, "stats.passive_insight": {"wis"},
        "stats.passive_investigation": {"int"},
        "stats.carrying_capacity": {"str"}, "stats.push_drag_lift": {"str"},
    }
    result = {}
    for (kind, path, metric), value in numeric_target_values(definition, state).items():
        if parent_language_invalid and kind == "proficiency" and path.startswith("proficiencies.languages."):
            continue
        if (not (native_baseline_target(kind, path, metric)
                 or native_advancement_input_target(kind, path, metric))
                or value is None):
            continue
        inputs = dict(context)
        if kind == "field":
            if not equipment_qualified:
                continue
            # A skill/proficiency marker proves a choice, not an equipment total.
            # Other fields depend only on gear mechanics that can affect them.
            if path == "stats.armor_class":
                inputs["equipment"] = definition.equipment_catalog
            else:
                abilities = ability_dependencies.get(path, set())
                inputs["equipment"] = [row for row, current in item_inputs if (
                    abilities & set(dict(current.get("ability_score_minimums") or {}))
                    or dict(dict(current.get("campaign_option") or {}).get("stat_adjustments") or {}).get(
                        path.removeprefix("stats."))
                )]
            if reconstructed:
                selected = {row.get("id") for row in inputs["equipment"]}
                inputs["equipment_sources"] = {row.get("id"): current for row, current in item_inputs
                                               if row.get("id") in selected}
        result[path] = numeric_value_digest({"inputs": inputs, "kind": kind,
                                            "path": path, "value": value})
    return result


def _field(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, dict) else getattr(value, key, None)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _page_ref(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("page_ref") or value.get("slug") or value.get("page_slug")
    return _text(value).replace("\\", "/").strip("/").removesuffix(".md").casefold()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _numeric_witness_identity(witness: dict[str, Any]) -> str:
    from .character_source_repair import NativeAggregateWitness, NativeSpellChoiceDecision
    from .character_spell_reconstruction import NativeSpellReconstructionFact
    from .character_language_electives import NativeElectiveDecision, PendingElectiveOutcome
    from .character_external_proficiencies import ExternalProficiencyCustody
    if type(witness) is ExternalProficiencyCustody:
        return _canonical({"witness": dict(witness), "external_proficiency_origin": witness.origin})
    if type(witness) in (NativeElectiveDecision, PendingElectiveOutcome):
        return _canonical({"witness": dict(witness), "elective_decision_type": type(witness).__name__,
            "elective_decision_origin": witness.origin})
    if type(witness) is NativeSpellChoiceDecision:
        return _canonical({"witness": dict(witness), "spell_choice_origin": witness.origin})
    if type(witness) is NativeSpellReconstructionFact:
        return _canonical({"witness": dict(witness), "spell_reconstruction_origin": witness.origin})
    return _canonical({"witness": dict(witness), "native_aggregate_origin": witness.origin}
                      if isinstance(witness, NativeAggregateWitness) else witness)


def _source_identity(row: dict[str, Any]) -> tuple[str, str]:
    ref = row.get("systems_ref")
    if isinstance(ref, dict):
        key = _text(ref.get("entry_key"))
        if key:
            return "systems", key
        slug = _text(ref.get("slug"))
        if slug:
            return "systems_slug", slug
    page = _page_ref(row.get("page_ref"))
    return ("page", page) if page else ("", "")


def _current_systems_entry(
    campaign_slug: str, source_kind: str, source_key: str, systems_service: Any,
) -> Any | None:
    if systems_service is None:
        return None
    if source_kind == "systems":
        getter = getattr(systems_service, "get_entry_for_campaign", None)
    else:
        getter = getattr(systems_service, "get_entry_by_slug_for_campaign", None)
    if not callable(getter):
        return None
    entry = getter(campaign_slug, source_key)
    if entry is None:
        return None
    enabled = getattr(systems_service, "is_entry_enabled_for_campaign", None)
    if not callable(enabled) or not enabled(campaign_slug, entry):
        return None
    actual = _text(getattr(entry, "entry_key" if source_kind == "systems" else "slug", ""))
    return entry if actual == source_key else None


def _eligible_page_records(records: list[Any] | None) -> dict[str, list[Any]]:
    eligible_sections = {"Mechanics", "Items", "Spells"}
    result: dict[str, list[Any]] = {}
    for record in list(records or []):
        page = _field(record, "page")
        if (not bool(_field(page, "published"))
                or _text(_field(page, "section")) not in eligible_sections):
            continue
        ref = _page_ref(_field(record, "page_ref") or _field(page, "route_slug"))
        if ref:
            result.setdefault(ref, []).append(record)
    return result


def _current_payload(
    *, campaign_slug: str, kind: str, source_kind: str, source_key: str,
    systems_service: Any, pages: dict[str, list[Any]], expected_slug: str = "",
    expected_ref: dict[str, Any] | None = None,
    expected_feature: dict[str, Any] | None = None,
    expected_profile: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str]:
    if kind == "item" and not source_kind.startswith("systems"):
        return None, "exact Systems item link missing"
    if source_kind.startswith("systems"):
        entry = _current_systems_entry(campaign_slug, source_kind, source_key, systems_service)
        if entry is None:
            return None, "source unavailable"
        if expected_slug and _text(getattr(entry, "slug", "")) != expected_slug:
            return None, "source identity changed"
        if kind == "feature" and expected_feature is not None:
            from .divine_avatar_forms import _declares_divine_avatar_feature, _avatar_feature_source
            if _declares_divine_avatar_feature(expected_feature):
                if _avatar_feature_source(expected_feature) != (source_kind, source_key):
                    return None, "source identity changed"
                ref = expected_feature["systems_ref"]
                for field in ("entry_key", "slug", "source_id", "entry_type", "title", "library_slug"):
                    value = ref.get(field)
                    if value is None or type(value) is str and not value.strip():
                        continue
                    actual = getattr(entry, field, None)
                    if type(value) is not str or type(actual) is not str:
                        return None, "source identity changed"
                    if (value.strip().casefold() != actual.strip().casefold() if field == "title"
                            else value.strip() != actual.strip()):
                        return None, "source identity changed"
                if _text(getattr(entry, "entry_type", "")) not in {
                        "feature", "feat", "optionalfeature", "classfeature", "subclassfeature"}:
                    return None, "source kind changed"
        if kind == "item":
            ref = dict(expected_ref or {})
            for field in ("entry_key", "slug", "source_id", "entry_type"):
                if _text(ref.get(field)) and _text(ref.get(field)) != _text(getattr(entry, field, "")):
                    return None, "source identity changed"
            if _text(ref.get("title")) and _text(ref.get("title")).casefold() != _text(getattr(entry, "title", "")).casefold():
                return None, "source identity changed"
        entry_type = _text(getattr(entry, "entry_type", ""))
        if kind == "item" and entry_type != "item":
            return None, "source kind changed"
        if kind == "spell" and entry_type != "spell":
            return None, "source kind changed"
        if kind == "class" and entry_type != "class":
            return None, "source kind changed"
        if kind == "feature" and entry_type not in {"feature", "feat", "optionalfeature", "classfeature", "subclassfeature"}:
            from .character_subclass_companion import selected_subclass_companion_matches
            if entry_type == "subclass" and selected_subclass_companion_matches(
                    expected_feature, expected_profile, entry, systems_service, campaign_slug):
                return {}, ""  # Exact inert container; its metadata grants no effects.
            from .character_background_companion import systems_background_companion_matches
            if not systems_background_companion_matches(expected_feature, expected_profile, entry):
                return None, "source kind changed"
            # The selected background certifies this exact narrative projection,
            # never arbitrary mechanics copied from its parent metadata.
            return {}, ""
        metadata = deepcopy(dict(getattr(entry, "metadata", {}) or {}))
        if is_campaign_item_mechanics_metadata(metadata) and not campaign_item_mechanics_is_approved(metadata):
            return None, "source needs review"
        return metadata, ""
    if source_kind != "page":
        return None, "exact source link missing"
    matches = pages.get(source_key) or []
    if len(matches) != 1:
        return None, "source unavailable or ambiguous"
    record = matches[0]
    page = _field(record, "page")
    section = _text(_field(page, "section"))
    if (kind == "item" and section != "Items") or (
        kind == "feature" and section != "Mechanics"
    ) or (kind == "spell" and section not in {"Mechanics", "Spells"}
    ):
        return None, "source kind changed"
    metadata = deepcopy(dict(_field(record, "metadata") or {}))
    if kind == "item":
        if not is_campaign_item_mechanics_metadata(metadata) or not campaign_item_mechanics_is_approved(metadata):
            return None, "source needs review"
        return metadata, ""
    if kind == "spell":
        return metadata, ""
    option = build_campaign_page_character_option(record, default_kind="feature")
    if not isinstance(option, dict):
        return None, "source mechanics unavailable"
    return {"campaign_option": option}, ""


def valid_manual_authorization(
    record: Any, *, character_slug: str, target_kind: str,
    target_id: str, metric: str, definition: CharacterDefinition,
    verified_manual_actions: tuple[Any, ...] = (),
) -> bool:
    """A definition marker alone never authorizes manual mechanics."""
    if not isinstance(record, dict) or metric not in _METRICS:
        return False
    required = {
        "schema_version", "character_slug", "target_kind", "target_id",
        "metric", "action_id", "provenance", "target_digest",
    }
    if set(record) != required or type(record.get("schema_version")) is not int or record["schema_version"] != 2:
        return False
    if record.get("provenance") != "manager" or record.get("target_kind") not in {"spell", "source_row"}:
        return False
    if any(not isinstance(record.get(key), str) or not record[key].strip() for key in required - {"schema_version"}):
        return False
    if (record["character_slug"], record["target_kind"], record["target_id"], record["metric"]) != (
        character_slug, target_kind, target_id, metric,
    ):
        return False
    if record["target_digest"] != manual_target_digest(definition, target_kind, target_id):
        return False
    marker = _canonical(record)
    return any(
        witness == marker if isinstance(witness, str)
        else isinstance(witness, dict) and witness == record
        for witness in verified_manual_actions
    )


_NUMERIC_AUTHORIZATION_FIELDS = frozenset({
    "schema_version", "character_slug", "target_kind", "target_id",
    "metric", "value_digest", "action_id", "provenance",
})


def manual_target_digest(definition: CharacterDefinition, target_kind: str, target_id: str) -> str | None:
    """Bind a manager decision to one exact row and its linked owner row."""
    spellcasting = dict(definition.spellcasting or {})
    rows = list(spellcasting.get("spells" if target_kind == "spell" else "source_rows") or [])
    id_key = "id" if target_kind == "spell" else "source_row_id"
    matches = [row for row in rows if isinstance(row, dict) and _text(row.get(id_key)) == target_id]
    if len(matches) != 1:
        return None
    target = matches[0]
    if target_kind == "spell":
        row_id = _text(target.get("spell_source_row_id"))
        class_id = _text(target.get("class_row_id"))
        owner_rows = [row for row in list(spellcasting.get("source_rows") or [])
                      if isinstance(row, dict) and _text(row.get("source_row_id")) == row_id] if row_id else []
        owner_rows += [row for row in list(spellcasting.get("class_rows") or [])
                       if isinstance(row, dict) and _text(row.get("class_row_id")) == class_id] if class_id else []
    else:
        owner_rows = [row for row in list(spellcasting.get("spells") or [])
                      if isinstance(row, dict) and _text(row.get("spell_source_row_id")) == target_id]
        row_id = target_id
    linked_instances = [
        {"kind": kind, "id": row.get("id"), "systems_ref": row.get("systems_ref"),
         "page_ref": row.get("page_ref"), "campaign_option": row.get("campaign_option")}
        for kind, rows in (("feature", definition.features), ("item", definition.equipment_catalog))
        for row in list(rows or []) if isinstance(row, dict) and row_id in _source_row_ids(row)
    ]
    return numeric_value_digest({"target": target, "owner_rows": owner_rows,
                                 "linked_instances": linked_instances})


def numeric_target_owner_digest(
    definition: CharacterDefinition, state: dict[str, Any],
    target_kind: str, target_id: str, metric: str,
) -> str | None:
    values = numeric_target_values(definition, state)
    key = (target_kind, target_id, metric)
    if key not in values:
        return None
    return _numeric_owner_digest_from_inputs(
        values, definition.to_dict(), target_kind, target_id, metric,
    )


def _numeric_owner_digest_from_inputs(values, payload, target_kind, target_id, metric):
    """Hash exact private input content; never classify or trust an owner."""
    key = (target_kind, target_id, metric)
    stats = dict(payload.get("stats") or {})
    context: dict[str, Any] = {"target": values[key], "kind": target_kind,
                               "path": target_id, "metric": metric}
    if target_kind == "field":
        context["stats"] = stats.get(target_id.removeprefix("stats."))
        if target_id.startswith("stats.ability_scores."):
            ability = target_id.split(".")[2]
            context["ability"] = dict(stats.get("ability_scores") or {}).get(ability)
            context["input"] = dict(dict(stats.get("ability_inputs") or {}).get("scores") or {}).get(ability)
        if target_id in {"stats.max_hp", "stats.proficiency_bonus"}:
            context["classes"] = dict(payload.get("profile") or {}).get("classes")
            context["progression"] = dict(payload.get("source") or {}).get("native_progression")
    elif target_kind == "proficiency":
        context["classes"] = dict(payload.get("profile") or {}).get("classes")
        context["features"] = [(row.get("id"), row.get("systems_ref"), row.get("page_ref"))
                               for row in list(payload.get("features") or []) if isinstance(row, dict)]
    elif target_kind == "resource":
        context["classes"] = dict(payload.get("profile") or {}).get("classes")
        if target_id.startswith("resource:"):
            template_id = target_id.removeprefix("resource:")
            # A resource witness belongs to the exact linked feature and class
            # row. Unrelated feature edits do not invalidate this witness.
            context["owner_features"] = [row for row in list(payload.get("features") or [])
                                         if isinstance(row, dict)
                                         and _text(row.get("tracker_ref")) == template_id]
        else:
            context["features"] = [(row.get("id"), row.get("systems_ref"), row.get("page_ref"),
                                    row.get("campaign_option")) for row in list(payload.get("features") or [])
                                   if isinstance(row, dict)]
    return numeric_value_digest(context)


def _plain_preparation_data(value):
    """Bound a read-only built-in graph; custom protocols retain the old path."""
    pending = [(value, 0, False)]
    active, complete = set(), set()
    visited = 0
    while pending:
        item, depth, leaving = pending.pop()
        if not leaving:
            visited += 1
            if visited > 32768:
                return False
        kind = type(item)
        if (item is None or kind is str or kind is bytes or kind is bool
                or kind is int or kind is float):
            continue
        if (kind is not dict and kind is not list and kind is not tuple) or depth > 64:
            return False
        identity = id(item)
        if leaving:
            active.remove(identity)
            complete.add(identity)
            continue
        if identity in active:
            return False
        if identity in complete:
            continue
        if len(item) > 32768:
            return False
        active.add(identity)
        pending.append((item, depth, True))
        if kind is dict:
            if any(type(key) is not str for key in item):
                return False
            pending.extend((child, depth + 1, False) for child in item.values())
        else:
            pending.extend((child, depth + 1, False) for child in item)
    return True


def _plain_numeric_witness_data(witnesses):
    """Check exact envelopes and bound data before any recursive comparison."""
    if type(witnesses) is not tuple or len(witnesses) > 32768:
        return False
    from .character_source_repair import NativeAggregateWitness, NativeSpellChoiceDecision
    from .character_spell_grants import NativeGrantCustody
    from .character_spell_reconstruction import NativeSpellReconstructionFact
    from .character_language_electives import NativeElectiveDecision, PendingElectiveOutcome
    from .character_external_proficiencies import ExternalProficiencyCustody
    supported = (NativeAggregateWitness, NativeSpellChoiceDecision, NativeGrantCustody,
                 NativeSpellReconstructionFact, NativeElectiveDecision, PendingElectiveOutcome,
                 ExternalProficiencyCustody)
    data = []
    remaining = 32768
    for witness in witnesses:
        kind = type(witness)
        if kind is not dict and not any(kind is wrapper for wrapper in supported):
            return False
        remaining -= dict.__len__(witness) + 3
        if remaining < 0:
            return False
        origin = None
        if kind is not dict:
            try:
                attributes = object.__getattribute__(witness, "__dict__")
            except AttributeError:
                return False
            if type(attributes) is not dict or len(attributes) != 1:
                return False
            key = next(iter(attributes))
            if type(key) is not str or key != "origin":
                return False
            origin = attributes[key]
        # Exact stock dict types only; neither operation traverses descendants.
        data.append((dict.copy(witness), origin))
    return _plain_preparation_data(tuple(data))


def numeric_value_digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def numeric_target_values(
    definition: CharacterDefinition, state: dict[str, Any],
) -> dict[tuple[str, str, str], Any]:
    """Exact raw values bound by v2 manager/native audit witnesses.

    A missing key is unowned. Callers must reject duplicate target IDs before
    issuing a witness; a dict lookup cannot resolve an ownership collision.
    """
    values: dict[tuple[str, str, str], Any] = {}
    stats = dict(definition.stats or {})
    abilities = dict(stats.get("ability_scores") or {})
    inputs = dict(dict(stats.get("ability_inputs") or {}).get("scores") or {})
    for key, label in (("str", "strength"), ("dex", "dexterity"),
                       ("con", "constitution"), ("int", "intelligence"),
                       ("wis", "wisdom"), ("cha", "charisma")):
        row = dict(abilities.get(key) or abilities.get(label) or {})
        score_path = f"stats.ability_scores.{key}.score"
        if (isinstance(inputs.get(key), dict)
                and inputs[key].get("stage") in {"base", "pre_penalty"}
                and type(inputs[key].get("score")) is int):
            values[("field", score_path, "base")] = deepcopy(inputs[key])
        for metric in ("score", "modifier", "save_bonus"):
            values[("field", f"stats.ability_scores.{key}.{metric}", "final")] = row.get(metric)
    for key in ("proficiency_bonus", "max_hp", "armor_class", "initiative_bonus",
                "speed", "passive_perception", "passive_insight",
                "passive_investigation", "carrying_capacity", "push_drag_lift"):
        values[("field", f"stats.{key}", "final")] = stats.get(key)
    for row in list(definition.skills or []):
        if isinstance(row, dict) and _text(row.get("name")):
            values[("proficiency", f"skills.{_text(row['name']).casefold()}", "grant")] = deepcopy(row)
    for kind, rows in dict(definition.proficiencies or {}).items():
        for value in list(rows or []):
            if _text(value):
                values[("proficiency", f"proficiencies.{kind}.{_text(value).casefold()}", "grant")] = value
    withheld_resources = set(dict(definition.source or {}).get(
        "item_transition_withheld_resources") or [])
    resource_state = _observed_list(state.get("resources"))
    for row in list(definition.resource_templates or []):
        if isinstance(row, dict) and _text(row.get("id")):
            resource_id = _text(row["id"])
            if resource_id in withheld_resources:
                matches = [current for current in resource_state
                           if isinstance(current, dict)
                           and _text(current.get("id")) == resource_id]
                if (len(matches) == 1 and row.get("max") is None
                        and row.get("initial_current") is None
                        and row.get("authority_status") == NEEDS_REPAIR
                        and matches[0].get("max") is None
                        and matches[0].get("current") is None
                        and _text(matches[0].get("authority_status")).casefold()
                        == NEEDS_REPAIR.casefold()):
                    # Exact publication retirement keeps the row for repair,
                    # but it is no longer a current numeric proof target.
                    continue
            values[("resource", f"resource:{_text(row['id'])}", "owner_reset")] = deepcopy(row)
    for row in _observed_list(state.get("spell_slots")):
        if isinstance(row, dict) and type(row.get("level")) is int and row["level"] > 0:
            stable_id = f"{_text(row.get('slot_lane_id'))}:{row['level']}"
            values[("resource", f"spell_slot:{stable_id}", "owner_reset")] = {
                "slot_lane_id": _text(row.get("slot_lane_id")),
                "level": row["level"], "max": row.get("max"),
            }
    for row in _observed_pools(state):
        if isinstance(row, dict) and type(row.get("faces")) is int and row["faces"] > 0:
            values[("resource", f"hit_die:{row['faces']}", "owner_reset")] = {
                "faces": row["faces"], "max": row.get("max"),
            }
    spellcasting = dict(definition.spellcasting or {})
    for row in list(spellcasting.get("spells") or []):
        if (isinstance(row, dict) and _text(row.get("id"))
                and _text(row.get("class_row_id")) and not _text(row.get("spell_source_row_id"))):
            values[("spell_choice", f"spell_choice:{_text(row['id'])}", "selection")] = deepcopy(row)
    for family, id_key in (("class", "class_row_id"), ("source", "source_row_id")):
        for row in list(spellcasting.get(f"{family}_rows") or []):
            if not isinstance(row, dict) or not _text(row.get(id_key)):
                continue
            for formula_metric in ("spell_attack_bonus", "spell_save_dc"):
                target_id = f"spell_metric:{family}:{_text(row[id_key])}:{formula_metric}"
                values[("spell_metric", target_id, "formula")] = {
                    "value": row.get(formula_metric), "ability": row.get("spellcasting_ability"),
                    "source": row.get("class_ref") if family == "class" else row.get("source_ref"),
                    "row_id": row.get(id_key),
                }
    return values


def valid_numeric_authorization(
    record: Any, *, character_slug: str, target_kind: str,
    target_id: str, metric: str, raw_value: Any,
    owner_digest: str | None = None,
    verified_actions: tuple[Any, ...] = (),
) -> bool:
    """A v2 marker is effective only with its exact trusted audit witness."""
    if not isinstance(record, dict):
        return False
    is_manager = record.get("provenance") == "manager"
    is_page_feature = record.get("provenance") == "page_feature_update"
    required = _NUMERIC_AUTHORIZATION_FIELDS | (
        {"owner_digest"} if is_manager else
        {"owner_digest", "source_basis_digest", "page_ref", "page_revision",
         "feature_id", "source_snapshot_digest", "operation_digest", "config_revision",
         "initial_value"} if is_page_feature else set()
    )
    if set(record) != required:
        return False
    if type(record.get("schema_version")) is not int or record["schema_version"] != (
        3 if is_manager else 4 if is_page_feature else 2
    ):
        return False
    if record.get("target_kind") not in {"field", "proficiency", "resource", "spell_metric", "spell_choice"}:
        return False
    if record.get("metric") not in {"base", "final", "adjustment", "grant", "owner_reset", "formula", "selection"}:
        return False
    if record.get("target_kind") == "spell_metric" and (
        is_manager or record.get("metric") != "formula"
    ):
        return False
    if record.get("target_kind") == "spell_choice" and (is_manager or record.get("metric") != "selection"):
        return False
    if record.get("provenance") == "native_spell_choice" and record.get("target_kind") != "spell_choice":
        return False
    if record.get("provenance") == "native_elective_decision" and not (
            record.get("target_kind") == "proficiency" and record.get("metric") == "grant"
            and type(record.get("target_id")) is str and record["target_id"].startswith("proficiencies.languages.")):
        return False
    if record.get("provenance") == "native_external_proficiency" and not (
            record.get("target_kind") == "proficiency" and record.get("metric") == "grant"
            and type(record.get("target_id")) is str
            and record["target_id"].startswith(("proficiencies.tools.", "proficiencies.languages."))):
        return False
    if record.get("provenance") not in {"manager", "native_creation", "native_level_up", "native_spell_choice", "page_feature_update", "native_reconstruction", "native_requalification", "native_elective_decision", "native_external_proficiency"}:
        return False
    if is_page_feature and (
        target_kind != "resource" or metric != "owner_reset"
        or not target_id.startswith("resource:campaign-option-tracker:")
        or type(record.get("page_revision")) is not int or record["page_revision"] < 1
        or type(record.get("config_revision")) is not int or record["config_revision"] < 1
        or type(record.get("initial_value")) is not int or record["initial_value"] < 0
        or not isinstance(raw_value, dict)
        or record.get("initial_value") != raw_value.get("initial_current")
        or record.get("initial_value") != raw_value.get("max")
        or record.get("operation_digest") != record.get("action_id")
        or target_id != f"resource:campaign-option-tracker:{record.get('feature_id')}"
        or any(not isinstance(record.get(key), str) or len(record[key]) != 64
               for key in ("owner_digest", "source_basis_digest", "source_snapshot_digest", "operation_digest"))
        or not isinstance(record.get("page_ref"), str) or not record["page_ref"]
        or not isinstance(record.get("feature_id"), str) or not record["feature_id"]
    ):
        return False
    if any(not isinstance(record.get(key), str) or not record[key].strip()
           for key in _NUMERIC_AUTHORIZATION_FIELDS - {"schema_version"}):
        return False
    if (record["character_slug"], record["target_kind"], record["target_id"], record["metric"]) != (
        character_slug, target_kind, target_id, metric,
    ):
        return False
    if record["value_digest"] != numeric_value_digest(raw_value):
        return False
    if (is_manager or is_page_feature) and (owner_digest is None or record.get("owner_digest") != owner_digest):
        return False
    marker = _canonical(record)
    return any(
        witness == marker if isinstance(witness, str)
        else isinstance(witness, dict) and witness == record
        for witness in verified_actions
    )


@dataclass(frozen=True, slots=True)
class AuthorityGrant:
    kind: str
    instance_id: str
    source_kind: str
    source_key: str
    effect_id: str
    payload_json: str

    @property
    def grant_id(self) -> tuple[str, str, str, str, str]:
        return self.kind, self.source_kind, self.source_key, self.instance_id, self.effect_id


@dataclass(frozen=True, slots=True)
class AuthorityStatus:
    kind: str
    instance_id: str
    status: str
    reason: str


@dataclass(frozen=True, slots=True)
class EffectiveStatus:
    """One numeric owner decision; a raw table value is never an effective fallback."""

    path: str
    status: str
    raw: Any
    effective: Any | None
    reason: str

    @property
    def is_effective(self) -> bool:
        return self.status in {VERIFIED, MANUAL} and self.effective is not None


def _require_modifier_retention_rows(definition, history):
    """An exact old row may survive; changed or colliding rows cannot."""
    seen = set()
    for entry in history:
        observation, source = entry["observation"], entry["source_row"]
        identity = observation["id"]
        if identity in seen or entry["reason"] != "modifier_not_entitlement":
            raise ValueError("Modifier history has conflicting retained observations.")
        seen.add(identity)
        rows = [row for row in definition.spellcasting.get("spells", [])
                if isinstance(row, dict) and (row.get("id") == identity
                    or row.get("spell_source_row_id") == entry["source_row_id"])]
        sources = [row for row in definition.spellcasting.get("source_rows", [])
                   if isinstance(row, dict) and row.get("source_row_id") == entry["source_row_id"]]
        if rows != [observation] or sources != [source]:
            raise ValueError("A prospective spell/source row changed retained modifier history.")


def _modifier_retention_entries(authority, definition, history):
    from .character_spell_properties import FIELD, normalize_item_spell_properties
    entries = authority.spell_property_item_entries(definition)
    result = []
    for retained in history:
        legacy = retained["source_row_id"]
        owners = [entry for entry in entries
                  if any(effect.get("legacy_source_row_id") == legacy
                         for effect in normalize_item_spell_properties(entry[FIELD]))]
        if (len(owners) != 1 or owners[0]["item_id"] != retained["item_id"]
                or owners[0]["source_ref"] != retained["source_ref"]
                or owners[0]["legacy_entitlement_cleared"] is not True
                or legacy in owners[0]["current_source_rows"]):
            raise ValueError("Retained modifier history lacks a unique current non-entitling item owner.")
        # Other newly attained class source rows are independent. The relevant
        # legacy ID must still have no competing current owner.
        result.append({key: value for key, value in owners[0].items() if key != "current_source_rows"})
    return result


def _modifier_retention_edges(authority, history):
    view = authority.native_grant_view
    if view is None:
        raise ValueError("Modifier history has no inspected native migration frame.")
    result = []
    for entry in history:
        rows = [edge for edge in view.migration_edges if edge.get("old_spell_id") == entry["observation"]["id"]]
        if (len(rows) != 1 or rows[0].get("grant_ids") != []
                or rows[0].get("unresolved_observation_digest") != numeric_value_digest(entry["observation"])):
            raise ValueError("Modifier history lost its exact empty-grant migration edge.")
        result.append(rows[0])
    return result


@dataclass(frozen=True, slots=True)
class _ModifierHistoryRetention:
    """Detached continuation data, never a current native-grant witness."""
    definition_digest: str
    raw_definition_digest: str
    state_digest: str
    state_revision: int
    source_digest: str
    entries_json: str
    edges_json: str
    history_json: str


@dataclass(frozen=True, slots=True)
class SourceAuthority:
    definition_digest: str
    state_digest: str
    state_revision: int | None
    grants: tuple[AuthorityGrant, ...]
    statuses: tuple[AuthorityStatus, ...]
    warnings: tuple[tuple[str, str], ...]
    verified_manual_actions: tuple[str, ...]
    verified_class_rows: frozenset[str] = frozenset()
    verified_source_rows: frozenset[str] = frozenset()
    disputed_source_rows: frozenset[str] = frozenset()
    field_statuses: tuple[EffectiveStatus, ...] = ()
    resource_statuses: tuple[EffectiveStatus, ...] = ()
    verified_numeric_actions: tuple[str, ...] = ()
    active_item_ids: frozenset[str] = frozenset()
    source_snapshot_digest: str = ""
    resource_basis_digests: tuple[tuple[str, str], ...] = ()
    verified_formula_rows: frozenset[str] = frozenset()
    verified_spell_grants: frozenset[tuple[str, str]] = frozenset()
    verified_spell_choices: frozenset[str] = frozenset()
    current_spell_keys: frozenset[tuple[str, str]] = frozenset()
    inert_page_companions: frozenset[str] = frozenset()
    requested_active_item_ids: frozenset[str] = frozenset()
    unqualified_native_aggregate_adjustments: frozenset[str] = frozenset()
    equipment_hand_rows: tuple[str, ...] | None = None
    managed_pool_owners: tuple[str, ...] = ()
    native_grant_view: Any = None
    native_grant_owners: tuple[dict[str, Any], ...] = ()
    native_grant_custody_confirmed: bool = False
    native_ritual_spell_keys: frozenset[str] = frozenset()
    confirmed_retired_spell_choices: frozenset[str] = frozenset()
    confirmed_active_spell_choices: frozenset[str] = frozenset()
    native_choice_ledger_json: str = ""
    original_definition_digest: str = ""
    reconstructed_spell_roles: tuple[tuple[str, str, int], ...] = ()
    spell_property_bases: tuple[tuple[str, str], ...] = ()
    spell_property_clear_owners: frozenset[str] = frozenset()
    feature_composition: Any = None
    managed_resource_targets: frozenset[str] = frozenset()
    slot_grant_context_json: str = ""
    wizard_rule_context_json: str = ""
    item_spell_context_json: str = ""
    item_prepared_context_json: str = ""
    passive_member_frames: tuple[str, ...] = ()
    tracker_associations: tuple[dict[str, Any], ...] = ()
    modifier_history_retention: _ModifierHistoryRetention | None = None

    def _numeric_context(self, input_definition, input_state, *, formula_scope="current"):
        """Ephemeral raw-input ownership and per-output temporary dependencies."""
        from .divine_avatar_forms import (registered_divine_avatar_feature,
            _declares_divine_avatar_feature, _current_divine_avatar_feature_frame,
            _divine_avatar_feature_effect_eligible,
            divine_avatar_activation_kind, qualified_divine_avatar_numeric_effects,
            DIVINE_AVATAR_FORMS_LEGACY_PAGE_REF)
        if type(formula_scope) is not str or formula_scope not in {"durable", "current"}:
            raise ValueError("Unknown numeric formula scope")
        all_paths = set(NATIVE_BASELINE_FIELDS) | {"stats.max_hp", "__spellcasting__", "__preparation__"}
        all_paths.update(f"stats.ability_scores.{key}.{metric}"
            for key in ("str", "dex", "con", "int", "wis", "cha")
            for metric in ("score", "modifier", "save_bonus"))
        all_paths.update(row.path for row in self.field_statuses if row.path.startswith("skills."))
        context = {"valid": False, "scope": formula_scope, "blocked": frozenset(all_paths),
                   "closed_feature_ids": frozenset(), "effects": {}}
        if type(input_definition) is not CharacterDefinition or type(input_state) is not dict:
            return context
        input_digest = numeric_value_digest(input_definition.to_dict())
        if numeric_value_digest(input_state) != self.state_digest:
            return context
        if input_digest != self.definition_digest:
            if input_digest != self.original_definition_digest:
                return context
            # The original frame is admitted only through its exact current
            # state-owned equipment overlay, never as an arbitrary prior basis.
            from .character_equipment_activation import effective_definition
            try:
                reconciled, _warnings = effective_definition(input_definition, input_state)
                if numeric_value_digest(reconciled.to_dict()) != self.definition_digest:
                    return context
            except (TypeError, ValueError):
                return context
        context.update(valid=True, blocked=frozenset())
        activation = divine_avatar_activation_kind(input_state)
        candidates = []
        counts = Counter(_text(row.get("id")) for row in input_definition.features if type(row) is dict)
        for row in input_definition.features:
            if type(row) is not dict:
                continue
            if _declares_divine_avatar_feature(row):
                candidates.append(row)
        avatar_paths = {"stats.armor_class", "stats.passive_perception", "stats.passive_insight",
            "__spellcasting__", "__preparation__"}
        avatar_paths.update(f"stats.ability_scores.wis.{metric}" for metric in ("score", "modifier", "save_bonus"))
        avatar_paths.update("skills." + name for name in (
            "animal handling", "insight", "medicine", "perception", "survival"))
        from .character_feature_composition import FeatureComposition
        composition = self.feature_composition
        closed = (set(composition.replaced_ids | composition.qualified_ids)
                  if type(composition) is FeatureComposition and composition.matches_definition(input_definition) else set())
        blocked = set()
        if formula_scope == "current" and not candidates:
            if activation == "active":
                # Strict supported v1 state bounds possible temporary effects,
                # but a stored activation cannot supply its absent source owner.
                blocked.update(avatar_paths)
            elif activation == "unknown":
                # Without a selected footprint, malformed/future state cannot
                # be silently narrowed to the favorable known-v1 dependency set.
                blocked.update(all_paths)
        for row in candidates:
            identity = _text(row.get("id"))
            if (not registered_divine_avatar_feature(row) or counts.get(identity) != 1
                    or len(candidates) != 1):
                blocked.update(all_paths)
                continue
            status = self.status_for("feature", identity)
            if status == VERIFIED:
                if _current_divine_avatar_feature_frame(row, self) is None:
                    blocked.update(all_paths)
                    continue
            else:
                reasons = [value.reason for value in self.statuses
                           if value.kind == "feature" and value.instance_id == identity]
                if any(reason in {"source identity changed", "source kind changed",
                        "authenticated physical item/page relation changed"} for reason in reasons):
                    blocked.update(all_paths)
                    continue
            # Registration proves only which temporary dependencies are possible.
            # It never changes the feature's unresolved source status or grants it.
            closed.add(identity)
            if formula_scope == "current" and activation != "inactive" and (
                    status != VERIFIED or not _divine_avatar_feature_effect_eligible(row)
                    or activation != "active"):
                blocked.update(avatar_paths)
        context["closed_feature_ids"] = frozenset(closed)
        context["blocked"] = frozenset(blocked)
        if formula_scope == "current" and not blocked:
            context["effects"] = qualified_divine_avatar_numeric_effects(input_definition, input_state, self)
        return context

    def _with_numeric_restrictions(self, context):
        blocked = context["blocked"]
        rows = tuple(replace(row, effective=None) if row.path in blocked and not (
            row.status == MANUAL and row.reason != "baseline_authorized") else row
            for row in self.field_statuses)
        return replace(self, field_statuses=rows,
            verified_formula_rows=(frozenset() if "__spellcasting__" in blocked else self.verified_formula_rows))

    def _with_resolved_ability_inputs(self, definition, scores, resolved):
        """Prime a local copy from the real resolver, never from saved output."""
        from .character_ability_inputs import input_records
        original = input_records(definition.stats)
        rows = []
        counts = Counter(row.path for row in self.field_statuses)
        for status in self.field_statuses:
            parts = status.path.split(".")
            if (len(parts) == 4 and parts[:2] == ["stats", "ability_scores"] and parts[3] == "score"
                    and status.reason == "baseline_authorized" and status.status in {VERIFIED, MANUAL}):
                key = parts[2]
                before, after = original.get(key), resolved.get(key)
                valid = (counts[status.path] == 1 and type(before) is dict and type(after) is dict
                    and before.get("stage") in {"base", "pre_penalty"}
                    and after.get("stage") in {"base", "pre_penalty"}
                    and before.get("provenance") not in {
                        "unambiguous_legacy_inverse", "legacy_lossy_output", "changed_lossy_layer"}
                    and after.get("provenance") not in {
                        "unambiguous_legacy_inverse", "legacy_lossy_output", "changed_lossy_layer"}
                    and type(before.get("score")) is int and before["score"] >= 0
                    and type(scores.get(key)) is int and scores[key] >= 0)
                status = replace(status, effective=scores[key] if valid else None)
            rows.append(status)
        return replace(self, field_statuses=tuple(rows))

    @property
    def spell_choice_ledger(self) -> dict[str, Any]:
        """A derived server view; serialized copies are never admission proof."""
        return json.loads(self.native_choice_ledger_json) if self.native_choice_ledger_json else {"choices": [], "pools": []}

    @property
    def identity(self) -> str:
        return hashlib.sha256(_canonical({
            "definition": self.definition_digest,
            **({"original_definition": self.original_definition_digest}
                if self.original_definition_digest and self.original_definition_digest != self.definition_digest
                    and self.native_choice_ledger_json else {}),
            "state": self.state_digest,
            "state_revision": self.state_revision,
            "source_snapshot": self.source_snapshot_digest,
            "grants": [(grant.grant_id, grant.payload_json) for grant in self.grants],
            "statuses": [(row.kind, row.instance_id, row.status) for row in self.statuses],
            "manual_actions": self.verified_manual_actions,
            "numeric_actions": self.verified_numeric_actions,
            "requested_active_items": sorted(self.requested_active_item_ids),
            "unqualified_native_aggregate_adjustments": sorted(self.unqualified_native_aggregate_adjustments),
            "equipment_hand_rows": self.equipment_hand_rows,
            "active_items": sorted(self.active_item_ids),
            "fields": [(row.path, row.status, row.effective, row.reason) for row in self.field_statuses],
            "resources": [(row.path, row.status, row.effective, row.reason) for row in self.resource_statuses],
            "resource_bases": self.resource_basis_digests,
            **({"feature_composition": self.feature_composition.identity_json}
               if self.feature_composition is not None and self.feature_composition.identity_json != "{}" else {}),
            **({"managed_pool_owners": self.managed_pool_owners} if self.managed_pool_owners else {}),
            **({"tracker_associations": self.tracker_associations} if self.tracker_associations else {}),
            **({"passive_member_frames": self.passive_member_frames} if self.passive_member_frames else {}),
            **({"managed_resource_targets": sorted(self.managed_resource_targets)}
               if self.managed_resource_targets else {}),
            **({"slot_contributions": self.slot_grant_context_json} if self.slot_grant_context_json else {}),
            **({"item_spell_context": self.item_spell_context_json} if self.item_spell_context_json else {}),
            **({"item_prepared_context": self.item_prepared_context_json} if self.item_prepared_context_json else {}),
            "formula_rows": sorted(self.verified_formula_rows),
            "spell_grants": sorted(self.verified_spell_grants),
            "spell_choices": sorted(self.verified_spell_choices),
            **({"reconstructed_spell_roles": self.reconstructed_spell_roles} if self.reconstructed_spell_roles else {}),
            **({"native_choice_ledger": self.spell_choice_ledger} if self.native_choice_ledger_json else {}),
            **({"class_choice_decisions": {"active": sorted(self.confirmed_active_spell_choices),
                    "retired": sorted(self.confirmed_retired_spell_choices)}}
                if self.confirmed_active_spell_choices or self.confirmed_retired_spell_choices else {}),
            "current_spell_keys": sorted(self.current_spell_keys),
            "spell_property_bases": self.spell_property_bases,
            "spell_property_clear_owners": sorted(self.spell_property_clear_owners),
            **({"native_grants": {"occurrences": self.native_grant_view.occurrences,
                "diagnostics": self.native_grant_view.diagnostics,
                "edges": self.native_grant_view.migration_edges},
                "native_grant_owners": self.native_grant_owners}
               if self.native_grant_view is not None else {}),
        }).encode("utf-8")).hexdigest()

    def resource_basis_digest(self, target_id: str) -> str | None:
        return dict(self.resource_basis_digests).get(target_id)

    def derive_managed_tracker_templates(self, definition, features, *, build_templates, **inputs):
        """Use one proved pool input without deleting retained source aliases.

        Pool facts were resolved while constructing this authority. Consuming
        them does not bind numbers, resolve sources again or recurse into the
        normalizer. The generic builder keeps its strict unproved defaults.
        """
        if not self.managed_pool_owners and not self.passive_member_frames:
            return build_templates(features, **inputs)
        rows = [deepcopy(row) for row in features]
        by_id = {_text(row.get("id")): row for row in rows}
        raw_features = [row for row in definition.features if isinstance(row, dict)]
        raw_templates = [row for row in definition.resource_templates if isinstance(row, dict)]
        aliases, canonical_ids = {}, set()
        for encoded in self.passive_member_frames:
            frame = json.loads(encoded)
            original, canonical = frame["feature"], frame["canonical"]
            identity = _text(original.get("id"))
            if (sum(row == original for row in raw_features) != 1
                    or identity not in by_id
                    or self.status_for("feature", identity) != VERIFIED
                    or frame["class"] not in profile_class_rows(definition.profile)):
                raise ValueError("Current passive member source frame changed.")
            canonical_ids.add(identity)
            for field in ("source", "class_row_id"):
                by_id[identity][field] = canonical[field]
        for encoded in self.managed_pool_owners:
            pool = json.loads(encoded)
            members = pool["members"]
            if (pool["class"] not in profile_class_rows(definition.profile)
                    or sum(row == pool["template"] for row in raw_templates) != 1
                    or sorted(_canonical(row) for row in raw_features
                              if _text(row.get("tracker_ref")) == pool["template"]["id"])
                       != sorted(_canonical(row["feature"]) for row in members)):
                raise ValueError("Current managed resource owner frame changed.")
            canonical = members[0]["canonical"]
            canonical_id = _text(canonical.get("id"))
            if any(_text(member["feature"].get("id")) not in by_id for member in members):
                raise ValueError("A qualified managed resource owner is absent from the effective frame.")
            canonical_ids.add(canonical_id)
            by_id[canonical_id]["source"] = canonical["source"]
            for member in members[1:]:
                aliases[_text(member["feature"].get("id"))] = canonical_id
        tracker_rows = [row for row in rows if _text(row.get("id")) not in aliases]
        derived, templates = build_templates(tracker_rows, **inputs)
        derived_by_id = {_text(row.get("id")): row for row in derived}
        retained = []
        original_ids = {_text(row.get("id")) for row in features}
        for original in features:
            identity = _text(original.get("id"))
            row = deepcopy(derived_by_id.get(identity, original))
            if identity in aliases:
                row = deepcopy(original)
                owner = derived_by_id.get(aliases[identity], {})
                for field in ("tracker_ref", "activation_type"):
                    if field in owner:
                        row[field] = deepcopy(owner[field])
            if identity in aliases or identity in canonical_ids:
                # Display citations and exact links remain retained provenance.
                for field in ("id", "source", "systems_ref", "page_ref", "class_row_id"):
                    if field in original:
                        row[field] = deepcopy(original[field])
                    else:
                        row.pop(field, None)
            retained.append(row)
        retained.extend(row for row in derived if _text(row.get("id")) not in original_ids)
        return retained, templates

    def numeric_basis_digest(self, target_id: str) -> str | None:
        return dict(self.resource_basis_digests).get(target_id)

    def formula_metric_verified(self, family: str, row_id: str, metric: str) -> bool:
        return f"spell_metric:{family}:{row_id}:{metric}" in self.verified_formula_rows

    @property
    def grant_ids(self) -> frozenset[tuple[str, str, str, str, str]]:
        return frozenset(grant.grant_id for grant in self.grants)

    def field_status(self, path: str) -> EffectiveStatus:
        matching = [row for row in self.field_statuses if row.path == path]
        return next((row for row in matching if row.status == CONFLICT),
                    matching[0] if matching else
                    EffectiveStatus(path, UNKNOWN, None, None, "field_owner_unproven"))

    def resource_status(self, kind: str, stable_id: str) -> EffectiveStatus:
        path = f"{kind}:{stable_id}"
        matching = [row for row in self.resource_statuses if row.path == path]
        return next((row for row in matching if row.status == CONFLICT),
                    matching[0] if matching else
                    EffectiveStatus(path, UNKNOWN, None, None, "resource_owner_unproven"))

    def item_counter_rule(self, definition: CharacterDefinition, physical_id: str):
        from .character_item_capabilities import item_counter_rule
        return item_counter_rule(self, definition, physical_id)

    def item_capability_entries(self, definition: CharacterDefinition):
        from .character_item_capabilities import qualified_item_capabilities
        return qualified_item_capabilities(self, definition)

    def attack_inputs_effective(self, attack: dict[str, Any], definition: CharacterDefinition) -> bool:
        abilities = attack.get("authority_ability_dependencies")
        if not isinstance(abilities, list) or not abilities:
            # Historical opaque attacks cannot prove a precomputed number.
            return False
        if any(key not in {"str", "dex", "con", "int", "wis", "cha"}
               or not self.field_status(f"stats.ability_scores.{key}.score").is_effective
               for key in abilities):
            return False
        if not attack.get("authority_requires_proficiency_bonus"):
            return True
        if not self.field_status("stats.proficiency_bonus").is_effective:
            return False
        if attack.get("authority_unarmed") is True:
            return True
        matches = attack.get("authority_weapon_proficiencies")
        return isinstance(matches, list) and bool(matches) and any(
            self.field_status(f"proficiencies.weapons.{_text(value).casefold()}").is_effective
            for value in matches if isinstance(value, str)
        )

    def bind_projected_numbers(self, definition: CharacterDefinition, *,
                               item_catalog: dict[str, Any] | None = None,
                               systems_service: Any | None = None,
                               campaign_page_records: list[Any] | None = None,
                               historical_resource_custody: bool = False,
                               input_definition: CharacterDefinition | None = None,
                               input_state: dict[str, Any] | None = None,
                               formula_scope: str = "current") -> SourceAuthority:
        """Bind formula results only after every required input has an owner."""
        if type(formula_scope) is not str or formula_scope not in {"durable", "current"}:
            raise ValueError("Unknown numeric formula scope")
        stats = dict(definition.stats or {})
        abilities = dict(stats.get("ability_scores") or {})
        projected_inputs = dict(dict(stats.get("ability_inputs") or {}).get("scores") or {})
        field_rows = {row.path: row for row in self.field_statuses}
        context = (None if historical_resource_custody else
            self._numeric_context(input_definition, input_state, formula_scope=formula_scope))
        recipe_scores = (None if historical_resource_custody else _qualified_spell_capacity_scores(
            self, input_definition, input_state, formula_scope=formula_scope) if context["valid"] else {})
        for key, label in (("str", "strength"), ("dex", "dexterity"),
                           ("con", "constitution"), ("int", "intelligence"),
                           ("wis", "wisdom"), ("cha", "charisma")):
            ability = dict(abilities.get(key) or abilities.get(label) or {})
            score_path = f"stats.ability_scores.{key}.score"
            score_status = field_rows.get(score_path)
            score = ability.get("score")
            if (not historical_resource_custody and score_status is not None
                    and score_status.reason == "baseline_authorized" and score_status.status in {VERIFIED, MANUAL}):
                field_rows[score_path] = replace(score_status,
                    effective=recipe_scores.get(key) if type(recipe_scores.get(key)) is int else None)
                score_status = field_rows[score_path]
            if (score_status is not None and score_status.reason == "baseline_authorized"
                    and score_status.status in {VERIFIED, MANUAL} and type(score) is int
                    and (historical_resource_custody
                         and dict(projected_inputs.get(key) or {}).get("stage") in {"base", "pre_penalty"}
                         or not historical_resource_custody and type(recipe_scores.get(key)) is int)):
                field_rows[score_path] = replace(score_status,
                    effective=score if historical_resource_custody else recipe_scores[key])
            if field_rows.get(score_path) is not None and field_rows[score_path].is_effective:
                modifier_path = f"stats.ability_scores.{key}.modifier"
                modifier = ability.get("modifier")
                if (field_rows.get(modifier_path) is not None
                        and field_rows[modifier_path].status == UNKNOWN
                        and type(modifier) is int):
                    field_rows[modifier_path] = EffectiveStatus(
                        modifier_path, VERIFIED, field_rows[modifier_path].raw,
                        modifier, "derived_from_authorized_score",
                    )
                save_path = f"stats.ability_scores.{key}.save_bonus"
                save = ability.get("save_bonus")
                if (self.field_status("stats.proficiency_bonus").is_effective
                        and self.verified_class_rows
                        and field_rows.get(save_path) is not None
                        and field_rows[save_path].status == UNKNOWN
                        and type(save) is int):
                    field_rows[save_path] = EffectiveStatus(
                        save_path, VERIFIED, field_rows[save_path].raw,
                        save, "derived_from_authorized_inputs",
                    )
        current_inputs = replace(self, field_statuses=tuple(field_rows.values()))
        if context is not None:
            current_inputs = current_inputs._with_numeric_restrictions(context)
            field_rows = {row.path: row for row in current_inputs.field_statuses}
        eligible = {path for path, status in field_rows.items()
                    if (path in NATIVE_BASELINE_FIELDS or path == "stats.max_hp" and isinstance(
                        dict(definition.source.get("native_progression") or {}).get("hp_recipe"), dict)) and status.status != CONFLICT
                    and (status.reason == "native_aggregate_recipe_pending"
                         or path == "stats.max_hp" and status.status in {VERIFIED, MANUAL}
                         or path == "stats.armor_class" and not status.is_effective
                         and status.reason == "aggregate_owner_unproven")}
        if eligible and not historical_resource_custody:
            recipes = _qualified_native_aggregate_values(
                current_inputs, definition, item_catalog=item_catalog,
                systems_service=systems_service, campaign_page_records=campaign_page_records,
                numeric_context=context,
            )
            for path in eligible:
                expected = recipes.get(path)
                if expected is not None and stats.get(path.removeprefix("stats.")) == expected:
                    field_rows[path] = EffectiveStatus(path, VERIFIED, field_rows[path].raw,
                        expected, "derived_from_qualified_native_recipe")
        bound = replace(current_inputs, field_statuses=tuple(field_rows.values()))
        # Activation's closed/projected custody comparison does not publish or
        # expose current managed capacities. Its raw snapshots retain the prior
        # resource-owner evidence; ordinary reads and services always bind it.
        if historical_resource_custody:
            return bound
        # Numbers come from the effective projection, but structural ownership
        # remains bound to the authenticated selection before source suppression.
        # Reconcile SQLite activation here too: retained inventory flags cannot
        # authorize current item bonuses.
        resource_definition = None
        if context["valid"]:
            from .character_equipment_activation import effective_definition
            resource_definition, _ = effective_definition(input_definition, input_state)
            if numeric_value_digest(resource_definition.to_dict()) != self.definition_digest:
                resource_definition = None
        bound = replace(bound, resource_statuses=_current_managed_resource_statuses(
            bound, resource_definition, systems_service=systems_service,
            campaign_page_records=campaign_page_records,
        ))
        from .character_spell_slots import refresh_slot_grant_statuses
        from .character_item_casting import bind_context
        from .character_item_prepared import bind_context as bind_prepared_context
        bound = bind_context(refresh_slot_grant_statuses(bound), definition,
            input_definition, input_state, systems_service)
        return bind_prepared_context(bound, definition, input_definition, input_state)

    def bind_current_numbers(self, definition: CharacterDefinition, state: dict[str, Any], *,
                             systems_service: Any, campaign_page_records: list[Any] | None,
                             item_catalog: dict[str, Any] | None = None,
                             formula_scope: str = "durable") -> SourceAuthority:
        """Use the read path's qualified formulas before a guarded native write."""
        from .character_equipment_activation import effective_definition
        from .character_builder import normalize_definition_to_native_model
        from .character_read_foundation import read_item_catalog_for_definition, normalize_read_facade
        current, _ = effective_definition(definition, state)
        context = self._numeric_context(definition, state, formula_scope=formula_scope)
        catalog = read_item_catalog_for_definition(
            current, item_catalog=item_catalog, systems_service=systems_service,
            campaign_page_records=campaign_page_records,
        )
        projected = normalize_read_facade(
            normalize_definition_to_native_model, current, mode="effective", source_authority=self, item_catalog=catalog,
            systems_service=systems_service, campaign_page_records=campaign_page_records,
            transient_effects=context["effects"],
        )
        return self.bind_projected_numbers(
            projected, item_catalog=catalog, systems_service=systems_service,
            campaign_page_records=campaign_page_records,
            input_definition=definition, input_state=state, formula_scope=formula_scope,
        )

    def require_authoring_inputs(self) -> None:
        """Refuse a definition rewrite that would invert unowned old totals."""
        required = [f"stats.ability_scores.{key}.score"
                    for key in ("str", "dex", "con", "int", "wis", "cha")]
        required.extend(("stats.proficiency_bonus", "stats.max_hp",
                         "stats.armor_class", "stats.initiative_bonus", "stats.speed"))
        unresolved = [path for path in required if not (
            self.field_status(path).is_effective or
            (self.field_status(path).status in {VERIFIED, MANUAL}
             and self.field_status(path).reason == "baseline_authorized")
        )]
        if unresolved:
            raise ValueError("Character mechanics need manager source repair before recalculation: "
                             + ", ".join(unresolved))

    def suppress_unknown_numbers(self, definition: CharacterDefinition, *,
                                 item_catalog: dict[str, Any] | None = None) -> CharacterDefinition:
        """Return a read-only effective sheet with disputed arithmetic withheld.

        This runs after the legacy normalizer has built its internal formula
        candidate. Its candidate numbers are never exposed as effective when
        an input owner is unknown. Historical values remain on the raw record
        and in this snapshot's status.raw for manager/table reference.
        """
        payload = deepcopy(definition.to_dict())
        stats = dict(payload.get("stats") or {})
        abilities = dict(stats.get("ability_scores") or {})
        for key, label in (("str", "strength"), ("dex", "dexterity"),
                           ("con", "constitution"), ("int", "intelligence"),
                           ("wis", "wisdom"), ("cha", "charisma")):
            for alias in (key, label):
                if alias not in abilities:
                    continue
                row = dict(abilities.get(alias) or {})
                for metric in ("score", "modifier", "save_bonus"):
                    status = self.field_status(f"stats.ability_scores.{key}.{metric}")
                    if status.reason == "baseline_authorized" and status.is_effective:
                        row[metric] = deepcopy(status.effective)
                        continue
                    if not status.is_effective:
                        row[metric] = None
                    elif status.reason != "baseline_authorized":
                        row[metric] = deepcopy(status.effective)
                abilities[alias] = row
        stats["ability_scores"] = abilities
        for key in ("proficiency_bonus", "max_hp", "armor_class", "initiative_bonus",
                    "speed", "passive_perception", "passive_insight",
                    "passive_investigation", "carrying_capacity", "push_drag_lift"):
            status = self.field_status(f"stats.{key}")
            if not status.is_effective:
                stats[key] = None
            elif status.reason != "baseline_authorized":
                stats[key] = deepcopy(status.effective)
        # Rebuild formatted reminder strings after input qualification; the
        # historical strings may already contain an unqualified numeric DC.
        from .character_builder_equipment import _derive_attack_reminder_state_from_character_inputs
        reminder_definition = self.effective_definition(definition)
        reminder_scores = {key: self.field_status(f"stats.ability_scores.{key}.score").effective
                           for key in ("str", "dex", "con", "int", "wis", "cha")
                           if self.field_status(f"stats.ability_scores.{key}.score").is_effective}
        stats["attack_reminder_state"] = _derive_attack_reminder_state_from_character_inputs(
            features=reminder_definition.features,
            equipment_catalog=reminder_definition.equipment_catalog, item_catalog=item_catalog,
            ability_scores=reminder_scores,
            proficiency_bonus=self.field_status("stats.proficiency_bonus").effective,
            source_authority=self,
        )
        payload["stats"] = stats
        for row in list(payload.get("skills") or []):
            if not isinstance(row, dict):
                continue
            name = _text(row.get("name")).casefold()
            ability = {
                "athletics": "str", "acrobatics": "dex", "sleight of hand": "dex",
                "stealth": "dex", "arcana": "int", "history": "int",
                "investigation": "int", "nature": "int", "religion": "int",
                "animal handling": "wis", "insight": "wis", "medicine": "wis",
                "perception": "wis", "survival": "wis", "deception": "cha",
                "intimidation": "cha", "performance": "cha", "persuasion": "cha",
            }.get(name)
            if ability and not self.field_status(f"stats.ability_scores.{ability}.score").is_effective:
                row["bonus"] = None
            if self.field_status(f"skills.{name}").status in {UNKNOWN, CONFLICT}:
                row["authority_status"] = NEEDS_REPAIR
                row["bonus"] = None
        proficiencies = dict(payload.get("proficiencies") or {})
        for kind, entries in proficiencies.items():
            proficiencies[kind] = [entry for entry in list(entries or [])
                                   if self.field_status(
                                       f"proficiencies.{kind}.{_text(entry).casefold()}"
                                   ).is_effective]
        automatic_tools = [row.effective for row in self.field_statuses
                           if row.reason == "automatic_tool_expertise" and row.is_effective]
        if automatic_tools:
            proficiencies["tool_expertise"] = list(dict.fromkeys(
                list(proficiencies.get("tool_expertise") or []) + automatic_tools))
        payload["proficiencies"] = proficiencies
        for attack in list(payload.get("attacks") or []):
            if isinstance(attack, dict) and not self.attack_inputs_effective(attack, definition):
                attack["authority_status"] = NEEDS_REPAIR
                attack["mechanics_suppressed"] = True
                for key in ("attack_bonus", "attack_roll_bonus", "to_hit_bonus",
                            "damage_bonus", "save_dc", "damage_formula", "damage"):
                    if key in attack:
                        attack[key] = None
        spellcasting = dict(payload.get("spellcasting") or {})
        manual_records = list(spellcasting.get("manual_authorizations") or [])
        class_rows = list(spellcasting.get("class_rows") or [])
        # A summary has no independent row identity. Qualify owned rows first,
        # then derive the single-class summary from that exact qualified row.
        for row in [*([] if class_rows else [spellcasting]), *class_rows,
                    *list(spellcasting.get("source_rows") or [])]:
            if not isinstance(row, dict):
                continue
            for metric in ("spell_attack_bonus", "spell_save_dc"):
                if metric in row:
                    row_id = _text(row.get("source_row_id") or row.get("class_row_id"))
                    independently_manual = bool(row_id and any(
                        self.manual_authorization(
                            record, character_slug=definition.character_slug,
                            target_kind="source_row", target_id=row_id, metric=metric,
                            definition=definition,
                        ) for record in manual_records
                    ))
                    ability_name = _text(row.get("spellcasting_ability")).casefold()
                    ability_key = {"strength": "str", "dexterity": "dex",
                                   "constitution": "con", "intelligence": "int",
                                   "wisdom": "wis", "charisma": "cha"}.get(ability_name)
                    raw_provenance = row.get("spell_metric_provenance")
                    metric_record = raw_provenance.get(metric) if isinstance(raw_provenance, dict) else None
                    is_formula = isinstance(metric_record, dict) and metric_record.get("kind") == "formula"
                    family = "source" if row.get("source_row_id") else "class"
                    formula_safe = bool(
                        self.formula_metric_verified(family, row_id, metric) and ability_key
                        and is_formula
                        and self.field_status("stats.proficiency_bonus").is_effective
                        and self.field_status(f"stats.ability_scores.{ability_key}.score").is_effective
                    )
                    if is_formula and not independently_manual and not formula_safe:
                        row[metric] = None
        if class_rows:
            for metric in ("spell_attack_bonus", "spell_save_dc"):
                spellcasting[metric] = class_rows[0].get(metric) if len(class_rows) == 1 else None
        for template in list(payload.get("resource_templates") or []):
            if not isinstance(template, dict):
                continue
            status = self.resource_status("resource", _text(template.get("id")))
            if not status.is_effective:
                template["authority_status"] = NEEDS_REPAIR
                for key in ("max", "initial_current", "reset_on", "reset_to"):
                    template[key] = None
            elif (status.reason == "derived_from_current_managed_owner"
                  and isinstance(status.effective, dict)):
                template["initial_current"] = status.effective["initial_current"]
        if self.native_grant_view is not None:
            spellcasting = self._native_spell_projection(definition, spellcasting)
        payload["spellcasting"] = spellcasting
        return CharacterDefinition.from_dict(payload)

    def _native_spell_projection(self, definition, spellcasting):
        from .character_spell_grants import native_grant_spell_ids, project_native_spellcasting
        try:
            fixed_ids = native_grant_spell_ids(definition)
        except ValueError:
            fixed_ids = {row.get("id") for row in definition.spellcasting.get("spells", [])
                         if isinstance(row, dict)}
        classes, items = [], []
        for raw in spellcasting.get("spells", []):
            if not isinstance(raw, dict) or self.spell_status(raw, definition=definition) != VERIFIED:
                continue
            # A derived DTO may still carry an earlier projection's refusal.
            # Only this fresh successful qualification may replace that status;
            # review flags and historical grant observations remain untouched.
            row = deepcopy(raw)
            row["authority_status"] = VERIFIED
            row["authority_note"] = ""
            if raw.get("spell_source_row_id"):
                items.append(row)
            elif (raw.get("id") in self.verified_spell_choices
                    and (raw.get("id") in self.confirmed_active_spell_choices
                         or any(identity == raw.get("id") and role == "available"
                                for identity, role, _level in self.reconstructed_spell_roles))):
                row["is_always_prepared"] = False
                row["is_bonus_known"] = False
                row.pop("always_prepared", None)
                # A current ritual tag is a publication fact, not proof that
                # this class/feature can cast that spell as a ritual. Preserve
                # qualified source-row ritual-book/item behavior in its adapter.
                row["grant_spell_has_ritual_tag"] = (
                    dict(row.get("systems_ref") or {}).get("entry_key") in self.native_ritual_spell_keys)
                row["is_ritual"] = False
                for alias in ("ritual", "isRitual", "base_is_ritual", "base_ritual"):
                    row.pop(alias, None)
                classes.append(row)
        projected = project_native_spellcasting(definition, self.native_grant_view,
            qualified_class_spells=classes, qualified_item_spells=items,
            confirmed_retired_spell_choices=self.confirmed_retired_spell_choices,
            choice_ledger=self.spell_choice_ledger)
        for field in ("class_rows", "source_rows", "slot_lanes", "slot_progression",
                      "spell_attack_bonus", "spell_save_dc", "spellcasting_ability"):
            if field in spellcasting:
                projected[field] = deepcopy(spellcasting[field])
        return projected

    def status_for(self, kind: str, instance_id: str) -> str:
        matching = [row.status for row in self.statuses if row.kind == kind and row.instance_id == instance_id]
        if NEEDS_ATTENTION in matching:
            return NEEDS_ATTENTION
        return matching[0] if matching else NEEDS_REPAIR

    def manual_authorization(self, record: Any, *, character_slug: str, target_kind: str, target_id: str, metric: str,
                             definition: CharacterDefinition) -> bool:
        return valid_manual_authorization(
            record, character_slug=character_slug, target_kind=target_kind,
            target_id=target_id, metric=metric, definition=definition,
            verified_manual_actions=self.verified_manual_actions,
        )

    def approved_payload(self, kind: str, instance_id: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.status_for(kind, instance_id) != VERIFIED:
            return result
        for grant in self.grants:
            if grant.kind != kind or grant.instance_id != instance_id:
                continue
            field, value = next(iter(json.loads(grant.payload_json).items()))
            if field in result:
                if isinstance(result[field], list):
                    result[field].append(value)
                else:
                    result[field] = [result[field], value]
            else:
                result[field] = [value] if field in {
                    "spell_support", "spellcasting_modifiers", "spell_property_modifiers", "defensive_rules",
                    "attack_reminder_rules", "resource_template_bonuses", "item_use_actions",
                } else value
        return result

    def active_item_effect_entries(self, definition: CharacterDefinition) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for item in list(definition.equipment_catalog or []):
            if not isinstance(item, dict):
                continue
            item_id = _text(item.get("id"))
            if item_id not in self.active_item_ids or self.status_for("item", item_id) != VERIFIED:
                continue
            payload = self.approved_payload("item", item_id)
            if payload:
                entries.append({"item_id": item_id, "item_name": _text(item.get("name")), **payload})
        return entries

    def spell_property_item_entries(self, definition):
        """All verified declarations, including inactive owners, from owned facts."""
        from .character_spell_properties import FIELD
        entries = []
        physical = [json.loads(row) for row in self.equipment_hand_rows or ()]
        for item in definition.equipment_catalog:
            if not isinstance(item, dict):
                continue
            identity = _text(item.get("id"))
            if self.status_for("item", identity) != VERIFIED:
                continue
            payload = self.approved_payload("item", identity)
            if FIELD not in payload:
                continue
            identities = {(grant.source_kind, grant.source_key) for grant in self.grants
                if grant.kind == "item" and grant.instance_id == identity
                and FIELD in json.loads(grant.payload_json)}
            if len(identities) != 1 or _source_identity(item) not in identities:
                raise ValueError("Spell modifier history lost its current exact item source owner.")
            matching = [row for row in physical if isinstance(row, dict)
                        and (row.get("catalog_ref") or row.get("id")) == identity]
            known = (len(matching) == 1 and type(matching[0].get("weapon_wield_mode")) is str
                     and matching[0]["weapon_wield_mode"] in {"", "main-hand", "off-hand", "two-handed"}
                     and type(matching[0].get("quantity")) is int)
            mode = matching[0].get("weapon_wield_mode") if known else None
            quantity = matching[0]["quantity"] if known else None
            # Source activation already establishes exact physical identity,
            # equipped state and required attunement; holding is separate.
            held = (known and quantity > 0 and identity in self.active_item_ids
                    and mode in {"main-hand", "off-hand", "two-handed"})
            entries.append({"item_id": identity, "item_name": _text(item.get("name")), "source_ref": deepcopy(item.get("systems_ref")),
                "source_basis_digest": numeric_value_digest(payload),
                "condition_known": known, "wielded": held, FIELD: payload[FIELD],
                "legacy_entitlement_cleared": identity in self.spell_property_clear_owners,
                "current_source_rows": sorted(self.verified_source_rows | self.disputed_source_rows)})
        return entries

    def continue_spell_modifier_history(self, prior_authority, prior_definition, definition, *,
                                       prior_state, prior_state_revision, state, state_revision):
        """Retain exact prior observations without authenticating future grants.

        Only the actual prior/current authorities can issue this request-local
        carrier. Its consumers are normalization/history preservation, not play
        projection, native grant verification or publication authorization.
        """
        if type(self) is not SourceAuthority or type(prior_authority) is not SourceAuthority:
            raise ValueError("Modifier history needs its exact prior authority.")
        for authority, frame, frame_state, revision in (
                (prior_authority, prior_definition, prior_state, prior_state_revision),
                (self, definition, state, state_revision)):
            if (type(frame) is not CharacterDefinition or type(frame_state) is not dict
                    or type(revision) is not int or revision < 0
                    or authority.state_revision != revision
                    or authority.state_digest != numeric_value_digest(frame_state)
                    or numeric_value_digest(frame.to_dict()) not in {
                        authority.definition_digest, authority.original_definition_digest}):
                raise ValueError("Modifier history no longer matches its character/state frame.")
        history = prior_authority.retained_spell_modifier_history(prior_definition)
        if not history:
            return self
        if (not prior_authority.native_grant_custody_confirmed
                or not self.source_snapshot_digest
                or self.source_snapshot_digest != prior_authority.source_snapshot_digest):
            raise ValueError("Modifier history lost its confirmed prior or current source frame.")
        prior_entries = _modifier_retention_entries(prior_authority, prior_definition, history)
        entries = _modifier_retention_entries(self, definition, history)
        edges = _modifier_retention_edges(self, history)
        if entries != prior_entries or edges != _modifier_retention_edges(prior_authority, history):
            raise ValueError("Modifier history changed its exact physical/source or migration relation.")
        _require_modifier_retention_rows(definition, history)
        return replace(self, modifier_history_retention=_ModifierHistoryRetention(
            self.definition_digest, numeric_value_digest(definition.to_dict()), self.state_digest, state_revision,
            self.source_snapshot_digest, _canonical(entries), _canonical(edges), _canonical(history)))

    def retained_spell_modifier_history(self, definition):
        from .character_spell_properties import FIELD, item_spell_property_facts, normalize_item_spell_properties
        entries = self.spell_property_item_entries(definition)
        declared = {effect["legacy_source_row_id"] for entry in entries
                    for effect in normalize_item_spell_properties(entry[FIELD])
                    if "legacy_source_row_id" in effect}
        _rules, history, _warnings = item_spell_property_facts(raw_definition=definition,
            item_entries=entries, native_view=self.native_grant_view,
            native_custody_confirmed=self.native_grant_custody_confirmed)
        required = {row.get("id") for row in definition.spellcasting.get("spells", [])
                    if isinstance(row, dict) and row.get("spell_source_row_id") in declared}
        retention = self.modifier_history_retention
        if retention is not None:
            if (type(retention) is not _ModifierHistoryRetention
                    or retention.definition_digest != self.definition_digest
                    or numeric_value_digest(definition.to_dict()) not in {
                        retention.definition_digest, retention.raw_definition_digest}
                    or retention.state_digest != self.state_digest
                    or retention.state_revision != self.state_revision
                    or retention.source_digest != self.source_snapshot_digest):
                raise ValueError("Modifier history continuation no longer matches its exact candidate.")
            retained = json.loads(retention.history_json)
            if (_canonical(_modifier_retention_entries(self, definition, retained)) != retention.entries_json
                    or _canonical(_modifier_retention_edges(self, retained)) != retention.edges_json):
                raise ValueError("Modifier history continuation source relation changed.")
            _require_modifier_retention_rows(definition, retained)
            # Keep the pending native view/custody unchanged. These old rows
            # cannot supply current casting entitlement or numeric authority.
            history = retained
        if required != {entry["observation"]["id"] for entry in history}:
            raise ValueError("Legacy item observations need exact current custody before normalization.")
        return history

    def project_spell_properties(self, definition, spellcasting):
        from .character_spell_properties import project_spell_properties
        return project_spell_properties(spellcasting, raw_definition=definition,
            bases=self.spell_property_bases, item_entries=self.spell_property_item_entries(definition),
            native_view=self.native_grant_view, native_custody_confirmed=self.native_grant_custody_confirmed)

    def effective_definition(self, definition: CharacterDefinition) -> CharacterDefinition:
        """Replace historical effect copies with current approved payloads."""
        payload = deepcopy(definition.to_dict())
        from .character_feature_history import declared_ids
        history_ids = declared_ids(definition, self.verified_numeric_actions)
        for attack in list(payload.get("attacks") or []):
            if isinstance(attack, dict):
                for key in tuple(attack):
                    if key.startswith("authority_"):
                        attack.pop(key, None)
        for kind, field, effect_fields in (
            ("feature", "features", _FEATURE_EFFECT_FIELDS),
            ("item", "equipment_catalog", _ITEM_EFFECT_FIELDS),
        ):
            approved_rows: list[dict[str, Any]] = []
            for row in list(payload.get(field) or []):
                if not isinstance(row, dict):
                    continue
                for effect_field in effect_fields:
                    row.pop(effect_field, None)
                instance_id = _text(row.get("id"))
                if self.status_for(kind, instance_id) != VERIFIED or kind == "feature" and instance_id in history_ids:
                    if kind == "item":
                        row["mechanics_suppressed"] = True
                        row["is_equipped"] = False
                        row["is_attuned"] = False
                        row.pop("weapon_wield_mode", None)
                    else:
                        row["mechanics_suppressed"] = True
                    row["authority_status"] = self.status_for(kind, instance_id)
                    approved_rows.append(row)
                    continue
                if kind == "item":
                    row["is_equipped"] = instance_id in self.active_item_ids
                    if not row["is_equipped"]:
                        row["is_attuned"] = False
                        row.pop("weapon_wield_mode", None)
                    else:
                        row.update(self.approved_payload(kind, instance_id))
                    if "item_capabilities" in self.approved_payload(kind, instance_id):
                        from .character_item_capabilities import active_clause
                        owned = [entry for entry in self.item_capability_entries(definition)
                                 if entry["catalog_id"] == instance_id]
                        if len(owned) == 1:
                            entry = owned[0]
                            row["item_capabilities"] = deepcopy(entry["capability"])
                            # Preserve attuned-only facts without enabling other
                            # unequipped bonuses or reusing imported booleans.
                            row["is_attuned"] = entry["physical"].get("is_attuned") is True
                            casting = entry["capability"].get("casting")
                            if casting is not None and active_clause(entry, casting["activation"]):
                                row["spell_support"] = deepcopy(self.approved_payload(kind, instance_id).get("spell_support", []))
                        else:
                            row.pop("item_capabilities", None)
                            row.pop("spell_support", None)
                else:
                    from .divine_avatar_forms import (
                        _declares_divine_avatar_feature, _current_divine_avatar_feature_frame,
                        _divine_avatar_feature_effect_eligible)
                    original = next((value for value in definition.features if isinstance(value, dict)
                                     and _text(value.get("id")) == instance_id), {})
                    raw_avatar = _declares_divine_avatar_feature(original)
                    if instance_id in self.inert_page_companions and not raw_avatar:
                        approved_rows.append(row)
                        continue
                    current_payload = self.approved_payload(kind, instance_id)
                    current_avatar = _declares_divine_avatar_feature({"id": instance_id, **current_payload})
                    if ((raw_avatar or current_avatar)
                            and (not _divine_avatar_feature_effect_eligible(original)
                                 or _current_divine_avatar_feature_frame(original, self) is None)):
                        # A valid current replacement cannot bless an invalid raw
                        # Avatar selection or expose qualified benefit actions.
                        row["mechanics_suppressed"] = True
                        row["authority_status"] = NEEDS_REPAIR
                        approved_rows.append(row)
                        continue
                    row.update(current_payload)
                if kind == "feature":
                    saved_option = dict(next((original.get("campaign_option") for original in definition.features
                                              if isinstance(original, dict) and _text(original.get("id")) == instance_id), {}) or {})
                    current_option = row.get("campaign_option")
                    if isinstance(current_option, dict) and isinstance(saved_option.get("selected_choices"), dict):
                        current_option["selected_choices"] = deepcopy(saved_option["selected_choices"])
                approved_rows.append(row)
            if kind == "feature":
                from .character_feature_composition import apply_effective_composition
                approved_rows = apply_effective_composition(approved_rows, self.feature_composition)
            payload[field] = approved_rows
        spellcasting = dict(payload.get("spellcasting") or {})
        # Keep saved formula provenance through derivation. A failed current
        # witness must remain a formula so suppress_unknown_numbers can withhold
        # its numeric result; only a distinct manual total is manual.
        clean_spells: list[dict[str, Any]] = []
        for raw in list(spellcasting.get("spells") or []):
            if not isinstance(raw, dict):
                continue
            spell = dict(raw)
            spell.pop("historical_mark", None)
            status = self.spell_status(spell, definition=definition)
            spell["authority_status"] = status
            spell["authority_note"] = (
                "Source needs repair; use this spell with your GM. Automatic benefits are unavailable."
                if status == NEEDS_REPAIR else
                "Conflicting source records need manager attention. Automatic benefits are unavailable."
                if status == NEEDS_ATTENTION else
                "Manager-authorized manual spell." if status == MANUAL else ""
            )
            # Historical flags and free-use claims are never current grants.
            spell["is_always_prepared"] = False
            spell["is_bonus_known"] = False
            spell.pop("grant_source_label", None)
            if "always prepared" in _text(spell.get("source")).casefold():
                spell.pop("source", None)
            for access_field in ("spell_access_type", "spell_access_uses", "spell_access_reset_on"):
                spell.pop(access_field, None)
            if status != VERIFIED:
                if status != MANUAL:
                    spell["mark"] = ""
                original_row_id = _text(spell.pop("spell_source_row_id", None))
                if original_row_id:
                    spell["authority_original_source_row_id"] = original_row_id
                original_class_id = _text(spell.pop("class_row_id", None))
                if original_class_id:
                    spell["authority_original_class_row_id"] = original_class_id
                spell.pop("campaign_option_sources", None)
            clean_spells.append(spell)
        spellcasting["spells"] = clean_spells
        spellcasting["source_rows"] = [
            row for row in list(spellcasting.get("source_rows") or [])
            if isinstance(row, dict) and _text(row.get("source_row_id")) in self.verified_source_rows
            or isinstance(row, dict) and self._manual_row_authorized(row, definition)
        ]
        if self.native_grant_view is not None:
            spellcasting = self._native_spell_projection(definition, spellcasting)
        payload["spellcasting"] = spellcasting
        return CharacterDefinition.from_dict(payload)

    def _manual_row_authorized(self, row: dict[str, Any], definition: CharacterDefinition) -> bool:
        row_id = _text(row.get("source_row_id"))
        records = list(dict(definition.spellcasting or {}).get("manual_authorizations") or [])
        return bool(row_id and any(
            self.manual_authorization(record, character_slug=definition.character_slug,
                                      target_kind="source_row", target_id=row_id, metric=metric,
                                      definition=definition)
            for record in records for metric in ("spell_attack_bonus", "spell_save_dc")
        ))

    def source_row_is_effective(self, row_id: str, definition: CharacterDefinition) -> bool:
        if row_id in self.verified_class_rows or row_id in self.verified_source_rows:
            return True
        return any(
            isinstance(row, dict) and _text(row.get("source_row_id")) == row_id
            and self._manual_row_authorized(row, definition)
            for row in list(dict(definition.spellcasting or {}).get("source_rows") or [])
        )

    def spell_status(self, spell: dict[str, Any], *, definition: CharacterDefinition) -> str:
        if spell.get("item_spell_review_only") or spell.get("spell_source_review_only"):
            return NEEDS_ATTENTION
        spell_id = _text(spell.get("id"))
        if self.native_grant_view is not None:
            from .character_spell_grants import native_grant_spell_ids
            try:
                fixed = native_grant_spell_ids(definition)
            except ValueError:
                return NEEDS_REPAIR
            origins = self.native_grant_view.for_spell(spell_id)
            if spell_id in fixed or origins:
                if any(row["status"] == VERIFIED and (
                    row["contributions"].get("always_prepared") is True
                    or row["contributions"].get("bonus_known") is True
                    or row["contributions"].get("ritual") is True) for row in origins):
                    return VERIFIED
                # An unqualified feature declaration cannot erase a separately
                # witnessed ordinary class/source entitlement.
        original_row_id = _text(spell.get("authority_original_source_row_id"))
        row_id = original_row_id or _text(spell.get("spell_source_row_id"))
        if row_id in self.disputed_source_rows:
            return NEEDS_ATTENTION
        if row_id:
            declared = [json.loads(grant.payload_json).get("item_capabilities") for grant in self.grants
                        if grant.kind == "item" and "item_capabilities" in json.loads(grant.payload_json)]
            declared = [cap for cap in declared if (cap.get("casting") or {}).get("source_row_id") == row_id]
            if declared:
                owners = [entry for entry in self.item_capability_entries(definition)
                          if (entry["capability"].get("casting") or {}).get("source_row_id") == row_id]
                if len(owners) != 1:
                    return NEEDS_ATTENTION
        if row_id:
            spell_keys = {key for owned_id, key in self.current_spell_keys if owned_id == spell_id}
            if (row_id in self.verified_source_rows
                    and self.status_for("spell", spell_id) == VERIFIED
                    and any((row_id, key) in self.verified_spell_grants for key in spell_keys if key)):
                return VERIFIED
        elif (not original_row_id and _text(spell.get("class_row_id") or spell.get("authority_original_class_row_id")) in self.verified_class_rows
              and self.status_for("spell", spell_id) == VERIFIED
              and spell_id in self.verified_spell_choices):
            return VERIFIED
        records = list(dict(definition.spellcasting or {}).get("manual_authorizations") or [])
        if spell_id and any(
            self.manual_authorization(record, character_slug=definition.character_slug,
                                      target_kind="spell", target_id=spell_id, metric="availability",
                                      definition=definition)
            for record in records
        ):
            return MANUAL
        return NEEDS_REPAIR

    def annotate_spellcasting(
        self, spellcasting: dict[str, Any], *, definition: CharacterDefinition,
    ) -> dict[str, Any]:
        """Expose effective spell ownership without mutating historical rows."""
        projected = deepcopy(dict(spellcasting or {}))
        projected.pop(MISSING_OVERRIDE_AUTHORITY_KEY, None)
        saved_spells_by_id: dict[str, list[dict[str, Any]]] = {}
        for saved in list(dict(definition.spellcasting or {}).get("spells") or []):
            if isinstance(saved, dict) and _text(saved.get("id")):
                saved_spells_by_id.setdefault(_text(saved.get("id")), []).append(saved)
        projected_spell_id_counts: dict[str, int] = {}
        for raw in list(projected.get("spells") or []):
            if isinstance(raw, dict) and _text(raw.get("id")):
                spell_id = _text(raw.get("id"))
                projected_spell_id_counts[spell_id] = projected_spell_id_counts.get(spell_id, 0) + 1
        saved_class_row_counts: dict[str, int] = {}
        for row in list(dict(definition.spellcasting or {}).get("class_rows") or []):
            if isinstance(row, dict) and _text(row.get("class_row_id")):
                row_id = _text(row.get("class_row_id"))
                saved_class_row_counts[row_id] = saved_class_row_counts.get(row_id, 0) + 1
        saved_source_rows: dict[str, list[dict[str, Any]]] = {}
        for row in list(dict(definition.spellcasting or {}).get("source_rows") or []):
            if isinstance(row, dict) and _text(row.get("source_row_id")):
                saved_source_rows.setdefault(_text(row.get("source_row_id")), []).append(row)
        spells: list[dict[str, Any]] = []
        wizard_contexts = json.loads(self.wizard_rule_context_json) if self.wizard_rule_context_json else {}
        ledger_choices = {}
        for choice in self.spell_choice_ledger.get("choices", []):
            ledger_choices.setdefault(choice.get("spell_id"), []).append(choice)
        for raw in list(projected.get("spells") or []):
            if not isinstance(raw, dict):
                continue
            spell = dict(raw)
            spell.pop("historical_mark", None)
            status = self.spell_status(spell, definition=definition)
            spell["authority_status"] = status
            spell["authority_note"] = (
                "Source needs repair; use this spell with your GM. Automatic benefits are unavailable."
                if status == NEEDS_REPAIR else
                "Conflicting source records need manager attention. Automatic benefits are unavailable."
                if status == NEEDS_ATTENTION else
                "Manager-authorized manual spell." if status == MANUAL else ""
            )
            if status != VERIFIED:
                if status != MANUAL:
                    spell["mark"] = ""
                # A saved mark is historical read context, never an effective
                # spell choice. Match both unique spell identity and source row
                # before exposing it; item and disputed rows stay review-only.
                spell_id = _text(spell.get("id"))
                saved_matches = saved_spells_by_id.get(spell_id, [])
                if (status in {NEEDS_REPAIR, NEEDS_ATTENTION} and spell_id
                        and len(saved_matches) == 1
                        and projected_spell_id_counts.get(spell_id) == 1
                        and not spell.get("item_spell_review_only")
                        and not spell.get("spell_source_review_only")):
                    saved = saved_matches[0]
                    saved_mark = _text(saved.get("mark"))
                    saved_source_id = _text(saved.get("spell_source_row_id"))
                    projected_source_id = _text(spell.get("authority_original_source_row_id")
                                                or spell.get("spell_source_row_id"))
                    saved_class_id = _text(saved.get("class_row_id"))
                    projected_class_id = _text(spell.get("authority_original_class_row_id")
                                               or spell.get("class_row_id"))
                    source_rows = saved_source_rows.get(saved_source_id, [])
                    class_or_feature = bool(
                        (not saved_source_id and saved_class_id
                         and saved_class_row_counts.get(saved_class_id) == 1)
                        or (saved_source_id and len(source_rows) == 1
                            and _text(source_rows[0].get("source_row_kind")).casefold()
                            in {"source", "feature", "feat"})
                    )
                    if (saved_mark.casefold() in {
                            "prepared", "known", "spellbook", "prepared + spellbook",
                    }
                            and _text(saved.get("spell_source_row_kind")).casefold() != "item"
                            and saved_source_id == projected_source_id
                            and saved_class_id == projected_class_id
                            and class_or_feature):
                        spell["historical_mark"] = saved_mark
                original_row_id = _text(spell.pop("authority_original_source_row_id", None))
                if original_row_id:
                    spell["spell_source_row_id"] = original_row_id
                original_class_id = _text(spell.pop("authority_original_class_row_id", None))
                if original_class_id:
                    spell["class_row_id"] = original_class_id
                spell["is_always_prepared"] = False
                spell["is_bonus_known"] = False
                for field in ("spell_access_type", "spell_access_uses", "spell_access_reset_on"):
                    spell.pop(field, None)
                spell.pop("campaign_option_sources", None)
            spell.pop("wizard_ritual_note", None)
            spell_id = _text(spell.get("id"))
            saved = saved_spells_by_id.get(spell_id, [])
            choices = ledger_choices.get(spell_id, [])
            choice = choices[0] if len(choices) == 1 else {}
            if (status == VERIFIED and len(saved) == 1 and projected_spell_id_counts.get(spell_id) == 1
                    and not saved[0].get("spell_source_row_id")
                    and wizard_contexts.get(saved[0].get("class_row_id"), {}).get("ritual") is True
                    and spell_id in self.confirmed_active_spell_choices
                    and choice.get("pool") == "spellbook" and choice.get("ordinary_counted") is True
                    and choice.get("current_usable") is True
                    and dict(saved[0].get("systems_ref") or {}).get("entry_key") in self.native_ritual_spell_keys):
                spell["is_ritual"] = True
                spell["wizard_ritual_note"] = "Wizard spellbook ritual: preparation is not required. Ritual casting is table managed."
            spells.append(spell)
        projected["spells"] = spells
        projected["source_rows"] = [
            row for row in list(projected.get("source_rows") or [])
            if isinstance(row, dict) and (
                _text(row.get("source_row_id")) in self.verified_source_rows
                or self._manual_row_authorized(row, definition)
            )
        ]
        for key, id_key, verified in (
            ("class_rows", "class_row_id", self.verified_class_rows),
            ("source_rows", "source_row_id", self.verified_source_rows),
        ):
            for row in projected.get(key) or []:
                row_id = _text(row.get(id_key))
                # Always replace any historical marker. Only an independently
                # verified per-metric manager action can authorize an override
                # whose saved base is absent.
                row.pop(MISSING_OVERRIDE_AUTHORITY_KEY, None)
                witnessed = {}
                for metric in ("spell_attack_bonus", "spell_save_dc"):
                    authorized = any(self.manual_authorization(
                        record, character_slug=definition.character_slug,
                        target_kind="source_row", target_id=row_id, metric=metric,
                        definition=definition,
                    ) for record in list(dict(definition.spellcasting or {}).get("manual_authorizations") or []))
                    if authorized:
                        witnessed[metric] = VERIFIED_MISSING_OVERRIDE
                    if row_id in verified:
                        continue
                    if not authorized:
                        row[metric] = None
                if witnessed:
                    row[MISSING_OVERRIDE_AUTHORITY_KEY] = witnessed
                if row_id in verified:
                    continue
                row["authority_status"] = MANUAL if self._manual_row_authorized(row, definition) else NEEDS_REPAIR
                row["spell_metric_notes"] = ["Source needs repair; automatic spell math is unavailable."]
        class_rows = list(projected.get("class_rows") or [])
        if len(class_rows) == 1:
            for metric in ("spell_attack_bonus", "spell_save_dc"):
                projected[metric] = class_rows[0].get(metric)
        elif class_rows:
            for metric in ("spell_attack_bonus", "spell_save_dc"):
                projected[metric] = None
        if self.native_grant_view is not None:
            projected = self._native_spell_projection(definition, projected)
        return projected


def _source_row_ids(value: Any) -> set[str]:
    ids: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"spell_source_row_id", "source_row_id"} and isinstance(child, str) and child.strip():
                ids.add(child.strip())
            elif (key in {"source", "spell_source"} and isinstance(child, dict)
                  and _text(child.get("kind") or child.get("row_kind")) in {"item", "source"}
                  and _text(child.get("id"))):
                ids.add(_text(child["id"]))
                ids.update(_source_row_ids(child))
            else:
                ids.update(_source_row_ids(child))
    elif isinstance(value, list):
        for child in value:
            ids.update(_source_row_ids(child))
    return ids


def _current_spell_grant_membership(
    grants: tuple[AuthorityGrant, ...], definition: CharacterDefinition,
    spell_entries: list[Any],
) -> frozenset[tuple[str, str]]:
    """Exact fixed/explicit-option spell membership from current approved owners."""
    from .character_builder_spells import (
        _extract_spell_support_grants, _extract_spell_support_choice_specs_from_value,
        _spell_support_support_kwargs, _iter_unlocked_additional_spell_values,
        _resolve_item_spell_selector,
    )
    from .character_campaign_options import collect_campaign_option_spell_grants
    from .item_spell_support import parse_item_spell_support

    level = sum(int(row.get("level") or 0) for row in profile_class_rows(definition.profile))
    owners = {"feature": {str(row.get("id") or ""): row for row in definition.features if isinstance(row, dict)},
              "item": {str(row.get("id") or ""): row for row in definition.equipment_catalog if isinstance(row, dict)}}
    found: set[tuple[str, str]] = set()
    invalid_item_sources: set[str] = set()
    item_claims: dict[tuple[str, str], list[Any]] = {}
    item_source_behaviors: dict[str, set[tuple[str, ...]]] = {}
    item_spell_catalog = _spell_entries_catalog(spell_entries)
    item_blocks: dict[str, list[Any]] = {}
    for grant in grants:
        if grant.kind != "item":
            continue
        payload = json.loads(grant.payload_json)
        if "spell_support" in payload:
            item_blocks.setdefault(grant.instance_id, []).append(payload["spell_support"])
    invalid_item_owners = {
        instance_id for instance_id, blocks in item_blocks.items()
        if (parsed := parse_item_spell_support(blocks)).diagnostics
        or any(record.invalid for record in parsed.records)
    }
    for grant in grants:
        payload = json.loads(grant.payload_json)
        owner = owners.get(grant.kind, {}).get(grant.instance_id) or {}
        option = owner.get("campaign_option")
        option = option if isinstance(option, dict) else {}
        raw_selected = option.get("selected_choices")
        selected = raw_selected if isinstance(raw_selected, dict) else {}
        selections = [str(value).strip().casefold() for values in selected.values()
                      for value in (values if isinstance(values, list) else []) if str(value).strip()]
        for field, effect in payload.items():
            if field == "spell_support" and isinstance(effect, dict):
                try:
                    if grant.kind == "item":
                        parsed = parse_item_spell_support([effect])
                        if parsed.diagnostics or grant.instance_id in invalid_item_owners:
                            invalid_item_sources.update(
                                source_id for _, source_id, _, _ in parsed.source_declarations if source_id
                            )
                            invalid_item_sources.update(
                                record.source_row_id for record in parsed.records if record.source_row_id
                            )
                        for record in parsed.records:
                            if record.source_row_id:
                                item_source_behaviors.setdefault(record.source_row_id, set()).add((
                                    record.source_row_kind, record.source_row_title,
                                    record.source_ability_key, record.source_mode,
                                    record.spell_list_class_name,
                                ))
                        fixed = [] if parsed.diagnostics or grant.instance_id in invalid_item_owners else [
                            {"value": record.spell_selector, "spell_source_row_id": record.source_row_id,
                             "record": record}
                            for record in parsed.records
                            if not record.invalid and (
                                record.availability is None or record.availability <= max(level, 1)
                            )
                        ]
                    else:
                        fixed = _extract_spell_support_grants([effect], target_level=max(level, 1))
                    raw_choices = (
                        [] if grant.kind == "item" and grant.instance_id in invalid_item_owners else
                        _iter_unlocked_additional_spell_values(
                            effect.get("choices", effect.get("select")), target_level=max(level, 1)
                        )
                    )
                except (TypeError, ValueError):
                    continue
                for spell in fixed:
                    row_id = _text(spell.get("spell_source_row_id") or effect.get("spell_source_row_id"))
                    value = _text(spell.get("value")).casefold()
                    if row_id and value:
                        if grant.kind == "item":
                            entry = _resolve_item_spell_selector(value, item_spell_catalog)
                            if entry is not None:
                                identity = f"systems:{_text(getattr(entry, 'entry_key', '')) or _text(getattr(entry, 'slug', ''))}"
                                found.add((row_id, identity))
                                record = spell["record"]
                                item_claims.setdefault((row_id, identity), []).append(record)
                        else:
                            found.add((row_id, value))
                inherited = _spell_support_support_kwargs(effect)
                for choice in raw_choices:
                    try:
                        specs = _extract_spell_support_choice_specs_from_value(
                            choice, inherited_support_kwargs=inherited,
                        )
                    except (TypeError, ValueError):
                        continue
                    for spec in specs:
                        row_id = _text(spec.get("spell_source_row_id"))
                        options = {_text(value).casefold() for value in list(spec.get("options") or [])}
                        chosen = [value for value in selections if value in options]
                        if row_id and options and len(chosen) <= int(spec.get("count") or 1):
                            if grant.kind == "item":
                                for value in chosen:
                                    entry = _resolve_item_spell_selector(value, item_spell_catalog)
                                    if entry is not None:
                                        found.add((row_id, f"systems:{_text(getattr(entry, 'entry_key', '')) or _text(getattr(entry, 'slug', ''))}"))
                            else:
                                found.update((row_id, value) for value in chosen)
            elif field == "campaign_option" and isinstance(effect, dict):
                row_id = _text(effect.get("spell_source_row_id") or effect.get("source_row_id"))
                if row_id:
                    try:
                        spell_rows = collect_campaign_option_spell_grants([effect])
                    except (TypeError, ValueError):
                        continue
                    for spell in spell_rows:
                        value = _text(spell.get("value")).casefold()
                        if value:
                            found.add((row_id, value))
    conflicting_item_claims: set[tuple[str, str]] = set()
    for claim_key, records in item_claims.items():
        selected_level = max(-1 if record.availability is None else record.availability for record in records)
        selected = [
            record for record in records
            if (-1 if record.availability is None else record.availability) == selected_level
        ]
        if len({
            (record.access_type, record.access_uses, record.access_reset_on,
             record.mark, record.always_prepared, record.bonus_known, record.ritual)
            for record in selected
        }) > 1:
            conflicting_item_claims.add(claim_key)
    invalid_item_sources.update(
        row_id for row_id, behaviors in item_source_behaviors.items() if len(behaviors) > 1
    )
    return frozenset(
        (row_id, value) for row_id, value in found
        if row_id not in invalid_item_sources
        and (row_id, value) not in conflicting_item_claims
    )


def _unambiguous_current_spell_keys(
    candidates: set[tuple[str, str, str]], entries: list[Any],
    pages: dict[str, list[Any]],
) -> frozenset[tuple[str, str]]:
    """Keep a grant key only when one current source owns that spelling."""
    key_owners: dict[str, set[str]] = {}
    catalog = _spell_entries_catalog(entries)
    field = (lambda entry, name: catalog_field(catalog, entry, name)) if native_catalog(entries) is not None else (lambda entry, name: getattr(entry, name, ""))
    for entry in catalog_rows(catalog, raw=True):
        owner = f"systems:{_text(field(entry, 'entry_key')) or _text(field(entry, 'slug'))}"
        for name in (field(entry, "slug"), field(entry, "title")):
            key = _text(name).casefold()
            if key:
                key_owners.setdefault(key, set()).add(owner)
    for ref, matches in pages.items():
        if len(matches) != 1:
            continue
        page = _field(matches[0], "page")
        if _text(_field(page, "section")) not in {"Spells", "Mechanics"}:
            continue
        for name in (ref, _field(page, "title")):
            key = _text(name).casefold()
            if key:
                key_owners.setdefault(key, set()).add(f"page:{ref}")
    return frozenset((spell_id, key) for spell_id, key, owner in candidates
                     if key_owners.get(key) == {owner})


def _source_derived_spell_choice_frames(
    definition: CharacterDefinition, *, systems_service: Any,
    pages: dict[str, list[Any]], verified_class_rows: frozenset[str],
    source_snapshot_digest: str,
    spellbook_ids: frozenset[str] = frozenset(),
) -> dict[str, dict[str, Any]]:
    """Fresh exact local rule facts; the snapshot remains part of every old hash."""
    from .character_builder_catalogs import _load_phb_level_one_spell_lists

    all_class_rows = profile_class_rows(definition.profile)
    class_counts = {row_id: sum(_text(row.get("row_id")) == row_id for row in all_class_rows)
                    for row_id in verified_class_rows}
    class_rows = {_text(row.get("row_id")): row for row in all_class_rows
                  if _text(row.get("row_id")) in verified_class_rows
                  and class_counts.get(_text(row.get("row_id"))) == 1}
    spells = [row for row in list(dict(definition.spellcasting or {}).get("spells") or [])
              if isinstance(row, dict) and _text(row.get("id"))]
    counts = {spell_id: sum(_text(row.get("id")) == spell_id for row in spells)
              for spell_id in {_text(row.get("id")) for row in spells}}
    frames: dict[str, dict[str, Any]] = {}
    book_rules = {}
    reconstructed = isinstance(definition.source.get("native_reconstruction_choices"), dict)
    eligibility = _reconstructed_spell_choice_eligibility(
        definition, class_rows, systems_service, enforce_capacity=False) if reconstructed else {}
    current_book_eligibility = _reconstructed_spell_choice_eligibility(
        definition, class_rows, systems_service, enforce_capacity=False,
        current_wizard_preparation=True) if reconstructed and spellbook_ids else {}
    for spell in spells:
        from .character_spell_grants import native_class_choice_state
        try:
            choice_state = native_class_choice_state(spell)
        except ValueError:
            continue
        spell_id = _text(spell.get("id"))
        row_id = _text(spell.get("class_row_id"))
        class_row = class_rows.get(row_id)
        if (counts[spell_id] != 1 or class_row is None or _text(spell.get("spell_source_row_id"))):
            continue
        if reconstructed and spell_id not in eligibility and choice_state != "retired":
            continue
        if reconstructed and spell_id in spellbook_ids and spell_id not in current_book_eligibility and choice_state != "retired":
            continue
        class_name = _text(class_row.get("class_name") or dict(class_row.get("systems_ref") or {}).get("title"))
        class_source_kind, class_source_key = _source_identity(class_row)
        spell_source_kind, spell_source_key = _source_identity(spell)
        class_meta, class_reason = _current_payload(
            campaign_slug=definition.campaign_slug, kind="class",
            source_kind=class_source_kind, source_key=class_source_key,
            systems_service=systems_service, pages=pages,
            expected_slug=_text(dict(class_row.get("systems_ref") or {}).get("slug")),
        )
        spell_meta, spell_reason = _current_payload(
            campaign_slug=definition.campaign_slug, kind="spell",
            source_kind=spell_source_kind, source_key=spell_source_key,
            systems_service=systems_service, pages=pages,
            expected_slug=_text(dict(spell.get("systems_ref") or {}).get("slug")),
        )
        if class_reason or spell_reason or class_meta is None or spell_meta is None or not class_name:
            continue
        try:
            spell_level = int(spell_meta.get("level"))
        except (TypeError, ValueError):
            continue
        class_lists = spell_meta.get("class_lists")
        listed = isinstance(class_lists, dict) and any(
            class_name.casefold() in {_text(name).casefold() for name in names if _text(name)}
            for names in class_lists.values() if isinstance(names, list)
        )
        if not listed:
            phb_lists = dict(_load_phb_level_one_spell_lists() or {})
            title = _text(dict(spell.get("systems_ref") or {}).get("title") or spell.get("name"))
            listed = title in list(dict(phb_lists.get(class_name) or {}).get(str(spell_level)) or [])
        automatic = reconstructed and spell_id in eligibility and any(
            row["id"] == spell_id and (row["always"] or row.get("bonus")) for row in eligibility[spell_id]["selections"])
        if not listed and not automatic:
            continue
        basis = {
            "source_snapshot": source_snapshot_digest,
            "class_row": class_row, "class_source": class_meta,
            "spell_source": spell_meta, "spell_id": spell_id,
            "spell_source_key": spell_source_key, "spell_level": spell_level,
        }
        if spell_id in spellbook_ids:
            from .character_wizard_rules import spellbook_rule_basis
            if row_id not in book_rules:
                book_rules[row_id] = spellbook_rule_basis(definition, class_row, systems_service)
            rules = book_rules[row_id]
            if rules is None:
                continue
            basis["wizard_spellbook_rules"] = rules
        if reconstructed and choice_state is None:
            basis.pop("source_snapshot")
            basis["retained_selection_eligibility"] = eligibility[spell_id]
        frames[f"spell_choice:{spell_id}"] = basis
    return frames


def _source_derived_spell_choice_bases(
    definition: CharacterDefinition, *, systems_service: Any,
    pages: dict[str, list[Any]], verified_class_rows: frozenset[str],
    source_snapshot_digest: str,
) -> dict[str, str]:
    """Preserve the existing persisted basis recipe and digest format."""
    return {target: numeric_value_digest(frame) for target, frame in
        _source_derived_spell_choice_frames(definition, systems_service=systems_service,
            pages=pages, verified_class_rows=verified_class_rows,
            source_snapshot_digest=source_snapshot_digest).items()}


def _historical_choice_source_matches(definition, raw, marker, decisions, witnesses, frame):
    """Require the old audited hash to prove the SAME fresh local dependencies.

    Only the unrelated global snapshot may differ. This never creates or
    replaces a marker, source receipt, transition or current source fact.
    """
    from .character_source_repair import NativeSpellChoiceDecision, _sha256_hex
    if (type(frame) is not dict or "source_snapshot" not in frame
            or not _sha256_hex(frame["source_snapshot"])):
        return False
    matched = [w for w in decisions if type(w) is NativeSpellChoiceDecision
        and w.matches(raw, marker) and w.origin[:2] == (
            definition.campaign_slug, definition.character_slug)]
    if (not matched or any(not _sha256_hex(w.get("source_snapshot_digest"))
            or any(type(value) is not int or value < 1 for value in w.origin[2:]) for w in matched)):
        return False
    snapshots = {w["source_snapshot_digest"] for w in matched}
    paired = [w for w in witnesses if type(w) is dict
        and w.get("authorization") == marker and "transition_proof" not in w]
    if (len(snapshots) != 1 or not paired
            or any(not _sha256_hex(w.get("source_basis_digest")) for w in paired)):
        return False
    bases = {w["source_basis_digest"] for w in paired}
    if len(bases) != 1:
        return False
    old = dict(frame)
    old["source_snapshot"] = next(iter(snapshots))
    return numeric_value_digest(old) == next(iter(bases))


def _current_fixed_spell_grant_frame(selected_class, selected_subclass, features, catalog, level):
    """Read only the supported fixed automatic slice with complete flag coverage.

    None means unproved, distinct from a complete empty frame. Importer-defined
    top-level null containers mean absent; null leaves/flags never mean false.
    Literal publication identity survives every resolution step.
    """
    import re
    from .character_builder_spells import (
        _inferred_always_prepared_spell_evidence, _inferred_bonus_cantrip_spell_evidence,
        _literal_spell_reference, _resolve_spell_entry,
    )
    prepared, known = set(), set()
    visited = 0
    ap_fields = {"is_always_prepared", "always_prepared", "isAlwaysPrepared", "alwaysPrepared", "prepared"}
    bk_fields = {"bonus_known", "is_bonus_known"}
    flag_fields = ap_fields | bk_fields | {"ritual", "is_ritual"}
    reference_fields = {"spell", "value", "title", "slug"}

    def fail():
        raise ValueError("Automatic spell source is outside the complete fixed-grant slice.")

    def visit(depth):
        nonlocal visited
        visited += 1
        if depth > 16 or visited > 2048:
            fail()

    def literal(value, exact_kind=None):
        if not isinstance(value, str) or not value.strip():
            fail()
        value = value.strip()
        tag = re.fullmatch(r"\{@spell ([^}]+)\}", value)
        if tag:
            value = tag.group(1)
        if "#" in value or "{" in value or "}" in value:
            fail()
        if exact_kind is not None:
            if exact_kind != "slug":
                fail()
            entry = catalog_index(catalog, "by_slug", required=True).get(value)
            if entry is None:
                fail()
            selector = entry.entry_key
        elif value.startswith("source-spell:"):
            parts = value.split(":", 2)
            if len(parts) != 3 or not parts[1].strip() or not parts[2].strip():
                fail()
            selector = value
        else:
            parts = value.split("|")
            if len(parts) > 3 or not parts[0].strip():
                fail()
            selector = _literal_spell_reference(value)
        entry = _resolve_spell_entry(selector, catalog)
        if (entry is None or entry.entry_type != "spell"
                or catalog_index(catalog, "by_entry_key", required=True).get(entry.entry_key) != entry
                or catalog_index(catalog, "by_slug", required=True).get(entry.slug) != entry
                or type(entry.metadata.get("level")) is not int
                or not 0 <= entry.metadata["level"] <= 9):
            fail()
        return entry.slug

    def aliases(metadata, left, right):
        values = [metadata[key] for key in (left, right) if key in metadata and metadata[key] is not None]
        if len(values) == 2 and _canonical(values[0]) != _canonical(values[1]):
            fail()
        if not values:  # The importer writes None for an absent raw additionalSpells field.
            return []
        if not isinstance(values[0], list):
            fail()
        return values[0]

    def unlocked(raw):
        if not isinstance(raw, dict):
            fail()
        for key, value in raw.items():
            if key == "_":
                yield value
                continue
            if type(key) is int:
                unlock = key
            elif isinstance(key, str) and re.fullmatch(r"(?:0|[1-9][0-9]?)", key):
                unlock = int(key)
            else:
                fail()
            if not 0 <= unlock <= 20:
                fail()
            if unlock <= level:
                yield value

    def additional_values(value, ap, bk, depth=0, resolve=literal):
        visit(depth)
        if isinstance(value, str):
            key = resolve(value)
            if ap:
                prepared.add(key)
            if bk:
                known.add(key)
        elif isinstance(value, list):
            for child in value:
                additional_values(child, ap, bk, depth + 1, resolve)
        elif isinstance(value, dict) and value and set(value) <= {"_", "all"}:
            for child in value.values():
                additional_values(child, ap, bk, depth + 1, resolve)
        else:
            fail()

    def additional_block(block, resolve=literal):
        if (not isinstance(block, dict) or set(block) - {"name", "prepared", "known"}
                or not {"prepared", "known"} & set(block)
                or "name" in block and not isinstance(block["name"], str)):
            fail()
        for field in ("prepared", "known"):
            if field in block:
                for value in unlocked(block[field]):
                    additional_values(value, field == "prepared", field == "known", resolve=resolve)

    def flags(row, inherited):
        result = dict(inherited)
        for names, label in ((ap_fields, "ap"), (bk_fields, "bk"), ({"ritual", "is_ritual"}, "ritual")):
            values = [row[key] for key in names if key in row]
            if any(type(value) is not bool for value in values) or len(set(values)) > 1:
                fail()
            if values:
                if label in result and result[label] != values[0]:
                    fail()
                result[label] = values[0]
        for field in ("category", "kind"):
            if field in row:
                if not isinstance(row[field], str) or row[field].casefold() != "prepared":
                    fail()
                if result.get("ap") is False:
                    fail()
                result["ap"] = True
        if "mark" in row:
            mark = row["mark"]
            if not isinstance(mark, str) or mark.casefold() not in {"", "granted", "prepared", "known", "cantrip"}:
                fail()
            if mark.casefold() in {"known", "cantrip"}:
                if result.get("bk") is False:
                    fail()
                result["bk"] = True
        return result

    def support_values(value, inherited, depth=0):
        visit(depth)
        if isinstance(value, list):
            for child in value:
                support_values(child, inherited, depth + 1)
            return
        if isinstance(value, str):
            keys, selected = [literal(value)], inherited
        elif isinstance(value, dict):
            if set(value) - (reference_fields | flag_fields | {"_", "mark", "category", "kind"}):
                fail()
            selected = flags(value, inherited)
            if "_" in value:
                support_values(value["_"], selected, depth + 1)
            keys = [literal(value[field], "slug" if field == "slug" else None)
                    for field in reference_fields if field in value]
            if not keys:
                if "_" not in value:
                    fail()
                return
            if len(set(keys)) != 1:
                fail()
        else:
            fail()
        if selected.get("ap", False):
            prepared.add(keys[0])
        if selected.get("bk", False):
            known.add(keys[0])

    try:
        owners = [entry for entry in (selected_class, selected_subclass, *features) if entry is not None]
        for owner in owners:
            for block in aliases(owner.metadata, "additional_spells", "additionalSpells"):
                additional_block(block)
            for block in aliases(owner.metadata, "spell_support", "spellSupport"):
                if (not isinstance(block, dict)
                        or set(block) - (flag_fields | {"grants", "fixed", "name", "mark", "category", "kind"})
                        or not {"grants", "fixed"} & set(block)
                        or "name" in block and not isinstance(block["name"], str)):
                    fail()
                if "grants" in block and "fixed" in block and _canonical(block["grants"]) != _canonical(block["fixed"]):
                    fail()
                inherited = flags(block, {})
                for value in unlocked(block["grants"] if "grants" in block else block["fixed"]):
                    support_values(value, inherited)
        feature_entries = [{"entry": entry} for entry in features]
        inferred = _inferred_always_prepared_spell_evidence(feature_entries)
        inferred += _inferred_bonus_cantrip_spell_evidence(feature_entries, selected_class=selected_class)
        for evidence in inferred:
            # Legacy inference may return titles. Recover a table/prose tag's
            # declared edition before resolving that title, never after a
            # unique other-edition catalogue match has already been chosen.
            from .repository import normalize_lookup
            references = {}
            def collect(value, depth=0):
                visit(depth)
                if isinstance(value, str):
                    for match in re.finditer(r"\{@spell ([^}]+)\}", value):
                        raw = match.group(1)
                        references.setdefault(normalize_lookup(raw.split("|", 1)[0]), []).append(raw)
                elif isinstance(value, list):
                    for child in value:
                        collect(child, depth + 1)
                elif isinstance(value, dict):
                    for child in value.values():
                        collect(child, depth + 1)
            collect(evidence["owners"][0].body.get("entries"))
            def inferred_literal(value):
                if not isinstance(value, str):
                    fail()
                if value.startswith("source-spell:"):
                    return literal(value)
                tag = re.fullmatch(r"\{@spell ([^}]+)\}", value.strip())
                if tag or "|" in value:
                    return literal(value)
                exact = {literal(raw) for raw in references.get(normalize_lookup(value), [])}
                if len(exact) > 1:
                    fail()
                return next(iter(exact)) if exact else literal(value)
            additional_block(evidence["block"], inferred_literal)
        return {"prepared": frozenset(prepared), "known": frozenset(known)}
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def current_native_automatic_spell_origins(definition, systems_service):
    """Derive deterministic grants from current attained owners, never flags.

    This supplies source facts for an explicit correction, not a witness or an
    elective selection. Ordinary spell-choice basis construction is unchanged.
    """
    from .character_builder_catalogs import _build_spell_catalog
    from .character_builder_spells import _spell_payload_key
    collector = getattr(systems_service, "collect_attained_deterministic_feature_entries", None)
    loader = getattr(systems_service, "list_enabled_entries_for_campaign", None)
    if not callable(collector) or not callable(loader):
        return {}
    catalog = build_read_spell_catalog(systems_service, definition.campaign_slug)
    if catalog is None:
        catalog = _build_spell_catalog(loader(definition.campaign_slug, entry_type="spell"))
    rows = profile_class_rows(definition.profile)
    spells = definition.spellcasting.get("spells")
    if not isinstance(spells, list):
        return {}

    def exact(ref, kind):
        if not isinstance(ref, dict) or not ref.get("entry_key"):
            return None
        entry = systems_service.get_entry_for_campaign(definition.campaign_slug, ref["entry_key"])
        if entry is None or entry.entry_type != kind or any(
                ref.get(key) and ref[key] != getattr(entry, key, None)
                for key in ("entry_key", "entry_type", "slug", "source_id", "title", "library_slug")):
            return None
        return entry

    def source(entry):
        return {"entry_key": entry.entry_key, "entry_type": entry.entry_type,
                "source_id": entry.source_id, "library_slug": getattr(entry, "library_slug", None),
                "metadata": deepcopy(entry.metadata), "body": deepcopy(entry.body)}

    result = {}
    for row in rows:
        row_id, level = row.get("row_id"), row.get("level")
        if (not row_id or sum(other.get("row_id") == row_id for other in rows) != 1
                or type(level) is not int or not 1 <= level <= 20):
            continue
        cls = exact(row.get("systems_ref"), "class")
        subclass = _current_reconstruction_subclass(definition, row, cls, systems_service)
        if cls is None or row.get("subclass_ref") and subclass is None:
            continue
        owners = {entry.entry_key: entry for entry in (cls, subclass) if entry is not None}
        attained = {}
        for owner in tuple(owners.values()):
            for entry in collector(definition.campaign_slug, owner, attained_level=level,
                                   selected_feature_branches={}):
                attained[entry.entry_key] = entry
        owners.update(attained)
        grants = _current_fixed_spell_grant_frame(cls, subclass, list(attained.values()), catalog, level)
        if grants is None:
            continue
        prepared, known = grants["prepared"], grants["known"]
        chain = {"class_row": deepcopy(row), "attained_level": level,
                 "owners": [source(owners[key]) for key in sorted(owners)]}
        for spell in spells:
            if (not isinstance(spell, dict) or spell.get("class_row_id") != row_id
                    or spell.get("spell_source_row_id") or spell.get("page_ref")):
                continue
            entry = exact(spell.get("systems_ref"), "spell")
            spell_id = spell.get("id")
            if (entry is None or not spell_id
                    or catalog_index(catalog, "by_entry_key", required=True).get(entry.entry_key) != entry
                    or catalog_index(catalog, "by_slug", required=True).get(entry.slug) != entry
                    or type(entry.metadata.get("level")) is not int
                    or sum(isinstance(other, dict) and other.get("id") == spell_id for other in spells) != 1
                    or sum(isinstance(other, dict) and other.get("class_row_id") == row_id
                           and dict(other.get("systems_ref") or {}).get("entry_key") == entry.entry_key
                           for other in spells) != 1):
                continue
            key = _spell_payload_key(spell)
            if key not in prepared and key not in known:
                continue
            result[spell_id] = {"kind": "deterministic_automatic_grant", "class_row_id": row_id,
                "entry_key": entry.entry_key, "always_prepared": key in prepared, "bonus_known": key in known,
                "owners": sorted(owners), "source_chain_digest": numeric_value_digest({
                    **chain, "spell_source": source(entry)})}
    return result


def _reconstructed_spell_choice_eligibility(definition, class_rows, systems_service, *, enforce_capacity=True,
                                           current_wizard_preparation=False):
    """Bound imported class choices by the same current native progression.

    Unattained/over-capacity observations remain in the definition, but receive
    no choice witness. Spellbook copying has no progression maximum; preparation
    and access still require the current class level and exact list membership.
    Feature/source-row grants are independently authenticated elsewhere.
    """
    from .character_builder_foundation import _effective_spellcasting_profile_for_row
    from .character_builder_derivation import (
        _prepared_spell_count_for_level, _spell_slot_progression_for_class_level,
        _spell_progression_value,
    )
    from .character_builder_spells import _spell_mark_tokens, _spell_payload_key
    raw_spells = definition.spellcasting.get("spells")
    if not isinstance(raw_spells, list) or systems_service is None:
        return {}
    from .character_spell_grants import has_native_grants, native_grant_spell_ids
    migrated = has_native_grants(definition)
    try:
        fixed_spell_ids = native_grant_spell_ids(definition) if migrated else frozenset()
    except ValueError:
        return {}
    scores = {key: dict(definition.stats.get("ability_scores", {}).get(key) or {}).get("score")
              for key in ("str", "dex", "con", "int", "wis", "cha")}
    scores_complete = all(type(value) is int for value in scores.values())
    if enforce_capacity and not scores_complete:
        return {}
    result = {}
    def exact(ref, kind):
        if not isinstance(ref, dict) or not ref.get("entry_key"):
            return None
        entry = systems_service.get_entry_for_campaign(definition.campaign_slug, ref["entry_key"])
        if entry is None or entry.entry_type != kind or any(
                ref.get(key) and ref[key] != getattr(entry, key, None)
                for key in ("entry_key", "slug", "source_id", "entry_type")):
            return None
        return entry
    for row_id, row in class_rows.items():
        cls = exact(row.get("systems_ref"), "class")
        subclass = _current_reconstruction_subclass(definition, row, cls, systems_service) if cls is not None else None
        level = row.get("level")
        if cls is None or type(level) is not int or not 1 <= level <= 20 or row.get("subclass_ref") and subclass is None:
            continue
        options = {"selected_class": cls, "selected_subclass": subclass}
        profile = _effective_spellcasting_profile_for_row(cls.title, row_level=level, **options)
        if not profile:
            continue
        from .character_builder_foundation import _spellcasting_mode_from_progression
        current_wizard = current_wizard_preparation and _spellcasting_mode_from_progression(profile) == "wizard"
        slots = _spell_slot_progression_for_class_level(cls.title, level, **options)
        maximum = max((slot.get("level", 0) for slot in slots if type(slot.get("level")) is int), default=0)
        cantrip_limit = _spell_progression_value(cls.title, "cantrip_progression", level, **options)
        known_limit = _spell_progression_value(cls.title, "spells_known_progression", level, **options)
        prepared_limit = _prepared_spell_count_for_level(cls.title, scores, level, **options) if scores_complete else None
        automatic_keys = frozenset()
        bonus_keys = frozenset()
        collector = getattr(systems_service, "collect_attained_deterministic_feature_entries", None)
        attained_entries = {}
        if callable(collector):
            for owner in (cls, subclass):
                if owner is not None:
                    for feature in collector(definition.campaign_slug, owner, attained_level=level,
                                             selected_feature_branches={}):
                        attained_entries[feature.entry_key] = feature
        loader = getattr(systems_service, "list_enabled_entries_for_campaign", None)
        if not migrated and any(isinstance(spell, dict) and spell.get("class_row_id") == row_id and (
                spell.get("is_bonus_known") is True or spell.get("is_always_prepared") is True
                or spell.get("always_prepared") is True) for spell in raw_spells):
            from .character_builder_catalogs import _build_spell_catalog
            if callable(loader) and callable(collector):
                catalog = build_read_spell_catalog(systems_service, definition.campaign_slug)
                if catalog is None:
                    catalog = _build_spell_catalog(loader(definition.campaign_slug, entry_type="spell"))
                grants = _current_fixed_spell_grant_frame(cls, subclass, list(attained_entries.values()), catalog, level)
                if grants is not None:
                    automatic_keys, bonus_keys = grants["prepared"], grants["known"]
        selections = []
        retired_selection_ids = set()
        for spell in raw_spells:
            if (not isinstance(spell, dict) or spell.get("class_row_id") != row_id
                    or spell.get("spell_source_row_id")):
                continue
            from .character_spell_grants import native_class_choice_state
            try:
                choice_state = native_class_choice_state(spell)
            except ValueError:
                continue
            if choice_state == "retired":
                retired_selection_ids.add(spell.get("id"))
            entry = exact(spell.get("systems_ref"), "spell")
            if entry is None or type(entry.metadata.get("level")) is not int:
                continue
            spell_level = entry.metadata["level"]
            tokens = _spell_mark_tokens(spell.get("mark"))
            prepared = spell.get("is_prepared", spell.get("prepared", "prepared" in tokens))
            if current_wizard:
                from .character_spell_reconstruction import _marks as checkpoint_marks
                try:
                    tokens, prepared = checkpoint_marks(spell)
                except (TypeError, ValueError):
                    continue
            always = spell.get("always_prepared", spell.get("is_always_prepared", False))
            bonus = spell.get("is_bonus_known", False)
            if choice_state == "active":
                # Historical aggregate flags are not the independent elective path.
                always, bonus = False, False
            if type(prepared) is not bool or type(always) is not bool or type(bonus) is not bool:
                continue
            if (len({spell[key] for key in ("is_prepared", "prepared") if type(spell.get(key)) is bool}) > 1
                    or len({spell[key] for key in ("always_prepared", "is_always_prepared") if type(spell.get(key)) is bool}) > 1
                    or "prepared" in tokens and prepared is False):
                continue
            # An always-prepared exception needs its actual feature grant; it
            # cannot be authenticated merely by a retained true marker.
            if always and _spell_payload_key(spell) not in automatic_keys:
                continue
            if bonus and _spell_payload_key(spell) not in bonus_keys:
                continue
            selections.append({"id": spell.get("id"), "entry_key": entry.entry_key,
                "level": spell_level, "prepared": prepared, "always": always, "bonus": bonus})
        cantrips = [spell for spell in selections if spell["id"] not in retired_selection_ids and spell["level"] == 0 and not spell["always"] and not spell["bonus"]]
        prepared = [spell for spell in selections if spell["id"] not in retired_selection_ids and spell["level"] > 0 and spell["prepared"] and not spell["always"]]
        leveled = [spell for spell in selections if spell["id"] not in retired_selection_ids and spell["level"] > 0 and not spell["always"] and not spell["bonus"]]
        duplicated = {spell["entry_key"] for spell in selections
                      if sum(other["entry_key"] == spell["entry_key"] for other in selections) != 1}
        frame = {"class_row": row, "profile": profile, "scores": scores,
                 "selections": selections, "cantrip_limit": cantrip_limit,
                 "known_limit": known_limit, "prepared_limit": prepared_limit, "maximum_spell_level": maximum,
                 "automatic_prepared_keys": sorted(automatic_keys)}
        frame["automatic_bonus_known_keys"] = sorted(bonus_keys)
        if subclass is not None:
            frame["subclass_source"] = {"entry_key": subclass.entry_key, "metadata": subclass.metadata, "body": subclass.body}
        if automatic_keys or bonus_keys:
            if not callable(collector):
                continue
            automatic_sources = {}
            for owner in (cls, subclass):
                if owner is None:
                    continue
                for feature in collector(definition.campaign_slug, owner, attained_level=level,
                                         selected_feature_branches={}):
                    attained_entries[feature.entry_key] = feature
                    if any(feature.metadata.get(key) for key in ("additional_spells", "spell_support", "spell_manager", "campaign_option")):
                        automatic_sources[feature.entry_key] = {"metadata": feature.metadata, "body": feature.body}
            from .character_builder_spells import _inferred_always_prepared_spell_evidence, _inferred_bonus_cantrip_spell_evidence
            feature_entries = [{"entry": entry} for entry in attained_entries.values()]
            inferred = _inferred_always_prepared_spell_evidence(feature_entries)
            inferred += _inferred_bonus_cantrip_spell_evidence(feature_entries, selected_class=cls)
            for evidence in inferred:
                for owner in evidence["owners"]:
                    automatic_sources[owner.entry_key] = {"metadata": owner.metadata, "body": owner.body}
            frame["automatic_sources"] = automatic_sources
        for spell in selections:
            if (spell["id"] in retired_selection_ids or not spell["id"] or enforce_capacity and spell["entry_key"] in duplicated or not 0 <= spell["level"] <= maximum
                    or enforce_capacity and not spell["always"] and (spell["level"] == 0 and len(cantrips) > cantrip_limit
                        or spell["level"] > 0 and known_limit and len(leveled) > known_limit
                        or spell["prepared"] and spell["level"] > 0 and len(prepared) > prepared_limit)):
                continue
            result[spell["id"]] = frame
    return result


def class_choice_retention_ids(definition):
    """Retain observations, including unproved origins; this grants no benefit."""
    from .character_spell_grants import has_native_grants
    if not has_native_grants(definition):
        return frozenset()
    return frozenset(_text(row.get("id")) for row in definition.spellcasting.get("spells", [])
        if isinstance(row, dict) and _text(row.get("id"))
        and not _text(row.get("spell_source_row_id")))


def _qualified_spell_capacity_scores(authority, definition, state, *, validated_inputs=None,
                                     formula_scope="current"):
    """Bind only ability/effect adapters, without spell projection or authority recursion."""
    from .character_ability_inputs import input_records, resolve_inputs
    from .character_adjustments import apply_recoverable_ability_score_penalties
    from .character_builder_derivation import (
        _campaign_option_feat_selections_from_features, _campaign_option_feat_selected_choices_from_features,
        _apply_feat_ability_score_bonuses, _structured_ability_score_minimums,
        _apply_item_effect_ability_score_minimums,
    )
    context = authority._numeric_context(definition, state, formula_scope=formula_scope)
    if not context["valid"]:
        return {}
    features = []
    for raw in definition.features:
        if not isinstance(raw, dict) or authority.status_for("feature", _text(raw.get("id"))) != VERIFIED:
            continue
        row = {"id": raw.get("id"), "page_ref": deepcopy(raw.get("page_ref")),
            **authority.approved_payload("feature", _text(raw.get("id")))}
        option = row.get("campaign_option")
        if isinstance(option, dict) and isinstance(raw.get("campaign_option"), dict):
            option["selected_choices"] = deepcopy(raw["campaign_option"].get("selected_choices", {}))
        features.append(row)
    bonuses = _apply_feat_ability_score_bonuses({key: 0 for key in ("str", "dex", "con", "int", "wis", "cha")},
        feat_selections=_campaign_option_feat_selections_from_features(features),
        selected_choices=_campaign_option_feat_selected_choices_from_features(features), strict=False)
    minimums = _structured_ability_score_minimums(features)
    minimums = _apply_item_effect_ability_score_minimums(
        {key: int(minimums.get(key, 0)) for key in ("str", "dex", "con", "int", "wis", "cha")},
        item_effect_entries=authority.active_item_effect_entries(definition))
    records = input_records(definition.stats)
    scores, resolved = resolve_inputs(definition.stats, bonuses=bonuses, minimums=minimums)
    scores = apply_recoverable_ability_score_penalties(scores, definition.stats.get("recoverable_penalties"))
    result, final_scores = {}, set()
    for key in ("str", "dex", "con", "int", "wis", "cha"):
        status = authority.field_status(f"stats.ability_scores.{key}.score")
        approved = status.status in {VERIFIED, MANUAL} and (
            status.is_effective or status.reason == "baseline_authorized")
        if validated_inputs is not None:
            approved = status.status != CONFLICT and key in validated_inputs
        if approved and status.is_effective and status.reason != "baseline_authorized" and type(status.effective) is int:
            # Match suppress_unknown_numbers: an authorized final total takes
            # precedence over durable base records and transient candidates.
            result[key] = status.effective
            final_scores.add(key)
        elif (approved and key in records and records[key].get("stage") in {"base", "pre_penalty"}
                and records[key].get("provenance") not in {
                    "unambiguous_legacy_inverse", "legacy_lossy_output", "changed_lossy_layer"}
                and resolved.get(key, {}).get("stage") in {"base", "pre_penalty"}
                and type(scores.get(key)) is int):
            result[key] = scores[key]
    from .character_builder_derivation import _transient_ability_score_overrides
    for key in tuple(result):
        if f"stats.ability_scores.{key}.score" in context["blocked"] and key not in final_scores:
            result.pop(key)
    transient = context["effects"]
    for key, value in _transient_ability_score_overrides(transient.get("ability_score_overrides")).items():
        if key in result and key not in final_scores:
            result[key] = value
    return result


def _spell_reconstruction_roles(definition, witnesses, pending=None):
    """Detached role facts; never decode a stored/plain dictionary as custody."""
    from .character_spell_reconstruction import NativeSpellReconstructionFact, PendingSpellCheckpoint
    rows = {row.get("id"): row for row in definition.spellcasting.get("spells", []) if isinstance(row, dict)}
    found = {}
    for fact in witnesses:
        if type(fact) is not NativeSpellReconstructionFact or type(fact.get("target_id")) is not str:
            continue
        identity = fact["target_id"].removeprefix("spell_choice:")
        if (identity not in rows or not fact.matches(rows[identity])
                or fact.origin[:2] != (definition.campaign_slug, definition.character_slug)):
            continue
        prior = found.get(identity)
        stamp = (fact.origin[4], fact.origin[2])
        value = (fact["role"], fact["spell_level"])
        if prior is None or stamp > prior[0]:
            found[identity] = (stamp, value)
        elif stamp == prior[0] and value != prior[1]:
            raise ValueError("The durable spell reconstruction role is ambiguous.")
    if pending is not None:
        if type(pending) is not PendingSpellCheckpoint or not pending.matches_definition(definition):
            raise ValueError("The prospective spell checkpoint changed its exact scope.")
        for entry in pending.checkpoint["entries"]:
            raw = rows.get(entry["spell_id"])
            if raw is None or pending.role_for(raw) != entry["role"]:
                raise ValueError("The prospective spell checkpoint has an unavailable row.")
            found[entry["spell_id"]] = ((pending.checkpoint["prior_generation"] + 1, 0), (entry["role"], entry["spell_level"]))
    return tuple((identity, *found[identity][1]) for identity in sorted(found))


def _spellbook_basis_ids(definition, witnesses, pending=None):
    """Historical immutable membership selects a recipe, never current custody."""
    from .character_spell_reconstruction import NativeSpellReconstructionFact
    result = {raw["id"] for raw in definition.spellcasting.get("spells", []) if type(raw) is dict
        and any(type(fact) is NativeSpellReconstructionFact and fact.matches_membership(raw)
            and fact.origin[:2] == (definition.campaign_slug, definition.character_slug) for fact in witnesses)}
    if pending is not None:
        # The ordinary role validator owns issuer, complete scope and ambiguity.
        result.update(identity for identity, role, _level in
            _spell_reconstruction_roles(definition, (), pending) if role == "book")
    return frozenset(result)


def _prepared_reconstruction_owners(definition, service, verified_rows):
    from .character_builder_foundation import _spellcasting_mode_for_class
    result = set()
    for row in profile_class_rows(definition.profile):
        identity, ref = row.get("row_id"), row.get("systems_ref", {})
        if identity not in verified_rows or not isinstance(ref, dict):
            continue
        entry = _current_systems_entry(definition.campaign_slug, "systems", ref.get("entry_key", ""), service)
        subclass = _current_reconstruction_subclass(definition, row, entry, service) if entry is not None else None
        if (entry is not None and entry.entry_type == "class" and (not row.get("subclass_ref") or subclass is not None)
                and _spellcasting_mode_for_class(entry.title, row_level=row.get("level"), selected_class=entry,
                    selected_subclass=subclass) == "prepared"):
            result.add(identity)
    return result


def _validated_spell_checkpoint_result(result, prior_record, candidate, state, actor_id, systems_service):
    from .character_native_requalification import NativeRequalification
    from .character_spell_reconstruction import PendingSpellCheckpoint, validate_saved_spell_checkpoint
    from .character_source_reads import phase_of
    if (type(result) is not NativeRequalification or type(result.spell_checkpoint) is not PendingSpellCheckpoint
            or result.candidate.to_dict() != candidate.to_dict() or state != prior_record.state_record.state
            or result.provenance.get("schema_version") not in {5, 6}):
        raise ValueError("Current spell confirmation needs its exact native issuer-bound result.")
    checkpoint = result.spell_checkpoint
    data = checkpoint.checkpoint
    result.validate_binding(prior_record, actor_id, data["action_id"], source_read_phase=phase_of(systems_service))
    if (not checkpoint.matches_definition(candidate) or data["actor_id"] != actor_id
            or data["prior_generation"] != prior_record.committed_revision
            or data["prior_state_revision"] != prior_record.state_record.revision
            or result.provenance["spell_origin_plan"].get("current_checkpoint") != data):
        raise ValueError("The current spell confirmation no longer matches its original target.")
    validate_saved_spell_checkpoint(prior_record.definition, candidate, data)
    return checkpoint


def ordinary_native_spell_choice_state(raw, marker=None, *, verified_numeric_actions=()):
    """Positive ordinary origin, independent of numeric/model/source custody."""
    from .character_source_repair import NativeSpellChoiceDecision
    if not isinstance(marker, dict):
        return UNKNOWN
    states = {w.get("state") for w in verified_numeric_actions
        if type(w) is NativeSpellChoiceDecision and w.matches(raw, marker)}
    return next(iter(states)) if len(states) == 1 else UNKNOWN


def native_spell_choice_birth_is_absent(prior_definition, raw, *, candidate_definition=None):
    """A renamed observation or preexisting marker is never a native birth."""
    if not isinstance(raw, dict) or not _text(raw.get("id")) or not _text(raw.get("class_row_id")):
        return False
    spell_id, row_id = raw["id"], raw["class_row_id"]
    ref = raw.get("systems_ref")
    if not isinstance(ref, dict) or not ref.get("entry_key") or not ref.get("source_id"):
        return False
    rows = prior_definition.spellcasting.get("spells", [])
    markers = prior_definition.source.get("source_authorizations", [])
    if (not isinstance(rows, list) or not isinstance(markers, list)
            or any(not isinstance(marker, dict) for marker in markers)
            or any(not isinstance(row, dict) for row in rows)
            or len({_text(row.get("id")) for row in rows}) != len(rows)):
        return False
    if candidate_definition is not None:
        proposed = candidate_definition.spellcasting.get("spells", [])
        if not isinstance(proposed, list) or any(not isinstance(row, dict) for row in proposed):
            return False
        if not {_text(row.get("id")) for row in rows} <= {_text(row.get("id")) for row in proposed}:
            return False
    for old in rows:
        if not isinstance(old, dict) or not _text(old.get("id")):
            return False
        old_ref = old.get("systems_ref")
        if old.get("id") == spell_id or (old.get("class_row_id") == row_id
                and not old.get("spell_source_row_id") and isinstance(old_ref, dict)
                and (old_ref.get("entry_key"), old_ref.get("source_id"))
                    == (ref["entry_key"], ref["source_id"])):
            return False
    return not any(isinstance(marker, dict) and marker.get("target_kind") == "spell_choice"
        and marker.get("target_id") == f"spell_choice:{spell_id}" for marker in markers)


def resolve_native_spell_pool_inception(prior_definition, *, class_row_id, selected_class,
        selected_subclass, target_level, kind, prior_authority=None):
    """Resolve one first pool from rebuilt prior facts and actual future sources.

    A projected ledger is advisory. Strict callers supply actual SourceAuthority;
    publication independently rebuilds these same facts under its reservation.
    """
    from .character_builder_foundation import (_effective_spellcasting_profile_for_row,
        _spellcasting_mode_for_class, _spellcasting_profile_start_level)
    result = {"status": UNKNOWN, "reason": "prior_pool_presence_unresolved"}
    if kind not in {"cantrip", "known", "prepared", "spellbook"} or not class_row_id:
        return result
    if isinstance(prior_authority, SourceAuthority):
        if numeric_value_digest(prior_definition.to_dict()) not in {
                prior_authority.original_definition_digest, prior_authority.definition_digest}:
            return result
        ledger = prior_authority.spell_choice_ledger
    elif prior_authority is None and prior_definition.spellcasting.get("native_grant_projection") is True:
        ledger = prior_definition.spellcasting.get("native_choice_ledger")
    else:
        return result
    if not isinstance(ledger, dict) or ledger.get("inventory_complete") is not True:
        return result
    matches = [row for row in ledger.get("presence", [])
        if row.get("class_row_id") == class_row_id and row.get("kind") == kind]
    if len(matches) > 1:
        return result
    if matches and matches[0]["status"] == "PRESENT":
        return {"status": "PRESENT", "reason": "qualified_prior_pool"}
    if selected_class is None or getattr(selected_class, "entry_type", None) != "class" or type(target_level) is not int:
        return result
    options = dict(selected_class=selected_class, selected_subclass=selected_subclass)
    future = _effective_spellcasting_profile_for_row(selected_class.title, row_level=target_level, **options)
    mode = _spellcasting_mode_for_class(selected_class.title, row_level=target_level, **options)
    future_kinds = ({"known"} if mode == "known" else {"prepared", "spellbook"} if mode == "wizard"
                    else {"prepared"} if mode == "prepared" else set())
    if future.get("cantrip_progression"):
        future_kinds.add("cantrip")
    start = _spellcasting_profile_start_level(future)
    if not future or kind not in future_kinds or start < 1 or target_level < start:
        return result
    owners = ledger.get("owner_ids", [])
    if matches:
        prior = matches[0]
        if (prior["status"] != "ABSENT" or prior.get("class_entry_key") != selected_class.entry_key
                or prior.get("class_source_id") != selected_class.source_id
                or target_level != prior.get("attained_level", -2) + 1):
            return result
    elif (class_row_id in owners or target_level != 1 or any(
            row.get("entry_key") == selected_class.entry_key and row.get("source_id") == selected_class.source_id
            for row in ledger.get("owner_sources", []))):
        return result
    # Scan the full original inventory, including dormant/withdrawn ownership.
    if class_row_id in ledger.get("obligation_owner_ids", []):
        return result
    return {"status": "ABSENT", "reason": "proved_first_supported_pool"}


def _native_spell_choice_ledger(authority, definition, systems_service, *, state=None, campaign_page_records=None, prospective_active=(),
        prospective_retired=(), retained_states=None, validated_inputs=None):
    """One acyclic aggregation of history, current benefits, and complete pools."""
    from .character_spell_grants import has_native_grants, grant_display_id, validate_native_grant_model
    from .character_builder_spells import _spell_mark_tokens
    from .character_builder_foundation import _effective_spellcasting_profile_for_row, _spellcasting_mode_for_class
    from .character_builder_derivation import _spell_progression_value, _spell_slot_progression_for_class_level, _prepared_spell_count_for_level
    import re
    scores = _qualified_spell_capacity_scores(authority, definition, state or {}, validated_inputs=validated_inputs)
    raw_rows = [row for row in definition.spellcasting.get("spells", []) if isinstance(row, dict)]
    profiles = profile_class_rows(definition.profile)
    pages = _eligible_page_records(campaign_page_records)
    choices, pools, presence = [], [], []
    active = set(authority.confirmed_active_spell_choices) | set(prospective_active)
    retired = (set(authority.confirmed_retired_spell_choices) - set(prospective_active)) | set(prospective_retired)
    active -= retired
    reconstruction_roles = {identity: (role, level) for identity, role, level in authority.reconstructed_spell_roles}
    grants = list(authority.native_grant_view.occurrences) if authority.native_grant_view is not None else []
    # Qualification may stop before emitting occurrences. Their retained
    # obligations still exist; no missing source/type fact is a zero cost.
    emitted = {row["id"] for row in grants}
    model = definition.spellcasting.get("native_spell_grants")
    try:
        if has_native_grants(definition):
            validate_native_grant_model(definition)
        model_valid = True
    except (TypeError, ValueError):
        model_valid = False
    if model_valid and isinstance(model, dict):
        grants.extend({**row, "status": "UNPROVED", "contributions": {}}
            for row in model["occurrences"] if isinstance(row, dict) and row.get("id") not in emitted)
    owner_ids = {_text(row.get("row_id")) for row in profiles}
    acquisition_owners = (definition.source["native_acquisitions"]["owners"]
                          if model_valid and has_native_grants(definition) else [])
    unowned_obligations = sorted({_text(row.get("id") or row.get("owner_id")) or "unowned-spell-observation"
        for row in [*raw_rows, *grants, *acquisition_owners]
        if not row.get("spell_source_row_id") and (not _text(row.get("class_row_id"))
            or _text(row.get("class_row_id")) not in owner_ids)})
    for owner in profiles:
        row_id = _text(owner.get("row_id"))
        valid_owner = bool(row_id and sum(_text(row.get("row_id")) == row_id for row in profiles) == 1
            and row_id in authority.verified_class_rows and type(owner.get("level")) is int
            and 1 <= owner["level"] <= 20)
        ref = dict(owner.get("systems_ref") or {})
        cls = _current_systems_entry(definition.campaign_slug, "systems", ref.get("entry_key", ""), systems_service)
        valid_owner = bool(valid_owner and cls is not None and cls.entry_type == "class" and all(
            not ref.get(key) or ref[key] == getattr(cls, key, None)
            for key in ("entry_key", "slug", "source_id", "entry_type", "title", "library_slug")))
        subclass = _current_reconstruction_subclass(definition, owner, cls, systems_service) if valid_owner else None
        valid_owner = valid_owner and (not owner.get("subclass_ref") or subclass is not None)
        options = {"selected_class": cls, "selected_subclass": subclass}
        level = owner.get("level")
        profile = _effective_spellcasting_profile_for_row(cls.title, row_level=level, **options) if valid_owner else {}
        mode = _spellcasting_mode_for_class(cls.title, row_level=level, **options) if profile else ""
        from .character_builder_foundation import _spellcasting_profile_start_level
        full_profile = (_effective_spellcasting_profile_for_row(cls.title, row_level=0, **options)
                        if valid_owner else {})
        start = _spellcasting_profile_start_level(full_profile) if full_profile else 0
        prior_active = bool(profile and start > 0 and level >= start)
        from .character_builder_foundation import (_class_supports_shared_slot_multiclass,
            _subclass_supports_shared_slot_multiclass)
        inactive_supported = bool(valid_owner and (full_profile and start > level or
            not full_profile and _class_supports_shared_slot_multiclass(
                systems_service, definition.campaign_slug, cls, campaign_page_records=campaign_page_records)
            and _subclass_supports_shared_slot_multiclass(systems_service, definition.campaign_slug,
                subclass, selected_class=cls, campaign_page_records=campaign_page_records)))
        active_kinds = ({"known"} if mode == "known" else {"prepared", "spellbook"} if mode == "wizard"
                        else {"prepared"} if mode == "prepared" else set())
        if profile.get("cantrip_progression"):
            active_kinds.add("cantrip")
        for kind in ("cantrip", "known", "prepared", "spellbook"):
            presence.append({"class_row_id": row_id, "kind": kind,
                "status": "PRESENT" if valid_owner and prior_active and kind in active_kinds else
                    "ABSENT" if inactive_supported else UNKNOWN,
                "class_entry_key": cls.entry_key if valid_owner else None,
                "class_source_id": cls.source_id if valid_owner else None,
                "attained_level": level, "source_basis_digest": numeric_value_digest({
                    "class": {"metadata": cls.metadata, "body": cls.body},
                    "subclass": {"metadata": subclass.metadata, "body": subclass.body} if subclass else None,
                    "row": owner}) if valid_owner else None})
        if not profile and valid_owner and not any(raw.get("class_row_id") == row_id
                and not raw.get("spell_source_row_id") for raw in raw_rows) and not any(
                grant.get("class_row_id") == row_id for grant in grants):
            continue
        maximum = None
        if profile and isinstance(profile.get("slot_progression"), list) and len(profile["slot_progression"]) >= level:
            slots = _spell_slot_progression_for_class_level(cls.title, level, **options)
            if all(type(slot.get("level")) is int and type(slot.get("max_slots")) is int for slot in slots):
                maximum = max((slot["level"] for slot in slots if slot["max_slots"] > 0), default=0)
        allowances = {}
        for kind, field in (("cantrip", "cantrip_progression"), ("known", "spells_known_progression")):
            values = profile.get(field)
            allowances[kind] = (_spell_progression_value(cls.title, field, level, **options)
                if isinstance(values, list) and type(level) is int and 1 <= level <= len(values)
                and type(values[level - 1]) is int and values[level - 1] >= 0 else None)
        prepared_values = profile.get("prepared_spells_progression")
        formula = profile.get("prepared_spells")
        prepared_supported = (isinstance(prepared_values, list) and type(level) is int
            and 1 <= level <= len(prepared_values) and type(prepared_values[level - 1]) is int
            and prepared_values[level - 1] >= 0)
        if not prepared_supported and isinstance(formula, str):
            match = re.fullmatch(r"(?:<\$level\$>|level)(?:\s*/\s*([1-9]\d*))?\s*\+\s*(?:<\$([a-z]+)_mod\$>|([a-z]+))", formula.strip(), re.IGNORECASE)
            if match:
                from .character_builder_derivation import _prepared_spell_formula_ability_key
                key = _prepared_spell_formula_ability_key(match.group(2) or match.group(3))
                prepared_supported = key in scores
        allowances["prepared"] = (_prepared_spell_count_for_level(cls.title, scores, level, **options)
            if prepared_supported and valid_owner else None)
        kinds = ["known"] if mode == "known" else ["prepared", "spellbook"] if mode == "wizard" else ["prepared"] if mode == "prepared" else ["known", "prepared"]
        if profile.get("cantrip_progression") or any(raw.get("class_row_id") == row_id
                and authority.status_for("spell", _text(raw.get("id"))) == VERIFIED
                and dict(raw.get("systems_ref") or {}).get("entry_key")
                and (entry := _current_systems_entry(definition.campaign_slug, "systems",
                    raw["systems_ref"]["entry_key"], systems_service)) is not None
                and type(entry.metadata.get("level")) is int and entry.metadata["level"] == 0
                for raw in raw_rows):
            kinds.insert(0, "cantrip")
        row_choices = []
        for raw in raw_rows:
            if _text(raw.get("class_row_id")) != row_id or raw.get("spell_source_row_id"):
                continue
            spell_id = _text(raw.get("id"))
            unique = bool(spell_id and sum(_text(other.get("id")) == spell_id for other in raw_rows) == 1)
            historical = "retired" if spell_id in retired else "active" if spell_id in active else "UNKNOWN"
            if retained_states and spell_id in retained_states:
                historical = retained_states[spell_id]
            exact_ref = dict(raw.get("systems_ref") or {})
            source_kind, source_key = _source_identity(raw)
            metadata, reason = _current_payload(campaign_slug=definition.campaign_slug, kind="spell",
                source_kind=source_kind, source_key=source_key, systems_service=systems_service, pages=pages,
                expected_slug=_text(exact_ref.get("slug")))
            entry = _current_systems_entry(definition.campaign_slug, source_kind, source_key, systems_service) if source_kind.startswith("systems") else None
            spell_level = metadata.get("level") if metadata is not None else None
            exact_current = (source_kind == "page" or entry is not None and all(
                not exact_ref.get(key) or exact_ref[key] == getattr(entry, key, None)
                for key in ("entry_key", "slug", "source_id", "entry_type", "title", "library_slug")))
            current = bool(unique and valid_owner and metadata is not None and not reason and exact_current
                and type(spell_level) is int and 0 <= spell_level <= 9)
            reconstruction_role, retained_level = reconstruction_roles.get(spell_id, (None, None))
            if not current and reconstruction_role in {"available", "prepared", "known", "book", "automatic", "cantrip"}:
                # Retain a proved count category, never current source eligibility.
                spell_level = retained_level
            origin = [grant for grant in grants if grant.get("class_row_id") == row_id
                and grant.get("spell_ref", {}).get("entry_key") == exact_ref.get("entry_key")]
            confirmed_origins = [grant for grant in origin if grant.get("status") == VERIFIED]
            # A positive independent feature origin does not establish that a
            # retained raw observation has no ordinary historical obligation.
            ordinary = historical == "active"
            supported = bool(current and maximum is not None and spell_level <= maximum
                and authority.numeric_basis_digest(f"spell_choice:{spell_id}") is not None)
            pool = "cantrip" if current and spell_level == 0 else "known" if mode == "known" and current else "spellbook" if mode == "wizard" and current else "prepared" if mode == "prepared" and current else None
            facts = {"known": False, "prepared": False}
            for kind in facts:
                contributions = [grant.get("contributions", {}).get(f"counts_against_{kind}") for grant in confirmed_origins]
                if any(value is True for value in contributions):
                    facts[kind] = True
                elif any(value is None for value in contributions):
                    facts[kind] = None
            if ordinary:
                facts["known"] = True if supported else None
                tokens = _spell_mark_tokens(raw.get("mark"))
                preparation_values = [raw[key] for key in ("is_prepared", "prepared") if key in raw]
                preparation_valid = (all(type(value) is bool for value in preparation_values)
                    and len(set(preparation_values)) <= 1
                    and not ("prepared" in tokens and preparation_values and preparation_values[0] is False))
                prepared = preparation_values[0] if preparation_values else "prepared" in tokens
                if mode == "wizard":
                    from .character_spell_reconstruction import _marks as checkpoint_marks
                    try:
                        _, prepared = checkpoint_marks(raw)
                        preparation_valid = True
                    except (TypeError, ValueError):
                        preparation_valid = False
                ordinary_prepared = prepared if supported and preparation_valid else None
                # Independent counted feature origins survive an unprepared
                # ordinary path or its retirement.
                if facts["prepared"] is not True:
                    facts["prepared"] = ordinary_prepared
            elif historical == "UNKNOWN":
                facts = {"known": None, "prepared": None}
            # A prepared class receives leveled list access, not a learned spell
            # repertoire. A current checkpoint can resolve the role of retained
            # observations without assigning historical selection or retirement.
            list_role = bool(mode == "prepared" and type(spell_level) is int and spell_level > 0
                and (reconstruction_role in {"available", "prepared"} or ordinary))
            fixed_role = reconstruction_role == "automatic"
            retained_obligation = True
            ordinary_counted = bool(ordinary and supported)
            prepared_flag = False
            if list_role:
                from .character_spell_reconstruction import _marks as checkpoint_marks
                try:
                    _, prepared_flag = checkpoint_marks(raw)
                    valid_preparation = True
                except (TypeError, ValueError):
                    # Invalid/contradictory observations cannot establish free
                    # capacity or present preparation entitlement.
                    valid_preparation, prepared_flag = False, True
                qualified_preparation = bool(ordinary and supported and valid_preparation)
                historical = "available"
                retained_obligation = bool(prepared_flag)
                ordinary_counted = bool(prepared_flag and qualified_preparation)
                facts["known"] = False
                if facts["prepared"] is not True:
                    facts["prepared"] = (bool(prepared_flag) if valid_preparation and (not prepared_flag or qualified_preparation) else None)
            elif fixed_role:
                historical = "fixed"
                retained_obligation = False
                ordinary_counted = False
                facts = {kind: (True if any(grant.get("contributions", {}).get(f"counts_against_{kind}") is True
                    for grant in confirmed_origins) else None if any(grant.get("contributions", {}).get(f"counts_against_{kind}") is None
                    for grant in confirmed_origins) else False) for kind in ("known", "prepared")}
            qualified_benefit = any(any(grant.get("contributions", {}).get(field) is True
                for field in ("always_prepared", "bonus_known", "ritual")) for grant in confirmed_origins)
            choice = {"spell_id": spell_id, "class_row_id": row_id, "historical_state": historical,
                "retained_obligation": retained_obligation,
                "current_usable": bool(supported and (ordinary and (not list_role or valid_preparation)
                    and (mode != "wizard" or preparation_valid)
                    or list_role and valid_preparation and not prepared_flag) or qualified_benefit),
                "ordinary_eligible": supported,
                "ordinary_counted": ordinary_counted, "replaceable": bool(ordinary and supported and mode == "known"),
                "pool": pool, "counts_against_known": facts["known"], "counts_against_prepared": facts["prepared"],
                "reason": "historical_choice_unresolved" if historical == "UNKNOWN" else
                    "current_choice_source_or_count_unresolved" if ordinary and not supported else
                    "confirmed_retirement" if historical == "retired" else "qualified_active_choice",
                "entry_key": f"{source_kind}:{source_key}", "spell_level": spell_level if current or reconstruction_role is not None else None,
                "class_list_available": bool(list_role and supported),
                "ordinary_prepared": (ordinary_prepared if mode == "wizard" and ordinary
                    else bool(list_role and prepared_flag and ordinary_counted)),
                "current_reconstruction_role": reconstruction_role}
            row_choices.append(choice)
            choices.append(choice)
        for grant in grants:
            display_id = grant_display_id(grant)
            if (grant.get("class_row_id") != row_id or grant.get("status") != VERIFIED
                    or any(raw.get("id") == display_id for raw in raw_rows)
                    or any(choice["spell_id"] == display_id for choice in row_choices)):
                continue
            contributions = grant.get("contributions", {})
            if not any(contributions.get(field) is True for field in ("always_prepared", "bonus_known", "ritual")):
                continue
            spell_level = grant.get("spell_level")
            choice = {"spell_id": display_id, "class_row_id": row_id, "historical_state": "fixed",
                "retained_obligation": False, "current_usable": True, "ordinary_counted": False,
                "replaceable": False, "pool": "cantrip" if spell_level == 0 else "known" if mode == "known" else "spellbook" if mode == "wizard" else "prepared",
                "reason": "independently_qualified_fixed_origin",
                "counts_against_known": contributions.get("counts_against_known"),
                "counts_against_prepared": contributions.get("counts_against_prepared"),
                "entry_key": "systems:" + grant["spell_ref"]["entry_key"], "spell_level": spell_level}
            row_choices.append(choice)
            choices.append(choice)
        for kind in kinds:
            counted, ordinary_ids, unresolved, identities = [], [], (
                list(unowned_obligations) + ([] if model_valid else ["native-grant-model"])), set()
            for choice in row_choices:
                unknown_origin = choice["historical_state"] == "UNKNOWN" or (choice["historical_state"] == "active" and not choice["ordinary_counted"])
                if unknown_origin and (choice["pool"] is None or kind == choice["pool"] or kind == "prepared" and mode == "wizard"):
                    unresolved.append(choice["spell_id"])
                relevant = (kind == "cantrip" and choice["spell_level"] == 0 or
                    kind == "known" and choice["spell_level"] is not None and choice["spell_level"] > 0 or
                    kind in {"prepared", "spellbook"} and choice["spell_level"] is not None and choice["spell_level"] > 0)
                count = choice["counts_against_prepared" if kind == "prepared" else "counts_against_known"]
                if kind == "spellbook":
                    count = choice["ordinary_counted"]
                if relevant and count is None:
                    unresolved.append(choice["spell_id"])
                if relevant and count is True:
                    identity = choice["entry_key"]
                    if identity not in identities:
                        identities.add(identity)
                        counted.append(choice["spell_id"])
                    if choice["ordinary_counted"]:
                        ordinary_ids.append(choice["spell_id"])
            # Authenticated grants can have no retained display row.
            for grant in grants:
                if grant.get("class_row_id") != row_id:
                    continue
                grant_level = grant.get("spell_level")
                contribution = grant.get("contributions", {}).get("counts_against_prepared" if kind == "prepared" else "counts_against_known")
                relevant = grant_level == 0 if kind == "cantrip" else type(grant_level) is int and grant_level > 0
                if kind == "spellbook":
                    continue
                if grant.get("status") != VERIFIED or relevant and contribution is None:
                    unresolved.append(grant["id"])
                elif relevant and contribution is True:
                    identity = "systems:" + grant["spell_ref"]["entry_key"]
                    if identity not in identities:
                        identities.add(identity)
                        counted.append(grant_display_id(grant))
            allowance = None if kind == "spellbook" else allowances.get(kind)
            known = bool(valid_owner and profile and (kind == "spellbook" or allowance is not None) and not unresolved)
            occupancy = len(identities) if known else None
            pools.append({"class_row_id": row_id, "kind": kind, "status": "KNOWN" if known else "UNKNOWN",
                "allowance": allowance, "occupancy": occupancy,
                "remaining": allowance - occupancy if known and allowance is not None else None,
                "counted_spell_ids": counted, "ordinary_spell_ids": ordinary_ids,
                "unresolved_spell_ids": sorted(set(unresolved)),
                "unresolved_reasons": (["current_class_owner_or_casting_profile_unresolved"] if not valid_owner or not profile else [])
                    + (["current_allowance_unresolved"] if kind != "spellbook" and allowance is None else [])
                    + (["historical_class_owner_unresolved"] if unowned_obligations else [])
                    + (["retained_choice_or_grant_count_unresolved"] if unresolved else [])})
    # Missing or ambiguous class ownership must not silently drop observations.
    covered = {row["spell_id"] for row in choices}
    for raw in raw_rows:
        if not raw.get("spell_source_row_id") and _text(raw.get("id")) not in covered:
            choices.append({"spell_id": _text(raw.get("id")), "class_row_id": _text(raw.get("class_row_id")),
                "historical_state": "UNKNOWN", "retained_obligation": True, "current_usable": False,
                "ordinary_counted": False, "replaceable": False, "pool": None,
                "reason": "class_owner_unresolved",
                "counts_against_known": None, "counts_against_prepared": None})
    observation_ids = {_text(raw.get("id")) for raw in raw_rows}
    markers = definition.source.get("source_authorizations", [])
    owners = acquisition_owners
    complete = (isinstance(definition.spellcasting.get("spells", []), list)
        and len(raw_rows) == len(definition.spellcasting.get("spells", []))
        and len(observation_ids) == len(raw_rows) and "" not in observation_ids
        and isinstance(markers, list) and all(isinstance(marker, dict) for marker in markers)
        and len({_text(row.get("row_id")) for row in profiles}) == len(profiles)
        and all(_text(row.get("row_id")) for row in profiles) and model_valid)
    obligation_owners = {_text(row.get("class_row_id")) for row in [*raw_rows, *grants, *owners]
                         if isinstance(row, dict) and not row.get("spell_source_row_id")}
    if any(not owner or owner not in owner_ids for owner in obligation_owners):
        # An unowned historical observation might belong to the proposed
        # first pool. Preserve it; an unmatched ID cannot prove absence.
        complete = False
    if any(marker.get("target_kind") == "spell_choice"
            and (not isinstance(marker.get("target_id"), str)
                or marker["target_id"].removeprefix("spell_choice:") not in observation_ids)
            for marker in markers if isinstance(marker, dict)):
        complete = False
    return {"choices": choices, "pools": pools, "presence": presence,
        "inventory_complete": complete, "owner_ids": [_text(row.get("row_id")) for row in profiles],
        "owner_sources": [dict(row.get("systems_ref") or {}) for row in profiles],
        "obligation_owner_ids": sorted(obligation_owners)}


def _current_reconstruction_subclass(definition, row, class_entry, systems_service):
    """Exact current subclass and its declared native parent, never a title alias."""
    ref = row.get("subclass_ref")
    if not isinstance(ref, dict) or not ref.get("entry_key") or systems_service is None:
        return None
    entry = systems_service.get_entry_for_campaign(definition.campaign_slug, ref["entry_key"])
    if (entry is None or entry.entry_type != "subclass" or class_entry is None
            or any(ref.get(key) and ref[key] != getattr(entry, key, None)
                   for key in ("entry_key", "slug", "source_id", "entry_type", "title", "library_slug"))
            or _text(entry.metadata.get("class_name")).casefold() != _text(class_entry.title).casefold()
            or _text(entry.metadata.get("class_source")).casefold() != _text(class_entry.source_id).casefold()):
        return None
    return entry


def _native_aggregate_feature_rows(authority, retained_definition, effective_features):
    """Keep unproved owners blocking, but omit inert retained descriptions.

    This is only a private arithmetic frame. The original rows and their repair
    statuses remain visible and retain no mechanical authority. A copied name,
    missing/duplicate identity or unresolved linked source cannot acquire effects.
    """
    if not isinstance(retained_definition.source.get("native_reconstruction_choices"), dict):
        return list(effective_features)
    historical = {status.instance_id for status in authority.statuses if status.kind == "feature"
                  and status.status == VERIFIED and status.reason == "authenticated_history_only"}
    originals = {}
    for row in retained_definition.features:
        if isinstance(row, dict):
            originals.setdefault(_text(row.get("id")), []).append(row)
    effective_ids = {}
    for row in effective_features:
        if isinstance(row, dict):
            identity = _text(row.get("id"))
            effective_ids[identity] = effective_ids.get(identity, 0) + 1
    result = []
    for row in effective_features:
        identity = _text(row.get("id")) if isinstance(row, dict) else ""
        retained = originals.get(identity, [])
        if (identity and len(retained) == 1 and effective_ids.get(identity) == 1
                and type(retained[0].get("id")) is str and type(row.get("id")) is str
                and row.get("mechanics_suppressed") is True
                and (authority.status_for("feature", identity) == NEEDS_REPAIR or identity in historical)
                and _source_identity(retained[0]) == ("", "")
                and _source_identity(row) == ("", "")):
            continue
        result.append(row)
    return result


def _qualified_native_aggregate_values(authority, definition, *, item_catalog, systems_service,
                                       campaign_page_records, numeric_context=None):
    """Recompute only closed native recipes; saved aggregate totals are removed."""
    from .character_builder_derivation import (
        _derive_definition_stats, _derive_definition_skills, _extract_speed_label,
        _extract_size_label, _normalize_size_label, SIZE_CARRYING_CAPACITY_MULTIPLIERS,
        _effect_speed_bonus,
        _armor_class_ability_dependencies,
        SKILL_LABELS,
    )
    from .character_builder_equipment import _extract_character_effect_keys, _split_effect_key
    from .character_read_foundation import read_item_catalog_for_definition
    from .repository import normalize_lookup
    import math

    # Owner identity does not authorize stale copied mechanics. Use the same
    # current approved payload frame and exact catalogue as ordinary derivation.
    retained_definition = definition
    definition = authority.effective_definition(definition)
    definition.features = _native_aggregate_feature_rows(
        authority, retained_definition, definition.features)

    fields = {row.path: row for row in authority.field_statuses}
    scores = {}
    for key in ("str", "dex", "con", "int", "wis", "cha"):
        status = fields.get(f"stats.ability_scores.{key}.score")
        if status is not None and status.is_effective and type(status.effective) is int:
            scores[key] = status.effective
    pb_status = fields.get("stats.proficiency_bonus")
    pb_ok = pb_status is not None and pb_status.is_effective and type(pb_status.effective) is int
    closed_ids = numeric_context["closed_feature_ids"] if numeric_context is not None else frozenset()
    blocked = numeric_context["blocked"] if numeric_context is not None else NATIVE_BASELINE_FIELDS
    features_ok = all(authority.status_for("feature", _text(row.get("id"))) == VERIFIED
                      or _text(row.get("id")) in closed_ids
                      for row in definition.features if isinstance(row, dict))
    rows = profile_class_rows(definition.profile)
    classes_ok = bool(rows) and {row.get("row_id") for row in rows} == set(authority.verified_class_rows)

    def exact_entry(ref, types):
        if systems_service is None or not isinstance(ref, dict) or not ref:
            return None
        kind, key = _source_identity({"systems_ref": ref})
        entry = _current_systems_entry(definition.campaign_slug, kind, key, systems_service)
        if entry is None or getattr(entry, "entry_type", "") not in types:
            return None
        if any(_text(ref.get(field)) and _text(ref[field]) != _text(getattr(entry, field, ""))
               for field in ("entry_key", "slug", "source_id", "entry_type", "title", "library_slug")):
            return None
        return entry

    classes_ok = classes_ok and all(exact_entry(row.get("systems_ref"), {"class"}) is not None for row in rows)
    if isinstance(definition.source.get("native_reconstruction_choices"), dict):
        def closed_feature(row):
            if _text(row.get("id")) in closed_ids:
                return True
            if authority.status_for("feature", _text(row.get("id"))) == VERIFIED:
                return True
            entry = exact_entry(row.get("systems_ref"), {"classfeature", "subclassfeature"})
            if entry is None:
                return False
            metadata = dict(entry.metadata or {})
            owner = next((owner for owner in rows if owner.get("row_id") == row.get("class_row_id")), None)
            if owner is None and len(rows) == 1:
                owner = rows[0]
            # A current exact feature explicitly belonging to a later level
            # contributes no current mechanics. Its retained description does
            # not block independent aggregates at the actual level.
            return bool(owner and type(metadata.get("level")) is int
                        and type(owner.get("level")) is int and metadata["level"] > owner["level"]
                        and _text(metadata.get("class_name")).casefold() == _text(owner.get("class_name")).casefold()
                        and row.get("mechanics_suppressed"))
        features_ok = all(closed_feature(row) for row in definition.features if isinstance(row, dict))
    # Legacy formulas inspect names as selectors. In this private arithmetic
    # frame those selectors come only from exact current source identities.
    def source_selectors(row, entry):
        row["name"] = _text(getattr(entry, "title", "")) if entry is not None else ""
        ref = dict(row.get("systems_ref") or {})
        for field in ("title", "slug"):
            ref[field] = _text(getattr(entry, field, "")) if entry is not None else ""
        row["systems_ref"] = ref
    for row in rows:
        entry = exact_entry(row.get("systems_ref"), {"class"})
        row["class_name"] = _text(getattr(entry, "title", "")) if entry is not None else ""
        subclass = exact_entry(row.get("subclass_ref"), {"subclass"})
        row["subclass_name"] = _text(getattr(subclass, "title", "")) if subclass is not None else ""
        row["subclass_ref"] = ({**dict(row.get("subclass_ref") or {}), "title": subclass.title,
                                "slug": subclass.slug} if subclass is not None else {})
    definition.profile["classes"] = rows
    definition.profile["class_name"] = rows[0]["class_name"] if rows else ""
    definition.profile["subclass_name"] = rows[0]["subclass_name"] if rows else ""
    definition.profile["subclass_ref"] = deepcopy(rows[0]["subclass_ref"]) if rows else {}
    page_lookup = _eligible_page_records(campaign_page_records)
    for row in definition.features:
        kind, key = _source_identity(row)
        if kind.startswith("systems"):
            ref = dict(row.get("systems_ref") or {})
            ref.pop("title", None)  # Display text is not a feature source selector.
            if ref.get("entry_type") == "subclass":
                from .character_subclass_companion import selected_subclass_companion_matches
                entry = exact_entry(ref, {"subclass"})
                originals = [original for original in retained_definition.features
                             if isinstance(original, dict) and original.get("id") == row.get("id")]
                if (entry is not None and len(originals) == 1
                        and authority.status_for("feature", _text(row.get("id"))) == VERIFIED
                        and selected_subclass_companion_matches(originals[0], retained_definition.profile,
                            entry, systems_service, definition.campaign_slug)):
                    # Context has no arithmetic selectors or effects. Only this
                    # private frame is reduced; retained content stays intact.
                    identity = row["id"]
                    row.clear()
                    row["id"] = identity
                    continue
            entry = exact_entry(ref, {
                "feature", "feat", "optionalfeature", "classfeature", "subclassfeature", "background"})
            features_ok = features_ok and entry is not None
            source_selectors(row, entry)
        elif kind == "page":
            records = page_lookup.get(key, [])
            row["name"] = _text(_field(_field(records[0], "page"), "title")) if len(records) == 1 else ""
    for row in definition.equipment_catalog:
        source_selectors(row, exact_entry(row.get("systems_ref"), {"item"}))
    item_catalog = read_item_catalog_for_definition(
        definition, item_catalog=item_catalog, systems_service=systems_service,
        campaign_page_records=campaign_page_records,
    )
    species = (exact_entry(definition.profile.get("species_ref"), {"race", "subrace"})
               if not definition.profile.get("species_page_ref") else None)
    features = list(definition.features or [])
    effects = _extract_character_effect_keys(features)
    invalid = set(authority.unqualified_native_aggregate_adjustments)
    initiative_abilities = {"dex"}
    initiative_pb = False
    passive_paths = {name: f"stats.passive_{name}" for name in ("perception", "insight", "investigation")}
    for effect in effects:
        parts = _split_effect_key(effect)
        kind = normalize_lookup(parts[0]) if parts else ""
        try:
            if kind == "initiativebonus":
                if len(parts) != 2: raise ValueError()
                int(parts[1])
            elif kind == "initiativebonusability":
                if len(parts) != 2 or normalize_lookup(parts[1]) not in {"str", "dex", "con", "int", "wis", "cha"}: raise ValueError()
                initiative_abilities.add(normalize_lookup(parts[1]))
            elif kind == "halfproficiency":
                if len(parts) < 2: raise ValueError()
                target = normalize_lookup(parts[1])
                if target == "all":
                    if len(parts) != 2: raise ValueError()
                    initiative_pb = True
                elif target in {"abilities", "skills"}:
                    if len(parts) != 3: raise ValueError()
                    selectors = [normalize_lookup(value) for value in parts[2].split(",")]
                    allowed = {"str", "dex", "con", "int", "wis", "cha"} if target == "abilities" else set(SKILL_LABELS)
                    if not selectors or any(not value or value not in allowed for value in selectors): raise ValueError()
                    initiative_pb = initiative_pb or target == "abilities" and "dex" in selectors
                else: raise ValueError()
            elif kind == "speedbonus":
                if len(parts) != 2: raise ValueError()
                int(parts[1])
            elif kind == "carryingcapacitymultiplier":
                if len(parts) != 2 or not math.isfinite(float(parts[1])) or float(parts[1]) <= 0: raise ValueError()
            elif kind in {"passivebonus", "skillbonus"}:
                if len(parts) != 3: raise ValueError()
                allowed = set(passive_paths) if kind == "passivebonus" else set(SKILL_LABELS)
                selectors = [normalize_lookup(value) for value in parts[1].split(",")]
                if len(selectors) != 1 or any(not value or value not in allowed for value in selectors): raise ValueError()
                int(parts[2])
        except (ValueError, TypeError, OverflowError):
            if kind.startswith("initiative"): invalid.add("stats.initiative_bonus")
            elif kind == "halfproficiency":
                invalid.update(passive_paths.values())
                if len(parts) < 2 or normalize_lookup(parts[1]) != "skills":
                    invalid.add("stats.initiative_bonus")
            elif kind.startswith("speed"): invalid.add("stats.speed")
            elif kind.startswith("carrying"): invalid.update({"stats.carrying_capacity", "stats.push_drag_lift"})
            elif kind.startswith(("passive", "skill")): invalid.update(passive_paths.values())

    invalid.update(_unqualified_native_aggregate_adjustments(dict(definition.stats or {})))

    # Unknown arithmetic inputs have placeholders only inside unrelated formulas;
    # each output below must prove every input it actually reads.
    arithmetic_scores = {key: scores.get(key, 0) for key in ("str", "dex", "con", "int", "wis", "cha")}
    payload = deepcopy(definition.to_dict())
    for path in NATIVE_BASELINE_FIELDS: payload["stats"].pop(path.removeprefix("stats."), None)
    payload["stats"].pop("manual_adjustments", None)
    scratch = CharacterDefinition.from_dict(payload)
    skills = _derive_definition_skills(scratch, ability_scores=arithmetic_scores,
        proficiency_bonus=pb_status.effective if pb_ok else 0, source_authority=authority)
    qualified = set()
    def qualify(path, inputs_ready):
        if inputs_ready and path not in invalid and path not in blocked:
            qualified.add(path)
    gear_ok = all(authority.status_for("item", item_id) == VERIFIED for item_id in authority.requested_active_item_ids)
    ac_dependencies = _armor_class_ability_dependencies(
        equipment_catalog=list(definition.equipment_catalog or []), features=features,
        class_names=[row.get("class_name", "") for row in rows],
        subclass_names=[row.get("subclass_name", "") for row in rows], item_catalog=item_catalog,
        allow_plain_unarmored_base=definition.source.get("source_type") == "native_character_builder",
    )
    qualify("stats.armor_class", classes_ok and features_ok and gear_ok and ac_dependencies <= scores.keys())
    recipe = dict(definition.source.get("native_progression") or {}).get("hp_recipe")
    if isinstance(recipe, dict):
        hp_owners = [row.get("owner_id") for row in recipe.get("continuing_effects", []) if isinstance(row, dict)]
        qualify("stats.max_hp", classes_ok and "con" in scores and all(
            authority.status_for("feature", identity) == VERIFIED for identity in hp_owners))
    qualify("stats.initiative_bonus", features_ok and initiative_abilities <= scores.keys() and (not initiative_pb or pb_ok))
    speed = _extract_speed_label(species) if species is not None else ""
    import re
    raw_speed = dict(species.metadata or {}).get("speed") if species is not None else None
    movement_ok = ((type(raw_speed) in {int, float} and math.isfinite(raw_speed) and raw_speed >= 0)
                   or isinstance(raw_speed, str) and bool(raw_speed.strip()))
    if _effect_speed_bonus(effects) and not re.search(r"\d+", speed):
        movement_ok = False  # Existing speed arithmetic cannot apply this modifier.
    qualify("stats.speed", features_ok and species is not None and movement_ok)
    size = _normalize_size_label(_extract_size_label(species)) if species is not None else ""
    size_ok = normalize_lookup(size) in SIZE_CARRYING_CAPACITY_MULTIPLIERS
    for path in ("stats.carrying_capacity", "stats.push_drag_lift"):
        qualify(path, features_ok and "str" in scores and size_ok)
    for name, path in passive_paths.items():
        matching = [row for row in definition.skills if normalize_lookup(row.get("name")) == name]
        skill_status = fields.get(f"skills.{name}")
        explicit = len(matching) == 1 and matching[0].get("proficiency_level") in {"none", "half_proficient", "proficient", "expertise"}
        qualify(path, features_ok and pb_ok and ("int" if name == "investigation" else "wis") in scores
               and explicit and skill_status is not None and skill_status.is_effective)
    calculated = _derive_definition_stats(scratch, ability_scores=arithmetic_scores,
        proficiency_bonus=pb_status.effective if pb_ok else 0, skills=skills, features=features,
        item_catalog=item_catalog or {}, selected_species=species, source_authority=authority,
        historical_option_payloads=[],
        qualified_aggregate_paths=frozenset(qualified))
    if numeric_context is not None and "stats.armor_class" in qualified and calculated.get("armor_class") is not None:
        from .character_builder_derivation import _transient_numeric_adjustment
        calculated["armor_class"] += _transient_numeric_adjustment(
            numeric_context["effects"].get("stat_adjustments"), "armor_class")
    return {path: calculated[path.removeprefix("stats.")] for path in qualified
            if calculated.get(path.removeprefix("stats.")) is not None}


def _passive_member_frames(definition, attained_owners, statuses, verified_classes):
    """Bind passive matching to proved sources without saving class ownership."""
    from .managed_resource_registry import (
        managed_resource_feature_identity, resolve_managed_resource_family_and_member,
    )
    from .repository import normalize_lookup
    classes = profile_class_rows(definition.profile)
    class_ids = [_text(row.get("row_id")) for row in classes]
    if not all(class_ids) or len(set(class_ids)) != len(class_ids):
        return ()
    verified = {row.instance_id for row in statuses if row.kind == "feature" and row.status == VERIFIED}
    features = [row for row in definition.features if isinstance(row, dict)]
    ids = [_text(row.get("id")) for row in features]
    frames = []
    for feature in features:
        identity = _text(feature.get("id"))
        ref = dict(feature.get("systems_ref") or {})
        owners = attained_owners.get(ref.get("entry_key"), frozenset())
        if (identity not in verified or ids.count(identity) != 1 or len(owners) != 1
                or feature.get("page_ref") or feature.get("tracker_ref")
                or ref.get("entry_type") not in {"classfeature", "subclassfeature"}):
            continue
        owner = next(iter(owners))
        if owner not in verified_classes or _text(feature.get("class_row_id")) not in {"", owner}:
            continue
        canonical = deepcopy(feature)
        canonical.update(source=ref.get("source_id"), class_row_id=owner)
        family, member = resolve_managed_resource_family_and_member(canonical)
        if (managed_resource_feature_identity(canonical) is None or not family or not member
                or member.get("tracker")
                or dict(family.get("match_slug_members") or {}).get(normalize_lookup(ref.get("slug", "")))
                   != member.get("key")):
            continue
        frames.append(_canonical({"feature": feature, "canonical": canonical,
            "class": classes[class_ids.index(owner)]}))
    return tuple(frames)


def _current_managed_pool_owners(
    definition: CharacterDefinition, *, systems_service: Any,
    pages: dict[str, list[Any]], verified_class_rows: frozenset[str] | None = None,
    feature_statuses: tuple[AuthorityStatus, ...] | None = None,
    infer_missing: bool = False, feature_composition=None, armor_selectors=None, tracker_bindings=(),
) -> dict[str, dict[str, Any]]:
    """Prove pool membership from current typed sources, never display citations.

    This structural proof supplies neither a capacity nor numeric authority.
    Every retained alias must qualify; selecting one good row cannot hide an
    ambiguous or unproved second owner. Inference is limited to missing class
    ownership during reconstruction and is independently repeated at issuance.
    """
    from .managed_resource_registry import (
        managed_resource_feature_identity, resolve_managed_resource_family_and_member,
    )
    from .repository import normalize_lookup

    if systems_service is None:
        return {}
    if armor_selectors is None:
        armor_selectors = _armor_structure(definition, systems_service)
    classes = profile_class_rows(definition.profile)
    class_ids = [_text(row.get("row_id")) for row in classes]
    if not classes or any(not value for value in class_ids) or len(set(class_ids)) != len(class_ids):
        return {}
    features = [row for row in definition.features if isinstance(row, dict)]
    ids = [_text(row.get("id")) for row in features]
    statuses = {(row.kind, row.instance_id): row.status for row in feature_statuses or ()}
    from .character_feature_composition import resolve_feature_composition, registered_owner_payload
    composition = feature_composition if feature_composition is not None else resolve_feature_composition(
        definition, systems_service, feature_statuses=feature_statuses, verified_class_rows=verified_class_rows)

    def entry_for(row, kinds):
        kind, key = _source_identity(row)
        if not kind.startswith("systems") or row.get("page_ref"):
            return None
        entry = _current_systems_entry(definition.campaign_slug, kind, key, systems_service)
        ref = row.get("systems_ref")
        if (entry is None or not isinstance(ref, dict) or entry.entry_type not in kinds
                or any(_text(ref.get(field)) != _text(getattr(entry, field, ""))
                       for field in ("entry_key", "entry_type", "source_id", "slug"))
                or any(_text(ref.get(field)) and _text(ref[field]) != _text(getattr(entry, field, ""))
                       for field in ("title", "library_slug"))):
            return None
        return entry

    from .character_tracker_associations import physical_id

    result = {}
    for template in definition.resource_templates:
        if not isinstance(template, dict):
            continue
        tracker_id = _text(template.get("id"))
        owners = [row for row in features if _text(row.get("tracker_ref")) == tracker_id]
        if (not tracker_id or not owners
                or sum(isinstance(row, dict) and _text(row.get("id")) == tracker_id
                       for row in definition.resource_templates) != 1):
            continue
        members, pool_identity, pool_shape = [], None, None
        for feature in owners:
            feature_id = _text(feature.get("id"))
            entry = entry_for(feature, {"classfeature", "subclassfeature", "optionalfeature", "feature"})
            kind, key = _source_identity(feature)
            current, reason = _current_payload(
                campaign_slug=definition.campaign_slug, kind="feature", source_kind=kind,
                source_key=key, systems_service=systems_service, pages=pages,
                expected_slug=_text(dict(feature.get("systems_ref") or {}).get("slug")),
                expected_feature=feature, expected_profile=definition.profile,
            )
            if (not feature_id or ids.count(feature_id) != 1 or entry is None or current is None or reason
                    or feature_statuses is not None and statuses.get(("feature", feature_id)) != VERIFIED):
                break
            if entry.entry_type == "feature":
                current = registered_owner_payload(composition, feature_id, current, definition=definition)
                if current is None:
                    break
            matching_classes = []
            for class_row in classes:
                row_id = _text(class_row.get("row_id"))
                class_entry = entry_for(class_row, {"class"})
                level = class_row.get("level")
                if (class_entry is None or type(level) is not int or not 1 <= level <= 20
                        or verified_class_rows is not None and row_id not in verified_class_rows
                        or _text(feature.get("class_row_id")) not in {"", row_id}
                        or _text(template.get("class_row_id")) not in {"", row_id}
                        or not infer_missing and (_text(feature.get("class_row_id")) != row_id
                                                  or _text(template.get("class_row_id")) != row_id)):
                    continue
                # A missing owner needs a positive source relationship, not
                # merely the presence of a single class on the character.
                if (not _text(current.get("class_name"))
                        or _text(current["class_name"]).casefold() != _text(class_entry.title).casefold()
                        or _text(current.get("class_source") or "PHB").casefold() != _text(class_entry.source_id).casefold()):
                    continue
                attained = current.get("level")
                if entry.entry_type in {"classfeature", "subclassfeature"} and (
                        type(attained) is not int or not 1 <= attained <= level):
                    continue
                if entry.entry_type in {"classfeature", "subclassfeature"}:
                    parent = class_entry
                    if entry.entry_type == "subclassfeature":
                        parent = _current_reconstruction_subclass(definition, class_row, class_entry, systems_service)
                    loader = getattr(systems_service, "collect_attained_deterministic_feature_entries", None)
                    if (parent is None or not callable(loader)
                            or entry.entry_key not in {child.entry_key for child in loader(
                                definition.campaign_slug, parent, attained_level=level,
                                selected_feature_branches=armor_selectors)}):
                        continue
                matching_classes.append(row_id)
            if len(matching_classes) != 1:
                break
            canonical = deepcopy(feature)
            canonical["class_row_id"] = matching_classes[0]
            canonical["source"] = entry.source_id
            if entry.entry_type == "feature":
                canonical["mechanic_effects"] = deepcopy(current["mechanic_effects"])
            identity = managed_resource_feature_identity(canonical)
            family, member = resolve_managed_resource_family_and_member(canonical)
            source_member = dict((family or {}).get("match_slug_members") or {}).get(normalize_lookup(entry.slug))
            tracker = dict((member or {}).get("tracker") or {})
            shape = (_text(canonical.get("category") or "class_feature"),
                     _text(tracker.get("label") or canonical.get("name")),
                     _text(tracker.get("notes") or canonical.get("name")))
            if (identity is None or not family or not member
                    or physical_id(member, canonical, tracker_bindings) != tracker_id
                    or source_member != member.get("key") and not (
                        member.get("generate_from_primary") is True
                        and source_member == dict(family.get("primary") or {}).get("key"))
                    or pool_identity is not None and identity != pool_identity
                    or pool_shape is not None and shape != pool_shape):
                break
            pool_identity = identity
            pool_shape = shape
            members.append({"feature": deepcopy(feature), "canonical": canonical,
                            "owner": [kind, key], "source": current})
        else:
            if members:
                members.sort(key=lambda row: (row["owner"], row["feature"]["id"]))
                result[tracker_id] = {"class_row_id": pool_identity[1], "members": members,
                    "class": deepcopy(next(row for row in classes if _text(row.get("row_id")) == pool_identity[1])),
                    "template": deepcopy(template)}
    return result


def _managed_resource_tracker_ids(feature_composition) -> set[str]:
    from .managed_resource_registry import MANAGED_RESOURCE_FAMILIES

    managed_ids = {
        _text(dict(member.get("tracker") or {}).get("id"))
        for family in MANAGED_RESOURCE_FAMILIES
        for member in [family["primary"], *family.get("members", ())]
        if member.get("tracker")
    }
    if feature_composition is not None:
        managed_ids.update(json.loads(value)["resource_id"]
            for value in feature_composition.resource_owners)
    return managed_ids


def _recognized_managed_resource_targets(definition: CharacterDefinition, feature_composition, tracker_bindings=()) -> frozenset[str]:
    """Classify the authenticated structural frame, not a caller's projection."""
    from .managed_resource_registry import resolve_managed_resource_family_and_member

    managed_ids = _managed_resource_tracker_ids(feature_composition)
    managed_ids.update(row["tracker_id"] for row in tracker_bindings)
    features = [row for row in definition.features if isinstance(row, dict)]
    targets = set()
    for raw in definition.resource_templates:
        if not isinstance(raw, dict):
            continue
        tracker_id = _text(raw.get("id"))
        if tracker_id not in managed_ids:
            continue
        owners = [row for row in features if _text(row.get("tracker_ref")) == tracker_id]
        # Opaque manual ownership does not become managed by reusing an ID.
        if owners and all(
                not row.get("systems_ref") and not _page_ref(row.get("page_ref"))
                or resolve_managed_resource_family_and_member(row)[0] is None
                for row in owners):
            continue
        targets.add(tracker_id)
    return frozenset(targets)


def _qualified_current_managed_templates(
    authority: SourceAuthority, definition: CharacterDefinition, *,
    systems_service: Any, campaign_page_records: list[Any] | None,
) -> dict[str, dict[str, Any] | None]:
    """Separate an audited historical owner from its qualified current capacity.

    Definition is the activation-reconciled structural input, before source
    suppression; qualified numeric inputs come from authority. This calculation
    grants no owner/reset authority.
    The projected template's maximum is never an input to this calculation.
    """
    from .character_feature_trackers import build_managed_resource_tracker_template
    from .managed_resource_registry import (
        managed_resource_feature_identity,
        resolve_managed_resource_family_and_member,
    )
    from .character_builder_equipment import _item_effect_metadata, _metadata_requires_attunement
    from .repository import normalize_lookup

    managed_ids = _recognized_managed_resource_targets(definition, authority.feature_composition, authority.tracker_associations)
    class_rows = profile_class_rows(definition.profile)
    class_ids = [_text(row.get("row_id")) for row in class_rows]
    features = [row for row in definition.features if isinstance(row, dict)]
    templates = [row for row in definition.resource_templates if isinstance(row, dict)]
    pages = _eligible_page_records(campaign_page_records)
    pools = _current_managed_pool_owners(
        definition, systems_service=systems_service, pages=pages,
        verified_class_rows=authority.verified_class_rows, feature_statuses=authority.statuses,
        feature_composition=authority.feature_composition, tracker_bindings=authority.tracker_associations,
    )

    def exact_entry(row: dict[str, Any], entry_types: set[str]) -> Any | None:
        source_kind, source_key = _source_identity(row)
        if not source_kind.startswith("systems"):
            return None
        entry = _current_systems_entry(definition.campaign_slug, source_kind, source_key, systems_service)
        ref = dict(row.get("systems_ref") or {})
        if entry is None or _text(getattr(entry, "entry_type", "")) not in entry_types:
            return None
        if any(_text(ref.get(key)) and _text(ref[key]) != _text(getattr(entry, key, ""))
               for key in ("entry_key", "slug", "source_id", "entry_type", "title", "library_slug")):
            return None
        return entry

    def formula_inputs(formula: dict[str, Any]) -> tuple[set[str], bool] | None:
        kind = _text(formula.get("kind")).lower()
        if kind == "ability_modifier":
            key = _text(formula.get("ability")).lower()
            return ({key}, False) if key in {"str", "dex", "con", "int", "wis", "cha"} else None
        if kind in {"proficiency_bonus", "total_half_level"}:
            return set(), True
        if kind in {"fixed", "level", "threshold"}:
            return set(), False
        parts = formula.get("parts")
        if kind != "sum" or not isinstance(parts, list) or not parts:
            return None
        required: set[str] = set()
        uses_pb = False
        for part in parts:
            child = formula_inputs(part) if isinstance(part, dict) else None
            if child is None:
                return None
            required.update(child[0])
            uses_pb = uses_pb or child[1]
        return required, uses_pb

    def current_template(raw: dict[str, Any], tracker_id: str) -> dict[str, Any] | None:
        matching = [row for row in templates if _text(row.get("id")) == tracker_id]
        owners = [row for row in features if _text(row.get("tracker_ref")) == tracker_id]
        existing_singleton = len(owners) == 1 and managed_resource_feature_identity(owners[0]) is not None
        if (systems_service is None or not isinstance(raw, dict) or _text(raw.get("id")) != tracker_id
                or len(matching) != 1 or not existing_singleton and tracker_id not in pools
                or not class_ids or any(not value for value in class_ids)
                or len(class_ids) != len(set(class_ids))):
            return None
        # Existing singletons continue through every original validation below.
        # New citation/alias frames additionally require the strict pool proof.
        feature = owners[0] if existing_singleton else pools[tracker_id]["members"][0]["canonical"]
        feature_id = _text(feature.get("id"))
        identity = managed_resource_feature_identity(feature)
        if (identity is None or not feature_id
                or sum(_text(row.get("id")) == feature_id for row in features) != 1
                or authority.status_for("feature", feature_id) != VERIFIED):
            return None
        family, member = resolve_managed_resource_family_and_member(feature)
        from .character_tracker_associations import physical_id
        if not family or not member or physical_id(member, feature, authority.tracker_associations) != tracker_id:
            return None
        entry = exact_entry(feature, {"classfeature", "subclassfeature", "optionalfeature", "feature"})
        source_kind, source_key = _source_identity(feature)
        current, reason = _current_payload(
            campaign_slug=definition.campaign_slug, kind="feature", source_kind=source_kind,
            source_key=source_key, systems_service=systems_service, pages=pages,
            expected_slug=_text(dict(feature.get("systems_ref") or {}).get("slug")),
            expected_feature=feature, expected_profile=definition.profile,
        )
        if entry is None or current is None or reason:
            return None
        if entry.entry_type == "feature":
            from .character_feature_composition import registered_owner_payload
            current = registered_owner_payload(authority.feature_composition, feature_id, current, definition=definition)
            if current is None:
                return None
        source_member = dict(family.get("match_slug_members") or {}).get(normalize_lookup(entry.slug))
        if (source_member != member.get("key") and not (
                member.get("generate_from_primary") is True
                and source_member == dict(family.get("primary") or {}).get("key"))):
            return None
        row_id = _text(feature.get("class_row_id"))
        owner = next((row for row in class_rows if _text(row.get("row_id")) == row_id), None)
        if (owner is None or row_id not in authority.verified_class_rows
                or _text(raw.get("class_row_id")) != row_id
                or _text(matching[0].get("class_row_id")) != row_id):
            return None
        class_entry = exact_entry(owner, {"class"})
        level = owner.get("level")
        if class_entry is None or type(level) is not int or not 1 <= level <= 20:
            return None
        if entry.entry_type in {"classfeature", "subclassfeature"}:
            attained = current.get("level")
            if type(attained) is not int or not 1 <= attained <= level:
                return None
        if current.get("class_name") and (
                _text(current["class_name"]).casefold() != _text(class_entry.title).casefold()
                or _text(current.get("class_source") or "PHB").casefold() != _text(class_entry.source_id).casefold()):
            return None
        if current.get("subclass_name") and entry.entry_type == "subclassfeature":
            parent = _current_reconstruction_subclass(definition, owner, class_entry, systems_service)
            collector = getattr(systems_service, "collect_attained_deterministic_feature_entries", None)
            if (parent is None or not callable(collector)
                    or entry.entry_key not in {child.entry_key for child in collector(
                        definition.campaign_slug, parent, attained_level=level,
                        selected_feature_branches=_armor_structure(definition, systems_service))}):
                return None
        elif existing_singleton and tracker_id not in pools and current.get("subclass_name") and entry.entry_type != "feature":
            subclass_ref = dict(owner.get("subclass_ref") or {})
            if (_text(current["subclass_name"]).casefold() != _text(subclass_ref.get("title")).casefold()
                    or _text(current.get("subclass_source") or "PHB").casefold() != _text(subclass_ref.get("source_id")).casefold()):
                return None
        inputs = formula_inputs(dict(dict(member.get("tracker") or {}).get("max_formula") or {}))
        if inputs is None:
            return None
        required, uses_pb = inputs
        scores: dict[str, int] = {}
        for key in required:
            value = authority.field_status(f"stats.ability_scores.{key}.score")
            if not value.is_effective or type(value.effective) is not int:
                return None
            scores[key] = value.effective
        if uses_pb and (set(class_ids) != set(authority.verified_class_rows)
                       or any(type(row.get("level")) is not int or not 1 <= row["level"] <= 20
                              or exact_entry(row, {"class"}) is None for row in class_rows)
                       or sum(row["level"] for row in class_rows) > 20):
            return None
        order = raw.get("display_order")
        if type(order) is not int:
            return None
        expected = build_managed_resource_tracker_template(
            member, feature, ability_scores=scores, current_level=level, display_order=order,
            total_character_level=sum(row["level"] for row in class_rows) if uses_pb else level,
        )
        if expected is not None:
            expected["id"] = physical_id(member, feature, authority.tracker_associations)
        if expected is None or _text(expected.get("id")) != tracker_id:
            return None
        expected.pop("activation_type", None)
        expected["class_row_id"] = row_id
        if any(raw.get(key) != expected.get(key) for key in
               ("id", "label", "category", "reset_on", "reset_to", "rest_behavior", "class_row_id")):
            return None
        seed = raw.get("initial_current")
        uninitialized = seed is None and isinstance(definition.source.get("native_reconstruction_choices"), dict)
        if (not uninitialized and (type(seed) is not int or seed < 0)
                or type(raw.get("max")) is not int or raw["max"] < 0):
            return None
        # Bootstrap spending is historical; no read or activation refills it.
        expected["initial_current"] = seed
        canonical_id = _text(dict(member.get("tracker") or {}).get("id"))
        bonus_targets = {tracker_id, canonical_id}
        items = [row for row in definition.equipment_catalog if isinstance(row, dict)]
        for item in items:
            item_id = _text(item.get("id"))
            admitted = authority.approved_payload("item", item_id).get("resource_template_bonuses", [])
            known_bonus = any(_text(row.get("id") or row.get("tracker_id")) in bonus_targets
                              for row in admitted if isinstance(row, dict))
            kind, key = _source_identity(item)
            metadata, error = _current_payload(
                campaign_slug=definition.campaign_slug, kind="item", source_kind=kind, source_key=key,
                systems_service=systems_service, pages=pages,
                expected_slug=_text(dict(item.get("systems_ref") or {}).get("slug")),
                expected_ref=dict(item.get("systems_ref") or {}),
            )
            if metadata is None or error:
                if known_bonus:
                    return None
                continue
            bonuses = _item_effect_metadata({
                "resource_template_bonuses": metadata.get("resource_template_bonuses", []),
            }).get("resource_template_bonuses", [])
            relevant = [row for row in bonuses if _text(row.get("id")) == tracker_id]
            canonical_bonuses = [row for row in bonuses if canonical_id != tracker_id and _text(row.get("id")) == canonical_id]
            if not relevant and not canonical_bonuses and not known_bonus:
                continue
            if (not item_id or sum(_text(row.get("id")) == item_id for row in items) != 1
                    or authority.status_for("item", item_id) != VERIFIED):
                return None
            active = bool(item.get("is_equipped")) and not item.get("mechanics_suppressed")
            if (_metadata_requires_attunement(metadata.get("attunement"))
                    or metadata.get("requires_attunement") is True) and not item.get("is_attuned"):
                active = False
            if active != (item_id in authority.active_item_ids):
                return None
            if active:
                if canonical_bonuses:
                    # A physical association does not retarget an item capacity grant.
                    return None
                admitted_bonuses = _item_effect_metadata({"resource_template_bonuses": admitted}).get("resource_template_bonuses", [])
                if relevant != [row for row in admitted_bonuses if _text(row.get("id")) == tracker_id]:
                    return None
                expected["max"] += sum(row["bonus"] for row in relevant)
        return expected if type(expected.get("max")) is int and expected["max"] >= 0 else None

    result: dict[str, dict[str, Any] | None] = {}
    for raw in templates:
        tracker_id = _text(raw.get("id"))
        if tracker_id not in managed_ids:
            continue
        try:
            result[tracker_id] = current_template(raw, tracker_id)
        except (TypeError, ValueError, KeyError):
            # Malformed current metadata is not an old maximum fallback.
            result[tracker_id] = None
    return result


def _current_managed_resource_statuses(
    authority: SourceAuthority, definition: CharacterDefinition | None, *,
    systems_service: Any, campaign_page_records: list[Any] | None,
) -> tuple[EffectiveStatus, ...]:
    if definition is None:
        # No authenticated structural input is not an empty managed inventory:
        # that would retain a historical effective maximum below.
        return tuple(replace(status, effective=None, reason="current_managed_resource_inputs_unproven")
            if status.path.startswith("resource:")
            and status.path.removeprefix("resource:") in authority.managed_resource_targets and status.is_effective
            else status for status in authority.resource_statuses)
    templates = _qualified_current_managed_templates(
        authority, definition, systems_service=systems_service,
        campaign_page_records=campaign_page_records,
    )
    rows: list[EffectiveStatus] = []
    for status in authority.resource_statuses:
        tracker_id = status.path.removeprefix("resource:")
        if not status.path.startswith("resource:") or tracker_id not in templates or not status.is_effective:
            rows.append(status)
            continue
        expected = templates[tracker_id] if sum(row.path == status.path for row in authority.resource_statuses) == 1 else None
        if expected is not None:
            historical_seed = status.raw.get("initial_current") if isinstance(status.raw, dict) else None
            uninitialized = historical_seed is None and isinstance(definition.source.get("native_reconstruction_choices"), dict)
            if not uninitialized and (type(historical_seed) is not int or historical_seed < 0):
                expected = None
            else:
                expected = {**expected, "initial_current": historical_seed}
        rows.append(replace(status, effective=expected, reason=(
            "derived_from_current_managed_owner" if expected is not None else (
                "associated_tracker_current_capacity_unproven"
                if any(row["tracker_id"] == tracker_id for row in authority.tracker_associations)
                else "current_managed_resource_unproven")
        )))
    return tuple(rows)


def validate_native_managed_resource_templates(
    definition: CharacterDefinition, state: dict[str, Any], *, authority: SourceAuthority,
    systems_service: Any, campaign_page_records: list[Any] | None,
    prior_definition: CharacterDefinition | None = None,
    restored_resource_currents: tuple[tuple[str, int], ...] = (),
    prior_authority: SourceAuthority | None = None,
) -> None:
    """Validate native issuance independently of an existing resource witness."""
    from .character_equipment_activation import effective_definition
    current, _ = effective_definition(definition, state)
    bound = authority.bind_current_numbers(
        definition, state, systems_service=systems_service,
        campaign_page_records=campaign_page_records,
    )
    expected = _qualified_current_managed_templates(
        bound, current, systems_service=systems_service,
        campaign_page_records=campaign_page_records,
    )
    prior = list(prior_definition.resource_templates or []) if prior_definition is not None else []
    restored = dict(restored_resource_currents)
    if len(restored) != len(restored_resource_currents) or set(restored) - set(expected):
        raise NativeAdvancementValidationError("Native managed resource inputs changed. Review this advancement.")
    for tracker_id, template in expected.items():
        matching = [row for row in definition.resource_templates if isinstance(row, dict) and _text(row.get("id")) == tracker_id]
        old = [row for row in prior if isinstance(row, dict) and _text(row.get("id")) == tracker_id]
        if (template is None or len(matching) != 1 or len(old) > 1
                # Retained notes are history; current descriptions are projected.
                or any(matching[0].get(key) != value for key, value in template.items() if key != "notes")
                or old and matching[0].get("initial_current") != old[0].get("initial_current")
                or old and type(matching[0].get("initial_current")) is int and matching[0]["initial_current"] > template.get("max", -1)
                    and (prior_authority is None or not prior_authority.resource_status("resource", tracker_id).is_effective)
                or tracker_id in restored and (old or type(restored[tracker_id]) is not int
                    or not 0 <= restored[tracker_id] <= template.get("max", -1))
                or not old and matching[0].get("initial_current") != restored.get(tracker_id, template.get("max"))):
            raise NativeAdvancementValidationError("Native managed resource inputs changed. Review this advancement.")


def _source_derived_resource_bases(
    definition: CharacterDefinition, *, systems_service: Any,
    pages: dict[str, list[Any]], verified_class_rows: frozenset[str],
    feature_statuses: tuple[AuthorityStatus, ...],
    field_statuses: tuple[EffectiveStatus, ...], feature_composition=None, armor_selectors=None, tracker_bindings=(),
) -> dict[str, str]:
    """Prove exact current owner and formula inputs for durable resource witnesses.

    Only source shapes whose formula can be independently recomputed are
    included. A saved template or state row alone never supplies its owner.
    """
    from .character_feature_trackers import build_managed_resource_tracker_template
    from .managed_resource_registry import resolve_managed_resource_family_and_member, managed_resource_feature_identity
    from .character_ability_inputs import input_records, resolve_inputs
    from .character_adjustments import apply_recoverable_ability_score_penalties, normalize_recoverable_penalties
    from .character_hit_dice import derive_hit_dice_max_pools, _hit_die_faces_for_class_row
    from .character_spell_slots import spell_slot_lanes_from_spellcasting
    from .character_builder_derivation import (
        _spell_slot_progression_for_class_level,
        _shared_slot_progression_for_caster_level,
        _multiclass_slot_contribution_for_row,
    )
    from .character_builder_foundation import (
        _class_caster_progression, SUPPORTED_MULTICLASS_CASTER_PROGRESSIONS,
    )

    class_rows = profile_class_rows(definition.profile)
    class_ids = [_text(row.get("row_id")) for row in class_rows]
    if not class_ids or any(not row_id for row_id in class_ids) or len(class_ids) != len(set(class_ids)):
        return {}
    class_by_id = {row_id: row for row_id, row in zip(class_ids, class_rows)}
    feature_ids = [_text(row.get("id")) for row in definition.features if isinstance(row, dict)]
    template_ids = [_text(row.get("id")) for row in definition.resource_templates if isinstance(row, dict)]
    if (any(not value for value in feature_ids + template_ids)
            or len(feature_ids) != len(set(feature_ids))
            or len(template_ids) != len(set(template_ids))):
        return {}
    status_by_feature = {row.instance_id: row.status for row in feature_statuses if row.kind == "feature"}
    from .character_builder_derivation import (
        _apply_feat_ability_score_bonuses, _campaign_option_feat_selections_from_features,
        _campaign_option_feat_selected_choices_from_features, _structured_ability_score_minimums,
    )
    qualified_features = []
    for feature in definition.features:
        if not isinstance(feature, dict) or status_by_feature.get(_text(feature.get("id"))) != VERIFIED:
            continue
        kind, key = _source_identity(feature)
        current, reason = _current_payload(
            campaign_slug=definition.campaign_slug, kind="feature", source_kind=kind, source_key=key,
            systems_service=systems_service, pages=pages, expected_feature=feature,
            expected_profile=definition.profile,
        )
        if current is None or reason:
            continue
        row = {**feature, "campaign_option": deepcopy(current.get("campaign_option") or {})}
        if isinstance(row["campaign_option"], dict):
            row["campaign_option"]["selected_choices"] = deepcopy(dict(feature.get("campaign_option") or {}).get("selected_choices") or {})
        qualified_features.append(row)
    stats = dict(definition.stats or {})
    records = input_records(stats)
    bonuses = _apply_feat_ability_score_bonuses(
        {key: 0 for key in ("str", "dex", "con", "int", "wis", "cha")},
        feat_selections=_campaign_option_feat_selections_from_features(qualified_features),
        selected_choices=_campaign_option_feat_selected_choices_from_features(qualified_features), strict=False,
    )
    pre_item, resolved_inputs = resolve_inputs(
        stats, bonuses=bonuses, minimums=_structured_ability_score_minimums(qualified_features),
    )
    pre_item = apply_recoverable_ability_score_penalties(pre_item, normalize_recoverable_penalties(stats.get("recoverable_penalties")))
    effective_scores: dict[str, int] = {}
    for key in ("str", "dex", "con", "int", "wis", "cha"):
        status = next((row for row in field_statuses
                       if row.path == f"stats.ability_scores.{key}.score"), None)
        if status is None:
            continue
        if (key in records and records[key].get("stage") in {"base", "pre_penalty"}
                and resolved_inputs[key].get("stage") != "unresolved"
                and (status.is_effective or status.status in {VERIFIED, MANUAL}
                     and status.reason == "baseline_authorized")):
            effective_scores[key] = pre_item[key]
    bases: dict[str, str] = {}
    from .character_feature_composition import resolve_feature_composition, registered_owner_payload
    composition = feature_composition if feature_composition is not None else resolve_feature_composition(
        definition, systems_service, feature_statuses=feature_statuses, verified_class_rows=verified_class_rows)
    pools = _current_managed_pool_owners(
        definition, systems_service=systems_service, pages=pages,
        verified_class_rows=verified_class_rows, feature_statuses=feature_statuses,
        feature_composition=composition, armor_selectors=armor_selectors, tracker_bindings=tracker_bindings,
    )
    for template in definition.resource_templates:
        if not isinstance(template, dict):
            continue
        template_id = _text(template.get("id"))
        owners = [feature for feature in definition.features
                  if isinstance(feature, dict) and _text(feature.get("tracker_ref")) == template_id]
        pool = pools.get(template_id)
        existing_singleton = len(owners) == 1 and managed_resource_feature_identity(owners[0]) is not None
        if pool is None and not existing_singleton:
            continue
        feature = owners[0] if existing_singleton else pool["members"][0]["canonical"]
        row_id = _text(feature.get("class_row_id"))
        if (status_by_feature.get(_text(feature.get("id"))) != VERIFIED
                or row_id not in verified_class_rows
                or _text(template.get("class_row_id")) != row_id):
            continue
        source_kind, source_key = _source_identity(feature)
        current, reason = _current_payload(
            campaign_slug=definition.campaign_slug, kind="feature",
            source_kind=source_kind, source_key=source_key,
            systems_service=systems_service, pages=pages,
            expected_slug=_text(dict(feature.get("systems_ref") or {}).get("slug")),
            expected_feature=feature, expected_profile=definition.profile,
        )
        if source_kind.startswith("systems") and dict(feature.get("systems_ref") or {}).get("entry_type") == "feature":
            current = registered_owner_payload(composition, _text(feature.get("id")), current, definition=definition)
        family, member = resolve_managed_resource_family_and_member(feature)
        slug = _text(dict(feature.get("systems_ref") or {}).get("slug"))
        if (current is None or reason or not family or not member or not slug
                or managed_resource_feature_identity(feature) is None
                or slug.casefold() not in {
                    _text(entry.get("slug")).casefold()
                    for entry in list(family.get("inventory") or ()) if isinstance(entry, dict)
                }):
            continue
        tracker = dict(member.get("tracker") or {})
        formula = dict(tracker.get("max_formula") or {})
        def required_abilities(part: dict[str, Any]) -> set[str]:
            if _text(part.get("kind")).lower() == "ability_modifier":
                return {_text(part.get("ability")).lower()}
            return set().union(*(required_abilities(child) for child in list(part.get("parts") or [])
                                 if isinstance(child, dict)))
        if any(key not in effective_scores for key in required_abilities(formula)):
            continue
        def uses_proficiency_bonus(part: dict[str, Any]) -> bool:
            return (_text(part.get("kind")).lower() in {"proficiency_bonus", "total_half_level"}
                    or any(uses_proficiency_bonus(child)
                           for child in list(part.get("parts") or [])
                           if isinstance(child, dict)))
        if uses_proficiency_bonus(formula) and (
                set(class_ids) != set(verified_class_rows)
                or any(type(row.get("level")) is not int or row["level"] < 1
                       for row in class_rows)):
            continue
        level = class_by_id[row_id].get("level")
        if type(level) is not int or not 1 <= level <= 20:
            continue
        attained = current.get("level")
        if type(attained) is not int or not 1 <= attained <= level:
            continue
        expected = build_managed_resource_tracker_template(
            member, feature, ability_scores=effective_scores,
            current_level=level, display_order=int(template.get("display_order") or 0),
            total_character_level=sum(row["level"] for row in class_rows
                                      if type(row.get("level")) is int),
        )
        from .character_tracker_associations import physical_id
        if expected is not None:
            expected["id"] = physical_id(member, feature, tracker_bindings)
        if expected is None or _text(expected.get("id")) != template_id:
            continue
        expected.pop("activation_type", None)
        expected["class_row_id"] = row_id
        # Exact trusted audit/value custody authenticates this historical seed.
        # A later inactive-item capacity may be smaller than the original seed.
        initial_current = template.get("initial_current")
        uninitialized = initial_current is None and isinstance(definition.source.get("native_reconstruction_choices"), dict)
        if (not uninitialized and (type(initial_current) is not int or initial_current < 0)
                or type(template.get("max")) is not int
                or template["max"] < 0):
            continue
        expected["initial_current"] = initial_current
        # Historical notes need not equal the current source-derived description.
        # Keep the complete derived recipe (including its notes) in the proof.
        if any(template.get(key) != value for key, value in expected.items() if key not in {"max", "notes"}):
            continue
        basis_payload = {
            "owner": _source_identity(feature), "source": current,
            "class": class_by_id[row_id], "formula": formula,
            "inputs": {key: effective_scores[key] for key in sorted(required_abilities(formula))},
            "template": expected,
        }
        if not existing_singleton:
            basis_payload["pool_members"] = pool["members"]
        associated = [row for row in tracker_bindings if row["tracker_id"] == template_id]
        if associated:
            basis_payload["physical_association"] = associated[0]
        # New source-owned recipes also bind local publication content. Old
        # family digest formats remain unchanged for retained witnesses.
        from .character_feature_composition import TIDES_KEY
        replacement_owner = composition.resource_owner(_text(feature.get("id")))
        if replacement_owner is not None:
            basis_payload["registered_owner"] = replacement_owner
        elif source_kind.startswith("systems") and source_key == TIDES_KEY:
            publication = _current_systems_entry(definition.campaign_slug, source_kind, source_key, systems_service)
            if publication is None:
                continue
            basis_payload["local_rules"] = {"metadata": publication.metadata, "body": publication.body}
        bases[f"resource:{template_id}"] = numeric_value_digest(basis_payload)
    # Hit Die faces must come from the current class payload, not a copied
    # class-row override or the fallback die used for an unknown class.
    if set(class_ids) == set(verified_class_rows):
        class_proofs: list[dict[str, Any]] = []
        for row_id in class_ids:
            row = class_by_id[row_id]
            source_kind, source_key = _source_identity(row)
            current, reason = _current_payload(
                campaign_slug=definition.campaign_slug, kind="class",
                source_kind=source_kind, source_key=source_key,
                systems_service=systems_service, pages=pages,
                expected_slug=_text(dict(row.get("systems_ref") or {}).get("slug")),
            )
            if current is None or reason:
                break
            current_faces = _hit_die_faces_for_class_row({"metadata": current})
            if current_faces <= 0 or _hit_die_faces_for_class_row(row) != current_faces:
                break
            class_proofs.append({"row": row, "source": current, "faces": current_faces})
        if len(class_proofs) == len(class_ids):
            for pool in derive_hit_dice_max_pools(definition):
                faces = pool["faces"]
                owners = [proof for proof in class_proofs if proof["faces"] == faces]
                bases[f"hit_die:{faces}"] = numeric_value_digest({
                    "owners": owners, "faces": faces, "max": pool["max"],
                })
    raw_lanes = list(dict(definition.spellcasting or {}).get("slot_lanes") or [])
    lane_ids = [_text(lane.get("id")) for lane in raw_lanes if isinstance(lane, dict)]
    if (raw_lanes and len(lane_ids) == len(raw_lanes)
            and all(lane_ids) and len(lane_ids) == len(set(lane_ids))):
        for lane in spell_slot_lanes_from_spellcasting(definition.spellcasting):
            lane_id = _text(lane.get("id"))
            row_ids = list(lane.get("row_ids") or [])
            if lane.get("shared"):
                if (lane_id != "shared-multiclass-slots" or len(row_ids) < 2
                        or len(row_ids) != len(set(row_ids))
                        or set(class_ids) != set(verified_class_rows)):
                    continue
                shareable: list[dict[str, Any]] = []
                shared_valid = True
                for class_row_id in class_ids:
                    class_row = class_by_id[class_row_id]
                    if class_row.get("subclass_ref"):
                        shared_valid = False
                        break
                    source_kind, source_key = _source_identity(class_row)
                    current, reason = _current_payload(
                        campaign_slug=definition.campaign_slug, kind="class",
                        source_kind=source_kind, source_key=source_key,
                        systems_service=systems_service, pages=pages,
                        expected_slug=_text(dict(class_row.get("systems_ref") or {}).get("slug")),
                    )
                    entry = _current_systems_entry(definition.campaign_slug, source_kind, source_key, systems_service)
                    level = class_row.get("level")
                    class_name = _text(getattr(entry, "title", ""))
                    if (current is None or reason or entry is None or not class_name
                            or _text(class_row.get("class_name")).casefold() != class_name.casefold()
                            or type(level) is not int or level < 1):
                        shared_valid = False
                        break
                    progression = _class_caster_progression(
                        class_name, selected_class=entry, row_level=level,
                    )
                    if progression in SUPPORTED_MULTICLASS_CASTER_PROGRESSIONS:
                        shareable.append({"row_id": class_row_id, "row": class_row,
                                          "source": current, "progression": progression})
                if (not shared_valid or len(shareable) < 2
                        or set(row_ids) != {proof["row_id"] for proof in shareable}):
                    continue
                total_caster_level = sum(
                    _multiclass_slot_contribution_for_row(proof["row"]["level"], proof["progression"])
                    for proof in shareable
                )
                expected = _shared_slot_progression_for_caster_level(total_caster_level)
                if _canonical(expected) != _canonical(list(lane.get("slot_progression") or [])):
                    continue
                for slot in expected:
                    slot_level = slot.get("level")
                    if type(slot_level) is not int or slot_level < 1:
                        continue
                    bases[f"spell_slot:{lane_id}:{slot_level}"] = numeric_value_digest({
                        "owners": sorted(shareable, key=lambda row: row["row_id"]),
                        "lane": lane_id, "level": slot_level,
                        "max": slot.get("max_slots"),
                    })
                continue
            if (not lane_id or len(row_ids) != 1
                    or row_ids[0] not in verified_class_rows):
                continue
            row = class_by_id[row_ids[0]]
            reconstructed = isinstance(definition.source.get("native_reconstruction_choices"), dict)
            if row.get("subclass_ref") and not reconstructed:
                continue
            source_kind, source_key = _source_identity(row)
            current, reason = _current_payload(
                campaign_slug=definition.campaign_slug, kind="class",
                source_kind=source_kind, source_key=source_key,
                systems_service=systems_service, pages=pages,
                expected_slug=_text(dict(row.get("systems_ref") or {}).get("slug")),
            )
            entry = _current_systems_entry(definition.campaign_slug, source_kind, source_key, systems_service)
            level = row.get("level")
            class_name = _text(getattr(entry, "title", ""))
            if (current is None or reason or entry is None or not class_name
                    or _text(row.get("class_name")).casefold() != class_name.casefold()
                    or type(level) is not int or level < 1):
                continue
            subclass = _current_reconstruction_subclass(definition, row, entry, systems_service) if reconstructed else None
            if row.get("subclass_ref") and subclass is None:
                continue
            expected = _spell_slot_progression_for_class_level(
                class_name, level, selected_class=entry, selected_subclass=subclass,
            )
            actual = list(lane.get("slot_progression") or [])
            if _canonical(expected) != _canonical(actual):
                continue
            for slot in expected:
                slot_level = slot.get("level")
                if type(slot_level) is not int or slot_level < 1:
                    continue
                basis = {
                    "owner": row, "source": current, "lane": lane_id,
                    "level": slot_level, "max": slot.get("max_slots"),
                }
                if subclass is not None:
                    basis["subclass_source"] = {"entry_key": subclass.entry_key, "metadata": subclass.metadata, "body": subclass.body}
                bases[f"spell_slot:{lane_id}:{slot_level}"] = numeric_value_digest(basis)
    return bases


def _source_derived_hp_basis(
    definition: CharacterDefinition, *, systems_service: Any,
    pages: dict[str, list[Any]], verified_class_rows: frozenset[str],
    feature_statuses: tuple[AuthorityStatus, ...], _current_inputs=None,
) -> str | None:
    """Bind a native HP baseline/history to exact current classes and features."""
    from .character_hit_dice import _hit_die_faces_for_class_row
    source = dict(definition.source or {})
    if _text(source.get("source_type")) != "native_character_builder":
        return None
    class_rows = profile_class_rows(definition.profile)
    ids = [_text(row.get("row_id")) for row in class_rows]
    if (not ids or any(not value for value in ids) or len(ids) != len(set(ids))
            or set(ids) != set(verified_class_rows)):
        return None
    source_classes: list[dict[str, Any]] = []
    for row in class_rows:
        source_kind, source_key = _source_identity(row)
        current, reason = _current_payload(
            campaign_slug=definition.campaign_slug, kind="class",
            source_kind=source_kind, source_key=source_key,
            systems_service=systems_service, pages=pages,
            expected_slug=_text(dict(row.get("systems_ref") or {}).get("slug")),
        )
        if current is None or reason or _hit_die_faces_for_class_row(row) != _hit_die_faces_for_class_row({"metadata": current}):
            return None
        source_classes.append({"row": row, "source": current})
    source_features: list[dict[str, Any]] = []
    statuses = {row.instance_id: row.status for row in feature_statuses if row.kind == "feature"}
    recipe_value = dict(source.get("native_progression") or {}).get("hp_recipe")
    hp_owners = {row.get("owner_id") for row in recipe_value.get("continuing_effects", [])
                 if isinstance(row, dict)} if isinstance(recipe_value, dict) else None
    for feature in definition.features:
        if hp_owners is not None and isinstance(feature, dict) and feature.get("id") not in hp_owners:
            continue
        if not isinstance(feature, dict) or statuses.get(_text(feature.get("id"))) != VERIFIED:
            return None
        source_kind, source_key = _source_identity(feature)
        current, reason = _current_payload(
            campaign_slug=definition.campaign_slug, kind="feature",
            source_kind=source_kind, source_key=source_key,
            systems_service=systems_service, pages=pages,
            expected_slug=_text(dict(feature.get("systems_ref") or {}).get("slug")),
            expected_feature=feature, expected_profile=definition.profile,
        )
        if current is None or reason:
            return None
        source_features.append({"id": feature.get("id"), "source": current})
    inputs = dict(dict(definition.stats or {}).get("ability_inputs") or {}).get("scores") or {}
    con = dict(inputs.get("con") or {}) if isinstance(inputs, dict) else {}
    con_score = con.get("score")
    if (con.get("stage") not in {"base", "pre_penalty"}
            or type(con_score) is not int):
        return None
    progression = dict(source.get("native_progression") or {})
    if progression.get("hp_recipe") is not None:
        from .character_hp_recipe import canonical_recipe, evaluate_recipe
        try:
            if len(class_rows) != 1:
                return None
            recipe = canonical_recipe(progression["hp_recipe"], faces=_hit_die_faces_for_class_row(class_rows[0]))
            current_con = dict(dict(definition.stats.get("ability_scores") or {}).get("con") or {}).get("score")
            expected = evaluate_recipe(recipe, progression.get("history", []),
                level=class_rows[0]["level"], constitution=current_con,
                faces=_hit_die_faces_for_class_row(class_rows[0]))
            if definition.stats.get("max_hp") != expected:
                return None
            from .character_reconstruction_authority import reconstructed_input_bases
            con_basis = (_current_inputs.constitution(definition, systems_service, feature_statuses)
                if _current_inputs is not None else
                reconstructed_input_bases(definition, systems_service=systems_service,
                    statuses=feature_statuses).get("stats.ability_scores.con.score"))
            if con_basis is None or len(source_features) != len(hp_owners):
                return None
            return numeric_value_digest({"classes": source_classes, "features": source_features,
                "constitution_input": con, "current_constitution": current_con,
                "constitution_basis": con_basis,
                "recipe": recipe, "history": progression.get("history", []), "max_hp": expected})
        except (KeyError, TypeError, ValueError):
            return None
    baseline = dict(progression.get("hp_baseline") or {})
    baseline_level, baseline_hp = baseline.get("level"), baseline.get("max_hp")
    current_hp = dict(definition.stats or {}).get("max_hp")
    if (type(baseline_level) is not int or baseline_level != 1
            or type(baseline_hp) is not int or baseline_hp < 1
            or type(current_hp) is not int or current_hp < 1):
        return None
    history = list(progression.get("history") or [])
    total_level = sum(row.get("level") for row in class_rows if type(row.get("level")) is int)
    if total_level != baseline_level + len(history):
        return None
    if not history:
        if len(class_rows) != 1:
            return None
        faces = _hit_die_faces_for_class_row(class_rows[0])
        if baseline_hp != max(1, faces + (con_score - 10) // 2) or current_hp != baseline_hp:
            return None
    else:
        calculated = baseline_hp
        for index, event in enumerate(history, start=1):
            if (not isinstance(event, dict) or event.get("kind") != "level_up"
                    or event.get("from_level") != index
                    or event.get("to_level") != index + 1
                    or event.get("target_level") != index + 1
                    or type(event.get("hp_gain")) is not int or event["hp_gain"] < 1
                    or type(event.get("max_hp_delta")) is not int
                    or event["max_hp_delta"] < event["hp_gain"]):
                return None
            row_id = _text(event.get("class_row_id"))
            matching = [row for row in class_rows if _text(row.get("row_id")) == row_id]
            if len(matching) != 1 or dict(event.get("class_ref") or {}) != dict(matching[0].get("systems_ref") or {}):
                return None
            calculated += event["max_hp_delta"]
        if calculated != current_hp:
            return None
    return numeric_value_digest({
        "classes": source_classes, "features": source_features,
        "constitution_input": con, "baseline": baseline,
        "history": history, "max_hp": current_hp,
    })


def _source_derived_formula_bases(
    definition: CharacterDefinition, *, systems_service: Any,
    verified_class_rows: frozenset[str], verified_source_rows: frozenset[str],
    grants: tuple[AuthorityGrant, ...], source_snapshot_digest: str,
) -> dict[str, str]:
    """Offer a basis for native issuance only when current class math is exact."""
    from .character_builder_derivation import _spellcasting_ability_name_for_class

    profile_rows = profile_class_rows(definition.profile)
    profile_by_id = {_text(row.get("row_id")): row for row in profile_rows}
    if len(profile_by_id) != len(profile_rows):
        return {}
    spell_rows = list(dict(definition.spellcasting or {}).get("class_rows") or [])
    ids = [_text(row.get("class_row_id")) for row in spell_rows if isinstance(row, dict)]
    if len(ids) != len(spell_rows) or len(ids) != len(set(ids)):
        return {}
    stats = dict(definition.stats or {})
    pb = stats.get("proficiency_bonus")
    abilities = dict(stats.get("ability_scores") or {})
    if type(pb) is not int:
        return {}
    labels = {"Strength": "str", "Dexterity": "dex", "Constitution": "con",
              "Intelligence": "int", "Wisdom": "wis", "Charisma": "cha"}
    bases: dict[str, str] = {}
    for spell_row in spell_rows:
        row_id = _text(spell_row.get("class_row_id"))
        profile = profile_by_id.get(row_id)
        reconstructed = isinstance(definition.source.get("native_reconstruction_choices"), dict)
        if row_id not in verified_class_rows or profile is None or profile.get("subclass_ref") and not reconstructed:
            continue
        source_kind, source_key = _source_identity(profile)
        entry = _current_systems_entry(definition.campaign_slug, source_kind, source_key, systems_service)
        if entry is None or _text(getattr(entry, "entry_type", "")) != "class":
            continue
        if type(profile.get("level")) is not int or profile["level"] < 1:
            continue
        subclass = _current_reconstruction_subclass(definition, profile, entry, systems_service) if reconstructed else None
        if profile.get("subclass_ref") and subclass is None:
            continue
        expected_ability = _spellcasting_ability_name_for_class(
            _text(getattr(entry, "title", "")), selected_class=entry,
            row_level=profile["level"], selected_subclass=subclass,
        )
        ability_key = labels.get(expected_ability)
        if (not ability_key or _text(spell_row.get("spellcasting_ability")) != expected_ability
                or type(dict(abilities.get(ability_key) or {}).get("score")) is not int):
            continue
        modifier = (abilities[ability_key]["score"] - 10) // 2
        expected_values = {"spell_attack_bonus": pb + modifier,
                           "spell_save_dc": 8 + pb + modifier}
        raw_provenance = spell_row.get("spell_metric_provenance")
        provenance = dict(raw_provenance) if isinstance(raw_provenance, dict) else {}
        for metric, expected in expected_values.items():
            record = provenance.get(metric)
            if (spell_row.get(metric) != expected
                    or not isinstance(record, dict) or record.get("kind") != "formula"):
                continue
            target_id = f"spell_metric:class:{row_id}:{metric}"
            basis = {
                "source_snapshot": source_snapshot_digest,
                "class_source": {"entry_key": source_key, "metadata": getattr(entry, "metadata", None)},
                "class_row": profile, "ability": ability_key,
                "score": abilities[ability_key]["score"], "pb": pb,
                "metric": metric, "expected": expected,
            }
            if reconstructed:
                basis.pop("source_snapshot")
                if subclass is not None:
                    basis["subclass_source"] = {"entry_key": subclass.entry_key, "metadata": subclass.metadata, "body": subclass.body}
            bases[target_id] = numeric_value_digest(basis)
    from .item_spell_support import parse_item_spell_support
    from .character_builder_spells import _resolve_item_spell_selector

    source_proofs: dict[str, list[tuple[str, AuthorityGrant]]] = {}
    item_proofs: dict[str, list[tuple[Any, AuthorityGrant]]] = {}
    item_behaviors: dict[str, set[tuple[str, ...]]] = {}
    current_spell_entries = getattr(systems_service, "list_enabled_entries_for_campaign", None)
    spell_entries = (read_enabled_spell_entries(systems_service, definition.campaign_slug)
                     if callable(current_spell_entries) else None)
    if spell_entries is None:
        spell_entries = (current_spell_entries(definition.campaign_slug, entry_type="spell")
                         if callable(current_spell_entries) else [])
    spell_catalog = _spell_entries_catalog(spell_entries)
    item_blocks: dict[str, list[Any]] = {}
    for grant in grants:
        if grant.kind == "item":
            payload = json.loads(grant.payload_json)
            if "spell_support" in payload:
                item_blocks.setdefault(grant.instance_id, []).append(payload["spell_support"])
    invalid_item_owners = {
        owner for owner, blocks in item_blocks.items()
        if (parsed := parse_item_spell_support(blocks)).diagnostics
        or any(record.invalid for record in parsed.records)
    }
    def visit(value: Any, grant: AuthorityGrant) -> None:
        if isinstance(value, list):
            for child in value:
                visit(child, grant)
        elif isinstance(value, dict):
            row_id = _text(value.get("spell_source_row_id") or value.get("source_row_id"))
            ability_key = _text(value.get("spell_source_ability_key")
                                or value.get("spellcasting_ability_key"))
            if row_id and ability_key in labels.values():
                source_proofs.setdefault(row_id, []).append((ability_key, grant))
            for child in value.values():
                visit(child, grant)
    for grant in grants:
        payload = json.loads(grant.payload_json)
        if grant.kind == "item" and isinstance(payload.get("spell_support"), dict):
            if grant.instance_id in invalid_item_owners:
                continue
            parsed = parse_item_spell_support([payload["spell_support"]])
            if parsed.diagnostics or any(record.invalid for record in parsed.records):
                continue
            for record in parsed.records:
                if record.source_row_id and record.source_ability_key and record.source_row_kind in {"item", "source"}:
                    item_behaviors.setdefault(record.source_row_id, set()).add((
                        record.source_row_kind, record.source_row_title,
                        record.source_ability_key, record.source_mode,
                        record.spell_list_class_name, grant.source_key,
                    ))
                    if _resolve_item_spell_selector(record.spell_selector, spell_catalog) is not None:
                        item_proofs.setdefault(record.source_row_id, []).append((record, grant))
        else:
            visit(payload, grant)
    source_rows = list(dict(definition.spellcasting or {}).get("source_rows") or [])
    source_ids = [_text(row.get("source_row_id")) for row in source_rows if isinstance(row, dict)]
    if len(source_rows) != len(source_ids) or len(source_ids) != len(set(source_ids)):
        return bases
    for spell_row in source_rows:
        row_id = _text(spell_row.get("source_row_id"))
        proofs = list({(ability, grant.grant_id): (ability, grant)
                       for ability, grant in source_proofs.get(row_id) or []}.values())
        item_rows = item_proofs.get(row_id) or []
        if row_id not in verified_source_rows:
            continue
        item_basis: Any = None
        if item_rows:
            # All declarations must describe one exact row behavior. A
            # different spell may share that formula; a disagreeing same-spell
            # access declaration cannot.
            behaviors = {
                (record.source_row_kind, record.source_row_title,
                 record.source_ability_key, record.source_mode,
                 record.spell_list_class_name, grant.source_key)
                for record, grant in item_rows
            }
            claims: dict[str, set[tuple[Any, ...]]] = {}
            for record, _ in item_rows:
                spell_entry = _resolve_item_spell_selector(record.spell_selector, spell_catalog)
                if spell_entry is None:
                    continue
                spell_identity = _text(getattr(spell_entry, "entry_key", "")) or _text(getattr(spell_entry, "slug", ""))
                claims.setdefault(spell_identity, set()).add((
                    record.access_type, record.access_uses, record.access_reset_on,
                    record.mark, record.always_prepared, record.bonus_known, record.ritual,
                ))
            if (len(behaviors) != 1 or len(item_behaviors.get(row_id, set())) != 1
                    or any(len(values) != 1 for values in claims.values()) or proofs):
                continue
            ability_key = item_rows[0][0].source_ability_key
            item_basis = tuple(sorted((record.spell_key, record.access_type,
                                       record.access_uses, record.access_reset_on,
                                       grant.grant_id)
                                      for record, grant in item_rows))
            grant = item_rows[0][1]
            physical_copies = [item for item in definition.equipment_catalog
                               if isinstance(item, dict)
                               and _source_identity(item) == (grant.source_kind, grant.source_key)]
            if len(physical_copies) > 1:
                # A formula belongs to the one approved item source. Physical
                # copies share its rule, so equip/attune changes must not
                # change the basis merely by changing the number of grants.
                item_basis = ("identical_physical_copies_v2", tuple(sorted({
                    (record.spell_key, record.access_type, record.access_uses,
                     record.access_reset_on, source.source_kind, source.source_key,
                     source.effect_id, source.payload_json)
                    for record, source in item_rows
                })))
            elif len(item_rows) == 1:
                raw_effect = json.loads(grant.payload_json).get("spell_support") or {}
                if (isinstance(raw_effect, dict)
                        and raw_effect.get("spell_source_row_id") == row_id
                        and raw_effect.get("spell_source_ability_key") == ability_key):
                    item_basis = None
        elif len(proofs) == 1:
            ability_key, grant = proofs[0]
        else:
            continue
        expected_ability = next((label for label, key in labels.items() if key == ability_key), "")
        score = dict(abilities.get(ability_key) or {}).get("score")
        if _text(spell_row.get("spellcasting_ability")) != expected_ability or type(score) is not int:
            continue
        modifier = (score - 10) // 2
        expected_values = {"spell_attack_bonus": pb + modifier,
                           "spell_save_dc": 8 + pb + modifier}
        raw_provenance = spell_row.get("spell_metric_provenance")
        provenance = dict(raw_provenance) if isinstance(raw_provenance, dict) else {}
        for metric, expected in expected_values.items():
            record = provenance.get(metric)
            if (spell_row.get(metric) != expected
                    or not isinstance(record, dict) or record.get("kind") != "formula"):
                continue
            target_id = f"spell_metric:source:{row_id}:{metric}"
            basis_payload = {
                "source_snapshot": source_snapshot_digest,
                "ability": ability_key, "score": score, "pb": pb,
                "metric": metric, "expected": expected,
            }
            # Keep the historic singleton digest byte-for-byte for flat
            # declarations. Multi-block item proof uses all exact grants.
            basis_payload["grant"] = (
                item_basis if item_basis is not None else
                (grant.grant_id, grant.payload_json)
            )
            if isinstance(definition.source.get("native_reconstruction_choices"), dict):
                basis_payload.pop("source_snapshot")
            bases[target_id] = numeric_value_digest(basis_payload)
    return bases


def _page_feature_resource_bases(
    definition: CharacterDefinition, *, pages: dict[str, list[Any]],
    feature_statuses: tuple[AuthorityStatus, ...], source_snapshot_digest: str,
) -> dict[str, str]:
    """Recompute an exact tracker from one currently visible committed page."""
    from .character_builder_features import _build_campaign_option_tracker_template
    from .character_builder_static_bundle import _campaign_page_option_allowed_for_linked_field
    from .character_update_adapters import _campaign_option_is_choice_bearing, _definition_total_level

    result: dict[str, str] = {}
    if not source_snapshot_digest:
        return result
    features = [row for row in definition.features if isinstance(row, dict)]
    templates = [row for row in definition.resource_templates if isinstance(row, dict)]
    for template in templates:
        tracker_id = _text(template.get("id"))
        owners = [row for row in features if _text(row.get("tracker_ref")) == tracker_id]
        if not tracker_id or len(owners) != 1 or sum(
            _text(row.get("id")) == tracker_id for row in templates
        ) != 1:
            continue
        feature = owners[0]
        feature_id = _text(feature.get("id"))
        page_ref = _text(feature.get("page_ref"))
        records = pages.get(page_ref) or []
        if (not feature_id or tracker_id != f"campaign-option-tracker:{feature_id}"
                or len(records) != 1 or not page_ref
                or sum(_text(row.get("id")) == feature_id for row in features) != 1
                or any(row.status != VERIFIED for row in feature_statuses
                       if row.kind == "feature" and row.instance_id == feature_id)):
            continue
        record = records[0]
        page = _field(record, "page")
        revision = _field(page, "committed_revision")
        if (type(revision) is not int or revision < 1
                or not bool(_field(page, "published"))
                or bool(_field(page, "is_deprecated_wiki_overview"))):
            continue
        option = build_campaign_page_character_option(record, default_kind="feature")
        if (not isinstance(option, dict) or _campaign_option_is_choice_bearing(option)
                or not _campaign_page_option_allowed_for_linked_field(
                    record, field_kind="campaign_page_feature", campaign_option=option,
                ) or _canonical(feature.get("campaign_option")) != _canonical(option)):
            continue
        expected = _build_campaign_option_tracker_template(
            feature, display_order=int(template.get("display_order") or 0),
            current_level=_definition_total_level(definition.to_dict()),
        )
        if (not isinstance(expected, dict) or expected.get("id") != tracker_id
                or any(template.get(key) != value for key, value in expected.items())):
            continue
        if sum(1 for row in feature_statuses if row.kind == "feature"
               and row.instance_id == feature_id and row.status == VERIFIED) != 1:
            continue
        basis = {
            "source_snapshot": source_snapshot_digest,
            "page_ref": page_ref, "page_revision": revision,
            "feature_id": feature_id, "feature": feature,
            "template": template, "approved_option": option,
        }
        if isinstance(definition.source.get("native_reconstruction_choices"), dict):
            basis.pop("source_snapshot")
        result[f"resource:{tracker_id}"] = numeric_value_digest(basis)
    return result


def with_pending_page_feature_witnesses(
    authority: SourceAuthority, definition: CharacterDefinition,
    state: dict[str, Any], markers: tuple[dict[str, Any], ...],
) -> SourceAuthority:
    """Simulate only exact page witnesses until the publication audit commits."""
    if not markers:
        return authority
    values = numeric_target_values(definition, state)
    bases = dict(authority.resource_basis_digests)
    existing = list(dict(definition.source or {}).get("source_authorizations") or [])
    actions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for marker in markers:
        target_id = marker.get("target_id") if isinstance(marker, dict) else None
        key = ("resource", target_id, "owner_reset")
        if (not isinstance(target_id, str) or target_id in seen
                or existing.count(marker) != 1
                or bases.get(target_id) != marker.get("source_basis_digest")
                or key not in values
                or not valid_numeric_authorization(
                    marker, character_slug=definition.character_slug,
                    target_kind="resource", target_id=target_id, metric="owner_reset",
                    raw_value=values[key],
                    owner_digest=numeric_target_owner_digest(
                        definition, state, "resource", target_id, "owner_reset",
                    ), verified_actions=(marker,),
                )):
            raise ValueError("Page feature resource witness changed.")
        seen.add(target_id)
        actions.append({"authorization": marker,
                        "source_basis_digest": marker["source_basis_digest"]})
    from .character_source_repair import load_verified_numeric_actions
    trusted = (*load_verified_numeric_actions(definition.campaign_slug,
                                              definition.character_slug), *actions)
    fields, resources = _numeric_statuses(definition, state, trusted, bases,
                                          authority.source_snapshot_digest)
    return replace(authority, field_statuses=fields, resource_statuses=resources,
                   verified_numeric_actions=tuple(_numeric_witness_identity(row) for row in trusted))


def _numeric_statuses(
    definition: CharacterDefinition, state: dict[str, Any],
    verified_actions: tuple[Any, ...],
    resource_basis_digests: dict[str, str] | None = None,
    source_snapshot_digest: str = "",
) -> tuple[tuple[EffectiveStatus, ...], tuple[EffectiveStatus, ...]]:
    """Classify legacy numeric owners before any normalizer uses saved totals.

    The old definition has no independent field/resource audit witness. Even a
    `native_creation` provenance string is copyable through raw PUT, so it does
    not authenticate a base or an inverse of a previously applied effect.
    """
    stats = dict(definition.stats or {})
    abilities = dict(stats.get("ability_scores") or {})
    markers = list(dict(definition.source or {}).get("source_authorizations") or [])
    target_values = numeric_target_values(definition, state)
    resource_bases = resource_basis_digests or {}
    owner_payload = None
    owner_inputs_checked = False
    native_owner_inputs = (
        type(definition) is CharacterDefinition
        and vars(CharacterDefinition).get("to_dict") is _NATIVE_CHARACTER_TO_DICT
        and type(definition.system) is str and is_dnd_5e_system(definition.system)
        and type(state) is dict
        and type(source_snapshot_digest) is str
    )

    def owner_digest(kind, path, metric):
        nonlocal owner_payload, owner_inputs_checked
        if native_owner_inputs and (kind, path, metric) in target_values:
            if not owner_inputs_checked:
                owner_inputs_checked = True
                payload = definition.to_dict()
                if _plain_preparation_data((payload, state, resource_bases)):
                    if _plain_numeric_witness_data(verified_actions):
                        owner_payload = payload
            if owner_payload is not None:
                return _numeric_owner_digest_from_inputs(
                    target_values, owner_payload, kind, path, metric,
                )
        return numeric_target_owner_digest(definition, state, kind, path, metric)

    def decide(path: str, kind: str, metric: str, raw: Any, reason: str) -> EffectiveStatus:
        matches = [record for record in markers if isinstance(record, dict)
                   and record.get("target_kind") == kind
                   and record.get("target_id") == path
                   and record.get("metric") == metric]
        if len(matches) > 1:
            return EffectiveStatus(path, CONFLICT, deepcopy(raw), None,
                                   "authorization_conflict")
        if len(matches) == 1 and kind == "field" and metric == "final" and (
                path in NATIVE_BASELINE_FIELDS or path == "stats.max_hp" and isinstance(
                    dict(definition.source.get("native_progression") or {}).get("hp_recipe"), dict)):
            from .character_source_repair import NativeAggregateWitness
            automatic = [witness for witness in verified_actions
                         if isinstance(witness, NativeAggregateWitness)
                         and witness.get("authorization") == matches[0]]
            if len(automatic) > 1:
                return EffectiveStatus(path, CONFLICT, deepcopy(raw), None, "native_aggregate_origin_conflict")
            if len(automatic) == 1 and valid_numeric_authorization(
                    matches[0], character_slug=definition.character_slug,
                    target_kind=kind, target_id=path, metric=metric,
                    raw_value=target_values.get((kind, path, metric)),
                    owner_digest=owner_digest(kind, path, metric),
                    verified_actions=(matches[0],)):
                history = hashlib.sha256(json.dumps({"classes": definition.profile.get("classes"),
                    "native_progression": dict(definition.source or {}).get("native_progression")},
                    sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
                if automatic[0].origin[-1] != history:
                    return EffectiveStatus(path, UNKNOWN, deepcopy(raw), None, "native_aggregate_history_unproven")
                return EffectiveStatus(path, UNKNOWN, deepcopy(raw), None, "native_aggregate_recipe_pending")
        trusted_witnesses = verified_actions
        if (len(matches) == 1 and (kind == "resource" or (kind == "field" and path == "stats.max_hp")
                                  or native_baseline_target(kind, path, metric)
                                  or (matches[0].get("provenance") in {"native_level_up", "native_reconstruction", "native_requalification"}
                                      and native_advancement_input_target(kind, path, metric)))
                and matches[0].get("provenance") in {"native_level_up", "native_creation", "page_feature_update", "native_reconstruction", "native_requalification", "native_elective_decision", "native_external_proficiency"}):
            basis = resource_bases.get(path)
            trusted_witnesses = tuple(
                witness.get("authorization") for witness in verified_actions
                if isinstance(witness, dict) and witness.get("source_basis_digest") == basis
                and basis is not None
                and _transition_matches(witness, kind, path, metric,
                                        target_values.get((kind, path, metric)),
                                        owner_digest(kind, path, metric),
                                        source_snapshot_digest)
                and (matches[0].get("provenance") != "page_feature_update"
                     or matches[0].get("source_basis_digest") == basis
                     or witness.get("transition_proof") is not None)
            )
            if matches[0].get("provenance") == "page_feature_update":
                owners = [row for row in definition.features if isinstance(row, dict)
                          and _text(row.get("tracker_ref")) == path.removeprefix("resource:")]
                if (len(owners) != 1
                        or _text(owners[0].get("id")) != matches[0].get("feature_id")
                        or _text(owners[0].get("page_ref")) != matches[0].get("page_ref")):
                    trusted_witnesses = ()
        if len(matches) == 1 and (kind, path, metric) in target_values and valid_numeric_authorization(
            matches[0], character_slug=definition.character_slug,
            target_kind=kind, target_id=path, metric=metric,
            raw_value=target_values.get((kind, path, metric)),
            owner_digest=owner_digest(kind, path, metric),
            verified_actions=trusted_witnesses,
        ):
            status = MANUAL if matches[0]["provenance"] == "manager" else VERIFIED
            return EffectiveStatus(path, status, deepcopy(raw),
                                   deepcopy(raw) if metric != "base" else None,
                                   "baseline_authorized" if metric == "base" else "")
        return EffectiveStatus(path, UNKNOWN, deepcopy(raw), None, reason)

    fields: list[EffectiveStatus] = []
    for key, label in (("str", "strength"), ("dex", "dexterity"),
                       ("con", "constitution"), ("int", "intelligence"),
                       ("wis", "wisdom"), ("cha", "charisma")):
        payload = dict(abilities.get(key) or abilities.get(label) or {})
        for metric in ("score", "modifier", "save_bonus"):
            path = f"stats.ability_scores.{key}.{metric}"
            if metric == "score" and isinstance(target_values.get(("field", path, "base")), dict):
                base_status = decide(path, "field", "base", payload.get(metric),
                                     "ability_baseline_owner_unproven")
                if base_status.status in {VERIFIED, MANUAL, CONFLICT}:
                    fields.append(base_status)
                    continue
            fields.append(decide(path, "field", "final", payload.get(metric),
                                 "ability_baseline_owner_unproven"))
    for key in ("proficiency_bonus", "max_hp", "armor_class", "initiative_bonus",
                "speed", "passive_perception", "passive_insight",
                "passive_investigation", "carrying_capacity", "push_drag_lift"):
        path = f"stats.{key}"
        fields.append(decide(path, "field", "final", stats.get(key),
                             "aggregate_owner_unproven"))
    skill_counts: dict[str, int] = {}
    for row in list(definition.skills or []):
        if isinstance(row, dict) and _text(row.get("name")):
            key = _text(row["name"]).casefold()
            skill_counts[key] = skill_counts.get(key, 0) + 1
    for row in list(definition.skills or []):
        if not isinstance(row, dict):
            continue
        name = _text(row.get("name")).casefold()
        if name:
            path = f"skills.{name}"
            fields.append(
                EffectiveStatus(path, CONFLICT, deepcopy(row), None, "skill_identity_conflict")
                if skill_counts[name] > 1 else
                decide(path, "proficiency", "grant", row, "skill_grant_owner_unproven")
            )
    for kind, values in dict(definition.proficiencies or {}).items():
        for value in list(values or []):
            label = _text(value).casefold()
            if label:
                path = f"proficiencies.{kind}.{label}"
                fields.append(decide(path, "proficiency", "grant", value,
                                     "proficiency_owner_unproven"))

    resources: list[EffectiveStatus] = []
    seen: set[str] = set()
    for template in list(definition.resource_templates or []):
        if not isinstance(template, dict):
            continue
        stable_id = _text(template.get("id"))
        path = f"resource:{stable_id}"
        status = CONFLICT if not stable_id or path in seen else UNKNOWN
        seen.add(path)
        resources.append(EffectiveStatus(path, CONFLICT, deepcopy(template), None,
                                         "resource_identity_conflict") if status == CONFLICT
                         else decide(path, "resource", "owner_reset", template,
                                     "resource_owner_unproven"))
    for slot in _observed_list(state.get("spell_slots")):
        if not isinstance(slot, dict):
            continue
        lane = _text(slot.get("slot_lane_id"))
        level = slot.get("level")
        stable_id = f"{lane}:{level}" if type(level) is int and level > 0 else ""
        path = f"spell_slot:{stable_id}"
        status = CONFLICT if not stable_id or path in seen else UNKNOWN
        seen.add(path)
        resources.append(EffectiveStatus(path, CONFLICT, deepcopy(slot), None,
                                         "spell_slot_identity_conflict") if status == CONFLICT
                         else decide(path, "resource", "owner_reset", slot,
                                     "spell_slot_owner_unproven"))
    for pool in _observed_pools(state):
        if not isinstance(pool, dict):
            continue
        faces = pool.get("faces")
        stable_id = str(faces) if type(faces) is int and faces > 0 else ""
        path = f"hit_die:{stable_id}"
        status = CONFLICT if not stable_id or path in seen else UNKNOWN
        seen.add(path)
        resources.append(EffectiveStatus(path, CONFLICT, deepcopy(pool), None,
                                         "hit_die_identity_conflict") if status == CONFLICT
                         else decide(path, "resource", "owner_reset", pool,
                                     "hit_die_owner_unproven"))
    inventory_ids = [_text(item.get("id")) for item in _observed_list(state.get("inventory"))
                     if isinstance(item, dict)]
    for item in _observed_list(state.get("inventory")):
        if not isinstance(item, dict) or (item.get("charges_current") is None
                                          and item.get("charges_max") is None):
            continue
        stable_id = _text(item.get("id"))
        path = f"item_charge:{stable_id}"
        resources.append(EffectiveStatus(
            path, UNKNOWN if stable_id and inventory_ids.count(stable_id) == 1 else CONFLICT,
            {"current": item.get("charges_current"), "max": item.get("charges_max")},
            None, "item_charge_owner_unproven" if stable_id and inventory_ids.count(stable_id) == 1
            else "item_charge_identity_conflict",
        ))
    return tuple(fields), tuple(resources)


def _transition_matches(witness: dict[str, Any], kind: str, target_id: str,
                        metric: str, raw_value: Any, owner_digest: str,
                        source_snapshot_digest: str) -> bool:
    proof = witness.get("transition_proof")
    if proof is None:
        return True
    if not isinstance(proof, dict):
        return False
    return (proof.get("schema_version") in {1, 2}
            and (proof.get("target_kind"), proof.get("target_id"), proof.get("metric"))
                == (kind, target_id, metric)
            and proof.get("authorization") == witness.get("authorization")
            and proof.get("new_basis") == witness.get("source_basis_digest")
            and proof.get("new_snapshot") == source_snapshot_digest
            and proof.get("value_digest") == numeric_value_digest(raw_value)
            and proof.get("owner_digest") == owner_digest)

def build_source_authority(
    *, definition: CharacterDefinition, state: dict[str, Any],
    systems_service: Any, campaign_page_records: list[Any] | None,
    verified_manual_actions: tuple[Any, ...] = (),
    verified_numeric_actions: tuple[Any, ...] = (),
    state_revision: int | None = None,
    prospective_spell_checkpoint: Any | None = None,
) -> SourceAuthority:
    """Classify the exact current links in a previously reconciled definition."""
    from .character_source_reads import BuilderPhaseReader, phase_of, SourceReadConflict
    if isinstance(systems_service, BuilderPhaseReader):
        raise SourceReadConflict("A builder cache adapter cannot issue source authority.")
    phase = phase_of(systems_service)
    if phase is not None:
        if (definition.campaign_slug, definition.character_slug) != (
                phase.owner.campaign_slug, phase.owner.character_slug):
            raise SourceReadConflict("Source authority model differs from its phase owner.")
        phase.bind_pages(campaign_page_records, sections={"Mechanics", "Items", "Spells"})
    if not is_dnd_5e_system(definition.system):
        raise ValueError("SourceAuthority applies only to DND-5E projections")
    payload = definition.to_dict()
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    pages = _eligible_page_records(campaign_page_records)
    revision_loader = getattr(systems_service, "get_builder_static_revision_for_character_read", None)
    if not callable(revision_loader):
        revision_loader = getattr(systems_service, "get_builder_static_revision", None)
    systems_revision = (
        revision_loader(definition.campaign_slug, entry_types=(
            "class", "classfeature", "feat", "feature", "item", "optionalfeature",
            "spell", "subclassfeature",
        )) if callable(revision_loader) else None
    )
    page_snapshot = [
        {
            "ref": ref,
            "section": _field(_field(record, "page"), "section"),
            "published": _field(_field(record, "page"), "published"),
            "reveal_after_session": _field(_field(record, "page"), "reveal_after_session"),
            "updated_at": _text(_field(record, "updated_at")),
            "committed_revision": _field(_field(record, "page"), "committed_revision"),
            "metadata": _field(record, "metadata"),
        }
        for ref, records in pages.items() for record in records
    ]
    if any(not row["updated_at"] for row in page_snapshot):
        raise ValueError("Campaign page source revision is unavailable")
    source_snapshot_digest = hashlib.sha256(_canonical({
        "systems_revision": systems_revision,
        "pages": sorted(page_snapshot, key=lambda row: (row["ref"], _canonical(row))),
    }).encode("utf-8")).hexdigest()
    grants: list[AuthorityGrant] = []
    statuses: list[AuthorityStatus] = []
    warnings: list[tuple[str, str]] = []
    verified_class_rows: set[str] = set()
    active_item_ids: set[str] = set()
    spell_property_clear_owners = set()
    inert_page_companions: set[str] = set()
    current_feature_payloads: dict[str, Any] = {}
    from .character_feature_history import declared_ids as historical_feature_ids
    history_ids = historical_feature_ids(definition, verified_numeric_actions)
    from .character_parent_facets import qualified_mappings, linked_companion_facet
    parent_facets = qualified_mappings(definition, systems_service, verified_numeric_actions)
    from .character_armor_models import qualified as qualified_armor, MODEL, PATH, ELECTIVE_CHILDREN, GUARDIAN_MEMBERS
    armor_choices = qualified_armor(definition, systems_service, verified_numeric_actions)
    armor_branches = {MODEL: list(PATH)} if armor_choices else {}
    from .character_tracker_associations import qualified as qualified_trackers
    try:
        tracker_bindings = qualified_trackers(definition, verified_numeric_actions)
    except (ValueError, TypeError, KeyError):
        tracker_bindings = ()
    armor_summaries = {row["summary_id"] for row in armor_choices if row["summary_id"]}
    companion_claims = {}
    for feature in definition.features:
        if isinstance(feature, dict):
            ref = feature.get("systems_ref")
            if isinstance(ref, dict) and ref.get("entry_type") in {"background", "race", "subrace"}:
                key = (ref.get("entry_key"), feature.get("name"))
                companion_claims[key] = companion_claims.get(key, 0) + 1
    from .character_equipment_activation import analyze_activation
    activation_analysis = analyze_activation(definition, state)
    exact_activation_indices = {row["index"] for row in activation_analysis["rows"]
        if row["source"] == "sqlite" and row["status"] == "exact"}
    current_activation_rows = {row["id"]: row["state"] for row in activation_analysis["rows"]
        if row["source"] == "sqlite" and row["status"] == "exact"}
    for index, class_row in enumerate(profile_class_rows(definition.profile), start=1):
        row_id = _text(class_row.get("row_id")) or f"class-row-{index}"
        source_kind, source_key = _source_identity(class_row)
        current, reason = _current_payload(
            campaign_slug=definition.campaign_slug, kind="class",
            source_kind=source_kind, source_key=source_key,
            systems_service=systems_service, pages=pages,
            expected_slug=_text(dict(class_row.get("systems_ref") or {}).get("slug")),
        )
        if current is not None and not reason:
            verified_class_rows.add(row_id)
        else:
            statuses.append(AuthorityStatus("class_row", row_id, NEEDS_REPAIR, reason))
    attained_reconstruction_keys = None
    attained_feature_owners = {}
    if isinstance(definition.source.get("native_reconstruction_choices"), dict):
        from .character_reconstruction_authority import attained_reconstruction_feature_owners
        attained_feature_owners = attained_reconstruction_feature_owners(definition, systems_service,
            armor_selectors=armor_branches)
        attained_reconstruction_keys = frozenset(attained_feature_owners)
    for kind, rows in (("feature", definition.features), ("item", definition.equipment_catalog)):
        seen_instances: set[str] = set()
        for index, raw in enumerate(list(rows or []), start=1):
            if not isinstance(raw, dict):
                continue
            instance_id = _text(raw.get("id"))
            if not instance_id or instance_id in seen_instances:
                statuses.append(AuthorityStatus(kind, instance_id or f"index:{index}", NEEDS_ATTENTION, "instance identity ambiguous"))
                continue
            seen_instances.add(instance_id)
            source_kind, source_key = _source_identity(raw)
            if kind == "item" and source_kind == "page":
                source_kind, source_key = "", ""
            current, reason = _current_payload(
                campaign_slug=definition.campaign_slug, kind=kind,
                source_kind=source_kind, source_key=source_key,
                systems_service=systems_service, pages=pages,
                expected_slug=_text(dict(raw.get("systems_ref") or {}).get("slug")),
                expected_ref=dict(raw.get("systems_ref") or {}) if kind == "item" else None,
                expected_feature=raw if kind == "feature" else None,
                expected_profile=definition.profile,
            )
            if kind == "feature" and instance_id in parent_facets:
                current, reason = {}, ""
            if kind == "feature" and instance_id in armor_summaries:
                current, reason = {}, ""
            if (kind == "feature" and dict(raw.get("systems_ref") or {}).get("entry_key") in ELECTIVE_CHILDREN
                    and instance_id not in armor_summaries
                    and (not armor_choices or dict(raw.get("systems_ref") or {}).get("entry_key")
                         not in GUARDIAN_MEMBERS
                         or raw.get("class_row_id") not in (None, "", armor_choices[0]["class_row_id"]))):
                current, reason = None, "Armor Model selection has no authenticated current owner"
            if kind == "feature" and isinstance(raw.get("systems_ref"), dict):
                ref = raw["systems_ref"]
                if ref.get("entry_type") in {"background", "race", "subrace"}:
                    entry = _current_systems_entry(definition.campaign_slug, "systems", ref.get("entry_key"), systems_service)
                    if (entry is not None and linked_companion_facet(raw, definition.profile, entry) is not None
                            and companion_claims.get((ref.get("entry_key"), raw.get("name"))) == 1):
                        current, reason = {}, ""
                    else:
                        current, reason = None, "selected parent facet is unavailable, conflicting or ambiguous"
            if current is not None and kind == "item" and "item_capabilities" in current:
                from .character_item_capabilities import normalize_item_capabilities, validate_capability_spell_support
                try:
                    current["item_capabilities"] = normalize_item_capabilities(current["item_capabilities"])
                    validate_capability_spell_support(current["item_capabilities"], current.get("spell_support", []))
                    from .character_item_capabilities import validate_capability_source
                    validate_capability_source(current["item_capabilities"], current)
                    if current["item_capabilities"].get("schema_version") == 2:
                        from .character_item_casting import validate_mode_sources
                        validate_mode_sources(current["item_capabilities"], current.get("spell_support", []),
                            definition.campaign_slug, systems_service)
                    casting = current["item_capabilities"].get("casting")
                    if casting is not None:
                        exact_spell = _current_systems_entry(definition.campaign_slug, "systems", casting["spell_entry_key"], systems_service)
                        from .item_spell_support import parse_item_spell_support
                        from .character_builder_spells import _resolve_item_spell_selector
                        records = parse_item_spell_support(current.get("spell_support", []), strict=True).records
                        enabled = getattr(systems_service, "list_enabled_entries_for_campaign", None)
                        resolved = _resolve_item_spell_selector(records[0].spell_selector, {"entries":
                            enabled(definition.campaign_slug, entry_type="spell") if callable(enabled) else []})
                        if (exact_spell is None or exact_spell.entry_type != "spell" or resolved is None
                                or resolved.entry_key != casting["spell_entry_key"]):
                            raise ValueError("The exact item casting publication is unavailable.")
                except (TypeError, ValueError):
                    current, reason = None, "item capability source/usage contract needs repair"
            if current is not None and kind == "item":
                from .character_reconstruction_items import current_mapping_matches
                if not current_mapping_matches(definition, raw, systems_service, campaign_page_records):
                    current, reason = None, "authenticated physical item/page relation changed"
            if (current is not None and kind == "feature" and attained_reconstruction_keys is not None
                    and dict(raw.get("systems_ref") or {}).get("entry_type") in {"classfeature", "subclassfeature"}
                    and instance_id not in armor_summaries
                    and dict(raw.get("systems_ref") or {}).get("entry_key") not in attained_reconstruction_keys):
                current, reason = None, "retained class feature is not proved attained by the current class/subclass owner"
            if kind == "feature":
                if instance_id in history_ids:
                    # Even stale or malformed historical intent cannot re-enable
                    # a mechanical owner. Qualification is a final status-only pass.
                    current, reason = None, "historical association requires current owner and custody"
                current_feature_payloads[instance_id] = deepcopy(current) if current is not None and not reason else None
            physical_activation = current_activation_rows.get(instance_id, {}) if kind == "item" else {}
            active = kind != "item" or (physical_activation.get("is_equipped") is True
                                       and not raw.get("mechanics_suppressed"))
            if current is not None and kind == "item":
                from .character_builder_equipment import _metadata_requires_attunement
                if (_metadata_requires_attunement(current.get("attunement"))
                        or current.get("requires_attunement") is True) and physical_activation.get("is_attuned") is not True:
                    active = False
            if current is None or reason:
                statuses.append(AuthorityStatus(kind, instance_id, NEEDS_REPAIR, reason or "source unavailable"))
                warnings.append(("source_needs_repair", f"{kind.title()} {instance_id} needs source repair."))
                continue
            statuses.append(AuthorityStatus(kind, instance_id, VERIFIED, ""))
            if (kind == "item" and "spell_property_modifiers" in current
                    and type(current.get("spell_support")) is list and not current["spell_support"]):
                # Current source fact before activation filtering. This is
                # non-entitling clear intent, never a stored Character flag.
                spell_property_clear_owners.add(instance_id)
            page_matches = (pages.get(source_key) or []) if source_kind == "page" else []
            page = _field(page_matches[0], "page") if len(page_matches) == 1 else None
            committed_revision = _field(page, "committed_revision")
            if (kind == "feature" and is_page_choice_shape(raw)
                    and not raw.get("campaign_option")
                    and type(committed_revision) is int and committed_revision > 0):
                # The committed page proves the choice, but an omitted saved
                # option is not permission to acquire its mechanics on read.
                inert_page_companions.add(instance_id)
                continue
            capability_casting_active = False
            if kind == "item" and "item_capabilities" in current:
                casting = current["item_capabilities"].get("casting")
                matching = [row for index, row in enumerate(_observed_list(state.get("inventory")))
                    if index in exact_activation_indices and isinstance(row, dict)
                    and (row.get("catalog_ref") or row.get("id")) == instance_id]
                capability_casting_active = bool(casting is not None and len(matching) == 1
                    and type(matching[0].get("quantity")) is int and matching[0]["quantity"] == 1
                    and matching[0].get("is_attuned") is True and not raw.get("mechanics_suppressed")
                    and (casting["activation"] == "attuned" or matching[0].get("is_equipped") is True))
            if not active and (kind != "item" or not ({"spell_property_modifiers", "item_capabilities"} & current.keys())):
                continue
            if kind == "item" and active:
                active_item_ids.add(instance_id)
            relevant = (_ITEM_EFFECT_FIELDS if active else frozenset({"spell_property_modifiers", "item_capabilities"})
                | (frozenset({"spell_support"}) if capability_casting_active else frozenset())) if kind == "item" else _FEATURE_EFFECT_FIELDS
            if kind == "item" and (current.get("item_capabilities") or {}).get("casting") is not None and not capability_casting_active:
                relevant = relevant - {"spell_support"}
            for field in sorted(relevant & current.keys()):
                value = current[field]
                if value in (None, "", [], {}):
                    continue
                effects = list(value) if isinstance(value, list) else [value]
                for effect_index, effect in enumerate(effects):
                    effect_id = _text(effect.get("effect_id")) if isinstance(effect, dict) else ""
                    effect_id = f"{field}:{effect_id or effect_index}"
                    grants.append(AuthorityGrant(kind, instance_id, source_kind, source_key, effect_id, _canonical({field: effect})))
    from .character_feature_composition import resolve_feature_composition
    composition = resolve_feature_composition(definition, systems_service,
        current_payloads=current_feature_payloads, feature_statuses=tuple(statuses),
        verified_class_rows=frozenset(verified_class_rows))
    disabled = composition.replaced_ids | composition.withheld_ids | composition.unresolved_ids
    grants = [grant for grant in grants if grant.kind != "feature" or grant.instance_id not in disabled]
    composed_statuses = []
    for status in statuses:
        if status.kind == "feature" and status.status == VERIFIED:
            if status.instance_id in composition.replaced_ids:
                status = replace(status, status=REPLACED, reason="replaced_by_current_qualified_source")
            elif status.instance_id in composition.withheld_ids | composition.unresolved_ids:
                status = replace(status, status=NEEDS_REPAIR, reason="replacement_source_or_owner_unproven")
        composed_statuses.append(status)
    statuses = composed_statuses
    if composition.withheld_ids or composition.unresolved_ids:
        warnings.append(("replacement_source_needs_repair", "A retained feature replacement needs current source and owner repair."))
    spell_counts: dict[str, int] = {}
    current_spell_keys: set[tuple[str, str]] = set()
    spell_property_bases = []
    spell_key_candidates: set[tuple[str, str, str]] = set()
    for raw in list(dict(definition.spellcasting or {}).get("spells") or []):
        if isinstance(raw, dict) and _text(raw.get("id")):
            spell_id = _text(raw["id"])
            spell_counts[spell_id] = spell_counts.get(spell_id, 0) + 1
    for raw in list(dict(definition.spellcasting or {}).get("spells") or []):
        if not isinstance(raw, dict):
            continue
        spell_id = _text(raw.get("id"))
        if not spell_id:
            continue
        if spell_counts[spell_id] != 1:
            statuses.append(AuthorityStatus("spell", spell_id, NEEDS_ATTENTION, "spell identity ambiguous"))
            continue
        source_kind, source_key = _source_identity(raw)
        current, reason = _current_payload(
            campaign_slug=definition.campaign_slug, kind="spell",
            source_kind=source_kind, source_key=source_key,
            systems_service=systems_service, pages=pages,
            expected_slug=_text(dict(raw.get("systems_ref") or {}).get("slug")),
        )
        if current is not None and not reason:
            if source_kind.startswith("systems"):
                entry = _current_systems_entry(definition.campaign_slug, source_kind, source_key,
                                               systems_service)
                names = (getattr(entry, "slug", ""), getattr(entry, "title", "")) if entry is not None else ()
                if entry is not None:
                    from .character_builder_spells import _build_spell_payload
                    display = _build_spell_payload(entry.title, entry)
                    spell_property_bases.append((spell_id, _canonical({
                        "spell_ref": {"entry_key": entry.entry_key, "entry_type": "spell", "source_id": entry.source_id},
                        "range": display["range"], "casting_time": display["casting_time"]})))
                owner = (f"systems:{_text(getattr(entry, 'entry_key', '')) or _text(getattr(entry, 'slug', ''))}"
                         if entry is not None else "")
            else:
                matches = pages.get(source_key) or []
                page = _field(matches[0], "page") if len(matches) == 1 else None
                names = (source_key, _field(page, "title")) if page is not None else ()
                owner = f"page:{source_key}"
            spell_key_candidates.update((spell_id, _text(name).casefold(), owner)
                                        for name in names if _text(name) and owner)
            if owner and source_kind.startswith("systems"):
                current_spell_keys.add((spell_id, owner))
        statuses.append(AuthorityStatus("spell", spell_id, VERIFIED if current is not None and not reason else NEEDS_REPAIR,
                                        reason or ""))
    by_id: dict[tuple[str, str, str, str, str], AuthorityGrant] = {}
    disputed: set[tuple[str, str, str, str, str]] = set()
    for grant in grants:
        prior = by_id.get(grant.grant_id)
        if prior is not None and prior.payload_json != grant.payload_json:
            disputed.add(grant.grant_id)
        else:
            by_id[grant.grant_id] = grant
    for grant_id in disputed:
        warnings.append(("source_collision", "Conflicting current source effects need manager attention."))
        statuses.append(AuthorityStatus(grant_id[0], grant_id[3], NEEDS_ATTENTION, "conflicting current effect"))
    clean_grants = tuple(grant for grant_id, grant in by_id.items() if grant_id not in disputed)
    list_spells = getattr(systems_service, "list_enabled_entries_for_campaign", None)
    entries = (read_enabled_spell_entries(systems_service, definition.campaign_slug)
               if callable(list_spells) else None)
    if entries is None:
        entries = list_spells(definition.campaign_slug, entry_type="spell") if callable(list_spells) else []
    verified_spell_grants = _current_spell_grant_membership(clean_grants, definition, entries)
    # Grant values may be display names. Resolve them against the current
    # catalog and reject a title/slug alias shared by two eligible spells.
    current_spell_keys.update(_unambiguous_current_spell_keys(spell_key_candidates, entries, pages))
    source_owners: dict[str, set[tuple[str, str, str]]] = {}
    item_source_ids: set[str] = set()
    for grant in clean_grants:
        payload = json.loads(grant.payload_json)
        row_ids = _source_row_ids(payload)
        if grant.kind == "item" and isinstance(payload.get("spell_support"), dict):
            from .item_spell_support import parse_item_spell_support
            parsed = parse_item_spell_support([payload["spell_support"]])
            row_ids.update(record.source_row_id for record in parsed.records if record.source_row_id)
            row_ids.update(source_id for _, source_id, _, _ in parsed.source_declarations if source_id)
        for row_id in row_ids:
            source_owners.setdefault(row_id, set()).add((grant.kind, grant.source_key, grant.instance_id))
            if grant.kind == "item":
                item_source_ids.add(row_id)
    # Physical copies may share a current exact Systems source and its spell
    # row. A distinct source, including a non-item owner, still disputes it.
    disputed_rows = frozenset(
        row_id for row_id, owners in source_owners.items()
        if len(owners) > 1 and not (
            all(kind == "item" for kind, _, _ in owners)
            and len({source_key for _, source_key, _ in owners}) == 1
        )
    )
    for row_id in disputed_rows:
        statuses.append(AuthorityStatus("source_row", row_id, NEEDS_ATTENTION, "conflicting current owners"))
        warnings.append(("source_row_collision", "Conflicting spell source rows need manager attention."))
    verified_item_spell_rows = {row_id for row_id, _ in verified_spell_grants}
    verified_source_rows = frozenset(
        source_owners.keys() - disputed_rows - (item_source_ids - verified_item_spell_rows)
    )
    witnesses = tuple(_canonical(witness) for witness in verified_manual_actions if isinstance(witness, dict))
    native_bases = _native_baseline_bases(
        definition, state, systems_service=systems_service, statuses=statuses,
        verified_class_rows=verified_class_rows, source_snapshot_digest=source_snapshot_digest,
        pages=pages, feature_composition=composition,
    )
    current_inputs = None
    if isinstance(definition.source.get("native_reconstruction_choices"), dict):
        from .character_reconstruction_authority import reconstructed_input_bases
        from .character_current_inputs import current_input_compilation
        current_inputs = current_input_compilation(definition=definition, state=state,
            state_revision=state_revision, statuses=statuses, manual_actions=verified_manual_actions,
            numeric_actions=verified_numeric_actions, source_snapshot_digest=source_snapshot_digest,
            systems_service=systems_service, prospective_checkpoint=prospective_spell_checkpoint)
        for ability in ("str", "dex", "con", "int", "wis", "cha"):
            native_bases.pop(f"stats.ability_scores.{ability}.score", None)
        for key in tuple(native_bases):
            if key.startswith(("skills.", "proficiencies.")):
                native_bases.pop(key)
        if current_inputs is None:
            native_bases.update(reconstructed_input_bases(definition, systems_service=systems_service,
                statuses=statuses, elective_witnesses=verified_numeric_actions))
        else:
            native_bases.update(reconstructed_input_bases(definition, systems_service=systems_service,
                statuses=statuses, elective_witnesses=verified_numeric_actions, _current_inputs=current_inputs))
    from .character_external_proficiencies import source_bases as external_proficiency_bases
    try:
        native_bases.update(external_proficiency_bases(definition, verified_numeric_actions))
    except ValueError:
        warnings.append(("external_proficiency_unconfirmed", "An acquired proficiency needs manager review."))
    preliminary_fields, _ = _numeric_statuses(
        definition, state, verified_numeric_actions, native_bases, source_snapshot_digest,
    )
    resource_bases = _source_derived_resource_bases(
        definition, systems_service=systems_service, pages=pages,
        verified_class_rows=frozenset(verified_class_rows),
        feature_statuses=tuple(statuses), field_statuses=preliminary_fields,
        feature_composition=composition, armor_selectors=armor_branches, tracker_bindings=tracker_bindings,
    )
    resource_bases.update(_page_feature_resource_bases(
        definition, pages=pages, feature_statuses=tuple(statuses),
        source_snapshot_digest=source_snapshot_digest,
    ))
    hp_args = dict(systems_service=systems_service, pages=pages,
        verified_class_rows=frozenset(verified_class_rows), feature_statuses=tuple(statuses))
    if current_inputs is not None and current_inputs.reuse_hp:
        hp_args["_current_inputs"] = current_inputs
    hp_basis = _source_derived_hp_basis(definition, **hp_args)
    if hp_basis is not None:
        resource_bases["stats.max_hp"] = hp_basis
    resource_bases.update(_source_derived_formula_bases(
        definition, systems_service=systems_service,
        verified_class_rows=frozenset(verified_class_rows),
        verified_source_rows=verified_source_rows, grants=clean_grants,
        source_snapshot_digest=source_snapshot_digest,
    ))
    reconstruction_roles = _spell_reconstruction_roles(definition, verified_numeric_actions, prospective_spell_checkpoint)
    choice_frames = _source_derived_spell_choice_frames(
        definition, systems_service=systems_service, pages=pages,
        verified_class_rows=frozenset(verified_class_rows),
        source_snapshot_digest=source_snapshot_digest,
        spellbook_ids=_spellbook_basis_ids(definition, verified_numeric_actions, prospective_spell_checkpoint),
    )
    resource_bases.update({target: numeric_value_digest(frame)
                           for target, frame in choice_frames.items()})
    resource_bases.update(native_bases)
    field_statuses, resource_statuses = _numeric_statuses(
        definition, state, verified_numeric_actions, resource_bases,
        source_snapshot_digest,
    )
    class_rows = profile_class_rows(definition.profile)
    class_ids = [_text(row.get("row_id")) for row in class_rows]
    pb_derivation_valid = (class_ids and all(class_ids) and len(class_ids) == len(set(class_ids))
            and set(class_ids) == verified_class_rows
            and all(type(row.get("level")) is int and row["level"] > 0 for row in class_rows))
    if pb_derivation_valid:
        total_level = sum(row["level"] for row in class_rows)
        expected_pb = 2 + (total_level - 1) // 4
        if dict(definition.stats or {}).get("proficiency_bonus") == expected_pb:
            field_statuses = tuple(
                EffectiveStatus(row.path, VERIFIED, row.raw, expected_pb,
                                "derived_from_current_class_level")
                if row.path == "stats.proficiency_bonus" and row.status != CONFLICT else row
                for row in field_statuses
            )
        else:
            pb_derivation_valid = False
    if not pb_derivation_valid:
        field_statuses = tuple(
            EffectiveStatus(row.path, UNKNOWN, row.raw, None,
                            "proficiency_formula_owner_unproven")
            if row.path == "stats.proficiency_bonus" and row.status not in {MANUAL, CONFLICT} else row
            for row in field_statuses
        )
    from .character_builder import (_extract_class_weapon_proficiencies,
                                    _extract_multiclass_gained_weapon_proficiencies)
    native_weapon_grants: set[str] = set()
    for index, class_row in enumerate(class_rows):
        row_id = _text(class_row.get("row_id"))
        if row_id not in verified_class_rows:
            continue
        source_kind, source_key = _source_identity(class_row)
        entry = _current_systems_entry(definition.campaign_slug, source_kind, source_key, systems_service)
        if entry is None or _text(getattr(entry, "entry_type", "")) != "class":
            continue
        values = (_extract_class_weapon_proficiencies(entry) if index == 0
                  else _extract_multiclass_gained_weapon_proficiencies(entry))
        native_weapon_grants.update(_text(value).casefold() for value in values if _text(value))
    if native_weapon_grants:
        field_statuses = tuple(
            EffectiveStatus(row.path, VERIFIED, row.raw, row.raw,
                            "derived_from_current_class_weapon_grant")
            if (row.path.startswith("proficiencies.weapons.")
                and row.path.removeprefix("proficiencies.weapons.") in native_weapon_grants
                and row.status == UNKNOWN) else row
            for row in field_statuses
        )
    from .character_builder import validated_background_instrument_names
    instrument_grants = {
        _text(name).casefold() for name in validated_background_instrument_names(
            definition, systems_service, strict=False,
        )
    } if systems_service is not None else set()
    if instrument_grants:
        field_statuses = tuple(
            EffectiveStatus(row.path, VERIFIED, row.raw, row.raw,
                            "derived_from_current_background_instrument_choice")
            if (row.path.startswith("proficiencies.tools.")
                and row.path.removeprefix("proficiencies.tools.") in instrument_grants
                and row.status == UNKNOWN) else row
            for row in field_statuses
        )
    formula_targets: set[str] = set()
    spell_choice_targets: set[str] = set()
    retired_choice_targets: set[str] = set()
    historical_active_targets: set[str] = set()
    marker_rows = list(dict(definition.source or {}).get("source_authorizations") or [])
    reconstruction_role_map = {identity: (role, level) for identity, role, level in reconstruction_roles}
    prepared_owners = _prepared_reconstruction_owners(definition, systems_service, frozenset(verified_class_rows)) if reconstruction_roles else set()
    values = numeric_target_values(definition, state)
    for (kind, target_id, metric), raw_value in values.items():
        if kind not in {"spell_metric", "spell_choice"}:
            continue
        from .character_spell_grants import native_class_choice_state
        from .character_source_repair import NativeSpellChoiceDecision
        decision_state = None
        if kind == "spell_choice":
            try:
                decision_state = native_class_choice_state(raw_value)
            except ValueError:
                continue
        decisions = tuple(witness for witness in verified_numeric_actions
            if type(witness) is NativeSpellChoiceDecision and witness.matches(raw_value)
            and witness.get("target_id") == target_id)
        pending_selected = bool(kind == "spell_choice" and prospective_spell_checkpoint is not None
            and prospective_spell_checkpoint.confirms_choice(raw_value))
        if decision_state is not None and not decisions and not pending_selected:
            continue
        matches = [marker for marker in marker_rows if isinstance(marker, dict)
                   and marker.get("target_kind") == kind
                   and marker.get("target_id") == target_id
                   and marker.get("metric") == metric]
        if len(matches) != 1:
            continue
        if decision_state is not None and not pending_selected and not any(w.matches(raw_value, matches[0]) for w in decisions):
            continue
        if kind == "spell_choice" and (pending_selected or ordinary_native_spell_choice_state(
                raw_value, matches[0], verified_numeric_actions=verified_numeric_actions) == "active"):
            historical = tuple(witness.get("authorization", witness) for witness in verified_numeric_actions
                if isinstance(witness, dict) and witness.get("authorization", witness) == matches[0])
            if valid_numeric_authorization(matches[0], character_slug=definition.character_slug,
                    target_kind=kind, target_id=target_id, metric=metric, raw_value=raw_value,
                    verified_actions=historical):
                historical_active_targets.add(target_id.removeprefix("spell_choice:"))
        if decision_state == "retired":
            # Retirement is an authenticated historical management decision,
            # not a benefit that current source drift can reactivate.
            historical = tuple(witness.get("authorization", witness) for witness in verified_numeric_actions
                if isinstance(witness, dict) and witness.get("authorization", witness) == matches[0])
            if valid_numeric_authorization(matches[0], character_slug=definition.character_slug,
                    target_kind=kind, target_id=target_id, metric=metric, raw_value=raw_value,
                    verified_actions=historical):
                retired_choice_targets.add(target_id.removeprefix("spell_choice:"))
            continue
        if target_id not in resource_bases:
            continue
        basis = resource_bases[target_id]
        trusted = tuple(witness.get("authorization") for witness in verified_numeric_actions
                        if isinstance(witness, dict) and witness.get("source_basis_digest") == basis
                        and _transition_matches(witness, kind, target_id, metric,
                            raw_value, numeric_target_owner_digest(
                                definition, state, kind, target_id, metric),
                            source_snapshot_digest))
        current_binding = valid_numeric_authorization(
            matches[0], character_slug=definition.character_slug,
            target_kind=kind, target_id=target_id, metric=metric,
            raw_value=raw_value, verified_actions=trusted,
        )
        if (not current_binding and kind == "spell_choice" and decision_state == "active"
                and _historical_choice_source_matches(definition, raw_value, matches[0],
                    decisions, verified_numeric_actions, choice_frames.get(target_id))):
            historical = tuple(w.get("authorization") for w in verified_numeric_actions
                if type(w) is dict and w.get("authorization") == matches[0]
                and "transition_proof" not in w)
            current_binding = valid_numeric_authorization(matches[0],
                character_slug=definition.character_slug, target_kind=kind,
                target_id=target_id, metric=metric, raw_value=raw_value,
                verified_actions=historical)
        if current_binding:
            if kind == "spell_metric":
                formula_targets.add(target_id)
            elif (not ("native_spell_grants" in definition.spellcasting or "native_acquisitions" in definition.source)
                    or pending_selected or ordinary_native_spell_choice_state(raw_value, matches[0],
                        verified_numeric_actions=verified_numeric_actions) == "active"):
                spell_choice_targets.add(target_id.removeprefix("spell_choice:"))
    for raw in definition.spellcasting.get("spells", []):
        if (isinstance(raw, dict) and raw.get("class_row_id") in prepared_owners
                and reconstruction_role_map.get(raw.get("id"), (None, None))[0] == "available"
                and f"spell_choice:{raw.get('id')}" in resource_bases):
            spell_choice_targets.add(raw["id"])
    all_managed_pools = _current_managed_pool_owners(
        definition, systems_service=systems_service, pages=pages,
        verified_class_rows=frozenset(verified_class_rows), feature_statuses=tuple(statuses),
        feature_composition=composition, armor_selectors=armor_branches, tracker_bindings=tracker_bindings,
    )
    managed_pools = {key: pool for key, pool in all_managed_pools.items()
                     if len(pool["members"]) > 1
                     or pool["members"][0]["feature"] != pool["members"][0]["canonical"]}
    from .character_spell_grants import (has_native_grants, qualify_native_grants,
        NativeGrantCustody, grant_model_digest)
    native_view, native_owners = None, ()
    if has_native_grants(definition):
        native_view = qualify_native_grants(definition, systems_service, custody=verified_numeric_actions)
        if any(isinstance(witness, NativeGrantCustody)
               and witness.get("native_grant_model_digest") == grant_model_digest(definition)
               for witness in verified_numeric_actions):
            native_owners = tuple(deepcopy(definition.source.get("native_acquisitions", {}).get("owners", [])))
    authority = SourceAuthority(digest, hashlib.sha256(_canonical(state).encode("utf-8")).hexdigest(),
                           state_revision, clean_grants, tuple(statuses), tuple(warnings), witnesses,
                           frozenset(verified_class_rows), verified_source_rows, disputed_rows,
                           field_statuses, resource_statuses,
                           tuple(_numeric_witness_identity(witness) for witness in verified_numeric_actions
                                 if isinstance(witness, dict)), frozenset(active_item_ids),
                           source_snapshot_digest, tuple(sorted(resource_bases.items())),
                           frozenset(formula_targets), verified_spell_grants,
                           frozenset(spell_choice_targets), frozenset(current_spell_keys),
                           frozenset(inert_page_companions), frozenset(
                               _text(row.get("id")) for row in definition.equipment_catalog
                               if isinstance(row, dict) and current_activation_rows.get(
                                   _text(row.get("id")), {}).get("is_equipped") is True),
                           _unqualified_native_aggregate_adjustments(dict(definition.stats or {})),
                           tuple(_canonical({**{key: row.get(key) for key in (
                               "id", "catalog_ref", "quantity", "is_equipped", "is_attuned", "weapon_wield_mode", "charges_current", "charges_max")},
                               "activation_current": index in exact_activation_indices})
                               if isinstance(row, dict) else _canonical(row)
                               for index, row in enumerate(list(state.get("inventory") or []))),
                           tuple(_canonical(managed_pools[key]) for key in sorted(managed_pools)),
                           native_view, native_owners, bool(native_view is not None and any(
                               isinstance(witness, NativeGrantCustody)
                               and witness.get("native_grant_model_digest") == grant_model_digest(definition)
                               and witness.origin and witness.origin[0] != "pending_acquisition"
                               for witness in verified_numeric_actions)),
                           frozenset(catalog_field(_spell_entries_catalog(entries), entry, "entry_key")
                               for entry in catalog_rows(_spell_entries_catalog(entries), raw=True)
                               if catalog_field(_spell_entries_catalog(entries), entry, "entry_type") == "spell"
                               and catalog_field(_spell_entries_catalog(entries), entry, "metadata").get("ritual") is True),
                           frozenset(retired_choice_targets), frozenset(historical_active_targets))
    authority = replace(authority, reconstructed_spell_roles=reconstruction_roles,
                        feature_composition=composition,
                        passive_member_frames=_passive_member_frames(definition,
                            attained_feature_owners, tuple(statuses), frozenset(verified_class_rows)),
                        managed_resource_targets=_recognized_managed_resource_targets(definition, composition, tracker_bindings),
                        tracker_associations=tracker_bindings,
                        spell_property_bases=tuple(spell_property_bases),
                        spell_property_clear_owners=frozenset(spell_property_clear_owners))
    from .character_feature_proficiency_grants import project_automatic_expertise
    authority = project_automatic_expertise(authority, definition, systems_service,
        verified_numeric_actions, attained_feature_owners)
    # Current capacity/reset comes from the exact item source, not imported
    # charge totals or historical numeric witnesses. Availability stays unknown
    # until a bounded current pair is explicitly recorded.
    from .character_item_capabilities import known_counter
    charge_statuses = {row.path: row for row in authority.resource_statuses}
    for entry in authority.item_capability_entries(definition):
        counter = entry["capability"].get("counter")
        if counter is None:
            continue
        path = f"item_charge:{entry['physical_id']}"
        physical = entry["physical"]
        known = known_counter(physical, counter["maximum"])
        charge_statuses[path] = EffectiveStatus(path, VERIFIED if known else UNKNOWN,
            {"current": physical.get("charges_current"), "max": physical.get("charges_max")},
            {"current": physical["charges_current"], "max": counter["maximum"],
             "reset_on": counter["reset_on"], "reset_to": counter["reset_to"],
             "source_basis_digest": entry["source_basis_digest"]} if known else None,
            "current_approved_item_uses" if known else "item_uses_current_unrecorded_or_incompatible")
    authority = replace(authority, resource_statuses=tuple(charge_statuses.values()))
    from .character_wizard_rules import qualified_read_context
    authority = replace(authority, wizard_rule_context_json=_canonical(
        qualified_read_context(authority, definition, systems_service)))
    from .character_spell_slots import bind_slot_grants
    authority = bind_slot_grants(authority, definition, state, systems_service, all_managed_pools)
    from .character_feature_history import qualify_authority
    authority = qualify_authority(authority, definition, state, systems_service)
    return replace(authority, native_choice_ledger_json=_canonical(
        _native_spell_choice_ledger(authority, definition, systems_service, state=state,
            campaign_page_records=campaign_page_records))) if has_native_grants(definition) else authority


def build_reconciled_source_authority(
    *, definition: CharacterDefinition, state: dict[str, Any],
    state_revision: int, systems_service: Any,
    campaign_page_records: list[Any] | None,
    verified_manual_actions: tuple[Any, ...] = (),
    verified_numeric_actions: tuple[Any, ...] = (),
    prospective_spell_checkpoint: Any | None = None,
) -> SourceAuthority:
    """Pure writer/read entry point after revisioned SQLite activation wins."""
    from .character_equipment_activation import effective_definition

    reconciled, _warnings = effective_definition(definition, state)
    authority = build_source_authority(
        definition=reconciled, state=state, state_revision=state_revision,
        systems_service=systems_service,
        campaign_page_records=campaign_page_records,
        verified_manual_actions=verified_manual_actions,
        verified_numeric_actions=verified_numeric_actions,
        prospective_spell_checkpoint=prospective_spell_checkpoint,
    )
    return replace(authority, original_definition_digest=numeric_value_digest(definition.to_dict()))


def _native_spell_choice_capacity_frame(definition):
    """Capacity intent excludes notes, proof renewal, and copied advisory views."""
    from .character_spell_grants import CLASS_CHOICE_STATE_FIELD
    return {"classes": profile_class_rows(definition.profile),
        "choices": [{key: row.get(key) for key in (
            "id", "class_row_id", "systems_ref", "page_ref", "spell_source_row_id", "mark",
            "prepared", "is_prepared", CLASS_CHOICE_STATE_FIELD)}
            for row in definition.spellcasting.get("spells", []) if isinstance(row, dict)],
        "grants": definition.spellcasting.get("native_spell_grants")}


def native_spell_choice_capacity_affected(prior_definition, candidate_definition):
    from .character_spell_grants import has_native_grants
    return bool((has_native_grants(prior_definition) or has_native_grants(candidate_definition))
        and _native_spell_choice_capacity_frame(prior_definition) != _native_spell_choice_capacity_frame(candidate_definition))


def validate_native_spell_choice_capacity_transition(prior_definition, candidate_definition, state, *,
        prior_authority, systems_service, campaign_page_records,
        verified_numeric_actions=(), verified_manual_actions=(), advancement_intent=None,
        adoption_proof=None, prior_record=None, actor_id=None):
    """Check complete affected pools before issuance; candidate markers prove nothing.

    Callers reload actual original custody and witnesses again under reservation.
    Returned snapshots describe that comparison, never reusable permission.
    """
    from .character_source_reads import phase_of
    if not native_spell_choice_capacity_affected(prior_definition, candidate_definition):
        return ()
    if (not isinstance(prior_authority, SourceAuthority) or systems_service is None
            or (prior_authority.original_definition_digest or prior_authority.definition_digest)
                != numeric_value_digest(prior_definition.to_dict())):
        raise ValueError("The actual original class choice authority is required.")
    from .character_spell_grants import (native_class_choice_state, GrantView, _inspect_source_grants,
        validate_native_grant_model, has_native_grants)
    from .character_ability_inputs import input_records
    adoption = None
    checkpoint = None
    checkpoint_witnesses = tuple(verified_numeric_actions)
    if has_native_grants(prior_definition):
        validate_native_grant_model(prior_definition)
        if not prior_authority.native_grant_custody_confirmed:
            raise ValueError("The prior canonical model needs confirmed saved custody.")
    else:
        from .character_reconciliation import PendingReviewedSourceProof
        if (type(adoption_proof) is not PendingReviewedSourceProof or prior_record is None
                or prior_record.definition.to_dict() != prior_definition.to_dict()):
            raise ValueError("First native model adoption needs its exact reviewed source proof.")
        adoption = adoption_proof.native_spell_origin_delta(prior_record, candidate_definition, state, actor_id,
            source_read_phase=phase_of(systems_service))
        if not isinstance(adoption, dict) or adoption.get("schema_version") not in {2, 3, 4}:
            raise ValueError("First native model adoption needs its exact reviewed migration.")
        if adoption["schema_version"] in {3, 4}:
            result = adoption_proof.native_result
            checkpoint = _validated_spell_checkpoint_result(result, prior_record, candidate_definition, state, actor_id, systems_service)
            # Only a freshly bound native issuer result may supply these pending numeric witnesses.
            checkpoint_witnesses += tuple({"authorization": marker, "source_basis_digest": result.provenance["renewed_source_bases"][marker["target_id"]]}
                for marker in result.authorizations if marker.get("provenance") == "native_requalification")
    validate_native_grant_model(candidate_definition)
    before_rows = [row for row in prior_definition.spellcasting.get("spells", []) if isinstance(row, dict)]
    after_rows = [row for row in candidate_definition.spellcasting.get("spells", []) if isinstance(row, dict)]
    old = {_text(row.get("id")): row for row in before_rows}
    new = {_text(row.get("id")): row for row in after_rows}
    if (len(old) != len(before_rows) or len(new) != len(after_rows) or "" in old or "" in new):
        raise ValueError("Class choice identity is ambiguous.")
    if adoption is not None:
        removed = set(adoption["request"]["remove_ids"])
        if (prior_definition.profile != candidate_definition.profile
                or state != prior_record.state_record.state
                or set(new) != set(old) - removed
                or checkpoint is None and any(new[key] != old[key] for key in new)):
            raise ValueError("First adoption cannot allocate, reprepare or reclassify ordinary choices.")
    prior_ledger = (prior_authority.spell_choice_ledger if has_native_grants(prior_definition) else
        _native_spell_choice_ledger(prior_authority, prior_definition, systems_service,
            state=prior_record.state_record.state, campaign_page_records=campaign_page_records))
    prior_pools = prior_ledger["pools"]
    prior_choices = {row["spell_id"]: row for row in prior_ledger["choices"]}
    def retained_choice_state(choice):
        # Prepared-list presentation uses "available" even for a proved active
        # preparation. Transfer its actual prior ordinary fact, not that display
        # label. The prospective ledger still rechecks current source, owner,
        # list, level and marks; this does not confer new selection or custody.
        if (choice["historical_state"] == "available"
                and choice["pool"] == "prepared"
                and all(choice.get(key) is True for key in (
                    "ordinary_prepared", "ordinary_counted", "ordinary_eligible",
                    "current_usable", "counts_against_prepared", "retained_obligation"))):
            return "active"
        return choice["historical_state"]
    changed_ids = {key for key in set(old) | set(new) if old.get(key) != new.get(key)}
    affected = {_text(row.get("class_row_id")) for key in changed_ids for row in (old.get(key), new.get(key))
        if isinstance(row, dict) and not row.get("spell_source_row_id")}
    old_classes = {_text(row.get("row_id")): row for row in profile_class_rows(prior_definition.profile)}
    new_classes = {_text(row.get("row_id")): row for row in profile_class_rows(candidate_definition.profile)}
    affected.update(key for key in set(old_classes) | set(new_classes) if old_classes.get(key) != new_classes.get(key))
    old_grants = {row.get("id"): row for row in prior_definition.spellcasting.get("native_spell_grants", {}).get("occurrences", []) if isinstance(row, dict)}
    new_grants = {row.get("id"): row for row in candidate_definition.spellcasting.get("native_spell_grants", {}).get("occurrences", []) if isinstance(row, dict)}
    changed_grant_owners = {row.get("class_row_id") for key in set(old_grants) | set(new_grants)
        if old_grants.get(key) != new_grants.get(key) for row in (old_grants.get(key), new_grants.get(key)) if isinstance(row, dict)}
    affected.update(changed_grant_owners)
    if not affected and adoption is None:
        return ()
    advancement = old_classes != new_classes
    valid_intent = (isinstance(advancement_intent, NativeAdvancementIntent)
        and advancement_intent.matches_resource_readback(prior_definition, candidate_definition)
        and advancement_intent.ability_inputs_json == _canonical(candidate_definition.stats.get("ability_inputs")))
    if advancement and not valid_intent:
        raise ValueError("Prospective class capacity needs the actual validated advancement inputs.")
    candidate = build_reconciled_source_authority(definition=candidate_definition, state=state,
        state_revision=prior_authority.state_revision, systems_service=systems_service,
        campaign_page_records=campaign_page_records, verified_numeric_actions=checkpoint_witnesses,
        verified_manual_actions=verified_manual_actions, prospective_spell_checkpoint=checkpoint)
    # Retained independently authenticated grant origins do not lose custody
    # merely because a strict producer appends an independently checked feature.
    inspected = _inspect_source_grants(candidate_definition, systems_service)
    prior_origins = {row["id"]: row for row in prior_authority.native_grant_view.occurrences
        if row.get("status") == VERIFIED} if prior_authority.native_grant_view is not None else {}
    qualified = []
    for row in inspected.occurrences:
        same = row["id"] in prior_origins and all(row.get(key) == prior_origins[row["id"]].get(key)
            for key in ("owner_id", "acquisition_id", "source_ref", "class_row_id", "rule_id", "leaf_id", "spell_ref", "source_basis_digest"))
        qualified.append({**row, "status": VERIFIED if row.get("status") == "SOURCE_SUPPORTED"
            and (same or valid_intent or adoption is not None and row["id"] in adoption["supported_grant_ids"]) else "UNPROVED"})
    candidate = replace(candidate, native_grant_view=GrantView(tuple(qualified), inspected.diagnostics, inspected.migration_edges))
    if adoption is not None:
        retained = ({key: retained_choice_state(value) for key, value in prior_choices.items() if key in new}
                    if checkpoint is None else {})
        ledger = _native_spell_choice_ledger(candidate, candidate_definition, systems_service,
            state=state, campaign_page_records=campaign_page_records, retained_states=retained)
        snapshots = []
        for phase, model in (("prior", prior_ledger), ("prospective", ledger)):
            for pool in model["pools"]:
                if pool["status"] == "KNOWN" and pool["remaining"] is not None and pool["remaining"] < 0:
                    raise ValueError("A proved class choice bound is exceeded during adoption.")
                if checkpoint is not None and phase == "prospective" and pool["status"] != "KNOWN":
                    raise ValueError("The complete current reconstruction capacity is unresolved.")
                snapshots.append(_canonical({"phase": phase, "nonallocating_adoption": checkpoint is None,
                    **({"current_spell_reconstruction": True} if checkpoint is not None else {}), "pool": pool}))
        return tuple(snapshots)
    retained, active, retired = {}, set(), set()
    for spell_id, raw in new.items():
        if raw.get("spell_source_row_id"):
            continue
        previous = prior_choices.get(spell_id)
        if old.get(spell_id) == raw and previous:
            retained[spell_id] = retained_choice_state(previous)
            continue
        declared = native_class_choice_state(raw)
        if declared == "retired":
            if not previous or not previous["ordinary_counted"]:
                raise ValueError("Only an independently eligible ordinary choice may retire.")
            retired.add(spell_id)
        elif declared == "active":
            if candidate.numeric_basis_digest(f"spell_choice:{spell_id}") is None:
                raise ValueError("The prospective choice needs its exact current spell source and list.")
            if previous and previous["historical_state"] == "UNKNOWN":
                raise ValueError("An unresolved choice cannot be recast as new capacity.")
            if previous is None and not native_spell_choice_birth_is_absent(prior_definition, raw,
                    candidate_definition=candidate_definition):
                raise ValueError("A new choice cannot borrow or rename an original obligation.")
            active.add(spell_id)
        elif previous and old.get(spell_id) == raw:
            retained[spell_id] = retained_choice_state(previous)
        else:
            raise ValueError("A new ordinary choice needs its actual native selection checkpoint.")
    for spell_id in set(old) - set(new):
        previous = prior_choices.get(spell_id)
        if previous and previous["retained_obligation"] and not previous["ordinary_counted"]:
            raise ValueError("An unresolved retained obligation cannot release capacity.")
    inputs = input_records(candidate_definition.stats) if valid_intent else None
    if inputs is not None and any(not (prior_authority.field_status(f"stats.ability_scores.{key}.score").status in {VERIFIED, MANUAL})
            for key in inputs):
        raise ValueError("Advancement ability inputs need independently qualified original owners.")
    ledger = _native_spell_choice_ledger(candidate, candidate_definition, systems_service,
        state=state, campaign_page_records=campaign_page_records, prospective_active=active,
        prospective_retired=retired, retained_states=retained, validated_inputs=inputs)
    snapshots = []
    prospective_choices = {row["spell_id"]: row for row in ledger["choices"]}
    for row_id in sorted(affected):
        previous = [row for row in prior_pools if row["class_row_id"] == row_id]
        prospective = [row for row in ledger["pools"] if row["class_row_id"] == row_id]
        has_obligations = any(choice["class_row_id"] == row_id for choice in (*prior_choices.values(), *ledger["choices"]))
        if not prospective and not previous and not has_obligations and row_id not in changed_grant_owners:
            continue
        if not prospective:
            raise ValueError("The complete class choice pool is unavailable.")
        # Restrict choice edits to their actual pools. A class/source-model
        # change affects all of that owner's pools; unrelated pools retain
        # independent nonallocating preservation.
        all_pools = old_classes.get(row_id) != new_classes.get(row_id) or row_id in changed_grant_owners
        if not all_pools:
            selected_kinds = set()
            for spell_id in changed_ids:
                for choice in (prior_choices.get(spell_id), prospective_choices.get(spell_id)):
                    if choice is not None and choice["class_row_id"] == row_id:
                        if choice["pool"] is None:
                            selected_kinds.update(pool["kind"] for pool in (*previous, *prospective))
                        else:
                            selected_kinds.add(choice["pool"])
                            if choice["pool"] == "spellbook":
                                selected_kinds.add("prepared")
            previous = [pool for pool in previous if pool["kind"] in selected_kinds]
            prospective = [pool for pool in prospective if pool["kind"] in selected_kinds]
        # Source withdrawal never supplies a refund, even for net-zero swaps.
        if any(row["status"] != "KNOWN" or row["remaining"] is not None and row["remaining"] < 0 for row in previous):
            raise ValueError("The prior class choice capacity is unresolved.")
        for pool in prospective:
            if pool["status"] != "KNOWN" or pool["remaining"] is not None and pool["remaining"] < 0:
                raise ValueError("The prospective class choice capacity is unresolved or exceeded.")
            old_pool = next((row for row in previous if row["kind"] == pool["kind"]), None)
            if old_pool is None:
                row = new_classes.get(row_id)
                ref = row.get("systems_ref", {}) if row else {}
                cls = _current_systems_entry(candidate_definition.campaign_slug, "systems", ref.get("entry_key", ""), systems_service)
                subclass = _current_reconstruction_subclass(candidate_definition, row, cls, systems_service) if cls and row else None
                presence_authority = replace(prior_authority, native_choice_ledger_json=_canonical(prior_ledger))
                inception = resolve_native_spell_pool_inception(prior_definition,
                    prior_authority=presence_authority, class_row_id=row_id,
                    selected_class=cls, selected_subclass=subclass,
                    target_level=row.get("level") if row else None, kind=pool["kind"])
                if not valid_intent or inception["status"] != "ABSENT":
                    raise ValueError("The absent prior pool needs authenticated first acquisition.")
            snapshots.append(_canonical({"class_row_id": row_id, "kind": pool["kind"],
                "prior": old_pool, "prospective": pool}))
    return tuple(snapshots)


def validate_native_spell_choice_decision_transition(prior_record, candidate_definition, state, *,
        prior_authority, actor_id, operation_kind, allow_management=False, allow_progression=False,
        systems_service=None, campaign_page_records=None, connection=None, checkpoint_proof=None):
    """Validate exact typed decisions, never a generic trusted-authoring bypass."""
    from .character_spell_grants import (native_class_choice_rows, native_class_choice_state,
        CLASS_CHOICE_STATE_FIELD, grant_model_digest, validate_native_grant_model)
    before = prior_record.definition
    if checkpoint_proof is not None:
        _validated_spell_checkpoint_result(checkpoint_proof, prior_record, candidate_definition, state, actor_id, systems_service)
        return ()  # Current confirmation is in its dedicated nested schema5 proof, not a fabricated selection event.
    if not any(CLASS_CHOICE_STATE_FIELD in row for model in (before, candidate_definition)
            for row in model.spellcasting.get("spells", []) if isinstance(row, dict)):
        return ()
    old_rows, new_rows = native_class_choice_rows(before), native_class_choice_rows(candidate_definition)
    from .character_source_repair import load_verified_numeric_actions, load_verified_manual_actions, _decision_generation
    from .db import get_db
    db = connection if connection is not None else get_db()
    _decision_generation(db, before.campaign_slug, before.character_slug,
        prior_record.committed_revision, numeric_value_digest(before.to_dict()))
    prior_numeric = load_verified_numeric_actions(before.campaign_slug, before.character_slug, connection=db, strict=True)
    prior_authority = build_reconciled_source_authority(definition=before,
        state=prior_record.state_record.state, state_revision=prior_record.state_record.revision,
        systems_service=systems_service, campaign_page_records=campaign_page_records,
        verified_numeric_actions=prior_numeric,
        verified_manual_actions=load_verified_manual_actions(before.campaign_slug, before.character_slug, connection=db, strict=True))
    typed = {spell_id for spell_id, row in old_rows.items() if CLASS_CHOICE_STATE_FIELD in row}
    available = {row["spell_id"] for row in prior_authority.spell_choice_ledger.get("choices", [])
        if row.get("class_list_available") is True and row.get("current_usable") is True
        and row.get("ordinary_eligible") is True and row.get("ordinary_prepared") is False}
    def selection_markers(model, spell_id):
        return [m for m in model.source.get("source_authorizations", []) if isinstance(m, dict)
            and (m.get("target_kind"), m.get("target_id"), m.get("metric")) == ("spell_choice", f"spell_choice:{spell_id}", "selection")]
    reviewed_renewals = set()
    if operation_kind == "character_update_apply":
        from .character_source_repair import _valid_numeric_witness_marker
        for spell_id in typed:
            current_markers = selection_markers(candidate_definition, spell_id)
            if (old_rows.get(spell_id) == new_rows.get(spell_id) and len(current_markers) == 1
                    and current_markers != selection_markers(before, spell_id)
                    and _valid_numeric_witness_marker(current_markers[0], before.character_slug, "native_requalification")
                    and current_markers[0].get("value_digest") == numeric_value_digest(new_rows[spell_id])):
                # The coordinator separately requires its exact reviewed native
                # requalification proof. Its durable reader validates the retained
                # original decision before binding this renewed marker.
                reviewed_renewals.add(spell_id)
    changed = [spell_id for spell_id in set(old_rows) | set(new_rows)
        if (spell_id in old_rows and CLASS_CHOICE_STATE_FIELD in old_rows[spell_id]
            or spell_id in new_rows and CLASS_CHOICE_STATE_FIELD in new_rows[spell_id])
        and (old_rows.get(spell_id) != new_rows.get(spell_id)
            or selection_markers(before, spell_id) != selection_markers(candidate_definition, spell_id))
        and spell_id not in reviewed_renewals]
    if not changed:
        return ()
    if (operation_kind != "interactive_update" or not (allow_management or allow_progression)
            or type(actor_id) is not int or actor_id < 1 or systems_service is None
            or prior_authority is None or not prior_authority.native_grant_custody_confirmed
            or prior_authority.state_revision != prior_record.state_record.revision):
        raise ValueError("The class choice decision needs its exact authenticated prior view.")
    old_model, new_model = validate_native_grant_model(before), validate_native_grant_model(candidate_definition)
    if allow_management and grant_model_digest(before) != grant_model_digest(candidate_definition):
        raise ValueError("A spell management decision cannot change native feature grants.")
    if allow_progression and (any(row not in new_model["occurrences"] for row in old_model["occurrences"])
            or any(row not in candidate_definition.source["native_acquisitions"]["owners"]
                for row in before.source["native_acquisitions"]["owners"])):
        raise ValueError("Advancement changed retained feature grant identities.")
    candidate = build_reconciled_source_authority(definition=candidate_definition,
        state=state, state_revision=prior_record.state_record.revision,
        systems_service=systems_service, campaign_page_records=campaign_page_records,
        verified_numeric_actions=prior_numeric)
    decisions = []
    active = set(prior_authority.confirmed_active_spell_choices)
    expected_provenance = "native_level_up" if allow_progression else "native_spell_choice"
    from .character_source_repair import _valid_numeric_witness_marker
    for spell_id in sorted(changed):
        old, new = old_rows.get(spell_id), new_rows.get(spell_id)
        birth = old is None and new is not None and native_spell_choice_birth_is_absent(before, new,
            candidate_definition=candidate_definition)
        if new is None or old is None and not birth:
            raise ValueError("A typed class choice observation cannot be removed or borrow prior history.")
        old_state, new_state = native_class_choice_state(old) if old is not None else None, native_class_choice_state(new)
        left, right = deepcopy(old), deepcopy(new)
        if left is not None:
            left.pop(CLASS_CHOICE_STATE_FIELD, None)
        right.pop(CLASS_CHOICE_STATE_FIELD, None)
        from .character_spell_reconstruction import _marks as checkpoint_marks
        available_preparation = bool(old is not None and old_state is None and new_state == "active"
            and spell_id in available and left != right
            and {key for key in set(left) | set(right) if (key in left) != (key in right) or left.get(key) != right.get(key)} <= {"mark", "prepared", "is_prepared"}
            and checkpoint_marks(old)[1] is False and checkpoint_marks(new)[1] is True)
        preparation = bool(new_state == old_state and new_state is not None and left != right
            and {key for key in set(left) | set(right) if (key in left) != (key in right) or left.get(key) != right.get(key)} <= {"mark", "prepared", "is_prepared"})
        continuing = bool(new_state == old_state and new_state is not None and left == right)
        if new_state not in {"active", "retired"} or (left != right and not preparation and not available_preparation and not birth):
            raise ValueError("A class choice decision must preserve all historical spell observations.")
        target = f"spell_choice:{spell_id}"
        old_markers = [m for m in before.source.get("source_authorizations", []) if isinstance(m, dict)
            and (m.get("target_kind"), m.get("target_id"), m.get("metric")) == ("spell_choice", target, "selection")]
        current = [m for m in candidate_definition.source.get("source_authorizations", []) if isinstance(m, dict)
            and (m.get("target_kind"), m.get("target_id"), m.get("metric")) == ("spell_choice", target, "selection")]
        if (len(current) != 1 or not _valid_numeric_witness_marker(current[0], before.character_slug, expected_provenance)
                or current[0].get("schema_version") != 2
                or current[0].get("provenance") != ("native_level_up" if allow_progression else "native_spell_choice")
                or current[0].get("value_digest") != numeric_value_digest(new)
                or candidate.numeric_basis_digest(target) is None):
            raise ValueError("The new class choice marker or current source basis is unavailable.")
        if available_preparation:
            if len(old_markers) > 1:
                raise ValueError("The retained available-list observation has ambiguous prior markers.")
            operation = "prepare_available"
            active.add(spell_id)
        elif preparation or continuing:
            confirmed = (prior_authority.confirmed_retired_spell_choices if old_state == "retired"
                else prior_authority.confirmed_active_spell_choices)
            if spell_id not in confirmed or len(old_markers) != 1:
                raise ValueError("A continued class choice needs its exact confirmed prior decision.")
            operation = "prepare" if preparation else "continue"
        elif new_state == "retired":
            if spell_id not in active or len(old_markers) != 1:
                raise ValueError("Only an independently proved ordinary choice can retire.")
            operation = "retire"
            active.remove(spell_id)
        elif old_state == "retired":
            if spell_id not in prior_authority.confirmed_retired_spell_choices or len(old_markers) != 1:
                raise ValueError("Reactivation needs the confirmed prior retirement decision.")
            operation = "reactivate"
            active.add(spell_id)
        else:
            if not birth or spell_id in active or old_markers:
                raise ValueError("A fresh ordinary choice cannot borrow unresolved historical choice proof.")
            operation = "select"
            active.add(spell_id)
        decisions.append({"spell_id": spell_id, "operation": operation,
            "before_state": old_state, "after_state": new_state,
            "before_row_digest": numeric_value_digest(old), "after_row_digest": numeric_value_digest(new),
            "prior_authorization": deepcopy(old_markers[0]) if old_markers else None,
            "prior_owner_digest": numeric_target_owner_digest(before, prior_record.state_record.state,
                "spell_choice", target, "selection") if old_markers else None,
            "prior_source_basis_digest": next((w.get("source_basis_digest") for w in prior_numeric
                if isinstance(w, dict) and w.get("authorization", w) == old_markers[0]
                and w.get("source_basis_digest") and not w.get("transition_proof")), None) if old_markers else None})
    from .character_builder_foundation import _spellcasting_mode_for_class
    for row_id in {new_rows[d["spell_id"]]["class_row_id"] for d in decisions}:
        rows = [r for r in profile_class_rows(candidate_definition.profile) if r.get("row_id") == row_id]
        if len(rows) != 1 or (row_id not in prior_authority.verified_class_rows and not allow_progression):
            raise ValueError("The class choice owner is ambiguous.")
        row = rows[0]
        ref = dict(row.get("systems_ref") or {})
        entry = _current_systems_entry(candidate_definition.campaign_slug, "systems", ref.get("entry_key", ""), systems_service)
        if entry is None or entry.entry_type != "class" or any(ref.get(key) and ref[key] != getattr(entry, key, None)
                for key in ("entry_key", "slug", "source_id", "entry_type")):
            raise ValueError("The current class choice source is unavailable.")
        subclass = _current_reconstruction_subclass(candidate_definition, row, entry, systems_service)
        options = dict(selected_class=entry, selected_subclass=subclass)
        mode = _spellcasting_mode_for_class(entry.title, row_level=row["level"], **options)
        row_decisions = [d for d in decisions if new_rows[d["spell_id"]]["class_row_id"] == row_id]
        if mode not in {"known", "prepared", "wizard"}:
            raise ValueError("The typed class choice has no supported ordinary selection mode.")
        for decision in row_decisions:
            raw = new_rows[decision["spell_id"]]
            spell_ref = raw.get("systems_ref", {})
            spell = _current_systems_entry(candidate_definition.campaign_slug, "systems", spell_ref.get("entry_key", ""), systems_service)
            if spell is None or type(spell.metadata.get("level")) is not int:
                raise ValueError("The ordinary choice spell level is unavailable.")
            if decision["operation"] == "retire" and (spell.metadata["level"] == 0 or mode not in {"known", "wizard"}):
                raise ValueError("This ordinary class choice cannot be removed.")
        if any(d["operation"] in {"prepare", "prepare_available"} for d in row_decisions):
            if mode not in {"prepared", "wizard"}:
                raise ValueError("This class choice does not support preparation edits.")
            effective = prior_authority.effective_definition(before)
            effective_rows = {r.get("id"): r for r in effective.spellcasting.get("spells", []) if isinstance(r, dict)}
            for decision in row_decisions:
                if decision["operation"] in {"prepare", "prepare_available"} and effective_rows.get(decision["spell_id"], {}).get("is_always_prepared") is True:
                    raise ValueError("A fixed always-prepared path cannot be toggled.")
        # Complete prior/prospective pool bounds are shared with ordinary
        # untyped choices, before issuance and freshly at publication. Typed
        # decision custody cannot substitute for or independently recalculate it.
    return tuple(decisions)


def prepare_native_spell_choice_authorizations(
    *, prior_definition: CharacterDefinition, candidate_definition: CharacterDefinition,
    state: dict[str, Any], state_revision: int, systems_service: Any,
    campaign_page_records: list[Any] | None, prior_record: Any | None = None,
    actor_id: int | None = None,
) -> tuple[CharacterDefinition, tuple[dict[str, Any], ...], dict[str, str], str]:
    """Mark changed choices from the guarded spell editor for postwrite audit."""
    from .character_source_repair import numeric_authorization_record, add_numeric_authorization

    numeric = ()
    if native_spell_choice_capacity_affected(prior_definition, candidate_definition):
        if prior_record is None or prior_record.definition.to_dict() != prior_definition.to_dict():
            raise ValueError("The actual original class choice record is required.")
        from .character_source_repair import load_verified_numeric_actions, load_verified_manual_actions
        numeric = load_verified_numeric_actions(prior_definition.campaign_slug, prior_definition.character_slug, strict=True)
        manual = load_verified_manual_actions(prior_definition.campaign_slug, prior_definition.character_slug, strict=True)
        original = build_reconciled_source_authority(definition=prior_definition,
            state=prior_record.state_record.state, state_revision=prior_record.state_record.revision,
            systems_service=systems_service, campaign_page_records=campaign_page_records,
            verified_numeric_actions=numeric, verified_manual_actions=manual)
        validate_native_spell_choice_capacity_transition(prior_definition, candidate_definition, state,
            prior_authority=original, systems_service=systems_service,
            campaign_page_records=campaign_page_records,
            verified_numeric_actions=numeric, verified_manual_actions=manual)
    authority = build_reconciled_source_authority(
        definition=candidate_definition, state=state, state_revision=state_revision,
        systems_service=systems_service, campaign_page_records=campaign_page_records,
        verified_numeric_actions=numeric,
    )
    prior_values = numeric_target_values(prior_definition, state)
    values = numeric_target_values(candidate_definition, state)
    changed_ids = {
        key[1] for key in set(prior_values) | set(values)
        if key[0] == "spell_choice" and prior_values.get(key) != values.get(key)
    }
    action_id = uuid4().hex
    markers: list[dict[str, Any]] = []
    bases: dict[str, str] = {}
    for (kind, target_id, metric), raw in values.items():
        if kind != "spell_choice":
            continue
        if prior_values.get((kind, target_id, metric)) == raw:
            continue
        basis = authority.numeric_basis_digest(target_id)
        if basis is None:
            continue
        markers.append(numeric_authorization_record(
            character_slug=candidate_definition.character_slug,
            target_kind=kind, target_id=target_id, metric=metric,
            raw_value=raw, action_id=action_id, provenance="native_spell_choice",
        ))
        bases[target_id] = basis
    if len(markers) > 128:
        raise ValueError("Too many spell selections for one source review.")
    payload = deepcopy(candidate_definition.to_dict())
    if changed_ids:
        changed_spell_ids = {target_id.removeprefix("spell_choice:") for target_id in changed_ids}
        spellcasting = dict(payload.get("spellcasting") or {})
        spellcasting["manual_authorizations"] = [
            row for row in list(spellcasting.get("manual_authorizations") or [])
            if not (isinstance(row, dict) and row.get("target_kind") == "spell"
                    and row.get("target_id") in changed_spell_ids)
        ]
        payload["spellcasting"] = spellcasting
        source = dict(payload.get("source") or {})
        source["source_authorizations"] = [
            row for row in list(source.get("source_authorizations") or [])
            if not (isinstance(row, dict) and row.get("target_kind") == "spell_choice"
                    and row.get("target_id") in changed_ids)
        ]
        payload["source"] = source
    for marker in markers:
        payload = add_numeric_authorization(payload, marker)
    result = CharacterDefinition.from_dict(payload)
    from .character_spell_grants import CLASS_CHOICE_STATE_FIELD
    if any(CLASS_CHOICE_STATE_FIELD in row for row in result.spellcasting.get("spells", []) if isinstance(row, dict)):
        if prior_record is None or prior_record.definition.to_dict() != prior_definition.to_dict():
            raise ValueError("The actual prior class choice record is required.")
        from .character_source_repair import load_verified_numeric_actions, load_verified_manual_actions
        prior_authority = build_reconciled_source_authority(definition=prior_definition,
            state=state, state_revision=state_revision, systems_service=systems_service,
            campaign_page_records=campaign_page_records,
            verified_numeric_actions=load_verified_numeric_actions(result.campaign_slug, result.character_slug, strict=True),
            verified_manual_actions=load_verified_manual_actions(result.campaign_slug, result.character_slug, strict=True))
        validate_native_spell_choice_decision_transition(prior_record, result, state,
            prior_authority=prior_authority, actor_id=actor_id, operation_kind="interactive_update",
            allow_management=True, systems_service=systems_service,
            campaign_page_records=campaign_page_records)
    return result, tuple(markers), bases, authority.source_snapshot_digest


def prepare_native_level_up_resource_authorizations(
    *, prior_definition: CharacterDefinition, candidate_definition: CharacterDefinition,
    prior_state: dict[str, Any], state_revision: int, systems_service: Any,
    campaign_page_records: list[Any] | None,
    verified_manual_actions: tuple[Any, ...] = (),
    verified_numeric_actions: tuple[Any, ...] = (),
    advancement_intent: NativeAdvancementIntent | None = None,
) -> tuple[CharacterDefinition, tuple[dict[str, Any], ...], dict[str, str], tuple[Any, ...], str, dict[str, Any]]:
    """Pre-mark exact new or previously owned source-derived resource maxima.

    The returned simulated witnesses permit the pending merge. They are never
    durable authority: the caller must audit a confirmed publication readback.
    """
    from .character_source_repair import numeric_authorization_record, add_numeric_authorization
    from .character_hit_dice import derive_hit_dice_max_pools
    from .character_spell_slots import spell_slot_lanes_from_spellcasting
    if (not isinstance(advancement_intent, NativeAdvancementIntent)
            or not advancement_intent.matches(prior_definition, candidate_definition)):
        raise NativeAdvancementValidationError(
            "This advancement could not be validated. Refresh its preview and review the choices."
        )
    prospective_state = deepcopy(prior_state)
    prior_values = numeric_target_values(prior_definition, prior_state)
    prior_authority = build_reconciled_source_authority(
        definition=prior_definition, state=prior_state,
        state_revision=state_revision, systems_service=systems_service,
        campaign_page_records=campaign_page_records,
        verified_manual_actions=verified_manual_actions,
        verified_numeric_actions=verified_numeric_actions,
    )
    prior_authority = prior_authority.bind_current_numbers(
        prior_definition, prior_state, systems_service=systems_service,
        campaign_page_records=campaign_page_records,
    )
    validate_native_spell_choice_capacity_transition(prior_definition, candidate_definition, prior_state,
        prior_authority=prior_authority, systems_service=systems_service,
        campaign_page_records=campaign_page_records, verified_numeric_actions=verified_numeric_actions,
        verified_manual_actions=verified_manual_actions, advancement_intent=advancement_intent)
    prior_slots = list(prior_state.get("spell_slots") or [])
    prospective_slots = deepcopy(prior_slots)
    for lane in spell_slot_lanes_from_spellcasting(candidate_definition.spellcasting):
        lane_id = _text(lane.get("id"))
        if not lane_id:
            continue
        for slot in list(lane.get("slot_progression") or []):
            level = slot.get("level")
            max_slots = slot.get("max_slots")
            if type(level) is not int or level < 1 or type(max_slots) is not int:
                continue
            matches = [row for row in prospective_slots if isinstance(row, dict)
                       and _text(row.get("slot_lane_id")) == lane_id and row.get("level") == level]
            if len(matches) == 1:
                matches[0]["max"] = max_slots
            elif not matches and not any(isinstance(row, dict) and row.get("level") == level
                                         and not _text(row.get("slot_lane_id")) for row in prior_slots):
                prospective_slots.append({"slot_lane_id": lane_id, "level": level,
                                          "max": max_slots, "used": 0})
    prospective_state["spell_slots"] = prospective_slots
    prior_pools = list(dict(prior_state.get("hit_dice") or {}).get("pools") or [])
    prospective_pools = deepcopy(prior_pools)
    for pool in derive_hit_dice_max_pools(candidate_definition):
        matches = [row for row in prospective_pools if isinstance(row, dict)
                   and row.get("faces") == pool["faces"]]
        if len(matches) == 1:
            matches[0]["max"] = pool["max"]
        elif not matches:
            prospective_pools.append({"faces": pool["faces"], "max": pool["max"],
                                      "current": pool["max"]})
    prospective_state["hit_dice"] = {"pools": prospective_pools}
    baseline = build_reconciled_source_authority(
        definition=candidate_definition, state=prospective_state,
        state_revision=state_revision, systems_service=systems_service,
        campaign_page_records=campaign_page_records,
        verified_manual_actions=verified_manual_actions,
        verified_numeric_actions=verified_numeric_actions,
    )
    values = numeric_target_values(candidate_definition, prospective_state)
    action_id = uuid4().hex
    markers: list[dict[str, Any]] = []
    bases: dict[str, str] = {}
    # Prove explicit input renewals first. Dependent resource formulas can then
    # use those strict-producer inputs without borrowing an unowned old total.
    for (kind, target_id, metric), raw_value in values.items():
        if not native_advancement_input_target(kind, target_id, metric):
            continue
        basis = baseline.numeric_basis_digest(target_id)
        if (basis is None or raw_value is None
                or not prior_authority.field_status(target_id).is_effective):
            continue
        if (prior_values.get((kind, target_id, metric)) == raw_value
                and prior_authority.numeric_basis_digest(target_id) == basis):
            continue
        markers.append(numeric_authorization_record(
            character_slug=candidate_definition.character_slug,
            target_kind=kind, target_id=target_id, metric=metric,
            raw_value=raw_value, action_id=action_id, provenance="native_level_up",
        ))
        bases[target_id] = basis
    input_payload = candidate_definition.to_dict()
    for marker in markers:
        input_payload = add_numeric_authorization(input_payload, marker)
    candidate_definition = CharacterDefinition.from_dict(input_payload)
    input_witnesses = tuple(verified_numeric_actions) + tuple(
        {"authorization": marker, "source_basis_digest": bases[marker["target_id"]]}
        for marker in markers
    )
    baseline = build_reconciled_source_authority(
        definition=candidate_definition, state=prospective_state,
        state_revision=state_revision, systems_service=systems_service,
        campaign_page_records=campaign_page_records,
        verified_manual_actions=verified_manual_actions,
        verified_numeric_actions=input_witnesses,
    )
    baseline = baseline.continue_spell_modifier_history(
        prior_authority, prior_definition, candidate_definition,
        prior_state=prior_state, prior_state_revision=state_revision,
        state=prospective_state, state_revision=state_revision)
    validate_native_managed_resource_templates(
        candidate_definition, prospective_state, authority=baseline,
        systems_service=systems_service, campaign_page_records=campaign_page_records,
        prior_definition=prior_definition,
        restored_resource_currents=advancement_intent.restored_resource_currents,
        prior_authority=prior_authority,
    )
    candidate_ids = [target_id for kind, target_id, metric in values
                     if kind == "resource" and metric == "owner_reset"]
    for target_id in candidate_ids:
        if not target_id or candidate_ids.count(target_id) != 1:
            continue
        basis = baseline.resource_basis_digest(target_id)
        raw_value = values.get(("resource", target_id, "owner_reset"))
        if basis is None or raw_value is None:
            continue
        prior_value = prior_values.get(("resource", target_id, "owner_reset"))
        if prior_value is not None:
            if (numeric_value_digest(prior_value) == numeric_value_digest(raw_value)
                    and prior_authority.resource_basis_digest(target_id) == basis):
                continue
            kind, stable_id = target_id.split(":", 1)
            if not prior_authority.resource_status(kind, stable_id).is_effective:
                continue
        elif target_id.startswith("resource:"):
            resource_id = target_id.removeprefix("resource:")
            if any(_text(row.get("id")) == resource_id for row in prior_definition.resource_templates
                   if isinstance(row, dict)) or any(
                       _text(row.get("id")) == resource_id for row in list(prior_state.get("resources") or [])
                       if isinstance(row, dict)):
                continue
        markers.append(numeric_authorization_record(
            character_slug=candidate_definition.character_slug,
            target_kind="resource", target_id=target_id, metric="owner_reset",
            raw_value=raw_value, action_id=action_id, provenance="native_level_up",
        ))
        bases[target_id] = basis
    for (kind, target_id, metric), raw_value in values.items():
        if not native_baseline_target(kind, target_id, metric):
            continue
        basis = baseline.numeric_basis_digest(target_id)
        prior_status = prior_authority.field_status(target_id)
        if basis is None or raw_value is None or not prior_status.is_effective:
            continue
        if (prior_values.get((kind, target_id, metric)) == raw_value
                and prior_authority.numeric_basis_digest(target_id) == basis):
            continue
        markers.append(numeric_authorization_record(
            character_slug=candidate_definition.character_slug,
            target_kind=kind, target_id=target_id, metric=metric,
            raw_value=raw_value, action_id=action_id, provenance="native_level_up",
        ))
        bases[target_id] = basis
    for (kind, target_id, metric), raw_value in values.items():
        if kind not in {"spell_metric", "spell_choice"}:
            continue
        basis = baseline.numeric_basis_digest(target_id)
        if basis is None or (kind == "spell_metric" and raw_value.get("value") is None):
            continue
        prior_value = prior_values.get((kind, target_id, metric))
        if prior_value is not None:
            prior_verified = (target_id in prior_authority.verified_formula_rows if kind == "spell_metric"
                              else target_id.removeprefix("spell_choice:") in prior_authority.verified_spell_choices)
            if kind == "spell_choice" and prior_value != raw_value:
                from .character_spell_grants import native_class_choice_state
                old_state, new_state = native_class_choice_state(prior_value), native_class_choice_state(raw_value)
                spell_id = target_id.removeprefix("spell_choice:")
                prior_markers = [m for m in prior_definition.source.get("source_authorizations", []) if isinstance(m, dict)
                    and (m.get("target_kind"), m.get("target_id"), m.get("metric")) == (kind, target_id, metric)]
                if new_state == "active" and old_state == "retired":
                    prior_verified = spell_id in prior_authority.confirmed_retired_spell_choices
            if not prior_verified:
                continue
            if (numeric_value_digest(prior_value) == numeric_value_digest(raw_value)
                    and prior_authority.numeric_basis_digest(target_id) == basis):
                continue
        markers.append(numeric_authorization_record(
            character_slug=candidate_definition.character_slug,
            target_kind=kind, target_id=target_id, metric=metric,
            raw_value=raw_value, action_id=action_id, provenance="native_level_up",
        ))
        bases[target_id] = basis
    hp_target = "stats.max_hp"
    hp_basis = baseline.numeric_basis_digest(hp_target)
    prior_hp = (prior_authority.field_status("stats.max_hp").effective
                if isinstance(dict(prior_definition.source.get("native_progression") or {}).get("hp_recipe"), dict)
                else dict(prior_definition.stats or {}).get("max_hp"))
    candidate_hp = dict(candidate_definition.stats or {}).get("max_hp")
    prior_history = list(dict(dict(prior_definition.source or {}).get("native_progression") or {}).get("history") or [])
    candidate_history = list(dict(dict(candidate_definition.source or {}).get("native_progression") or {}).get("history") or [])
    new_event = candidate_history[-1] if len(candidate_history) == len(prior_history) + 1 else None
    if (hp_basis is not None and prior_authority.field_status(hp_target).is_effective
            and type(prior_hp) is int and type(candidate_hp) is int
            and candidate_history[:-1] == prior_history
            and isinstance(new_event, dict)
            and type(new_event.get("max_hp_delta")) is int
            and candidate_hp == prior_hp + new_event["max_hp_delta"]):
        markers.append(numeric_authorization_record(
            character_slug=candidate_definition.character_slug,
            target_kind="field", target_id=hp_target, metric="final",
            raw_value=candidate_hp, action_id=action_id, provenance="native_level_up",
        ))
        bases[hp_target] = hp_basis
    payload = candidate_definition.to_dict()
    for marker in markers:
        payload = add_numeric_authorization(payload, marker)
    marked_definition = CharacterDefinition.from_dict(payload)
    simulated = tuple(verified_numeric_actions) + tuple(
        {"authorization": marker, "source_basis_digest": bases[marker["target_id"]]}
        for marker in markers
    )
    return marked_definition, tuple(markers), bases, simulated, baseline.source_snapshot_digest, prospective_state


# Finite ordinary callback surface omitted by invocation-owned current inputs.
_CURRENT_INPUT_RECIPE = tuple((name, globals()[name]) for name in (
    'deepcopy',
    'AuthorityStatus',
    '_canonical',
    '_numeric_witness_identity',
    '_source_identity',
    '_current_systems_entry',
    'numeric_value_digest',
    'numeric_target_values',
    '_source_derived_hp_basis',
))
