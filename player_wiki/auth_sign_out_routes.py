from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Flask, flash, redirect, session, url_for


@dataclass(frozen=True)
class AuthSignOutRouteDependencies:
    login_required: Callable[..., object]
    get_current_session_record: Callable[..., object]
    get_auth_store: Callable[..., object]


def register_auth_sign_out_route(
    app: Flask,
    *,
    dependencies: AuthSignOutRouteDependencies,
) -> None:
    def sign_out() -> str:
        session_record = dependencies.get_current_session_record()
        if session_record is not None:
            dependencies.get_auth_store().revoke_session(session_record.id)

        session.clear()
        flash("Signed out.", "success")
        return redirect(url_for("sign_in"))

    app.add_url_rule(
        "/sign-out",
        endpoint="sign_out",
        view_func=dependencies.login_required(sign_out),
        methods=("POST",),
    )
