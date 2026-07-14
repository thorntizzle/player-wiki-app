from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, abort, jsonify, request

from .campaign_combat_service import (
    CampaignCombatRevisionConflictError,
    CampaignCombatValidationError,
)


@dataclass(frozen=True)
class CombatApiReadDependencies:
    combat_scope_access_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    build_combat_payload: Callable[..., dict[str, Any]]
    should_short_circuit_live_response: Callable[..., bool]


@dataclass(frozen=True)
class CombatConditionApiDependencies:
    combat_scope_access_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    login_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    can_manage_combat: Callable[[str], bool]
    get_current_user: Callable[[], Any | None]
    load_json_object: Callable[[], dict[str, Any]]
    require_supported_combat_campaign: Callable[[str], Any]
    get_combat_service: Callable[[], Any]
    build_combat_payload: Callable[..., dict[str, Any]]
    json_error: Callable[..., Any]


@dataclass(frozen=True)
class CombatCombatantDeleteApiDependencies:
    combat_scope_access_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    login_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    can_manage_combat: Callable[[str], bool]
    require_supported_combat_campaign: Callable[[str], Any]
    get_combat_service: Callable[[], Any]
    build_combat_payload: Callable[..., dict[str, Any]]
    json_error: Callable[..., Any]


@dataclass(frozen=True)
class CombatCustomNpcCreateApiDependencies:
    combat_scope_access_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    login_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    can_manage_combat: Callable[[str], bool]
    get_current_user: Callable[[], Any | None]
    load_json_object: Callable[[], dict[str, Any]]
    require_supported_combat_campaign: Callable[[str], Any]
    get_combat_service: Callable[[], Any]
    build_combat_payload: Callable[..., dict[str, Any]]
    json_error: Callable[..., Any]


@dataclass(frozen=True)
class CombatNpcResourcesUpdateApiDependencies:
    combat_scope_access_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    login_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    can_manage_combat: Callable[[str], bool]
    get_current_user: Callable[[], Any | None]
    load_json_object: Callable[[], dict[str, Any]]
    require_supported_combat_campaign: Callable[[str], Any]
    get_combat_service: Callable[[], Any]
    build_combat_payload: Callable[..., dict[str, Any]]
    json_error: Callable[..., Any]


def register_combat_api_read_routes(
    api: Blueprint,
    *,
    dependencies: CombatApiReadDependencies,
) -> None:
    def combat_state(campaign_slug: str):
        payload = dependencies.build_combat_payload(campaign_slug)
        if dependencies.should_short_circuit_live_response(
            request.headers,
            live_revision=int(payload["live_revision"] or 0),
            live_view_token=str(payload["live_view_token"] or ""),
        ):
            return jsonify(
                {
                    "ok": True,
                    "changed": False,
                    "live_revision": payload["live_revision"],
                    "live_view_token": payload["live_view_token"],
                }
            )
        return jsonify({"ok": True, **payload})

    def combat_live_state(campaign_slug: str):
        payload = dependencies.build_combat_payload(
            campaign_slug,
            include_sidebar_choices=False,
        )
        if dependencies.should_short_circuit_live_response(
            request.headers,
            live_revision=int(payload["live_revision"] or 0),
            live_view_token=str(payload["live_view_token"] or ""),
        ):
            return jsonify(
                {
                    "ok": True,
                    "changed": False,
                    "live_revision": payload["live_revision"],
                    "live_view_token": payload["live_view_token"],
                }
            )
        return jsonify({"ok": True, **payload})

    combat_state_view = dependencies.combat_scope_access_required(combat_state)
    combat_live_state_view = dependencies.combat_scope_access_required(
        combat_live_state
    )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/combat",
        endpoint="combat_state",
        view_func=combat_state_view,
        methods=("GET",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/combat/live-state",
        endpoint="combat_live_state",
        view_func=combat_live_state_view,
        methods=("GET",),
    )


def register_combat_condition_api_routes(
    api: Blueprint,
    *,
    dependencies: CombatConditionApiDependencies,
) -> None:
    def combat_condition_create(campaign_slug: str, combatant_id: int):
        if not dependencies.can_manage_combat(campaign_slug):
            return dependencies.json_error(
                "You do not have permission to manage combat.",
                403,
                code="forbidden",
            )

        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.",
                401,
                code="auth_required",
            )

        try:
            payload = dependencies.load_json_object()
            dependencies.require_supported_combat_campaign(campaign_slug)
            dependencies.get_combat_service().add_condition(
                campaign_slug,
                combatant_id,
                name=str(payload.get("name") or "").strip(),
                duration_text=str(payload.get("duration_text") or "").strip(),
                created_by_user_id=user.id,
            )
        except (CampaignCombatValidationError, ValueError) as exc:
            return dependencies.json_error(
                str(exc),
                400,
                code="validation_error",
            )

        return jsonify(
            {
                "ok": True,
                **dependencies.build_combat_payload(campaign_slug),
            }
        )

    def combat_condition_delete(campaign_slug: str, condition_id: int):
        if not dependencies.can_manage_combat(campaign_slug):
            return dependencies.json_error(
                "You do not have permission to manage combat.",
                403,
                code="forbidden",
            )

        try:
            dependencies.require_supported_combat_campaign(campaign_slug)
            dependencies.get_combat_service().delete_condition(
                campaign_slug,
                condition_id,
            )
        except CampaignCombatValidationError as exc:
            return dependencies.json_error(
                str(exc),
                400,
                code="validation_error",
            )

        return jsonify(
            {
                "ok": True,
                **dependencies.build_combat_payload(campaign_slug),
            }
        )

    combat_condition_create_view = dependencies.combat_scope_access_required(
        dependencies.login_required(combat_condition_create)
    )
    combat_condition_delete_view = dependencies.combat_scope_access_required(
        dependencies.login_required(combat_condition_delete)
    )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/conditions",
        endpoint="combat_condition_create",
        view_func=combat_condition_create_view,
        methods=("POST",),
    )
    api.add_url_rule(
        "/campaigns/<campaign_slug>/combat/conditions/<int:condition_id>",
        endpoint="combat_condition_delete",
        view_func=combat_condition_delete_view,
        methods=("DELETE",),
    )


def register_combat_combatant_delete_api_route(
    api: Blueprint,
    *,
    dependencies: CombatCombatantDeleteApiDependencies,
) -> None:
    def combat_combatant_delete(campaign_slug: str, combatant_id: int):
        if not dependencies.can_manage_combat(campaign_slug):
            return dependencies.json_error(
                "You do not have permission to manage combat.",
                403,
                code="forbidden",
            )

        try:
            dependencies.require_supported_combat_campaign(campaign_slug)
            dependencies.get_combat_service().delete_combatant(
                campaign_slug,
                combatant_id,
            )
        except CampaignCombatValidationError as exc:
            return dependencies.json_error(
                str(exc),
                400,
                code="validation_error",
            )

        return jsonify(
            {
                "ok": True,
                **dependencies.build_combat_payload(campaign_slug),
            }
        )

    combat_combatant_delete_view = dependencies.combat_scope_access_required(
        dependencies.login_required(combat_combatant_delete)
    )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>",
        endpoint="combat_combatant_delete",
        view_func=combat_combatant_delete_view,
        methods=("DELETE",),
    )


def register_combat_custom_npc_create_api_route(
    api: Blueprint,
    *,
    dependencies: CombatCustomNpcCreateApiDependencies,
) -> None:
    def combat_add_npc(campaign_slug: str):
        if not dependencies.can_manage_combat(campaign_slug):
            return dependencies.json_error(
                "You do not have permission to manage combat.",
                403,
                code="forbidden",
            )

        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.",
                401,
                code="auth_required",
            )

        try:
            payload = dependencies.load_json_object()
            dependencies.require_supported_combat_campaign(campaign_slug)
            dependencies.get_combat_service().add_npc_combatant(
                campaign_slug,
                display_name=str(payload.get("display_name") or "").strip(),
                turn_value=payload.get("turn_value"),
                initiative_bonus=payload.get("initiative_bonus"),
                dexterity_modifier=payload.get("dexterity_modifier"),
                initiative_priority=payload.get("initiative_priority"),
                current_hp=payload.get("current_hp"),
                max_hp=payload.get("max_hp"),
                temp_hp=payload.get("temp_hp"),
                movement_total=payload.get("movement_total"),
                created_by_user_id=user.id,
            )
        except (CampaignCombatValidationError, ValueError) as exc:
            return dependencies.json_error(
                str(exc),
                400,
                code="validation_error",
            )

        return jsonify(
            {
                "ok": True,
                **dependencies.build_combat_payload(campaign_slug),
            }
        )

    combat_add_npc_view = dependencies.combat_scope_access_required(
        dependencies.login_required(combat_add_npc)
    )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/combat/npc-combatants",
        endpoint="combat_add_npc",
        view_func=combat_add_npc_view,
        methods=("POST",),
    )


def register_combat_npc_resources_update_api_route(
    api: Blueprint,
    *,
    dependencies: CombatNpcResourcesUpdateApiDependencies,
) -> None:
    def combat_npc_resources_update(campaign_slug: str, combatant_id: int):
        if not dependencies.can_manage_combat(campaign_slug):
            return dependencies.json_error(
                "You do not have permission to manage combat.",
                403,
                code="forbidden",
            )

        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.",
                401,
                code="auth_required",
            )

        combat_service = dependencies.get_combat_service()
        combatant = combat_service.get_combatant(campaign_slug, combatant_id)
        if combatant is None:
            abort(404)

        try:
            payload = dependencies.load_json_object()
            dependencies.require_supported_combat_campaign(campaign_slug)
            expected_combatant_revision = payload.get("expected_combatant_revision")
            counters = payload.get("counters")
            if not isinstance(counters, list):
                raise CampaignCombatValidationError(
                    "NPC resource counters must be sent as a list."
                )
            combat_service.update_npc_resource_counters(
                campaign_slug,
                combatant_id,
                expected_revision=(
                    int(expected_combatant_revision)
                    if expected_combatant_revision is not None
                    and str(expected_combatant_revision).strip()
                    else None
                ),
                counter_values=counters,
                updated_by_user_id=user.id,
            )
        except CampaignCombatRevisionConflictError:
            return dependencies.json_error(
                "This combatant changed in another combat view. Refresh and try again.",
                409,
                code="state_conflict",
            )
        except (CampaignCombatValidationError, ValueError) as exc:
            return dependencies.json_error(
                str(exc),
                400,
                code="validation_error",
            )

        return jsonify(
            {
                "ok": True,
                **dependencies.build_combat_payload(campaign_slug),
            }
        )

    combat_npc_resources_update_view = dependencies.combat_scope_access_required(
        dependencies.login_required(combat_npc_resources_update)
    )

    api.add_url_rule(
        "/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/npc-resources",
        endpoint="combat_npc_resources_update",
        view_func=combat_npc_resources_update_view,
        methods=("PATCH",),
    )
