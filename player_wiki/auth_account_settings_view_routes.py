from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Flask


@dataclass(frozen=True)
class AuthAccountSettingsViewRouteDependencies:
    login_required: Callable[..., object]
    render_account_settings_page: Callable[..., object]


def register_auth_account_settings_view_route(
    app: Flask,
    *,
    dependencies: AuthAccountSettingsViewRouteDependencies,
) -> None:
    def account_settings_view():
        return dependencies.render_account_settings_page()

    app.add_url_rule(
        "/account",
        endpoint="account_settings_view",
        view_func=dependencies.login_required(account_settings_view),
        methods=("GET",),
    )
