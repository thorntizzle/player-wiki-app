from __future__ import annotations

import hmac
import secrets

from flask import Flask, current_app, g, jsonify, render_template, request, session
from markupsafe import Markup, escape

CSRF_FIELD_NAME = "_csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_SESSION_KEY = "csrf_token"
CSRF_FAILURE_CODE = "csrf_failed"
CSRF_FAILURE_MESSAGE = "The request could not be verified."

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_SESSION_SETUP_ENDPOINTS = frozenset({"sign_in_submit", "invite_setup", "password_reset"})
_TOKEN_BYTES = 32
_TOKEN_LENGTH = 43
_MAX_SUBMITTED_TOKEN_LENGTH = 256


def register_csrf(app: Flask) -> None:
    app.config.setdefault("CSRF_ENABLED", True)
    app.jinja_env.globals["csrf_input"] = csrf_input

    @app.after_request
    def protect_authenticated_html(response):
        if response.mimetype != "text/html" or request.path.startswith("/static/"):
            return response
        if (
            getattr(g, "current_session_record", None) is not None
            or getattr(g, "current_api_token_record", None) is not None
            or getattr(g, "csrf_token_rendered", False)
            or getattr(g, "browser_session_started", False)
        ):
            response.headers["Cache-Control"] = "private, no-store"
        return response


def csrf_input() -> Markup:
    token = get_or_create_csrf_token()
    g.csrf_token_rendered = bool(token)
    return Markup(
        f'<input type="hidden" name="{CSRF_FIELD_NAME}" value="{escape(token)}">'
    )


def get_or_create_csrf_token() -> str:
    if getattr(g, "current_session_record", None) is None:
        return ""

    current = session.get(CSRF_SESSION_KEY)
    if _is_well_formed_token(current):
        return current

    token = secrets.token_urlsafe(_TOKEN_BYTES)
    session[CSRF_SESSION_KEY] = token
    return token


def enforce_csrf() -> object | None:
    if not current_app.config.get("CSRF_ENABLED", True):
        return None
    if request.method in _SAFE_METHODS:
        return None
    if request.endpoint in _SESSION_SETUP_ENDPOINTS:
        return None
    if getattr(g, "current_session_record", None) is None:
        return None
    if getattr(g, "current_api_token_record", None) is not None:
        return None

    expected = session.get(CSRF_SESSION_KEY)
    submitted = request.headers.get(CSRF_HEADER_NAME)
    if submitted is None:
        submitted = request.form.get(CSRF_FIELD_NAME)

    if not _is_well_formed_token(expected) or not _is_bounded_submission(submitted):
        return csrf_failure_response()
    if not hmac.compare_digest(expected, submitted):
        return csrf_failure_response()
    return None


def csrf_failure_response():
    if _wants_json_error():
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": CSRF_FAILURE_CODE,
                        "message": CSRF_FAILURE_MESSAGE,
                        "details": {},
                    },
                }
            ),
            400,
        )
    return render_template("csrf_error.html"), 400


def _is_well_formed_token(value: object) -> bool:
    return isinstance(value, str) and len(value) == _TOKEN_LENGTH


def _is_bounded_submission(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= _MAX_SUBMITTED_TOKEN_LENGTH
        and len(value) == _TOKEN_LENGTH
    )


def _wants_json_error() -> bool:
    return (
        request.path.startswith("/api/")
        or request.headers.get("X-Requested-With", "").lower() == "xmlhttprequest"
        or request.is_json
    )
