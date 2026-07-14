from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, jsonify, request


@dataclass(frozen=True)
class CombatApiReadDependencies:
    combat_scope_access_required: Callable[[Callable[..., Any]], Callable[..., Any]]
    build_combat_payload: Callable[..., dict[str, Any]]
    should_short_circuit_live_response: Callable[..., bool]


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
