from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from re import fullmatch, sub
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import quote

from flask import abort, redirect, render_template, request, url_for

from .auth import campaign_scope_access_required
from .csrf import CSRF_FIELD_NAME
from .character_update_adapters import (
    CampaignEquipmentAddIntent,
    CampaignFeatureGrantIntent,
    EquipmentSafeRelinkIntent,
    SourceAccessDecision,
    SystemsItemAddIntent,
)
from .character_update_planner import (
    ChangeKind,
    DiagnosticCode,
    OperationKind,
    PlanStatus,
    SemanticCategory,
    SourceIdentity,
    SourceKind,
    StateImpact,
)


MAX_OPERATIONS = 128
MAX_SOURCE_IDENTITY_LENGTH = 512
MAX_FORM_CHOICE_LENGTH = 1600
MAX_QUANTITY = 999

_INTENT_REVIEW = "review"
_INTENT_BACK = "back"
_INTENT_CANCEL = "cancel"
_POST_INTENTS = frozenset({_INTENT_REVIEW, _INTENT_BACK, _INTENT_CANCEL})
_ROW_FIELD_PATTERN = r"operation_(0|[1-9][0-9]{0,2})_(choice|quantity)"

_CHOICE_GROUP_LABELS = {
    OperationKind.CAMPAIGN_FEATURE_GRANT: "Campaign features and boons",
    OperationKind.CAMPAIGN_EQUIPMENT_ADD: "Campaign equipment",
    OperationKind.SYSTEMS_ITEM_ADD: "Approved Systems items",
    OperationKind.EQUIPMENT_SAFE_RELINK: "Safe equipment relinks",
}

_OPERATION_LABELS = {
    OperationKind.CAMPAIGN_FEATURE_GRANT: "Grant campaign feature or boon",
    OperationKind.CAMPAIGN_EQUIPMENT_ADD: "Add campaign equipment",
    OperationKind.SYSTEMS_ITEM_ADD: "Add Systems item",
    OperationKind.EQUIPMENT_SAFE_RELINK: "Relink existing equipment",
}

_PLAN_STATUS_LABELS = {
    PlanStatus.READY: "Ready for a later apply workflow",
    PlanStatus.NO_OP: "No changes needed",
    PlanStatus.BLOCKED: "Blocked — inspect the diagnostics",
}

_STATE_IMPACT_LABELS = {
    StateImpact.PRESERVE_EXACT: "Existing character state stays exactly as it is.",
    StateImpact.RECONCILE_REQUIRED: (
        "A later apply workflow would reconcile new resource or inventory state."
    ),
}

_DIAGNOSTIC_MESSAGES = {
    DiagnosticCode.INVALID_INPUT: "The proposed operation is outside the supported update contract.",
    DiagnosticCode.UNSUPPORTED_SYSTEM: "Only DND-5E characters can use this preview.",
    DiagnosticCode.UNSUPPORTED_OPERATION: "One operation is not supported by this preview.",
    DiagnosticCode.UNSUPPORTED_VERSION: "One operation uses an unsupported preview version.",
    DiagnosticCode.SOURCE_POLICY_FAILED: "A selected source is no longer eligible or visible.",
    DiagnosticCode.AMBIGUOUS_SOURCE: "A selected source no longer has one exact match.",
    DiagnosticCode.CHOICE_BEARING: "That grant needs additional choices in a separate editor.",
    DiagnosticCode.DUPLICATE_OPERATION: "The same operation was selected more than once.",
    DiagnosticCode.CONFLICTING_INTENT: "Multiple operations target the same character entry.",
    DiagnosticCode.IDENTITY_COLLISION: "The proposed change conflicts with an existing character entry.",
    DiagnosticCode.MISSING_DEPENDENCY: "An operation dependency is missing.",
    DiagnosticCode.SELF_DEPENDENCY: "An operation cannot depend on itself.",
    DiagnosticCode.OUT_OF_REQUEST_DEPENDENCY: "An operation depends on content outside this preview.",
    DiagnosticCode.CYCLIC_DEPENDENCY: "The proposed operations contain a dependency cycle.",
    DiagnosticCode.MISSING_WHOLE_STATE: "A complete character-state snapshot is required.",
    DiagnosticCode.MUTABLE_STATE_HAZARD: "The proposed change could alter existing mutable state.",
    DiagnosticCode.AMBIGUOUS_RELINK: "The equipment relink is no longer an exact safe match.",
    DiagnosticCode.ADAPTER_FAILED: "The native character adapter could not prepare this operation.",
    DiagnosticCode.DERIVATION_FAILED: "Native DND-5E derivation could not preview this update.",
    DiagnosticCode.DERIVATION_WARNING: "Native DND-5E derivation reported an unresolved warning.",
    DiagnosticCode.PROJECTION_FAILED: "The semantic preview could not be projected safely.",
    DiagnosticCode.PROJECTION_WARNING: "The semantic preview reported an unresolved warning.",
    DiagnosticCode.STATE_IMPACT_FAILED: "State impact could not be projected safely.",
    DiagnosticCode.STATE_IMPACT_WARNING: "State impact reported an unresolved warning.",
    DiagnosticCode.STATE_IMPACT_HAZARD: "The preview found a mutable-state hazard.",
    DiagnosticCode.STATE_IMPACT_MISMATCH: "The projected state change exceeded the eligible envelope.",
    DiagnosticCode.INVALID_SEMANTIC_DIFF: "The semantic preview returned an unsupported change summary.",
    DiagnosticCode.UNEXPLAINED_SEMANTIC_CHANGE: "The preview found a change not explained by the selected operations.",
}


@dataclass(frozen=True)
class CharacterUpdatePreviewRouteDependencies:
    load_character_context: Callable[..., tuple[object, object]]
    can_manage_campaign_session: Callable[..., bool]
    get_authenticated_user: Callable[..., object | None]
    get_current_auth_source: Callable[..., str]
    is_dnd_5e_system: Callable[..., bool]
    redirect_unsupported_native_character_tools: Callable[..., object]
    get_systems_service: Callable[..., object]
    list_builder_campaign_page_records: Callable[..., list[object]]
    list_enabled_systems_items: Callable[..., list[object]]
    can_access_campaign_systems_entry: Callable[..., bool]
    build_campaign_page_character_option: Callable[..., Mapping[str, Any] | None]
    campaign_page_option_allowed: Callable[..., bool]
    campaign_option_is_choice_bearing: Callable[..., bool]
    systems_item_is_approved: Callable[..., bool]
    character_definition_from_dict: Callable[..., object]
    prepare_native_derivation_foundation: Callable[..., object]
    normalize_definition_with_prepared_native_foundation: Callable[..., object]
    merge_state_with_definition: Callable[..., Mapping[str, Any]]
    prepare_character_update_adapters: Callable[..., object]
    plan_character_update: Callable[..., object]


@dataclass(frozen=True, slots=True)
class _UpdateChoice:
    value: str
    kind: OperationKind
    label: str
    source_kind: SourceKind
    source_value: str
    target_id: str
    quantity_supported: bool


@dataclass(frozen=True, slots=True)
class _SourceFoundation:
    systems_service: object
    campaign_page_records: tuple[object, ...]
    systems_entries: tuple[object, ...]
    choices: tuple[_UpdateChoice, ...]


def _single_value(name: str) -> str | None:
    values = request.form.getlist(name)
    if len(values) != 1:
        return None
    return str(values[0])


def _has_only_structural_form_fields() -> bool:
    if len(request.form) > (MAX_OPERATIONS * 2) + 3:
        return False
    for name in request.form.keys():
        if name in {CSRF_FIELD_NAME, "intent", "operation_count"}:
            continue
        if fullmatch(_ROW_FIELD_PATTERN, str(name)) is None:
            return False
    return all(len(request.form.getlist(name)) == 1 for name in request.form.keys())


def _stable_target_id(prefix: str, source_value: str) -> str:
    source_slug = sub(r"[^a-z0-9]+", "-", source_value.casefold()).strip("-")
    if not source_slug:
        return ""
    target = f"{prefix}-{source_slug}"
    return target if len(target) <= MAX_SOURCE_IDENTITY_LENGTH else ""


def _choice_value(
    kind: OperationKind,
    source_kind: SourceKind,
    source_value: str,
    target_id: str,
) -> str:
    return ":".join(
        (
            kind.value,
            source_kind.value,
            quote(source_value, safe=""),
            quote(target_id, safe=""),
        )
    )


def _page_ref(record: object) -> str:
    return str(getattr(record, "page_ref", "") or "").strip()


def _page_title(record: object) -> str:
    page = getattr(record, "page", None)
    return str(getattr(page, "title", "") or "").strip()


def _entry_key(entry: object) -> str:
    return str(getattr(entry, "entry_key", "") or "").strip()


def _entry_title(entry: object) -> str:
    return str(getattr(entry, "title", "") or "").strip()


def _new_choice(
    *,
    kind: OperationKind,
    label: str,
    source_kind: SourceKind,
    source_value: str,
    target_id: str,
    quantity_supported: bool,
) -> _UpdateChoice | None:
    if (
        not source_value
        or len(source_value) > MAX_SOURCE_IDENTITY_LENGTH
        or not target_id
        or len(target_id) > MAX_SOURCE_IDENTITY_LENGTH
    ):
        return None
    value = _choice_value(kind, source_kind, source_value, target_id)
    if len(value) > MAX_FORM_CHOICE_LENGTH:
        return None
    return _UpdateChoice(
        value=value,
        kind=kind,
        label=label or "Untitled source",
        source_kind=source_kind,
        source_value=source_value,
        target_id=target_id,
        quantity_supported=quantity_supported,
    )


def _build_source_foundation(
    dependencies: CharacterUpdatePreviewRouteDependencies,
    campaign_slug: str,
    campaign: object,
    record: object,
) -> _SourceFoundation:
    page_records = tuple(
        dependencies.list_builder_campaign_page_records(campaign_slug, campaign)
    )
    systems_service = dependencies.get_systems_service()
    systems_entries = tuple(
        dependencies.list_enabled_systems_items(systems_service, campaign_slug)
    )

    feature_choices: list[_UpdateChoice] = []
    campaign_item_choices: list[_UpdateChoice] = []
    for page_record in page_records:
        page_ref = _page_ref(page_record)
        title = _page_title(page_record)
        if not page_ref or not title:
            continue
        page = getattr(page_record, "page", None)
        section = str(getattr(page, "section", "") or "").strip()
        option = dict(
            dependencies.build_campaign_page_character_option(
                page_record,
                default_kind="item" if section == "Items" else "feature",
            )
            or {}
        )
        if dependencies.campaign_option_is_choice_bearing(option):
            continue
        if dependencies.campaign_page_option_allowed(
            page_record,
            field_kind="campaign_page_feature",
            campaign_option=option,
        ):
            choice = _new_choice(
                kind=OperationKind.CAMPAIGN_FEATURE_GRANT,
                label=title,
                source_kind=SourceKind.CAMPAIGN_PAGE,
                source_value=page_ref,
                target_id=_stable_target_id("campaign-feature", page_ref),
                quantity_supported=False,
            )
            if choice is not None:
                feature_choices.append(choice)
        if dependencies.campaign_page_option_allowed(
            page_record,
            field_kind="campaign_page_item",
            campaign_option=option,
        ):
            choice = _new_choice(
                kind=OperationKind.CAMPAIGN_EQUIPMENT_ADD,
                label=title,
                source_kind=SourceKind.CAMPAIGN_PAGE,
                source_value=page_ref,
                target_id=_stable_target_id("campaign-item", page_ref),
                quantity_supported=True,
            )
            if choice is not None:
                campaign_item_choices.append(choice)

    systems_item_choices: list[_UpdateChoice] = []
    retained_systems_entries: list[object] = []
    for entry in systems_entries:
        if str(getattr(entry, "entry_type", "") or "").strip().casefold() != "item":
            continue
        entry_key = _entry_key(entry)
        entry_slug = str(getattr(entry, "slug", "") or "").strip()
        if (
            not entry_key
            or not entry_slug
            or not dependencies.can_access_campaign_systems_entry(
                campaign_slug, entry_slug
            )
            or not dependencies.systems_item_is_approved(entry)
        ):
            continue
        choice = _new_choice(
            kind=OperationKind.SYSTEMS_ITEM_ADD,
            label=_entry_title(entry),
            source_kind=SourceKind.SYSTEMS_ENTRY,
            source_value=entry_key,
            target_id=_stable_target_id("systems-item", entry_key),
            quantity_supported=True,
        )
        if choice is not None:
            systems_item_choices.append(choice)
            retained_systems_entries.append(entry)

    add_choices = feature_choices + campaign_item_choices + systems_item_choices
    target_counts = Counter(choice.target_id for choice in add_choices)
    add_choices = [
        choice for choice in add_choices if target_counts[choice.target_id] == 1
    ]
    feature_choices = [
        choice
        for choice in add_choices
        if choice.kind is OperationKind.CAMPAIGN_FEATURE_GRANT
    ]
    campaign_item_choices = [
        choice
        for choice in add_choices
        if choice.kind is OperationKind.CAMPAIGN_EQUIPMENT_ADD
    ]
    systems_item_choices = [
        choice for choice in add_choices if choice.kind is OperationKind.SYSTEMS_ITEM_ADD
    ]

    relink_choices: list[_UpdateChoice] = []
    state = dict(getattr(getattr(record, "state_record", None), "state", {}) or {})
    inventory_rows = [
        dict(row)
        for row in list(state.get("inventory") or [])
        if isinstance(row, Mapping)
    ]
    inventory_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in inventory_rows:
        row_id = str(row.get("catalog_ref") or row.get("id") or "").strip()
        if row_id:
            inventory_by_id.setdefault(row_id, []).append(row)

    definition = getattr(record, "definition", None)
    for raw_equipment in list(getattr(definition, "equipment_catalog", None) or []):
        equipment = dict(raw_equipment) if isinstance(raw_equipment, Mapping) else {}
        equipment_id = str(equipment.get("id") or "").strip()
        equipment_name = str(equipment.get("name") or "").strip()
        if (
            not equipment_id
            or len(equipment_id) > MAX_SOURCE_IDENTITY_LENGTH
            or not equipment_name
            or equipment.get("page_ref")
            or equipment.get("systems_ref")
            or len(inventory_by_id.get(equipment_id, ())) != 1
        ):
            continue
        matching_sources = [
            choice
            for choice in campaign_item_choices + systems_item_choices
            if choice.label == equipment_name
        ]
        if len(matching_sources) != 1:
            continue
        source_choice = matching_sources[0]
        relink = _new_choice(
            kind=OperationKind.EQUIPMENT_SAFE_RELINK,
            label=f"{equipment_name} — {source_choice.label}",
            source_kind=source_choice.source_kind,
            source_value=source_choice.source_value,
            target_id=equipment_id,
            quantity_supported=False,
        )
        if relink is not None:
            relink_choices.append(relink)

    choices = tuple(
        sorted(
            feature_choices
            + campaign_item_choices
            + systems_item_choices
            + relink_choices,
            key=lambda choice: (
                tuple(_CHOICE_GROUP_LABELS).index(choice.kind),
                choice.label.casefold(),
                choice.value,
            ),
        )
    )
    retained_entry_keys = {
        choice.source_value
        for choice in choices
        if choice.source_kind is SourceKind.SYSTEMS_ENTRY
    }
    return _SourceFoundation(
        systems_service,
        page_records,
        tuple(
            entry
            for entry in retained_systems_entries
            if _entry_key(entry) in retained_entry_keys
        ),
        choices,
    )


def _empty_rows(count: int) -> list[dict[str, str]]:
    return [
        {"index": str(index), "choice": "", "quantity": "1"}
        for index in range(count)
    ]


def _parse_form(
    choice_index: Mapping[str, _UpdateChoice] | None,
    *,
    require_complete: bool,
) -> tuple[str, list[dict[str, str]], dict[str, str], str | None]:
    errors: dict[str, str] = {}
    first_error: str | None = None

    def add_error(field_id: str, message: str) -> None:
        nonlocal first_error
        if field_id not in errors:
            errors[field_id] = message
        if first_error is None:
            first_error = field_id

    raw_count = _single_value("operation_count")
    count_value = (
        raw_count
        if raw_count is not None and fullmatch(r"[0-9]{1,3}", raw_count)
        else "1"
    )
    if (
        raw_count is None
        or fullmatch(r"[1-9][0-9]{0,2}", raw_count) is None
        or not 1 <= int(raw_count) <= MAX_OPERATIONS
    ):
        count = 1
        add_error(
            "operation-count",
            "Choose between 1 and 128 operation rows.",
        )
    else:
        count = int(raw_count)

    allowed_names = {CSRF_FIELD_NAME, "intent", "operation_count"}
    allowed_names.update(
        f"operation_{index}_{suffix}"
        for index in range(count)
        for suffix in ("choice", "quantity")
    )
    if set(request.form.keys()) - allowed_names:
        add_error(
            "operation-count",
            "The submitted form contained fields outside this preview.",
        )

    rows: list[dict[str, str]] = []
    for index in range(count):
        choice_name = f"operation_{index}_choice"
        quantity_name = f"operation_{index}_quantity"
        choice_field_id = f"operation-{index}-choice"
        quantity_field_id = f"operation-{index}-quantity"

        raw_choice = _single_value(choice_name)
        choice_value = str(raw_choice or "")
        if (
            raw_choice is None
            or len(choice_value) > MAX_FORM_CHOICE_LENGTH
            or "\x00" in choice_value
        ):
            choice_value = ""
            add_error(choice_field_id, "Choose one available operation.")
        elif (
            choice_index is not None
            and choice_value
            and choice_value not in choice_index
        ):
            choice_value = ""
            add_error(
                choice_field_id,
                "That source is no longer available. Choose a current option.",
            )
        elif require_complete and not choice_value:
            add_error(choice_field_id, "Choose one available operation.")

        raw_quantity = _single_value(quantity_name)
        quantity_value = (
            raw_quantity
            if raw_quantity is not None
            and len(raw_quantity) <= 3
            and "\x00" not in raw_quantity
            else "1"
        )
        if (
            raw_quantity is None
            or len(raw_quantity) > 3
            or "\x00" in raw_quantity
            or fullmatch(r"[1-9][0-9]*", raw_quantity) is None
            or int(raw_quantity) > MAX_QUANTITY
        ):
            add_error(
                quantity_field_id,
                f"Enter a whole-number quantity from 1 to {MAX_QUANTITY}.",
            )

        rows.append(
            {
                "index": str(index),
                "choice": choice_value,
                "quantity": quantity_value,
            }
        )

    for name in request.form.keys():
        if len(request.form.getlist(name)) != 1:
            add_error(
                "operation-count",
                "Each preview field must be submitted exactly once.",
            )
            break
    return count_value, rows, errors, first_error


def _validate_row_choices(
    rows: Sequence[Mapping[str, str]],
    choice_index: Mapping[str, _UpdateChoice],
    errors: Mapping[str, str],
    first_error: str | None,
    *,
    require_complete: bool,
) -> tuple[list[dict[str, str]], dict[str, str], str | None]:
    validated_rows = [dict(row) for row in rows]
    validated_errors = dict(errors)
    validated_first_error = first_error
    for index, row in enumerate(validated_rows):
        choice_value = str(row.get("choice") or "")
        field_id = f"operation-{index}-choice"
        if choice_value and choice_value not in choice_index:
            row["choice"] = ""
            validated_errors.setdefault(
                field_id,
                "That source is no longer available. Choose a current option.",
            )
            if validated_first_error is None:
                validated_first_error = field_id
        elif require_complete and not choice_value:
            validated_errors.setdefault(
                field_id,
                "Choose one available operation.",
            )
            if validated_first_error is None:
                validated_first_error = field_id
    return validated_rows, validated_errors, validated_first_error


def _choice_groups(choices: Sequence[_UpdateChoice]) -> list[dict[str, object]]:
    return [
        {
            "kind": kind.value,
            "label": label,
            "choices": [choice for choice in choices if choice.kind is kind],
        }
        for kind, label in _CHOICE_GROUP_LABELS.items()
    ]


def _intents_for_rows(
    rows: Sequence[Mapping[str, str]],
    choice_index: Mapping[str, _UpdateChoice],
) -> tuple[object, ...]:
    intents: list[object] = []
    for row in rows:
        choice = choice_index[str(row["choice"])]
        quantity = int(str(row["quantity"]))
        if choice.kind is OperationKind.CAMPAIGN_FEATURE_GRANT:
            intents.append(
                CampaignFeatureGrantIntent(choice.source_value, choice.target_id)
            )
        elif choice.kind is OperationKind.CAMPAIGN_EQUIPMENT_ADD:
            intents.append(
                CampaignEquipmentAddIntent(
                    choice.source_value,
                    choice.target_id,
                    quantity,
                )
            )
        elif choice.kind is OperationKind.SYSTEMS_ITEM_ADD:
            intents.append(
                SystemsItemAddIntent(
                    choice.source_value,
                    choice.target_id,
                    quantity,
                )
            )
        else:
            intents.append(
                EquipmentSafeRelinkIntent(
                    choice.target_id,
                    SourceIdentity(choice.source_kind, choice.source_value),
                )
            )
    return tuple(intents)


def _project_plan(plan: object) -> dict[str, object]:
    operations = [
        {
            "number": index + 1,
            "label": _OPERATION_LABELS.get(
                OperationKind(operation.kind), "Character update operation"
            ),
            "status": str(getattr(operation.status, "value", operation.status)).replace(
                "_", " "
            ).title(),
        }
        for index, operation in enumerate(tuple(getattr(plan, "operations", ())))
    ]
    diagnostics = [
        {
            "message": _DIAGNOSTIC_MESSAGES.get(
                diagnostic.code,
                "The preview found an unsupported conflict.",
            )
        }
        for diagnostic in tuple(getattr(plan, "diagnostics", ()))
    ]

    semantic_rows = tuple(getattr(plan, "semantic_diff", ()))
    categories: list[dict[str, object]] = []
    for category in SemanticCategory:
        rows_by_change: dict[ChangeKind, list[dict[str, str]]] = {
            change: [] for change in ChangeKind
        }
        for row in semantic_rows:
            if SemanticCategory(row.category) is not category:
                continue
            change = ChangeKind(row.change)
            rows_by_change[change].append(
                {
                    "label": str(row.label),
                    "before": str(row.before),
                    "after": str(row.after),
                }
            )
        categories.append(
            {
                "key": category.value,
                "label": category.value[0].upper() + category.value[1:],
                "groups": [
                    {
                        "key": change.value,
                        "label": change.value.title(),
                        "rows": rows_by_change[change],
                    }
                    for change in ChangeKind
                ],
                "has_changes": any(rows_by_change.values()),
            }
        )

    status = PlanStatus(getattr(plan, "status"))
    state_impact = StateImpact(getattr(plan, "state_impact"))
    reconciliation = getattr(plan, "reconciliation", None)
    return {
        "status": status.value,
        "status_label": _PLAN_STATUS_LABELS[status],
        "state_impact": state_impact.value,
        "state_impact_label": _STATE_IMPACT_LABELS[state_impact],
        "resource_addition_count": len(
            tuple(getattr(reconciliation, "resources", ()))
        ),
        "inventory_addition_count": len(
            tuple(getattr(reconciliation, "inventory", ()))
        ),
        "operations": operations,
        "diagnostics": diagnostics,
        "categories": categories,
    }


def _fault_review() -> dict[str, object]:
    return {
        "status": "fault",
        "status_label": "Preview needs inspection",
        "state_impact": "unknown",
        "state_impact_label": (
            "No update was applied. Refresh the character, inspect the selected "
            "sources, and return to this preview."
        ),
        "resource_addition_count": 0,
        "inventory_addition_count": 0,
        "operations": [],
        "diagnostics": [
            {
                "message": (
                    "The current character or source foundation could not be "
                    "prepared safely."
                )
            }
        ],
        "categories": [
            {
                "key": category.value,
                "label": category.value[0].upper() + category.value[1:],
                "groups": [],
                "has_changes": False,
            }
            for category in SemanticCategory
        ],
    }


def _render_page(
    *,
    campaign: object,
    record: object,
    choices: Sequence[_UpdateChoice],
    operation_count: str,
    rows: Sequence[Mapping[str, str]],
    errors: Mapping[str, str] | None = None,
    first_error: str | None = None,
    review: Mapping[str, object] | None = None,
    preview_only: bool = False,
    status_code: int = 200,
):
    return (
        render_template(
            "character_update_preview.html",
            campaign=campaign,
            character=getattr(record, "definition", None),
            choice_groups=_choice_groups(choices),
            choice_count=len(choices),
            operation_count=operation_count,
            operation_rows=list(rows),
            errors=dict(errors or {}),
            first_error=first_error,
            review=dict(review or {}) if review is not None else None,
            preview_only=preview_only,
            active_nav="characters",
        ),
        status_code,
    )


def register_character_update_preview_route(
    app: Any,
    *,
    dependencies: CharacterUpdatePreviewRouteDependencies,
) -> None:
    def character_update_preview_view(
        campaign_slug: str,
        character_slug: str,
    ):
        actor = dependencies.get_authenticated_user()
        preview_only = bool(
            request.method == "GET"
            and dependencies.get_current_auth_source() == "view_as"
            and actor is not None
            and bool(getattr(actor, "is_admin", False))
        )
        can_manage = bool(dependencies.can_manage_campaign_session(campaign_slug))
        if not can_manage and not preview_only:
            abort(403)

        if request.method == "POST":
            intent = _single_value("intent")
            if intent not in _POST_INTENTS or not _has_only_structural_form_fields():
                abort(400)
            if intent == _INTENT_CANCEL:
                return redirect(
                    url_for(
                        "character_read_view",
                        campaign_slug=campaign_slug,
                        character_slug=character_slug,
                    )
                )
        else:
            intent = None

        campaign, record = dependencies.load_character_context(
            campaign_slug, character_slug
        )
        if not (
            dependencies.is_dnd_5e_system(getattr(campaign, "system", ""))
            and dependencies.is_dnd_5e_system(
                getattr(getattr(record, "definition", None), "system", "")
            )
        ):
            return dependencies.redirect_unsupported_native_character_tools(
                campaign_slug,
                character_slug=character_slug,
                message="Character update preview is available only for DND-5E characters.",
            )

        if request.method == "POST":
            require_complete = intent == _INTENT_REVIEW
            operation_count, rows, errors, first_error = _parse_form(
                None,
                require_complete=require_complete,
            )
        else:
            require_complete = False
            operation_count = "1"
            rows = _empty_rows(1)
            errors = {}
            first_error = None

        foundation = _build_source_foundation(
            dependencies,
            campaign_slug,
            campaign,
            record,
        )
        choice_index = {choice.value: choice for choice in foundation.choices}
        if request.method == "GET":
            return _render_page(
                campaign=campaign,
                record=record,
                choices=foundation.choices,
                operation_count=operation_count,
                rows=rows,
                preview_only=preview_only,
            )

        rows, errors, first_error = _validate_row_choices(
            rows,
            choice_index,
            errors,
            first_error,
            require_complete=require_complete,
        )
        if errors:
            return _render_page(
                campaign=campaign,
                record=record,
                choices=foundation.choices,
                operation_count=operation_count,
                rows=rows,
                errors=errors,
                first_error=first_error,
                status_code=400,
            )
        if intent == _INTENT_BACK:
            return _render_page(
                campaign=campaign,
                record=record,
                choices=foundation.choices,
                operation_count=operation_count,
                rows=rows,
            )

        intents = _intents_for_rows(rows, choice_index)

        source_decisions = {
            (choice.source_kind, choice.source_value): SourceAccessDecision()
            for choice in foundation.choices
        }

        def resolve_access(source: SourceIdentity) -> SourceAccessDecision:
            try:
                kind = SourceKind(source.kind)
            except (TypeError, ValueError):
                return SourceAccessDecision(False, False, False)
            return source_decisions.get(
                (kind, str(source.value)),
                SourceAccessDecision(False, False, False),
            )

        try:
            native_foundation = (
                dependencies.prepare_native_derivation_foundation(
                    getattr(record, "definition"),
                    systems_service=foundation.systems_service,
                    campaign_page_records=list(
                        foundation.campaign_page_records
                    ),
                )
            )

            def normalize_definition(
                payload: Mapping[str, Any],
            ) -> Mapping[str, Any]:
                definition = dependencies.character_definition_from_dict(
                    dict(payload)
                )
                normalized = (
                    dependencies.normalize_definition_with_prepared_native_foundation(
                        definition,
                        native_foundation,
                    )
                )
                return dict(normalized.to_dict())

            def merge_state(
                definition_payload: Mapping[str, Any],
                state_payload: Mapping[str, Any],
            ) -> Mapping[str, Any]:
                definition = dependencies.character_definition_from_dict(
                    dict(definition_payload)
                )
                return dict(
                    dependencies.merge_state_with_definition(
                        definition,
                        dict(state_payload),
                    )
                )

            prepared = dependencies.prepare_character_update_adapters(
                target_identity=f"{campaign_slug}/{character_slug}",
                baseline_identity=(
                    "character-state-revision-"
                    f"{int(getattr(getattr(record, 'state_record', None), 'revision', 0))}"
                ),
                definition=dict(record.definition.to_dict()),
                state=dict(record.state_record.state or {}),
                intents=intents,
                campaign_page_records=foundation.campaign_page_records,
                systems_entries=foundation.systems_entries,
                resolve_access=resolve_access,
                normalize_definition=normalize_definition,
                merge_state=merge_state,
            )
            plan = dependencies.plan_character_update(
                prepared.snapshot,
                prepared.operations,
                **prepared.planner_kwargs(),
            )
            review = _project_plan(plan)
            status_code = 200
        except Exception:
            review = _fault_review()
            status_code = 409

        return _render_page(
            campaign=campaign,
            record=record,
            choices=foundation.choices,
            operation_count=operation_count,
            rows=rows,
            review=review,
            status_code=status_code,
        )

    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/update-preview",
        endpoint="character_update_preview_view",
        view_func=campaign_scope_access_required("characters")(
            character_update_preview_view
        ),
        methods=("GET", "POST"),
    )


__all__ = [
    "CharacterUpdatePreviewRouteDependencies",
    "register_character_update_preview_route",
]
