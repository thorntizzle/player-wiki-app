from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Flask, current_app, flash, g, redirect, render_template, request, session, url_for


@dataclass(frozen=True)
class AuthInviteSetupRouteDependencies:
    get_auth_store: Callable[..., object]
    validate_password_inputs: Callable[..., object]
    generate_password_hash: Callable[..., object]
    timedelta: Callable[..., object]
    begin_browser_session: Callable[..., object]


def register_auth_invite_setup_route(
    app: Flask,
    *,
    dependencies: AuthInviteSetupRouteDependencies,
) -> None:
    def invite_setup(token: str) -> str | tuple[str, int]:
        resolved = dependencies.get_auth_store().get_valid_invite(token)
        if resolved is None:
            return render_template(
                "invite_setup.html",
                mode="invite",
                token_valid=False,
                page_title="Set your password",
            ), 400

        _, user = resolved
        if user.status != "invited":
            return render_template(
                "invite_setup.html",
                mode="invite",
                token_valid=False,
                page_title="Set your password",
            ), 400

        if request.method == "POST":
            display_name = request.form.get("display_name", user.display_name).strip()
            password = request.form.get("password", "")
            password_confirmation = request.form.get("password_confirmation", "")
            errors = dependencies.validate_password_inputs(password, password_confirmation)
            if not display_name:
                errors.append("Display name is required.")

            if errors:
                for error in errors:
                    flash(error, "error")
                return render_template(
                    "invite_setup.html",
                    mode="invite",
                    token_valid=True,
                    page_title="Set your password",
                    display_name=display_name,
                    user=user,
                ), 400

            password_hash = dependencies.generate_password_hash(password)
            store = dependencies.get_auth_store()
            user = store.complete_invite(
                token, display_name=display_name, password_hash=password_hash
            )
            if user is None:
                return render_template(
                    "invite_setup.html",
                    mode="invite",
                    token_valid=False,
                    page_title="Set your password",
                ), 400
            try:
                raw_token, _ = store.create_session(
                    user.id,
                    expires_in=dependencies.timedelta(
                        hours=current_app.config["SESSION_TTL_HOURS"]
                    ),
                    user_agent=request.user_agent.string or None,
                    ip_address=request.remote_addr,
                )
                dependencies.begin_browser_session(raw_token)
                flash("Account setup complete.", "success")
                return redirect(url_for("home"))
            except Exception:
                # Account activation and credential revocation remain committed.
                session.clear()
                g.browser_session_started = False
                return render_template("auth_transition_recovery.html", mode="invite"), 503

        return render_template(
            "invite_setup.html",
            mode="invite",
            token_valid=True,
            page_title="Set your password",
            display_name=user.display_name,
            user=user,
        )

    app.add_url_rule(
        "/invite/<token>",
        endpoint="invite_setup",
        view_func=invite_setup,
        methods=("GET", "POST"),
    )
