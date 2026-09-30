"""Manager-only explicit repair of ambiguous DND equipment activation."""

from __future__ import annotations

from typing import Any, Callable

from flask import abort, render_template, request

from .auth import campaign_scope_access_required
from .csrf import CSRF_FIELD_NAME
from .character_equipment_activation import (
    analyze_activation, definition_digest, repair_activation_state,
    repair_definition_identity,
)
from .character_reconciliation import CharacterPublicationConflict
from .character_store import CharacterStateConflictError
from .character_service import CharacterStateValidationError
from .runtime_lease import RuntimeStateLeaseError
from .system_policy import is_dnd_5e_system


def register_character_equipment_activation_repair_route(
    app: Any, *, load_character_context: Callable[..., Any],
    can_manage_campaign_content: Callable[[str], bool],
    get_current_auth_source: Callable[[], str],
    get_current_user: Callable[[], Any],
    coordinator: Any,
) -> None:
    def view(campaign_slug: str, character_slug: str):
        if not can_manage_campaign_content(campaign_slug):
            abort(403)
        context = load_character_context(campaign_slug, character_slug)
        if context is None:
            abort(404)
        campaign, record = context
        if not is_dnd_5e_system(record.definition.system):
            abort(404)
        outcome = ""
        status_code = 200
        submitted_draft: dict[str, str] = {}
        if request.method == "POST":
            submitted_draft = {
                key: str(request.form.get(key) or "")[:160]
                for key in ("choice", "row_index", "state_index", "target_id")
            }
            if get_current_auth_source() == "view_as":
                abort(403)
            user = get_current_user()
            if user is None:
                abort(403)
            allowed = {CSRF_FIELD_NAME, "expected_revision", "definition_digest",
                       "row_index", "state_index", "choice", "target_id"}
            if set(request.form) - allowed:
                abort(400)
            try:
                expected_revision = int(request.form["expected_revision"])
                expected_digest = str(request.form["definition_digest"])
                row_index = int(request.form["row_index"])
                choice = str(request.form["choice"])
                target_id = str(request.form.get("target_id") or "").strip()
                if len(expected_digest) != 64 or len(target_id) > 160:
                    raise ValueError("Repair input is invalid.")
                if (expected_revision != record.state_record.revision
                        or expected_digest != definition_digest(record.definition)):
                    raise CharacterStateConflictError("The reviewed Character changed. Refresh this preview.")
                if choice == "remap_definition":
                    new_definition, desired_state = repair_definition_identity(
                        record.definition, record.state_record.state,
                        definition_index=row_index,
                        state_index=int(request.form.get("state_index", "-1")),
                        new_id=target_id,
                    )
                else:
                    new_definition = record.definition
                    desired_state = repair_activation_state(
                        record.definition, record.state_record.state,
                        row_index=row_index, choice=choice, target_id=target_id,
                    )
                coordinator.update(
                    record, new_definition, record.import_metadata, desired_state,
                    expected_revision=expected_revision,
                    updated_by_user_id=user.id,
                    operation_kind="activation_repair",
                )
                refreshed = load_character_context(campaign_slug, character_slug)
                if refreshed is None:
                    abort(404)
                _, record = refreshed
                outcome = "Repair applied and reread from durable Character state."
            except (CharacterStateConflictError, CharacterPublicationConflict,
                    RuntimeStateLeaseError) as exc:
                outcome = str(exc) or "The Character changed; refresh before repairing."
                status_code = 409
            except (CharacterStateValidationError, ValueError, KeyError) as exc:
                outcome = str(exc)
                status_code = 400
        analysis = analyze_activation(record.definition, record.state_record.state)
        definition_rows = [item for item in list(record.definition.equipment_catalog or [])
                           if isinstance(item, dict) and not item.get("is_currency_only")]
        state_ids = {str(item.get("catalog_ref") or item.get("id") or "").strip()
                     for item in list(record.state_record.state.get("inventory") or [])
                     if isinstance(item, dict)}
        unique_targets = [str(item.get("id") or "").strip() for item in definition_rows
                          if str(item.get("id") or "").strip() not in state_ids
                          and sum(1 for row in definition_rows
                                  if str(row.get("id") or "").strip() == str(item.get("id") or "").strip()) == 1]
        return render_template(
            "character_equipment_activation_repair.html",
            campaign=campaign, character=record.definition,
            analysis=analysis, state_revision=record.state_record.revision,
            definition_digest=definition_digest(record.definition),
            unique_targets=unique_targets, outcome=outcome,
            submitted_draft=submitted_draft if status_code != 200 else {},
            state_rows=list(record.state_record.state.get("inventory") or []),
            active_nav="characters",
        ), status_code

    app.add_url_rule(
        "/campaigns/<campaign_slug>/characters/<character_slug>/equipment-activation-repair",
        endpoint="character_equipment_activation_repair_view",
        view_func=campaign_scope_access_required("characters")(view),
        methods=("GET", "POST"),
    )
