from __future__ import annotations

import json
from datetime import date
import re
import threading
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from player_wiki import auth as auth_module
from player_wiki.loading_presenter import (
    select_campaign_loading_image_url,
    select_campaign_loading_image_urls,
)
from player_wiki.models import Campaign, Page


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
    assert ".app-loading-cover__media" in html
    assert "app-loading-cover__message" in html
    assert "root.classList.contains(loadingClass) && cover.classList.contains(\"app-loading-cover--media-ready\")" in html
    assert "--app-loading-bg" in html
    assert "Loading campaign player wiki..." in html


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


def test_base_template_uses_loading_image_for_campaign_when_available(client):
    response = client.get("/campaigns/linden-pass")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'app-loading-cover--with-image' in html
    assert 'app-loading-cover--media-ready' in html
    assert 'data-app-loading-media-urls=' in html
    assert 'data-app-loading-media-url="/campaigns/linden-pass/assets/' in html
    assert "style='--app-loading-media: url(\"/campaigns/linden-pass/assets/" in html
    assert "force-cache" in html
    assert "background-size: contain" in html


def test_base_template_no_loading_image_for_global_routes(client):
    response = client.get("/sign-in")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'app-loading-cover--with-image' not in html
    cover_match = re.search(r'<div class="app-loading-cover[^"]*"', html)
    assert cover_match is not None
    assert cover_match.group(0) == '<div class="app-loading-cover"'


def test_base_template_has_theme_scoped_palette_for_loading_cover(client):
    response = client.get("/campaigns/linden-pass")
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    bg, ink, accent, _ = _loading_theme_palette("parchment")
    assert 'html[data-theme="parchment"]' in html
    assert f"--app-loading-bg: {bg};" in html
    assert f"--app-loading-ink: {ink};" in html
    assert f"--app-loading-accent: {accent};" in html


def _loading_theme_palette(theme_key: str) -> tuple[str, str, str, str]:
    themes = {
        "parchment": ("#efe2c5", "#2f241a", "#8c4f31", "0.16"),
        "moonlit": ("#172331", "#eaf1ff", "#d4b16f", "0.18"),
        "verdant": ("#dfe9db", "#233126", "#4a7e60", "0.16"),
        "ember": ("#f0d3bc", "#351d18", "#a34c31", "0.14"),
    }
    return themes[theme_key]


def _extract_loading_media_urls(html: str) -> list[str]:
    match = re.search(r"data-app-loading-media-urls='([^']*)'", html)
    if not match:
        return []
    raw_urls = match.group(1)
    try:
        parsed_urls = json.loads(raw_urls)
    except Exception:
        return []
    if not isinstance(parsed_urls, list):
        return []
    return [url for url in parsed_urls if isinstance(url, str)]


def _extract_loading_media_url(html: str) -> str | None:
    urls = _extract_loading_media_urls(html)
    if not urls:
        return None
    return urls[0]


def _sign_in_in_browser(page, base_url: str, email: str, password: str):
    page.goto(f"{base_url}/sign-in", wait_until="load")
    page.wait_for_selector("input[name='email']")
    page.fill("input[name='email']", email)
    page.fill("input[name='password']", password)
    page.click("button[type='submit']")
    page.wait_for_load_state("load")


def _set_browser_theme(page, base_url: str, theme_key: str):
    page.goto(f"{base_url}/account", wait_until="load")
    status = page.evaluate(
        """async (themeKey) => {
            const body = new URLSearchParams();
            body.set("theme_key", themeKey);
            const response = await fetch("/account/theme", {
              method: "POST",
              body,
              credentials: "same-origin",
            });
            return response.status;
        }""",
        theme_key,
    )
    assert status == 200


def _build_loading_presenter_campaign() -> Campaign:
    return Campaign(
        title="Loading Image Unit Test",
        slug="loading-images",
        summary="Unit fixture for loading image selection.",
        system="DND-5E",
        current_session=2,
        source_wiki_root="",
        player_content_dir="",
        assets_dir="",
        pages={},
    )


def test_select_campaign_loading_image_urls_filters_missing_and_ineligible_paths():
    campaign = _build_loading_presenter_campaign()
    campaign.pages = {
        "visible-valid": Page(
            title="Captain",
            route_slug="captain",
            source_path="",
            body_markdown="",
            section="NPCs",
            page_type="npc",
            image_path="npcs/captain.png",
        ),
        "visible-unpublished": Page(
            title="Hidden",
            route_slug="hidden",
            source_path="",
            body_markdown="",
            section="NPCs",
            page_type="npc",
            published=False,
            image_path="images/hidden.png",
        ),
        "visible-traversal": Page(
            title="Traversal",
            route_slug="traversal",
            source_path="",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="../outside/secret.png",
        ),
        "visible-external": Page(
            title="External",
            route_slug="external",
            source_path="",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="https://example.com/artwork.png",
        ),
        "visible-missing": Page(
            title="Missing",
            route_slug="missing",
            source_path="",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="missing/no-file.png",
        ),
        "global-page": Page(
            title="Global",
            route_slug="global-page",
            source_path="global/events/overview",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="npcs/global.png",
        ),
    }

    image_urls = select_campaign_loading_image_urls(
        campaign,
        can_access_wiki=True,
        image_exists=lambda _, image_path: image_path == "npcs/captain.png",
        build_image_url=lambda _, image_path: f"/campaigns/loading-images/assets/{image_path}",
        selection_seed="loading-unit-test",
        selection_date=date(2026, 5, 30),
        max_loading_images=4,
    )
    assert image_urls == ["/campaigns/loading-images/assets/npcs/captain.png"]


def test_select_campaign_loading_image_urls_limit_and_stable_for_same_day():
    campaign = _build_loading_presenter_campaign()
    campaign.pages = {
        "first": Page(
            title="First",
            route_slug="first",
            source_path="content/first.md",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="npcs/first.png",
        ),
        "second": Page(
            title="Second",
            route_slug="second",
            source_path="content/second.md",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="npcs/second.png",
        ),
        "third": Page(
            title="Third",
            route_slug="third",
            source_path="content/third.md",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="npcs/third.png",
        ),
        "fourth": Page(
            title="Fourth",
            route_slug="fourth",
            source_path="content/fourth.md",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="npcs/fourth.png",
        ),
    }

    select_kwargs = {
        "can_access_wiki": True,
        "image_exists": lambda *_args: True,
        "build_image_url": lambda _, image_path: f"/campaigns/loading-images/assets/{image_path}",
        "selection_seed": "loading-unit-test",
        "selection_date": date(2026, 5, 30),
    }
    first_result = select_campaign_loading_image_urls(
        campaign,
        **select_kwargs,
        max_loading_images=3,
    )
    second_result = select_campaign_loading_image_urls(
        campaign,
        **select_kwargs,
        max_loading_images=3,
    )
    assert len(first_result) == 3
    assert first_result == second_result


def test_select_campaign_loading_image_urls_falls_back_when_no_candidates():
    campaign = _build_loading_presenter_campaign()
    campaign.pages = {
        "missing-one": Page(
            title="Missing",
            route_slug="missing",
            source_path="",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="missing/no-file.png",
        )
    }

    image_urls = select_campaign_loading_image_urls(
        campaign,
        can_access_wiki=True,
        image_exists=lambda *_args: False,
        build_image_url=lambda _, image_path: f"/campaigns/loading-images/assets/{image_path}",
        selection_seed="loading-unit-test",
        selection_date=date(2026, 5, 30),
    )
    assert image_urls == []


def test_select_campaign_loading_image_url_wraps_list_wrapper():
    campaign = _build_loading_presenter_campaign()
    campaign.pages = {
        "single": Page(
            title="Single",
            route_slug="single",
            source_path="",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="npcs/captain.png",
        )
    }

    image_url = select_campaign_loading_image_url(
        campaign,
        can_access_wiki=True,
        image_exists=lambda *_args: True,
        build_image_url=lambda _, image_path: f"/campaigns/loading-images/assets/{image_path}",
        selection_seed="loading-unit-test",
        selection_date=date(2026, 5, 30),
        max_scanned_pages=4,
    )
    assert image_url == "/campaigns/loading-images/assets/npcs/captain.png"


def test_select_campaign_loading_image_url_stable_for_same_day():
    campaign = _build_loading_presenter_campaign()
    campaign.pages = {
        "first": Page(
            title="First",
            route_slug="first",
            source_path="",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="npcs/captain.png",
        ),
        "second": Page(
            title="Second",
            route_slug="second",
            source_path="",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="lore/map.png",
        ),
    }

    image_url = lambda: select_campaign_loading_image_url(
        campaign,
        can_access_wiki=True,
        image_exists=lambda _, image_path: True,
        build_image_url=lambda _, image_path: f"/campaigns/loading-images/assets/{image_path}",
        selection_date=date(2026, 5, 30),
    )
    assert image_url() == image_url()


def test_select_campaign_loading_image_url_blocks_inaccessible_campaign_content():
    campaign = _build_loading_presenter_campaign()
    campaign.pages = {
        "visible": Page(
            title="Locked Page",
            route_slug="locked",
            source_path="",
            body_markdown="",
            section="Lore",
            page_type="page",
            image_path="npcs/captain.png",
        ),
    }

    image_url = select_campaign_loading_image_url(
        campaign,
        can_access_wiki=False,
        image_exists=lambda *_args: True,
        build_image_url=lambda _, image_path: f"/campaigns/loading-images/assets/{image_path}",
    )
    assert image_url is None


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


def _set_viewport_for_theme_checks(page, is_mobile: bool):
    if is_mobile:
        page.set_viewport_size({"width": 390, "height": 844})
    else:
        page.set_viewport_size({"width": 1280, "height": 900})


@pytest.mark.parametrize("theme_key", ["parchment", "moonlit", "verdant", "ember"])
@pytest.mark.parametrize("is_mobile", [False, True])
def test_browser_loading_palette_for_themes_during_delayed_stylesheet(
    static_asset_live_server,
    users,
    theme_key,
    is_mobile,
):
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
            _set_viewport_for_theme_checks(page, is_mobile)
            _sign_in_in_browser(
                page,
                static_asset_live_server,
                users["party"]["email"],
                users["party"]["password"],
            )
            _set_browser_theme(page, static_asset_live_server, theme_key)

            expected_bg, expected_ink, expected_accent, expected_media_opacity = _loading_theme_palette(theme_key)

            def delay_stylesheet(route):
                time.sleep(1.2)
                route.continue_()

            page.route("**/static/styles.css**", delay_stylesheet)
            page.goto(f"{static_asset_live_server}/campaigns/linden-pass", wait_until="commit")
            page.wait_for_timeout(450)

            palette = page.evaluate(
                """() => {
                    const root = document.documentElement;
                    const cover = document.querySelector('.app-loading-cover');
                    return {
                      background: getComputedStyle(root).getPropertyValue('--app-loading-bg').trim(),
                      ink: getComputedStyle(root).getPropertyValue('--app-loading-ink').trim(),
                      accent: getComputedStyle(root).getPropertyValue('--app-loading-accent').trim(),
                      mediaOpacity: getComputedStyle(root).getPropertyValue('--app-loading-media-opacity').trim(),
                      hasLoadingClass: root.classList.contains('app-loading'),
                      coverOpacity: getComputedStyle(cover).opacity,
                      pageShellOpacity: getComputedStyle(document.querySelector('.page-shell')).opacity,
                    };
                }"""
            )
            assert palette["hasLoadingClass"] is True
            assert palette["coverOpacity"] == "1"
            assert palette["pageShellOpacity"] == "0"
            assert palette["background"] == expected_bg
            assert palette["ink"] == expected_ink
            assert palette["accent"] == expected_accent
            assert palette["mediaOpacity"] == expected_media_opacity

            page.unroute("**/static/styles.css**")
            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=5000)
            expect(page.locator(".page-shell")).to_be_visible(timeout=5000)
        finally:
            page.close()
            browser.close()


def test_browser_loading_cover_dismisses_when_cover_image_is_blocked(static_asset_live_server):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            baseline_response = page.goto(
                f"{static_asset_live_server}/campaigns/linden-pass",
                wait_until="load",
            )
            assert baseline_response is not None
            assert baseline_response.status == 200
            media_urls = _extract_loading_media_urls(baseline_response.text())
            assert media_urls
            page.wait_for_timeout(150)

            def block_loading_media(route):
                request_path = urlsplit(route.request.url).path
                for media_url in media_urls:
                    if request_path == urlsplit(media_url).path:
                        route.abort()
                        return
                route.continue_()

            page.route("**", block_loading_media)

            start_time = time.perf_counter()
            page.goto(f"{static_asset_live_server}/campaigns/linden-pass", wait_until="commit")
            page.wait_for_function(
                "document.documentElement.classList.contains('app-loading')",
                timeout=2000,
            )
            page.wait_for_function(
                "!document.documentElement.classList.contains('app-loading')",
                timeout=5000,
            )
            hide_ms = (time.perf_counter() - start_time) * 1000

            assert hide_ms < 2500
            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=2000)
            expect(page.locator(".page-shell")).to_be_visible(timeout=2000)
        finally:
            page.close()
            browser.close()


def test_browser_loading_media_rotation_advances_between_navigation(static_asset_live_server):
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
            page.goto(f"{static_asset_live_server}/campaigns/linden-pass", wait_until="load")
            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=5000)

            media_urls = _extract_loading_media_urls(page.content())
            if len(media_urls) < 2:
                pytest.skip("insufficient loading media candidates for rotation test")

            start_index = page.evaluate(
                "Number(sessionStorage.getItem('cpw:app-loading-media-index') || 0)"
            )

            page.evaluate(
                """
                () => {
                  const link = document.createElement('a');
                  link.id = 'app-loading-rotation-link';
                  link.href = '/campaigns/linden-pass/overview';
                  link.textContent = 'overview';
                  link.style.position = 'relative';
                  document.body.appendChild(link);
                }
                """
            )
            page.locator("#app-loading-rotation-link").click()

            expect(page.locator(".app-loading-cover")).to_be_visible(timeout=5000)
            expect(page.locator(".app-loading-cover")).to_be_hidden(timeout=7000)

            end_index = page.evaluate(
                "Number(sessionStorage.getItem('cpw:app-loading-media-index') || 0)"
            )
            assert start_index != end_index
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
