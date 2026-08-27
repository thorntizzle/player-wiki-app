"""Pure planning kernel for bounded DND-5E character updates.

The planner intentionally knows nothing about Flask, persistence, repositories, or
source services.  Callers prepare exact source identities and immutable snapshots,
then inject pure functions for definition adaptation, derivation, and semantic
projection.  Mutable state is never passed to an adapter and is never changed here.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Protocol, Sequence, TypeAlias
from urllib.parse import quote


PLANNER_VERSION = 1
SUPPORTED_SYSTEM = "DND-5E"
MAX_OPERATIONS = 128
MAX_DEPENDENCIES = 64
MAX_TEXT_LENGTH = 512
MAX_DIFF_ROWS = 512
_DIGEST_DOMAIN = b"campaign-player-wiki:character-update-plan:v1\x00"
class OperationKind(str, Enum):
    CAMPAIGN_FEATURE_GRANT = "campaign_feature_grant"
    CAMPAIGN_EQUIPMENT_ADD = "campaign_equipment_add"
    SYSTEMS_ITEM_ADD = "systems_item_add"
    EQUIPMENT_SAFE_RELINK = "equipment_safe_relink"


class SourceKind(str, Enum):
    CAMPAIGN_PAGE = "campaign_page"
    SYSTEMS_ENTRY = "systems_entry"


class OperationStatus(str, Enum):
    READY = "ready"
    ALREADY_SATISFIED = "already_satisfied"
    BLOCKED = "blocked"


class PlanStatus(str, Enum):
    READY = "ready"
    NO_OP = "no_op"
    BLOCKED = "blocked"


class StateImpact(str, Enum):
    PRESERVE_EXACT = "preserve_exact"
    RECONCILE_REQUIRED = "reconcile_required"


class ChangeKind(str, Enum):
    ADDED = "added"
    UPDATED = "updated"
    REMOVED = "removed"


class SemanticCategory(str, Enum):
    FEATURES = "features"
    EQUIPMENT_INVENTORY = "equipment/inventory"
    SPELLS = "spells"
    ATTACKS = "attacks"
    ARMOR_CLASS = "Armor Class"
    RESOURCES = "resources"


_CATEGORY_ORDER = {category: index for index, category in enumerate(SemanticCategory)}


class DiagnosticCode(str, Enum):
    INVALID_INPUT = "invalid_input"
    UNSUPPORTED_SYSTEM = "unsupported_system"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    UNSUPPORTED_VERSION = "unsupported_version"
    SOURCE_POLICY_FAILED = "source_policy_failed"
    AMBIGUOUS_SOURCE = "ambiguous_source"
    CHOICE_BEARING = "choice_bearing"
    DUPLICATE_OPERATION = "duplicate_operation"
    CONFLICTING_INTENT = "conflicting_intent"
    IDENTITY_COLLISION = "identity_collision"
    MISSING_DEPENDENCY = "missing_dependency"
    SELF_DEPENDENCY = "self_dependency"
    OUT_OF_REQUEST_DEPENDENCY = "out_of_request_dependency"
    CYCLIC_DEPENDENCY = "cyclic_dependency"
    MISSING_WHOLE_STATE = "missing_whole_state"
    MUTABLE_STATE_HAZARD = "mutable_state_hazard"
    AMBIGUOUS_RELINK = "ambiguous_relink"
    ADAPTER_FAILED = "adapter_failed"
    DERIVATION_FAILED = "derivation_failed"
    DERIVATION_WARNING = "derivation_warning"
    PROJECTION_FAILED = "projection_failed"
    PROJECTION_WARNING = "projection_warning"
    STATE_IMPACT_FAILED = "state_impact_failed"
    STATE_IMPACT_WARNING = "state_impact_warning"
    STATE_IMPACT_HAZARD = "state_impact_hazard"
    STATE_IMPACT_MISMATCH = "state_impact_mismatch"
    INVALID_SEMANTIC_DIFF = "invalid_semantic_diff"
    UNEXPLAINED_SEMANTIC_CHANGE = "unexplained_semantic_change"


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    kind: SourceKind | str
    value: str


@dataclass(frozen=True, slots=True)
class SourceAttestation:
    policy_allowed: bool = True
    ambiguous: bool = False
    choice_bearing: bool = False


@dataclass(frozen=True, slots=True)
class ResourceAddition:
    resource_id: str
    initial_value: int = 0
    label: str = ""


@dataclass(frozen=True, slots=True)
class CampaignFeatureGrant:
    page_ref: str
    feature_id: str
    definition: Mapping[str, Any]
    label: str = ""
    resources: tuple[ResourceAddition, ...] = ()
    source: SourceAttestation = field(default_factory=SourceAttestation)


@dataclass(frozen=True, slots=True)
class CampaignEquipmentAdd:
    page_ref: str
    equipment_id: str
    definition: Mapping[str, Any]
    inventory_row: Mapping[str, Any]
    quantity: int = 1
    label: str = ""
    source: SourceAttestation = field(default_factory=SourceAttestation)


@dataclass(frozen=True, slots=True)
class SystemsItemAdd:
    entry_key: str
    equipment_id: str
    definition: Mapping[str, Any]
    inventory_row: Mapping[str, Any]
    quantity: int = 1
    label: str = ""
    source: SourceAttestation = field(default_factory=SourceAttestation)


@dataclass(frozen=True, slots=True)
class EquipmentSafeRelink:
    equipment_id: str
    target_source: SourceIdentity
    definition: Mapping[str, Any]
    inventory_before: Mapping[str, Any]
    inventory_after: Mapping[str, Any]
    label: str = ""
    source: SourceAttestation = field(default_factory=SourceAttestation)


OperationPayload: TypeAlias = (
    CampaignFeatureGrant | CampaignEquipmentAdd | SystemsItemAdd | EquipmentSafeRelink
)


@dataclass(frozen=True, slots=True)
class UpdateOperation:
    kind: OperationKind | str
    payload: OperationPayload | object
    dependencies: tuple[str, ...] = ()
    version: int = PLANNER_VERSION


@dataclass(frozen=True, slots=True)
class ExistingFeature:
    feature_id: str
    source: SourceIdentity
    definition: Mapping[str, Any]
    resources: tuple[ResourceAddition, ...] = ()


@dataclass(frozen=True, slots=True)
class ExistingEquipment:
    equipment_id: str
    source: SourceIdentity | None
    definition: Mapping[str, Any]
    inventory_row: Mapping[str, Any]
    quantity: int = 1


@dataclass(frozen=True, slots=True)
class CharacterSnapshot:
    target_identity: str
    baseline_identity: str
    system: str
    definition: Mapping[str, Any]
    state: Mapping[str, Any] | None
    features: Mapping[str, ExistingFeature] = field(default_factory=dict)
    equipment: Mapping[str, ExistingEquipment] = field(default_factory=dict)
    state_resource_ids: frozenset[str] = frozenset()
    whole_state: bool = True


@dataclass(frozen=True, slots=True)
class DerivationResult:
    character: Mapping[str, Any]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SemanticDiffRow:
    category: SemanticCategory | str
    identity: str
    label: str
    change: ChangeKind | str
    before: str
    after: str


@dataclass(frozen=True, slots=True)
class SemanticProjection:
    rows: tuple[SemanticDiffRow, ...] = ()
    warnings: tuple[str, ...] = ()


class OperationAdapter(Protocol):
    def __call__(
        self, definition: Mapping[str, Any], operation: UpdateOperation
    ) -> Mapping[str, Any]: ...


class CharacterDeriver(Protocol):
    def __call__(
        self, definition: Mapping[str, Any], state: Mapping[str, Any]
    ) -> DerivationResult: ...


class SemanticProjector(Protocol):
    def __call__(
        self,
        baseline_definition: Mapping[str, Any],
        derived_character: Mapping[str, Any],
        state: Mapping[str, Any],
    ) -> SemanticProjection: ...


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: DiagnosticCode
    message: str
    operation_id: str | None = None


@dataclass(frozen=True, slots=True)
class PlannedOperation:
    operation_id: str
    kind: OperationKind | str
    version: int
    dependencies: tuple[str, ...]
    status: OperationStatus


@dataclass(frozen=True, slots=True)
class StateReconciliation:
    resources: tuple[ResourceAddition, ...] = ()
    inventory: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True, slots=True)
class StateImpactProjection:
    impact: StateImpact | str
    reconciliation: StateReconciliation = field(default_factory=StateReconciliation)
    warnings: tuple[str, ...] = ()
    hazards: tuple[str, ...] = ()


class StateImpactProjector(Protocol):
    def __call__(
        self,
        baseline_state: Mapping[str, Any],
        derived_character: Mapping[str, Any],
        operations: tuple[UpdateOperation, ...],
    ) -> StateImpactProjection: ...


@dataclass(frozen=True, slots=True)
class CharacterUpdatePlan:
    version: int
    target_identity: str
    baseline_identity: str
    status: PlanStatus
    operations: tuple[PlannedOperation, ...]
    state_impact: StateImpact
    reconciliation: StateReconciliation
    semantic_diff: tuple[SemanticDiffRow, ...]
    digest: str | None
    candidate_definition: Mapping[str, Any] | None
    derived_character: Mapping[str, Any] | None
    diagnostics: tuple[Diagnostic, ...] = ()


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be a non-empty, trim-stable string")
    if len(value) > MAX_TEXT_LENGTH or "\x00" in value:
        raise ValueError(f"{field_name} is outside the bounded text contract")
    return value


def _source(source: SourceIdentity, field_name: str) -> tuple[str, str]:
    try:
        kind = SourceKind(source.kind).value
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} has an unsupported source kind") from exc
    return kind, _text(source.value, f"{field_name}.value")


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        raise ValueError("floating-point values are not canonical planner inputs")
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _canonical_value(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("canonical mappings require string keys")
        return {key: _canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_canonical_value(item) for item in value]
        return sorted(normalized, key=_canonical_json)
    raise ValueError(f"unsupported canonical value: {type(value).__name__}")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _canonical_value(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )


def _same(left: Any, right: Any) -> bool:
    return _canonical_json(left) == _canonical_json(right)


def _quoted(value: str) -> str:
    return quote(value, safe="")


def operation_id(operation: UpdateOperation) -> str:
    """Return the stable V1 identity for a typed operation."""

    kind = OperationKind(operation.kind)
    payload = operation.payload
    prefix = f"character-update:v{operation.version}:{kind.value}:"
    if kind is OperationKind.CAMPAIGN_FEATURE_GRANT and isinstance(
        payload, CampaignFeatureGrant
    ):
        return prefix + "campaign_page:" + _quoted(_text(payload.page_ref, "page_ref"))
    if kind is OperationKind.CAMPAIGN_EQUIPMENT_ADD and isinstance(
        payload, CampaignEquipmentAdd
    ):
        return prefix + "campaign_page:" + _quoted(_text(payload.page_ref, "page_ref"))
    if kind is OperationKind.SYSTEMS_ITEM_ADD and isinstance(payload, SystemsItemAdd):
        return prefix + "systems_entry:" + _quoted(_text(payload.entry_key, "entry_key"))
    if kind is OperationKind.EQUIPMENT_SAFE_RELINK and isinstance(
        payload, EquipmentSafeRelink
    ):
        target_kind, target_value = _source(payload.target_source, "target_source")
        return (
            prefix
            + f"equipment:{_quoted(_text(payload.equipment_id, 'equipment_id'))}:"
            + f"{target_kind}:{_quoted(target_value)}"
        )
    raise ValueError("operation kind and payload type do not match")


def _operation_source(operation: UpdateOperation) -> SourceIdentity:
    payload = operation.payload
    if isinstance(payload, CampaignFeatureGrant | CampaignEquipmentAdd):
        return SourceIdentity(SourceKind.CAMPAIGN_PAGE, payload.page_ref)
    if isinstance(payload, SystemsItemAdd):
        return SourceIdentity(SourceKind.SYSTEMS_ENTRY, payload.entry_key)
    if isinstance(payload, EquipmentSafeRelink):
        return payload.target_source
    raise ValueError("unsupported operation payload")


def _attestation(operation: UpdateOperation) -> SourceAttestation:
    payload = operation.payload
    if isinstance(
        payload,
        CampaignFeatureGrant
        | CampaignEquipmentAdd
        | SystemsItemAdd
        | EquipmentSafeRelink,
    ):
        return payload.source
    raise ValueError("unsupported operation payload")


def _operation_target_key(operation: UpdateOperation) -> tuple[str, str]:
    payload = operation.payload
    if isinstance(payload, CampaignFeatureGrant):
        return "feature", payload.feature_id
    if isinstance(payload, CampaignEquipmentAdd | SystemsItemAdd | EquipmentSafeRelink):
        return "equipment", payload.equipment_id
    raise ValueError("unsupported operation payload")


def _operation_intent(operation: UpdateOperation) -> dict[str, Any]:
    """Canonical digest intent, intentionally excluding labels and source bodies."""

    payload = operation.payload
    source_kind, source_value = _source(_operation_source(operation), "source")
    intent: dict[str, Any] = {
        "id": operation_id(operation),
        "kind": OperationKind(operation.kind).value,
        "version": operation.version,
        "source": {"kind": source_kind, "identity": source_value},
        "dependencies": sorted(set(operation.dependencies)),
    }
    if isinstance(payload, CampaignFeatureGrant):
        intent["feature_id"] = payload.feature_id
        intent["resources"] = [
            {"resource_id": item.resource_id, "initial_value": item.initial_value}
            for item in sorted(payload.resources, key=lambda item: item.resource_id)
        ]
    elif isinstance(payload, CampaignEquipmentAdd | SystemsItemAdd):
        intent["equipment_id"] = payload.equipment_id
        intent["inventory_quantity"] = payload.quantity
    elif isinstance(payload, EquipmentSafeRelink):
        target_kind, target_value = _source(payload.target_source, "target_source")
        intent["equipment_id"] = payload.equipment_id
        intent["target"] = {"kind": target_kind, "identity": target_value}
    return intent


def _already_satisfied(
    snapshot: CharacterSnapshot, operation: UpdateOperation
) -> tuple[bool, Diagnostic | None]:
    payload = operation.payload
    op_id = operation_id(operation)
    if isinstance(payload, CampaignFeatureGrant):
        existing = (
            snapshot.features.get(payload.feature_id)
            if isinstance(snapshot.features, Mapping)
            else None
        )
        if existing is None:
            return False, None
        intended_source = SourceIdentity(SourceKind.CAMPAIGN_PAGE, payload.page_ref)
        if (
            _same(existing.source, intended_source)
            and _same(existing.definition, payload.definition)
            and _same(existing.resources, payload.resources)
        ):
            return True, None
        return False, Diagnostic(
            DiagnosticCode.IDENTITY_COLLISION,
            "Feature identity already exists with different intent.",
            op_id,
        )
    if isinstance(payload, CampaignEquipmentAdd | SystemsItemAdd):
        existing = (
            snapshot.equipment.get(payload.equipment_id)
            if isinstance(snapshot.equipment, Mapping)
            else None
        )
        if existing is None:
            return False, None
        intended_source = (
            SourceIdentity(SourceKind.CAMPAIGN_PAGE, payload.page_ref)
            if isinstance(payload, CampaignEquipmentAdd)
            else SourceIdentity(SourceKind.SYSTEMS_ENTRY, payload.entry_key)
        )
        if (
            _same(existing.source, intended_source)
            and _same(existing.definition, payload.definition)
            and _same(existing.inventory_row, payload.inventory_row)
            and existing.quantity == payload.quantity
        ):
            return True, None
        return False, Diagnostic(
            DiagnosticCode.IDENTITY_COLLISION,
            "Equipment identity already exists with different intent.",
            op_id,
        )
    if isinstance(payload, EquipmentSafeRelink):
        existing = (
            snapshot.equipment.get(payload.equipment_id)
            if isinstance(snapshot.equipment, Mapping)
            else None
        )
        if existing is None:
            return False, Diagnostic(
                DiagnosticCode.IDENTITY_COLLISION,
                "Relink requires an existing stable equipment identity.",
                op_id,
            )
        if _same(existing.source, payload.target_source):
            if _same(existing.definition, payload.definition) and _same(
                existing.inventory_row, payload.inventory_after
            ):
                return True, None
            return False, Diagnostic(
                DiagnosticCode.IDENTITY_COLLISION,
                "Relink target already exists with different intent.",
                op_id,
            )
        if existing.source is not None:
            return False, Diagnostic(
                DiagnosticCode.AMBIGUOUS_RELINK,
                "Safe relink cannot replace an existing non-matching source link.",
                op_id,
            )
    return False, None


def _validate_payload(snapshot: CharacterSnapshot, operation: UpdateOperation) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    try:
        op_id = operation_id(operation)
        kind = OperationKind(operation.kind)
        _source(_operation_source(operation), "source")
        attestation = _attestation(operation)
        if not isinstance(attestation, SourceAttestation):
            raise ValueError("source attestation must be a typed SourceAttestation")
        target_type, target_id = _operation_target_key(operation)
        _text(target_id, f"{target_type}_id")
        _canonical_json(getattr(operation.payload, "definition"))
    except (TypeError, ValueError) as exc:
        return [Diagnostic(DiagnosticCode.INVALID_INPUT, str(exc))]

    if not attestation.policy_allowed:
        diagnostics.append(
            Diagnostic(
                DiagnosticCode.SOURCE_POLICY_FAILED,
                "Source policy did not allow this operation.",
                op_id,
            )
        )
    if attestation.ambiguous:
        code = (
            DiagnosticCode.AMBIGUOUS_RELINK
            if kind is OperationKind.EQUIPMENT_SAFE_RELINK
            else DiagnosticCode.AMBIGUOUS_SOURCE
        )
        diagnostics.append(Diagnostic(code, "Exact source identity is ambiguous.", op_id))
    if attestation.choice_bearing:
        diagnostics.append(
            Diagnostic(
                DiagnosticCode.CHOICE_BEARING,
                "Choice-bearing grants are outside V1.",
                op_id,
            )
        )

    payload = operation.payload
    if isinstance(payload, CampaignFeatureGrant):
        seen_resources: set[str] = set()
        for resource in payload.resources:
            try:
                resource_id = _text(resource.resource_id, "resource_id")
                if (
                    isinstance(resource.initial_value, bool)
                    or not isinstance(resource.initial_value, int)
                    or resource.initial_value < 0
                ):
                    raise ValueError("resource initial_value must be a non-negative integer")
            except (TypeError, ValueError) as exc:
                diagnostics.append(Diagnostic(DiagnosticCode.INVALID_INPUT, str(exc), op_id))
                continue
            if resource_id in seen_resources:
                diagnostics.append(
                    Diagnostic(
                        DiagnosticCode.IDENTITY_COLLISION,
                        "A feature grant cannot repeat a resource identity.",
                        op_id,
                    )
                )
            seen_resources.add(resource_id)
    elif isinstance(payload, CampaignEquipmentAdd | SystemsItemAdd):
        try:
            _canonical_json(payload.inventory_row)
            if (
                isinstance(payload.quantity, bool)
                or not isinstance(payload.quantity, int)
                or payload.quantity <= 0
            ):
                raise ValueError("new inventory quantity must be a positive integer")
        except (TypeError, ValueError) as exc:
            diagnostics.append(Diagnostic(DiagnosticCode.INVALID_INPUT, str(exc), op_id))
    elif isinstance(payload, EquipmentSafeRelink):
        try:
            _source(payload.target_source, "target_source")
            _canonical_json(payload.inventory_before)
            _canonical_json(payload.inventory_after)
        except (TypeError, ValueError) as exc:
            diagnostics.append(Diagnostic(DiagnosticCode.INVALID_INPUT, str(exc), op_id))
        existing = (
            snapshot.equipment.get(payload.equipment_id)
            if isinstance(snapshot.equipment, Mapping)
            else None
        )
        if existing is not None and (
            not _same(payload.inventory_before, payload.inventory_after)
            or not _same(existing.inventory_row, payload.inventory_before)
        ):
            diagnostics.append(
                Diagnostic(
                    DiagnosticCode.MUTABLE_STATE_HAZARD,
                    "Safe relink must preserve every inventory-facing field exactly.",
                    op_id,
                )
            )
    return diagnostics


def _topological_order(
    operations: Mapping[str, UpdateOperation]
) -> tuple[list[str], set[str]]:
    indegree = {op_id: 0 for op_id in operations}
    children = {op_id: set() for op_id in operations}
    for op_id, operation in operations.items():
        for dependency in set(operation.dependencies):
            if dependency in operations and dependency != op_id:
                children[dependency].add(op_id)
                indegree[op_id] += 1
    ready = sorted(op_id for op_id, degree in indegree.items() if degree == 0)
    ordered: list[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for child in sorted(children[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()
    cyclic = {op_id for op_id, degree in indegree.items() if degree > 0}
    return ordered + sorted(cyclic), cyclic


def _validate_diff(rows: Iterable[SemanticDiffRow]) -> tuple[SemanticDiffRow, ...]:
    normalized: list[SemanticDiffRow] = []
    identities: set[tuple[SemanticCategory, str]] = set()
    for index, row in enumerate(rows):
        if index >= MAX_DIFF_ROWS:
            raise ValueError("semantic diff exceeds bounded row count")
        if not isinstance(row, SemanticDiffRow):
            raise ValueError("semantic projector must return SemanticDiffRow values")
        try:
            category = SemanticCategory(row.category)
            change = ChangeKind(row.change)
        except ValueError as exc:
            raise ValueError("semantic diff contains an unsupported category or change") from exc
        identity = _text(row.identity, "semantic identity")
        label = _text(row.label, "semantic label")
        before = _human_summary(row.before, "before")
        after = _human_summary(row.after, "after")
        key = (category, identity)
        if key in identities:
            raise ValueError("semantic diff contains duplicate stable identities")
        identities.add(key)
        normalized.append(
            SemanticDiffRow(category, identity, label, change, before, after)
        )
    return tuple(
        sorted(
            normalized,
            key=lambda row: (
                _CATEGORY_ORDER[SemanticCategory(row.category)],
                row.identity,
                row.change,
            ),
        )
    )


_JSON_ATOM_PATTERN = (
    r'(?:"[^"\r\n]{0,64}"|-?\d{1,20}(?:\.\d{1,20})?|true|false|null)'
)
_HASH_ALGORITHM_LABEL_PATTERN = (
    r"(?:sha(?:[-_]?(?:1|224|256|384|512))?|md5|"
    r"blake(?:[-_]?(?:2[bs]?|3))?)"
)
_MACHINE_VALUE_PATTERN = (
    r"(?:[0-9a-f]{8,128}(?![0-9a-f])|"
    r"(?=[A-Za-z0-9+/=_-]{4,128}(?![A-Za-z0-9+/=_-]))"
    r"(?=[A-Za-z0-9+/=_-]{0,127}[0-9+/=_-])"
    r"[A-Za-z0-9+/=_-]{4,128})"
)
_STRUCTURAL_ENTITY_PATTERN = re.compile(
    r"&(?:[A-Za-z][A-Za-z0-9]{1,30}|#[0-9]{1,7}|#[xX][0-9A-Fa-f]{1,6});"
)
_SUSPICIOUS_SUMMARY_PATTERNS = (
    re.compile(
        r'\{[^{}\r\n]{0,200}(?:"[^"\r\n]{1,64}"|[A-Za-z_]'
        r"[A-Za-z0-9_-]{0,63})\s{0,8}:[^{}\r\n]{0,200}\}"
    ),
    re.compile(r"(?:\{\s{0,8}\}|\[\s{0,8}\])"),
    re.compile(
        r"\[\s{0,8}"
        + _JSON_ATOM_PATTERN
        + r"(?:\s{0,8},\s{0,8}"
        + _JSON_ATOM_PATTERN
        + r"){0,31}\s{0,8}\]",
        re.IGNORECASE,
    ),
    re.compile(r'["\'][A-Za-z_][A-Za-z0-9_-]{0,63}["\']\s{0,8}:'),
    re.compile(r"(?<!\S)(?:---|\.\.\.)(?!\S)"),
    re.compile(r"(?i)(?<!\S)%YAML\b"),
    re.compile(
        r"\b(?:yaml|state|config|payload)(?:\s+(?:payload|field|key))?\s+"
        r"[a-z_][a-z0-9_-]{0,63}\s{0,8}:\s{0,8}\S",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:[a-z][a-z0-9_-]{0,63})\s{0,8}:\s{0,8}"
        r"\S"
    ),
    re.compile(
        r"(?<![\w])[a-z][a-z0-9]{0,31}(?:_[a-z0-9]{1,32})+"
        r"\s{0,8}:\s{0,8}\S"
    ),
    re.compile(r"(?i)\bYAML\b[^&!*\r\n]{0,64}[&!*][A-Za-z_][A-Za-z0-9_-]{0,63}"),
    re.compile(
        r"(?i)\b(?:anchor\s{1,8}&|alias\s{1,8}\*|tag\s{1,8}!)"
        r"[A-Za-z_][A-Za-z0-9_-]{0,63}"
    ),
    re.compile(
        r"(?i)(?<![\w])(?!e\.g(?:\.|\b))(?!i\.e(?:\.|\b))"
        r"(?:\$\.)?[A-Za-z_][A-Za-z0-9_]{0,63}"
        r"(?:\.[A-Za-z_][A-Za-z0-9_]{0,63}){1,8}(?![\w])"
    ),
    re.compile(
        r'\$(?:\.[A-Za-z_][A-Za-z0-9_]{0,63}|\[(?:\d{1,6}|["\']'
        r'[A-Za-z_][A-Za-z0-9_]{0,63}["\'])\]){1,8}'
    ),
    re.compile(
        r"\b[A-Za-z_][A-Za-z0-9_]{0,63}"
        r'(?:\[(?:\d{1,6}|["\'][A-Za-z_][A-Za-z0-9_]{0,63}["\'])\]){1,8}'
        r"(?:\.[A-Za-z_][A-Za-z0-9_]{0,63}){0,8}"
    ),
    re.compile(
        r"(?<![:\w])/(?:[A-Za-z_][A-Za-z0-9_~-]{0,63})"
        r"(?:/(?:[A-Za-z_][A-Za-z0-9_~-]{0,63})){1,8}(?![\w/])"
    ),
    re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{32,}(?![0-9a-f])"),
    re.compile(
        r"(?i)\b"
        + _HASH_ALGORITHM_LABEL_PATTERN
        + r"\b(?:\s{0,8}(?::|=)\s{0,8}|\s{1,8})"
        + _MACHINE_VALUE_PATTERN
    ),
    re.compile(
        r"(?i)\b(?:hash|digest|checksum)\b"
        r"\s{0,8}(?::|=)\s{0,8}[A-Za-z0-9+/=_-]{4,128}"
    ),
    re.compile(
        r"(?i)\b(?:hash|digest|checksum)\b\s{1,8}"
        r"[0-9a-f]{8,128}(?![0-9a-f])"
    ),
    re.compile(r"(?i)(?<!\w)(?:[a-z]:[\\/]|\\\\[A-Za-z0-9_.-]{1,64}\\)"),
    re.compile(
        r"(?<![:\w])/(?:[A-Za-z0-9._~-]{1,64}/){1,8}"
        r"[A-Za-z0-9._~-]{1,128}"
    ),
    re.compile(
        r"(?i)(?<![\w.-])[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
        r"\.(?:ya?ml|json)(?![\w.-])"
    ),
    re.compile(r"(?i)\b(?:https?|file|data|javascript):[^\s]{1,480}"),
    re.compile(
        r"</?[A-Za-z][A-Za-z0-9:-]{0,31}(?:\s[^<>\r\n]{0,256})?/?>"
        r"|<(?:!--|\?|!DOCTYPE)[^<>\r\n]{0,256}>",
        re.IGNORECASE,
    ),
    _STRUCTURAL_ENTITY_PATTERN,
    re.compile(
        r"!?\[[^\]\r\n]{0,128}\]"
        r"(?:\([^\)\r\n]{1,256}\)|\[[^\]\r\n]{0,128}\])"
    ),
    re.compile(r"`|~~~|~~[^~\r\n]{1,256}~~"),
    re.compile(
        r"(?<!\w)(?:\*\*|__)[^\r\n]{1,256}(?:\*\*|__)(?!\w)"
        r"|(?<!\w)[*_][^\s*_\r\n][^*_\r\n]{0,128}[*_](?!\w)"
    ),
    re.compile(r"^(?:#{1,6}|>|[-+*]|\d{1,3}[.)])\s"),
)


def _contains_suspicious_summary_content(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SUSPICIOUS_SUMMARY_PATTERNS)


def _human_summary(value: object, field_name: str) -> str:
    text = _text(value, f"semantic {field_name}")
    if "\n" in text or "\r" in text or _contains_suspicious_summary_content(text):
        raise ValueError("semantic summaries must be human text without raw data, hashes, or paths")
    return text


def _validated_state_projection(
    projection: StateImpactProjection,
    *,
    eligible_resources: Sequence[ResourceAddition],
    eligible_inventory: Sequence[tuple[str, int]],
) -> tuple[StateImpact, StateReconciliation]:
    if not isinstance(projection, StateImpactProjection):
        raise TypeError("state projector must return StateImpactProjection")
    try:
        impact = StateImpact(projection.impact)
    except (TypeError, ValueError) as exc:
        raise ValueError("state projector returned an unsupported impact") from exc
    reconciliation = projection.reconciliation
    if not isinstance(reconciliation, StateReconciliation):
        raise TypeError("state projection reconciliation must be typed")
    if not isinstance(reconciliation.resources, tuple) or not isinstance(
        reconciliation.inventory, tuple
    ):
        raise TypeError("state reconciliation rows must be immutable tuples")

    projected_resources: list[ResourceAddition] = []
    projected_resource_keys: set[tuple[str, int]] = set()
    projected_resource_ids: set[str] = set()
    for resource in reconciliation.resources:
        if not isinstance(resource, ResourceAddition):
            raise TypeError("state resource additions must be typed")
        resource_id = _text(resource.resource_id, "projected resource identity")
        if (
            isinstance(resource.initial_value, bool)
            or not isinstance(resource.initial_value, int)
            or resource.initial_value < 0
        ):
            raise ValueError("projected resource values must be non-negative integers")
        key = (resource_id, resource.initial_value)
        if resource_id in projected_resource_ids:
            raise ValueError("state projection repeats a resource addition")
        projected_resource_ids.add(resource_id)
        projected_resource_keys.add(key)
        projected_resources.append(deepcopy(resource))

    projected_inventory: list[tuple[str, int]] = []
    projected_inventory_ids: set[str] = set()
    for row in reconciliation.inventory:
        if not isinstance(row, tuple) or len(row) != 2:
            raise TypeError("state inventory additions must be (equipment_id, quantity) tuples")
        equipment_id, quantity = row
        equipment_id = _text(equipment_id, "projected equipment identity")
        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity <= 0
        ):
            raise ValueError("projected inventory quantity must be a positive integer")
        if equipment_id in projected_inventory_ids:
            raise ValueError("state projection repeats an inventory identity")
        projected_inventory_ids.add(equipment_id)
        projected_inventory.append((equipment_id, quantity))

    normalized = StateReconciliation(
        tuple(sorted(projected_resources, key=lambda item: item.resource_id)),
        tuple(sorted(projected_inventory)),
    )
    expected_resource_keys = sorted(
        (item.resource_id, item.initial_value) for item in eligible_resources
    )
    actual_resource_keys = sorted(projected_resource_keys)
    expected_inventory = sorted(eligible_inventory)
    actual_inventory = sorted(projected_inventory)
    has_eligible_additions = bool(expected_resource_keys or expected_inventory)

    if impact is StateImpact.PRESERVE_EXACT:
        if normalized.resources or normalized.inventory:
            raise ValueError("preserve_exact requires empty reconciliation")
        if has_eligible_additions:
            raise ValueError("state projection omitted required eligible additions")
    elif not has_eligible_additions:
        raise ValueError("reconcile_required has no eligible additions")

    if (
        expected_resource_keys != actual_resource_keys
        or expected_inventory != actual_inventory
    ):
        raise ValueError("state reconciliation does not match the eligible operation envelope")
    return impact, normalized


def _blocked_plan(
    snapshot: CharacterSnapshot,
    operations: Sequence[PlannedOperation],
    diagnostics: Sequence[Diagnostic],
) -> CharacterUpdatePlan:
    blocked = tuple(
        PlannedOperation(
            item.operation_id,
            item.kind,
            item.version,
            item.dependencies,
            OperationStatus.BLOCKED,
        )
        for item in operations
    )
    return CharacterUpdatePlan(
        PLANNER_VERSION,
        snapshot.target_identity,
        snapshot.baseline_identity,
        PlanStatus.BLOCKED,
        blocked,
        StateImpact.PRESERVE_EXACT,
        StateReconciliation(),
        (),
        None,
        None,
        None,
        tuple(diagnostics),
    )


def plan_character_update(
    snapshot: CharacterSnapshot,
    operations: Sequence[UpdateOperation],
    *,
    adapter: OperationAdapter,
    derive: CharacterDeriver,
    project_state_impact: StateImpactProjector,
    project_semantics: SemanticProjector,
) -> CharacterUpdatePlan:
    """Build an all-or-nothing deterministic V1 character update plan.

    Every caller-owned value is deep-copied before inspection or before it is
    supplied to a seam.  A valid plan calls ``derive`` exactly once and
    ``project_state_impact`` and ``project_semantics`` exactly once, including
    an already-satisfied no-op. Blocked input calls none of those seams.
    """

    local_snapshot = deepcopy(snapshot)
    local_operations = tuple(deepcopy(tuple(operations)))
    diagnostics: list[Diagnostic] = []
    known_state_resource_ids: frozenset[str] = frozenset()

    try:
        _text(local_snapshot.target_identity, "target_identity")
        _text(local_snapshot.baseline_identity, "baseline_identity")
        _canonical_json(local_snapshot.definition)
        if local_snapshot.state is None or not local_snapshot.whole_state:
            diagnostics.append(
                Diagnostic(
                    DiagnosticCode.MISSING_WHOLE_STATE,
                    "A complete whole-character state snapshot is required.",
                )
            )
        else:
            _canonical_json(local_snapshot.state)
        if not isinstance(local_snapshot.features, Mapping):
            raise ValueError("features must be an exact identity mapping")
        for key, existing in local_snapshot.features.items():
            if not isinstance(existing, ExistingFeature) or key != existing.feature_id:
                raise ValueError(
                    "feature index keys must exactly match typed feature identities"
                )
            _text(key, "existing feature identity")
            _source(existing.source, "existing feature source")
            _canonical_json(existing.definition)
            _canonical_json(existing.resources)
        if not isinstance(local_snapshot.equipment, Mapping):
            raise ValueError("equipment must be an exact identity mapping")
        for key, existing in local_snapshot.equipment.items():
            if not isinstance(existing, ExistingEquipment) or key != existing.equipment_id:
                raise ValueError(
                    "equipment index keys must exactly match typed equipment identities"
                )
            _text(key, "existing equipment identity")
            if existing.source is not None:
                _source(existing.source, "existing equipment source")
            _canonical_json(existing.definition)
            _canonical_json(existing.inventory_row)
            if (
                isinstance(existing.quantity, bool)
                or not isinstance(existing.quantity, int)
                or existing.quantity <= 0
            ):
                raise ValueError("existing equipment quantity must be a positive integer")
        for resource_id in local_snapshot.state_resource_ids:
            _text(resource_id, "existing resource identity")
        known_state_resource_ids = frozenset(local_snapshot.state_resource_ids)
        if local_snapshot.system != SUPPORTED_SYSTEM:
            diagnostics.append(
                Diagnostic(
                    DiagnosticCode.UNSUPPORTED_SYSTEM,
                    "V1 accepts only canonical DND-5E targets.",
                )
            )
    except (TypeError, ValueError) as exc:
        diagnostics.append(Diagnostic(DiagnosticCode.INVALID_INPUT, str(exc)))

    if not local_operations or len(local_operations) > MAX_OPERATIONS:
        diagnostics.append(
            Diagnostic(
                DiagnosticCode.INVALID_INPUT,
                "operation count must be between 1 and 128",
            )
        )

    by_id: dict[str, UpdateOperation] = {}
    duplicate_ids: set[str] = set()
    for operation in local_operations:
        if not isinstance(operation, UpdateOperation):
            diagnostics.append(
                Diagnostic(
                    DiagnosticCode.INVALID_INPUT,
                    "operations must be typed UpdateOperation values",
                )
            )
            continue
        try:
            OperationKind(operation.kind)
        except (TypeError, ValueError):
            diagnostics.append(
                Diagnostic(DiagnosticCode.UNSUPPORTED_OPERATION, "Unknown V1 operation kind.")
            )
            continue
        if isinstance(operation.version, bool) or operation.version != PLANNER_VERSION:
            diagnostics.append(
                Diagnostic(DiagnosticCode.UNSUPPORTED_VERSION, "Unknown operation version.")
            )
            continue
        if not isinstance(operation.dependencies, tuple):
            diagnostics.append(
                Diagnostic(
                    DiagnosticCode.INVALID_INPUT,
                    "dependencies must be an immutable tuple of operation identities",
                )
            )
            continue
        if len(operation.dependencies) > MAX_DEPENDENCIES:
            diagnostics.append(
                Diagnostic(DiagnosticCode.INVALID_INPUT, "dependency count exceeds the V1 bound")
            )
            continue
        if any(not isinstance(item, str) for item in operation.dependencies):
            diagnostics.append(
                Diagnostic(
                    DiagnosticCode.MISSING_DEPENDENCY,
                    "Dependency identities must be strings.",
                )
            )
            continue
        try:
            op_id = operation_id(operation)
        except (TypeError, ValueError) as exc:
            diagnostics.append(Diagnostic(DiagnosticCode.INVALID_INPUT, str(exc)))
            continue
        if op_id in by_id:
            duplicate_ids.add(op_id)
        else:
            by_id[op_id] = operation
        diagnostics.extend(_validate_payload(local_snapshot, operation))

    for op_id in sorted(duplicate_ids):
        diagnostics.append(
            Diagnostic(
                DiagnosticCode.DUPLICATE_OPERATION,
                "Duplicate operation identity.",
                op_id,
            )
        )

    target_owners: dict[tuple[str, str], str] = {}
    resource_owners: dict[str, str] = {}
    for op_id, operation in sorted(by_id.items()):
        try:
            target_key = _operation_target_key(operation)
            owner = target_owners.get(target_key)
            if owner is not None and owner != op_id:
                diagnostics.append(
                    Diagnostic(
                        DiagnosticCode.CONFLICTING_INTENT,
                        "Multiple operations target one stable identity.",
                        op_id,
                    )
                )
            target_owners[target_key] = op_id
            if isinstance(operation.payload, CampaignFeatureGrant):
                for resource in operation.payload.resources:
                    owner = resource_owners.get(resource.resource_id)
                    if owner is not None and owner != op_id:
                        diagnostics.append(
                            Diagnostic(
                                DiagnosticCode.CONFLICTING_INTENT,
                                "Multiple operations add one resource identity.",
                                op_id,
                            )
                        )
                    resource_owners[resource.resource_id] = op_id
        except (TypeError, ValueError):
            pass

    for op_id, operation in sorted(by_id.items()):
        clean_dependencies: set[str] = set()
        for dependency in operation.dependencies:
            if not isinstance(dependency, str) or not dependency.strip():
                diagnostics.append(
                    Diagnostic(
                        DiagnosticCode.MISSING_DEPENDENCY,
                        "Dependency identities must be non-empty strings.",
                        op_id,
                    )
                )
                continue
            clean_dependencies.add(dependency)
        if op_id in clean_dependencies:
            diagnostics.append(
                Diagnostic(
                    DiagnosticCode.SELF_DEPENDENCY,
                    "An operation cannot depend on itself.",
                    op_id,
                )
            )
        for dependency in sorted(clean_dependencies - set(by_id)):
            diagnostics.append(
                Diagnostic(
                    DiagnosticCode.OUT_OF_REQUEST_DEPENDENCY,
                    "Dependency is outside this request.",
                    op_id,
                )
            )

    ordered_ids, cyclic_ids = _topological_order(by_id)
    for op_id in sorted(cyclic_ids):
        diagnostics.append(
            Diagnostic(
                DiagnosticCode.CYCLIC_DEPENDENCY,
                "Dependency cycle blocks the whole plan.",
                op_id,
            )
        )

    statuses: dict[str, OperationStatus] = {}
    for op_id in ordered_ids:
        operation = by_id[op_id]
        try:
            satisfied, collision = _already_satisfied(local_snapshot, operation)
        except (TypeError, ValueError) as exc:
            diagnostics.append(Diagnostic(DiagnosticCode.INVALID_INPUT, str(exc), op_id))
            satisfied, collision = False, None
        if collision is not None:
            diagnostics.append(collision)
        statuses[op_id] = (
            OperationStatus.ALREADY_SATISFIED if satisfied else OperationStatus.READY
        )
        if (
            statuses[op_id] is OperationStatus.READY
            and isinstance(operation.payload, CampaignFeatureGrant)
        ):
            for resource in operation.payload.resources:
                if resource.resource_id in known_state_resource_ids:
                    diagnostics.append(
                        Diagnostic(
                            DiagnosticCode.IDENTITY_COLLISION,
                            "Resource additions require wholly new resource identities.",
                            op_id,
                        )
                    )

    planned = tuple(
        PlannedOperation(
            op_id,
            by_id[op_id].kind,
            by_id[op_id].version,
            tuple(sorted(set(by_id[op_id].dependencies))),
            statuses.get(op_id, OperationStatus.BLOCKED),
        )
        for op_id in ordered_ids
    )
    if diagnostics:
        return _blocked_plan(local_snapshot, planned, diagnostics)

    candidate: Mapping[str, Any] = deepcopy(local_snapshot.definition)
    resources: list[ResourceAddition] = []
    inventory: list[tuple[str, int]] = []
    for op_id in ordered_ids:
        operation = by_id[op_id]
        if statuses[op_id] is OperationStatus.ALREADY_SATISFIED:
            continue
        try:
            adapted = adapter(deepcopy(candidate), deepcopy(operation))
            _canonical_json(adapted)
            candidate = deepcopy(adapted)
        except Exception as exc:  # pure seam failures become bounded plan diagnostics
            return _blocked_plan(
                local_snapshot,
                planned,
                [
                    Diagnostic(
                        DiagnosticCode.ADAPTER_FAILED,
                        f"Adapter rejected operation: {type(exc).__name__}",
                        op_id,
                    )
                ],
            )
        payload = operation.payload
        if isinstance(payload, CampaignFeatureGrant):
            resources.extend(deepcopy(payload.resources))
        elif isinstance(payload, CampaignEquipmentAdd | SystemsItemAdd):
            inventory.append((payload.equipment_id, payload.quantity))

    assert local_snapshot.state is not None
    try:
        derived = derive(deepcopy(candidate), deepcopy(local_snapshot.state))
        if not isinstance(derived, DerivationResult):
            raise TypeError("deriver must return DerivationResult")
        _canonical_json(derived.character)
    except Exception as exc:
        return _blocked_plan(
            local_snapshot,
            planned,
            [
                Diagnostic(
                    DiagnosticCode.DERIVATION_FAILED,
                    f"Derivation failed: {type(exc).__name__}",
                )
            ],
        )
    if derived.warnings:
        return _blocked_plan(
            local_snapshot,
            planned,
            [
                Diagnostic(
                    DiagnosticCode.DERIVATION_WARNING,
                    "Derivation returned warnings.",
                )
            ],
        )

    ready_operations = tuple(
        deepcopy(by_id[op_id])
        for op_id in ordered_ids
        if statuses[op_id] is OperationStatus.READY
    )
    state_projection: StateImpactProjection | None = None
    state_projection_error: Exception | None = None
    try:
        state_projection = project_state_impact(
            deepcopy(local_snapshot.state),
            deepcopy(derived.character),
            deepcopy(ready_operations),
        )
    except Exception as exc:
        state_projection_error = exc

    semantic_projection: SemanticProjection | None = None
    semantic_projection_error: Exception | None = None
    semantic_diff: tuple[SemanticDiffRow, ...] = ()
    try:
        semantic_projection = project_semantics(
            deepcopy(local_snapshot.definition),
            deepcopy(derived.character),
            deepcopy(local_snapshot.state),
        )
        if not isinstance(semantic_projection, SemanticProjection):
            raise TypeError("semantic projector must return SemanticProjection")
        semantic_diff = _validate_diff(semantic_projection.rows)
    except Exception as exc:
        semantic_projection_error = exc

    if state_projection_error is not None:
        return _blocked_plan(
            local_snapshot,
            planned,
            [
                Diagnostic(
                    DiagnosticCode.STATE_IMPACT_FAILED,
                    "State-impact projection failed: "
                    f"{type(state_projection_error).__name__}",
                )
            ],
        )
    if semantic_projection_error is not None:
        return _blocked_plan(
            local_snapshot,
            planned,
            [
                Diagnostic(
                    DiagnosticCode.PROJECTION_FAILED,
                    "Semantic projection failed: "
                    f"{type(semantic_projection_error).__name__}",
                )
            ],
        )
    assert state_projection is not None
    assert semantic_projection is not None
    if not isinstance(state_projection, StateImpactProjection):
        return _blocked_plan(
            local_snapshot,
            planned,
            [
                Diagnostic(
                    DiagnosticCode.STATE_IMPACT_FAILED,
                    "State-impact projector must return StateImpactProjection.",
                )
            ],
        )
    if not isinstance(state_projection.warnings, tuple) or not isinstance(
        state_projection.hazards, tuple
    ):
        return _blocked_plan(
            local_snapshot,
            planned,
            [
                Diagnostic(
                    DiagnosticCode.STATE_IMPACT_FAILED,
                    "State-impact warnings and hazards must be immutable tuples.",
                )
            ],
        )
    if state_projection.warnings:
        return _blocked_plan(
            local_snapshot,
            planned,
            [
                Diagnostic(
                    DiagnosticCode.STATE_IMPACT_WARNING,
                    "State-impact projection returned warnings.",
                )
            ],
        )
    if state_projection.hazards:
        return _blocked_plan(
            local_snapshot,
            planned,
            [
                Diagnostic(
                    DiagnosticCode.STATE_IMPACT_HAZARD,
                    "State-impact projection returned mutation hazards.",
                )
            ],
        )
    try:
        state_impact, reconciliation = _validated_state_projection(
            state_projection,
            eligible_resources=resources,
            eligible_inventory=inventory,
        )
    except (TypeError, ValueError):
        return _blocked_plan(
            local_snapshot,
            planned,
            [
                Diagnostic(
                    DiagnosticCode.STATE_IMPACT_MISMATCH,
                    "State-impact projection does not match the eligible envelope.",
                )
            ],
        )
    if semantic_projection.warnings:
        return _blocked_plan(
            local_snapshot,
            planned,
            [
                Diagnostic(
                    DiagnosticCode.PROJECTION_WARNING,
                    "Semantic projection returned warnings.",
                )
            ],
        )

    effective_count = sum(
        status is OperationStatus.READY for status in statuses.values()
    )
    if effective_count == 0 and semantic_diff:
        return _blocked_plan(
            local_snapshot,
            planned,
            [
                Diagnostic(
                    DiagnosticCode.UNEXPLAINED_SEMANTIC_CHANGE,
                    "Already-satisfied intent must have an empty semantic diff.",
                )
            ],
        )

    status = PlanStatus.NO_OP if effective_count == 0 else PlanStatus.READY
    digest_basis = {
        "version": PLANNER_VERSION,
        "target_identity": local_snapshot.target_identity,
        "baseline_identity": local_snapshot.baseline_identity,
        "operations": [_operation_intent(by_id[op_id]) for op_id in ordered_ids],
        "state_impact": state_impact.value,
        "reconciliation": {
            "resources": [
                {"resource_id": item.resource_id, "initial_value": item.initial_value}
                for item in reconciliation.resources
            ],
            "inventory": [
                {"equipment_id": equipment_id, "quantity": quantity}
                for equipment_id, quantity in reconciliation.inventory
            ],
        },
        "semantic_diff": [
            {
                "category": SemanticCategory(row.category).value,
                "identity": row.identity,
                "change": ChangeKind(row.change).value,
                "before": row.before,
                "after": row.after,
            }
            for row in semantic_diff
        ],
    }
    digest = hashlib.sha256(
        _DIGEST_DOMAIN + _canonical_json(digest_basis).encode("utf-8")
    ).hexdigest()
    return CharacterUpdatePlan(
        PLANNER_VERSION,
        local_snapshot.target_identity,
        local_snapshot.baseline_identity,
        status,
        planned,
        state_impact,
        reconciliation,
        semantic_diff,
        digest,
        deepcopy(candidate),
        deepcopy(derived.character),
        (),
    )


__all__ = [
    "CampaignEquipmentAdd",
    "CampaignFeatureGrant",
    "ChangeKind",
    "CharacterDeriver",
    "CharacterSnapshot",
    "CharacterUpdatePlan",
    "DerivationResult",
    "Diagnostic",
    "DiagnosticCode",
    "EquipmentSafeRelink",
    "ExistingEquipment",
    "ExistingFeature",
    "OperationAdapter",
    "OperationKind",
    "OperationStatus",
    "PlanStatus",
    "PlannedOperation",
    "ResourceAddition",
    "SemanticCategory",
    "SemanticDiffRow",
    "SemanticProjection",
    "SemanticProjector",
    "SourceAttestation",
    "SourceIdentity",
    "SourceKind",
    "StateImpact",
    "StateImpactProjection",
    "StateImpactProjector",
    "StateReconciliation",
    "SystemsItemAdd",
    "UpdateOperation",
    "operation_id",
    "plan_character_update",
]
