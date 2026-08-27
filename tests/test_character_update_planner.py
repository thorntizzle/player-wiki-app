from __future__ import annotations

from copy import deepcopy
import ast
import builtins
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest

import player_wiki.character_update_planner as planner_module
from player_wiki.character_update_planner import (
    CampaignEquipmentAdd,
    CampaignFeatureGrant,
    ChangeKind,
    CharacterSnapshot,
    DerivationResult,
    DiagnosticCode,
    EquipmentSafeRelink,
    ExistingEquipment,
    ExistingFeature,
    OperationKind,
    OperationStatus,
    PlanStatus,
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
    plan_character_update,
)


def _snapshot(**changes):
    values = {
        "target_identity": "character:hero",
        "baseline_identity": "revision:7",
        "system": "DND-5E",
        "definition": {"name": "Hero", "features": [], "equipment": []},
        "state": {"vitals": {"current_hp": 9}, "notes": "keep me"},
    }
    values.update(changes)
    return CharacterSnapshot(**values)


def _feature(
    page_ref="Mechanics/Rewards/Ember Gift",
    feature_id="feature:ember-gift",
    *,
    resources=(),
    source=SourceAttestation(),
    definition=None,
    dependencies=(),
):
    return UpdateOperation(
        OperationKind.CAMPAIGN_FEATURE_GRANT,
        CampaignFeatureGrant(
            page_ref,
            feature_id,
            definition or {"id": feature_id, "name": "Ember Gift"},
            "Ember Gift",
            tuple(resources),
            source,
        ),
        tuple(dependencies),
    )


def _campaign_equipment(
    page_ref="Items/Glass Sword",
    equipment_id="equipment:glass-sword",
    *,
    quantity=1,
    source=SourceAttestation(),
    definition=None,
    inventory_row=None,
    dependencies=(),
):
    return UpdateOperation(
        OperationKind.CAMPAIGN_EQUIPMENT_ADD,
        CampaignEquipmentAdd(
            page_ref,
            equipment_id,
            definition or {"id": equipment_id, "name": "Glass Sword"},
            inventory_row or {"id": equipment_id, "name": "Glass Sword"},
            quantity,
            "Glass Sword",
            source,
        ),
        tuple(dependencies),
    )


def _systems_equipment(
    entry_key="dnd5e|item|phb|rope-hempen-50-feet",
    equipment_id="equipment:rope",
    *,
    dependencies=(),
):
    return UpdateOperation(
        OperationKind.SYSTEMS_ITEM_ADD,
        SystemsItemAdd(
            entry_key,
            equipment_id,
            {"name": "Rope", "id": equipment_id},
            {"name": "Rope", "id": equipment_id},
            1,
            "Rope",
        ),
        tuple(dependencies),
    )


def _relink(*, after=None, source=SourceAttestation(), dependencies=()):
    before = {"id": "equipment:blade", "quantity": 1, "equipped": False}
    return UpdateOperation(
        OperationKind.EQUIPMENT_SAFE_RELINK,
        EquipmentSafeRelink(
            "equipment:blade",
            SourceIdentity(SourceKind.SYSTEMS_ENTRY, "dnd5e|item|phb|longsword"),
            {"id": "equipment:blade", "name": "Blade", "entry_key": "dnd5e|item|phb|longsword"},
            before,
            before if after is None else after,
            "Blade",
            source,
        ),
        tuple(dependencies),
    )


class Harness:
    def __init__(self, rows=(), state_projection=None):
        self.adapter_calls = []
        self.derive_calls = 0
        self.state_calls = 0
        self.projection_calls = 0
        self.rows = tuple(rows)
        self.state_projection = state_projection

    def adapter(self, definition, operation):
        self.adapter_calls.append(operation_id(operation))
        result = deepcopy(definition)
        payload = operation.payload
        if isinstance(payload, CampaignFeatureGrant):
            result.setdefault("features", []).append(deepcopy(dict(payload.definition)))
        elif isinstance(payload, (CampaignEquipmentAdd, SystemsItemAdd)):
            result.setdefault("equipment", []).append(deepcopy(dict(payload.definition)))
        elif isinstance(payload, EquipmentSafeRelink):
            result.setdefault("relinks", []).append(
                {"id": payload.equipment_id, "target": payload.target_source.value}
            )
        return result

    def derive(self, definition, state):
        self.derive_calls += 1
        character = deepcopy(definition)
        character["observed_hp"] = state["vitals"]["current_hp"]
        return DerivationResult(character)

    def project_state(self, state, derived, operations):
        assert self.derive_calls == 1
        self.state_calls += 1
        if self.state_projection is not None:
            return deepcopy(self.state_projection)
        resources = []
        inventory = []
        for operation in operations:
            payload = operation.payload
            if isinstance(payload, CampaignFeatureGrant):
                resources.extend(deepcopy(payload.resources))
            elif isinstance(payload, (CampaignEquipmentAdd, SystemsItemAdd)):
                inventory.append((payload.equipment_id, payload.quantity))
        reconciliation = StateReconciliation(
            tuple(sorted(resources, key=lambda item: item.resource_id)),
            tuple(sorted(inventory)),
        )
        impact = (
            StateImpact.RECONCILE_REQUIRED
            if reconciliation.resources or reconciliation.inventory
            else StateImpact.PRESERVE_EXACT
        )
        return StateImpactProjection(impact, reconciliation)

    def project(self, baseline, derived, state):
        self.projection_calls += 1
        assert state["notes"] == "keep me"
        return SemanticProjection(self.rows)


def _plan(snapshot, operations, harness=None):
    harness = harness or Harness()
    plan = plan_character_update(
        snapshot,
        operations,
        adapter=harness.adapter,
        derive=harness.derive,
        project_state_impact=harness.project_state,
        project_semantics=harness.project,
    )
    return plan, harness


def _codes(plan):
    return {diagnostic.code for diagnostic in plan.diagnostics}


def test_v1_schema_exports_exact_operation_and_semantic_category_sets():
    assert {kind.value for kind in OperationKind} == {
        "campaign_feature_grant",
        "campaign_equipment_add",
        "systems_item_add",
        "equipment_safe_relink",
    }
    assert {category.value for category in SemanticCategory} == {
        "features",
        "equipment/inventory",
        "spells",
        "attacks",
        "Armor Class",
        "resources",
    }
    assert {kind.value for kind in SourceKind} == {"campaign_page", "systems_entry"}


@pytest.mark.parametrize("kind", ["spell_add", "remove", "manual_update", "xianxia_grant"])
def test_unknown_or_excluded_operation_types_block_before_seams(kind):
    plan, harness = _plan(
        _snapshot(),
        [UpdateOperation(kind, object())],
    )
    assert plan.status is PlanStatus.BLOCKED
    assert DiagnosticCode.UNSUPPORTED_OPERATION in _codes(plan)
    assert harness.adapter_calls == []
    assert harness.derive_calls == harness.projection_calls == 0


def test_non_dnd_target_blocks_before_all_seams():
    plan, harness = _plan(_snapshot(system="Xianxia"), [_feature()])
    assert DiagnosticCode.UNSUPPORTED_SYSTEM in _codes(plan)
    assert plan.status is PlanStatus.BLOCKED
    assert harness.adapter_calls == []
    assert harness.derive_calls == harness.projection_calls == 0


def test_operation_ids_use_exact_source_identity_and_relink_target():
    feature = _feature(page_ref="Mechanics/A B")
    relink = _relink()
    assert operation_id(feature) == (
        "character-update:v1:campaign_feature_grant:campaign_page:Mechanics%2FA%20B"
    )
    assert "equipment%3Ablade" in operation_id(relink)
    assert "systems_entry" in operation_id(relink)
    assert "Items%2FOld%20Blade" not in operation_id(relink)
    assert "dnd5e%7Citem%7Cphb%7Clongsword" in operation_id(relink)


def test_dependency_order_is_canonical_with_lexical_tie_breaks_and_deduped_edges():
    first = _feature(page_ref="Mechanics/B", feature_id="feature:b")
    second = _systems_equipment(entry_key="dnd5e|item|phb|a", equipment_id="equipment:a")
    dependent = _campaign_equipment(
        page_ref="Items/C",
        equipment_id="equipment:c",
        dependencies=(operation_id(first), operation_id(first), operation_id(second)),
    )
    plan, harness = _plan(_snapshot(), [dependent, first, second])
    expected_roots = sorted([operation_id(first), operation_id(second)])
    assert plan.status is PlanStatus.READY
    assert [item.operation_id for item in plan.operations] == expected_roots + [
        operation_id(dependent)
    ]
    assert harness.adapter_calls == expected_roots + [operation_id(dependent)]
    assert plan.operations[-1].dependencies == tuple(sorted(set(dependent.dependencies)))


@pytest.mark.parametrize(
    ("dependencies", "code"),
    [
        (("",), DiagnosticCode.MISSING_DEPENDENCY),
        (("outside",), DiagnosticCode.OUT_OF_REQUEST_DEPENDENCY),
    ],
)
def test_missing_and_out_of_request_dependencies_block_all_operations(dependencies, code):
    operation = _feature(dependencies=dependencies)
    plan, harness = _plan(_snapshot(), [operation])
    assert plan.status is PlanStatus.BLOCKED
    assert code in _codes(plan)
    assert all(item.status is OperationStatus.BLOCKED for item in plan.operations)
    assert harness.derive_calls == 0


def test_self_and_cyclic_dependencies_block_whole_plan():
    base_a = _feature(page_ref="Mechanics/A", feature_id="feature:a")
    base_b = _feature(page_ref="Mechanics/B", feature_id="feature:b")
    self_dependent = _feature(
        page_ref="Mechanics/Self",
        feature_id="feature:self",
    )
    self_dependent = UpdateOperation(
        self_dependent.kind,
        self_dependent.payload,
        (operation_id(self_dependent),),
    )
    self_plan, _ = _plan(_snapshot(), [self_dependent])
    assert DiagnosticCode.SELF_DEPENDENCY in _codes(self_plan)

    a = UpdateOperation(base_a.kind, base_a.payload, (operation_id(base_b),))
    b = UpdateOperation(base_b.kind, base_b.payload, (operation_id(base_a),))
    cycle_plan, _ = _plan(_snapshot(), [b, a])
    assert DiagnosticCode.CYCLIC_DEPENDENCY in _codes(cycle_plan)
    assert cycle_plan.digest is None


def test_duplicate_conflict_ambiguity_policy_choice_and_version_are_all_or_nothing():
    duplicate = _feature()
    ambiguous = _campaign_equipment(source=SourceAttestation(ambiguous=True))
    denied = _systems_equipment()
    denied = UpdateOperation(
        denied.kind,
        SystemsItemAdd(
            denied.payload.entry_key,
            denied.payload.equipment_id,
            denied.payload.definition,
            denied.payload.inventory_row,
            source=SourceAttestation(policy_allowed=False),
        ),
    )
    choice = _feature(
        page_ref="Mechanics/Choice",
        feature_id="feature:choice",
        source=SourceAttestation(choice_bearing=True),
    )
    bad_version = UpdateOperation(
        OperationKind.CAMPAIGN_FEATURE_GRANT,
        CampaignFeatureGrant("Mechanics/V2", "feature:v2", {"id": "feature:v2"}),
        version=2,
    )
    plan, harness = _plan(
        _snapshot(), [duplicate, duplicate, ambiguous, denied, choice, bad_version]
    )
    assert {
        DiagnosticCode.DUPLICATE_OPERATION,
        DiagnosticCode.AMBIGUOUS_SOURCE,
        DiagnosticCode.SOURCE_POLICY_FAILED,
        DiagnosticCode.CHOICE_BEARING,
        DiagnosticCode.UNSUPPORTED_VERSION,
    } <= _codes(plan)
    assert plan.status is PlanStatus.BLOCKED
    assert harness.adapter_calls == []


def test_two_different_sources_cannot_target_one_feature_identity():
    left = _feature(page_ref="Mechanics/Left", feature_id="feature:same")
    right = _feature(page_ref="Mechanics/Right", feature_id="feature:same")
    plan, _ = _plan(_snapshot(), [right, left])
    assert DiagnosticCode.CONFLICTING_INTENT in _codes(plan)


def test_exact_existing_intent_is_noop_but_still_derives_and_projects_once():
    operation = _feature()
    payload = operation.payload
    snapshot = _snapshot(
        features={
            payload.feature_id: ExistingFeature(
                payload.feature_id,
                SourceIdentity(SourceKind.CAMPAIGN_PAGE, payload.page_ref),
                payload.definition,
            )
        }
    )
    plan, harness = _plan(snapshot, [operation])
    assert plan.status is PlanStatus.NO_OP
    assert plan.operations[0].status is OperationStatus.ALREADY_SATISFIED
    assert plan.state_impact is StateImpact.PRESERVE_EXACT
    assert plan.semantic_diff == ()
    assert harness.adapter_calls == []
    assert harness.derive_calls == harness.projection_calls == 1


def test_exact_existing_feature_and_resource_intent_is_noop_not_a_resource_collision():
    resource = ResourceAddition("resource:ember", 2, "Ember Charges")
    operation = _feature(resources=(resource,))
    payload = operation.payload
    snapshot = _snapshot(
        features={
            payload.feature_id: ExistingFeature(
                payload.feature_id,
                SourceIdentity(SourceKind.CAMPAIGN_PAGE, payload.page_ref),
                payload.definition,
                (resource,),
            )
        },
        state_resource_ids=frozenset({resource.resource_id}),
    )
    plan, _ = _plan(snapshot, [operation])
    assert plan.status is PlanStatus.NO_OP
    assert plan.state_impact is StateImpact.PRESERVE_EXACT


def test_existing_identity_with_different_intent_blocks():
    operation = _feature()
    snapshot = _snapshot(
        features={
            "feature:ember-gift": ExistingFeature(
                "feature:ember-gift",
                SourceIdentity(SourceKind.CAMPAIGN_PAGE, "Mechanics/Other"),
                {"id": "feature:ember-gift"},
            )
        }
    )
    plan, _ = _plan(snapshot, [operation])
    assert DiagnosticCode.IDENTITY_COLLISION in _codes(plan)


def test_existing_equipment_quantity_merge_is_an_identity_collision():
    operation = _campaign_equipment(quantity=2)
    payload = operation.payload
    snapshot = _snapshot(
        equipment={
            payload.equipment_id: ExistingEquipment(
                payload.equipment_id,
                SourceIdentity(SourceKind.CAMPAIGN_PAGE, payload.page_ref),
                payload.definition,
                payload.inventory_row,
                1,
            )
        }
    )
    plan, _ = _plan(snapshot, [operation])
    assert DiagnosticCode.IDENTITY_COLLISION in _codes(plan)


def test_definition_only_feature_and_safe_relink_preserve_state_exactly():
    existing = ExistingEquipment(
        "equipment:blade",
        None,
        {"id": "equipment:blade", "name": "Old Blade"},
        {"id": "equipment:blade", "quantity": 1, "equipped": False},
    )
    plan, _ = _plan(
        _snapshot(equipment={existing.equipment_id: existing}),
        [_feature(), _relink()],
    )
    assert plan.status is PlanStatus.READY
    assert plan.state_impact is StateImpact.PRESERVE_EXACT
    assert plan.reconciliation.resources == plan.reconciliation.inventory == ()


def test_safe_relink_refuses_conflicting_link_and_exact_target_is_noop():
    operation = _relink()
    payload = operation.payload
    inventory = deepcopy(payload.inventory_after)
    conflicting = ExistingEquipment(
        payload.equipment_id,
        SourceIdentity(SourceKind.CAMPAIGN_PAGE, "Items/Other Blade"),
        payload.definition,
        inventory,
    )
    blocked, blocked_harness = _plan(
        _snapshot(equipment={conflicting.equipment_id: conflicting}),
        [operation],
    )
    assert DiagnosticCode.AMBIGUOUS_RELINK in _codes(blocked)
    assert blocked_harness.adapter_calls == []

    satisfied = ExistingEquipment(
        payload.equipment_id,
        payload.target_source,
        payload.definition,
        inventory,
    )
    noop, noop_harness = _plan(
        _snapshot(equipment={satisfied.equipment_id: satisfied}),
        [operation],
    )
    assert noop.status is PlanStatus.NO_OP
    assert noop.operations[0].status is OperationStatus.ALREADY_SATISFIED
    assert noop_harness.adapter_calls == []
    assert noop_harness.derive_calls == 1
    assert noop_harness.state_calls == noop_harness.projection_calls == 1


def test_new_resources_and_inventory_rows_are_the_only_reconcile_cases():
    resource = ResourceAddition("resource:ember", 2, "Ember Charges")
    feature_plan, _ = _plan(_snapshot(), [_feature(resources=(resource,))])
    assert feature_plan.state_impact is StateImpact.RECONCILE_REQUIRED
    assert feature_plan.reconciliation.resources == (resource,)

    equipment_plan, _ = _plan(_snapshot(), [_campaign_equipment(quantity=3)])
    assert equipment_plan.state_impact is StateImpact.RECONCILE_REQUIRED
    assert equipment_plan.reconciliation.inventory == (("equipment:glass-sword", 3),)


def test_state_impact_seam_runs_once_after_derivation_for_valid_mixed_additions():
    resource = ResourceAddition("resource:ember", 2, "Ember Charges")
    harness = Harness()
    plan, harness = _plan(
        _snapshot(),
        [_feature(resources=(resource,)), _campaign_equipment(quantity=3)],
        harness,
    )
    assert plan.status is PlanStatus.READY
    assert harness.derive_calls == 1
    assert harness.state_calls == 1
    assert harness.projection_calls == 1
    assert plan.reconciliation == StateReconciliation(
        (resource,), (("equipment:glass-sword", 3),)
    )


@pytest.mark.parametrize(
    "projection",
    [
        StateImpactProjection(StateImpact.PRESERVE_EXACT),
        StateImpactProjection(
            StateImpact.RECONCILE_REQUIRED,
            StateReconciliation((ResourceAddition("resource:extra", 0),)),
        ),
        StateImpactProjection(
            StateImpact.RECONCILE_REQUIRED,
            StateReconciliation((ResourceAddition("resource:ember", 99),)),
        ),
        StateImpactProjection(
            StateImpact.RECONCILE_REQUIRED,
            StateReconciliation(
                (
                    ResourceAddition("resource:ember", 2),
                    ResourceAddition("resource:extra", 0),
                )
            ),
        ),
    ],
)
def test_state_projection_rejects_missing_mismatched_and_extra_feature_rows(projection):
    operation = _feature(resources=(ResourceAddition("resource:ember", 2),))
    harness = Harness(state_projection=projection)
    plan, harness = _plan(_snapshot(), [operation], harness)
    assert DiagnosticCode.STATE_IMPACT_MISMATCH in _codes(plan)
    assert harness.derive_calls == harness.state_calls == harness.projection_calls == 1


@pytest.mark.parametrize(
    "projection",
    [
        StateImpactProjection(StateImpact.PRESERVE_EXACT),
        StateImpactProjection(
            StateImpact.RECONCILE_REQUIRED,
            StateReconciliation(inventory=(("equipment:glass-sword", 2),)),
        ),
        StateImpactProjection(
            StateImpact.RECONCILE_REQUIRED,
            StateReconciliation(
                inventory=(
                    ("equipment:glass-sword", 3),
                    ("equipment:extra", 1),
                )
            ),
        ),
    ],
)
def test_state_projection_rejects_missing_mismatched_and_extra_inventory_rows(projection):
    harness = Harness(state_projection=projection)
    plan, harness = _plan(_snapshot(), [_campaign_equipment(quantity=3)], harness)
    assert DiagnosticCode.STATE_IMPACT_MISMATCH in _codes(plan)
    assert harness.derive_calls == harness.state_calls == harness.projection_calls == 1


@pytest.mark.parametrize(
    "impact",
    [StateImpact.PRESERVE_EXACT, StateImpact.RECONCILE_REQUIRED],
)
def test_state_projection_rejects_reconciliation_without_eligible_additions(impact):
    projection = StateImpactProjection(
        impact, StateReconciliation((ResourceAddition("resource:opaque", 0),))
    )
    plan, _ = _plan(
        _snapshot(),
        [_feature()],
        Harness(state_projection=projection),
    )
    assert DiagnosticCode.STATE_IMPACT_MISMATCH in _codes(plan)


def test_reconcile_required_with_no_eligible_or_projected_additions_is_rejected():
    plan, _ = _plan(
        _snapshot(),
        [_feature()],
        Harness(
            state_projection=StateImpactProjection(StateImpact.RECONCILE_REQUIRED)
        ),
    )
    assert DiagnosticCode.STATE_IMPACT_MISMATCH in _codes(plan)


def test_state_projection_rejects_warnings_and_all_existing_state_hazards():
    warning, warning_harness = _plan(
        _snapshot(),
        [_feature()],
        Harness(
            state_projection=StateImpactProjection(
                StateImpact.PRESERVE_EXACT,
                warnings=("shape uncertain",),
            )
        ),
    )
    assert DiagnosticCode.STATE_IMPACT_WARNING in _codes(warning)
    assert warning_harness.state_calls == warning_harness.projection_calls == 1

    hazards = (
        "existing row updated",
        "existing row removed",
        "existing value clamped",
        "existing rows merged",
        "opaque state changed",
    )
    hazard, hazard_harness = _plan(
        _snapshot(),
        [_feature()],
        Harness(
            state_projection=StateImpactProjection(
                StateImpact.PRESERVE_EXACT,
                hazards=hazards,
            )
        ),
    )
    assert DiagnosticCode.STATE_IMPACT_HAZARD in _codes(hazard)
    assert hazard_harness.state_calls == hazard_harness.projection_calls == 1


def test_state_projection_requires_the_typed_immutable_result():
    harness = Harness(state_projection={"impact": "preserve_exact"})
    plan, harness = _plan(_snapshot(), [_feature()], harness)
    assert DiagnosticCode.STATE_IMPACT_FAILED in _codes(plan)
    assert harness.derive_calls == harness.state_calls == harness.projection_calls == 1


def test_existing_resource_missing_state_and_relink_mutation_hazards_block():
    collision, _ = _plan(
        _snapshot(state_resource_ids=frozenset({"resource:ember"})),
        [_feature(resources=(ResourceAddition("resource:ember"),))],
    )
    assert DiagnosticCode.IDENTITY_COLLISION in _codes(collision)

    missing, _ = _plan(_snapshot(state=None), [_feature()])
    assert DiagnosticCode.MISSING_WHOLE_STATE in _codes(missing)

    existing = ExistingEquipment(
        "equipment:blade",
        None,
        {"id": "equipment:blade"},
        {"id": "equipment:blade", "quantity": 1, "equipped": False},
    )
    hazard, _ = _plan(
        _snapshot(equipment={existing.equipment_id: existing}),
        [_relink(after={"id": "equipment:blade", "quantity": 0, "equipped": False})],
    )
    assert DiagnosticCode.MUTABLE_STATE_HAZARD in _codes(hazard)

    ambiguous, _ = _plan(
        _snapshot(equipment={existing.equipment_id: existing}),
        [_relink(source=SourceAttestation(ambiguous=True))],
    )
    assert DiagnosticCode.AMBIGUOUS_RELINK in _codes(ambiguous)


@pytest.mark.parametrize("category", list(SemanticCategory))
def test_semantic_diff_accepts_only_the_six_canonical_categories(category):
    row = SemanticDiffRow(
        category,
        f"semantic:{category.name.lower()}",
        "Readable label",
        ChangeKind.ADDED,
        "Not present",
        "Now available",
    )
    plan, harness = _plan(_snapshot(), [_feature()], Harness((row,)))
    assert plan.status is PlanStatus.READY
    assert plan.semantic_diff == (row,)
    assert harness.derive_calls == harness.projection_calls == 1


def test_invalid_semantic_category_and_projection_warning_block():
    invalid = SemanticDiffRow("notes", "notes:x", "Notes", "updated", "Old", "New")
    plan, _ = _plan(_snapshot(), [_feature()], Harness((invalid,)))
    assert DiagnosticCode.PROJECTION_FAILED in _codes(plan)

    harness = Harness()
    harness.project = lambda *_: SemanticProjection(warnings=("warning",))
    plan, _ = _plan(_snapshot(), [_feature()], harness)
    assert DiagnosticCode.PROJECTION_WARNING in _codes(plan)


def _plan_with_summary(summary, *, field_name="after"):
    values = {"before": "Not present", "after": "Now available"}
    values[field_name] = summary
    raw = SemanticDiffRow(
        SemanticCategory.FEATURES,
        "feature:x",
        "Feature",
        ChangeKind.ADDED,
        values["before"],
        values["after"],
    )
    return _plan(_snapshot(), [_feature()], Harness((raw,)))[0]


@pytest.mark.parametrize("field_name", ["before", "after"])
@pytest.mark.parametrize(
    "summary",
    [
        'State payload: {"current_hp":9}',
        "YAML current_hp: 9",
        "State field stats.armor_class changed",
    ],
)
def test_exact_embedded_raw_summary_probes_block_without_candidate(field_name, summary):
    plan = _plan_with_summary(summary, field_name=field_name)
    assert plan.status is PlanStatus.BLOCKED
    assert DiagnosticCode.PROJECTION_FAILED in _codes(plan)
    assert plan.semantic_diff == ()
    assert plan.candidate_definition is None
    assert plan.derived_character is None
    assert plan.digest is None
    assert summary not in " ".join(item.message for item in plan.diagnostics)


@pytest.mark.parametrize(
    "summary",
    [
        "State values [1, 2, 3] were returned",
        "State values [1] were returned",
        'State key "current_hp": 9 was returned',
        "Config payload enabled: true was returned",
        "current_hp: 9",
        "name: Hero",
        "The row current_hp: 9 was returned",
        "Document marker --- begins here",
        "%YAML 1.2",
        "YAML anchor &shared was returned",
        "YAML tag !resource was returned",
        'State field inventory[0]["quantity"] changed',
        "State field $.stats.armor_class changed",
        'State field $["stats"]["armor_class"] changed',
        "State field a.b changed",
        "State pointer /stats/armor_class changed",
        "State pointer /inventory/0 changed",
        "Read C:\\private\\sheet.yaml before continuing",
        "Read /home/player/sheet.yaml before continuing",
        "The raw file sheet.json was returned",
        "Open file:///private/sheet.yaml for details",
        "Open https://example.test/raw.json for details",
        "The value data:text/plain,raw was returned",
        "The value javascript:alert(1) was returned",
        "Digest: abcdef0123456789 was returned",
        "Checksum deadbeef was returned",
        "Value abcdef0123456789abcdef0123456789 was returned",
        "Rendered <strong>Feature</strong> was returned",
        "Rendered &lt;strong&gt;Feature&lt;/strong&gt; was returned",
        "See [Feature](https://example.test) for details",
        "See [Feature][feature-ref] for details",
        "See ![Feature](image.png) for details",
        "Use `current_hp` for the value",
        "Use **bold** for the value",
        "Use _italic_ for the value",
        "Use ~~removed~~ for the value",
        "# Feature heading",
        "> Feature quote",
        "- Feature list item",
        "1. Feature list item",
        "Use ```code``` for the value",
    ],
)
def test_embedded_raw_data_paths_digests_uris_and_markup_are_rejected(summary):
    plan = _plan_with_summary(summary)
    assert plan.status is PlanStatus.BLOCKED
    assert _codes(plan) == {DiagnosticCode.PROJECTION_FAILED}
    assert plan.semantic_diff == ()
    assert plan.candidate_definition is None
    assert plan.derived_character is None
    assert plan.digest is None
    assert summary not in plan.diagnostics[0].message


@pytest.mark.parametrize(
    "summary",
    [
        "SHA1 abc12345 was returned",
        "SHA-224: abc12345 was returned",
        "SHA_256=abc12345 was returned",
        "SHA384 deadbeef was returned",
        "SHA-512: a1b2c3d4 was returned",
        "MD5: a1b2c3d4 was returned",
        "BLAKE2b abc12345 was returned",
        "BLAKE-2s: abc12345 was returned",
        "BLAKE_3=abc12345 was returned",
    ],
)
def test_hash_algorithm_labels_with_machine_values_are_rejected(summary):
    plan = _plan_with_summary(summary)
    assert plan.status is PlanStatus.BLOCKED
    assert _codes(plan) == {DiagnosticCode.PROJECTION_FAILED}
    assert plan.semantic_diff == ()
    assert plan.candidate_definition is None
    assert plan.derived_character is None
    assert plan.digest is None
    assert summary not in plan.diagnostics[0].message


@pytest.mark.parametrize(
    "summary",
    [
        "State payload: {} was returned",
        "State payload: [] was returned",
        "The result {} was returned",
        "The result [] was returned",
        "Anchor &shared was returned",
        "Alias *shared was returned",
        "Tag !resource was returned",
    ],
)
def test_empty_json_and_labeled_yaml_markers_are_rejected(summary):
    plan = _plan_with_summary(summary)
    assert plan.status is PlanStatus.BLOCKED
    assert _codes(plan) == {DiagnosticCode.PROJECTION_FAILED}
    assert plan.semantic_diff == ()
    assert plan.candidate_definition is None
    assert plan.derived_character is None
    assert plan.digest is None
    assert summary not in plan.diagnostics[0].message


@pytest.mark.parametrize("field_name", ["before", "after"])
@pytest.mark.parametrize(
    "summary",
    [
        "YAML anchor &a was returned",
        "Anchor &a was returned",
        "Alias *a was returned",
        "Tag !a was returned",
        "Rendered &quot; was returned",
        "Rendered &nbsp; was returned",
    ],
)
def test_c1_summary_escapes_block_without_echo_or_candidate(field_name, summary):
    plan = _plan_with_summary(summary, field_name=field_name)
    assert plan.status is PlanStatus.BLOCKED
    assert _codes(plan) == {DiagnosticCode.PROJECTION_FAILED}
    assert plan.semantic_diff == ()
    assert plan.candidate_definition is None
    assert plan.derived_character is None
    assert plan.digest is None
    assert summary not in plan.diagnostics[0].message


@pytest.mark.parametrize(
    "summary",
    [
        "Named mixed-case digit &Ab9; was returned",
        "Named boundary &" + "A" + ("b7" * 15) + "; was returned",
        "Decimal one digit &#1; was returned",
        "Decimal seven digits &#1234567; was returned",
        "Hex lower prefix one digit &#xA; was returned",
        "Hex upper prefix six mixed-case digits &#XAbCdE9; was returned",
    ],
)
def test_structural_entity_boundaries_block_without_echo_or_candidate(summary):
    plan = _plan_with_summary(summary)
    assert plan.status is PlanStatus.BLOCKED
    assert _codes(plan) == {DiagnosticCode.PROJECTION_FAILED}
    assert plan.semantic_diff == ()
    assert plan.candidate_definition is None
    assert plan.derived_character is None
    assert plan.digest is None
    assert summary not in plan.diagnostics[0].message


@pytest.mark.parametrize(
    "summary",
    [
        "An ordinary & remains ordinary prose.",
        "AT&T remains ordinary prose.",
        "R&D remains ordinary prose.",
        "Smith & Wesson remains ordinary prose.",
        "D&D and D&D; remain ordinary prose.",
        "The hero's shield remains equipped.",
        "Missing &nbsp without a semicolon remains prose.",
        "Malformed &; remains prose.",
        "Malformed &a; remains prose.",
        "Malformed &1amp; remains prose.",
        "Malformed &am-p; remains prose.",
        "Malformed &#; remains prose.",
        "Malformed &#x; remains prose.",
        "Malformed &#-1; remains prose.",
        "Malformed &#xGG; remains prose.",
        "Whitespace & nbsp; remains prose.",
        "Whitespace & #123; remains prose.",
        "Whitespace &# 123; remains prose.",
        "Over-bound named &" + "Q" + ("z" * 31) + "; remains prose.",
        "Over-bound decimal &#12345678; remains prose.",
        "Over-bound hex &#x1234567; remains prose.",
    ],
)
def test_non_structural_ampersand_prose_remains_ready(summary):
    plan = _plan_with_summary(summary)
    assert plan.status is PlanStatus.READY
    assert plan.semantic_diff[0].after == summary
    assert plan.digest


def _repeated_probe(fragment, length):
    return (fragment * ((length // len(fragment)) + 1))[:length]


def _entity_search_workload(length):
    probes = (
        _repeated_probe("&", length),
        _repeated_probe("&Partial", length),
        _repeated_probe("&#1234567", length),
        _repeated_probe("&am-p;", length),
        _repeated_probe("&nbsp", length),
    )
    assert all(len(probe) == length for probe in probes)
    assert not any(planner_module._STRUCTURAL_ENTITY_PATTERN.search(probe) for probe in probes)
    started = time.perf_counter()
    for _ in range(2_000):
        for probe in probes:
            planner_module._STRUCTURAL_ENTITY_PATTERN.search(probe)
    return time.perf_counter() - started


def test_structural_entity_search_is_bounded_on_adversarial_512_character_probes():
    elapsed_256 = _entity_search_workload(256)
    elapsed_512 = _entity_search_workload(512)
    assert elapsed_512 < 1.0
    assert elapsed_512 / max(elapsed_256, 1e-9) < 3.0


@pytest.mark.parametrize(
    "summary",
    [
        "Armor Class increased from 14 to 16.",
        "Armor Class: 16",
        "The feature now grants 2 uses per long rest.",
        "AC +1 while the shield is equipped.",
        "Deals 1d6 + 3 damage.",
        "Version v1.2 is now available.",
        "Use one charge, e.g. after a successful attack.",
        "The digest changed after the feature update.",
        "MD5 is an older algorithm.",
        "MD5: deprecated for new exports.",
        "BLAKE is mentioned without a machine value.",
        "SHA-256 may be selected for a future export.",
        "SHA-256: selected for a future export.",
        "Smith & Wesson is ordinary prose.",
        "Amazing! The feature worked.",
        "The calculation is 2 * 3.",
        "Choose option [A] during setup.",
        "Ordinary punctuation: commas, parentheses (yes), and D&D notation.",
    ],
)
def test_human_summary_accepts_frozen_prose_matrix(summary):
    first = _plan_with_summary(summary)
    second = _plan_with_summary(summary)
    assert first.status is second.status is PlanStatus.READY
    assert first.semantic_diff[0].after == summary
    assert first.digest == second.digest


def test_human_summary_enforces_text_boundaries_without_a_rejected_digest():
    accepted = _plan_with_summary("G" * 512)
    assert accepted.status is PlanStatus.READY
    assert accepted.digest

    for summary in (
        "G" * 513,
        " leading",
        "trailing ",
        "has\x00nul",
        "has\rcarriage",
        "has\nline",
    ):
        rejected = _plan_with_summary(summary)
        assert rejected.status is PlanStatus.BLOCKED
        assert _codes(rejected) == {DiagnosticCode.PROJECTION_FAILED}
        assert rejected.semantic_diff == ()
        assert rejected.candidate_definition is None
        assert rejected.derived_character is None
        assert rejected.digest is None


def test_noop_rejects_unexplained_semantic_changes():
    operation = _feature()
    payload = operation.payload
    snapshot = _snapshot(
        features={
            payload.feature_id: ExistingFeature(
                payload.feature_id,
                SourceIdentity(SourceKind.CAMPAIGN_PAGE, payload.page_ref),
                payload.definition,
            )
        }
    )
    row = SemanticDiffRow(
        SemanticCategory.FEATURES,
        payload.feature_id,
        "Ember Gift",
        ChangeKind.UPDATED,
        "Present",
        "Changed",
    )
    plan, _ = _plan(snapshot, [operation], Harness((row,)))
    assert DiagnosticCode.UNEXPLAINED_SEMANTIC_CHANGE in _codes(plan)


def test_inputs_and_seam_outputs_are_deeply_isolated():
    snapshot = _snapshot()
    operation = _feature()
    original_snapshot = deepcopy(snapshot)
    original_operation = deepcopy(operation)

    class MutatingHarness(Harness):
        def adapter(self, definition, operation):
            definition["name"] = "Mutated copy"
            operation.payload.definition["name"] = "Mutated operation copy"
            return definition

        def derive(self, definition, state):
            self.derive_calls += 1
            definition["derived"] = True
            state["vitals"]["current_hp"] = 0
            return DerivationResult(definition)

        def project_state(self, state, derived, operations):
            self.state_calls += 1
            state["notes"] = "state projection mutation"
            derived["derived"] = "state projection mutation"
            operations[0].payload.definition["name"] = "state projection mutation"
            return StateImpactProjection(StateImpact.PRESERVE_EXACT)

        def project(self, baseline, derived, state):
            self.projection_calls += 1
            baseline["name"] = "Projection copy"
            derived["derived"] = "projection mutation"
            state["notes"] = "projection mutation"
            return SemanticProjection()

    plan, harness = _plan(snapshot, [operation], MutatingHarness())
    assert snapshot == original_snapshot
    assert operation == original_operation
    assert plan.candidate_definition["name"] == "Mutated copy"
    assert plan.derived_character["derived"] is True
    assert harness.derive_calls == harness.state_calls == harness.projection_calls == 1


def test_mapping_and_operation_permutations_produce_same_order_and_digest():
    feature_a = _feature(
        page_ref="Mechanics/A",
        feature_id="feature:a",
        definition={"z": 2, "a": {"right": 2, "left": 1}},
    )
    feature_b = _feature(
        page_ref="Mechanics/B",
        feature_id="feature:b",
        definition={"a": {"left": 1, "right": 2}, "z": 2},
    )
    first, _ = _plan(_snapshot(), [feature_b, feature_a])
    second, _ = _plan(_snapshot(), [feature_a, feature_b])
    assert first.status is second.status is PlanStatus.READY
    assert first.digest == second.digest
    assert [item.operation_id for item in first.operations] == [
        item.operation_id for item in second.operations
    ]


def test_digest_excludes_labels_and_source_bodies_but_includes_semantic_change():
    left = _feature(definition={"id": "feature:ember-gift", "body": "secret source A"})
    right_payload = CampaignFeatureGrant(
        left.payload.page_ref,
        left.payload.feature_id,
        {"id": "feature:ember-gift", "body": "secret source B"},
        "Different request label",
    )
    right = UpdateOperation(left.kind, right_payload)
    left_plan, _ = _plan(_snapshot(), [left])
    right_plan, _ = _plan(_snapshot(), [right])
    assert left_plan.digest == right_plan.digest

    row = SemanticDiffRow(
        SemanticCategory.FEATURES,
        "feature:ember-gift",
        "Ignored label",
        ChangeKind.ADDED,
        "Not present",
        "Ember Gift available",
    )
    changed, _ = _plan(_snapshot(), [left], Harness((row,)))
    assert changed.digest != left_plan.digest
    assert len(changed.digest) == 64


def test_digest_is_stable_across_python_hash_seeds():
    repo_root = Path(__file__).resolve().parents[1]
    script = r'''
import json
from player_wiki.character_update_planner import *
snapshot = CharacterSnapshot(
    "character:hero", "revision:7", "DND-5E",
    {"b": 2, "a": 1}, {"vitals": {"current_hp": 9}},
)
lookup = {
    key: UpdateOperation(
        OperationKind.CAMPAIGN_FEATURE_GRANT,
        CampaignFeatureGrant(
            f"Mechanics/{key}",
            f"feature:{key.lower()}",
            {"id": f"feature:{key.lower()}"},
        ),
    )
    for key in ("B", "A")
}
operations = [lookup[key] for key in {"A", "B"}]
def adapter(definition, operation):
    result = dict(definition)
    result[operation.payload.feature_id] = True
    return result
def derive(definition, state): return DerivationResult(definition)
def project_state(*args): return StateImpactProjection(StateImpact.PRESERVE_EXACT)
def project(*args): return SemanticProjection()
plan = plan_character_update(
    snapshot, operations, adapter=adapter, derive=derive,
    project_state_impact=project_state,
    project_semantics=project,
)
print(json.dumps(
    {"digest": plan.digest, "ids": [item.operation_id for item in plan.operations]},
    sort_keys=True,
))
'''
    outputs = []
    for seed in ("1", "17", "53", "97", "211"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=str(repo_root))
        outputs.append(
            subprocess.run(
                [sys.executable, "-c", script],
                cwd=repo_root,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    assert outputs[0] == outputs[1]
    assert json.loads(outputs[0])["digest"]


def test_import_boundary_has_no_framework_service_or_io_dependencies():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "player_wiki"
        / "character_update_planner.py"
    )
    source = module_path.read_text(encoding="utf-8")
    imported_roots = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    forbidden = {
        "flask",
        "player_wiki",
        "sqlite3",
        "requests",
        "pathlib",
        "datetime",
        "time",
        "random",
        "secrets",
    }
    assert imported_roots.isdisjoint(forbidden)
    assert "open(" not in source.casefold()


def test_planner_execution_constructs_no_services_and_performs_no_io(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("planner attempted I/O")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(builtins, "open", forbidden)
    plan, harness = _plan(_snapshot(), [_feature()])
    assert plan.status is PlanStatus.READY
    assert harness.derive_calls == harness.state_calls == harness.projection_calls == 1


def test_derivation_and_projection_failures_are_sanitized_and_never_retry():
    harness = Harness()

    def bad_derive(*_):
        harness.derive_calls += 1
        raise RuntimeError("C:\\private\\character.yaml")

    harness.derive = bad_derive
    plan, _ = _plan(_snapshot(), [_feature()], harness)
    assert DiagnosticCode.DERIVATION_FAILED in _codes(plan)
    assert "private" not in plan.diagnostics[0].message
    assert harness.derive_calls == 1
    assert harness.projection_calls == 0

    harness = Harness()

    def bad_project(*_):
        harness.projection_calls += 1
        raise RuntimeError("raw source body")

    harness.project = bad_project
    plan, _ = _plan(_snapshot(), [_feature()], harness)
    assert DiagnosticCode.PROJECTION_FAILED in _codes(plan)
    assert "raw source" not in plan.diagnostics[0].message
    assert harness.derive_calls == harness.projection_calls == 1
