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


def test_base_template_includes_inline_loading_bootstrap_and_cover(client):
    response = client.get("/campaigns/linden-pass")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'id="app-loading-inline-styles"' in html
    assert ".app-loading-cover" in html
    assert 'id="app-loading-inline-script"' in html
    assert "requestAnimationFrame" in html
    assert "setTimeout" in html
    assert "failOpenDelayMs = 12000" in html
    assert "addEventListener" in html
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html

    html_opening_tag = re.search(r"<html[^>]*>", html)
    assert html_opening_tag is not None
    assert "app-loading" not in html_opening_tag.group(0)
    assert "cpw:app-loading-nav-start" in html
    assert "app-loading-closing" in html
    assert "prefers-reduced-motion" in html


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


def test_browser_shows_loading_cover_while_stylesheet_streams(static_asset_live_server):
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
                time.sleep(4.5)
                route.continue_()

            page.route("**/static/styles.css**", delay_stylesheet)

            page.goto(
                f"{static_asset_live_server}/campaigns/linden-pass",
                wait_until="commit",
            )

            page.wait_for_timeout(3500)
            loading_snapshot_during_delay = page.evaluate(
                """() => {
                    const cover = document.querySelector('.app-loading-cover');
                    return {
                      hasLoadingClass: document.documentElement.classList.contains('app-loading'),
                      coverOpacity: cover ? getComputedStyle(cover).opacity : null,
                      pageShellOpacity: getComputedStyle(document.querySelector('.page-shell')).opacity,
                      pageShellVisibility: getComputedStyle(document.querySelector('.page-shell')).visibility,
                    };
                }"""
            )
            assert loading_snapshot_during_delay["hasLoadingClass"] is True
            assert loading_snapshot_during_delay["coverOpacity"] == "1"
            assert loading_snapshot_during_delay["pageShellOpacity"] == "0"
            assert loading_snapshot_during_delay["pageShellVisibility"] == "hidden"

            page.wait_for_load_state("load", timeout=12000)

            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=5000)
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
            if paint_timing["firstContentfulPaint"] > 0:
                assert paint_timing["firstContentfulPaint"] >= paint_timing["cssResponseEnd"] - 1
        finally:
            page.close()
            browser.close()


def _measure_loading_hide_ms(page):
    return page.evaluate(
        """() => {
            const startMarker = Number(sessionStorage.getItem("cpw-test-nav-start") || 0);
            return new Promise((resolve) => {
              if (!startMarker) {
                resolve(-1);
                return;
              }
              let deadlineMs = 5000;
              const check = () => {
                if (!document.documentElement.classList.contains("app-loading")) {
                  resolve(Date.now() - startMarker);
                  return;
                }
                if (deadlineMs <= 0) {
                  resolve(-1);
                  return;
                }
                deadlineMs -= 32;
                window.setTimeout(check, 16);
              };
              check();
            });
        }"""
    )


def test_browser_navigation_feedback_short_minimum_duration(static_asset_live_server):
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
            page.route("**/static/styles.css**", lambda route: route.continue_())

            page.goto(
                f"{static_asset_live_server}/campaigns/linden-pass",
                wait_until="load",
            )
            page.wait_for_timeout(150)

            page.evaluate(
                """
                () => {
                  sessionStorage.setItem("cpw-test-nav-start", String(Date.now()));
                  const link = document.createElement("a");
                  link.href = "/campaigns/linden-pass?app-loading-nav-check=1";
                  link.id = "app-nav-feedback-check";
                  link.textContent = "Characters";
                  link.style.position = "relative";
                  document.body.appendChild(link);
                }
                """
            )

            nav_link = page.locator("#app-nav-feedback-check")
            nav_link.click()
            page.wait_for_function(
                "document.documentElement.classList.contains('app-loading')"
            )

            assert page.evaluate("document.documentElement.classList.contains('app-loading')")
            page.wait_for_timeout(50)
            assert page.evaluate("document.documentElement.classList.contains('app-loading')")

            hide_ms = _measure_loading_hide_ms(page)
            assert hide_ms >= 0
            assert hide_ms >= 170
            expect(page.locator("html")).not_to_have_class("app-loading", timeout=5000)
            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=5000)
            expect(page.locator(".page-shell")).to_be_visible(timeout=5000)
        finally:
            page.close()
            browser.close()


def test_browser_navigation_feedback_form_submit_shows_loader(static_asset_live_server):
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
            page.route("**/static/styles.css**", lambda route: route.continue_())

            page.goto(
                f"{static_asset_live_server}/campaigns/linden-pass",
                wait_until="load",
            )
            page.wait_for_timeout(150)

            page.evaluate(
                """
                () => {
                  sessionStorage.setItem("cpw-test-nav-start", String(Date.now()));
                  const form = document.createElement("form");
                  form.id = "app-nav-feedback-form";
                  form.method = "get";
                  form.action = "/campaigns/linden-pass?app-loading-form-check=1";
                  const submitButton = document.createElement("button");
                  submitButton.type = "submit";
                  submitButton.id = "app-nav-feedback-form-submit";
                  submitButton.textContent = "Submit";
                  form.appendChild(submitButton);
                  document.body.appendChild(form);
                }
                """
            )

            page.locator("#app-nav-feedback-form-submit").click()
            page.wait_for_function(
                "document.documentElement.classList.contains('app-loading')"
            )

            assert page.evaluate("document.documentElement.classList.contains('app-loading')")
            hide_ms = _measure_loading_hide_ms(page)
            assert hide_ms >= 0
            assert hide_ms >= 170
            expect(page.locator("html")).not_to_have_class("app-loading", timeout=5000)
            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=5000)
            expect(page.locator(".page-shell")).to_be_visible(timeout=5000)
        finally:
            page.close()
            browser.close()


def test_browser_navigation_feedback_exclusions_dont_show_loader(static_asset_live_server):
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page.goto(
                f"{static_asset_live_server}/campaigns/linden-pass",
                wait_until="load",
            )
            page.wait_for_timeout(150)

            page.evaluate(
                """
                () => {
                  const target = document.createElement("a");
                  target.href = "/campaigns/linden-pass?app-loading-nav-check=1";
                  target.textContent = "Characters";
                  target.id = "same-doc-exclude";
                  document.body.appendChild(target);

                  const hashTarget = document.createElement("a");
                  hashTarget.href = "#app-loading-test-hash";
                  hashTarget.textContent = "Hash jump";
                  hashTarget.id = "hash-only-exclude";
                  document.body.appendChild(hashTarget);

                  const section = document.createElement("section");
                  section.id = "app-loading-test-hash";
                  document.body.appendChild(section);

                  sessionStorage.removeItem("cpw:app-loading-nav-start");
                  sessionStorage.removeItem("cpw-test-nav-start");
                }
                """
            )

            page.evaluate(
                """
                () => {
                  const target = document.querySelector("#same-doc-exclude");
                  const clickEvent = new MouseEvent("click", {
                    bubbles: true,
                    cancelable: true,
                    button: 0,
                    ctrlKey: true,
                  });
                  target.dispatchEvent(clickEvent);
                }
                """
            )
            page.wait_for_timeout(150)
            assert not page.evaluate("document.documentElement.classList.contains('app-loading')")
            assert (
                page.evaluate("sessionStorage.getItem('cpw:app-loading-nav-start')") is None
            )

            page.locator("#hash-only-exclude").click()
            page.wait_for_timeout(120)
            assert page.url.endswith("#app-loading-test-hash")
            assert not page.evaluate("document.documentElement.classList.contains('app-loading')")
            assert (
                page.evaluate("sessionStorage.getItem('cpw:app-loading-nav-start')") is None
            )
        finally:
            page.close()
            browser.close()
