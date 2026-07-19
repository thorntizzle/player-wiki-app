from __future__ import annotations

import base64
from pathlib import Path
import re

from player_wiki.security_headers import build_content_security_policy


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = PROJECT_ROOT / "player_wiki" / "templates"
SESSION_SHELL_PATH = PROJECT_ROOT / "player_wiki" / "static" / "session-shell.js"

NONCE_PATTERN = re.compile(r"'nonce-([A-Za-z0-9_-]{43})'")
SCRIPT_TAG_PATTERN = re.compile(r"<script\b([^>]*)>", re.IGNORECASE)
STYLE_TAG_PATTERN = re.compile(r"<style\b([^>]*)>", re.IGNORECASE)
EVENT_HANDLER_PATTERN = re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)


def _policy_nonce(response) -> str:
    policy = response.headers["Content-Security-Policy"]
    matches = NONCE_PATTERN.findall(policy)
    assert len(matches) == 2
    assert len(set(matches)) == 1
    nonce = matches[0]
    assert len(base64.urlsafe_b64decode(nonce + "=")) == 32
    return nonce


def _assert_required_headers(response) -> None:
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["Permissions-Policy"] == (
        "camera=(), geolocation=(), microphone=(), payment=(), usb=()"
    )


def _inline_response_nonces(response) -> list[str]:
    html = response.get_data(as_text=True)
    nonces: list[str] = []
    for attributes in SCRIPT_TAG_PATTERN.findall(html):
        if re.search(r"\bsrc\s*=", attributes, re.IGNORECASE):
            continue
        match = re.search(r'\bnonce="([A-Za-z0-9_-]+)"', attributes)
        assert match is not None
        nonces.append(match.group(1))
    for attributes in STYLE_TAG_PATTERN.findall(html):
        match = re.search(r'\bnonce="([A-Za-z0-9_-]+)"', attributes)
        assert match is not None
        nonces.append(match.group(1))
    return nonces


def test_security_headers_use_exact_default_policy_and_unique_strong_nonces(app, client):
    app.config["APP_ENV"] = "development"
    first = client.get("/sign-in", base_url="http://localhost")
    second = client.get("/sign-in", base_url="http://localhost")

    assert first.status_code == 200
    assert second.status_code == 200
    first_nonce = _policy_nonce(first)
    second_nonce = _policy_nonce(second)
    assert first_nonce != second_nonce
    assert first.headers["Content-Security-Policy"] == build_content_security_policy(first_nonce)
    assert "unsafe-inline" not in first.headers["Content-Security-Policy"].split("script-src", 1)[1].split(";", 1)[0]
    assert "unsafe-eval" not in first.headers["Content-Security-Policy"]
    assert "upgrade-insecure-requests" not in first.headers["Content-Security-Policy"]
    assert "Strict-Transport-Security" not in first.headers
    _assert_required_headers(first)

    rendered_nonces = _inline_response_nonces(first)
    assert len(rendered_nonces) == 2
    assert set(rendered_nonces) == {first_nonce}
    assert f'styleElement.nonce = "{first_nonce}";' in first.get_data(as_text=True)


def test_hsts_and_upgrade_only_apply_to_secure_production_requests(app, client):
    app.config["APP_ENV"] = "development"
    development_https = client.get("/livez", base_url="https://localhost")
    assert "Strict-Transport-Security" not in development_https.headers
    assert "upgrade-insecure-requests" not in development_https.headers["Content-Security-Policy"]

    app.config["APP_ENV"] = "production"
    production_http = client.get("/livez", base_url="http://localhost")
    assert "Strict-Transport-Security" not in production_http.headers
    assert "upgrade-insecure-requests" not in production_http.headers["Content-Security-Policy"]

    production_https = client.get("/livez", base_url="https://localhost")
    nonce = _policy_nonce(production_https)
    assert production_https.headers["Strict-Transport-Security"] == (
        "max-age=31536000; includeSubDomains"
    )
    assert production_https.headers["Content-Security-Policy"] == build_content_security_policy(
        nonce,
        upgrade_insecure_requests=True,
    )
    _assert_required_headers(production_https)


def test_every_inline_template_element_is_nonces_and_no_inline_handlers_remain():
    inline_scripts: list[tuple[Path, str]] = []
    external_scripts: list[tuple[Path, str]] = []
    inline_styles: list[tuple[Path, str]] = []
    event_handlers: list[tuple[Path, str]] = []

    for path in sorted(TEMPLATES_ROOT.glob("*.html")):
        source = path.read_text(encoding="utf-8")
        for tag in re.findall(r"<script\b[^>]*>", source, re.IGNORECASE):
            target = external_scripts if re.search(r"\bsrc\s*=", tag, re.IGNORECASE) else inline_scripts
            target.append((path, tag))
        inline_styles.extend(
            (path, tag)
            for tag in re.findall(r"<style\b[^>]*>", source, re.IGNORECASE)
        )
        event_handlers.extend(
            (path, match.group(0))
            for match in EVENT_HANDLER_PATTERN.finditer(source)
        )

    assert len(inline_scripts) == 15
    assert len({path for path, _ in inline_scripts}) == 14
    assert len(external_scripts) == 4
    assert len(inline_styles) == 1
    assert all('nonce="{{ csp_nonce() }}"' in tag for _, tag in inline_scripts)
    assert all('nonce="{{ csp_nonce() }}"' in tag for _, tag in inline_styles)
    assert event_handlers == []

    base_source = (TEMPLATES_ROOT / "base.html").read_text(encoding="utf-8")
    assert 'document.createElement("style")' in base_source
    assert 'styleElement.nonce = "{{ csp_nonce() }}";' in base_source
    assert not re.search(r"createElement\(\s*['\"]script['\"]", base_source)


def test_session_currency_change_uses_the_existing_external_shell_listener():
    template_source = (TEMPLATES_ROOT / "_session_character_panel.html").read_text(
        encoding="utf-8"
    )
    shell_source = SESSION_SHELL_PATH.read_text(encoding="utf-8")

    assert "onchange=" not in template_source
    assert 'data-session-currency-autosubmit="1"' in template_source
    assert 'characterPane.addEventListener("change"' in shell_source
    assert "[data-session-currency-autosubmit='1']" in shell_source
    assert "field.form.requestSubmit();" in shell_source


def test_auth_token_and_authenticated_html_is_private_no_store(
    app,
    client,
    sign_in,
    users,
):
    for path in ("/sign-in", "/invite/not-a-token", "/reset/not-a-token"):
        response = client.get(path)
        assert response.status_code in {200, 400}
        assert response.headers["Cache-Control"] == "private, no-store"

    public = client.get("/campaigns/linden-pass")
    assert public.status_code == 200
    assert public.headers.get("Cache-Control") != "private, no-store"

    sign_in(users["admin"]["email"], users["admin"]["password"])
    for path in ("/account", "/admin", "/campaigns/linden-pass"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "private, no-store"


def test_disclosure_safe_csrf_error_keeps_security_and_no_store_headers(
    app,
    client,
    sign_in,
    users,
):
    sign_in(users["party"]["email"], users["party"]["password"])
    app.config["CSRF_ENABLED"] = True
    response = client.post("/account/theme", data={"theme_key": "parchment"})

    assert response.status_code == 400
    assert response.headers["Cache-Control"] == "private, no-store"
    assert "Refresh the page and try again." in response.get_data(as_text=True)
    assert "csrf_failed" not in response.get_data(as_text=True)
    _policy_nonce(response)
    _assert_required_headers(response)


def test_only_content_versioned_static_assets_receive_immutable_caching(app, client):
    app.config["APP_ENV"] = "production"
    page = client.get("/sign-in")
    stylesheet_match = re.search(r'href="([^"]*/static/styles\.css\?v=[^"]+)"', page.get_data(as_text=True))
    assert stylesheet_match is not None
    versioned_url = stylesheet_match.group(1)
    version = versioned_url.rsplit("=", 1)[1]

    versioned = client.get(versioned_url)
    assert versioned.status_code == 200
    assert versioned.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    _assert_required_headers(versioned)
    _policy_nonce(versioned)

    nonimmutable_urls = (
        "/static/styles.css",
        "/static/styles.css?v=",
        "/static/styles.css?v=not-the-content-digest",
        f"/static/styles.css?v={version}&v={version}",
        f"/static/styles.css?v={version}&v=malformed",
    )
    for url in nonimmutable_urls:
        response = client.get(url)
        assert response.status_code == 200
        assert "immutable" not in response.headers.get("Cache-Control", "")

    app.config["APP_ENV"] = "development"
    nonproduction = client.get(versioned_url)
    assert nonproduction.status_code == 200
    assert "immutable" not in nonproduction.headers.get("Cache-Control", "")


def test_security_headers_cover_fixed_not_found_responses(client):
    response = client.get("/definitely-not-a-route")
    assert response.status_code == 404
    _policy_nonce(response)
    _assert_required_headers(response)
