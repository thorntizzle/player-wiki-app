from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import re
import time
import unicodedata
from typing import Any, Callable

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from .auth import (
    can_manage_campaign_combat,
    campaign_scope_access_required,
    get_current_user,
)
from .campaign_combat_service import (
    CampaignCombatRevisionConflictError,
    CampaignCombatValidationError,
)
from .campaign_combat_preset_service import (
    CampaignCombatPresetAuthorizationError,
    CampaignCombatPresetValidationError,
)
from .campaign_combat_preset_sources import CampaignCombatPresetSourceValidationError
from .campaign_combat_preset_store import (
    CampaignCombatPresetConflictError,
    normalize_preset_name,
)
from .combat_models import (
    COMBAT_SOURCE_KIND_CHARACTER,
    COMBAT_SOURCE_KIND_DM_STATBLOCK,
    COMBAT_SOURCE_KIND_MANUAL_NPC,
    COMBAT_SOURCE_KIND_SYSTEMS_MONSTER,
    COMBAT_SOURCE_KINDS,
)
from .combat_preset_models import CampaignCombatPresetEntryInput
from .live_presenter import (
    build_unchanged_live_payload,
    should_short_circuit_live_response,
    should_skip_selected_combatant_detail_render,
)


combat = Blueprint("combat", __name__)


_PRESET_PAGE_SIZE = 25
_MAX_PRESET_PAGE = 1000
_MAX_PRESET_ROWS = 50
_MAX_PRESET_EXPANDED = 50
_MAX_PRESET_BODY_BYTES = 256 * 1024
_SQLITE_MIN_INTEGER = -(2**63)
_SQLITE_MAX_INTEGER = 2**63 - 1
_ENTRY_FIELD_RE = re.compile(
    r"^entry_(?P<index>0|[1-9][0-9]*)_(?P<field>id|source_kind|source_ref|quantity|"
    r"turn_value|initiative_priority|custom_name|initiative_bonus|dexterity_modifier|"
    r"max_hp|movement_total)$"
)
_PRESET_TOP_FIELDS = frozenset(
    {
        "_csrf_token",
        "intent",
        "name",
        "expected_revision",
        "review_digest",
        "entry_count",
        "search_row",
        "search_query",
    }
)
_SOURCE_LABELS = {
    COMBAT_SOURCE_KIND_CHARACTER: "Character",
    COMBAT_SOURCE_KIND_DM_STATBLOCK: "DM Content statblock",
    COMBAT_SOURCE_KIND_SYSTEMS_MONSTER: "Systems monster",
    COMBAT_SOURCE_KIND_MANUAL_NPC: "Manual NPC",
}
_STATUS_LABELS = {
    "current": "Current",
    "source_changed": "Source changed",
    "source_disabled": "Source disabled",
    "entry_disabled": "Entry disabled",
    "missing_or_inaccessible": "Missing or inaccessible",
}


class _PresetReviewError(ValueError):
    def __init__(self, message: str, statuses: list[dict[str, str]]) -> None:
        super().__init__(message)
        self.statuses = statuses


@dataclass(frozen=True)
class CombatRouteDependencies:
    build_campaign_combat_page_context: Callable[..., dict[str, object]]
    redirect_to_campaign_combat_dm: Callable[..., Any]
    parse_requested_combatant_id: Callable[..., int | None]
    build_combat_live_metadata: Callable[..., dict[str, object]]
    build_campaign_combat_live_state: Callable[..., dict[str, object]]
    build_live_json_response: Callable[..., Any]
    normalize_combat_dm_view: Callable[[str], str]
    build_campaign_combat_dm_status_context: Callable[..., dict[str, object]]
    build_campaign_combat_dm_live_state: Callable[..., dict[str, object]]
    build_campaign_combat_status_context: Callable[..., dict[str, object]]
    build_campaign_combat_status_live_state: Callable[..., dict[str, object]]
    parse_live_detail_state_token_header: Callable[[], str]
    require_supported_combat_system: Callable[[str], Any]
    get_campaign_combat_service: Callable[[], Any]
    respond_to_campaign_combat_mutation: Callable[..., Any]
    parse_expected_combatant_revision: Callable[[], int | None]
    normalize_combat_return_view: Callable[[str], str]
    get_requested_combatant_id_from_values: Callable[[], int | None]


def _dependencies() -> CombatRouteDependencies:
    return current_app.extensions["combat_route_dependencies"]


def _preset_service():
    return current_app.extensions["campaign_combat_preset_service"]


def _bounded_integer(
    value: Any,
    label: str,
    *,
    minimum: int = _SQLITE_MIN_INTEGER,
    maximum: int = _SQLITE_MAX_INTEGER,
    optional: bool = False,
) -> int | None:
    text = str(value or "").strip()
    if optional and not text:
        return None
    if not text or not text.lstrip("+-").isdecimal():
        raise ValueError(f"Enter a valid {label}.")
    parsed = int(text)
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"Enter a valid {label}.")
    return parsed


def _bounded_nfkc_name(value: Any, label: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not normalized or len(normalized.encode("utf-8")) > 320:
        raise ValueError(f"Enter a {label} no longer than 320 UTF-8 bytes.")
    return normalized


def _empty_preset_row() -> dict[str, str]:
    return {
        "id": "",
        "source_kind": COMBAT_SOURCE_KIND_MANUAL_NPC,
        "source_ref": "",
        "quantity": "1",
        "turn_value": "",
        "initiative_priority": "1",
        "custom_name": "",
        "initiative_bonus": "0",
        "dexterity_modifier": "0",
        "max_hp": "0",
        "movement_total": "30",
    }


def _draft_from_preset(preset: Any) -> dict[str, Any]:
    return {
        "name": preset.name,
        "expected_revision": str(preset.revision),
        "rows": [
            {
                "id": str(entry.id),
                "source_kind": entry.source_kind,
                "source_ref": entry.source_ref,
                "quantity": str(entry.quantity),
                "turn_value": "" if entry.turn_value is None else str(entry.turn_value),
                "initiative_priority": str(entry.initiative_priority),
                "custom_name": entry.custom_name,
                "initiative_bonus": (
                    "" if entry.initiative_bonus is None else str(entry.initiative_bonus)
                ),
                "dexterity_modifier": (
                    "" if entry.dexterity_modifier is None else str(entry.dexterity_modifier)
                ),
                "max_hp": "" if entry.max_hp is None else str(entry.max_hp),
                "movement_total": (
                    "" if entry.movement_total is None else str(entry.movement_total)
                ),
            }
            for entry in preset.entries
        ],
    }


def _parse_raw_preset_draft() -> dict[str, Any]:
    if request.content_length is not None and request.content_length > _MAX_PRESET_BODY_BYTES:
        abort(413)
    for key in request.form:
        if len(request.form.getlist(key)) != 1:
            raise ValueError("Submit each saved encounter field only once.")
        match = _ENTRY_FIELD_RE.fullmatch(key)
        if key not in _PRESET_TOP_FIELDS and match is None:
            raise ValueError("The saved encounter form contains an unknown field.")

    count = _bounded_integer(
        request.form.get("entry_count", ""),
        "entry count",
        minimum=0,
        maximum=_MAX_PRESET_ROWS,
    )
    assert count is not None
    seen_indices: set[int] = set()
    for key in request.form:
        match = _ENTRY_FIELD_RE.fullmatch(key)
        if match is None:
            continue
        index = int(match.group("index"))
        if index >= count:
            raise ValueError("The saved encounter form contains an unexpected row.")
        seen_indices.add(index)
    if count and seen_indices != set(range(count)):
        raise ValueError("The saved encounter form is missing a row.")

    rows: list[dict[str, str]] = []
    for index in range(count):
        row = {
            field: request.form.get(f"entry_{index}_{field}", "")
            for field in (
                "id",
                "source_kind",
                "source_ref",
                "quantity",
                "turn_value",
                "initiative_priority",
                "custom_name",
                "initiative_bonus",
                "dexterity_modifier",
                "max_hp",
                "movement_total",
            )
        }
        rows.append(row)
    return {
        "name": request.form.get("name", ""),
        "expected_revision": request.form.get("expected_revision", ""),
        "review_digest": request.form.get("review_digest", ""),
        "rows": rows,
        "search_row": request.form.get("search_row", ""),
        "search_query": request.form.get("search_query", ""),
    }


def _parse_preset_entries(
    draft: dict[str, Any],
    *,
    loaded_preset: Any | None,
) -> tuple[str, tuple[CampaignCombatPresetEntryInput, ...]]:
    normalized_name = _bounded_nfkc_name(draft.get("name"), "saved encounter name")
    try:
        normalized_name, name_key = normalize_preset_name(normalized_name)
    except (TypeError, ValueError) as exc:
        raise ValueError("Enter a valid saved encounter name.") from exc
    if len(name_key.encode("utf-8")) > 512:
        raise ValueError("Enter a valid saved encounter name.")

    loaded_by_id = {
        entry.id: entry for entry in (loaded_preset.entries if loaded_preset is not None else ())
    }
    retained_ids: set[int] = set()
    parsed: list[CampaignCombatPresetEntryInput] = []
    expanded = 0
    for position, row in enumerate(draft["rows"]):
        source_kind = str(row.get("source_kind") or "").strip()
        if source_kind not in COMBAT_SOURCE_KINDS:
            raise ValueError(f"Choose a valid source type for row {position + 1}.")
        retained_id = _bounded_integer(
            row.get("id"), "retained row ID", minimum=1, optional=True
        )
        if retained_id is not None:
            if loaded_preset is None or retained_id not in loaded_by_id or retained_id in retained_ids:
                raise ValueError(f"Row {position + 1} has an invalid retained row ID.")
            retained_ids.add(retained_id)
        quantity = _bounded_integer(
            row.get("quantity"), "quantity", minimum=1, maximum=50
        )
        assert quantity is not None
        expanded += quantity
        if expanded > _MAX_PRESET_EXPANDED:
            raise ValueError("A saved encounter may expand to at most 50 combatants.")
        turn_value = _bounded_integer(row.get("turn_value"), "turn value", optional=True)
        priority = _bounded_integer(
            row.get("initiative_priority"), "initiative priority", minimum=1
        )
        assert priority is not None
        source_ref = str(row.get("source_ref") or "").strip()
        if len(source_ref.encode("utf-8")) > 512:
            raise ValueError(f"Row {position + 1} has an invalid source reference.")

        if source_kind == COMBAT_SOURCE_KIND_MANUAL_NPC:
            custom_name = _bounded_nfkc_name(
                row.get("custom_name"), f"name for row {position + 1}"
            )
            initiative_bonus = _bounded_integer(row.get("initiative_bonus"), "initiative bonus")
            dexterity_modifier = _bounded_integer(
                row.get("dexterity_modifier"), "Dexterity modifier"
            )
            max_hp = _bounded_integer(row.get("max_hp"), "max HP", minimum=0)
            movement_total = _bounded_integer(
                row.get("movement_total"), "movement", minimum=0
            )
            entry = CampaignCombatPresetEntryInput(
                id=retained_id,
                source_kind=source_kind,
                quantity=quantity,
                turn_value=turn_value,
                initiative_priority=priority,
                custom_name=custom_name,
                initiative_bonus=initiative_bonus,
                dexterity_modifier=dexterity_modifier,
                max_hp=max_hp,
                movement_total=movement_total,
            )
        else:
            if not source_ref:
                raise ValueError(f"Choose an exact source reference for row {position + 1}.")
            entry = CampaignCombatPresetEntryInput(
                id=retained_id,
                source_kind=source_kind,
                source_ref=source_ref,
                quantity=quantity,
                turn_value=turn_value,
                initiative_priority=priority,
            )
        parsed.append(entry)
    return normalized_name, tuple(parsed)


def _review_preset_entries(
    campaign_slug: str,
    draft: dict[str, Any],
    *,
    loaded_preset: Any | None,
) -> tuple[str, tuple[CampaignCombatPresetEntryInput, ...], list[dict[str, str]], str]:
    name, entries = _parse_preset_entries(draft, loaded_preset=loaded_preset)
    loaded_by_id = {
        entry.id: entry for entry in (loaded_preset.entries if loaded_preset is not None else ())
    }
    inspection_inputs = []
    retained_source_positions: set[int] = set()
    for position, entry in enumerate(entries):
        loaded = loaded_by_id.get(entry.id)
        if (
            entry.source_kind != COMBAT_SOURCE_KIND_MANUAL_NPC
            and loaded is not None
            and loaded.source_kind == entry.source_kind
            and loaded.source_ref == entry.source_ref
        ):
            retained_source_positions.add(position)
            inspection_inputs.append(
                replace(
                    entry,
                    source_version=loaded.source_version,
                    version_scheme=loaded.version_scheme,
                )
            )
        elif entry.source_kind != COMBAT_SOURCE_KIND_MANUAL_NPC:
            inspection_inputs.append(
                replace(
                    entry,
                    source_version="0" * 64,
                    version_scheme="combat-seed-v1-sha256",
                )
            )
        else:
            inspection_inputs.append(entry)

    service = _preset_service()
    inspections = service.inspect_entries(campaign_slug, tuple(inspection_inputs))
    statuses = []
    for position, (entry, inspection) in enumerate(zip(entries, inspections, strict=True)):
        status = inspection.status
        if position not in retained_source_positions and status == "source_changed":
            status = "current"
        statuses.append(
            {
                "status": status,
                "label": _STATUS_LABELS.get(status, "Unavailable"),
                "source_label": _SOURCE_LABELS[entry.source_kind],
            }
        )
    blocked_statuses = {"source_disabled", "entry_disabled", "missing_or_inaccessible"}
    if any(row["status"] in blocked_statuses for row in statuses):
        raise _PresetReviewError(
            "Replace or remove unavailable sources before review.",
            statuses,
        )
    prepared = service.source_resolver.prepare_entries_for_save(campaign_slug, entries)

    revision = loaded_preset.revision if loaded_preset is not None else None
    digest_payload = {
        "name": name,
        "revision": revision,
        "rows": [
            {
                "id": entry.id,
                "position": position,
                "source_kind": entry.source_kind,
                "source_ref": entry.source_ref,
                "quantity": entry.quantity,
                "turn_value": entry.turn_value,
                "initiative_priority": entry.initiative_priority,
                "custom_name": entry.custom_name,
                "initiative_bonus": entry.initiative_bonus,
                "dexterity_modifier": entry.dexterity_modifier,
                "max_hp": entry.max_hp,
                "movement_total": entry.movement_total,
                "source_version": entry.source_version,
                "version_scheme": entry.version_scheme,
            }
            for position, entry in enumerate(prepared)
        ],
        "version": "preset-review-v1",
    }
    digest = hashlib.sha256(
        json.dumps(
            digest_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return name, prepared, statuses, digest


def _preset_url(
    campaign_slug: str,
    *,
    combatant_id: int | None = None,
    preset: str | int | None = None,
    preset_mode: str = "",
    preset_page: int | None = None,
    anchor: bool = True,
) -> str:
    values: dict[str, Any] = {"campaign_slug": campaign_slug, "view": "controls"}
    if combatant_id is not None:
        values["combatant"] = combatant_id
    if preset is not None:
        values["preset"] = preset
    if preset_mode:
        values["preset_mode"] = preset_mode
    if preset_page is not None and preset_page != 1:
        values["preset_page"] = preset_page
    url = url_for("campaign_combat_dm_view", **values)
    return f"{url}#saved-encounters" if anchor else url


def _safe_source_choice_maps(context: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {
        COMBAT_SOURCE_KIND_CHARACTER: {
            str(choice.get("slug") or ""): str(choice.get("name") or "")
            for choice in list(context.get("available_character_choices") or [])
        },
        COMBAT_SOURCE_KIND_DM_STATBLOCK: {
            str(choice.get("id") or ""): str(choice.get("title") or "")
            for choice in list(context.get("available_statblock_choices") or [])
        },
    }


def _present_preset_rows(
    entries: Any,
    *,
    statuses: Any,
    choice_maps: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    presented = []
    for position, (entry, status_row) in enumerate(zip(entries, statuses, strict=True)):
        safe_label = (
            entry.custom_name
            if entry.source_kind == COMBAT_SOURCE_KIND_MANUAL_NPC
            else choice_maps.get(entry.source_kind, {}).get(entry.source_ref, "")
        )
        presented.append(
            {
                "position": position + 1,
                "entry": entry,
                "source_label": _SOURCE_LABELS[entry.source_kind],
                "safe_label": safe_label,
                "status": status_row["status"] if isinstance(status_row, dict) else status_row.status,
                "status_label": (
                    status_row["label"]
                    if isinstance(status_row, dict)
                    else _STATUS_LABELS.get(status_row.status, "Unavailable")
                ),
                "setup_label": (
                    "Custom setup"
                    if entry.source_kind == COMBAT_SOURCE_KIND_MANUAL_NPC
                    else "Derived from source when saved"
                ),
            }
        )
    return presented


def _build_preset_browser(
    campaign_slug: str,
    context: dict[str, Any],
    *,
    page: int = 1,
    mode: str = "list",
    selected: Any | None = None,
    draft: dict[str, Any] | None = None,
    review_entries: Any = (),
    review_statuses: Any = (),
    review_digest: str = "",
    draft_statuses: list[dict[str, str]] | None = None,
    errors: list[str] | None = None,
    conflict: bool = False,
    search_results: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    service = _preset_service()
    rows = service.list_presets(
        campaign_slug,
        limit=_PRESET_PAGE_SIZE + 1,
        offset=(page - 1) * _PRESET_PAGE_SIZE,
    )
    has_next = len(rows) > _PRESET_PAGE_SIZE
    rows = rows[:_PRESET_PAGE_SIZE]
    combatant_id = context.get("requested_combatant_id")
    choice_maps = _safe_source_choice_maps(context)
    selected_rows: list[dict[str, Any]] = []
    if selected is not None and mode == "detail":
        try:
            inspected = service.inspect_entries(campaign_slug, selected.entries)
        except (CampaignCombatPresetAuthorizationError, CampaignCombatPresetValidationError):
            inspected = tuple(
                type("Inspection", (), {"status": "missing_or_inaccessible"})()
                for _entry in selected.entries
            )
        selected_rows = _present_preset_rows(
            selected.entries,
            statuses=inspected,
            choice_maps=choice_maps,
        )
    review_rows = _present_preset_rows(
        review_entries,
        statuses=review_statuses,
        choice_maps=choice_maps,
    ) if review_entries else []
    return {
        "mode": mode,
        "page": page,
        "presets": rows,
        "has_previous": page > 1,
        "has_next": has_next,
        "previous_url": _preset_url(
            campaign_slug, combatant_id=combatant_id, preset_page=page - 1
        ) if page > 1 else "",
        "next_url": _preset_url(
            campaign_slug, combatant_id=combatant_id, preset_page=page + 1
        ) if has_next else "",
        "list_url": _preset_url(campaign_slug, combatant_id=combatant_id),
        "new_url": _preset_url(campaign_slug, combatant_id=combatant_id, preset="new"),
        "selected": selected,
        "selected_rows": selected_rows,
        "draft": draft,
        "review_rows": review_rows,
        "review_digest": review_digest,
        "review_expanded_count": sum(entry.quantity for entry in review_entries),
        "draft_statuses": draft_statuses or [],
        "errors": errors or [],
        "conflict": conflict,
        "search_results": search_results or [],
        "character_choices": list(context.get("available_character_choices") or []),
        "statblock_choices": list(context.get("available_statblock_choices") or []),
        "create_action": url_for(
            "campaign_combat_preset_collection",
            campaign_slug=campaign_slug,
            combatant=combatant_id,
        ),
        "update_action": (
            url_for(
                "campaign_combat_preset_item",
                campaign_slug=campaign_slug,
                preset_id=selected.id,
                combatant=combatant_id,
            )
            if selected is not None
            else ""
        ),
        "detail_url": (
            _preset_url(campaign_slug, combatant_id=combatant_id, preset=selected.id)
            if selected is not None
            else ""
        ),
        "edit_url": (
            _preset_url(
                campaign_slug,
                combatant_id=combatant_id,
                preset=selected.id,
                preset_mode="edit",
            )
            if selected is not None
            else ""
        ),
        "delete_action": (
            url_for(
                "campaign_combat_preset_delete",
                campaign_slug=campaign_slug,
                preset_id=selected.id,
                combatant=combatant_id,
            )
            if selected is not None
            else ""
        ),
        "combatant_id": combatant_id,
        "source_labels": _SOURCE_LABELS,
    }


def _render_preset_controls_document(
    campaign_slug: str,
    *,
    status: int = 200,
    **browser_options: Any,
):
    dependencies = _dependencies()
    context = dependencies.build_campaign_combat_page_context(
        campaign_slug,
        include_control_choices=True,
        combat_subpage="dm",
        combat_dm_view="controls",
        sync_player_character_snapshots=False,
    )
    context["combat_preset_browser"] = _build_preset_browser(
        campaign_slug,
        context,
        **browser_options,
    )
    return render_template("combat_dm.html", **context), status


def _require_preset_route_access(campaign_slug: str) -> None:
    if not can_manage_campaign_combat(campaign_slug):
        abort(403)
    if _dependencies().require_supported_combat_system(campaign_slug) is None:
        abort(404)
    try:
        _preset_service().list_presets(campaign_slug, limit=1, offset=0)
    except CampaignCombatPresetAuthorizationError:
        abort(403)


def _load_selected_preset(campaign_slug: str, preset_id: int):
    try:
        selected = _preset_service().get_preset(campaign_slug, preset_id)
    except (CampaignCombatPresetAuthorizationError, CampaignCombatPresetValidationError):
        abort(404)
    if selected is None:
        abort(404)
    return selected


@campaign_scope_access_required("combat")
def campaign_combat_view(campaign_slug: str):
    dependencies = _dependencies()
    if can_manage_campaign_combat(campaign_slug):
        return dependencies.redirect_to_campaign_combat_dm(
            campaign_slug,
            combatant_id=dependencies.parse_requested_combatant_id(),
        )
    context = dependencies.build_campaign_combat_page_context(
        campaign_slug,
        combat_subpage="combat",
    )
    return render_template("combat.html", **context)


@campaign_scope_access_required("combat")
def campaign_combat_live_state(campaign_slug: str):
    dependencies = _dependencies()
    state_check_started_at = time.perf_counter()
    live_metadata = dependencies.build_combat_live_metadata(campaign_slug, "combat")
    snapshot_sync_metrics = live_metadata.get("snapshot_sync_metrics")
    state_check_ms = (time.perf_counter() - state_check_started_at) * 1000
    if should_short_circuit_live_response(
        request.headers,
        live_revision=int(live_metadata["live_revision"] or 0),
        live_view_token=str(live_metadata["live_view_token"] or ""),
    ):
        return dependencies.build_live_json_response(
            build_unchanged_live_payload(
                live_revision=int(live_metadata["live_revision"] or 0),
                live_view_token=str(live_metadata["live_view_token"] or ""),
            ),
            view_name="combat",
            changed=False,
            live_revision=int(live_metadata["live_revision"] or 0),
            snapshot_sync_metrics=snapshot_sync_metrics,
            state_check_ms=state_check_ms,
            render_ms=0.0,
        )

    render_started_at = time.perf_counter()
    payload = dependencies.build_campaign_combat_live_state(
        campaign_slug,
        requested_detail_state_token=dependencies.parse_live_detail_state_token_header(),
        live_revision=int(live_metadata["live_revision"] or 0),
        live_view_token=str(live_metadata["live_view_token"] or ""),
        selected_combatant_id=dependencies.parse_requested_combatant_id(),
        sync_player_character_snapshots=False,
        owned_character_slugs=live_metadata.get("owned_character_slugs"),
    )
    render_ms = (time.perf_counter() - render_started_at) * 1000
    return dependencies.build_live_json_response(
        payload,
        view_name="combat",
        changed=True,
        live_revision=int(live_metadata["live_revision"] or 0),
        snapshot_sync_metrics=snapshot_sync_metrics,
        state_check_ms=state_check_ms,
        render_ms=render_ms,
    )


@campaign_scope_access_required("combat")
def campaign_combat_dm_view(campaign_slug: str):
    if not can_manage_campaign_combat(campaign_slug):
        abort(403)
    dependencies = _dependencies()
    combat_dm_view = dependencies.normalize_combat_dm_view(request.values.get("view", ""))
    if combat_dm_view == "controls":
        if dependencies.require_supported_combat_system(campaign_slug) is None:
            context = dependencies.build_campaign_combat_page_context(
                campaign_slug,
                include_control_choices=True,
                combat_subpage="dm",
                combat_dm_view=combat_dm_view,
                sync_player_character_snapshots=False,
            )
            return render_template("combat_dm.html", **context)
        try:
            _preset_service().list_presets(campaign_slug, limit=1, offset=0)
        except CampaignCombatPresetAuthorizationError:
            abort(403)
        context = dependencies.build_campaign_combat_page_context(
            campaign_slug,
            include_control_choices=True,
            combat_subpage="dm",
            combat_dm_view=combat_dm_view,
            sync_player_character_snapshots=False,
        )
        page_text = request.args.get("preset_page", "1")
        try:
            page = _bounded_integer(
                page_text,
                "saved encounter page",
                minimum=1,
                maximum=_MAX_PRESET_PAGE,
            )
        except ValueError as exc:
            context["combat_preset_browser"] = _build_preset_browser(
                campaign_slug,
                context,
                errors=[str(exc)],
            )
            return render_template("combat_dm.html", **context), 400
        assert page is not None

        selector = request.args.get("preset")
        selector_mode = request.args.get("preset_mode", "")
        if selector is None:
            if selector_mode:
                abort(404)
            context["combat_preset_browser"] = _build_preset_browser(
                campaign_slug,
                context,
                page=page,
            )
        elif selector == "new" and not selector_mode:
            context["combat_preset_browser"] = _build_preset_browser(
                campaign_slug,
                context,
                page=page,
                mode="edit",
                draft={"name": "", "expected_revision": "", "rows": [_empty_preset_row()]},
            )
        else:
            if not selector.isdecimal() or selector.startswith("0"):
                abort(404)
            preset_id = int(selector)
            if preset_id < 1 or preset_id > _SQLITE_MAX_INTEGER:
                abort(404)
            selected = _load_selected_preset(campaign_slug, preset_id)
            if selector_mode not in {"", "edit"}:
                abort(404)
            context["combat_preset_browser"] = _build_preset_browser(
                campaign_slug,
                context,
                page=page,
                mode="edit" if selector_mode == "edit" else "detail",
                selected=selected,
                draft=_draft_from_preset(selected) if selector_mode == "edit" else None,
            )
    else:
        context = dependencies.build_campaign_combat_dm_status_context(
            campaign_slug,
        )
    return render_template("combat_dm.html", **context)


def _preset_draft_response(campaign_slug: str, preset_id: int | None):
    _require_preset_route_access(campaign_slug)
    loaded = _load_selected_preset(campaign_slug, preset_id) if preset_id is not None else None
    try:
        draft = _parse_raw_preset_draft()
    except ValueError as exc:
        fallback = {
            "name": request.form.get("name", ""),
            "expected_revision": request.form.get("expected_revision", ""),
            "rows": [],
        }
        return _render_preset_controls_document(
            campaign_slug,
            status=400,
            mode="edit",
            selected=loaded,
            draft=fallback,
            errors=[str(exc)],
        )

    intent = request.form.get("intent", "").strip()
    if intent not in {
        "add_entry",
        "remove_entry",
        "move_up",
        "move_down",
        "search_source",
        "review",
        "save",
    }:
        return _render_preset_controls_document(
            campaign_slug,
            status=400,
            mode="edit",
            selected=loaded,
            draft=draft,
            errors=["Choose a valid saved encounter action."],
        )

    if loaded is not None:
        try:
            expected = _bounded_integer(
                draft.get("expected_revision"), "expected revision", minimum=1
            )
        except ValueError as exc:
            return _render_preset_controls_document(
                campaign_slug,
                status=400,
                mode="edit",
                selected=loaded,
                draft=draft,
                errors=[str(exc)],
            )
        if expected != loaded.revision:
            return _render_preset_controls_document(
                campaign_slug,
                status=409,
                mode="edit",
                selected=loaded,
                draft=draft,
                errors=["This saved encounter changed elsewhere. Refresh it, then review again."],
                conflict=True,
            )

    row_text = request.args.get("row", "")
    if intent in {"remove_entry", "move_up", "move_down"}:
        try:
            row_index = _bounded_integer(
                row_text,
                "row position",
                minimum=0,
                maximum=max(0, len(draft["rows"]) - 1),
            )
        except ValueError as exc:
            return _render_preset_controls_document(
                campaign_slug,
                status=400,
                mode="edit",
                selected=loaded,
                draft=draft,
                errors=[str(exc)],
            )
        assert row_index is not None
        if intent == "remove_entry":
            draft["rows"].pop(row_index)
        elif intent == "move_up" and row_index > 0:
            draft["rows"][row_index - 1], draft["rows"][row_index] = (
                draft["rows"][row_index],
                draft["rows"][row_index - 1],
            )
        elif intent == "move_down" and row_index + 1 < len(draft["rows"]):
            draft["rows"][row_index + 1], draft["rows"][row_index] = (
                draft["rows"][row_index],
                draft["rows"][row_index + 1],
            )
        return _render_preset_controls_document(
            campaign_slug,
            mode="edit",
            selected=loaded,
            draft=draft,
        )

    if intent == "add_entry":
        if len(draft["rows"]) >= _MAX_PRESET_ROWS:
            return _render_preset_controls_document(
                campaign_slug,
                status=400,
                mode="edit",
                selected=loaded,
                draft=draft,
                errors=["A saved encounter may contain at most 50 rows."],
            )
        draft["rows"].append(_empty_preset_row())
        return _render_preset_controls_document(
            campaign_slug,
            mode="edit",
            selected=loaded,
            draft=draft,
        )

    if intent == "search_source":
        try:
            search_row = _bounded_integer(
                draft.get("search_row"),
                "search row",
                minimum=0,
                maximum=max(0, len(draft["rows"]) - 1),
            )
            assert search_row is not None
            query = unicodedata.normalize("NFKC", str(draft.get("search_query") or "")).strip()
            if not 2 <= len(query) <= 100 or len(query.encode("utf-8")) > 320:
                raise ValueError("Enter 2 to 100 characters (at most 320 UTF-8 bytes) to search.")
            if draft["rows"][search_row].get("source_kind") != COMBAT_SOURCE_KIND_SYSTEMS_MONSTER:
                raise ValueError("Choose a Systems monster row to search.")
            systems_service = current_app.extensions["systems_service"]
            search_results = [
                {
                    "source_ref": entry.entry_key,
                    "label": entry.title,
                    "source_id": entry.source_id,
                }
                for entry in systems_service.search_monster_entries_for_campaign(
                    campaign_slug,
                    query=query,
                    limit=30,
                )[:30]
            ]
        except ValueError as exc:
            return _render_preset_controls_document(
                campaign_slug,
                status=400,
                mode="edit",
                selected=loaded,
                draft=draft,
                errors=[str(exc)],
            )
        draft["search_row"] = str(search_row)
        draft["search_query"] = query
        return _render_preset_controls_document(
            campaign_slug,
            mode="edit",
            selected=loaded,
            draft=draft,
            search_results=search_results,
        )

    try:
        name, prepared, statuses, digest = _review_preset_entries(
            campaign_slug,
            draft,
            loaded_preset=loaded,
        )
    except CampaignCombatPresetAuthorizationError:
        abort(403)
    except _PresetReviewError as exc:
        return _render_preset_controls_document(
            campaign_slug,
            status=400,
            mode="edit",
            selected=loaded,
            draft=draft,
            draft_statuses=exc.statuses,
            errors=[str(exc)],
        )
    except (ValueError, CampaignCombatPresetValidationError, CampaignCombatPresetSourceValidationError):
        return _render_preset_controls_document(
            campaign_slug,
            status=400,
            mode="edit",
            selected=loaded,
            draft=draft,
            errors=["Review the highlighted saved encounter fields and unavailable sources."],
        )

    draft["name"] = name
    if intent == "review":
        return _render_preset_controls_document(
            campaign_slug,
            mode="review",
            selected=loaded,
            draft=draft,
            review_entries=prepared,
            review_statuses=statuses,
            review_digest=digest,
        )

    submitted_digest = str(draft.get("review_digest") or "")
    if submitted_digest != digest:
        return _render_preset_controls_document(
            campaign_slug,
            status=409,
            mode="edit",
            selected=loaded,
            draft=draft,
            errors=["Review this draft again before saving; its reviewed values or sources changed."],
            conflict=True,
        )
    service = _preset_service()
    try:
        if loaded is None:
            saved = service.create_preset(campaign_slug, name=name, entries=prepared)
        else:
            saved = service.update_preset(
                campaign_slug,
                loaded.id,
                expected_revision=loaded.revision,
                name=name,
                entries=prepared,
            )
    except CampaignCombatPresetAuthorizationError:
        abort(403)
    except CampaignCombatPresetConflictError:
        return _render_preset_controls_document(
            campaign_slug,
            status=409,
            mode="edit",
            selected=loaded,
            draft=draft,
            errors=["This saved encounter conflicts with a current name or revision. Refresh and review again."],
            conflict=True,
        )
    except CampaignCombatPresetValidationError:
        return _render_preset_controls_document(
            campaign_slug,
            status=400,
            mode="edit",
            selected=loaded,
            draft=draft,
            errors=["Review the saved encounter fields and sources before saving."],
        )
    combatant_id = _dependencies().get_requested_combatant_id_from_values()
    return redirect(
        _preset_url(campaign_slug, combatant_id=combatant_id, preset=saved.id),
        code=303,
    )


@campaign_scope_access_required("combat")
def campaign_combat_preset_collection(campaign_slug: str):
    return _preset_draft_response(campaign_slug, None)


@campaign_scope_access_required("combat")
def campaign_combat_preset_item(campaign_slug: str, preset_id: int):
    return _preset_draft_response(campaign_slug, preset_id)


@campaign_scope_access_required("combat")
def campaign_combat_preset_delete(campaign_slug: str, preset_id: int):
    _require_preset_route_access(campaign_slug)
    if request.content_length is not None and request.content_length > _MAX_PRESET_BODY_BYTES:
        abort(413)
    if any(len(request.form.getlist(key)) != 1 for key in request.form) or set(
        request.form
    ) - {"_csrf_token", "expected_revision"}:
        return _render_preset_controls_document(
            campaign_slug,
            status=400,
            errors=["The delete form contains an unknown field."],
        )
    try:
        expected_revision = _bounded_integer(
            request.form.get("expected_revision"), "expected revision", minimum=1
        )
        assert expected_revision is not None
        _preset_service().delete_preset(
            campaign_slug,
            preset_id,
            expected_revision=expected_revision,
        )
    except CampaignCombatPresetAuthorizationError:
        abort(403)
    except (ValueError, CampaignCombatPresetValidationError):
        return _render_preset_controls_document(
            campaign_slug,
            status=400,
            errors=["Enter a valid saved encounter revision."],
        )
    except CampaignCombatPresetConflictError:
        return _render_preset_controls_document(
            campaign_slug,
            status=409,
            errors=["This saved encounter changed or was removed. Refresh before trying again."],
            conflict=True,
        )
    combatant_id = _dependencies().get_requested_combatant_id_from_values()
    return redirect(_preset_url(campaign_slug, combatant_id=combatant_id), code=303)


@campaign_scope_access_required("combat")
def campaign_combat_dm_live_state(campaign_slug: str):
    if not can_manage_campaign_combat(campaign_slug):
        abort(403)
    dependencies = _dependencies()
    selected_combatant_id = dependencies.parse_requested_combatant_id()
    combat_dm_view = dependencies.normalize_combat_dm_view(request.values.get("view", ""))
    requested_detail_state_token = dependencies.parse_live_detail_state_token_header()
    state_check_started_at = time.perf_counter()
    live_metadata = dependencies.build_combat_live_metadata(
        campaign_slug,
        "dm",
        selected_combatant_id=selected_combatant_id,
        combat_dm_view=combat_dm_view,
    )
    snapshot_sync_metrics = live_metadata.get("snapshot_sync_metrics")
    state_check_ms = (time.perf_counter() - state_check_started_at) * 1000
    if should_short_circuit_live_response(
        request.headers,
        live_revision=int(live_metadata["live_revision"] or 0),
        live_view_token=str(live_metadata["live_view_token"] or ""),
    ):
        return dependencies.build_live_json_response(
            build_unchanged_live_payload(
                live_revision=int(live_metadata["live_revision"] or 0),
                live_view_token=str(live_metadata["live_view_token"] or ""),
            ),
            view_name="combat-dm",
            changed=False,
            live_revision=int(live_metadata["live_revision"] or 0),
            snapshot_sync_metrics=snapshot_sync_metrics,
            state_check_ms=state_check_ms,
            render_ms=0.0,
        )

    render_started_at = time.perf_counter()
    include_selected_detail = True
    dm_status_context = None
    if combat_dm_view == "status":
        dm_status_context = dependencies.build_campaign_combat_dm_status_context(
            campaign_slug,
            selected_combatant_id=selected_combatant_id,
            sync_player_character_snapshots=False,
        )
        include_selected_detail = not should_skip_selected_combatant_detail_render(
            requested_detail_state_token=requested_detail_state_token,
            selected_detail_state_token=str(dm_status_context["combat_status_state_token"] or ""),
        )
    payload = dependencies.build_campaign_combat_dm_live_state(
        campaign_slug,
        selected_combatant_id=selected_combatant_id,
        combat_dm_view=combat_dm_view,
        live_revision=int(live_metadata["live_revision"] or 0),
        live_view_token=str(live_metadata["live_view_token"] or ""),
        sync_player_character_snapshots=False,
        include_selected_detail=include_selected_detail,
        context=dm_status_context,
    )
    render_ms = (time.perf_counter() - render_started_at) * 1000
    return dependencies.build_live_json_response(
        payload,
        view_name="combat-dm",
        changed=True,
        live_revision=int(live_metadata["live_revision"] or 0),
        snapshot_sync_metrics=snapshot_sync_metrics,
        state_check_ms=state_check_ms,
        render_ms=render_ms,
    )


@campaign_scope_access_required("combat")
def campaign_combat_status_view(campaign_slug: str):
    if not can_manage_campaign_combat(campaign_slug):
        abort(403)
    dependencies = _dependencies()
    selected_combatant_id = dependencies.parse_requested_combatant_id(strict=True)
    if selected_combatant_id is not None:
        combatant = dependencies.get_campaign_combat_service().get_combatant(
            campaign_slug,
            selected_combatant_id,
        )
        if combatant is None:
            abort(404)
    return dependencies.redirect_to_campaign_combat_dm(
        campaign_slug,
        combatant_id=selected_combatant_id,
    )


@campaign_scope_access_required("combat")
def campaign_combat_status_live_state(campaign_slug: str):
    if not can_manage_campaign_combat(campaign_slug):
        abort(403)
    dependencies = _dependencies()
    selected_combatant_id = dependencies.parse_requested_combatant_id()
    requested_detail_state_token = dependencies.parse_live_detail_state_token_header()
    state_check_started_at = time.perf_counter()
    live_metadata = dependencies.build_combat_live_metadata(
        campaign_slug,
        "status",
        selected_combatant_id=selected_combatant_id,
    )
    snapshot_sync_metrics = live_metadata.get("snapshot_sync_metrics")
    state_check_ms = (time.perf_counter() - state_check_started_at) * 1000
    if should_short_circuit_live_response(
        request.headers,
        live_revision=int(live_metadata["live_revision"] or 0),
        live_view_token=str(live_metadata["live_view_token"] or ""),
    ):
        return dependencies.build_live_json_response(
            build_unchanged_live_payload(
                live_revision=int(live_metadata["live_revision"] or 0),
                live_view_token=str(live_metadata["live_view_token"] or ""),
            ),
            view_name="combat-status",
            changed=False,
            live_revision=int(live_metadata["live_revision"] or 0),
            snapshot_sync_metrics=snapshot_sync_metrics,
            state_check_ms=state_check_ms,
            render_ms=0.0,
        )

    render_started_at = time.perf_counter()
    status_context = dependencies.build_campaign_combat_status_context(
        campaign_slug,
        selected_combatant_id=selected_combatant_id,
        sync_player_character_snapshots=False,
        strict_selected_combatant=False,
    )
    include_selected_detail = not should_skip_selected_combatant_detail_render(
        requested_detail_state_token=requested_detail_state_token,
        selected_detail_state_token=str(status_context["combat_status_state_token"] or ""),
    )
    payload = dependencies.build_campaign_combat_status_live_state(
        campaign_slug,
        selected_combatant_id=selected_combatant_id,
        live_revision=int(live_metadata["live_revision"] or 0),
        live_view_token=str(live_metadata["live_view_token"] or ""),
        sync_player_character_snapshots=False,
        include_selected_detail=include_selected_detail,
        context=status_context,
    )
    render_ms = (time.perf_counter() - render_started_at) * 1000
    return dependencies.build_live_json_response(
        payload,
        view_name="combat-status",
        changed=True,
        live_revision=int(live_metadata["live_revision"] or 0),
        snapshot_sync_metrics=snapshot_sync_metrics,
        state_check_ms=state_check_ms,
        render_ms=render_ms,
    )


@campaign_scope_access_required("combat")
def campaign_combat_add_player(campaign_slug: str):
    if not can_manage_campaign_combat(campaign_slug):
        abort(403)
    dependencies = _dependencies()
    if dependencies.require_supported_combat_system(campaign_slug) is None:
        return dependencies.respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=False,
            anchor="combat-tracker",
        )

    user = get_current_user()
    if user is None:
        abort(403)

    mutation_succeeded = False
    try:
        dependencies.get_campaign_combat_service().add_player_character(
            campaign_slug,
            character_slug=request.form.get("character_slug", ""),
            turn_value=request.form.get("turn_value"),
            initiative_priority=request.form.get("initiative_priority"),
            created_by_user_id=user.id,
        )
    except CampaignCombatValidationError as exc:
        flash(str(exc), "error")
    else:
        flash("Player character added to the combat tracker.", "success")
        mutation_succeeded = True

    return dependencies.respond_to_campaign_combat_mutation(
        campaign_slug,
        mutation_succeeded=mutation_succeeded,
        anchor="combat-tracker",
    )


@campaign_scope_access_required("combat")
def campaign_combat_add_npc(campaign_slug: str):
    if not can_manage_campaign_combat(campaign_slug):
        abort(403)
    dependencies = _dependencies()
    if dependencies.require_supported_combat_system(campaign_slug) is None:
        return dependencies.respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=False,
            anchor="combat-tracker",
        )

    user = get_current_user()
    if user is None:
        abort(403)

    mutation_succeeded = False
    try:
        dependencies.get_campaign_combat_service().add_npc_combatant(
            campaign_slug,
            display_name=request.form.get("display_name", ""),
            turn_value=request.form.get("turn_value"),
            dexterity_modifier=request.form.get("dexterity_modifier"),
            initiative_priority=request.form.get("initiative_priority"),
            current_hp=request.form.get("current_hp"),
            max_hp=request.form.get("max_hp"),
            temp_hp=request.form.get("temp_hp"),
            movement_total=request.form.get("movement_total"),
            created_by_user_id=user.id,
        )
    except CampaignCombatValidationError as exc:
        flash(str(exc), "error")
    else:
        flash("NPC combatant added to the combat tracker.", "success")
        mutation_succeeded = True

    return dependencies.respond_to_campaign_combat_mutation(
        campaign_slug,
        mutation_succeeded=mutation_succeeded,
        anchor="combat-tracker",
    )


@campaign_scope_access_required("combat")
def campaign_combat_advance_turn(campaign_slug: str):
    if not can_manage_campaign_combat(campaign_slug):
        abort(403)
    dependencies = _dependencies()
    if dependencies.require_supported_combat_system(campaign_slug) is None:
        return dependencies.respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=False,
            anchor="combat-summary",
        )

    user = get_current_user()
    if user is None:
        abort(403)

    mutation_succeeded = False
    try:
        dependencies.get_campaign_combat_service().advance_turn(
            campaign_slug,
            updated_by_user_id=user.id,
        )
    except CampaignCombatValidationError as exc:
        flash(str(exc), "error")
    else:
        flash("Advanced turn order.", "success")
        mutation_succeeded = True

    return dependencies.respond_to_campaign_combat_mutation(
        campaign_slug,
        mutation_succeeded=mutation_succeeded,
        anchor="combat-summary",
        ignore_requested_combatant_for_dm=(
            dependencies.normalize_combat_return_view(request.values.get("combat_view", "")) == "dm"
            and request.values.get("view", "").strip().lower() != "status"
        ),
    )


@campaign_scope_access_required("combat")
def campaign_combat_clear(campaign_slug: str):
    if not can_manage_campaign_combat(campaign_slug):
        abort(403)
    dependencies = _dependencies()
    if dependencies.require_supported_combat_system(campaign_slug) is None:
        return dependencies.respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=False,
            anchor="combat-summary",
        )

    user = get_current_user()
    if user is None:
        abort(403)

    mutation_succeeded = False
    try:
        dependencies.get_campaign_combat_service().clear_tracker(
            campaign_slug,
            updated_by_user_id=user.id,
        )
    except CampaignCombatValidationError as exc:
        flash(str(exc), "error")
    else:
        flash("Combat tracker cleared.", "success")
        mutation_succeeded = True

    return dependencies.respond_to_campaign_combat_mutation(
        campaign_slug,
        mutation_succeeded=mutation_succeeded,
        anchor="combat-summary",
    )


@campaign_scope_access_required("combat")
def campaign_combat_set_current_turn(campaign_slug: str, combatant_id: int):
    if not can_manage_campaign_combat(campaign_slug):
        abort(403)
    dependencies = _dependencies()
    if dependencies.require_supported_combat_system(campaign_slug) is None:
        return dependencies.respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=False,
            anchor="combat-tracker",
        )

    user = get_current_user()
    if user is None:
        abort(403)

    mutation_succeeded = False
    try:
        dependencies.get_campaign_combat_service().set_current_turn(
            campaign_slug,
            combatant_id,
            updated_by_user_id=user.id,
        )
    except CampaignCombatValidationError as exc:
        flash(str(exc), "error")
    else:
        flash("Current turn updated.", "success")
        mutation_succeeded = True

    return dependencies.respond_to_campaign_combat_mutation(
        campaign_slug,
        mutation_succeeded=mutation_succeeded,
        anchor=f"combatant-{combatant_id}",
    )


@campaign_scope_access_required("combat")
def campaign_combat_update_turn_value(campaign_slug: str, combatant_id: int):
    if not can_manage_campaign_combat(campaign_slug):
        abort(403)
    dependencies = _dependencies()
    if dependencies.require_supported_combat_system(campaign_slug) is None:
        return dependencies.respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=False,
            anchor=f"combatant-{combatant_id}",
        )

    user = get_current_user()
    if user is None:
        abort(403)

    mutation_succeeded = False
    mutation_outcome = None
    try:
        expected_combatant_revision = dependencies.parse_expected_combatant_revision()
        dependencies.get_campaign_combat_service().update_turn_value(
            campaign_slug,
            combatant_id,
            expected_revision=expected_combatant_revision,
            turn_value=request.form.get("turn_value"),
            initiative_priority=request.form.get("initiative_priority"),
            updated_by_user_id=user.id,
        )
    except CampaignCombatRevisionConflictError:
        mutation_outcome = "combatant-revision-conflict"
        flash("This combatant changed in another combat view. Refresh and try again.", "error")
    except CampaignCombatValidationError as exc:
        flash(str(exc), "error")
    else:
        flash("Turn value saved.", "success")
        mutation_succeeded = True

    return dependencies.respond_to_campaign_combat_mutation(
        campaign_slug,
        mutation_succeeded=mutation_succeeded,
        mutation_outcome=mutation_outcome,
        anchor=f"combatant-{combatant_id}",
    )


@campaign_scope_access_required("combat")
def campaign_combat_update_player_detail_visibility(campaign_slug: str, combatant_id: int):
    if not can_manage_campaign_combat(campaign_slug):
        abort(403)
    dependencies = _dependencies()
    if dependencies.require_supported_combat_system(campaign_slug) is None:
        return dependencies.respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=False,
            anchor=f"combatant-{combatant_id}",
        )

    user = get_current_user()
    if user is None:
        abort(403)

    mutation_succeeded = False
    mutation_outcome = None
    try:
        expected_combatant_revision = dependencies.parse_expected_combatant_revision()
        dependencies.get_campaign_combat_service().update_player_detail_visibility(
            campaign_slug,
            combatant_id,
            expected_revision=expected_combatant_revision,
            player_detail_visible=request.form.get("player_detail_visible") == "1",
            updated_by_user_id=user.id,
        )
    except CampaignCombatRevisionConflictError:
        mutation_outcome = "combatant-revision-conflict"
        flash("This combatant changed in another combat view. Refresh and try again.", "error")
    except CampaignCombatValidationError as exc:
        flash(str(exc), "error")
    else:
        flash("Player-facing NPC detail updated.", "success")
        mutation_succeeded = True

    return dependencies.respond_to_campaign_combat_mutation(
        campaign_slug,
        mutation_succeeded=mutation_succeeded,
        mutation_outcome=mutation_outcome,
        anchor=f"combatant-{combatant_id}",
    )


@campaign_scope_access_required("combat")
def campaign_combat_add_condition(campaign_slug: str, combatant_id: int):
    if not can_manage_campaign_combat(campaign_slug):
        abort(403)
    dependencies = _dependencies()
    if dependencies.require_supported_combat_system(campaign_slug) is None:
        return dependencies.respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=False,
            anchor=f"combatant-{combatant_id}",
        )

    user = get_current_user()
    if user is None:
        abort(403)

    mutation_succeeded = False
    try:
        dependencies.get_campaign_combat_service().add_condition(
            campaign_slug,
            combatant_id,
            name=request.form.get("condition_name", ""),
            duration_text=request.form.get("duration_text", ""),
            created_by_user_id=user.id,
        )
    except CampaignCombatValidationError as exc:
        flash(str(exc), "error")
    else:
        flash("Condition added.", "success")
        mutation_succeeded = True

    return dependencies.respond_to_campaign_combat_mutation(
        campaign_slug,
        mutation_succeeded=mutation_succeeded,
        anchor=f"combatant-{combatant_id}",
    )


@campaign_scope_access_required("combat")
def campaign_combat_delete_condition(campaign_slug: str, condition_id: int):
    if not can_manage_campaign_combat(campaign_slug):
        abort(403)
    dependencies = _dependencies()
    if dependencies.require_supported_combat_system(campaign_slug) is None:
        return dependencies.respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=False,
            anchor="combat-tracker",
        )

    try:
        deleted_condition = dependencies.get_campaign_combat_service().delete_condition(
            campaign_slug,
            condition_id,
        )
    except CampaignCombatValidationError as exc:
        flash(str(exc), "error")
        return dependencies.respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=False,
            anchor="combat-tracker",
        )

    flash("Condition removed.", "success")
    return dependencies.respond_to_campaign_combat_mutation(
        campaign_slug,
        mutation_succeeded=True,
        anchor=f"combatant-{deleted_condition.combatant_id}",
    )


@campaign_scope_access_required("combat")
def campaign_combat_update_condition(campaign_slug: str, condition_id: int):
    if not can_manage_campaign_combat(campaign_slug):
        abort(403)
    dependencies = _dependencies()
    if dependencies.require_supported_combat_system(campaign_slug) is None:
        return dependencies.respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=False,
            anchor="combat-tracker",
        )

    user = get_current_user()
    if user is None:
        abort(403)

    mutation_succeeded = False
    combatant_id = dependencies.get_requested_combatant_id_from_values()
    try:
        updated_condition = dependencies.get_campaign_combat_service().update_condition(
            campaign_slug,
            condition_id,
            name=request.form.get("condition_name", ""),
            duration_text=request.form.get("duration_text", ""),
            updated_by_user_id=user.id,
        )
        combatant_id = updated_condition.combatant_id
    except CampaignCombatValidationError as exc:
        flash(str(exc), "error")
    else:
        flash("Condition updated.", "success")
        mutation_succeeded = True

    return dependencies.respond_to_campaign_combat_mutation(
        campaign_slug,
        mutation_succeeded=mutation_succeeded,
        anchor=f"combatant-{combatant_id}" if combatant_id is not None else "combat-tracker",
    )


@campaign_scope_access_required("combat")
def campaign_combat_delete_combatant(campaign_slug: str, combatant_id: int):
    if not can_manage_campaign_combat(campaign_slug):
        abort(403)
    dependencies = _dependencies()
    if dependencies.require_supported_combat_system(campaign_slug) is None:
        return dependencies.respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=False,
            anchor="combat-tracker",
        )

    mutation_succeeded = False
    try:
        deleted_combatant = dependencies.get_campaign_combat_service().delete_combatant(
            campaign_slug,
            combatant_id,
        )
    except CampaignCombatValidationError as exc:
        flash(str(exc), "error")
    else:
        flash(f"Removed {deleted_combatant.display_name} from the combat tracker.", "success")
        mutation_succeeded = True

    return dependencies.respond_to_campaign_combat_mutation(
        campaign_slug,
        mutation_succeeded=mutation_succeeded,
        anchor="combat-tracker",
    )


@combat.record_once
def _register_legacy_endpoints(state: Any) -> None:
    registrations = (
        (
            "/campaigns/<campaign_slug>/combat",
            "campaign_combat_view",
            campaign_combat_view,
        ),
        (
            "/campaigns/<campaign_slug>/combat/live-state",
            "campaign_combat_live_state",
            campaign_combat_live_state,
        ),
        (
            "/campaigns/<campaign_slug>/combat/dm",
            "campaign_combat_dm_view",
            campaign_combat_dm_view,
        ),
        (
            "/campaigns/<campaign_slug>/combat/dm/live-state",
            "campaign_combat_dm_live_state",
            campaign_combat_dm_live_state,
        ),
        (
            "/campaigns/<campaign_slug>/combat/status",
            "campaign_combat_status_view",
            campaign_combat_status_view,
        ),
        (
            "/campaigns/<campaign_slug>/combat/status/live-state",
            "campaign_combat_status_live_state",
            campaign_combat_status_live_state,
        ),
    )
    for rule, endpoint, view_func in registrations:
        state.app.add_url_rule(
            rule,
            endpoint=endpoint,
            view_func=view_func,
            methods=("GET",),
        )


@combat.record_once
def _register_preset_endpoints(state: Any) -> None:
    preset_registrations = (
        (
            "/campaigns/<campaign_slug>/combat/presets",
            "campaign_combat_preset_collection",
            campaign_combat_preset_collection,
        ),
        (
            "/campaigns/<campaign_slug>/combat/presets/<int:preset_id>",
            "campaign_combat_preset_item",
            campaign_combat_preset_item,
        ),
        (
            "/campaigns/<campaign_slug>/combat/presets/<int:preset_id>/delete",
            "campaign_combat_preset_delete",
            campaign_combat_preset_delete,
        ),
    )
    for rule, endpoint, view_func in preset_registrations:
        state.app.add_url_rule(
            rule,
            endpoint=endpoint,
            view_func=view_func,
            methods=("POST",),
        )


def register_combat_basic_seeding_routes(app: Any) -> None:
    registrations = (
        (
            "/campaigns/<campaign_slug>/combat/player-combatants",
            "campaign_combat_add_player",
            campaign_combat_add_player,
        ),
        (
            "/campaigns/<campaign_slug>/combat/npc-combatants",
            "campaign_combat_add_npc",
            campaign_combat_add_npc,
        ),
    )
    for rule, endpoint, view_func in registrations:
        app.add_url_rule(
            rule,
            endpoint=endpoint,
            view_func=view_func,
            methods=("POST",),
        )


def register_combat_advance_turn_route(app: Any) -> None:
    app.add_url_rule(
        "/campaigns/<campaign_slug>/combat/advance-turn",
        endpoint="campaign_combat_advance_turn",
        view_func=campaign_combat_advance_turn,
        methods=("POST",),
    )


def register_combat_clear_route(app: Any) -> None:
    app.add_url_rule(
        "/campaigns/<campaign_slug>/combat/clear",
        endpoint="campaign_combat_clear",
        view_func=campaign_combat_clear,
        methods=("POST",),
    )


def register_combat_set_current_turn_route(app: Any) -> None:
    app.add_url_rule(
        "/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/set-current",
        endpoint="campaign_combat_set_current_turn",
        view_func=campaign_combat_set_current_turn,
        methods=("POST",),
    )


def register_combat_update_turn_value_route(app: Any) -> None:
    app.add_url_rule(
        "/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/turn",
        endpoint="campaign_combat_update_turn_value",
        view_func=campaign_combat_update_turn_value,
        methods=("POST",),
    )


def register_combat_update_player_detail_visibility_route(app: Any) -> None:
    app.add_url_rule(
        "/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/player-detail-visibility",
        endpoint="campaign_combat_update_player_detail_visibility",
        view_func=campaign_combat_update_player_detail_visibility,
        methods=("POST",),
    )


def register_combat_condition_routes(app: Any) -> None:
    registrations = (
        (
            "/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/conditions",
            "campaign_combat_add_condition",
            campaign_combat_add_condition,
        ),
        (
            "/campaigns/<campaign_slug>/combat/conditions/<int:condition_id>/delete",
            "campaign_combat_delete_condition",
            campaign_combat_delete_condition,
        ),
        (
            "/campaigns/<campaign_slug>/combat/conditions/<int:condition_id>",
            "campaign_combat_update_condition",
            campaign_combat_update_condition,
        ),
    )
    for rule, endpoint, view_func in registrations:
        app.add_url_rule(
            rule,
            endpoint=endpoint,
            view_func=view_func,
            methods=("POST",),
        )


def register_combat_delete_combatant_route(app: Any) -> None:
    app.add_url_rule(
        "/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/delete",
        endpoint="campaign_combat_delete_combatant",
        view_func=campaign_combat_delete_combatant,
        methods=("POST",),
    )


def register_combat_routes(
    app: Any,
    *,
    build_campaign_combat_page_context: Callable[..., dict[str, object]],
    redirect_to_campaign_combat_dm: Callable[..., Any],
    parse_requested_combatant_id: Callable[..., int | None],
    build_combat_live_metadata: Callable[..., dict[str, object]],
    build_campaign_combat_live_state: Callable[..., dict[str, object]],
    build_live_json_response: Callable[..., Any],
    normalize_combat_dm_view: Callable[[str], str],
    build_campaign_combat_dm_status_context: Callable[..., dict[str, object]],
    build_campaign_combat_dm_live_state: Callable[..., dict[str, object]],
    build_campaign_combat_status_context: Callable[..., dict[str, object]],
    build_campaign_combat_status_live_state: Callable[..., dict[str, object]],
    parse_live_detail_state_token_header: Callable[[], str],
    require_supported_combat_system: Callable[[str], Any],
    get_campaign_combat_service: Callable[[], Any],
    respond_to_campaign_combat_mutation: Callable[..., Any],
    parse_expected_combatant_revision: Callable[[], int | None],
    normalize_combat_return_view: Callable[[str], str],
    get_requested_combatant_id_from_values: Callable[[], int | None],
) -> None:
    app.extensions["combat_route_dependencies"] = CombatRouteDependencies(
        build_campaign_combat_page_context=build_campaign_combat_page_context,
        redirect_to_campaign_combat_dm=redirect_to_campaign_combat_dm,
        parse_requested_combatant_id=parse_requested_combatant_id,
        build_combat_live_metadata=build_combat_live_metadata,
        build_campaign_combat_live_state=build_campaign_combat_live_state,
        build_live_json_response=build_live_json_response,
        normalize_combat_dm_view=normalize_combat_dm_view,
        build_campaign_combat_dm_status_context=build_campaign_combat_dm_status_context,
        build_campaign_combat_dm_live_state=build_campaign_combat_dm_live_state,
        build_campaign_combat_status_context=build_campaign_combat_status_context,
        build_campaign_combat_status_live_state=build_campaign_combat_status_live_state,
        parse_live_detail_state_token_header=parse_live_detail_state_token_header,
        require_supported_combat_system=require_supported_combat_system,
        get_campaign_combat_service=get_campaign_combat_service,
        respond_to_campaign_combat_mutation=respond_to_campaign_combat_mutation,
        parse_expected_combatant_revision=parse_expected_combatant_revision,
        normalize_combat_return_view=normalize_combat_return_view,
        get_requested_combatant_id_from_values=get_requested_combatant_id_from_values,
    )
    app.register_blueprint(combat)
