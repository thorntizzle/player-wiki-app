from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable

from flask import Blueprint, abort, current_app, flash, render_template, request

from .auth import (
    can_manage_campaign_combat,
    campaign_scope_access_required,
    get_current_user,
)
from .campaign_combat_service import (
    CampaignCombatRevisionConflictError,
    CampaignCombatValidationError,
)
from .live_presenter import (
    build_unchanged_live_payload,
    should_short_circuit_live_response,
    should_skip_selected_combatant_detail_render,
)


combat = Blueprint("combat", __name__)


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
    parse_live_detail_state_token_header: Callable[[], str]
    require_supported_combat_system: Callable[[str], Any]
    get_campaign_combat_service: Callable[[], Any]
    respond_to_campaign_combat_mutation: Callable[..., Any]
    parse_expected_combatant_revision: Callable[[], int | None]
    normalize_combat_return_view: Callable[[str], str]


def _dependencies() -> CombatRouteDependencies:
    return current_app.extensions["combat_route_dependencies"]


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
        context = dependencies.build_campaign_combat_page_context(
            campaign_slug,
            include_control_choices=True,
            combat_subpage="dm",
            combat_dm_view=combat_dm_view,
        )
    else:
        context = dependencies.build_campaign_combat_dm_status_context(
            campaign_slug,
        )
    return render_template("combat_dm.html", **context)


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
        flash("This combatant changed in another combat view. Refresh and try again.", "error")
    except CampaignCombatValidationError as exc:
        flash(str(exc), "error")
    else:
        flash("Turn value saved.", "success")
        mutation_succeeded = True

    return dependencies.respond_to_campaign_combat_mutation(
        campaign_slug,
        mutation_succeeded=mutation_succeeded,
        anchor=f"combatant-{combatant_id}",
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
    )
    for rule, endpoint, view_func in registrations:
        state.app.add_url_rule(
            rule,
            endpoint=endpoint,
            view_func=view_func,
            methods=("GET",),
        )


def register_combat_advance_turn_route(app: Any) -> None:
    app.add_url_rule(
        "/campaigns/<campaign_slug>/combat/advance-turn",
        endpoint="campaign_combat_advance_turn",
        view_func=campaign_combat_advance_turn,
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
    parse_live_detail_state_token_header: Callable[[], str],
    require_supported_combat_system: Callable[[str], Any],
    get_campaign_combat_service: Callable[[], Any],
    respond_to_campaign_combat_mutation: Callable[..., Any],
    parse_expected_combatant_revision: Callable[[], int | None],
    normalize_combat_return_view: Callable[[str], str],
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
        parse_live_detail_state_token_header=parse_live_detail_state_token_header,
        require_supported_combat_system=require_supported_combat_system,
        get_campaign_combat_service=get_campaign_combat_service,
        respond_to_campaign_combat_mutation=respond_to_campaign_combat_mutation,
        parse_expected_combatant_revision=parse_expected_combatant_revision,
        normalize_combat_return_view=normalize_combat_return_view,
    )
    app.register_blueprint(combat)
