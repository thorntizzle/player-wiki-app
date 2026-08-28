from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from player_wiki.character_models import CharacterDefinition
from player_wiki.character_service import build_initial_state, merge_state_with_definition
from player_wiki.character_builder import normalize_definition_to_native_model
from player_wiki.character_update_adapters import (
    AdapterPreparationError,
    CampaignEquipmentAddIntent,
    CampaignFeatureGrantIntent,
    EquipmentSafeRelinkIntent,
    SourceAccessDecision,
    SystemsItemAddIntent,
    prepare_character_update_adapters,
)
from player_wiki.character_update_planner import (
    DiagnosticCode,
    OperationStatus,
    PlanStatus,
    SemanticCategory,
    SourceIdentity,
    SourceKind,
    StateImpact,
    plan_character_update,
)
from player_wiki.systems_models import SystemsEntryRecord


def _definition(**overrides):
    payload = {
        "campaign_slug": "adapter-campaign",
        "character_slug": "adapter-hero",
        "name": "Adapter Hero",
        "status": "active",
        "system": "DND-5E",
        "profile": {"level": 5},
        "stats": {
            "max_hp": 20,
            "armor_class": 14,
            "ability_scores": {
                key: {"score": 10, "modifier": 0, "save_bonus": 0}
                for key in ("str", "dex", "con", "int", "wis", "cha")
            },
        },
        "skills": [],
        "proficiencies": {
            "armor": [],
            "weapons": [],
            "tools": [],
            "languages": [],
            "tool_expertise": [],
        },
        "attacks": [],
        "features": [],
        "spellcasting": {},
        "equipment_catalog": [],
        "reference_notes": {"preserved": "definition"},
        "resource_templates": [],
        "source": {"kind": "native"},
    }
    payload.update(deepcopy(overrides))
    return payload


def _state(**overrides):
    payload = {
        "status": "active",
        "vitals": {
            "current_hp": 17,
            "temp_hp": 2,
            "death_saves": {"successes": 0, "failures": 0},
        },
        "hit_dice": {"pools": []},
        "resources": [],
        "inventory": [],
        "currency": {"cp": 1, "sp": 2, "ep": 0, "gp": 3, "pp": 0, "other": []},
        "spell_slots": [],
        "attunement": {"max_attuned_items": 3, "attuned_item_refs": []},
        "notes": {"player_notes_markdown": "Preserve me", "session_notes": []},
    }
    payload.update(deepcopy(overrides))
    return payload


def _page(
    page_ref,
    *,
    section="Mechanics",
    title="Harbor Blessing",
    option=None,
):
    return SimpleNamespace(
        campaign_slug="adapter-campaign",
        page_ref=page_ref,
        relative_path=f"content/{page_ref}.md",
        metadata={"character_option": deepcopy(option)} if option is not None else {},
        body_markdown="Prepared source body",
        page=SimpleNamespace(
            title=title,
            summary="A bounded prepared source summary.",
            section=section,
            subsection="",
        ),
        updated_at="2026-08-27T00:00:00Z",
    )


def _entry(entry_key="item|phb|adapter-blade", *, entry_type="item", title="Adapter Blade"):
    now = datetime(2026, 8, 27, tzinfo=UTC)
    return SystemsEntryRecord(
        id=1,
        library_slug="dnd-5e",
        source_id="PHB",
        entry_key=entry_key,
        entry_type=entry_type,
        slug=entry_key.rsplit("|", 1)[-1],
        title=title,
        source_page="",
        source_path="prepared://systems",
        search_text=title,
        player_safe_default=True,
        dm_heavy=False,
        metadata={"weight": "3 lb."},
        body={},
        rendered_html="",
        created_at=now,
        updated_at=now,
    )


def _access(_source):
    return SourceAccessDecision()


def _pure_normalize(definition):
    payload = deepcopy(dict(definition))
    templates = [dict(row) for row in list(payload.get("resource_templates") or [])]
    template_ids = {str(row.get("id") or "") for row in templates}
    features = [dict(row) for row in list(payload.get("features") or [])]
    for feature in features:
        option = dict(feature.get("campaign_option") or {})
        resource = dict(option.get("resource") or {})
        maximum = int(resource.get("max") or 0)
        if maximum <= 0:
            continue
        tracker_id = f"campaign-option-tracker:{feature['id']}"
        feature["tracker_ref"] = tracker_id
        if tracker_id not in template_ids:
            templates.append(
                {
                    "id": tracker_id,
                    "label": str(resource.get("label") or feature.get("name") or "Resource"),
                    "category": "custom_feature",
                    "initial_current": maximum,
                    "max": maximum,
                    "reset_on": str(resource.get("reset_on") or "manual"),
                    "reset_to": "unchanged",
                    "rest_behavior": "manual_only",
                    "notes": "",
                    "display_order": len(templates),
                }
            )
            template_ids.add(tracker_id)
    payload["features"] = features
    payload["resource_templates"] = templates
    return payload


def _pure_merge(definition, state):
    payload = deepcopy(dict(state))
    resources = [dict(row) for row in list(payload.get("resources") or [])]
    resource_ids = {str(row.get("id") or "") for row in resources}
    for template in list(definition.get("resource_templates") or []):
        resource_id = str(template.get("id") or "")
        if not resource_id or resource_id in resource_ids:
            continue
        resources.append(
            {
                "id": resource_id,
                "label": str(template.get("label") or "Resource"),
                "current": int(template.get("initial_current") or template.get("max") or 0),
                "max": template.get("max"),
                "reset_on": str(template.get("reset_on") or "manual"),
                "reset_to": str(template.get("reset_to") or "unchanged"),
                "rest_behavior": str(template.get("rest_behavior") or "manual_only"),
                "notes": str(template.get("notes") or ""),
                "display_order": int(template.get("display_order") or 0),
            }
        )
        resource_ids.add(resource_id)
    payload["resources"] = resources

    inventory = [dict(row) for row in list(payload.get("inventory") or [])]
    inventory_ids = {
        str(row.get("catalog_ref") or row.get("id") or "") for row in inventory
    }
    for item in list(definition.get("equipment_catalog") or []):
        item_id = str(item.get("id") or "")
        if not item_id or item_id in inventory_ids:
            continue
        inventory.append(
            {
                "id": item_id,
                "catalog_ref": item_id,
                "name": item.get("name"),
                "quantity": int(item.get("default_quantity") or 0),
                "weight": item.get("weight"),
                "is_equipped": bool(item.get("is_equipped", False)),
                "is_attuned": bool(item.get("is_attuned", False)),
                "charges_current": item.get("charges_current"),
                "charges_max": item.get("charges_max"),
                "notes": item.get("notes", ""),
                "tags": list(item.get("tags") or []),
            }
        )
        inventory_ids.add(item_id)
    payload["inventory"] = inventory
    return payload


def _prepare(
    intents,
    *,
    definition=None,
    state=None,
    pages=(),
    entries=(),
    access=_access,
    normalize=_pure_normalize,
    merge=_pure_merge,
):
    return prepare_character_update_adapters(
        target_identity="adapter-campaign/adapter-hero",
        baseline_identity="definition-revision-7-state-revision-11",
        definition=definition or _definition(),
        state=state or _state(),
        intents=intents,
        campaign_page_records=pages,
        systems_entries=entries,
        resolve_access=access,
        normalize_definition=normalize,
        merge_state=merge,
    )


def _plan(prepared):
    return plan_character_update(
        prepared.snapshot,
        prepared.operations,
        **prepared.planner_kwargs(),
    )


def _diagnostic_codes(plan):
    return {diagnostic.code for diagnostic in plan.diagnostics}


def test_campaign_feature_adapter_appends_one_canonical_row_and_reconciles_resource():
    page = _page(
        "mechanics/harbor-blessing",
        option={
            "kind": "feature",
            "name": "Harbor Blessing",
            "activation_type": "bonus_action",
            "description": "Gain a fixed blessing.",
            "resource": {"label": "Blessing Uses", "max": 2, "reset_on": "long_rest"},
        },
    )
    prepared = _prepare(
        [CampaignFeatureGrantIntent(page.page_ref, "campaign-feature-harbor-blessing")],
        pages=[page],
    )

    plan = _plan(prepared)

    assert plan.status is PlanStatus.READY
    assert plan.state_impact is StateImpact.RECONCILE_REQUIRED
    assert plan.reconciliation.resources[0].resource_id == (
        "campaign-option-tracker:campaign-feature-harbor-blessing"
    )
    assert plan.reconciliation.resources[0].initial_value == 2
    assert [row["id"] for row in plan.candidate_definition["features"]] == [
        "campaign-feature-harbor-blessing"
    ]
    assert plan.candidate_definition["features"][0]["page_ref"] == page.page_ref
    assert plan.derived_character["state"]["notes"] == _state()["notes"]
    assert {row.category for row in plan.semantic_diff} == {
        SemanticCategory.FEATURES,
        SemanticCategory.RESOURCES,
    }


@pytest.mark.parametrize(
    ("intent", "pages", "entries", "equipment_id", "source_key"),
    [
        (
            CampaignEquipmentAddIntent("items/harbor-rope", "campaign-item-harbor-rope", 2),
            [_page("items/harbor-rope", section="Items", title="Harbor Rope", option={"kind": "item"})],
            [],
            "campaign-item-harbor-rope",
            "page_ref",
        ),
        (
            SystemsItemAddIntent("item|phb|adapter-blade", "systems-item-adapter-blade", 1),
            [],
            [_entry()],
            "systems-item-adapter-blade",
            "systems_ref",
        ),
    ],
)
def test_equipment_add_adapters_append_without_quantity_merge(
    intent,
    pages,
    entries,
    equipment_id,
    source_key,
):
    baseline = _definition(
        equipment_catalog=[
            {
                "id": "existing-rope",
                "name": "Harbor Rope",
                "default_quantity": 4,
                "weight": "",
                "notes": "",
                "source_kind": "manual_edit",
                "campaign_option": None,
            }
        ]
    )
    baseline_state = _state(
        inventory=[
            {
                "id": "existing-rope",
                "catalog_ref": "existing-rope",
                "name": "Harbor Rope",
                "quantity": 4,
                "weight": "",
                "is_equipped": False,
                "is_attuned": False,
                "charges_current": None,
                "charges_max": None,
                "notes": "",
                "tags": [],
            }
        ]
    )
    prepared = _prepare(
        [intent],
        definition=baseline,
        state=baseline_state,
        pages=pages,
        entries=entries,
    )

    plan = _plan(prepared)

    assert plan.status is PlanStatus.READY
    rows = plan.candidate_definition["equipment_catalog"]
    assert [row["id"] for row in rows] == ["existing-rope", equipment_id]
    assert rows[0]["default_quantity"] == 4
    assert source_key in rows[1]
    inventory = plan.derived_character["state"]["inventory"]
    assert [(row["catalog_ref"], row["quantity"]) for row in inventory] == [
        ("existing-rope", 4),
        (equipment_id, intent.quantity),
    ]
    assert plan.reconciliation.inventory == ((equipment_id, intent.quantity),)


@pytest.mark.parametrize("target_kind", [SourceKind.CAMPAIGN_PAGE, SourceKind.SYSTEMS_ENTRY])
def test_safe_relink_changes_only_source_definition_and_preserves_inventory(target_kind):
    equipment = {
        "id": "legacy-blade",
        "name": "Legacy Blade",
        "default_quantity": 1,
        "weight": "3 lb.",
        "notes": "Keep this note",
        "source_kind": "manual_edit",
        "campaign_option": None,
        "custom": {"preserved": True},
    }
    inventory = {
        "id": "legacy-blade",
        "catalog_ref": "legacy-blade",
        "name": "Legacy Blade",
        "quantity": 1,
        "weight": "3 lb.",
        "is_equipped": True,
        "is_attuned": False,
        "charges_current": 2,
        "charges_max": 3,
        "notes": "Keep this state note",
        "tags": ["legacy"],
    }
    if target_kind is SourceKind.CAMPAIGN_PAGE:
        target = SourceIdentity(target_kind, "items/legacy-blade")
        pages = [_page(target.value, section="Items", title="Legacy Blade", option={"kind": "item"})]
        entries = []
    else:
        target = SourceIdentity(target_kind, "item|phb|adapter-blade")
        pages = []
        entries = [_entry()]
    prepared = _prepare(
        [EquipmentSafeRelinkIntent("legacy-blade", target)],
        definition=_definition(equipment_catalog=[equipment]),
        state=_state(inventory=[inventory]),
        pages=pages,
        entries=entries,
    )

    plan = _plan(prepared)

    assert plan.status is PlanStatus.READY
    assert plan.state_impact is StateImpact.PRESERVE_EXACT
    assert plan.reconciliation.inventory == ()
    assert plan.derived_character["state"] == _state(inventory=[inventory])
    relinked = plan.candidate_definition["equipment_catalog"][0]
    for key in ("id", "name", "default_quantity", "weight", "notes", "source_kind", "custom"):
        assert relinked[key] == equipment[key]
    assert any(
        row.category is SemanticCategory.EQUIPMENT_INVENTORY
        and row.change.value == "updated"
        for row in plan.semantic_diff
    )


def test_systems_safe_relink_preserves_unrelated_campaign_option():
    unrelated_campaign_option = {
        "kind": "legacy_annotation",
        "payload": {"preserved": True, "order": ["first", "second"]},
    }
    equipment = {
        "id": "legacy-blade",
        "name": "Legacy Blade",
        "default_quantity": 1,
        "source_kind": "manual_edit",
        "campaign_option": deepcopy(unrelated_campaign_option),
        "custom": {"preserved": True},
    }
    inventory = {
        "id": "legacy-blade",
        "catalog_ref": "legacy-blade",
        "name": "Legacy Blade",
        "quantity": 1,
    }
    target = SourceIdentity(SourceKind.SYSTEMS_ENTRY, "item|phb|adapter-blade")

    plan = _plan(
        _prepare(
            [EquipmentSafeRelinkIntent("legacy-blade", target)],
            definition=_definition(equipment_catalog=[equipment]),
            state=_state(inventory=[inventory]),
            entries=[_entry()],
        )
    )

    assert plan.status is PlanStatus.READY
    relinked = plan.candidate_definition["equipment_catalog"][0]
    assert relinked["campaign_option"] == unrelated_campaign_option
    assert relinked["custom"] == equipment["custom"]
    assert relinked["systems_ref"]["entry_key"] == target.value


@pytest.mark.parametrize("tamper", ["delete", "null", "mutate"])
def test_systems_safe_relink_validator_rejects_campaign_option_changes(tamper):
    campaign_option = {
        "kind": "legacy_annotation",
        "payload": {"preserved": True},
    }
    equipment = {
        "id": "legacy-blade",
        "name": "Legacy Blade",
        "default_quantity": 1,
        "campaign_option": campaign_option,
    }
    inventory = {
        "id": "legacy-blade",
        "catalog_ref": "legacy-blade",
        "name": "Legacy Blade",
        "quantity": 1,
    }
    prepared = _prepare(
        [
            EquipmentSafeRelinkIntent(
                "legacy-blade",
                SourceIdentity(SourceKind.SYSTEMS_ENTRY, "item|phb|adapter-blade"),
            )
        ],
        definition=_definition(equipment_catalog=[equipment]),
        state=_state(inventory=[inventory]),
        entries=[_entry()],
    )
    operation = prepared.operations[0]
    tampered_definition = deepcopy(dict(operation.payload.definition))
    if tamper == "delete":
        tampered_definition.pop("campaign_option", None)
    elif tamper == "null":
        tampered_definition["campaign_option"] = None
    else:
        tampered_definition["campaign_option"] = {
            "kind": "legacy_annotation",
            "payload": {"preserved": False},
        }
    tampered_operation = replace(
        operation,
        payload=replace(operation.payload, definition=tampered_definition),
    )

    with pytest.raises(ValueError, match="safe relink changed more"):
        prepared.adapter(prepared.snapshot.definition, tampered_operation)


def test_campaign_safe_relink_installs_only_its_target_source_metadata():
    equipment = {
        "id": "legacy-blade",
        "name": "Legacy Blade",
        "default_quantity": 1,
        "source_kind": "manual_edit",
        "campaign_option": {"kind": "legacy_annotation", "preserved": False},
        "custom": {"preserved": True},
    }
    inventory = {
        "id": "legacy-blade",
        "catalog_ref": "legacy-blade",
        "name": "Legacy Blade",
        "quantity": 1,
    }
    page = _page(
        "items/legacy-blade",
        section="Items",
        title="Legacy Blade",
        option={"kind": "item", "name": "Target Blade", "quantity": 4},
    )

    plan = _plan(
        _prepare(
            [
                EquipmentSafeRelinkIntent(
                    "legacy-blade",
                    SourceIdentity(SourceKind.CAMPAIGN_PAGE, page.page_ref),
                )
            ],
            definition=_definition(equipment_catalog=[equipment]),
            state=_state(inventory=[inventory]),
            pages=[page],
        )
    )

    assert plan.status is PlanStatus.READY
    relinked = plan.candidate_definition["equipment_catalog"][0]
    assert relinked["page_ref"] == page.page_ref
    assert "systems_ref" not in relinked
    assert relinked["campaign_option"]["page_ref"] == page.page_ref
    assert relinked["campaign_option"]["kind"] == "item"
    assert relinked["campaign_option"]["item_name"] == "Target Blade"
    for key in ("id", "name", "default_quantity", "source_kind", "custom"):
        assert relinked[key] == equipment[key]


def _campaign_safe_relink_validation_case(campaign_option_outcome):
    equipment = {
        "id": "legacy-blade",
        "name": "Legacy Blade",
        "default_quantity": 1,
        "source_kind": "manual_edit",
        "campaign_option": {"kind": "legacy_annotation", "preserved": False},
        "custom": {"preserved": True},
    }
    inventory = {
        "id": "legacy-blade",
        "catalog_ref": "legacy-blade",
        "name": "Legacy Blade",
        "quantity": 1,
    }
    page = _page(
        "items/legacy-blade",
        section="Items",
        title="Legacy Blade",
        option={
            "kind": "item",
            "name": "Target Blade",
            "quantity": 4,
        },
    )
    prepared = _prepare(
        [
            EquipmentSafeRelinkIntent(
                "legacy-blade",
                SourceIdentity(SourceKind.CAMPAIGN_PAGE, page.page_ref),
            )
        ],
        definition=_definition(equipment_catalog=[equipment]),
        state=_state(inventory=[inventory]),
        pages=[page],
    )
    operation = prepared.operations[0]
    expected_campaign_option = deepcopy(operation.payload.definition["campaign_option"])
    replacement = deepcopy(dict(operation.payload.definition))
    if campaign_option_outcome == "delete":
        replacement.pop("campaign_option", None)
    elif campaign_option_outcome == "null":
        replacement["campaign_option"] = None
    elif campaign_option_outcome == "mutate":
        replacement["campaign_option"]["item_name"] = "Mutated Blade"
    tampered_operation = replace(
        operation,
        payload=replace(operation.payload, definition=replacement),
    )
    return prepared, tampered_operation, expected_campaign_option, equipment, page


@pytest.mark.parametrize("campaign_option_outcome", ["exact", "delete", "null", "mutate"])
def test_campaign_safe_relink_direct_adapter_requires_exact_prepared_campaign_option(
    campaign_option_outcome,
):
    prepared, operation, expected_campaign_option, equipment, page = (
        _campaign_safe_relink_validation_case(campaign_option_outcome)
    )

    if campaign_option_outcome != "exact":
        with pytest.raises(ValueError, match="safe relink changed more"):
            prepared.adapter(prepared.snapshot.definition, operation)
        return

    adapted = prepared.adapter(prepared.snapshot.definition, operation)
    relinked = adapted["equipment_catalog"][0]
    assert relinked["page_ref"] == page.page_ref
    assert "systems_ref" not in relinked
    assert relinked["campaign_option"] == expected_campaign_option
    for key in ("id", "name", "default_quantity", "source_kind", "custom"):
        assert relinked[key] == equipment[key]


@pytest.mark.parametrize("campaign_option_outcome", ["exact", "delete", "null", "mutate"])
def test_campaign_safe_relink_public_plan_requires_exact_prepared_campaign_option(
    campaign_option_outcome,
):
    prepared, operation, expected_campaign_option, equipment, page = (
        _campaign_safe_relink_validation_case(campaign_option_outcome)
    )

    plan = plan_character_update(
        prepared.snapshot,
        (operation,),
        **prepared.planner_kwargs(),
    )

    if campaign_option_outcome != "exact":
        assert plan.status is PlanStatus.BLOCKED
        assert DiagnosticCode.ADAPTER_FAILED in _diagnostic_codes(plan)
        return

    assert plan.status is PlanStatus.READY
    relinked = plan.candidate_definition["equipment_catalog"][0]
    assert relinked["page_ref"] == page.page_ref
    assert "systems_ref" not in relinked
    assert relinked["campaign_option"] == expected_campaign_option
    for key in ("id", "name", "default_quantity", "source_kind", "custom"):
        assert relinked[key] == equipment[key]


def test_already_satisfied_addition_is_a_no_op_with_one_derivation_projection_cycle():
    page = _page("items/already-linked", section="Items", title="Already Linked", option={"kind": "item"})
    first = _prepare(
        [CampaignEquipmentAddIntent(page.page_ref, "already-linked", 1)],
        pages=[page],
    )
    operation = first.operations[0].payload
    definition = _definition(equipment_catalog=[deepcopy(dict(operation.definition))])
    state = _state(inventory=[deepcopy(dict(operation.inventory_row))])
    calls = {"normalize": 0, "merge": 0}

    def normalize(payload):
        calls["normalize"] += 1
        return _pure_normalize(payload)

    def merge(payload, current_state):
        calls["merge"] += 1
        return _pure_merge(payload, current_state)

    prepared = _prepare(
        [CampaignEquipmentAddIntent(page.page_ref, "already-linked", 1)],
        definition=definition,
        state=state,
        pages=[page],
        normalize=normalize,
        merge=merge,
    )

    plan = _plan(prepared)

    assert plan.status is PlanStatus.NO_OP
    assert plan.operations[0].status is OperationStatus.ALREADY_SATISFIED
    assert plan.semantic_diff == ()
    assert calls == {"normalize": 1, "merge": 1}


@pytest.mark.parametrize(
    "decision",
    [
        SourceAccessDecision(visible=False),
        SourceAccessDecision(enabled=False),
        SourceAccessDecision(approved=False),
    ],
)
def test_each_injected_source_policy_denial_blocks_before_native_callbacks(decision):
    page = _page("items/policy-item", section="Items", title="Policy Item", option={"kind": "item"})
    calls = {"normalize": 0, "merge": 0}

    def forbidden_normalize(_payload):
        calls["normalize"] += 1
        raise AssertionError("blocked input reached normalization")

    def forbidden_merge(_definition, _state_payload):
        calls["merge"] += 1
        raise AssertionError("blocked input reached state merge")

    prepared = _prepare(
        [CampaignEquipmentAddIntent(page.page_ref, "policy-item")],
        pages=[page],
        access=lambda _source: decision,
        normalize=forbidden_normalize,
        merge=forbidden_merge,
    )

    plan = _plan(prepared)

    assert plan.status is PlanStatus.BLOCKED
    assert DiagnosticCode.SOURCE_POLICY_FAILED in _diagnostic_codes(plan)
    assert calls == {"normalize": 0, "merge": 0}


@pytest.mark.parametrize(
    ("intent", "pages", "entries", "expected_code"),
    [
        (
            CampaignFeatureGrantIntent("mechanics/missing", "missing-feature"),
            [],
            [],
            DiagnosticCode.SOURCE_POLICY_FAILED,
        ),
        (
            CampaignEquipmentAddIntent("mechanics/not-an-item", "wrong-section"),
            [_page("mechanics/not-an-item", section="Mechanics")],
            [],
            DiagnosticCode.SOURCE_POLICY_FAILED,
        ),
        (
            SystemsItemAddIntent("spell|phb|not-an-item", "wrong-entry-type"),
            [],
            [_entry("spell|phb|not-an-item", entry_type="spell")],
            DiagnosticCode.SOURCE_POLICY_FAILED,
        ),
        (
            CampaignFeatureGrantIntent("mechanics/duplicate", "duplicate-source"),
            [_page("mechanics/duplicate"), _page("mechanics/duplicate")],
            [],
            DiagnosticCode.AMBIGUOUS_SOURCE,
        ),
    ],
)
def test_exact_source_resolution_blocks_missing_wrong_kind_and_duplicate_foundations(
    intent,
    pages,
    entries,
    expected_code,
):
    plan = _plan(_prepare([intent], pages=pages, entries=entries))

    assert plan.status is PlanStatus.BLOCKED
    assert expected_code in _diagnostic_codes(plan)


def test_choice_bearing_campaign_source_is_blocked():
    page = _page(
        "mechanics/choose-a-gift",
        option={
            "kind": "feature",
            "name": "Choose a Gift",
            "additional_spells": {"choose": {"count": 1, "from": ["spell-a"]}},
        },
    )

    plan = _plan(
        _prepare(
            [CampaignFeatureGrantIntent(page.page_ref, "choose-a-gift")],
            pages=[page],
        )
    )

    assert plan.status is PlanStatus.BLOCKED
    assert DiagnosticCode.CHOICE_BEARING in _diagnostic_codes(plan)


@pytest.mark.parametrize(
    "spell_metadata",
    [
        {"additional_spells": ["Magic Missile", "Shield"]},
        {
            "additionalSpells": {
                "fixed": ["Mage Hand"],
                "direct": {"spell": "Feather Fall"},
            }
        },
        {
            "spell_support": {
                "grants": ["Bless"],
                "fixed": {"spells": ["Guidance"]},
            }
        },
        {
            "spellManager": {
                "automatic_grants": ["Identify"],
                "config": {"ability": "int", "mode": "ritual_book"},
            }
        },
    ],
    ids=[
        "additional-spells-direct-list",
        "additional-spells-fixed-and-direct",
        "spell-support-grants-and-fixed",
        "spell-manager-automatic-grants-and-config",
    ],
)
def test_deterministic_spell_metadata_is_not_choice_bearing(spell_metadata):
    option = {"kind": "feature", "name": "Fixed Spell Feature", **spell_metadata}
    page = _page("mechanics/fixed-spell-feature", option=option)

    plan = _plan(
        _prepare(
            [CampaignFeatureGrantIntent(page.page_ref, "fixed-spell-feature")],
            pages=[page],
        )
    )

    assert plan.status is PlanStatus.READY
    assert DiagnosticCode.CHOICE_BEARING not in _diagnostic_codes(plan)


@pytest.mark.parametrize(
    "spell_metadata",
    [
        {"additionalSpells": [{"wrapper": {"Choo-se": {"count": 1}}}]},
        {"spell_support": {"nested": [{"Choi.ces": ["one", "two"]}]}},
        {"spellSupport": {"nested": ({"se-lect": {"from": ["spell-a"]}},)}},
        {"spell_support": {"nested": {"replacement": {"from": "a", "to": "b"}}}},
        {"spell_support": {"nested": {"re_place-ments": [{"from": "a", "to": "b"}]}}},
        {"spellManager": {"nested": [{"sourceOptions": ["wizard", "cleric"]}]}},
        {"spell_manager": {"nested": {"choice-fields": {"ability": ["int", "wis"]}}}},
        {"spell_support": {"select": 17}},
        {"spell_manager": {"source_options": "malformed but nonempty"}},
    ],
    ids=[
        "additional-spells-choose-alias",
        "generic-choices-alias",
        "spell-support-select-tuple",
        "spell-support-replacement",
        "spell-support-replacements-alias",
        "spell-manager-source-options-camel",
        "spell-manager-choice-fields-punctuation",
        "malformed-spell-support-selector",
        "malformed-manager-selector",
    ],
)
def test_unresolved_spell_selectors_are_choice_bearing_recursively(spell_metadata):
    page = _page(
        "mechanics/unresolved-spell-selector",
        option={"kind": "feature", "name": "Unresolved Spell Selector", **spell_metadata},
    )

    plan = _plan(
        _prepare(
            [CampaignFeatureGrantIntent(page.page_ref, "unresolved-spell-selector")],
            pages=[page],
        )
    )

    assert plan.status is PlanStatus.BLOCKED
    assert DiagnosticCode.CHOICE_BEARING in _diagnostic_codes(plan)


@pytest.mark.parametrize(
    "spell_metadata",
    [
        {"additional_spells": {"choose": {}}},
        {"spell_support": {"choices": [], "select": None, "replacement": ""}},
        {"spell_manager": {"source_options": {}, "choice_fields": ()}},
    ],
    ids=["additional-spells", "spell-support", "spell-manager"],
)
def test_empty_spell_selectors_are_not_choice_bearing(spell_metadata):
    page = _page(
        "mechanics/empty-spell-selectors",
        option={"kind": "feature", "name": "Empty Spell Selectors", **spell_metadata},
    )

    plan = _plan(
        _prepare(
            [CampaignFeatureGrantIntent(page.page_ref, "empty-spell-selectors")],
            pages=[page],
        )
    )

    assert plan.status is PlanStatus.READY
    assert DiagnosticCode.CHOICE_BEARING not in _diagnostic_codes(plan)


def test_fixed_spell_names_and_choice_like_prose_are_not_selectors():
    page = _page(
        "mechanics/fixed-choice-prose",
        option={
            "kind": "feature",
            "name": "Fixed Choice Prose",
            "description": "Choose courage: this prose does not request structured input.",
            "spell_support": {
                "grants": ["Choose Fate", "Selective Vision", "Replacement Soul"],
                "notes": "These are fixed spell names, not choices.",
            },
        },
    )

    plan = _plan(
        _prepare(
            [CampaignFeatureGrantIntent(page.page_ref, "fixed-choice-prose")],
            pages=[page],
        )
    )

    assert plan.status is PlanStatus.READY
    assert DiagnosticCode.CHOICE_BEARING not in _diagnostic_codes(plan)


def test_mixed_operations_normalize_merge_and_project_once_with_exact_reconciliation():
    feature_page = _page(
        "mechanics/fixed-boon",
        title="Fixed Boon",
        option={"kind": "feature", "name": "Fixed Boon", "resource": {"label": "Boon", "max": 1}},
    )
    item_page = _page(
        "items/fixed-kit",
        section="Items",
        title="Fixed Kit",
        option={"kind": "item", "quantity": 2},
    )
    calls = {"access": {}, "normalize": 0, "merge": 0}

    def access(source):
        key = (source.kind, source.value)
        calls["access"][key] = calls["access"].get(key, 0) + 1
        return SourceAccessDecision()

    def normalize(payload):
        calls["normalize"] += 1
        return _pure_normalize(payload)

    def merge(payload, current_state):
        calls["merge"] += 1
        return _pure_merge(payload, current_state)

    prepared = _prepare(
        [
            CampaignFeatureGrantIntent(feature_page.page_ref, "fixed-boon"),
            CampaignEquipmentAddIntent(item_page.page_ref, "fixed-kit", 2),
            SystemsItemAddIntent("item|phb|adapter-blade", "adapter-blade", 1),
        ],
        pages=[feature_page, item_page],
        entries=[_entry()],
        access=access,
        normalize=normalize,
        merge=merge,
    )

    plan = _plan(prepared)

    assert plan.status is PlanStatus.READY
    assert calls["normalize"] == 1
    assert calls["merge"] == 1
    assert set(calls["access"].values()) == {1}
    assert plan.reconciliation.resources[0].resource_id == "campaign-option-tracker:fixed-boon"
    assert plan.reconciliation.inventory == (("adapter-blade", 1), ("fixed-kit", 2))
    assert plan.derived_character["state"]["currency"] == _state()["currency"]
    assert plan.derived_character["state"]["vitals"] == _state()["vitals"]


@pytest.mark.parametrize("hazard", ["merge", "remove", "reorder"])
def test_native_derivation_blocks_equipment_merge_remove_and_reorder_hazards(hazard):
    page = _page("items/new", section="Items", title="New Item", option={"kind": "item"})
    baseline_items = [
        {"id": "existing-a", "name": "A", "default_quantity": 1},
        {"id": "existing-b", "name": "B", "default_quantity": 1},
    ]
    baseline_inventory = [
        {"id": row["id"], "catalog_ref": row["id"], "name": row["name"], "quantity": 1}
        for row in baseline_items
    ]

    def hazardous_normalize(payload):
        normalized = _pure_normalize(payload)
        rows = list(normalized["equipment_catalog"])
        if hazard == "merge":
            rows[-1]["id"] = rows[0]["id"]
        elif hazard == "remove":
            rows.pop(0)
        else:
            rows[0], rows[1] = rows[1], rows[0]
        normalized["equipment_catalog"] = rows
        return normalized

    plan = _plan(
        _prepare(
            [CampaignEquipmentAddIntent(page.page_ref, "new-item")],
            definition=_definition(equipment_catalog=baseline_items),
            state=_state(inventory=baseline_inventory),
            pages=[page],
            normalize=hazardous_normalize,
        )
    )

    assert plan.status is PlanStatus.BLOCKED
    assert DiagnosticCode.DERIVATION_WARNING in _diagnostic_codes(plan)


def test_state_impact_blocks_existing_state_change_and_unexpected_addition():
    page = _page("items/state-item", section="Items", title="State Item", option={"kind": "item"})

    def hazardous_merge(definition, state):
        merged = _pure_merge(definition, state)
        merged["vitals"]["current_hp"] -= 1
        merged["inventory"].append(
            {"id": "unexpected", "catalog_ref": "unexpected", "name": "Unexpected", "quantity": 1}
        )
        return merged

    plan = _plan(
        _prepare(
            [CampaignEquipmentAddIntent(page.page_ref, "state-item")],
            pages=[page],
            merge=hazardous_merge,
        )
    )

    assert plan.status is PlanStatus.BLOCKED
    assert DiagnosticCode.STATE_IMPACT_HAZARD in _diagnostic_codes(plan)


def test_native_derivation_blocks_unrelated_definition_change():
    page = _page("items/unrelated", section="Items", title="Unrelated", option={"kind": "item"})

    def hazardous_normalize(payload):
        normalized = _pure_normalize(payload)
        normalized["reference_notes"] = {"preserved": "changed"}
        return normalized

    plan = _plan(
        _prepare(
            [CampaignEquipmentAddIntent(page.page_ref, "unrelated")],
            pages=[page],
            normalize=hazardous_normalize,
        )
    )

    assert plan.status is PlanStatus.BLOCKED
    assert DiagnosticCode.DERIVATION_WARNING in _diagnostic_codes(plan)


def test_semantic_projection_sanitizes_markup_and_machine_content_to_bounded_human_text():
    hostile_title = "<script>alert(1)</script> **Blade** `payload` " + ("a" * 600)
    entry = _entry(title=hostile_title)
    plan = _plan(
        _prepare(
            [SystemsItemAddIntent(entry.entry_key, "sanitized-item")],
            entries=[entry],
        )
    )

    assert plan.status is PlanStatus.READY
    row = next(
        row
        for row in plan.semantic_diff
        if row.category is SemanticCategory.EQUIPMENT_INVENTORY
    )
    assert len(row.after) <= 512
    assert "<script>" not in row.after
    assert "**" not in row.after
    assert "`" not in row.after
    assert "payload -" not in row.after


def test_access_resolution_is_memoized_once_per_unique_identity_at_128_operation_bound():
    entries = [_entry(f"item|phb|bounded-{index}", title=f"Bounded Item {index}") for index in range(128)]
    intents = [
        SystemsItemAddIntent(entry.entry_key, f"bounded-item-{index}")
        for index, entry in enumerate(entries)
    ]
    calls = {"access": {}, "normalize": 0, "merge": 0}

    def access(source):
        calls["access"][source.value] = calls["access"].get(source.value, 0) + 1
        return SourceAccessDecision()

    def normalize(payload):
        calls["normalize"] += 1
        return _pure_normalize(payload)

    def merge(payload, current_state):
        calls["merge"] += 1
        return _pure_merge(payload, current_state)

    prepared = _prepare(
        intents,
        entries=entries,
        access=access,
        normalize=normalize,
        merge=merge,
    )

    assert len(prepared.operations) == 128
    assert len(calls["access"]) == 128
    assert set(calls["access"].values()) == {1}
    first = _plan(prepared)
    assert calls["normalize"] == 1
    assert calls["merge"] == 1
    second = _plan(prepared)
    assert calls["normalize"] == 2
    assert calls["merge"] == 2
    assert first.status is PlanStatus.READY
    assert second.status is PlanStatus.READY
    assert first.digest == second.digest
    assert calls["access"] == {entry.entry_key: 1 for entry in entries}


def test_repeated_source_access_is_memoized_even_when_planner_blocks_duplicate_intent():
    entry = _entry()
    calls = 0

    def access(_source):
        nonlocal calls
        calls += 1
        return SourceAccessDecision()

    prepared = _prepare(
        [
            SystemsItemAddIntent(entry.entry_key, "first"),
            SystemsItemAddIntent(entry.entry_key, "second"),
        ],
        entries=[entry],
        access=access,
    )
    plan = _plan(prepared)

    assert calls == 1
    assert plan.status is PlanStatus.BLOCKED
    assert DiagnosticCode.DUPLICATE_OPERATION in _diagnostic_codes(plan)


def test_callbacks_do_not_resolve_sources_or_mutate_caller_inputs_after_preparation():
    page = _page("items/no-io", section="Items", title="No IO", option={"kind": "item"})
    definition = _definition()
    state = _state()
    access_open = True

    def access(_source):
        if not access_open:
            raise AssertionError("post-preparation source access")
        return SourceAccessDecision()

    prepared = _prepare(
        [CampaignEquipmentAddIntent(page.page_ref, "no-io")],
        definition=definition,
        state=state,
        pages=[page],
        access=access,
    )
    access_open = False
    page.page.title = "Mutated after preparation"
    definition["name"] = "Mutated caller definition"
    state["notes"]["player_notes_markdown"] = "Mutated caller state"

    plan = _plan(prepared)

    assert plan.status is PlanStatus.READY
    assert prepared.snapshot.definition["name"] == "Adapter Hero"
    assert prepared.snapshot.state["notes"]["player_notes_markdown"] == "Preserve me"
    assert plan.candidate_definition["equipment_catalog"][0]["name"] == "No IO"


def test_adapter_module_has_no_forbidden_runtime_or_io_imports():
    source_path = Path(__file__).parents[1] / "player_wiki" / "character_update_adapters.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")

    forbidden = {
        "flask",
        "pathlib",
        "random",
        "requests",
        "socket",
        "time",
        "urllib",
        "player_wiki.db",
        "player_wiki.repository",
        "player_wiki.systems_service",
    }
    assert not {
        module
        for module in imported
        if any(module == blocked or module.startswith(blocked + ".") for blocked in forbidden)
    }


@pytest.mark.parametrize("intent_count", [0, 129])
def test_preparation_enforces_operation_bound(intent_count):
    entry = _entry()
    intents = [
        SystemsItemAddIntent(entry.entry_key, f"item-{index}")
        for index in range(intent_count)
    ]
    with pytest.raises(AdapterPreparationError, match="between 1 and 128"):
        _prepare(intents, entries=[entry])


def test_native_character_normalization_and_state_merge_owners_integrate_without_extra_writes():
    page = _page(
        "mechanics/native-fixed-boon",
        title="Native Fixed Boon",
        option={"kind": "feature", "name": "Native Fixed Boon"},
    )
    base_model = normalize_definition_to_native_model(CharacterDefinition.from_dict(_definition()))
    baseline = base_model.to_dict()
    state = merge_state_with_definition(base_model, build_initial_state(base_model))
    calls = {"normalize": 0, "merge": 0}

    def native_normalize(payload):
        calls["normalize"] += 1
        return normalize_definition_to_native_model(
            CharacterDefinition.from_dict(dict(payload)),
            campaign_page_records=[page],
        ).to_dict()

    def native_merge(payload, current_state):
        calls["merge"] += 1
        return merge_state_with_definition(
            CharacterDefinition.from_dict(dict(payload)),
            dict(current_state),
        )

    prepared = _prepare(
        [CampaignFeatureGrantIntent(page.page_ref, "native-fixed-boon")],
        definition=baseline,
        state=state,
        pages=[page],
        normalize=native_normalize,
        merge=native_merge,
    )

    adapted_definition = prepared.adapter(
        prepared.snapshot.definition,
        prepared.operations[0],
    )
    direct_derivation = prepared.derive(adapted_definition, prepared.snapshot.state)
    assert direct_derivation.warnings == ()
    assert direct_derivation.character["state"] == state
    calls.update(normalize=0, merge=0)

    plan = _plan(prepared)

    assert plan.status is PlanStatus.READY
    assert calls == {"normalize": 1, "merge": 1}
    assert plan.candidate_definition["features"][-1]["id"] == "native-fixed-boon"
    assert plan.derived_character["state"] == state


def test_preparation_rejects_non_trim_stable_identity_and_non_typed_access_decision():
    entry = _entry()
    with pytest.raises(AdapterPreparationError, match="trim-stable"):
        _prepare([SystemsItemAddIntent(" item|phb|adapter-blade", "item")], entries=[entry])
    with pytest.raises(AdapterPreparationError, match="SourceAccessDecision"):
        _prepare(
            [SystemsItemAddIntent(entry.entry_key, "item")],
            entries=[entry],
            access=lambda _source: True,
        )
