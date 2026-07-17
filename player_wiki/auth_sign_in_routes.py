from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from flask import Flask, current_app, flash, redirect, render_template, request, url_for


@dataclass(frozen=True)
class AuthSignInRouteDependencies:
    get_current_user: Callable[..., object]
    get_auth_store: Callable[..., object]
    get_login_throttle: Callable[..., object]
    account_digest: Callable[..., object]
    canonical_client_key: Callable[..., object]
    render_throttled_sign_in: Callable[..., object]
    check_sign_in_password: Callable[..., object]
    sign_in_failure_message: Callable[..., object]
    begin_browser_session: Callable[..., object]
    resolve_next_url: Callable[..., object]


def register_auth_sign_in_routes(
    app: Flask,
    *,
    dependencies: AuthSignInRouteDependencies,
) -> None:
    def sign_in() -> str:
        if dependencies.get_current_user() is not None:
            return redirect(url_for("home"))

        next_url = request.args.get("next", "").strip()
        return render_template("sign_in.html", next_url=next_url)

    def sign_in_submit() -> str:
        if dependencies.get_current_user() is not None:
            return redirect(url_for("home"))

        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        next_url = request.form.get("next", "").strip()

        store = dependencies.get_auth_store()
        throttle = dependencies.get_login_throttle()
        attempt = throttle.precheck(
            account_key=dependencies.account_digest(email),
            client_key=dependencies.canonical_client_key(request.remote_addr),
        )
        if attempt.decision.blocked:
            return dependencies.render_throttled_sign_in(
                email=email,
                next_url=next_url,
                retry_after=attempt.decision.retry_after,
            )

        try:
            user = store.get_user_by_email(email)
            password_matches = dependencies.check_sign_in_password(user, password)
        except Exception:
            throttle.cancel(attempt)
            raise
        if user is None or not user.is_active or not user.password_hash or not password_matches:
            decision = throttle.record_failure(attempt)
            if decision.blocked:
                return dependencies.render_throttled_sign_in(
                    email=email,
                    next_url=next_url,
                    retry_after=decision.retry_after,
                )
            flash(dependencies.sign_in_failure_message(), "error")
            return render_template("sign_in.html", email=email, next_url=next_url), 400

        try:
            raw_token, _ = store.create_session(
                user.id,
                expires_in=timedelta(hours=current_app.config["SESSION_TTL_HOURS"]),
                user_agent=request.user_agent.string or None,
                ip_address=request.remote_addr,
            )
            dependencies.begin_browser_session(raw_token)
        except Exception:
            throttle.cancel(attempt)
            raise
        throttle.record_success(attempt)
        flash(f"Signed in as {user.display_name}.", "success")
        return redirect(dependencies.resolve_next_url(next_url))

    app.add_url_rule(
        "/sign-in",
        endpoint="sign_in",
        view_func=sign_in,
        methods=("GET",),
    )
    app.add_url_rule(
        "/sign-in",
        endpoint="sign_in_submit",
        view_func=sign_in_submit,
        methods=("POST",),
    )
