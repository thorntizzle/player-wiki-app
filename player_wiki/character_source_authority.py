"""Read-only, exact-link authority for one reconciled DND character projection.

Historical definition rows are evidence of a selection, never evidence that the
selected source is still available.  This module deliberately has no database
access: the caller supplies independently verified manager audit witnesses.
"""

from __future__ import annotations

from copy import deepcopy
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


VERIFIED = "VERIFIED"
NEEDS_REPAIR = "NEEDS REPAIR"
NEEDS_ATTENTION = "NEEDS ATTENTION"
MANUAL = "MANUAL"
UNKNOWN = "UNKNOWN"
CONFLICT = "CONFLICT"
_METRICS = frozenset({"availability", "spell_attack_bonus", "spell_save_dc"})
_ITEM_EFFECT_FIELDS = frozenset({
    "ability_score_minimums", "attack_reminder_rules", "bonus", "bonus_ac",
    "bonus_attack_rolls", "bonus_damage_rolls", "bonus_weapon",
    "bonus_weapon_attack", "bonus_weapon_damage", "defensive_rules",
    "item_use_actions", "item_uses", "resource_template_bonuses",
    "spell_support", "spellcasting_modifiers", "campaign_option",
})
_FEATURE_EFFECT_FIELDS = frozenset({
    "campaign_option", "spell_manager", "spell_source_authorization",
    "additional_spells", "spell_support", "mechanic_effects", "modeled_effects",
})


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
) -> tuple[dict[str, Any] | None, str]:
    if source_kind.startswith("systems"):
        entry = _current_systems_entry(campaign_slug, source_kind, source_key, systems_service)
        if entry is None:
            return None, "source unavailable"
        if expected_slug and _text(getattr(entry, "slug", "")) != expected_slug:
            return None, "source identity changed"
        entry_type = _text(getattr(entry, "entry_type", ""))
        if kind == "item" and entry_type != "item":
            return None, "source kind changed"
        if kind == "spell" and entry_type != "spell":
            return None, "source kind changed"
        if kind == "class" and entry_type != "class":
            return None, "source kind changed"
        if kind == "feature" and entry_type not in {"feature", "feat", "optionalfeature", "classfeature", "subclassfeature"}:
            return None, "source kind changed"
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
    payload = definition.to_dict()
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
    for row in list(definition.resource_templates or []):
        if isinstance(row, dict) and _text(row.get("id")):
            values[("resource", f"resource:{_text(row['id'])}", "owner_reset")] = deepcopy(row)
    for row in list(state.get("spell_slots") or []):
        if isinstance(row, dict) and type(row.get("level")) is int and row["level"] > 0:
            stable_id = f"{_text(row.get('slot_lane_id'))}:{row['level']}"
            values[("resource", f"spell_slot:{stable_id}", "owner_reset")] = {
                "slot_lane_id": _text(row.get("slot_lane_id")),
                "level": row["level"], "max": row.get("max"),
            }
    for row in list(dict(state.get("hit_dice") or {}).get("pools") or []):
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
    if record.get("provenance") not in {"manager", "native_creation", "native_level_up", "native_spell_choice", "page_feature_update"}:
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

    @property
    def identity(self) -> str:
        return hashlib.sha256(_canonical({
            "definition": self.definition_digest,
            "state": self.state_digest,
            "state_revision": self.state_revision,
            "source_snapshot": self.source_snapshot_digest,
            "grants": [(grant.grant_id, grant.payload_json) for grant in self.grants],
            "statuses": [(row.kind, row.instance_id, row.status) for row in self.statuses],
            "manual_actions": self.verified_manual_actions,
            "numeric_actions": self.verified_numeric_actions,
            "active_items": sorted(self.active_item_ids),
            "fields": [(row.path, row.status, row.effective, row.reason) for row in self.field_statuses],
            "resources": [(row.path, row.status, row.effective, row.reason) for row in self.resource_statuses],
            "resource_bases": self.resource_basis_digests,
            "formula_rows": sorted(self.verified_formula_rows),
            "spell_grants": sorted(self.verified_spell_grants),
            "spell_choices": sorted(self.verified_spell_choices),
            "current_spell_keys": sorted(self.current_spell_keys),
        }).encode("utf-8")).hexdigest()

    def resource_basis_digest(self, target_id: str) -> str | None:
        return dict(self.resource_basis_digests).get(target_id)

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

    def bind_projected_numbers(self, definition: CharacterDefinition) -> SourceAuthority:
        """Bind formula results only after every required input has an owner."""
        stats = dict(definition.stats or {})
        abilities = dict(stats.get("ability_scores") or {})
        projected_inputs = dict(dict(stats.get("ability_inputs") or {}).get("scores") or {})
        field_rows = {row.path: row for row in self.field_statuses}
        for key, label in (("str", "strength"), ("dex", "dexterity"),
                           ("con", "constitution"), ("int", "intelligence"),
                           ("wis", "wisdom"), ("cha", "charisma")):
            ability = dict(abilities.get(key) or abilities.get(label) or {})
            score_path = f"stats.ability_scores.{key}.score"
            score_status = field_rows.get(score_path)
            score = ability.get("score")
            if (score_status is not None and score_status.reason == "baseline_authorized"
                    and score_status.status in {VERIFIED, MANUAL} and type(score) is int
                    and dict(projected_inputs.get(key) or {}).get("stage") in {"base", "pre_penalty"}):
                field_rows[score_path] = replace(score_status, effective=score)
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
        return replace(self, field_statuses=tuple(field_rows.values()))

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

    def suppress_unknown_numbers(self, definition: CharacterDefinition) -> CharacterDefinition:
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
        for row in [spellcasting, *list(spellcasting.get("class_rows") or []),
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
        for template in list(payload.get("resource_templates") or []):
            if not isinstance(template, dict):
                continue
            status = self.resource_status("resource", _text(template.get("id")))
            if not status.is_effective:
                template["authority_status"] = NEEDS_REPAIR
                for key in ("max", "initial_current", "reset_on", "reset_to"):
                    template[key] = None
        payload["spellcasting"] = spellcasting
        return CharacterDefinition.from_dict(payload)

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
                    "spell_support", "spellcasting_modifiers", "defensive_rules",
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

    def effective_definition(self, definition: CharacterDefinition) -> CharacterDefinition:
        """Replace historical effect copies with current approved payloads."""
        payload = deepcopy(definition.to_dict())
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
                if self.status_for(kind, instance_id) != VERIFIED:
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
                else:
                    if instance_id in self.inert_page_companions:
                        approved_rows.append(row)
                        continue
                    row.update(self.approved_payload(kind, instance_id))
                if kind == "feature":
                    saved_option = dict(next((original.get("campaign_option") for original in definition.features
                                              if isinstance(original, dict) and _text(original.get("id")) == instance_id), {}) or {})
                    current_option = row.get("campaign_option")
                    if isinstance(current_option, dict) and isinstance(saved_option.get("selected_choices"), dict):
                        current_option["selected_choices"] = deepcopy(saved_option["selected_choices"])
                approved_rows.append(row)
            payload[field] = approved_rows
        spellcasting = dict(payload.get("spellcasting") or {})
        for row in [spellcasting, *list(spellcasting.get("class_rows") or []),
                    *list(spellcasting.get("source_rows") or [])]:
            if not isinstance(row, dict):
                continue
            row_id = _text(row.get("source_row_id") or row.get("class_row_id"))
            if row is spellcasting and not row_id:
                class_rows = list(spellcasting.get("class_rows") or [])
                if len(class_rows) == 1 and isinstance(class_rows[0], dict):
                    row_id = _text(class_rows[0].get("class_row_id"))
            family = "source" if row.get("source_row_id") else "class"
            raw_provenance = row.get("spell_metric_provenance")
            provenance = dict(raw_provenance) if isinstance(raw_provenance, dict) else {}
            for metric in ("spell_attack_bonus", "spell_save_dc"):
                record = provenance.get(metric)
                if (isinstance(record, dict) and record.get("kind") == "formula"
                        and not self.formula_metric_verified(family, row_id, metric)):
                    provenance[metric] = {"kind": "manual_total"}
            if provenance:
                row["spell_metric_provenance"] = provenance
        clean_spells: list[dict[str, Any]] = []
        for raw in list(spellcasting.get("spells") or []):
            if not isinstance(raw, dict):
                continue
            spell = dict(raw)
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
        spell_id = _text(spell.get("id"))
        original_row_id = _text(spell.get("authority_original_source_row_id"))
        row_id = original_row_id or _text(spell.get("spell_source_row_id"))
        if row_id in self.disputed_source_rows:
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
        spells: list[dict[str, Any]] = []
        for raw in list(projected.get("spells") or []):
            if not isinstance(raw, dict):
                continue
            spell = dict(raw)
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
        return projected


def _source_row_ids(value: Any) -> set[str]:
    ids: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"spell_source_row_id", "source_row_id"} and isinstance(child, str) and child.strip():
                ids.add(child.strip())
            else:
                ids.update(_source_row_ids(child))
    elif isinstance(value, list):
        for child in value:
            ids.update(_source_row_ids(child))
    return ids


def _current_spell_grant_membership(
    grants: tuple[AuthorityGrant, ...], definition: CharacterDefinition,
) -> frozenset[tuple[str, str]]:
    """Exact fixed/explicit-option spell membership from current approved owners."""
    from .character_builder_spells import (
        _extract_spell_support_grants, _extract_spell_support_choice_specs_from_value,
        _spell_support_support_kwargs, _iter_unlocked_additional_spell_values,
    )
    from .character_campaign_options import collect_campaign_option_spell_grants

    level = sum(int(row.get("level") or 0) for row in profile_class_rows(definition.profile))
    owners = {"feature": {str(row.get("id") or ""): row for row in definition.features if isinstance(row, dict)},
              "item": {str(row.get("id") or ""): row for row in definition.equipment_catalog if isinstance(row, dict)}}
    found: set[tuple[str, str]] = set()
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
                    fixed = _extract_spell_support_grants([effect], target_level=max(level, 1))
                    raw_choices = _iter_unlocked_additional_spell_values(
                        effect.get("choices", effect.get("select")), target_level=max(level, 1))
                except (TypeError, ValueError):
                    continue
                for spell in fixed:
                    row_id = _text(spell.get("spell_source_row_id") or effect.get("spell_source_row_id"))
                    value = _text(spell.get("value")).casefold()
                    if row_id and value:
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
    return frozenset(found)


def _unambiguous_current_spell_keys(
    candidates: set[tuple[str, str, str]], entries: list[Any],
    pages: dict[str, list[Any]],
) -> frozenset[tuple[str, str]]:
    """Keep a grant key only when one current source owns that spelling."""
    key_owners: dict[str, set[str]] = {}
    for entry in entries:
        owner = f"systems:{_text(getattr(entry, 'entry_key', '')) or _text(getattr(entry, 'slug', ''))}"
        for name in (getattr(entry, "slug", ""), getattr(entry, "title", "")):
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


def _source_derived_spell_choice_bases(
    definition: CharacterDefinition, *, systems_service: Any,
    pages: dict[str, list[Any]], verified_class_rows: frozenset[str],
    source_snapshot_digest: str,
) -> dict[str, str]:
    """Current class/list membership for a separately witnessed native choice."""
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
    bases: dict[str, str] = {}
    for spell in spells:
        spell_id = _text(spell.get("id"))
        row_id = _text(spell.get("class_row_id"))
        class_row = class_rows.get(row_id)
        if (counts[spell_id] != 1 or class_row is None or _text(spell.get("spell_source_row_id"))):
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
        if not listed:
            continue
        basis = {
            "source_snapshot": source_snapshot_digest,
            "class_row": class_row, "class_source": class_meta,
            "spell_source": spell_meta, "spell_id": spell_id,
            "spell_source_key": spell_source_key, "spell_level": spell_level,
        }
        bases[f"spell_choice:{spell_id}"] = numeric_value_digest(basis)
    return bases


def _source_derived_resource_bases(
    definition: CharacterDefinition, *, systems_service: Any,
    pages: dict[str, list[Any]], verified_class_rows: frozenset[str],
    feature_statuses: tuple[AuthorityStatus, ...],
    field_statuses: tuple[EffectiveStatus, ...],
) -> dict[str, str]:
    """Prove exact current owner and formula inputs for durable resource witnesses.

    Only source shapes whose formula can be independently recomputed are
    included. A saved template or state row alone never supplies its owner.
    """
    from .character_feature_trackers import build_managed_resource_tracker_template
    from .managed_resource_registry import resolve_managed_resource_family_and_member
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
    input_scores = dict(dict(dict(definition.stats or {}).get("ability_inputs") or {}).get("scores") or {})
    effective_scores: dict[str, int] = {}
    for key in ("str", "dex", "con", "int", "wis", "cha"):
        status = next((row for row in field_statuses
                       if row.path == f"stats.ability_scores.{key}.score"), None)
        if status is None:
            continue
        if status.is_effective and type(status.effective) is int:
            effective_scores[key] = status.effective
        elif status.status in {VERIFIED, MANUAL} and status.reason == "baseline_authorized":
            score = dict(input_scores.get(key) or {}).get("score")
            if type(score) is int:
                effective_scores[key] = score
    bases: dict[str, str] = {}
    for template in definition.resource_templates:
        if not isinstance(template, dict):
            continue
        template_id = _text(template.get("id"))
        owners = [feature for feature in definition.features
                  if isinstance(feature, dict) and _text(feature.get("tracker_ref")) == template_id]
        if len(owners) != 1:
            continue
        feature = owners[0]
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
        )
        family, member = resolve_managed_resource_family_and_member(feature)
        slug = _text(dict(feature.get("systems_ref") or {}).get("slug"))
        if (current is None or reason or not family or not member or not slug
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
        level = class_by_id[row_id].get("level")
        if type(level) is not int or level < 1:
            continue
        expected = build_managed_resource_tracker_template(
            member, feature, ability_scores=effective_scores,
            current_level=level, display_order=int(template.get("display_order") or 0),
        )
        if expected is None or _text(expected.get("id")) != template_id:
            continue
        expected.pop("activation_type", None)
        expected["class_row_id"] = row_id
        if any(template.get(key) != value for key, value in expected.items()):
            continue
        bases[f"resource:{template_id}"] = numeric_value_digest({
            "owner": _source_identity(feature), "source": current,
            "class": class_by_id[row_id], "formula": formula,
            "inputs": {key: effective_scores[key] for key in sorted(required_abilities(formula))},
            "template": expected,
        })
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
            if row.get("subclass_ref"):
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
            expected = _spell_slot_progression_for_class_level(
                class_name, level, selected_class=entry,
            )
            actual = list(lane.get("slot_progression") or [])
            if _canonical(expected) != _canonical(actual):
                continue
            for slot in expected:
                slot_level = slot.get("level")
                if type(slot_level) is not int or slot_level < 1:
                    continue
                bases[f"spell_slot:{lane_id}:{slot_level}"] = numeric_value_digest({
                    "owner": row, "source": current, "lane": lane_id,
                    "level": slot_level, "max": slot.get("max_slots"),
                })
    return bases


def _source_derived_hp_basis(
    definition: CharacterDefinition, *, systems_service: Any,
    pages: dict[str, list[Any]], verified_class_rows: frozenset[str],
    feature_statuses: tuple[AuthorityStatus, ...],
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
    for feature in definition.features:
        if not isinstance(feature, dict) or statuses.get(_text(feature.get("id"))) != VERIFIED:
            return None
        source_kind, source_key = _source_identity(feature)
        current, reason = _current_payload(
            campaign_slug=definition.campaign_slug, kind="feature",
            source_kind=source_kind, source_key=source_key,
            systems_service=systems_service, pages=pages,
            expected_slug=_text(dict(feature.get("systems_ref") or {}).get("slug")),
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
        if row_id not in verified_class_rows or profile is None or profile.get("subclass_ref"):
            continue
        source_kind, source_key = _source_identity(profile)
        entry = _current_systems_entry(definition.campaign_slug, source_kind, source_key, systems_service)
        if entry is None or _text(getattr(entry, "entry_type", "")) != "class":
            continue
        if type(profile.get("level")) is not int or profile["level"] < 1:
            continue
        expected_ability = _spellcasting_ability_name_for_class(
            _text(getattr(entry, "title", "")), selected_class=entry,
            row_level=profile["level"],
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
            bases[target_id] = numeric_value_digest({
                "source_snapshot": source_snapshot_digest,
                "class_source": {"entry_key": source_key, "metadata": getattr(entry, "metadata", None)},
                "class_row": profile, "ability": ability_key,
                "score": abilities[ability_key]["score"], "pb": pb,
                "metric": metric, "expected": expected,
            })
    source_proofs: dict[str, list[tuple[str, AuthorityGrant]]] = {}
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
        visit(json.loads(grant.payload_json), grant)
    source_rows = list(dict(definition.spellcasting or {}).get("source_rows") or [])
    source_ids = [_text(row.get("source_row_id")) for row in source_rows if isinstance(row, dict)]
    if len(source_rows) != len(source_ids) or len(source_ids) != len(set(source_ids)):
        return bases
    for spell_row in source_rows:
        row_id = _text(spell_row.get("source_row_id"))
        proofs = list({(ability, grant.grant_id): (ability, grant)
                       for ability, grant in source_proofs.get(row_id) or []}.values())
        if row_id not in verified_source_rows or len(proofs) != 1:
            continue
        ability_key, grant = proofs[0]
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
            bases[target_id] = numeric_value_digest({
                "source_snapshot": source_snapshot_digest,
                "grant": (grant.grant_id, grant.payload_json),
                "ability": ability_key, "score": score, "pb": pb,
                "metric": metric, "expected": expected,
            })
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
        result[f"resource:{tracker_id}"] = numeric_value_digest({
            "source_snapshot": source_snapshot_digest,
            "page_ref": page_ref, "page_revision": revision,
            "feature_id": feature_id, "feature": feature,
            "template": template, "approved_option": option,
        })
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
                   verified_numeric_actions=tuple(_canonical(row) for row in trusted))


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

    def decide(path: str, kind: str, metric: str, raw: Any, reason: str) -> EffectiveStatus:
        matches = [record for record in markers if isinstance(record, dict)
                   and record.get("target_kind") == kind
                   and record.get("target_id") == path
                   and record.get("metric") == metric]
        if len(matches) > 1:
            return EffectiveStatus(path, CONFLICT, deepcopy(raw), None,
                                   "authorization_conflict")
        trusted_witnesses = verified_actions
        if (len(matches) == 1 and (kind == "resource" or (kind == "field" and path == "stats.max_hp"))
                and matches[0].get("provenance") in {"native_level_up", "native_creation", "page_feature_update"}):
            basis = resource_bases.get(path)
            trusted_witnesses = tuple(
                witness.get("authorization") for witness in verified_actions
                if isinstance(witness, dict) and witness.get("source_basis_digest") == basis
                and basis is not None
                and _transition_matches(witness, kind, path, metric,
                                        target_values.get((kind, path, metric)),
                                        numeric_target_owner_digest(
                                            definition, state, kind, path, metric),
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
            owner_digest=numeric_target_owner_digest(definition, state, kind, path, metric),
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
    for slot in list(state.get("spell_slots") or []):
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
    for pool in list(dict(state.get("hit_dice") or {}).get("pools") or []):
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
    inventory_ids = [_text(item.get("id")) for item in list(state.get("inventory") or [])
                     if isinstance(item, dict)]
    for item in list(state.get("inventory") or []):
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
    return (proof.get("schema_version") == 1
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
) -> SourceAuthority:
    """Classify the exact current links in a previously reconciled definition."""
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
    inert_page_companions: set[str] = set()
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
            current, reason = _current_payload(
                campaign_slug=definition.campaign_slug, kind=kind,
                source_kind=source_kind, source_key=source_key,
                systems_service=systems_service, pages=pages,
                expected_slug=_text(dict(raw.get("systems_ref") or {}).get("slug")),
            )
            active = kind != "item" or (bool(raw.get("is_equipped")) and not raw.get("mechanics_suppressed"))
            if current is not None and kind == "item":
                attunement = _text(current.get("attunement")).casefold()
                if ("requires attunement" in attunement or current.get("requires_attunement") is True) and not raw.get("is_attuned"):
                    active = False
            if current is None or reason:
                statuses.append(AuthorityStatus(kind, instance_id, NEEDS_REPAIR, reason or "source unavailable"))
                warnings.append(("source_needs_repair", f"{kind.title()} {instance_id} needs source repair."))
                continue
            statuses.append(AuthorityStatus(kind, instance_id, VERIFIED, ""))
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
            if not active:
                continue
            if kind == "item":
                active_item_ids.add(instance_id)
            relevant = _ITEM_EFFECT_FIELDS if kind == "item" else _FEATURE_EFFECT_FIELDS
            for field in sorted(relevant & current.keys()):
                value = current[field]
                if value in (None, "", [], {}):
                    continue
                effects = list(value) if isinstance(value, list) else [value]
                for effect_index, effect in enumerate(effects):
                    effect_id = _text(effect.get("effect_id")) if isinstance(effect, dict) else ""
                    effect_id = f"{field}:{effect_id or effect_index}"
                    grants.append(AuthorityGrant(kind, instance_id, source_kind, source_key, effect_id, _canonical({field: effect})))
    spell_counts: dict[str, int] = {}
    current_spell_keys: set[tuple[str, str]] = set()
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
                owner = (f"systems:{_text(getattr(entry, 'entry_key', '')) or _text(getattr(entry, 'slug', ''))}"
                         if entry is not None else "")
            else:
                matches = pages.get(source_key) or []
                page = _field(matches[0], "page") if len(matches) == 1 else None
                names = (source_key, _field(page, "title")) if page is not None else ()
                owner = f"page:{source_key}"
            spell_key_candidates.update((spell_id, _text(name).casefold(), owner)
                                        for name in names if _text(name) and owner)
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
    verified_spell_grants = _current_spell_grant_membership(clean_grants, definition)
    # Grant values may be display names. Resolve them against the current
    # catalog and reject a title/slug alias shared by two eligible spells.
    list_spells = getattr(systems_service, "list_enabled_entries_for_campaign", None)
    entries = list_spells(definition.campaign_slug, entry_type="spell") if callable(list_spells) else []
    current_spell_keys.update(_unambiguous_current_spell_keys(spell_key_candidates, entries, pages))
    source_owners: dict[str, set[tuple[str, str, str]]] = {}
    for grant in clean_grants:
        for row_id in _source_row_ids(json.loads(grant.payload_json)):
            source_owners.setdefault(row_id, set()).add((grant.kind, grant.source_key, grant.instance_id))
    disputed_rows = frozenset(row_id for row_id, owners in source_owners.items() if len(owners) > 1)
    for row_id in disputed_rows:
        statuses.append(AuthorityStatus("source_row", row_id, NEEDS_ATTENTION, "conflicting current owners"))
        warnings.append(("source_row_collision", "Conflicting spell source rows need manager attention."))
    verified_source_rows = frozenset(source_owners.keys() - disputed_rows)
    witnesses = tuple(_canonical(witness) for witness in verified_manual_actions if isinstance(witness, dict))
    preliminary_fields, _ = _numeric_statuses(
        definition, state, verified_numeric_actions,
    )
    resource_bases = _source_derived_resource_bases(
        definition, systems_service=systems_service, pages=pages,
        verified_class_rows=frozenset(verified_class_rows),
        feature_statuses=tuple(statuses), field_statuses=preliminary_fields,
    )
    resource_bases.update(_page_feature_resource_bases(
        definition, pages=pages, feature_statuses=tuple(statuses),
        source_snapshot_digest=source_snapshot_digest,
    ))
    hp_basis = _source_derived_hp_basis(
        definition, systems_service=systems_service, pages=pages,
        verified_class_rows=frozenset(verified_class_rows),
        feature_statuses=tuple(statuses),
    )
    if hp_basis is not None:
        resource_bases["stats.max_hp"] = hp_basis
    resource_bases.update(_source_derived_formula_bases(
        definition, systems_service=systems_service,
        verified_class_rows=frozenset(verified_class_rows),
        verified_source_rows=verified_source_rows, grants=clean_grants,
        source_snapshot_digest=source_snapshot_digest,
    ))
    resource_bases.update(_source_derived_spell_choice_bases(
        definition, systems_service=systems_service, pages=pages,
        verified_class_rows=frozenset(verified_class_rows),
        source_snapshot_digest=source_snapshot_digest,
    ))
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
    formula_targets: set[str] = set()
    spell_choice_targets: set[str] = set()
    marker_rows = list(dict(definition.source or {}).get("source_authorizations") or [])
    values = numeric_target_values(definition, state)
    for (kind, target_id, metric), raw_value in values.items():
        if kind not in {"spell_metric", "spell_choice"} or target_id not in resource_bases:
            continue
        matches = [marker for marker in marker_rows if isinstance(marker, dict)
                   and marker.get("target_kind") == kind
                   and marker.get("target_id") == target_id
                   and marker.get("metric") == metric]
        if len(matches) != 1:
            continue
        basis = resource_bases[target_id]
        trusted = tuple(witness.get("authorization") for witness in verified_numeric_actions
                        if isinstance(witness, dict) and witness.get("source_basis_digest") == basis
                        and _transition_matches(witness, kind, target_id, metric,
                            raw_value, numeric_target_owner_digest(
                                definition, state, kind, target_id, metric),
                            source_snapshot_digest))
        if valid_numeric_authorization(
            matches[0], character_slug=definition.character_slug,
            target_kind=kind, target_id=target_id, metric=metric,
            raw_value=raw_value, verified_actions=trusted,
        ):
            if kind == "spell_metric":
                formula_targets.add(target_id)
            else:
                spell_choice_targets.add(target_id.removeprefix("spell_choice:"))
    return SourceAuthority(digest, hashlib.sha256(_canonical(state).encode("utf-8")).hexdigest(),
                           state_revision, clean_grants, tuple(statuses), tuple(warnings), witnesses,
                           frozenset(verified_class_rows), verified_source_rows, disputed_rows,
                           field_statuses, resource_statuses,
                           tuple(_canonical(witness) for witness in verified_numeric_actions
                                 if isinstance(witness, dict)), frozenset(active_item_ids),
                           source_snapshot_digest, tuple(sorted(resource_bases.items())),
                           frozenset(formula_targets), verified_spell_grants,
                           frozenset(spell_choice_targets), frozenset(current_spell_keys),
                           frozenset(inert_page_companions))


def build_reconciled_source_authority(
    *, definition: CharacterDefinition, state: dict[str, Any],
    state_revision: int, systems_service: Any,
    campaign_page_records: list[Any] | None,
    verified_manual_actions: tuple[Any, ...] = (),
    verified_numeric_actions: tuple[Any, ...] = (),
) -> SourceAuthority:
    """Pure writer/read entry point after revisioned SQLite activation wins."""
    from .character_equipment_activation import effective_definition

    reconciled, _warnings = effective_definition(definition, state)
    return build_source_authority(
        definition=reconciled, state=state, state_revision=state_revision,
        systems_service=systems_service,
        campaign_page_records=campaign_page_records,
        verified_manual_actions=verified_manual_actions,
        verified_numeric_actions=verified_numeric_actions,
    )


def prepare_native_spell_choice_authorizations(
    *, prior_definition: CharacterDefinition, candidate_definition: CharacterDefinition,
    state: dict[str, Any], state_revision: int, systems_service: Any,
    campaign_page_records: list[Any] | None,
) -> tuple[CharacterDefinition, tuple[dict[str, Any], ...], dict[str, str], str]:
    """Mark changed choices from the guarded spell editor for postwrite audit."""
    from .character_source_repair import numeric_authorization_record, add_numeric_authorization

    authority = build_reconciled_source_authority(
        definition=candidate_definition, state=state, state_revision=state_revision,
        systems_service=systems_service, campaign_page_records=campaign_page_records,
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
    return CharacterDefinition.from_dict(payload), tuple(markers), bases, authority.source_snapshot_digest


def prepare_native_level_up_resource_authorizations(
    *, prior_definition: CharacterDefinition, candidate_definition: CharacterDefinition,
    prior_state: dict[str, Any], state_revision: int, systems_service: Any,
    campaign_page_records: list[Any] | None,
    verified_manual_actions: tuple[Any, ...] = (),
    verified_numeric_actions: tuple[Any, ...] = (),
) -> tuple[CharacterDefinition, tuple[dict[str, Any], ...], dict[str, str], tuple[Any, ...], str, dict[str, Any]]:
    """Pre-mark exact new or previously owned source-derived resource maxima.

    The returned simulated witnesses permit the pending merge. They are never
    durable authority: the caller must audit a confirmed publication readback.
    """
    from .character_source_repair import numeric_authorization_record, add_numeric_authorization
    from .character_hit_dice import derive_hit_dice_max_pools
    from .character_spell_slots import spell_slot_lanes_from_spellcasting
    prospective_state = deepcopy(prior_state)
    prior_values = numeric_target_values(prior_definition, prior_state)
    prior_authority = build_reconciled_source_authority(
        definition=prior_definition, state=prior_state,
        state_revision=state_revision, systems_service=systems_service,
        campaign_page_records=campaign_page_records,
        verified_manual_actions=verified_manual_actions,
        verified_numeric_actions=verified_numeric_actions,
    )
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
    candidate_ids = [target_id for kind, target_id, metric in values
                     if kind == "resource" and metric == "owner_reset"]
    action_id = uuid4().hex
    markers: list[dict[str, Any]] = []
    bases: dict[str, str] = {}
    for target_id in candidate_ids:
        if not target_id or candidate_ids.count(target_id) != 1:
            continue
        basis = baseline.resource_basis_digest(target_id)
        raw_value = values.get(("resource", target_id, "owner_reset"))
        if basis is None or raw_value is None:
            continue
        prior_value = prior_values.get(("resource", target_id, "owner_reset"))
        if prior_value is not None:
            if numeric_value_digest(prior_value) == numeric_value_digest(raw_value):
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
        if kind not in {"spell_metric", "spell_choice"}:
            continue
        basis = baseline.numeric_basis_digest(target_id)
        if basis is None or (kind == "spell_metric" and raw_value.get("value") is None):
            continue
        prior_value = prior_values.get((kind, target_id, metric))
        if prior_value is not None:
            prior_verified = (target_id in prior_authority.verified_formula_rows if kind == "spell_metric"
                              else target_id.removeprefix("spell_choice:") in prior_authority.verified_spell_choices)
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
    prior_hp = dict(prior_definition.stats or {}).get("max_hp")
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
