"""Request-local adapters for bounded DND-5E character update planning.

Preparation is the only phase that inspects campaign-page and Systems source
foundations or asks the caller for access decisions.  The callbacks returned to
``character_update_planner`` close over copied, canonical data and never consult
Flask, persistence, repositories, services, clocks, random values, or caches
outside the request.

The native normalizer and state merger are injected deliberately.  Production
callers bind the existing Character owners to already-prepared request-local
catalogs; tests can supply small pure equivalents.  Both callables must be pure
for the lifetime of the returned adapter bundle.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
import html
import json
import re
from typing import Any, Callable, Mapping, Protocol, Sequence, TypeAlias

from .character_builder_features import (
    _campaign_option_resource_payloads,
    _resolve_campaign_option_resource_max,
)
from .character_builder_static_bundle import (
    _campaign_page_option_allowed_for_linked_field,
)
from .character_campaign_options import build_campaign_page_character_option
from .character_update_planner import (
    CampaignEquipmentAdd,
    CampaignFeatureGrant,
    ChangeKind,
    CharacterSnapshot,
    DerivationResult,
    EquipmentSafeRelink,
    ExistingEquipment,
    ExistingFeature,
    OperationKind,
    ResourceAddition,
    SemanticCategory,
    SemanticDiffRow,
    SemanticProjection,
    SourceAttestation,
    SourceIdentity,
    SourceKind,
    StateImpact,
    StateImpactProjection,
    StateReconciliation,
    SystemsItemAdd,
    UpdateOperation,
    operation_id,
)


MAX_OPERATIONS = 128
MAX_SUMMARY_LENGTH = 512
SUPPORTED_SYSTEM = "DND-5E"
_CUSTOM_EQUIPMENT_SOURCE_KIND = "manual_edit"
_CAMPAIGN_FEATURE_CATEGORY = "custom_feature"
_CAMPAIGN_SOURCE_LABEL = "Campaign"


class AdapterPreparationError(ValueError):
    """The request-local adapter foundation is malformed."""


@dataclass(frozen=True, slots=True)
class SourceAccessDecision:
    """Injected current-policy result for one exact source identity."""

    visible: bool = True
    enabled: bool = True
    approved: bool = True

    @property
    def allowed(self) -> bool:
        return self.visible and self.enabled and self.approved


@dataclass(frozen=True, slots=True)
class CampaignFeatureGrantIntent:
    page_ref: str
    feature_id: str
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CampaignEquipmentAddIntent:
    page_ref: str
    equipment_id: str
    quantity: int | None = None
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SystemsItemAddIntent:
    entry_key: str
    equipment_id: str
    quantity: int = 1
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EquipmentSafeRelinkIntent:
    equipment_id: str
    target_source: SourceIdentity
    dependencies: tuple[str, ...] = ()


CharacterUpdateIntent: TypeAlias = (
    CampaignFeatureGrantIntent
    | CampaignEquipmentAddIntent
    | SystemsItemAddIntent
    | EquipmentSafeRelinkIntent
)


class NativeDefinitionNormalizer(Protocol):
    def __call__(self, definition: Mapping[str, Any]) -> Mapping[str, Any]: ...


class CharacterStateMerger(Protocol):
    def __call__(
        self,
        definition: Mapping[str, Any],
        state: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


SourceAccessResolver = Callable[[SourceIdentity], SourceAccessDecision]


@dataclass(frozen=True, slots=True)
class PreparedCharacterUpdateAdapters:
    """Canonical planner inputs plus request-local pure callbacks."""

    snapshot: CharacterSnapshot
    operations: tuple[UpdateOperation, ...]
    adapter: Callable[[Mapping[str, Any], UpdateOperation], Mapping[str, Any]]
    derive: Callable[[Mapping[str, Any], Mapping[str, Any]], DerivationResult]
    project_state_impact: Callable[
        [Mapping[str, Any], Mapping[str, Any], tuple[UpdateOperation, ...]],
        StateImpactProjection,
    ]
    project_semantics: Callable[
        [Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]],
        SemanticProjection,
    ]

    def planner_kwargs(self) -> dict[str, object]:
        return {
            "adapter": self.adapter,
            "derive": self.derive,
            "project_state_impact": self.project_state_impact,
            "project_semantics": self.project_semantics,
        }


@dataclass(frozen=True, slots=True)
class _ResolvedCampaignPage:
    page_ref: str
    title: str
    option: Mapping[str, Any]
    policy_allowed: bool
    ambiguous: bool
    choice_bearing: bool


@dataclass(frozen=True, slots=True)
class _ResolvedSystemsItem:
    entry_key: str
    title: str
    systems_ref: Mapping[str, str]
    metadata: Mapping[str, Any]
    policy_allowed: bool
    ambiguous: bool


@dataclass(frozen=True, slots=True)
class _SemanticCell:
    category: SemanticCategory
    identity: str
    label: str
    summary: str


@dataclass(frozen=True, slots=True)
class _SemanticSurface:
    cells: tuple[_SemanticCell, ...]
    warnings: tuple[str, ...]


class _SourceResolutionKind(str, Enum):
    FEATURE = "feature"
    ITEM = "item"


def prepare_character_update_adapters(
    *,
    target_identity: str,
    baseline_identity: str,
    definition: Mapping[str, Any],
    state: Mapping[str, Any],
    intents: Sequence[CharacterUpdateIntent],
    campaign_page_records: Sequence[Any],
    systems_entries: Sequence[Any],
    resolve_access: SourceAccessResolver,
    normalize_definition: NativeDefinitionNormalizer,
    merge_state: CharacterStateMerger,
) -> PreparedCharacterUpdateAdapters:
    """Prepare one bounded Character planner request.

    Exact page refs and entry keys are indexed once.  ``resolve_access`` is
    called once for each unique identity named by the request.  All source
    records, access decisions, canonical operation payloads, and the baseline
    semantic surface are materialized before the callbacks are returned.
    """

    clean_target_identity = _required_text(target_identity, "target_identity")
    clean_baseline_identity = _required_text(baseline_identity, "baseline_identity")
    local_definition = _copy_mapping(definition, "definition")
    local_state = _copy_mapping(state, "state")
    local_intents = tuple(deepcopy(tuple(intents)))
    if not local_intents or len(local_intents) > MAX_OPERATIONS:
        raise AdapterPreparationError("intent count must be between 1 and 128")
    if not callable(resolve_access):
        raise AdapterPreparationError("resolve_access must be callable")
    if not callable(normalize_definition) or not callable(merge_state):
        raise AdapterPreparationError(
            "normalize_definition and merge_state must be pure callables"
        )

    page_index = _exact_index(campaign_page_records, _campaign_page_ref)
    systems_index = _exact_index(systems_entries, _systems_entry_key)
    access_cache: dict[tuple[SourceKind, str], SourceAccessDecision] = {}
    page_cache: dict[tuple[str, _SourceResolutionKind], _ResolvedCampaignPage] = {}
    systems_cache: dict[str, _ResolvedSystemsItem] = {}

    def access_for(source: SourceIdentity) -> SourceAccessDecision:
        kind = _source_kind(source)
        value = _required_text(source.value, "source identity")
        key = (kind, value)
        if key not in access_cache:
            decision = resolve_access(SourceIdentity(kind, value))
            if not isinstance(decision, SourceAccessDecision):
                raise AdapterPreparationError(
                    "resolve_access must return SourceAccessDecision"
                )
            access_cache[key] = deepcopy(decision)
        return access_cache[key]

    def resolve_page(
        page_ref: str,
        resolution_kind: _SourceResolutionKind,
    ) -> _ResolvedCampaignPage:
        clean_page_ref = _required_text(page_ref, "page_ref")
        cache_key = (clean_page_ref, resolution_kind)
        if cache_key in page_cache:
            return page_cache[cache_key]
        records = page_index.get(clean_page_ref, ())
        ambiguous = len(records) != 1
        record = records[0] if len(records) == 1 else None
        field_kind = (
            "campaign_page_feature"
            if resolution_kind is _SourceResolutionKind.FEATURE
            else "campaign_page_item"
        )
        option: dict[str, Any] = {}
        title = "Campaign source"
        native_policy_allowed = False
        if record is not None:
            page = getattr(record, "page", None)
            title = str(getattr(page, "title", "") or "").strip() or title
            section = str(getattr(page, "section", "") or "").strip()
            option = dict(
                build_campaign_page_character_option(
                    record,
                    default_kind="item" if section == "Items" else "feature",
                )
                or {}
            )
            native_policy_allowed = _campaign_page_option_allowed_for_linked_field(
                record,
                field_kind=field_kind,
                campaign_option=option,
            )
        access = access_for(SourceIdentity(SourceKind.CAMPAIGN_PAGE, clean_page_ref))
        resolved = _ResolvedCampaignPage(
            clean_page_ref,
            title,
            deepcopy(option),
            bool(record is not None and native_policy_allowed and access.allowed),
            ambiguous,
            _campaign_option_is_choice_bearing(option),
        )
        page_cache[cache_key] = resolved
        return resolved

    def resolve_systems(entry_key: str) -> _ResolvedSystemsItem:
        clean_entry_key = _required_text(entry_key, "entry_key")
        if clean_entry_key in systems_cache:
            return systems_cache[clean_entry_key]
        entries = systems_index.get(clean_entry_key, ())
        ambiguous = len(entries) != 1
        entry = entries[0] if len(entries) == 1 else None
        title = "Systems item"
        metadata: dict[str, Any] = {}
        systems_ref: dict[str, str] = {}
        is_item = False
        if entry is not None:
            title = str(getattr(entry, "title", "") or "").strip() or title
            entry_type = str(getattr(entry, "entry_type", "") or "").strip()
            is_item = entry_type.casefold() == "item"
            metadata = deepcopy(dict(getattr(entry, "metadata", {}) or {}))
            systems_ref = {
                "entry_key": clean_entry_key,
                "entry_type": entry_type,
                "title": title,
                "slug": str(getattr(entry, "slug", "") or "").strip(),
                "source_id": str(getattr(entry, "source_id", "") or "").strip(),
            }
        access = access_for(SourceIdentity(SourceKind.SYSTEMS_ENTRY, clean_entry_key))
        resolved = _ResolvedSystemsItem(
            clean_entry_key,
            title,
            systems_ref,
            metadata,
            bool(entry is not None and is_item and access.allowed),
            ambiguous,
        )
        systems_cache[clean_entry_key] = resolved
        return resolved

    feature_rows = _mapping_rows(local_definition, "features")
    equipment_rows = _mapping_rows(local_definition, "equipment_catalog")
    state_resource_rows = _mapping_rows(local_state, "resources")
    state_inventory_rows = _mapping_rows(local_state, "inventory")
    inventory_by_identity = _inventory_index(state_inventory_rows)
    current_level = _definition_total_level(local_definition)

    operations: list[UpdateOperation] = []
    for intent in local_intents:
        dependencies = _dependencies(intent)
        if isinstance(intent, CampaignFeatureGrantIntent):
            feature_id = _required_text(intent.feature_id, "feature_id")
            source = resolve_page(intent.page_ref, _SourceResolutionKind.FEATURE)
            option = dict(source.option)
            definition_row = _campaign_feature_definition(
                feature_id=feature_id,
                source=source,
            )
            resources = _campaign_feature_resource_additions(
                feature_id=feature_id,
                option=option,
                current_level=current_level,
            )
            attestation = SourceAttestation(
                policy_allowed=source.policy_allowed,
                ambiguous=source.ambiguous,
                choice_bearing=source.choice_bearing,
            )
            operations.append(
                UpdateOperation(
                    OperationKind.CAMPAIGN_FEATURE_GRANT,
                    CampaignFeatureGrant(
                        source.page_ref,
                        feature_id,
                        definition_row,
                        _clean_human_text(source.title, fallback="Campaign feature"),
                        resources,
                        attestation,
                    ),
                    dependencies,
                )
            )
            continue

        if isinstance(intent, CampaignEquipmentAddIntent):
            equipment_id = _required_text(intent.equipment_id, "equipment_id")
            source = resolve_page(intent.page_ref, _SourceResolutionKind.ITEM)
            quantity = _campaign_item_quantity(source.option, intent.quantity)
            definition_row = _campaign_equipment_definition(
                equipment_id=equipment_id,
                quantity=quantity,
                source=source,
            )
            inventory_row = _inventory_row_for_definition(definition_row, quantity)
            attestation = SourceAttestation(
                policy_allowed=source.policy_allowed,
                ambiguous=source.ambiguous,
                choice_bearing=source.choice_bearing,
            )
            operations.append(
                UpdateOperation(
                    OperationKind.CAMPAIGN_EQUIPMENT_ADD,
                    CampaignEquipmentAdd(
                        source.page_ref,
                        equipment_id,
                        definition_row,
                        inventory_row,
                        quantity,
                        _clean_human_text(source.title, fallback="Campaign item"),
                        attestation,
                    ),
                    dependencies,
                )
            )
            continue

        if isinstance(intent, SystemsItemAddIntent):
            equipment_id = _required_text(intent.equipment_id, "equipment_id")
            quantity = _positive_integer(intent.quantity, "quantity")
            source = resolve_systems(intent.entry_key)
            definition_row = _systems_equipment_definition(
                equipment_id=equipment_id,
                quantity=quantity,
                source=source,
            )
            inventory_row = _inventory_row_for_definition(definition_row, quantity)
            attestation = SourceAttestation(
                policy_allowed=source.policy_allowed,
                ambiguous=source.ambiguous,
                choice_bearing=False,
            )
            operations.append(
                UpdateOperation(
                    OperationKind.SYSTEMS_ITEM_ADD,
                    SystemsItemAdd(
                        source.entry_key,
                        equipment_id,
                        definition_row,
                        inventory_row,
                        quantity,
                        _clean_human_text(source.title, fallback="Systems item"),
                        attestation,
                    ),
                    dependencies,
                )
            )
            continue

        if isinstance(intent, EquipmentSafeRelinkIntent):
            equipment_id = _required_text(intent.equipment_id, "equipment_id")
            target_kind = _source_kind(intent.target_source)
            target_value = _required_text(intent.target_source.value, "target source")
            source_identity = SourceIdentity(target_kind, target_value)
            matches = [
                row
                for row in equipment_rows
                if str(row.get("id") or "").strip() == equipment_id
            ]
            existing_definition = deepcopy(matches[0]) if len(matches) == 1 else {}
            inventory_matches = inventory_by_identity.get(equipment_id, ())
            inventory_before = (
                deepcopy(inventory_matches[0]) if len(inventory_matches) == 1 else {}
            )
            source_policy_allowed = False
            source_ambiguous = len(matches) != 1 or len(inventory_matches) != 1
            choice_bearing = False
            if target_kind is SourceKind.CAMPAIGN_PAGE:
                source = resolve_page(target_value, _SourceResolutionKind.ITEM)
                source_policy_allowed = source.policy_allowed
                source_ambiguous = source_ambiguous or source.ambiguous
                choice_bearing = source.choice_bearing
                relinked_definition = _relink_campaign_equipment(existing_definition, source)
                label = source.title
            else:
                systems_source = resolve_systems(target_value)
                source_policy_allowed = systems_source.policy_allowed
                source_ambiguous = source_ambiguous or systems_source.ambiguous
                relinked_definition = _relink_systems_equipment(
                    existing_definition,
                    systems_source,
                )
                label = systems_source.title
            operations.append(
                UpdateOperation(
                    OperationKind.EQUIPMENT_SAFE_RELINK,
                    EquipmentSafeRelink(
                        equipment_id,
                        source_identity,
                        relinked_definition,
                        inventory_before,
                        deepcopy(inventory_before),
                        _clean_human_text(label, fallback="Equipment source"),
                        SourceAttestation(
                            policy_allowed=source_policy_allowed,
                            ambiguous=source_ambiguous,
                            choice_bearing=choice_bearing,
                        ),
                    ),
                    dependencies,
                )
            )
            continue

        raise AdapterPreparationError(
            f"unsupported intent type: {type(intent).__name__}"
        )

    canonical_operations = tuple(deepcopy(operations))
    campaign_relink_options_by_operation_id: dict[str, Any] = {}
    for operation in canonical_operations:
        payload = operation.payload
        if not isinstance(payload, EquipmentSafeRelink):
            continue
        if _source_kind(payload.target_source) is not SourceKind.CAMPAIGN_PAGE:
            continue
        definition_payload = dict(payload.definition)
        if "campaign_option" in definition_payload:
            campaign_relink_options_by_operation_id[operation_id(operation)] = deepcopy(
                definition_payload["campaign_option"]
            )
    snapshot = _build_snapshot(
        target_identity=clean_target_identity,
        baseline_identity=clean_baseline_identity,
        definition=local_definition,
        state=local_state,
        feature_rows=feature_rows,
        equipment_rows=equipment_rows,
        state_resource_rows=state_resource_rows,
        inventory_by_identity=inventory_by_identity,
    )
    baseline_surface = _semantic_surface(local_definition, local_state)

    def adapter(
        candidate_definition: Mapping[str, Any],
        operation: UpdateOperation,
    ) -> Mapping[str, Any]:
        return _adapt_operation(
            candidate_definition,
            operation,
            campaign_relink_options_by_operation_id,
        )

    def derive(
        candidate_definition: Mapping[str, Any],
        baseline_state: Mapping[str, Any],
    ) -> DerivationResult:
        candidate = _copy_mapping(candidate_definition, "candidate definition")
        state_copy = _copy_mapping(baseline_state, "baseline state")
        normalized = _copy_mapping(
            normalize_definition(deepcopy(candidate)),
            "normalized definition",
        )
        merged_state = _copy_mapping(
            merge_state(deepcopy(normalized), deepcopy(state_copy)),
            "merged state",
        )
        warnings = _definition_derivation_hazards(
            candidate,
            normalized,
            canonical_operations,
        )
        return DerivationResult(
            {
                "definition": normalized,
                "state": merged_state,
            },
            warnings,
        )

    state_projection_cache: dict[str, StateImpactProjection] = {}

    def project_state_impact(
        baseline_state: Mapping[str, Any],
        derived_character: Mapping[str, Any],
        ready_operations: tuple[UpdateOperation, ...],
    ) -> StateImpactProjection:
        key = _canonical_json(
            {
                "baseline_state": baseline_state,
                "derived_character": derived_character,
                "operations": ready_operations,
            }
        )
        cached = state_projection_cache.get(key)
        if cached is None:
            cached = _project_state_impact(
                baseline_state,
                derived_character,
                ready_operations,
            )
            state_projection_cache[key] = cached
        return deepcopy(cached)

    def project_semantics(
        baseline_definition: Mapping[str, Any],
        derived_character: Mapping[str, Any],
        baseline_state: Mapping[str, Any],
    ) -> SemanticProjection:
        if not _same(baseline_definition, local_definition) or not _same(
            baseline_state,
            local_state,
        ):
            return SemanticProjection(
                (),
                ("Semantic projection received a different baseline foundation.",),
            )
        derived_bundle = _copy_mapping(derived_character, "derived character")
        derived_definition = _copy_mapping(
            derived_bundle.get("definition"),
            "derived definition",
        )
        derived_state = _copy_mapping(derived_bundle.get("state"), "derived state")
        after_surface = _semantic_surface(derived_definition, derived_state)
        return _semantic_diff(baseline_surface, after_surface)

    return PreparedCharacterUpdateAdapters(
        snapshot,
        canonical_operations,
        adapter,
        derive,
        project_state_impact,
        project_semantics,
    )


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise AdapterPreparationError(
            f"{field_name} must be a non-empty, trim-stable string"
        )
    if len(value) > MAX_SUMMARY_LENGTH or "\x00" in value:
        raise AdapterPreparationError(f"{field_name} is outside the bounded contract")
    return value


def _positive_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AdapterPreparationError(f"{field_name} must be a positive integer")
    return value


def _copy_mapping(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AdapterPreparationError(f"{field_name} must be a mapping")
    return deepcopy(dict(value))


def _mapping_rows(container: Mapping[str, Any], field_name: str) -> list[dict[str, Any]]:
    value = container.get(field_name)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(row, Mapping) for row in value):
        raise AdapterPreparationError(f"{field_name} must be a list of mappings")
    return [deepcopy(dict(row)) for row in value]


def _source_kind(source: SourceIdentity) -> SourceKind:
    if not isinstance(source, SourceIdentity):
        raise AdapterPreparationError("source identity must be typed")
    try:
        return SourceKind(source.kind)
    except (TypeError, ValueError) as exc:
        raise AdapterPreparationError("unsupported source identity kind") from exc


def _dependencies(intent: object) -> tuple[str, ...]:
    dependencies = getattr(intent, "dependencies", ())
    if not isinstance(dependencies, tuple) or not all(
        isinstance(item, str) for item in dependencies
    ):
        raise AdapterPreparationError("dependencies must be an immutable string tuple")
    return tuple(dependencies)


def _exact_index(
    values: Sequence[Any],
    identity: Callable[[Any], str],
) -> dict[str, tuple[Any, ...]]:
    collected: dict[str, list[Any]] = {}
    for value in tuple(values):
        key = identity(value)
        if not key:
            continue
        collected.setdefault(key, []).append(deepcopy(value))
    return {key: tuple(rows) for key, rows in collected.items()}


def _campaign_page_ref(record: Any) -> str:
    return str(getattr(record, "page_ref", "") or "").strip()


def _systems_entry_key(entry: Any) -> str:
    return str(getattr(entry, "entry_key", "") or "").strip()


_GENERIC_CHOICE_SELECTOR_KEYS = frozenset(
    {
        "choose",
        "choice",
        "choices",
        "optionalfeatureprogression",
        "selectedchoices",
    }
)
_SPELL_FAMILY_KEYS = frozenset({"additionalspells", "spellmanager", "spellsupport"})
_SPELL_FAMILY_SELECTOR_KEYS = {
    "additionalspells": frozenset({"choose"}),
    "spellsupport": frozenset({"choices", "select", "replacement", "replacements"}),
    "spellmanager": frozenset({"sourceoptions", "choicefields"}),
}


def _normalized_selector_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _selector_payload_is_empty(value: object) -> bool:
    if value is None or value == "":
        return True
    return isinstance(value, (Mapping, list, tuple)) and not value


def _campaign_option_is_choice_bearing(option: Mapping[str, Any]) -> bool:
    def visit(value: object, spell_families: frozenset[str] = frozenset()) -> bool:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                normalized_key = _normalized_selector_key(key)
                nested_families = spell_families
                if normalized_key in _SPELL_FAMILY_KEYS:
                    nested_families = spell_families | {normalized_key}
                selector_keys = set(_GENERIC_CHOICE_SELECTOR_KEYS)
                for family in nested_families:
                    selector_keys.update(_SPELL_FAMILY_SELECTOR_KEYS[family])
                if normalized_key in selector_keys and not _selector_payload_is_empty(nested):
                    return True
                if visit(nested, nested_families):
                    return True
        elif isinstance(value, (list, tuple)):
            return any(visit(item, spell_families) for item in value)
        return False

    resources = _campaign_option_resource_payloads(dict(option or {}))
    return len(resources) > 1 or visit(option)


def _campaign_feature_definition(
    *,
    feature_id: str,
    source: _ResolvedCampaignPage,
) -> dict[str, Any]:
    option = dict(source.option)
    name = str(
        option.get("feature_name")
        or option.get("display_name")
        or source.title
        or "Campaign feature"
    ).strip()
    activation_type = str(option.get("activation_type") or "passive").strip() or "passive"
    row: dict[str, Any] = {
        "id": feature_id,
        "name": name,
        "category": _CAMPAIGN_FEATURE_CATEGORY,
        "source": _CAMPAIGN_SOURCE_LABEL,
        "description_markdown": str(option.get("description_markdown") or "").strip(),
        "activation_type": activation_type,
        "tracker_ref": None,
        "page_ref": source.page_ref,
        "campaign_option": option or None,
    }
    return row


def _campaign_feature_resource_additions(
    *,
    feature_id: str,
    option: Mapping[str, Any],
    current_level: int,
) -> tuple[ResourceAddition, ...]:
    resources = _campaign_option_resource_payloads(dict(option or {}))
    if not resources:
        return ()
    resource = dict(resources[0])
    maximum = _resolve_campaign_option_resource_max(
        resource,
        current_level=current_level,
    )
    if maximum <= 0:
        return ()
    return (
        ResourceAddition(
            f"campaign-option-tracker:{feature_id}",
            maximum,
            _clean_human_text(
                resource.get("label") or option.get("feature_name"),
                fallback="Campaign resource",
            ),
        ),
    )


def _campaign_item_quantity(option: Mapping[str, Any], requested: int | None) -> int:
    if requested is not None:
        return _positive_integer(requested, "quantity")
    raw_quantity = option.get("quantity", 1)
    if isinstance(raw_quantity, bool):
        raise AdapterPreparationError("campaign item quantity must be a positive integer")
    try:
        quantity = int(raw_quantity)
    except (TypeError, ValueError) as exc:
        raise AdapterPreparationError(
            "campaign item quantity must be a positive integer"
        ) from exc
    return _positive_integer(quantity, "quantity")


def _base_equipment_definition(
    *,
    equipment_id: str,
    name: str,
    quantity: int,
    weight: object = "",
    notes: object = "",
) -> dict[str, Any]:
    return {
        "id": equipment_id,
        "name": str(name or "").strip() or "Equipment",
        "default_quantity": quantity,
        "weight": str(weight or "").strip(),
        "notes": str(notes or "").strip(),
        "source_kind": _CUSTOM_EQUIPMENT_SOURCE_KIND,
        "campaign_option": None,
    }


def _campaign_equipment_definition(
    *,
    equipment_id: str,
    quantity: int,
    source: _ResolvedCampaignPage,
) -> dict[str, Any]:
    option = dict(source.option)
    row = _base_equipment_definition(
        equipment_id=equipment_id,
        name=str(option.get("item_name") or source.title or "Campaign item"),
        quantity=quantity,
        weight=option.get("weight"),
        notes=option.get("notes"),
    )
    row["page_ref"] = source.page_ref
    row["campaign_option"] = option or None
    return row


def _systems_equipment_definition(
    *,
    equipment_id: str,
    quantity: int,
    source: _ResolvedSystemsItem,
) -> dict[str, Any]:
    row = _base_equipment_definition(
        equipment_id=equipment_id,
        name=source.title,
        quantity=quantity,
        weight=source.metadata.get("weight", ""),
    )
    if source.systems_ref:
        row["systems_ref"] = deepcopy(dict(source.systems_ref))
    return row


def _inventory_row_for_definition(
    definition: Mapping[str, Any],
    quantity: int,
) -> dict[str, Any]:
    return {
        "id": definition.get("id"),
        "catalog_ref": definition.get("id"),
        "name": definition.get("name"),
        "quantity": quantity,
        "weight": definition.get("weight"),
        "is_equipped": bool(definition.get("is_equipped", False)),
        "is_attuned": bool(definition.get("is_attuned", False)),
        "charges_current": definition.get("charges_current"),
        "charges_max": definition.get("charges_max"),
        "notes": definition.get("notes", ""),
        "tags": list(definition.get("tags") or []),
    }


def _relink_campaign_equipment(
    existing: Mapping[str, Any],
    source: _ResolvedCampaignPage,
) -> dict[str, Any]:
    row = deepcopy(dict(existing))
    row.pop("systems_ref", None)
    row["page_ref"] = source.page_ref
    row["campaign_option"] = deepcopy(dict(source.option)) or None
    return row


def _relink_systems_equipment(
    existing: Mapping[str, Any],
    source: _ResolvedSystemsItem,
) -> dict[str, Any]:
    row = deepcopy(dict(existing))
    row.pop("page_ref", None)
    if source.systems_ref:
        row["systems_ref"] = deepcopy(dict(source.systems_ref))
    return row


def _definition_total_level(definition: Mapping[str, Any]) -> int:
    profile = dict(definition.get("profile") or {})
    class_rows = [
        dict(row)
        for row in list(profile.get("classes") or profile.get("class_rows") or [])
        if isinstance(row, Mapping)
    ]
    if class_rows:
        return max(sum(max(int(row.get("level") or 0), 0) for row in class_rows), 1)
    for key in ("total_level", "level", "class_level"):
        try:
            value = int(profile.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 1


def _inventory_index(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[dict[str, Any], ...]]:
    collected: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        identity = str(row.get("catalog_ref") or row.get("id") or "").strip()
        if identity:
            collected.setdefault(identity, []).append(deepcopy(dict(row)))
    return {key: tuple(value) for key, value in collected.items()}


def _definition_source(row: Mapping[str, Any]) -> SourceIdentity | None:
    page_ref = _page_ref_value(row.get("page_ref"))
    if page_ref:
        return SourceIdentity(SourceKind.CAMPAIGN_PAGE, page_ref)
    systems_ref = dict(row.get("systems_ref") or {})
    entry_key = str(systems_ref.get("entry_key") or "").strip()
    if entry_key:
        return SourceIdentity(SourceKind.SYSTEMS_ENTRY, entry_key)
    return None


def _build_snapshot(
    *,
    target_identity: str,
    baseline_identity: str,
    definition: Mapping[str, Any],
    state: Mapping[str, Any],
    feature_rows: Sequence[Mapping[str, Any]],
    equipment_rows: Sequence[Mapping[str, Any]],
    state_resource_rows: Sequence[Mapping[str, Any]],
    inventory_by_identity: Mapping[str, tuple[dict[str, Any], ...]],
) -> CharacterSnapshot:
    features: dict[str, ExistingFeature] = {}
    for row in feature_rows:
        feature_id = str(row.get("id") or "").strip()
        source = _definition_source(row)
        if not feature_id or source is None or feature_id in features:
            continue
        tracker_ref = str(row.get("tracker_ref") or "").strip()
        resources = ()
        if tracker_ref:
            matching = [
                resource
                for resource in state_resource_rows
                if str(resource.get("id") or "").strip() == tracker_ref
            ]
            if len(matching) == 1:
                resources = (
                    ResourceAddition(
                        tracker_ref,
                        max(int(matching[0].get("current") or 0), 0),
                        str(matching[0].get("label") or ""),
                    ),
                )
        features[feature_id] = ExistingFeature(
            feature_id,
            source,
            deepcopy(dict(row)),
            resources,
        )

    equipment: dict[str, ExistingEquipment] = {}
    for row in equipment_rows:
        equipment_id = str(row.get("id") or "").strip()
        inventory_rows = inventory_by_identity.get(equipment_id, ())
        if not equipment_id or equipment_id in equipment or len(inventory_rows) != 1:
            continue
        inventory_row = inventory_rows[0]
        equipment[equipment_id] = ExistingEquipment(
            equipment_id,
            _definition_source(row),
            deepcopy(dict(row)),
            deepcopy(inventory_row),
            max(int(inventory_row.get("quantity") or 0), 1),
        )
    resource_ids = frozenset(
        str(row.get("id") or "").strip()
        for row in state_resource_rows
        if str(row.get("id") or "").strip()
    )
    return CharacterSnapshot(
        target_identity,
        baseline_identity,
        str(definition.get("system") or "").strip(),
        deepcopy(dict(definition)),
        deepcopy(dict(state)),
        features,
        equipment,
        resource_ids,
        True,
    )


def _adapt_operation(
    definition: Mapping[str, Any],
    operation: UpdateOperation,
    campaign_relink_options_by_operation_id: Mapping[str, Any],
) -> Mapping[str, Any]:
    candidate = _copy_mapping(definition, "candidate definition")
    if str(candidate.get("system") or "").strip() != SUPPORTED_SYSTEM:
        raise ValueError("adapter accepts only DND-5E definitions")
    try:
        kind = OperationKind(operation.kind)
    except (TypeError, ValueError) as exc:
        raise ValueError("unsupported adapter operation") from exc
    payload = operation.payload
    if kind is OperationKind.CAMPAIGN_FEATURE_GRANT and isinstance(
        payload,
        CampaignFeatureGrant,
    ):
        rows = _mapping_rows(candidate, "features")
        _assert_new_identity(rows, payload.feature_id)
        rows.append(deepcopy(dict(payload.definition)))
        candidate["features"] = rows
        return candidate
    if kind in {
        OperationKind.CAMPAIGN_EQUIPMENT_ADD,
        OperationKind.SYSTEMS_ITEM_ADD,
    } and isinstance(payload, CampaignEquipmentAdd | SystemsItemAdd):
        rows = _mapping_rows(candidate, "equipment_catalog")
        _assert_new_identity(rows, payload.equipment_id)
        rows.append(deepcopy(dict(payload.definition)))
        candidate["equipment_catalog"] = rows
        return candidate
    if kind is OperationKind.EQUIPMENT_SAFE_RELINK and isinstance(
        payload,
        EquipmentSafeRelink,
    ):
        rows = _mapping_rows(candidate, "equipment_catalog")
        matches = [
            index
            for index, row in enumerate(rows)
            if str(row.get("id") or "").strip() == payload.equipment_id
        ]
        if len(matches) != 1:
            raise ValueError("safe relink requires one exact equipment identity")
        existing = rows[matches[0]]
        if _definition_source(existing) is not None:
            raise ValueError("safe relink cannot replace an existing source link")
        replacement = deepcopy(dict(payload.definition))
        operation_key = operation_id(operation)
        has_campaign_option_expectation = (
            operation_key in campaign_relink_options_by_operation_id
        )
        expected_campaign_option = campaign_relink_options_by_operation_id.get(operation_key)
        if not _safe_relink_definition_change(
            existing,
            replacement,
            payload.target_source,
            has_campaign_option_expectation=has_campaign_option_expectation,
            expected_campaign_option=expected_campaign_option,
        ):
            raise ValueError("safe relink changed more than the exact source link")
        rows[matches[0]] = replacement
        candidate["equipment_catalog"] = rows
        return candidate
    raise ValueError("operation kind and payload type do not match")


def _assert_new_identity(rows: Sequence[Mapping[str, Any]], identity: str) -> None:
    if sum(str(row.get("id") or "").strip() == identity for row in rows):
        raise ValueError("addition requires a wholly new stable identity")


def _safe_relink_definition_change(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    target: SourceIdentity,
    *,
    has_campaign_option_expectation: bool,
    expected_campaign_option: Any,
) -> bool:
    before_copy = deepcopy(dict(before))
    after_copy = deepcopy(dict(after))
    kind = _source_kind(target)
    if kind is SourceKind.CAMPAIGN_PAGE:
        expected_ref = _required_text(target.value, "target source")
        if _page_ref_value(after_copy.get("page_ref")) != expected_ref:
            return False
        if after_copy.get("systems_ref"):
            return False
        if not has_campaign_option_expectation or "campaign_option" not in after_copy:
            return False
        if not _same(after_copy["campaign_option"], expected_campaign_option):
            return False
        after_copy.pop("page_ref", None)
        after_copy.pop("campaign_option", None)
    else:
        expected_key = _required_text(target.value, "target source")
        systems_ref = dict(after_copy.get("systems_ref") or {})
        if str(systems_ref.get("entry_key") or "").strip() != expected_key:
            return False
        if after_copy.get("page_ref"):
            return False
        after_copy.pop("systems_ref", None)
    before_copy.pop("page_ref", None)
    before_copy.pop("systems_ref", None)
    if kind is SourceKind.CAMPAIGN_PAGE:
        before_copy.pop("campaign_option", None)
    return _same(before_copy, after_copy)


def _definition_derivation_hazards(
    candidate: Mapping[str, Any],
    normalized: Mapping[str, Any],
    operations: Sequence[UpdateOperation],
) -> tuple[str, ...]:
    warnings: list[str] = []
    derived_top_level_fields = {
        "attacks",
        "equipment_catalog",
        "features",
        "proficiencies",
        "resource_templates",
        "skills",
        "spellcasting",
        "stats",
    }
    candidate_stable = {
        key: deepcopy(value)
        for key, value in candidate.items()
        if key not in derived_top_level_fields
    }
    normalized_stable = {
        key: deepcopy(value)
        for key, value in normalized.items()
        if key not in derived_top_level_fields
    }
    if not _same(candidate_stable, normalized_stable):
        warnings.append("Native derivation changed unrelated Character definition data.")
    if str(normalized.get("system") or "").strip() != SUPPORTED_SYSTEM:
        warnings.append("Native derivation changed the Character system.")
    expected_feature_additions = {
        operation.payload.feature_id
        for operation in operations
        if isinstance(operation.payload, CampaignFeatureGrant)
    }
    expected_equipment_additions = {
        operation.payload.equipment_id
        for operation in operations
        if isinstance(operation.payload, CampaignEquipmentAdd | SystemsItemAdd)
    }
    warnings.extend(
        _row_family_hazards(
            _mapping_rows(candidate, "features"),
            _mapping_rows(normalized, "features"),
            expected_feature_additions,
            "feature",
        )
    )
    warnings.extend(
        _row_family_hazards(
            _mapping_rows(candidate, "equipment_catalog"),
            _mapping_rows(normalized, "equipment_catalog"),
            expected_equipment_additions,
            "equipment",
        )
    )
    return tuple(dict.fromkeys(warnings))


def _row_family_hazards(
    before: Sequence[Mapping[str, Any]],
    after: Sequence[Mapping[str, Any]],
    expected_additions: set[str],
    label: str,
) -> list[str]:
    warnings: list[str] = []
    before_ids = [str(row.get("id") or "").strip() for row in before]
    after_ids = [str(row.get("id") or "").strip() for row in after]
    if any(not identity for identity in before_ids + after_ids):
        warnings.append(f"Native derivation produced an unstable {label} identity.")
        return warnings
    if len(set(after_ids)) != len(after_ids):
        warnings.append(f"Native derivation merged a {label} identity.")
    if set(before_ids) != set(after_ids):
        warnings.append(f"Native derivation added or removed an unexpected {label} row.")
    if [identity for identity in after_ids if identity in set(before_ids)] != before_ids:
        warnings.append(f"Native derivation reordered existing {label} rows.")
    before_by_id = {str(row.get("id") or "").strip(): dict(row) for row in before}
    after_by_id = {str(row.get("id") or "").strip(): dict(row) for row in after}
    for identity in set(before_ids) - expected_additions:
        if identity in after_by_id and not _same(before_by_id[identity], after_by_id[identity]):
            warnings.append(f"Native derivation changed an existing {label} row.")
            break
    for identity in expected_additions:
        if before_ids.count(identity) != 1 or after_ids.count(identity) != 1:
            warnings.append(f"Native derivation did not preserve one added {label} row.")
    return warnings


def _project_state_impact(
    baseline_state: Mapping[str, Any],
    derived_character: Mapping[str, Any],
    operations: tuple[UpdateOperation, ...],
) -> StateImpactProjection:
    baseline = _copy_mapping(baseline_state, "baseline state")
    bundle = _copy_mapping(derived_character, "derived character")
    merged = _copy_mapping(bundle.get("state"), "derived state")
    expected_resources = tuple(
        resource
        for operation in operations
        if isinstance(operation.payload, CampaignFeatureGrant)
        for resource in operation.payload.resources
    )
    expected_inventory = tuple(
        (operation.payload.equipment_id, operation.payload.quantity)
        for operation in operations
        if isinstance(operation.payload, CampaignEquipmentAdd | SystemsItemAdd)
    )
    hazards: list[str] = []

    baseline_other = deepcopy(baseline)
    merged_other = deepcopy(merged)
    baseline_resources = _mapping_rows(baseline_other, "resources")
    merged_resources = _mapping_rows(merged_other, "resources")
    baseline_inventory = _mapping_rows(baseline_other, "inventory")
    merged_inventory = _mapping_rows(merged_other, "inventory")
    baseline_other.pop("resources", None)
    merged_other.pop("resources", None)
    baseline_other.pop("inventory", None)
    merged_other.pop("inventory", None)
    if not _same(baseline_other, merged_other):
        hazards.append("State reconciliation changed data outside resources and inventory.")

    hazards.extend(
        _state_family_hazards(
            baseline_resources,
            merged_resources,
            {resource.resource_id: resource.initial_value for resource in expected_resources},
            identity=lambda row: str(row.get("id") or "").strip(),
            value=lambda row: int(row.get("current") or 0),
            label="resource",
        )
    )
    hazards.extend(
        _state_family_hazards(
            baseline_inventory,
            merged_inventory,
            dict(expected_inventory),
            identity=lambda row: str(row.get("catalog_ref") or row.get("id") or "").strip(),
            value=lambda row: int(row.get("quantity") or 0),
            label="inventory",
        )
    )
    reconciliation = StateReconciliation(
        tuple(sorted(expected_resources, key=lambda row: row.resource_id)),
        tuple(sorted(expected_inventory)),
    )
    impact = (
        StateImpact.RECONCILE_REQUIRED
        if expected_resources or expected_inventory
        else StateImpact.PRESERVE_EXACT
    )
    return StateImpactProjection(
        impact,
        reconciliation,
        (),
        tuple(dict.fromkeys(hazards)),
    )


def _state_family_hazards(
    before: Sequence[Mapping[str, Any]],
    after: Sequence[Mapping[str, Any]],
    expected_additions: Mapping[str, int],
    *,
    identity: Callable[[Mapping[str, Any]], str],
    value: Callable[[Mapping[str, Any]], int],
    label: str,
) -> list[str]:
    hazards: list[str] = []
    before_ids = [identity(row) for row in before]
    after_ids = [identity(row) for row in after]
    if any(not row_id for row_id in before_ids + after_ids):
        return [f"State {label} rows require stable identities."]
    if len(set(before_ids)) != len(before_ids) or len(set(after_ids)) != len(after_ids):
        return [f"State {label} identities must be unique."]
    before_by_id = {identity(row): dict(row) for row in before}
    after_by_id = {identity(row): dict(row) for row in after}
    if [row_id for row_id in after_ids if row_id in before_by_id] != before_ids:
        hazards.append(f"State reconciliation removed or reordered an existing {label} row.")
    for row_id, row in before_by_id.items():
        if row_id not in after_by_id or not _same(row, after_by_id[row_id]):
            hazards.append(f"State reconciliation changed an existing {label} row.")
            break
    actual_additions = [row_id for row_id in after_ids if row_id not in before_by_id]
    if set(actual_additions) != set(expected_additions):
        hazards.append(f"State reconciliation added an unexpected {label} row.")
    for row_id, expected_value in expected_additions.items():
        row = after_by_id.get(row_id)
        if row is None or value(row) != expected_value:
            hazards.append(f"State reconciliation produced an incorrect new {label} value.")
            break
    return hazards


def _semantic_diff(
    before: _SemanticSurface,
    after: _SemanticSurface,
) -> SemanticProjection:
    warnings = list(before.warnings) + list(after.warnings)
    before_by_key = {(cell.category, cell.identity): cell for cell in before.cells}
    after_by_key = {(cell.category, cell.identity): cell for cell in after.cells}
    for category in SemanticCategory:
        before_order = [
            cell.identity for cell in before.cells if cell.category is category
        ]
        after_order = [cell.identity for cell in after.cells if cell.category is category]
        if [identity for identity in after_order if identity in set(before_order)] != before_order:
            warnings.append(f"Semantic projection removed or reordered {category.value} rows.")
    rows: list[SemanticDiffRow] = []
    for key in sorted(
        set(before_by_key) | set(after_by_key),
        key=lambda item: (list(SemanticCategory).index(item[0]), item[1]),
    ):
        old = before_by_key.get(key)
        new = after_by_key.get(key)
        if old is None and new is not None:
            rows.append(
                SemanticDiffRow(
                    new.category,
                    new.identity,
                    new.label,
                    ChangeKind.ADDED,
                    "Not present",
                    new.summary,
                )
            )
        elif old is not None and new is None:
            rows.append(
                SemanticDiffRow(
                    old.category,
                    old.identity,
                    old.label,
                    ChangeKind.REMOVED,
                    old.summary,
                    "Not present",
                )
            )
        elif old is not None and new is not None and old.summary != new.summary:
            rows.append(
                SemanticDiffRow(
                    new.category,
                    new.identity,
                    new.label,
                    ChangeKind.UPDATED,
                    old.summary,
                    new.summary,
                )
            )
    return SemanticProjection(tuple(rows), tuple(dict.fromkeys(warnings)))


def _semantic_surface(
    definition: Mapping[str, Any],
    state: Mapping[str, Any],
) -> _SemanticSurface:
    cells: list[_SemanticCell] = []
    warnings: list[str] = []
    cells.extend(
        _row_semantic_cells(
            _mapping_rows(definition, "features"),
            SemanticCategory.FEATURES,
            _feature_identity,
            _feature_summary,
            warnings,
        )
    )
    inventory_lookup = {
        str(row.get("catalog_ref") or row.get("id") or "").strip(): row
        for row in _mapping_rows(state, "inventory")
        if str(row.get("catalog_ref") or row.get("id") or "").strip()
    }
    cells.extend(
        _row_semantic_cells(
            _mapping_rows(definition, "equipment_catalog"),
            SemanticCategory.EQUIPMENT_INVENTORY,
            _equipment_identity,
            lambda row: _equipment_summary(row, inventory_lookup),
            warnings,
        )
    )
    spellcasting = dict(definition.get("spellcasting") or {})
    cells.extend(
        _row_semantic_cells(
            [
                dict(row)
                for row in list(spellcasting.get("spells") or [])
                if isinstance(row, Mapping)
            ],
            SemanticCategory.SPELLS,
            _spell_identity,
            _spell_summary,
            warnings,
        )
    )
    cells.extend(
        _row_semantic_cells(
            _mapping_rows(definition, "attacks"),
            SemanticCategory.ATTACKS,
            _attack_identity,
            _attack_summary,
            warnings,
        )
    )
    stats = dict(definition.get("stats") or {})
    cells.append(
        _SemanticCell(
            SemanticCategory.ARMOR_CLASS,
            "armor-class",
            "Armor Class",
            _summary("Armor Class", stats.get("armor_class", 0)),
        )
    )
    cells.extend(
        _row_semantic_cells(
            _mapping_rows(state, "resources"),
            SemanticCategory.RESOURCES,
            lambda row: str(row.get("id") or "").strip(),
            _resource_summary,
            warnings,
        )
    )
    return _SemanticSurface(tuple(cells), tuple(dict.fromkeys(warnings)))


def _row_semantic_cells(
    rows: Sequence[Mapping[str, Any]],
    category: SemanticCategory,
    identity: Callable[[Mapping[str, Any]], str],
    summarize: Callable[[Mapping[str, Any]], tuple[str, str]],
    warnings: list[str],
) -> list[_SemanticCell]:
    cells: list[_SemanticCell] = []
    seen: set[str] = set()
    for row in rows:
        row_identity = identity(row)
        if not row_identity:
            warnings.append(f"{category.value} contains a row without stable identity.")
            continue
        if (
            row_identity != row_identity.strip()
            or len(row_identity) > MAX_SUMMARY_LENGTH
            or "\x00" in row_identity
            or "\n" in row_identity
            or "\r" in row_identity
        ):
            warnings.append(f"{category.value} contains an unsafe stable identity.")
            continue
        if row_identity in seen:
            warnings.append(f"{category.value} contains duplicate stable identities.")
            continue
        seen.add(row_identity)
        label, summary = summarize(row)
        cells.append(
            _SemanticCell(
                category,
                row_identity,
                _clean_human_text(label, fallback=category.value),
                _clean_human_text(summary, fallback="Present"),
            )
        )
    return cells


def _feature_identity(row: Mapping[str, Any]) -> str:
    return str(row.get("id") or "").strip()


def _equipment_identity(row: Mapping[str, Any]) -> str:
    return str(row.get("id") or "").strip()


def _spell_identity(row: Mapping[str, Any]) -> str:
    explicit = str(row.get("id") or row.get("spell_id") or "").strip()
    if explicit:
        return explicit
    systems_ref = dict(row.get("systems_ref") or {})
    entry_key = str(systems_ref.get("entry_key") or "").strip()
    page_ref = _page_ref_value(row.get("page_ref"))
    class_row_id = str(row.get("class_row_id") or row.get("source_row_id") or "").strip()
    if entry_key:
        return "spell entry " + entry_key + (" row " + class_row_id if class_row_id else "")
    if page_ref:
        return "spell page " + page_ref + (" row " + class_row_id if class_row_id else "")
    return ""


def _attack_identity(row: Mapping[str, Any]) -> str:
    explicit = str(row.get("id") or row.get("attack_id") or "").strip()
    if explicit:
        return explicit
    refs = [
        str(value or "").strip()
        for value in list(row.get("equipment_refs") or [])
        if str(value or "").strip()
    ]
    single_ref = str(row.get("equipment_ref") or "").strip()
    if single_ref and single_ref not in refs:
        refs.append(single_ref)
    mode_key = str(row.get("mode_key") or "").strip()
    if refs:
        return "attack equipment " + " and ".join(sorted(refs)) + (
            " mode " + mode_key if mode_key else ""
        )
    return ""


def _feature_summary(row: Mapping[str, Any]) -> tuple[str, str]:
    name = _clean_human_text(row.get("name"), fallback="Feature")
    link = _source_link_label(row)
    activation = _clean_human_text(row.get("activation_type"), fallback="passive")
    return name, _summary("Feature", name, "activation", activation, "source", link)


def _equipment_summary(
    row: Mapping[str, Any],
    inventory: Mapping[str, Mapping[str, Any]],
) -> tuple[str, str]:
    identity = str(row.get("id") or "").strip()
    state_row = dict(inventory.get(identity) or {})
    name = _clean_human_text(row.get("name"), fallback="Equipment")
    quantity = int(state_row.get("quantity") or row.get("default_quantity") or 0)
    equipped = "equipped" if bool(state_row.get("is_equipped")) else "not equipped"
    attuned = "attuned" if bool(state_row.get("is_attuned")) else "not attuned"
    return name, _summary(
        "Equipment",
        name,
        "quantity",
        quantity,
        equipped,
        attuned,
        "source",
        _source_link_label(row),
    )


def _spell_summary(row: Mapping[str, Any]) -> tuple[str, str]:
    name = _clean_human_text(row.get("name") or row.get("title"), fallback="Spell")
    level = int(row.get("level") or row.get("spell_level") or 0)
    preparation = (
        "always prepared"
        if bool(row.get("is_always_prepared"))
        else "prepared"
        if bool(row.get("is_prepared"))
        else "known"
        if bool(row.get("is_known"))
        else "available"
    )
    return name, _summary("Spell", name, "level", level, preparation)


def _attack_summary(row: Mapping[str, Any]) -> tuple[str, str]:
    name = _clean_human_text(row.get("name"), fallback="Attack")
    return name, _summary(
        "Attack",
        name,
        "bonus",
        row.get("attack_bonus", row.get("bonus", "none")),
        "damage",
        row.get("damage", "none"),
        "range",
        row.get("range", "none"),
    )


def _resource_summary(row: Mapping[str, Any]) -> tuple[str, str]:
    label = _clean_human_text(row.get("label"), fallback="Resource")
    maximum = row.get("max")
    maximum_text = "unlimited" if maximum is None else int(maximum)
    return label, _summary(
        "Resource",
        label,
        "current",
        int(row.get("current") or 0),
        "maximum",
        maximum_text,
    )


def _source_link_label(row: Mapping[str, Any]) -> str:
    if _page_ref_value(row.get("page_ref")):
        return "campaign page"
    systems_ref = dict(row.get("systems_ref") or {})
    if str(systems_ref.get("entry_key") or "").strip():
        return "Systems item"
    return "unlinked"


def _summary(*parts: object) -> str:
    return "; ".join(
        _clean_human_text(part, fallback="")
        for part in parts
        if _clean_human_text(part, fallback="")
    )


_MARKDOWN_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_HTML_TAG_RE = re.compile(r"<[^>]{0,256}>")
_MACHINE_TOKEN_RE = re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{32,}(?![0-9a-f])")
_UNSAFE_MARKUP_RE = re.compile(r"[`*_{}\[\]<>\\|~]")


def _clean_human_text(value: object, *, fallback: str) -> str:
    text = html.unescape(str(value or ""))
    text = _HTML_TAG_RE.sub(" ", text)
    text = _MARKDOWN_LINK_RE.sub(r"\1", text)
    text = _UNSAFE_MARKUP_RE.sub(" ", text)
    text = text.replace(":", " - ").replace("/", " ")
    text = _MACHINE_TOKEN_RE.sub("protected value", text)
    text = " ".join(text.replace("\r", " ").replace("\n", " ").split()).strip(" -")
    if not text:
        text = fallback
    if len(text) > MAX_SUMMARY_LENGTH:
        text = text[: MAX_SUMMARY_LENGTH - 1].rstrip() + "…"
    return text


def _page_ref_value(value: object) -> str:
    if isinstance(value, Mapping):
        return str(value.get("page_ref") or value.get("slug") or "").strip()
    return str(value or "").strip()


def _canonical_json(value: object) -> str:
    def canonical(item: object) -> object:
        if item is None or isinstance(item, (str, bool, int)):
            return item
        if isinstance(item, float):
            raise AdapterPreparationError("floating-point values are not canonical inputs")
        if isinstance(item, Enum):
            return item.value
        if hasattr(item, "__dataclass_fields__"):
            return {
                key: canonical(getattr(item, key))
                for key in sorted(item.__dataclass_fields__)
            }
        if isinstance(item, Mapping):
            if not all(isinstance(key, str) for key in item):
                raise AdapterPreparationError("canonical mappings require string keys")
            return {key: canonical(item[key]) for key in sorted(item)}
        if isinstance(item, (list, tuple)):
            return [canonical(child) for child in item]
        if isinstance(item, (set, frozenset)):
            values = [canonical(child) for child in item]
            return sorted(
                values,
                key=lambda child: json.dumps(child, sort_keys=True, separators=(",", ":")),
            )
        raise AdapterPreparationError(
            f"unsupported canonical value: {type(item).__name__}"
        )

    return json.dumps(
        canonical(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _same(left: object, right: object) -> bool:
    return _canonical_json(left) == _canonical_json(right)


__all__ = [
    "AdapterPreparationError",
    "CampaignEquipmentAddIntent",
    "CampaignFeatureGrantIntent",
    "EquipmentSafeRelinkIntent",
    "PreparedCharacterUpdateAdapters",
    "SourceAccessDecision",
    "SystemsItemAddIntent",
    "prepare_character_update_adapters",
]
