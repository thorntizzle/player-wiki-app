from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Flask, abort, flash, g, redirect, request, url_for


@dataclass(frozen=True)
class AuthAccountThemeRouteDependencies:
    login_required: Callable[..., object]
    get_current_user: Callable[..., object]
    is_valid_theme_key: Callable[..., object]
    render_account_settings_page: Callable[..., object]
    get_theme_preset: Callable[..., object]
    normalize_theme_key: Callable[..., object]
    get_auth_store: Callable[..., object]


def register_auth_account_theme_route(
    app: Flask,
    *,
    dependencies: AuthAccountThemeRouteDependencies,
) -> None:
    def account_theme_update():
        user = dependencies.get_current_user()
        if user is None:
            abort(401)

        requested_theme_key = request.form.get("theme_key", "")
        if not dependencies.is_valid_theme_key(requested_theme_key):
            flash("Choose a valid theme preset.", "error")
            return dependencies.render_account_settings_page(status_code=400)

        selected_theme = dependencies.get_theme_preset(
            dependencies.normalize_theme_key(requested_theme_key)
        )
        store = dependencies.get_auth_store()
        current_theme_key = store.get_user_preferences(user.id).theme_key
        if current_theme_key == selected_theme.key:
            flash(f"Theme already set to {selected_theme.label}.", "success")
            return redirect(url_for("account_settings_view"))

        store.set_user_theme_key(user.id, selected_theme.key)
        g.current_theme = selected_theme
        flash(f"Theme updated to {selected_theme.label}.", "success")
        return redirect(url_for("account_settings_view"))

    app.add_url_rule(
        "/account/theme",
        endpoint="account_theme_update",
        view_func=dependencies.login_required(account_theme_update),
        methods=("POST",),
    )
