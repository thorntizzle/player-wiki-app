from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint, jsonify


@dataclass(frozen=True)
class AuthMeSettingsViewApiDependencies:
    api_login_required: Callable[..., object]
    get_current_user: Callable[..., object]
    json_error: Callable[..., object]
    get_current_user_preferences: Callable[..., object]
    serialize_theme_preset: Callable[..., object]
    list_theme_presets: Callable[..., object]
    session_chat_order_choices: list[dict[str, str]]
    serialize_user: Callable[..., object]


def register_auth_me_settings_view_api_route(
    api: Blueprint,
    *,
    dependencies: AuthMeSettingsViewApiDependencies,
) -> None:
    def me_settings():
        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.", 401, code="auth_required"
            )

        preferences = dependencies.get_current_user_preferences()
        return jsonify(
            {
                "ok": True,
                "theme_presets": [
                    dependencies.serialize_theme_preset(preset)
                    for preset in dependencies.list_theme_presets()
                ],
                "session_chat_order_choices": dependencies.session_chat_order_choices,
                "preferences": {
                    "theme_key": preferences.theme_key,
                    "session_chat_order": preferences.session_chat_order,
                    "frontend_mode": preferences.frontend_mode,
                },
                "user": dependencies.serialize_user(user),
            }
        )

    api.add_url_rule(
        "/me/settings",
        endpoint="me_settings",
        view_func=dependencies.api_login_required(me_settings),
        methods=("GET",),
    )
