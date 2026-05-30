from __future__ import annotations

import re
import threading
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from player_wiki import auth as auth_module


def extract_stylesheet_href(html: str) -> str:
    match = re.search(r'href=\"([^\"]*/static/styles\.css[^\"]*)\"', html)
    assert match is not None
    return match.group(1)


def test_base_template_uses_versioned_stylesheet_url(client):
    response = client.get("/campaigns/linden-pass")
    assert response.status_code == 200

    href = extract_stylesheet_href(response.get_data(as_text=True))
    parsed = urlsplit(href)
    assert parsed.path == "/static/styles.css"

    query = parse_qs(parsed.query or "")
    assert "v" in query
    assert len(query["v"]) == 1
    assert query["v"][0].strip()


def test_versioned_stylesheet_response_uses_production_immutable_cache_headers(app, client):
    app.config["APP_ENV"] = "production"

    response = client.get("/campaigns/linden-pass")
    href = extract_stylesheet_href(response.get_data(as_text=True))
    css_response = client.get(href)
    assert css_response.status_code == 200

    cache_control = css_response.headers.get("Cache-Control", "")
    assert "public" in cache_control
    assert "max-age=31536000" in cache_control
    assert "immutable" in cache_control
    assert "no-cache" not in cache_control

    vary_header = (css_response.headers.get("Vary") or "").lower()
    assert "cookie" not in vary_header


def test_stylesheet_static_requests_bypass_request_identity(monkeypatch, client):
    call_count = {"count": 0}

    original_get_auth_store = auth_module.get_auth_store

    def tracking_get_auth_store():
        call_count["count"] += 1
        return original_get_auth_store()

    monkeypatch.setattr(auth_module, "get_auth_store", tracking_get_auth_store)

    page_response = client.get("/campaigns/linden-pass")
    assert page_response.status_code == 200
    assert call_count["count"] > 0
    page_request_count = call_count["count"]

    stylesheet_response = client.get("/static/styles.css?v=audittest")
    assert stylesheet_response.status_code == 200

    assert call_count["count"] == page_request_count
    vary_header = (stylesheet_response.headers.get("Vary") or "").lower()
    assert "cookie" not in vary_header


@pytest.fixture
def static_asset_live_server(app):
    from werkzeug.serving import make_server

    app.config["APP_ENV"] = "production"
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_browser_loads_styled_shell_through_versioned_stylesheet(static_asset_live_server):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            def delay_stylesheet(route):
                time.sleep(0.25)
                route.continue_()

            page.route("**/static/styles.css**", delay_stylesheet)
            page.goto(f"{static_asset_live_server}/campaigns/linden-pass", wait_until="load")
            expect(page.locator(".page-shell")).to_be_visible(timeout=5000)

            resource_urls = page.evaluate(
                "Array.from(performance.getEntriesByType('resource')).map((entry) => entry.name)"
            )
            stylesheet_urls = [
                url for url in resource_urls if "/static/styles.css" in str(url)
            ]
            assert stylesheet_urls
            assert all("?v=" in url for url in stylesheet_urls)

            assert page.evaluate("getComputedStyle(document.body).marginTop") == "0px"
            assert page.evaluate("getComputedStyle(document.documentElement).backgroundImage") != "none"
            paint_timing = page.evaluate(
                """() => {
                    const cssEntry = performance
                        .getEntriesByType('resource')
                        .find((entry) => entry.name.includes('/static/styles.css'));
                    const fcpEntry = performance
                        .getEntriesByType('paint')
                        .find((entry) => entry.name === 'first-contentful-paint');
                    return {
                        cssResponseEnd: cssEntry ? cssEntry.responseEnd : 0,
                        firstContentfulPaint: fcpEntry ? fcpEntry.startTime : 0,
                    };
                }"""
            )
            assert paint_timing["cssResponseEnd"] > 0
            assert paint_timing["firstContentfulPaint"] > 0
            assert paint_timing["firstContentfulPaint"] >= paint_timing["cssResponseEnd"] - 1
        finally:
            page.close()
            browser.close()
