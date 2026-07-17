from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flask import Flask, current_app, flash, redirect, render_template, request, url_for


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

        invite_record, user = resolved
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
            store.activate_user(user.id, display_name=display_name, password_hash=password_hash)
            store.consume_invite(invite_record.id)
            store.revoke_all_user_sessions(user.id)
            store.revoke_all_user_api_tokens(user.id)
            store.write_audit_event(
                event_type="user_activated",
                actor_user_id=user.id,
                target_user_id=user.id,
                metadata={"via": "invite"},
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
            flash("Account setup complete.", "success")
            return redirect(url_for("home"))

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
