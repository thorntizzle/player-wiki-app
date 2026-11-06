from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, jsonify, request

from .auth import get_authenticated_user
from .character_builder import CharacterBuildError
from .committed_publication import active
from .character_spell_grants import (
    ACQUISITION_FIELD, TRUSTED_ACQUISITION_KEY, GrantContractError,
    resolve_acquisition_intent,
)
from .system_policy import CHARACTER_ROUTE_LANE_DND5E, native_character_create_lane


@dataclass(frozen=True)
class CharacterCreateContextApiDependencies:
    ensure_character_authoring_access: Callable[[str], tuple[Any, Any | None]]
    build_character_create_payload: Callable[..., dict[str, Any]]


def register_character_create_context_api_route(
    api: Blueprint,
    *,
    dependencies: CharacterCreateContextApiDependencies,
) -> None:
    def character_create_context(campaign_slug: str):
        campaign, access_error = dependencies.ensure_character_authoring_access(
            campaign_slug
        )
        if access_error is not None:
            return access_error
        values = dict(request.args)
        values.pop(ACQUISITION_FIELD, None)
        values.pop(TRUSTED_ACQUISITION_KEY, None)
        try:
            if (native_character_create_lane(getattr(campaign, "system", "")) == CHARACTER_ROUTE_LANE_DND5E
                    and active()):
                token, acquisition = resolve_acquisition_intent(
                    request.args, campaign_slug=campaign_slug,
                    actor_id=getattr(get_authenticated_user(), "id", None),
                    mode="create", allow_issue="_live_preview" not in request.args,
                )
                values[ACQUISITION_FIELD] = token
                values[TRUSTED_ACQUISITION_KEY] = acquisition
            payload = dependencies.build_character_create_payload(
                campaign_slug,
                campaign,
                values,
            )
        except (GrantContractError, CharacterBuildError) as exc:
            return jsonify({"ok": False, "error": {
                "code": "acquisition_validation_failed" if isinstance(exc, GrantContractError) else "validation_error",
                "message": str(exc),
            }}), 400
        return jsonify(payload)

    api.add_url_rule(
        "/campaigns/<campaign_slug>/characters/create",
        endpoint="character_create_context",
        view_func=character_create_context,
        methods=("GET",),
    )
