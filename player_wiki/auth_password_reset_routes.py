from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Flask, current_app, flash, redirect, render_template, request, url_for


@dataclass(frozen=True)
class AuthPasswordResetRouteDependencies:
    get_auth_store: Callable[..., object]
    validate_password_inputs: Callable[..., object]
    generate_password_hash: Callable[..., object]
    timedelta: Callable[..., object]
    begin_browser_session: Callable[..., object]


def register_auth_password_reset_route(
    app: Flask,
    *,
    dependencies: AuthPasswordResetRouteDependencies,
) -> None:
    def password_reset(token: str) -> str | tuple[str, int]:
        resolved = dependencies.get_auth_store().get_valid_password_reset(token)
        if resolved is None:
            return render_template(
                "invite_setup.html",
                mode="reset",
                token_valid=False,
                page_title="Reset your password",
            ), 400

        reset_record, user = resolved
        if request.method == "POST":
            password = request.form.get("password", "")
            password_confirmation = request.form.get("password_confirmation", "")
            errors = dependencies.validate_password_inputs(password, password_confirmation)
            if errors:
                for error in errors:
                    flash(error, "error")
                return render_template(
                    "invite_setup.html",
                    mode="reset",
                    token_valid=True,
                    page_title="Reset your password",
                    user=user,
                ), 400

            store = dependencies.get_auth_store()
            store.set_password(user.id, dependencies.generate_password_hash(password))
            store.consume_password_reset(reset_record.id)
            store.revoke_all_user_sessions(user.id)
            store.revoke_all_user_api_tokens(user.id)
            store.write_audit_event(
                event_type="password_reset_completed",
                actor_user_id=user.id,
                target_user_id=user.id,
                metadata={"via": "reset_token"},
            )
            raw_token, _ = store.create_session(
                user.id,
                expires_in=dependencies.timedelta(
                    hours=current_app.config["SESSION_TTL_HOURS"]
                ),
                user_agent=request.user_agent.string or None,
                ip_address=request.remote_addr,
            )
            dependencies.begin_browser_session(raw_token)
            flash("Password updated.", "success")
            return redirect(url_for("home"))

        return render_template(
            "invite_setup.html",
            mode="reset",
            token_valid=True,
            page_title="Reset your password",
            user=user,
        )

    app.add_url_rule(
        "/reset/<token>",
        endpoint="password_reset",
        view_func=password_reset,
        methods=("GET", "POST"),
    )
