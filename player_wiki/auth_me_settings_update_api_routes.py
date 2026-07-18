from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint, jsonify


@dataclass(frozen=True)
class AuthMeSettingsUpdateApiDependencies:
    api_login_required: Callable[..., object]
    get_current_user: Callable[..., object]
    json_error: Callable[..., object]
    load_json_object: Callable[..., object]
    is_valid_theme_key: Callable[..., object]
    is_valid_session_chat_order: Callable[..., object]
    get_auth_store: Callable[..., object]
    get_theme_preset: Callable[..., object]
    normalize_session_chat_order: Callable[..., object]
    serialize_user: Callable[..., object]


def register_auth_me_settings_update_api_route(
    api: Blueprint,
    *,
    dependencies: AuthMeSettingsUpdateApiDependencies,
) -> None:
    def me_settings_update():
        user = dependencies.get_current_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.", 401, code="auth_required"
            )

        try:
            payload = dependencies.load_json_object()
        except ValueError as exc:
            return dependencies.json_error(
                str(exc), 400, code="validation_error"
            )

        requested_theme_key = payload.get("theme_key", "")
        requested_chat_order = payload.get("session_chat_order", "")
        has_theme_update = bool(str(requested_theme_key).strip())
        has_chat_order_update = bool(str(requested_chat_order).strip())

        if "frontend_mode" in payload:
            return dependencies.json_error(
                "Preferred frontend selection is no longer available.",
                400,
                code="validation_error",
            )

        if not has_theme_update and not has_chat_order_update:
            return dependencies.json_error(
                "No account settings were provided.",
                400,
                code="validation_error",
            )

        if has_theme_update:
            if not dependencies.is_valid_theme_key(str(requested_theme_key)):
                return dependencies.json_error(
                    "Choose a valid theme preset.",
                    400,
                    code="validation_error",
                )

        if has_chat_order_update:
            if not dependencies.is_valid_session_chat_order(requested_chat_order):
                return dependencies.json_error(
                    "Choose a valid live session chat order.",
                    400,
                    code="validation_error",
                )

        store = dependencies.get_auth_store()
        current_preferences = store.get_user_preferences(user.id)
        normalized_theme_key = current_preferences.theme_key
        normalized_chat_order = current_preferences.session_chat_order

        if has_theme_update:
            normalized_theme_key = dependencies.get_theme_preset(
                requested_theme_key
            ).key
            if normalized_theme_key != current_preferences.theme_key:
                store.set_user_theme_key(user.id, normalized_theme_key)

        if has_chat_order_update:
            normalized_chat_order = dependencies.normalize_session_chat_order(
                requested_chat_order
            )
            if normalized_chat_order != current_preferences.session_chat_order:
                store.set_user_session_chat_order(user.id, normalized_chat_order)

        updated_preferences = store.get_user_preferences(user.id)

        return jsonify(
            {
                "ok": True,
                "user": dependencies.serialize_user(user),
                "preferences": {
                    "theme_key": updated_preferences.theme_key,
                    "session_chat_order": updated_preferences.session_chat_order,
                    "frontend_mode": updated_preferences.frontend_mode,
                },
            }
        )

    api.add_url_rule(
        "/me/settings",
        endpoint="me_settings_update",
        view_func=dependencies.api_login_required(me_settings_update),
        methods=("PATCH",),
    )
