from __future__ import annotations

import secrets

from flask import Flask, g, request

_NONCE_BYTES = 32
_AUTH_HTML_ENDPOINTS = frozenset(
    {
        "sign_in",
        "sign_in_submit",
        "invite_setup",
        "password_reset",
        "account_settings_view",
        "account_theme_update",
        "account_session_chat_order_update",
    }
)

_PERMISSIONS_POLICY = "camera=(), geolocation=(), microphone=(), payment=(), usb=()"
_HSTS_POLICY = "max-age=31536000; includeSubDomains"


def register_security_headers(app: Flask) -> None:
    app.jinja_env.globals["csp_nonce"] = get_csp_nonce

    @app.after_request
    def apply_security_headers(response):
        production_secure = app.config.get("APP_ENV") == "production" and request.is_secure
        response.headers["Content-Security-Policy"] = build_content_security_policy(
            get_csp_nonce(),
            upgrade_insecure_requests=production_secure,
        )
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = _PERMISSIONS_POLICY

        if production_secure:
            response.headers["Strict-Transport-Security"] = _HSTS_POLICY
        else:
            response.headers.pop("Strict-Transport-Security", None)

        if response.mimetype == "text/html" and _is_auth_or_token_html_endpoint():
            response.headers["Cache-Control"] = "private, no-store"
        return response


def get_csp_nonce() -> str:
    nonce = getattr(g, "csp_nonce", None)
    if isinstance(nonce, str) and nonce:
        return nonce

    nonce = secrets.token_urlsafe(_NONCE_BYTES)
    g.csp_nonce = nonce
    return nonce


def build_content_security_policy(
    nonce: str,
    *,
    upgrade_insecure_requests: bool = False,
) -> str:
    directives = [
        "default-src 'self'",
        "base-uri 'none'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "frame-src 'none'",
        "form-action 'self'",
        f"script-src 'self' 'nonce-{nonce}'",
        "script-src-attr 'none'",
        f"style-src-elem 'self' 'nonce-{nonce}'",
        "style-src-attr 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "media-src 'self'",
        "worker-src 'none'",
        "manifest-src 'self'",
    ]
    if upgrade_insecure_requests:
        directives.append("upgrade-insecure-requests")
    return "; ".join(directives)


def _is_auth_or_token_html_endpoint() -> bool:
    endpoint = str(request.endpoint or "")
    return endpoint in _AUTH_HTML_ENDPOINTS or endpoint.startswith("admin_")
