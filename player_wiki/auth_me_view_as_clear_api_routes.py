from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint, jsonify


@dataclass(frozen=True)
class AuthMeViewAsClearApiDependencies:
    api_login_required: Callable[..., object]
    get_authenticated_user: Callable[..., object]
    json_error: Callable[..., object]
    clear_requested_view_as_user_id: Callable[..., object]
    serialize_view_as_state: Callable[..., object]


def register_auth_me_view_as_clear_api_route(
    api: Blueprint,
    *,
    dependencies: AuthMeViewAsClearApiDependencies,
) -> None:
    def me_view_as_clear():
        user = dependencies.get_authenticated_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.", 401, code="auth_required"
            )
        if not user.is_admin:
            return dependencies.json_error(
                "Only app admins can use View As.", 403, code="forbidden"
            )
        dependencies.clear_requested_view_as_user_id()
        return jsonify(
            {"ok": True, "view_as": dependencies.serialize_view_as_state()}
        )

    api.add_url_rule(
        "/me/view-as",
        endpoint="me_view_as_clear",
        view_func=dependencies.api_login_required(me_view_as_clear),
        methods=("DELETE",),
    )
