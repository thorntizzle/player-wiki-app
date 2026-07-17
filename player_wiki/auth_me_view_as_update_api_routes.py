from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Blueprint, jsonify


@dataclass(frozen=True)
class AuthMeViewAsUpdateApiDependencies:
    api_login_required: Callable[..., object]
    get_authenticated_user: Callable[..., object]
    json_error: Callable[..., object]
    load_json_object: Callable[..., object]
    clear_requested_view_as_user_id: Callable[..., object]
    serialize_view_as_state: Callable[..., object]
    get_auth_store: Callable[..., object]
    set_requested_view_as_user_id: Callable[..., object]


def register_auth_me_view_as_update_api_route(
    api: Blueprint,
    *,
    dependencies: AuthMeViewAsUpdateApiDependencies,
) -> None:
    def me_view_as_update():
        user = dependencies.get_authenticated_user()
        if user is None:
            return dependencies.json_error(
                "Authentication required.", 401, code="auth_required"
            )
        if not user.is_admin:
            return dependencies.json_error(
                "Only app admins can use View As.", 403, code="forbidden"
            )

        try:
            payload = dependencies.load_json_object()
        except ValueError as exc:
            return dependencies.json_error(
                str(exc), 400, code="validation_error"
            )

        raw_user_id = payload.get("user_id")
        if raw_user_id in (None, ""):
            dependencies.clear_requested_view_as_user_id()
            return jsonify(
                {"ok": True, "view_as": dependencies.serialize_view_as_state()}
            )

        try:
            target_user_id = int(raw_user_id)
        except (TypeError, ValueError):
            return dependencies.json_error(
                "Choose a valid user to view as.", 400, code="validation_error"
            )

        if target_user_id == user.id:
            dependencies.clear_requested_view_as_user_id()
            return jsonify(
                {"ok": True, "view_as": dependencies.serialize_view_as_state()}
            )

        target_user = dependencies.get_auth_store().get_user_by_id(target_user_id)
        if target_user is None or not target_user.is_active:
            return dependencies.json_error(
                "Choose an active user to view as.", 400, code="validation_error"
            )

        dependencies.set_requested_view_as_user_id(target_user.id)
        return jsonify(
            {"ok": True, "view_as": dependencies.serialize_view_as_state()}
        )

    api.add_url_rule(
        "/me/view-as",
        endpoint="me_view_as_update",
        view_func=dependencies.api_login_required(me_view_as_update),
        methods=("POST",),
    )
