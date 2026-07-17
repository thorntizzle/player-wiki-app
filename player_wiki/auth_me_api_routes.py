from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint, jsonify


@dataclass(frozen=True)
class AuthMeApiDependencies:
    api_login_required: Callable[..., object]
    get_authenticated_user: Callable[..., object]
    json_error: Callable[..., object]
    serialize_app_state: Callable[..., object]
    get_current_auth_source: Callable[..., object]
    serialize_user: Callable[..., object]
    get_current_memberships: Callable[..., object]
    serialize_membership: Callable[..., object]
    get_current_user_preferences: Callable[..., object]
    serialize_view_as_state: Callable[..., object]


def register_auth_me_api_route(
    api: Blueprint,
    *,
    dependencies: AuthMeApiDependencies,
) -> None:
    def me():
        user = dependencies.get_authenticated_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.", 401, code="auth_required"
            )
        return jsonify(
            {
                "ok": True,
                "app": dependencies.serialize_app_state(),
                "auth_source": dependencies.get_current_auth_source(),
                "user": dependencies.serialize_user(user),
                "memberships": [
                    dependencies.serialize_membership(item)
                    for item in dependencies.get_current_memberships()
                ],
                "preferences": {
                    "theme_key": dependencies.get_current_user_preferences().theme_key,
                    "session_chat_order": dependencies.get_current_user_preferences().session_chat_order,
                    "frontend_mode": dependencies.get_current_user_preferences().frontend_mode,
                },
                "view_as": dependencies.serialize_view_as_state(),
            }
        )

    api.add_url_rule(
        "/me",
        endpoint="me",
        view_func=dependencies.api_login_required(me),
        methods=("GET",),
    )
