from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Flask, abort, flash, g, redirect, request, url_for


@dataclass(frozen=True)
class AuthAccountSessionChatOrderRouteDependencies:
    login_required: Callable[..., object]
    get_current_user: Callable[..., object]
    is_valid_session_chat_order: Callable[..., object]
    render_account_settings_page: Callable[..., object]
    normalize_session_chat_order: Callable[..., object]
    get_auth_store: Callable[..., object]
    session_chat_order_labels: Callable[..., object]


def register_auth_account_session_chat_order_route(
    app: Flask,
    *,
    dependencies: AuthAccountSessionChatOrderRouteDependencies,
) -> None:
    def account_session_chat_order_update():
        user = dependencies.get_current_user()
        if user is None:
            abort(401)

        requested_order = request.form.get("session_chat_order", "")
        if not dependencies.is_valid_session_chat_order(requested_order):
            g.account_session_chat_order_error = (
                "Choose a valid live session chat order."
            )
            g.account_submitted_session_chat_order = requested_order
            return dependencies.render_account_settings_page(status_code=400)

        normalized_order = dependencies.normalize_session_chat_order(requested_order)
        current_preferences = dependencies.get_auth_store().get_user_preferences(user.id)
        if current_preferences.session_chat_order == normalized_order:
            flash(
                f"Live session chat order already set to {dependencies.session_chat_order_labels()[normalized_order]}.",
                "success",
            )
            return redirect(url_for("account_settings_view"))

        updated_preferences = dependencies.get_auth_store().set_user_session_chat_order(
            user.id, normalized_order
        )
        g.current_user_preferences = updated_preferences
        flash(
            f"Live session chat order updated to {dependencies.session_chat_order_labels()[normalized_order]}.",
            "success",
        )
        return redirect(url_for("account_settings_view"))

    app.add_url_rule(
        "/account/session-chat-order",
        endpoint="account_session_chat_order_update",
        view_func=dependencies.login_required(account_session_chat_order_update),
        methods=("POST",),
    )
