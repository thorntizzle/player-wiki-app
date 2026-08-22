from tests.helpers.character_state_helpers import (
    _read_character_definition,
    _write_character_definition,
    _write_character_state,
)
import re
import threading
import time
from copy import deepcopy
from types import SimpleNamespace

import player_wiki.app as app_module
import pytest
import yaml
from player_wiki.auth_store import AuthStore
from player_wiki.campaign_session_service import CampaignSessionValidationError
from tests.helpers.character_builder_fakes import (
    _builder_context_fixture,
    _level_up_context_fixture,
    _minimal_character_definition,
    _minimal_import_metadata,
)
from tests.helpers.systems_seed_helpers import (
    _seed_systems_item_entry,
    _seed_systems_spell_entry,
    _systems_ref,
)
from tests.helpers.xianxia_character_helpers import (
    _configure_xianxia_campaign,
    _valid_xianxia_create_data,
)


@pytest.fixture
def character_read_shell_live_server(app):
    from werkzeug.serving import make_server

    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        yield base_url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _check_no_horizontal_overflow(page, selector: str, viewport_name: str, *, required: bool) -> None:
    measurements = page.evaluate(
        """(selector) => {
            const element = document.querySelector(selector);
            if (!element) {
                return { selector, missing: true };
            }

            const rect = element.getBoundingClientRect();
            return {
                selector,
                missing: false,
                left: rect.left,
                right: rect.right,
                clientWidth: element.clientWidth,
                scrollWidth: element.scrollWidth,
            };
        }""",
        selector,
    )

    if required:
        assert not measurements["missing"], f"{viewport_name}: missing {selector}"
    elif measurements["missing"]:
        return

    assert measurements["left"] >= -1, f"{viewport_name}: {selector} starts before viewport start"
    assert measurements["right"] <= page.viewport_size["width"] + 1, (
        f"{viewport_name}: {selector} overflows to the right"
    )
    assert measurements["scrollWidth"] <= measurements["clientWidth"] + 1, (
        f"{viewport_name}: {selector} content does not fit its container"
    )


def _assert_character_read_no_overflow(page, viewport_name: str) -> None:
    required_selectors = [
        ".page-shell",
        "[data-character-read-shell-root]",
        ".character-sheet",
        ".character-header",
        ".character-subpage-nav-card",
        ".character-subpage-nav",
        ".character-header__identity h1",
    ]
    optional_selectors = [
        ".glance-grid--quick-row-3",
        ".resource-grid--compact",
        ".spell-slot-editor-list--compact",
        ".spell-card-grid",
        ".detail-grid",
        ".ability-grid--skills",
    ]

    document_width = page.evaluate(
        """() => {
            const root = document.scrollingElement || document.documentElement;
            return root.scrollWidth;
        }"""
    )
    assert document_width <= page.viewport_size["width"] + 2, (
        f"{viewport_name}: document overflows horizontally ({document_width} > {page.viewport_size['width']})"
    )

    for selector in required_selectors:
        _check_no_horizontal_overflow(page, selector, viewport_name, required=True)
    for selector in optional_selectors:
        _check_no_horizontal_overflow(page, selector, viewport_name, required=False)


def _set_overflow_test_character_name(page) -> None:
    page.locator(".character-header__identity h1").evaluate(
        """(element, value) => {
            element.textContent = value;
            element.title = value;
        }""",
        "Zigzag Blackscar With an Extremely Long Sheet Name for Overflow Testing",
    )


def _wait_for_app_loading_cover(page) -> None:
    from playwright.sync_api import expect

    expect(page.locator("html.app-loading, html.app-loading-closing")).to_have_count(
        0,
        timeout=5000,
    )


def _sign_in_browser(page, base_url: str, user) -> None:
    page.goto(f"{base_url}/sign-in")
    page.locator("input[name='email']").fill(user["email"])
    page.locator("input[name='password']").fill(user["password"])
    page.locator("button[type='submit']").click()
    page.wait_for_url(re.compile(rf"^{re.escape(base_url)}/.*"), timeout=5000)


def _write_leveler_fixture(app) -> None:
    character_dir = app.config["TEST_CAMPAIGNS_DIR"] / "linden-pass" / "characters" / "leveler"
    character_dir.mkdir(parents=True, exist_ok=True)
    definition = _minimal_character_definition("leveler", "Leveler")
    import_metadata = _minimal_import_metadata("leveler")
    (character_dir / "definition.yaml").write_text(yaml.safe_dump(definition.to_dict(), sort_keys=False), encoding="utf-8")
    (character_dir / "import.yaml").write_text(yaml.safe_dump(import_metadata.to_dict(), sort_keys=False), encoding="utf-8")


def _scroll_y(page) -> float:
    return float(page.evaluate("window.scrollY"))


@pytest.mark.parametrize(
    ("viewport_name", "viewport"),
    (
        ("desktop", {"width": 1280, "height": 900}),
        ("mobile", {"width": 390, "height": 800}),
    ),
)
def test_character_read_subpage_switch_has_local_busy_state_and_cancels_superseded_read(
    users,
    character_read_shell_live_server,
    viewport_name,
    viewport,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    delayed_fetch_script = """() => {
        window.__characterReadOriginalFetch = window.__characterReadOriginalFetch || window.fetch.bind(window);
        window.fetch = (url, options = {}) => new Promise((resolve, reject) => {
          const signal = options.signal;
          const abort = () => reject(new DOMException("Aborted", "AbortError"));
          if (signal && signal.aborted) {
            abort();
            return;
          }
          if (signal) {
            signal.addEventListener("abort", abort, { once: true });
          }
          window.__releaseCharacterReadFetch = () => {
            if (signal) {
              signal.removeEventListener("abort", abort);
            }
            window.__characterReadOriginalFetch(url, options).then(resolve, reject);
          };
        });
      }"""

    base_url = character_read_shell_live_server
    character_url = f"{base_url}/campaigns/linden-pass/characters/arden-march"
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport=viewport)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["dm"])
            page.goto(f"{character_url}?page=quick")
            _wait_for_app_loading_cover(page)
            loading = page.locator("[data-character-read-shell-loading]")
            shell = page.locator("[data-character-read-shell-root]")

            page.evaluate(delayed_fetch_script)
            page.locator("[data-character-read-target-subpage='inventory']").click()
            expect(loading).to_be_visible(timeout=2000)
            expect(shell).to_have_attribute("aria-busy", "true")
            expect(loading).to_contain_text("Loading Inventory")
            expect(
                page.locator("[data-character-read-target-subpage='inventory']")
            ).to_have_attribute("data-character-read-pending", "true")
            expect(page.locator("html.app-loading, html.app-loading-closing")).to_have_count(0)

            page.evaluate("window.__releaseCharacterReadFetch()")
            expect(page).to_have_url(re.compile(r"[?&]page=inventory(?:&|$)"), timeout=5000)
            expect(loading).to_be_hidden(timeout=5000)
            expect(shell).not_to_have_attribute("aria-busy", "true")
            expect(page.locator("[data-character-read-pending]")).to_have_count(0)

            page.evaluate(delayed_fetch_script)
            page.locator("[data-character-read-target-subpage='features']").click()
            expect(loading).to_be_visible(timeout=2000)
            page.locator("[data-character-read-target-subpage='quick']").click()
            expect(page).to_have_url(re.compile(r"[?&]page=quick(?:&|$)"), timeout=2000)
            expect(loading).to_be_hidden(timeout=2000)
            expect(shell).not_to_have_attribute("aria-busy", "true")
            expect(page.locator("[data-character-read-pending]")).to_have_count(0)
            expect(page.locator("html.app-loading, html.app-loading-closing")).to_have_count(0)
            _assert_character_read_no_overflow(page, viewport_name)
        finally:
            page.close()
            browser.close()


def test_character_read_abort_during_fresh_mount_settlement_rolls_back_before_failed_successor(
    users,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = character_read_shell_live_server
    character_url = f"{base_url}/campaigns/linden-pass/characters/arden-march"
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        features_gets = 0

        def count_features_gets(request):
            nonlocal features_gets
            if (
                request.method == "GET"
                and "/campaigns/linden-pass/characters/arden-march" in request.url
                and "page=features" in request.url
            ):
                features_gets += 1

        page.on("request", count_features_gets)
        page.route(
            re.compile(r"/campaigns/linden-pass/characters/arden-march\?page=personal$"),
            lambda route: route.fulfill(
                status=503,
                content_type="text/html",
                headers={"Retry-After": "2", "Cache-Control": "no-store"},
                body="<h1>Character pages are busy</h1>",
            ),
        )
        try:
            _sign_in_browser(page, base_url, users["dm"])
            page.goto(f"{character_url}?page=quick")
            _wait_for_app_loading_cover(page)
            expect(page.locator("h2:has-text('At a glance')")).to_be_visible()
            page.evaluate(
                """() => {
                  const panel = document.querySelector("[data-character-read-shell-panel]");
                  const header = panel.querySelector(".character-header");
                  const navCard = panel.querySelector("[data-character-subpage-nav-card]");
                  const nav = navCard.querySelector(".character-subpage-nav");
                  const navLinks = Array.from(
                    nav.querySelectorAll("[data-character-read-subpage-link]"),
                  );
                  window.__committedQuickSection = panel.querySelector(
                    "[data-character-read-section-content]",
                  );
                  window.__committedQuickChrome = {
                    header,
                    navCard,
                    nav,
                    headerOuter: header.outerHTML,
                    navCardOuter: navCard.outerHTML,
                    navLinks: new Map(navLinks.map((link) => [
                      link.dataset.characterReadTargetSubpage,
                      link,
                    ])),
                    order: navLinks.map((link) => link.dataset.characterReadTargetSubpage),
                  };
                  const originalFetch = window.fetch.bind(window);
                  window.fetch = async (url, options = {}) => {
                    const response = await originalFetch(url, options);
                    const method = String(options.method || "GET").toUpperCase();
                    if (method !== "GET" || !String(url).includes("page=features")) {
                      return response;
                    }
                    const responseDocument = new DOMParser().parseFromString(
                      await response.text(),
                      "text/html",
                    );
                    const responseHeader = responseDocument.querySelector(".character-header");
                    responseHeader.dataset.interruptedFreshHeader = "yes";
                    responseHeader.querySelector("h1").textContent = "Interrupted Fresh Features";
                    const responseNavCard = responseDocument.querySelector(
                      "[data-character-subpage-nav-card]",
                    );
                    responseNavCard.dataset.interruptedFreshNavCard = "yes";
                    const responseNav = responseNavCard.querySelector(".character-subpage-nav");
                    responseNav.setAttribute("aria-label", "Interrupted fresh character sections");
                    const inventory = responseNav.querySelector(
                      "[data-character-read-target-subpage='inventory']",
                    );
                    inventory.textContent = "Interrupted carried inventory";
                    inventory.href = `${window.location.pathname}?page=inventory#interrupted`;
                    inventory.dataset.interruptedFreshLink = "yes";
                    responseNav.prepend(inventory);
                    responseNav.querySelector(
                      "[data-character-read-target-subpage='controls']",
                    ).remove();
                    const extra = responseDocument.createElement("a");
                    extra.className = "ghost-button";
                    extra.href = `${window.location.pathname}?page=interrupted-extra`;
                    extra.dataset.characterReadSubpageLink = "";
                    extra.dataset.characterReadTargetSubpage = "interrupted-extra";
                    extra.textContent = "Interrupted extra";
                    responseNav.append(extra);
                    const replacement = new Response(
                      `<!doctype html>${responseDocument.documentElement.outerHTML}`,
                      {
                        status: response.status,
                        statusText: response.statusText,
                        headers: response.headers,
                      },
                    );
                    return new Proxy(replacement, {
                      get(target, property) {
                        if (property === "url") {
                          return response.url;
                        }
                        if (property === "redirected") {
                          return response.redirected;
                        }
                        const value = Reflect.get(target, property, target);
                        return typeof value === "function" ? value.bind(target) : value;
                      },
                    });
                  };
                  window.__abortDuringSettlementTriggered = false;
                  window.__abortedFeatureSection = null;
                  const observer = new MutationObserver((records) => {
                    if (window.__abortDuringSettlementTriggered) {
                      return;
                    }
                    const section = records.flatMap((record) => Array.from(record.addedNodes))
                      .find((node) => (
                        node instanceof HTMLElement
                        && node.matches("[data-character-read-section-content]")
                      ));
                    if (!(section instanceof HTMLElement)) {
                      return;
                    }
                    window.__abortDuringSettlementTriggered = true;
                    window.__abortedFeatureSection = section;
                    observer.disconnect();
                    panel.querySelector(
                      "[data-character-read-target-subpage='personal']",
                    ).click();
                  });
                  observer.observe(panel, { childList: true });
                }"""
            )

            page.locator("[data-character-read-target-subpage='features']").click()
            page.wait_for_function("() => window.__abortDuringSettlementTriggered === true")
            expect(page.locator("h2:has-text('At a glance')")).to_be_visible(timeout=5000)
            expect(page.locator("[data-character-read-shell-root]")).to_have_attribute(
                "data-character-read-shell-page",
                "quick",
            )
            expect(page).to_have_url(re.compile(r"[?&]page=quick(?:&|$)"))
            expect(page.locator("[data-character-read-shell-loading]")).to_contain_text(
                "Character pages are busy",
                timeout=5000,
            )
            assert features_gets == 1
            cache_state = page.evaluate(
                """() => {
                  const cache = window.__playerWikiCharacterReadShell.cache;
                  const quickKey = `${window.location.pathname}?page=quick`;
                  const featuresKey = `${window.location.pathname}?page=features`;
                  const personalKey = `${window.location.pathname}?page=personal`;
                  return {
                    mountedQuick: document.querySelector(
                      "[data-character-read-section-content]",
                    ) === window.__committedQuickSection,
                    cachedQuick: cache.get(quickKey)?.section === window.__committedQuickSection,
                    cachedFeatures: cache.has(featuresKey),
                    cachedPersonal: cache.has(personalKey),
                    shellMode: document.querySelector(
                      "[data-character-read-shell-root]",
                    ).dataset.characterReadShellMode,
                    shellPage: document.querySelector(
                      "[data-character-read-shell-root]",
                    ).dataset.characterReadShellPage,
                  };
                }"""
            )
            assert cache_state == {
                "mountedQuick": True,
                "cachedQuick": True,
                "cachedFeatures": False,
                "cachedPersonal": False,
                "shellMode": "read",
                "shellPage": "quick",
            }
            chrome_state = page.evaluate(
                """() => {
                  const state = window.__committedQuickChrome;
                  const header = document.querySelector(".character-header");
                  const navCard = document.querySelector("[data-character-subpage-nav-card]");
                  const nav = navCard.querySelector(".character-subpage-nav");
                  const links = Array.from(
                    nav.querySelectorAll("[data-character-read-subpage-link]"),
                  );
                  return {
                    headerNode: header === state.header,
                    navCardNode: navCard === state.navCard,
                    navNode: nav === state.nav,
                    headerExact: header.outerHTML === state.headerOuter,
                    navCardExact: navCard.outerHTML === state.navCardOuter,
                    orderExact: links.map(
                      (link) => link.dataset.characterReadTargetSubpage,
                    ).join("|") === state.order.join("|"),
                    linksExact: links.length === state.navLinks.size && links.every((link) => (
                      state.navLinks.get(link.dataset.characterReadTargetSubpage) === link
                    )),
                    linksConnected: Array.from(state.navLinks.values()).every(
                      (link) => link.isConnected,
                    ),
                    headerFreshAttribute: header.dataset.interruptedFreshHeader || "",
                    navCardFreshAttribute: navCard.dataset.interruptedFreshNavCard || "",
                    extraPresent: !!nav.querySelector(
                      "[data-character-read-target-subpage='interrupted-extra']",
                    ),
                  };
                }"""
            )
            assert chrome_state == {
                "headerNode": True,
                "navCardNode": True,
                "navNode": True,
                "headerExact": True,
                "navCardExact": True,
                "orderExact": True,
                "linksExact": True,
                "linksConnected": True,
                "headerFreshAttribute": "",
                "navCardFreshAttribute": "",
                "extraPresent": False,
            }

            page.locator("[data-character-read-target-subpage='features']").click()
            expect(page.locator("h2:has-text('Features and traits')")).to_be_visible(timeout=5000)
            expect(page).to_have_url(re.compile(r"[?&]page=features(?:&|$)"), timeout=5000)
            assert features_gets == 2
            expect(page.locator(".character-header__identity h1")).to_have_text(
                "Interrupted Fresh Features",
            )
            expect(page.locator(".character-header")).to_have_attribute(
                "data-interrupted-fresh-header",
                "yes",
            )
            expect(page.locator("[data-character-subpage-nav-card]")).to_have_attribute(
                "data-interrupted-fresh-nav-card",
                "yes",
            )
            expect(page.locator(".character-subpage-nav")).to_have_attribute(
                "aria-label",
                "Interrupted fresh character sections",
            )
            expect(
                page.locator("[data-character-read-target-subpage='inventory']")
            ).to_have_attribute("data-interrupted-fresh-link", "yes")
            expect(
                page.locator("[data-character-read-target-subpage='controls']")
            ).to_have_count(0)
            expect(
                page.locator("[data-character-read-target-subpage='interrupted-extra']")
            ).to_be_visible()
            assert not page.evaluate(
                """() => (
                  document.querySelector("[data-character-read-section-content]")
                  === window.__abortedFeatureSection
                )"""
            )
        finally:
            page.close()
            browser.close()


@pytest.mark.parametrize(
    "viewport",
    ({"width": 1280, "height": 900}, {"width": 390, "height": 800}),
)
def test_character_read_subpage_503_retains_mounted_page_history_and_never_retries(
    users,
    character_read_shell_live_server,
    viewport,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = character_read_shell_live_server
    character_url = f"{base_url}/campaigns/linden-pass/characters/arden-march"
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport=viewport)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        request_count = 0

        def return_busy(route):
            nonlocal request_count
            request_count += 1
            route.fulfill(
                status=503,
                content_type="text/html",
                headers={"Retry-After": "2", "Cache-Control": "no-store"},
                body="<h1>Character pages are busy</h1>",
            )

        try:
            _sign_in_browser(page, base_url, users["dm"])
            page.goto(f"{character_url}?page=quick")
            _wait_for_app_loading_cover(page)
            initial_history_length = page.evaluate("window.history.length")
            quick_panel_text = page.locator("[data-character-read-shell-panel]").inner_text()
            page.route(
                re.compile(r"/campaigns/linden-pass/characters/arden-march\?page=features$"),
                return_busy,
            )

            page.locator("[data-character-read-target-subpage='features']").click()

            loading = page.locator("[data-character-read-shell-loading]")
            expect(loading).to_be_visible(timeout=2000)
            expect(loading).to_contain_text(
                "Character pages are busy. Wait a moment, then choose the section again."
            )
            expect(page.locator("[data-character-read-shell-root]")).not_to_have_attribute(
                "aria-busy",
                "true",
            )
            expect(page.locator("[data-character-read-pending]")).to_have_count(0)
            expect(page).to_have_url(re.compile(r"[?&]page=quick(?:&|$)"))
            assert page.locator("[data-character-read-shell-panel]").inner_text() == quick_panel_text
            assert page.evaluate("window.history.length") == initial_history_length
            expect(page.locator("html.app-loading, html.app-loading-closing")).to_have_count(0)
            page.wait_for_timeout(500)
            assert request_count == 1
        finally:
            page.close()
            browser.close()


def test_character_read_post_save_503_retries_only_the_redirected_refresh(
    users,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = character_read_shell_live_server
    character_url = f"{base_url}/campaigns/linden-pass/characters/arden-march"
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["dm"])
            page.goto(f"{character_url}?page=quick")
            _wait_for_app_loading_cover(page)
            page.evaluate("window.__characterReadPostSaveMarker = 'alive'")
            page.evaluate(
                """() => {
                  const originalFetch = window.fetch.bind(window);
                  const state = {
                    postCount: 0,
                    refreshCount: 0,
                    busyRefreshesRemaining: 2,
                    refreshUrl: "",
                  };
                  const busyResponse = (url, redirected) => {
                    const response = new Response(
                      "<h1>Character pages are busy</h1>",
                      {
                        status: 503,
                        headers: {
                          "Retry-After": "1",
                          "Cache-Control": "no-store",
                          "Content-Type": "text/html",
                        },
                      },
                    );
                    return new Proxy(response, {
                      get(target, property) {
                        if (property === "redirected") {
                          return redirected;
                        }
                        if (property === "url") {
                          return url;
                        }
                        const value = Reflect.get(target, property, target);
                        return typeof value === "function" ? value.bind(target) : value;
                      },
                    });
                  };
                  window.__characterReadPostSaveBusyState = state;
                  window.fetch = async (url, options = {}) => {
                    const method = String(options.method || "GET").toUpperCase();
                    if (method === "POST") {
                      state.postCount += 1;
                      await originalFetch(url, {
                        ...options,
                        redirect: "manual",
                      });
                      state.refreshUrl = window.location.href;
                      return busyResponse(state.refreshUrl, true);
                    }
                    if (state.refreshUrl && String(url) === state.refreshUrl) {
                      state.refreshCount += 1;
                      if (state.busyRefreshesRemaining > 0) {
                        state.busyRefreshesRemaining -= 1;
                        return busyResponse(state.refreshUrl, false);
                      }
                    }
                    return originalFetch(url, options);
                  };
                }"""
            )

            hp_field = page.locator(
                "form[data-character-sheet-edit-form='vitals'] input[name='current_hp']"
            )
            hp_field.fill("12")

            loading = page.locator("[data-character-read-shell-loading]")
            expect(page.locator("[data-flash-stack-root] .flash-success")).to_have_text(
                "Vitals updated.",
                timeout=15000,
            )
            expect(hp_field).to_have_value("12", timeout=5000)
            expect(loading).to_be_hidden(timeout=5000)
            expect(page.locator("[data-character-read-shell-root]")).not_to_have_attribute(
                "aria-busy",
                "true",
            )
            assert page.evaluate("window.__characterReadPostSaveMarker") == "alive"
            assert page.evaluate("window.__characterReadPostSaveBusyState.postCount") == 1
            assert page.evaluate("window.__characterReadPostSaveBusyState.refreshCount") == 3
        finally:
            page.close()
            browser.close()


def test_character_read_visited_section_reattaches_initialized_live_nodes_without_network(
    users,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = character_read_shell_live_server
    character_url = f"{base_url}/campaigns/linden-pass/characters/arden-march"
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 500})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        spellcasting_gets = 0

        def count_spellcasting_gets(request):
            nonlocal spellcasting_gets
            if (
                request.method == "GET"
                and "/campaigns/linden-pass/characters/arden-march" in request.url
                and "page=spellcasting" in request.url
            ):
                spellcasting_gets += 1

        page.on("request", count_spellcasting_gets)
        try:
            _sign_in_browser(page, base_url, users["dm"])
            page.goto(f"{character_url}?page=spellcasting")
            _wait_for_app_loading_cover(page)
            expect(page.locator("[data-character-spellcasting-view-switch]").first).to_be_visible()
            page.evaluate(
                """() => {
                  const shell = document.querySelector("[data-character-read-shell-root]");
                  const panel = document.querySelector("[data-character-read-shell-panel]");
                  const header = panel.querySelector(".character-header");
                  const navCard = panel.querySelector("[data-character-subpage-nav-card]");
                  const nav = navCard.querySelector(".character-subpage-nav");
                  const navLinks = new Map(
                    Array.from(nav.querySelectorAll("[data-character-read-subpage-link]"))
                      .map((link) => [link.dataset.characterReadTargetSubpage, link]),
                  );
                  const section = panel.querySelector("[data-character-read-section-content]");
                  const marker = section.querySelector("[data-character-spellcasting-view-switch]");
                  const controller = marker.__characterSpellcastingActivateView;
                  const probe = document.createElement("input");
                  probe.name = "visited-panel-probe";
                  probe.value = "Draft kept on the live node.";
                  const spacer = document.createElement("div");
                  spacer.style.height = "1200px";
                  const details = document.createElement("details");
                  details.open = true;
                  details.append(document.createElement("summary"), document.createTextNode("Details state"));
                  const trigger = document.createElement("button");
                  trigger.type = "button";
                  trigger.textContent = "Open visited dialog";
                  trigger.dataset.presentationDialogTrigger = "visited-panel-dialog";
                  const dialog = document.createElement("dialog");
                  dialog.id = "visited-panel-dialog";
                  dialog.dataset.presentationDialog = "";
                  dialog.setAttribute("aria-labelledby", "visited-panel-dialog-title");
                  const dialogTitle = document.createElement("h2");
                  dialogTitle.id = "visited-panel-dialog-title";
                  dialogTitle.textContent = "Dialog state";
                  probe.dataset.presentationDialogInitialFocus = "";
                  dialog.append(dialogTitle, probe);
                  section.prepend(spacer);
                  section.append(details, trigger, dialog);
                  const presentation = window.__playerWikiPresentationController;
                  presentation.init(section);
                  presentation.openDialog(dialog, trigger);
                  window.__visitedPanelProbe = {
                    shell,
                    panel,
                    header,
                    navCard,
                    nav,
                    navLinks,
                    section,
                    marker,
                    controller,
                    probe,
                    details,
                    trigger,
                    dialog,
                  };
                  probe.focus({ preventScroll: true });
                  probe.setSelectionRange(6, 10);
                  window.scrollTo(0, 600);

                  window.__visitedPanelInitCalls = 0;
                  window.__visitedPanelOpenDialogCalls = 0;
                  window.__playerWikiPresentationController = {
                    init: (scope) => {
                      window.__visitedPanelInitCalls += 1;
                      return presentation.init(scope);
                    },
                    openDialog: (dialogNode, triggerNode) => {
                      window.__visitedPanelOpenDialogCalls += 1;
                      window.__visitedPanelOpenDialogArgumentsMatch = (
                        dialogNode === dialog && triggerNode === trigger
                      );
                      return presentation.openDialog(dialogNode, triggerNode);
                    },
                  };
                }"""
            )
            spellcasting_gets = 0

            page.evaluate(
                """async () => {
                  const link = document.querySelector("[data-character-read-target-subpage='personal']");
                  await window.__playerWikiCharacterReadShell.updateHistoryFromSubpage({
                    href: link.href,
                    replaceHistory: false,
                  });
                }"""
            )
            expect(page).to_have_url(re.compile(r"[?&]page=personal(?:&|$)"), timeout=5000)
            expect(page.locator("[data-character-read-target-subpage='spellcasting']")).to_be_visible()
            init_calls_after_personal = page.evaluate("window.__visitedPanelInitCalls")

            page.evaluate(
                """async () => {
                  const link = document.querySelector("[data-character-read-target-subpage='spellcasting']");
                  await window.__playerWikiCharacterReadShell.updateHistoryFromSubpage({
                    href: link.href,
                    replaceHistory: false,
                  });
                }"""
            )
            expect(page).to_have_url(re.compile(r"[?&]page=spellcasting(?:&|$)"), timeout=5000)
            expect(page.locator("input[name='visited-panel-probe']")).to_have_value(
                "Draft kept on the live node."
            )
            page.wait_for_timeout(100)

            assert spellcasting_gets == 0
            identity_state = page.evaluate(
                """() => {
                  const state = window.__visitedPanelProbe;
                  const marker = document.querySelector("[data-character-spellcasting-view-switch]");
                  const navLinks = Array.from(
                    document.querySelectorAll("[data-character-read-subpage-link]"),
                  );
                  return {
                    shell: document.querySelector("[data-character-read-shell-root]") === state.shell,
                    panel: document.querySelector("[data-character-read-shell-panel]") === state.panel,
                    header: document.querySelector(".character-header") === state.header,
                    navCard: document.querySelector("[data-character-subpage-nav-card]") === state.navCard,
                    nav: document.querySelector(".character-subpage-nav") === state.nav,
                    navLinks: navLinks.every((link) => (
                      state.navLinks.get(link.dataset.characterReadTargetSubpage) === link
                    )),
                    section: document.querySelector("[data-character-read-section-content]") === state.section,
                    marker: marker === state.marker,
                    controller: marker.__characterSpellcastingActivateView === state.controller,
                    probe: document.querySelector("input[name='visited-panel-probe']") === state.probe,
                    details: state.details.isConnected && state.details.open,
                    trigger: document.querySelector(
                      "[data-presentation-dialog-trigger='visited-panel-dialog']",
                    ) === state.trigger,
                    dialog: state.dialog.isConnected && state.dialog.open && state.dialog.matches(":modal"),
                    focus: document.activeElement === state.probe,
                    selectionStart: state.probe.selectionStart,
                    selectionEnd: state.probe.selectionEnd,
                  };
                }"""
            )
            assert identity_state == {
                "shell": True,
                "panel": True,
                "header": True,
                "navCard": True,
                "nav": True,
                "navLinks": True,
                "section": True,
                "marker": True,
                "controller": True,
                "probe": True,
                "details": True,
                "trigger": True,
                "dialog": True,
                "focus": True,
                "selectionStart": 6,
                "selectionEnd": 10,
            }
            assert page.evaluate("window.__visitedPanelInitCalls") == init_calls_after_personal
            assert page.evaluate("window.__visitedPanelOpenDialogCalls") == 1
            assert page.evaluate("window.__visitedPanelOpenDialogArgumentsMatch") is True
            assert abs(page.evaluate("window.scrollY") - 600) <= 2
            page.keyboard.press("Escape")
            expect(page.locator("#visited-panel-dialog")).to_be_hidden(timeout=5000)
            expect(
                page.locator("[data-presentation-dialog-trigger='visited-panel-dialog']")
            ).to_be_focused(timeout=5000)
        finally:
            page.close()
            browser.close()


def test_character_read_fresh_section_reconciles_stable_common_chrome_in_place(
    users,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = character_read_shell_live_server
    character_url = f"{base_url}/campaigns/linden-pass/characters/arden-march"
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["dm"])
            page.goto(f"{character_url}?page=quick")
            _wait_for_app_loading_cover(page)
            page.evaluate(
                """() => {
                  const shell = document.querySelector("[data-character-read-shell-root]");
                  const panel = shell.querySelector("[data-character-read-shell-panel]");
                  const header = panel.querySelector(".character-header");
                  const navCard = panel.querySelector("[data-character-subpage-nav-card]");
                  const nav = navCard.querySelector(".character-subpage-nav");
                  const links = new Map(
                    Array.from(nav.querySelectorAll("[data-character-read-subpage-link]"))
                      .map((link) => [link.dataset.characterReadTargetSubpage, link]),
                  );
                  const originalFetch = window.fetch.bind(window);
                  const presentation = window.__playerWikiPresentationController;
                  window.__freshSectionInitCalls = 0;
                  window.__playerWikiPresentationController = {
                    init: (scope) => {
                      window.__freshSectionInitCalls += 1;
                      return presentation.init(scope);
                    },
                  };
                  window.__freshCommonChrome = { shell, panel, header, navCard, nav, links };
                  window.fetch = async (url, options = {}) => {
                    const response = await originalFetch(url, options);
                    const method = String(options.method || "GET").toUpperCase();
                    if (method !== "GET" || !String(url).includes("page=personal")) {
                      return response;
                    }
                    const documentResponse = new DOMParser().parseFromString(
                      await response.text(),
                      "text/html",
                    );
                    const responseHeader = documentResponse.querySelector(".character-header");
                    responseHeader.dataset.freshHeader = "yes";
                    responseHeader.querySelector("h1").textContent = "Arden March Refreshed";
                    const responseNavCard = documentResponse.querySelector(
                      "[data-character-subpage-nav-card]",
                    );
                    responseNavCard.dataset.freshNavCard = "yes";
                    const responseNav = responseNavCard.querySelector(".character-subpage-nav");
                    responseNav.setAttribute("aria-label", "Fresh character sections");
                    const inventory = responseNav.querySelector(
                      "[data-character-read-target-subpage='inventory']",
                    );
                    inventory.textContent = "Carried inventory";
                    inventory.setAttribute("data-fresh-link", "yes");
                    inventory.href = `${window.location.pathname}?page=inventory#fresh`;
                    responseNav.prepend(inventory);
                    responseNav.querySelector(
                      "[data-character-read-target-subpage='controls']",
                    ).remove();
                    const extra = documentResponse.createElement("a");
                    extra.className = "ghost-button";
                    extra.href = `${window.location.pathname}?page=fresh-extra`;
                    extra.dataset.characterReadSubpageLink = "";
                    extra.dataset.characterReadTargetSubpage = "fresh-extra";
                    extra.textContent = "Fresh extra";
                    responseNav.append(extra);
                    const replacement = new Response(
                      `<!doctype html>${documentResponse.documentElement.outerHTML}`,
                      {
                        status: response.status,
                        statusText: response.statusText,
                        headers: response.headers,
                      },
                    );
                    return new Proxy(replacement, {
                      get(target, property) {
                        if (property === "url") {
                          return response.url;
                        }
                        if (property === "redirected") {
                          return response.redirected;
                        }
                        const value = Reflect.get(target, property, target);
                        return typeof value === "function" ? value.bind(target) : value;
                      },
                    });
                  };
                }"""
            )

            page.locator("[data-character-read-target-subpage='personal']").click()
            expect(page).to_have_url(re.compile(r"[?&]page=personal(?:&|$)"), timeout=5000)
            expect(page.locator("[data-character-read-section-content]")).to_be_visible(timeout=5000)

            chrome_state = page.evaluate(
                """() => {
                  const state = window.__freshCommonChrome;
                  const currentLinks = Array.from(
                    document.querySelectorAll("[data-character-read-subpage-link]"),
                  );
                  const inventory = currentLinks.find(
                    (link) => link.dataset.characterReadTargetSubpage === "inventory",
                  );
                  const controls = state.links.get("controls");
                  const extra = currentLinks.find(
                    (link) => link.dataset.characterReadTargetSubpage === "fresh-extra",
                  );
                  return {
                    shell: document.querySelector("[data-character-read-shell-root]") === state.shell,
                    panel: document.querySelector("[data-character-read-shell-panel]") === state.panel,
                    header: document.querySelector(".character-header") === state.header,
                    navCard: document.querySelector("[data-character-subpage-nav-card]") === state.navCard,
                    nav: document.querySelector(".character-subpage-nav") === state.nav,
                    personalLink: currentLinks.find(
                      (link) => link.dataset.characterReadTargetSubpage === "personal",
                    ) === state.links.get("personal"),
                    inventoryLink: inventory === state.links.get("inventory"),
                    inventoryFirst: inventory === state.nav.firstElementChild,
                    inventoryText: inventory.textContent.trim(),
                    inventoryFreshAttribute: inventory.dataset.freshLink,
                    inventoryHref: inventory.getAttribute("href"),
                    controlsRemoved: !controls.isConnected,
                    extraAdded: !!extra,
                    linkCount: currentLinks.length,
                    originalLinkCount: state.links.size,
                    headerText: state.header.querySelector("h1").textContent.trim(),
                    headerFreshAttribute: state.header.dataset.freshHeader,
                    navCardFreshAttribute: state.navCard.dataset.freshNavCard,
                    navLabel: state.nav.getAttribute("aria-label"),
                    activePersonal: state.links.get("personal").classList.contains("button-link"),
                    historyMode: window.history.state?.characterReadMode,
                    historySubpage: window.history.state?.characterReadSubpage,
                    historyHref: window.history.state?.characterReadHref,
                    initCalls: window.__freshSectionInitCalls,
                  };
                }"""
            )
            assert chrome_state == {
                "shell": True,
                "panel": True,
                "header": True,
                "navCard": True,
                "nav": True,
                "personalLink": True,
                "inventoryLink": True,
                "inventoryFirst": True,
                "inventoryText": "Carried inventory",
                "inventoryFreshAttribute": "yes",
                "inventoryHref": "/campaigns/linden-pass/characters/arden-march?page=inventory#fresh",
                "controlsRemoved": True,
                "extraAdded": True,
                "linkCount": chrome_state["originalLinkCount"],
                "originalLinkCount": chrome_state["originalLinkCount"],
                "headerText": "Arden March Refreshed",
                "headerFreshAttribute": "yes",
                "navCardFreshAttribute": "yes",
                "navLabel": "Fresh character sections",
                "activePersonal": True,
                "historyMode": "read",
                "historySubpage": "personal",
                "historyHref": "/campaigns/linden-pass/characters/arden-march?page=personal",
                "initCalls": 1,
            }
        finally:
            page.close()
            browser.close()


def test_character_read_successful_mutation_invalidates_visited_sections_but_conflict_does_not(
    app,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    base_url = character_read_shell_live_server
    character_url = f"{base_url}/campaigns/linden-pass/characters/arden-march"
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        portrait_gets = 0

        def count_portrait_gets(request):
            nonlocal portrait_gets
            if (
                request.method == "GET"
                and "/campaigns/linden-pass/characters/arden-march" in request.url
                and "page=portrait" in request.url
            ):
                portrait_gets += 1

        page.on("request", count_portrait_gets)
        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(f"{character_url}?page=notes")
            _wait_for_app_loading_cover(page)
            notes = page.locator("textarea[name='player_notes_markdown']")
            expect(notes).to_be_visible()
            page.evaluate(
                """() => {
                  const shell = document.querySelector("[data-character-read-shell-root]");
                  const panel = shell.querySelector("[data-character-read-shell-panel]");
                  const header = panel.querySelector(".character-header");
                  const navCard = panel.querySelector("[data-character-subpage-nav-card]");
                  const nav = navCard.querySelector(".character-subpage-nav");
                  const links = new Map(
                    Array.from(nav.querySelectorAll("[data-character-read-subpage-link]"))
                      .map((link) => [link.dataset.characterReadTargetSubpage, link]),
                  );
                  window.__mutationCommonChrome = { shell, panel, header, navCard, nav, links };
                  window.__mutationCommonChromeIdentity = () => {
                    const state = window.__mutationCommonChrome;
                    const currentLinks = Array.from(
                      document.querySelectorAll("[data-character-read-subpage-link]"),
                    );
                    return {
                      shell: document.querySelector("[data-character-read-shell-root]") === state.shell,
                      panel: document.querySelector("[data-character-read-shell-panel]") === state.panel,
                      header: document.querySelector(".character-header") === state.header,
                      navCard: document.querySelector("[data-character-subpage-nav-card]") === state.navCard,
                      nav: document.querySelector(".character-subpage-nav") === state.nav,
                      links: currentLinks.length === state.links.size && currentLinks.every((link) => (
                        state.links.get(link.dataset.characterReadTargetSubpage) === link
                      )),
                    };
                  };
                }"""
            )

            page.locator("[data-character-read-target-subpage='portrait']").click()
            expect(page).to_have_url(re.compile(r"[?&]page=portrait(?:&|$)"), timeout=5000)
            page.locator("[data-character-read-target-subpage='notes']").click()
            expect(notes).to_be_visible(timeout=5000)
            assert portrait_gets == 1

            notes.fill("Successful mutation invalidates prior panels.")
            page.get_by_role("button", name="Save note").click()
            expect(page.locator("[data-flash-stack-root] .flash-success")).to_have_text(
                "Note saved.", timeout=5000
            )
            assert all(page.evaluate("window.__mutationCommonChromeIdentity()").values())

            page.locator("[data-character-read-target-subpage='portrait']").click()
            expect(page).to_have_url(re.compile(r"[?&]page=portrait(?:&|$)"), timeout=5000)
            assert portrait_gets == 2
            page.locator("[data-character-read-target-subpage='notes']").click()
            expect(notes).to_be_visible(timeout=5000)
            assert portrait_gets == 2

            _write_character_state(
                app,
                "arden-march",
                lambda state: state.__setitem__(
                    "notes",
                    {
                        **dict(state.get("notes") or {}),
                        "player_notes_markdown": "Concurrent mutation for cache conflict.",
                    },
                ),
            )
            conflict_draft = "Conflict response must keep draft and visited cache."
            notes.fill(conflict_draft)
            page.get_by_role("button", name="Save note").click()
            expect(page.locator("[data-flash-stack-root] .flash-error")).to_have_text(
                "This sheet changed in another session. Refresh the page and try again.",
                timeout=5000,
            )
            expect(notes).to_have_value(conflict_draft)
            assert all(page.evaluate("window.__mutationCommonChromeIdentity()").values())

            page.locator("[data-character-read-target-subpage='portrait']").click()
            expect(page).to_have_url(re.compile(r"[?&]page=portrait(?:&|$)"), timeout=5000)
            assert portrait_gets == 2
        finally:
            page.close()
            browser.close()


def test_character_read_successful_post_commits_atomically_before_racing_navigation(
    users,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = character_read_shell_live_server
    character_url = f"{base_url}/campaigns/linden-pass/characters/arden-march"
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        portrait_gets = 0

        def count_portrait_gets(request):
            nonlocal portrait_gets
            if (
                request.method == "GET"
                and "/campaigns/linden-pass/characters/arden-march" in request.url
                and "page=portrait" in request.url
            ):
                portrait_gets += 1

        page.on("request", count_portrait_gets)
        try:
            _sign_in_browser(page, base_url, users["dm"])
            page.goto(f"{character_url}?page=notes")
            _wait_for_app_loading_cover(page)
            notes = page.locator("textarea[name='player_notes_markdown']")
            expect(notes).to_be_visible()

            page.locator("[data-character-read-target-subpage='portrait']").click()
            expect(page).to_have_url(re.compile(r"[?&]page=portrait(?:&|$)"), timeout=5000)
            page.locator("[data-character-read-target-subpage='notes']").click()
            expect(notes).to_be_visible(timeout=5000)
            assert portrait_gets == 1

            page.evaluate(
                """() => {
                  const originalFetch = window.fetch.bind(window);
                  window.fetch = async (url, options = {}) => {
                    const response = await originalFetch(url, options);
                    const method = String(options.method || "GET").toUpperCase();
                    if (method !== "POST") {
                      return response;
                    }
                    const responseDocument = new DOMParser().parseFromString(
                      await response.text(),
                      "text/html",
                    );
                    const responseHeader = responseDocument.querySelector(".character-header");
                    responseHeader.dataset.atomicPostHeader = "yes";
                    responseHeader.querySelector("h1").textContent = "Atomic save response";
                    const responseNavCard = responseDocument.querySelector(
                      "[data-character-subpage-nav-card]",
                    );
                    responseNavCard.dataset.atomicPostNavCard = "yes";
                    const responseNav = responseNavCard.querySelector(".character-subpage-nav");
                    responseNav.setAttribute("aria-label", "Atomic save character sections");
                    const portraitLink = responseNav.querySelector(
                      "[data-character-read-target-subpage='portrait']",
                    );
                    portraitLink.dataset.atomicPostLink = "yes";
                    portraitLink.textContent = "Fresh portrait";
                    const responseContent = responseDocument.querySelector(
                      "[data-character-read-section-content]",
                    );
                    responseContent.dataset.atomicPostContent = "yes";
                    const replacement = new Response(
                      `<!doctype html>${responseDocument.documentElement.outerHTML}`,
                      {
                        status: response.status,
                        statusText: response.statusText,
                        headers: response.headers,
                      },
                    );
                    return new Proxy(replacement, {
                      get(target, property) {
                        if (property === "url") {
                          return response.url;
                        }
                        if (property === "redirected") {
                          return response.redirected;
                        }
                        const value = Reflect.get(target, property, target);
                        return typeof value === "function" ? value.bind(target) : value;
                      },
                    });
                  };

                  window.history.replaceState(
                    {
                      characterReadMode: "read",
                      characterReadSubpage: "portrait",
                      characterReadHref: `${window.location.pathname}?page=portrait`,
                    },
                    "",
                    `${window.location.pathname}?page=notes`,
                  );
                  window.__atomicPostInitialRevision = document.querySelector(
                    "[data-character-sheet-edit-form='notes'] input[name='expected_revision']",
                  )?.value || "";
                  window.__atomicPostCommitSnapshot = null;
                  const panel = document.querySelector("[data-character-read-shell-panel]");
                  const observer = new MutationObserver((records) => {
                    if (window.__atomicPostCommitSnapshot) {
                      return;
                    }
                    const section = records.flatMap((record) => Array.from(record.addedNodes))
                      .find((node) => (
                        node instanceof HTMLElement
                        && node.matches("[data-character-read-section-content]")
                        && node.dataset.atomicPostContent === "yes"
                      ));
                    if (!(section instanceof HTMLElement)) {
                      return;
                    }
                    observer.disconnect();
                    const cache = window.__playerWikiCharacterReadShell.cache;
                    const prefix = window.location.pathname;
                    const header = panel.querySelector(".character-header");
                    const navCard = panel.querySelector("[data-character-subpage-nav-card]");
                    const nav = navCard.querySelector(".character-subpage-nav");
                    const portrait = nav.querySelector(
                      "[data-character-read-target-subpage='portrait']",
                    );
                    const flash = document.querySelector("[data-flash-stack-root] .flash-success");
                    const mountedRevision = section.querySelector(
                      "[data-character-sheet-edit-form='notes'] input[name='expected_revision']",
                    )?.value || "";
                    window.__atomicPostCommitSnapshot = {
                      cacheNotes: cache.get(`${prefix}?page=notes`)?.section === section,
                      cachedRevision: cache.get(`${prefix}?page=notes`)?.section.querySelector(
                        "[data-character-sheet-edit-form='notes'] input[name='expected_revision']",
                      )?.value || "",
                      cachePortrait: cache.has(`${prefix}?page=portrait`),
                      flash: flash?.textContent.trim() || "",
                      headerMarker: header.dataset.atomicPostHeader || "",
                      headerText: header.querySelector("h1")?.textContent.trim() || "",
                      navCardMarker: navCard.dataset.atomicPostNavCard || "",
                      navLabel: nav.getAttribute("aria-label") || "",
                      portraitMarker: portrait.dataset.atomicPostLink || "",
                      portraitText: portrait.textContent.trim(),
                      mountedContent: document.querySelector(
                        "[data-character-read-section-content]",
                      ) === section,
                      mountedRevision,
                      shellPage: document.querySelector(
                        "[data-character-read-shell-root]",
                      )?.dataset.characterReadShellPage,
                      historyMode: window.history.state?.characterReadMode,
                      historySubpage: window.history.state?.characterReadSubpage,
                      historyHref: window.history.state?.characterReadHref,
                    };
                    portrait.click();
                  });
                  observer.observe(panel, { childList: true });
                }"""
            )

            notes.fill("Successful mutation commits atomically before navigation.")
            page.get_by_role("button", name="Save note").click()

            page.wait_for_function("() => window.__atomicPostCommitSnapshot !== null")
            initial_revision = page.evaluate("window.__atomicPostInitialRevision")
            atomic_snapshot = page.evaluate("window.__atomicPostCommitSnapshot")
            mounted_revision = atomic_snapshot.pop("mountedRevision")
            cached_revision = atomic_snapshot.pop("cachedRevision")
            assert mounted_revision
            assert mounted_revision != initial_revision
            assert cached_revision == mounted_revision
            assert atomic_snapshot == {
                "cacheNotes": True,
                "cachePortrait": False,
                "flash": "Note saved.",
                "headerMarker": "yes",
                "headerText": "Atomic save response",
                "navCardMarker": "yes",
                "navLabel": "Atomic save character sections",
                "portraitMarker": "yes",
                "portraitText": "Fresh portrait",
                "mountedContent": True,
                "shellPage": "notes",
                "historyMode": "read",
                "historySubpage": "notes",
                "historyHref": "/campaigns/linden-pass/characters/arden-march?page=notes",
            }
            expect(page).to_have_url(re.compile(r"[?&]page=portrait(?:&|$)"), timeout=5000)
            expect(page.locator("[data-character-read-shell-root]")).to_have_attribute(
                "data-character-read-shell-page",
                "portrait",
            )
            assert portrait_gets == 2
        finally:
            page.close()
            browser.close()


def test_character_native_live_previews_preserve_focus_and_viewport(
    app,
    users,
    character_read_shell_live_server,
    monkeypatch,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    monkeypatch.setattr(app_module, "build_level_one_builder_context", lambda *args, **kwargs: _builder_context_fixture())
    monkeypatch.setattr(
        app_module,
        "native_level_up_readiness",
        lambda *args, **kwargs: {"status": "ready", "message": "", "reasons": []},
    )
    monkeypatch.setattr(
        app_module,
        "build_native_level_up_context",
        lambda *args, **kwargs: _level_up_context_fixture(),
    )
    _write_leveler_fixture(app)

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 960, "height": 420})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["dm"])

            page.goto(f"{base_url}/campaigns/linden-pass/characters/new")
            _wait_for_app_loading_cover(page)
            strength_field = page.locator("input[name='str']")
            expect(strength_field).to_be_visible(timeout=5000)
            strength_field.scroll_into_view_if_needed()
            page.wait_for_timeout(50)
            create_scroll_before = _scroll_y(page)
            with page.expect_response(
                lambda response: "/campaigns/linden-pass/characters/new" in response.url
                and "_live_preview=1" in response.url,
                timeout=5000,
            ):
                strength_field.fill("17")
            expect(strength_field).to_be_focused(timeout=5000)
            expect(strength_field).to_have_value("17", timeout=5000)
            assert abs(_scroll_y(page) - create_scroll_before) <= 40

            page.goto(f"{base_url}/campaigns/linden-pass/characters/leveler/level-up")
            _wait_for_app_loading_cover(page)
            hp_gain_field = page.locator("input[name='hp_gain']")
            expect(hp_gain_field).to_be_visible(timeout=5000)
            hp_gain_field.scroll_into_view_if_needed()
            page.wait_for_timeout(50)
            level_scroll_before = _scroll_y(page)
            with page.expect_response(
                lambda response: "/campaigns/linden-pass/characters/leveler/level-up" in response.url
                and "_live_preview=1" in response.url,
                timeout=5000,
            ):
                hp_gain_field.fill("9")
            expect(hp_gain_field).to_be_focused(timeout=5000)
            expect(hp_gain_field).to_have_value("9", timeout=5000)
            assert abs(_scroll_y(page) - level_scroll_before) <= 40
        finally:
            page.close()
            browser.close()


def test_character_systems_item_lookup_keeps_results_visible_while_refreshing(
    app,
    users,
    character_read_shell_live_server,
    monkeypatch,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    entry = _seed_systems_item_entry(app)
    with app.app_context():
        systems_service = app.extensions["systems_service"]
        original_search = systems_service.search_entries_for_campaign

    def _slow_search(*args, **kwargs):
        if str(kwargs.get("query") or "").strip().lower() == "lantern":
            time.sleep(1.0)
        return original_search(*args, **kwargs)

    monkeypatch.setattr(systems_service, "search_entries_for_campaign", _slow_search)

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["dm"])

            page.goto(f"{base_url}/campaigns/linden-pass/characters/selene-brook?page=inventory")
            _wait_for_app_loading_cover(page)
            search_input = page.locator("[data-character-systems-item-query]")
            results_select = page.locator("[data-character-systems-item-results]")
            status = page.locator("[data-character-systems-item-status]")
            expect(search_input).to_be_visible(timeout=5000)

            with page.expect_response(
                lambda response: "/equipment/systems-items/search" in response.url and "q=rope" in response.url,
                timeout=5000,
            ):
                search_input.fill("rope")
            expect(results_select).not_to_be_disabled(timeout=5000)
            expect(results_select.locator("option").first).to_have_text(re.compile(r"Rope"))
            assert results_select.input_value() == entry.slug

            search_input.fill("lantern")
            expect(status).to_have_text("Searching Systems items...", timeout=1500)
            expect(results_select).not_to_be_disabled(timeout=5000)
            expect(results_select.locator("option").first).to_have_text(re.compile(r"Rope"))
            assert results_select.input_value() == entry.slug
            expect(status).to_have_text("No enabled Systems items matched that search.", timeout=5000)
        finally:
            page.close()
            browser.close()


def test_spellcasting_subview_buttons_hide_and_show_panels(
    app,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Cleric 5"
        profile["classes"] = [{"class_name": "Cleric", "level": 5}]
        payload["profile"] = profile
        payload["spellcasting"] = {
            "spellcasting_class": "Cleric",
            "spellcasting_ability": "Wisdom",
            "spell_save_dc": 14,
            "spell_attack_bonus": 6,
            "slot_progression": [
                {"level": 1, "max_slots": 4},
                {"level": 2, "max_slots": 3},
                {"level": 3, "max_slots": 2},
            ],
            "spells": [
                {
                    "name": "Guidance",
                    "level": 0,
                    "casting_time": "1 action",
                    "range": "Touch",
                    "duration": "1 minute",
                    "components": "V, S",
                    "source": "Cleric",
                },
                {
                    "name": "Cure Wounds",
                    "level": 1,
                    "casting_time": "1 action",
                    "range": "Touch",
                    "duration": "Instantaneous",
                    "components": "V, S",
                    "source": "Cleric",
                },
                {
                    "name": "Bless",
                    "level": 1,
                    "casting_time": "1 action",
                    "range": "30 feet",
                    "duration": "Concentration, up to 1 minute",
                    "components": "V, S, M",
                    "source": "Cleric (Always Prepared)",
                    "mark": "P",
                    "is_always_prepared": True,
                },
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)
    set_campaign_visibility("linden-pass", characters="players")
    base_url = character_read_shell_live_server

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page.goto(f"{base_url}/sign-in")
            page.locator("input[name='email']").fill(users["dm"]["email"])
            page.locator("input[name='password']").fill(users["dm"]["password"])
            page.locator("button[type='submit']").click()
            page.wait_for_url(re.compile(rf"^{re.escape(base_url)}/.*"), timeout=5000)

            page.goto(f"{base_url}/campaigns/linden-pass/characters/arden-march?mode=read&page=spellcasting")
            _wait_for_app_loading_cover(page)

            current_panel = page.locator("#character-spell-current-view")
            preparation_panel = page.locator("#character-spell-preparation-view")
            expect(current_panel).to_be_visible(timeout=5000)
            expect(preparation_panel).to_be_hidden(timeout=5000)
            expect(current_panel.locator(".spell-card__name", has_text="Bless")).to_be_visible()
            expect(current_panel.locator(".spell-card__name", has_text="Cure Wounds")).to_have_count(0)

            page.get_by_role("tab", name="Preparation").click()
            expect(current_panel).to_be_hidden(timeout=5000)
            expect(preparation_panel).to_be_visible(timeout=5000)
            prep_spell_button = preparation_panel.locator(
                "[data-character-spell-modal-trigger]",
                has_text="Cure Wounds",
            )
            expect(prep_spell_button).to_be_visible()
            prep_spell_button.click()
            prep_dialog = page.locator("dialog[open]", has_text="Cure Wounds")
            expect(prep_dialog).to_be_visible()
            prep_dialog.get_by_role("button", name="Close").click()
            expect(prep_dialog).to_be_hidden()

            page.get_by_role("tab", name="Current spells").click()
            expect(current_panel).to_be_visible(timeout=5000)
            expect(preparation_panel).to_be_hidden(timeout=5000)
        finally:
            browser.close()


def test_character_read_shared_dialog_adopter_preserves_modal_and_fallback_contracts(
    app,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
    tmp_path,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    item_entry = _seed_systems_item_entry(
        app,
        slug="phb-item-backpack",
        title="Backpack",
        rendered_html=(
            '<p>Character item detail body from Systems.</p>'
            '<p><a href="/campaigns/linden-pass/systems/entries/phb-item-backpack">'
            "Open Backpack reference</a></p>"
        ),
    )
    spell_entry = _seed_systems_spell_entry(
        app,
        slug="phb-spell-message",
        title="Message",
        rendered_html="<p>Character spell detail body from Systems.</p>",
    )

    def _link_inventory_item(payload: dict) -> None:
        spellcasting = dict(payload.get("spellcasting") or {})
        spells = list(spellcasting.get("spells") or [])
        assert spells
        spells[0] = {
            **dict(spells[0]),
            "systems_ref": _systems_ref(spell_entry),
        }
        spellcasting["spells"] = spells
        payload["spellcasting"] = spellcasting

        equipment_catalog = list(payload.get("equipment_catalog") or [])
        assert len(equipment_catalog) > 4
        equipment_catalog[4] = {
            **dict(equipment_catalog[4]),
            "systems_ref": _systems_ref(item_entry),
        }
        payload["equipment_catalog"] = equipment_catalog

    _write_character_definition(app, "arden-march", _link_inventory_item)
    set_campaign_visibility("linden-pass", characters="players")
    base_url = character_read_shell_live_server
    character_url = f"{base_url}/campaigns/linden-pass/characters/arden-march"

    def _assert_dialog_label(page, dialog) -> None:
        labelled_by = dialog.get_attribute("aria-labelledby")
        assert labelled_by
        assert page.locator(f"#{labelled_by}").count() == 1
        assert page.locator(f"#{labelled_by}").inner_text().strip()

    def _assert_close_returns_without_scroll(page, trigger, close_action) -> None:
        scroll_before = _scroll_y(page)
        close_action()
        expect(page.locator("dialog[data-character-spell-modal][open]")).to_have_count(
            0,
            timeout=5000,
        )
        expect(trigger).to_be_focused(timeout=5000)
        assert abs(_scroll_y(page) - scroll_before) <= 1

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        desktop_context = browser.new_context(viewport={"width": 1280, "height": 900})
        desktop_page = desktop_context.new_page()
        try:
            _sign_in_browser(desktop_page, base_url, users["owner"])
            desktop_page.goto(f"{character_url}?page=spellcasting")
            _wait_for_app_loading_cover(desktop_page)
            expect(desktop_page.locator("html")).not_to_have_class(re.compile(r"app-loading"))

            spell_trigger = desktop_page.locator(
                "#character-spell-current-view [data-character-spell-modal-trigger]"
            ).first
            expect(spell_trigger).to_be_visible(timeout=5000)
            spell_trigger.scroll_into_view_if_needed()
            spell_trigger.focus()
            spell_scroll = _scroll_y(desktop_page)
            spell_trigger.press("Enter")
            spell_dialog = desktop_page.locator(
                "dialog[data-character-spell-modal][data-presentation-dialog][open]"
            ).first
            expect(spell_dialog).to_be_visible(timeout=5000)
            _assert_dialog_label(desktop_page, spell_dialog)
            assert spell_dialog.evaluate("dialog => dialog.matches(':modal')")
            expect(
                spell_dialog.locator("[data-presentation-dialog-initial-focus]")
            ).to_be_focused(timeout=5000)
            spell_dialog.get_by_role("button", name="Close").click()
            expect(spell_trigger).to_be_focused(timeout=5000)
            assert abs(_scroll_y(desktop_page) - spell_scroll) <= 1

            spell_trigger.press("Enter")
            expect(spell_dialog).to_be_visible(timeout=5000)
            _assert_close_returns_without_scroll(
                desktop_page,
                spell_trigger,
                lambda: desktop_page.keyboard.press("Escape"),
            )

            spell_trigger.press("Enter")
            expect(spell_dialog).to_be_visible(timeout=5000)
            _assert_close_returns_without_scroll(
                desktop_page,
                spell_trigger,
                lambda: desktop_page.mouse.click(1, 1),
            )
            assert "page=spellcasting" in desktop_page.url
            expect(desktop_page.locator("html.app-loading, html.app-loading-closing")).to_have_count(0)
            _assert_character_read_no_overflow(desktop_page, "desktop-dialog-1280x900")
            desktop_page.screenshot(path=str(tmp_path / "character_dialog_desktop_1280x900.png"))
        finally:
            desktop_page.close()
            desktop_context.close()

        mobile_context = browser.new_context(viewport={"width": 390, "height": 800})
        mobile_page = mobile_context.new_page()
        try:
            _sign_in_browser(mobile_page, base_url, users["dm"])
            mobile_page.goto(f"{character_url}?page=spellcasting")
            _wait_for_app_loading_cover(mobile_page)
            mobile_page.evaluate("document.documentElement.dataset.theme = 'moonlit'")
            expect(mobile_page.locator("html")).to_have_attribute("data-theme", "moonlit")

            mobile_page.locator("[data-character-read-target-subpage='inventory']").click()
            expect(mobile_page).to_have_url(re.compile(r"[?&]page=inventory(?:&|$)"), timeout=5000)
            item_trigger = mobile_page.locator("button.item-detail-button").first
            expect(item_trigger).to_be_visible(timeout=5000)
            item_trigger.scroll_into_view_if_needed()
            item_scroll = _scroll_y(mobile_page)
            item_trigger.click()
            item_dialog = mobile_page.locator(
                "dialog.item-detail-dialog[data-presentation-dialog][open]"
            ).first
            expect(item_dialog).to_be_visible(timeout=5000)
            _assert_dialog_label(mobile_page, item_dialog)
            assert item_dialog.evaluate("dialog => dialog.matches(':modal')")
            expect(
                item_dialog.locator("[data-presentation-dialog-initial-focus]")
            ).to_be_focused(timeout=5000)
            item_dialog.get_by_role("button", name="Close").click()
            expect(item_trigger).to_be_focused(timeout=5000)
            assert abs(_scroll_y(mobile_page) - item_scroll) <= 1
            assert "page=inventory" in mobile_page.url
            expect(mobile_page.locator("html.app-loading, html.app-loading-closing")).to_have_count(0)
            _assert_character_read_no_overflow(mobile_page, "mobile-dialog-390x800")
            mobile_page.screenshot(path=str(tmp_path / "character_dialog_mobile_390x800.png"))
        finally:
            mobile_page.close()
            mobile_context.close()

        no_js_context = browser.new_context(
            java_script_enabled=False,
            viewport={"width": 390, "height": 800},
        )
        no_js_page = no_js_context.new_page()
        try:
            _sign_in_browser(no_js_page, base_url, users["owner"])
            no_js_page.goto(f"{character_url}?page=spellcasting")
            expect(no_js_page.locator("[data-character-spell-modal-trigger]")).to_have_count(0)
            spell_fallback = no_js_page.locator("details.spell-card__fallback").first
            expect(spell_fallback).to_be_visible(timeout=5000)
            spell_fallback.locator("summary").click()
            expect(spell_fallback.locator(".spell-detail-content")).to_be_visible(timeout=5000)

            no_js_page.locator("[data-character-read-target-subpage='inventory']").click()
            expect(no_js_page).to_have_url(re.compile(r"[?&]page=inventory(?:&|$)"), timeout=5000)
            expect(no_js_page.locator("button.item-detail-button")).to_have_count(0)
            expect(no_js_page.locator(".item-description-detail").first).to_be_visible(timeout=5000)
            reference_link = no_js_page.get_by_role("link", name="Open Backpack reference")
            expect(reference_link).to_have_attribute(
                "href",
                "/campaigns/linden-pass/systems/entries/phb-item-backpack",
            )
            _assert_character_read_no_overflow(no_js_page, "mobile-no-js-390x800")
            no_js_page.screenshot(path=str(tmp_path / "character_dialog_no_js_390x800.png"))
        finally:
            no_js_page.close()
            no_js_context.close()
            browser.close()


def test_session_shell_draft_guard_models_native_select_defaults_and_modified_values(
    users,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            _sign_in_browser(page, base_url, users["dm"])
            page.goto(f"{base_url}/campaigns/linden-pass/session/dm?dm_view=tools")
            dm_pane = page.locator("[data-session-shell-pane='dm']")
            expect(dm_pane).to_be_visible(timeout=5000)

            page.evaluate(
                """() => {
                    const pane = document.querySelector('[data-session-shell-pane="dm"]');
                    const form = document.createElement('form');
                    form.id = 'session-shell-select-draft-probe';
                    form.method = 'post';
                    form.action = '/session-shell-select-draft-probe';
                    form.innerHTML = `
                        <select name="implicit_single">
                            <option value="">Implicit empty</option>
                            <option value="async">Async result</option>
                            <option value="server">Server result</option>
                        </select>
                        <select name="disabled_leading_single">
                            <option value="disabled" disabled>Disabled first</option>
                            <option value="enabled">Native enabled default</option>
                            <option value="server">Server result</option>
                        </select>
                        <select name="disabled_group_single">
                            <optgroup label="Disabled group" disabled>
                                <option value="grouped">Disabled grouped first</option>
                            </optgroup>
                            <option value="enabled">Native enabled default</option>
                            <option value="server">Server result</option>
                        </select>
                        <select name="listbox_single" size="3">
                            <option value="first">First</option>
                            <option value="second">Second</option>
                            <option value="server">Server result</option>
                        </select>
                        <select name="duplicate_default_single">
                            <option value="first" selected>First explicit default</option>
                            <option value="last" selected>Last explicit default</option>
                            <option value="server">Server result</option>
                        </select>
                        <select name="default_multi" multiple>
                            <option value="alpha" selected>Alpha</option>
                            <option value="beta">Beta</option>
                            <option value="gamma">Gamma</option>
                        </select>
                        <select name="modified_single">
                            <option value="">Implicit empty</option>
                            <option value="user">User selection</option>
                            <option value="server">Server result</option>
                        </select>
                        <select name="modified_multi" multiple>
                            <option value="alpha" selected>Alpha</option>
                            <option value="beta">Beta</option>
                            <option value="gamma">Gamma</option>
                        </select>
                    `;
                    pane.append(form);
                    const modifiedSingle = form.elements.modified_single;
                    const modifiedMulti = form.elements.modified_multi;
                    modifiedSingle.value = 'user';
                    modifiedSingle.dispatchEvent(new Event('change', { bubbles: true }));
                    modifiedMulti.options[1].selected = true;
                    modifiedMulti.dispatchEvent(new Event('change', { bubbles: true }));
                }"""
            )

            page.locator("[data-session-switch-target='session']").click()
            expect(page.locator("[data-session-shell-pane='session']")).to_be_visible(timeout=5000)
            page.locator("[data-session-switch-target='dm']").click()
            expect(dm_pane).to_be_visible(timeout=5000)

            page.evaluate(
                """() => {
                    const form = document.querySelector('#session-shell-select-draft-probe');
                    form.elements.implicit_single.value = 'async';
                    form.elements.disabled_leading_single.value = 'server';
                    form.elements.disabled_group_single.value = 'server';
                    form.elements.listbox_single.value = 'server';
                    form.elements.duplicate_default_single.value = 'server';
                    for (const option of form.elements.default_multi.options) {
                        option.selected = option.value === 'beta';
                    }
                    form.elements.modified_single.value = 'server';
                    for (const option of form.elements.modified_multi.options) {
                        option.selected = option.value === 'gamma';
                    }
                    form.append(document.createElement('span'));
                }"""
            )

            implicit_single = page.locator("#session-shell-select-draft-probe [name='implicit_single']")
            disabled_leading_single = page.locator(
                "#session-shell-select-draft-probe [name='disabled_leading_single']"
            )
            disabled_group_single = page.locator(
                "#session-shell-select-draft-probe [name='disabled_group_single']"
            )
            listbox_single = page.locator("#session-shell-select-draft-probe [name='listbox_single']")
            duplicate_default_single = page.locator(
                "#session-shell-select-draft-probe [name='duplicate_default_single']"
            )
            default_multi = page.locator("#session-shell-select-draft-probe [name='default_multi']")
            modified_single = page.locator("#session-shell-select-draft-probe [name='modified_single']")
            modified_multi = page.locator("#session-shell-select-draft-probe [name='modified_multi']")
            expect(implicit_single).to_have_value("async")
            expect(disabled_leading_single).to_have_value("server")
            expect(disabled_group_single).to_have_value("server")
            expect(listbox_single).to_have_value("server")
            expect(duplicate_default_single).to_have_value("server")
            expect(default_multi).to_have_values(["beta"])
            expect(modified_single).to_have_value("user")
            expect(modified_multi).to_have_values(["alpha", "beta"])
        finally:
            page.close()
            browser.close()


def test_character_spell_search_posts_exact_identity_for_same_slug_entries(
    app,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
    monkeypatch,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    shared_slug = "shared-echo"
    first_key = f"dnd-5e|spell|phb|{shared_slug}"
    second_key = f"dnd-5e|spell|xge|{shared_slug}"
    shared_entries = [
        SimpleNamespace(
            entry_key=first_key,
            entry_type="spell",
            slug=shared_slug,
            title="Shared Echo",
            source_id="PHB",
            source_page="200",
            search_text="Shared Echo",
            metadata={"level": 1, "class_lists": {"PHB": ["Artificer"]}},
        ),
        SimpleNamespace(
            entry_key=second_key,
            entry_type="spell",
            slug=shared_slug,
            title="Shared Echo",
            source_id="XGE",
            source_page="200",
            search_text="Shared Echo",
            metadata={"level": 1, "class_lists": {"XGE": ["Artificer"]}},
        ),
    ]
    original_list_enabled = app_module._list_campaign_enabled_entries

    def _list_enabled(systems_service, campaign_slug, entry_type):
        if campaign_slug == "linden-pass" and entry_type == "spell":
            return list(shared_entries)
        return original_list_enabled(systems_service, campaign_slug, entry_type)

    monkeypatch.setattr(app_module, "_list_campaign_enabled_entries", _list_enabled)

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Artificer 5"
        profile["classes"] = [
            {"row_id": "class-row-1", "class_name": "Artificer", "level": 5}
        ]
        payload["profile"] = profile
        payload["source"] = {
            "source_path": "builder://same-slug-browser-regression",
            "source_type": "native_character_builder",
            "imported_from": "In-app Native Builder",
            "imported_at": "2026-08-13T00:00:00Z",
            "parse_warnings": [],
        }
        stats = dict(payload.get("stats") or {})
        stats["ability_scores"] = {
            "intelligence": {"score": 16, "modifier": 3},
        }
        payload["stats"] = stats
        payload["spellcasting"] = {
            "spellcasting_class": "Artificer",
            "spellcasting_ability": "Intelligence",
            "spell_save_dc": 14,
            "spell_attack_bonus": 6,
            "slot_progression": [
                {"level": 1, "max_slots": 4},
                {"level": 2, "max_slots": 2},
            ],
            "slot_lanes": [
                {
                    "id": "class-row-1-slots",
                    "title": "Artificer spell slots",
                    "shared": False,
                    "row_ids": ["class-row-1"],
                    "slot_progression": [
                        {"level": 1, "max_slots": 4},
                        {"level": 2, "max_slots": 2},
                    ],
                }
            ],
            "class_rows": [
                {
                    "class_row_id": "class-row-1",
                    "class_name": "Artificer",
                    "level": 5,
                    "caster_progression": "half",
                    "spell_mode": "prepared",
                    "spellcasting_ability": "Intelligence",
                    "spell_save_dc": 14,
                    "spell_attack_bonus": 6,
                    "slot_lane_id": "class-row-1-slots",
                }
            ],
            "spells": [
                {
                    "name": "Shared Echo",
                    "level": 1,
                    "mark": "Prepared",
                    "class_row_id": "class-row-1",
                    "systems_ref": {
                        "entry_key": first_key,
                        "entry_type": "spell",
                        "slug": shared_slug,
                        "title": "Shared Echo",
                        "source_id": "PHB",
                    },
                }
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)
    set_campaign_visibility("linden-pass", characters="players")
    base_url = character_read_shell_live_server

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["dm"])
            page.goto(
                f"{base_url}/campaigns/linden-pass/characters/arden-march"
                "?mode=read&page=spellcasting"
            )
            _wait_for_app_loading_cover(page)
            page.get_by_role("tab", name="Preparation").click()
            form = page.locator(
                "[data-character-spell-search-form]"
                "[data-character-spell-search-kind='spell']"
                "[data-character-spell-search-target-row='class-row-1']"
            ).first
            query = form.locator("[data-character-spell-query]")
            results = form.locator("[data-character-spell-results]")
            expect(query).to_be_visible(timeout=5000)

            with page.expect_response(
                lambda response: (
                    "/spellcasting/spells/search" in response.url
                    and "q=echo" in response.url
                ),
                timeout=5000,
            ):
                query.fill("echo")
            expect(results).not_to_be_disabled(timeout=5000)
            expect(results.locator("option")).to_have_count(1)
            expect(results.locator("option")).to_have_text(re.compile(r"Shared Echo.*XGE"))
            assert results.input_value() == second_key

            with page.expect_request(
                lambda request: (
                    request.method == "POST"
                    and request.url.endswith(
                        "/campaigns/linden-pass/characters/arden-march/spellcasting/add"
                    )
                ),
                timeout=5000,
            ) as request_info:
                form.locator("button[type='submit']").click()
            post_data = request_info.value.post_data or ""
            assert 'name="selected_value"' in post_data
            assert f"\r\n\r\n{second_key}\r\n" in post_data
            expect(page.locator("[data-flash-stack-root] .flash-success")).to_have_text(
                "Spell list updated.",
                timeout=5000,
            )
        finally:
            page.close()
            browser.close()

    updated = _read_character_definition(app, "arden-march")
    assert {
        str(dict(spell.get("systems_ref") or {}).get("entry_key") or "")
        for spell in list((updated.get("spellcasting") or {}).get("spells") or [])
    } == {first_key, second_key}


def test_session_character_shared_dialog_adopter_preserves_direct_lazy_and_mutation_contracts(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
    tmp_path,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    spell_entry = _seed_systems_spell_entry(
        app,
        slug="phb-spell-message",
        title="Message",
        rendered_html="<p>Session spell detail body from Systems.</p>",
    )

    def _link_session_details(payload: dict) -> None:
        spellcasting = dict(payload.get("spellcasting") or {})
        spells = list(spellcasting.get("spells") or [])
        assert spells
        spells[0] = {**dict(spells[0]), "systems_ref": _systems_ref(spell_entry)}
        spellcasting["spells"] = spells
        payload["spellcasting"] = spellcasting

        equipment_catalog = list(payload.get("equipment_catalog") or [])
        for index, item in enumerate(equipment_catalog):
            if str(item.get("id") or "") == "light-crossbow-1":
                equipment_catalog[index] = {
                    **dict(item),
                    "name": "Stormglass Compass",
                    "page_ref": "items/stormglass-compass",
                }
                break
        payload["equipment_catalog"] = equipment_catalog

    def _link_session_item_state(payload: dict) -> None:
        inventory = list(payload.get("inventory") or [])
        for index, item in enumerate(inventory):
            if str(item.get("catalog_ref") or item.get("id") or "") == "light-crossbow-1":
                inventory[index] = {
                    **dict(item),
                    "name": "Stormglass Compass",
                    "notes": "A campaign-linked Session item.",
                }
                break
        payload["inventory"] = inventory

    _write_character_definition(app, "arden-march", _link_session_details)
    _write_character_state(app, "arden-march", _link_session_item_state)
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302

    base_url = character_read_shell_live_server
    direct_url = (
        f"{base_url}/campaigns/linden-pass/session/character"
        "?character=arden-march&page=inventory"
    )

    def _assert_label(page, dialog) -> None:
        labelled_by = dialog.get_attribute("aria-labelledby")
        assert labelled_by
        assert page.locator(f"#{labelled_by}").count() == 1
        assert page.locator(f"#{labelled_by}").inner_text().strip()

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        desktop_context = browser.new_context(viewport={"width": 1280, "height": 900})
        desktop_page = desktop_context.new_page()
        try:
            _sign_in_browser(desktop_page, base_url, users["owner"])
            desktop_page.goto(direct_url)
            _wait_for_app_loading_cover(desktop_page)
            scope = desktop_page.locator("[data-session-character-workspace-root]")
            expect(scope).to_have_attribute(
                "data-session-character-presentation-dialog-state", "ready", timeout=5000
            )
            expect(scope.locator("[data-session-character-presentation-dialog-trigger-gate]")).to_have_count(0)
            expect(scope.locator("template[data-character-presentation-dialog-trigger-template]")).to_have_count(0)
            expect(desktop_page.locator("html")).to_have_class(re.compile(r"spell-modal-js"))
            expect(desktop_page.locator("html")).not_to_have_class(re.compile(r"app-loading"))
            desktop_page.evaluate("window.__sessionDialogNoReloadMarker = 'alive'")

            item_trigger = scope.locator("button.item-detail-button").first
            item_trigger_count = scope.locator("button.item-detail-button").count()
            item_fallback = scope.locator("details[data-character-spell-fallback]").first
            expect(item_trigger).to_be_visible(timeout=5000)
            expect(item_fallback).to_be_hidden(timeout=5000)
            item_trigger.click()
            item_dialog = scope.locator("dialog.item-detail-dialog[open]").first
            expect(item_dialog).to_be_visible(timeout=5000)
            _assert_label(desktop_page, item_dialog)
            expect(item_dialog.locator("[data-presentation-dialog-initial-focus]")).to_be_focused()
            item_dialog.get_by_role("button", name="Close").click()
            expect(item_trigger).to_be_focused(timeout=5000)

            item_trigger.click()
            expect(item_dialog).to_be_visible(timeout=5000)
            item_dialog.dispatch_event("click")
            expect(item_dialog).to_be_hidden(timeout=5000)
            expect(item_trigger).to_be_focused(timeout=5000)

            desktop_page.evaluate(
                "window.__playerWikiCombatWorkspace.init(document.querySelector('[data-session-character-workspace-root]'))"
            )
            expect(scope).to_have_attribute(
                "data-session-character-presentation-dialog-state", "ready"
            )
            assert scope.locator("button.item-detail-button").count() == item_trigger_count

            item_trigger.click()
            expect(item_dialog).to_be_visible(timeout=5000)
            assert item_dialog.evaluate("dialog => dialog.matches(':modal')")
            desktop_page.evaluate(
                "document.querySelector('[data-session-character-section-link=\"spells\"]').click()"
            )
            expect(
                desktop_page.locator(
                    "[data-session-character-section-root][data-session-character-section='spells']"
                )
            ).to_be_visible(timeout=5000)
            spell_trigger = scope.locator("[data-character-spell-modal-trigger]", has_text="Message").first
            expect(spell_trigger).to_be_visible(timeout=5000)
            spell_trigger.click()
            spell_dialog = scope.locator("dialog[data-presentation-dialog][open]", has_text="Message")
            expect(spell_dialog).to_be_visible(timeout=5000)
            _assert_label(desktop_page, spell_dialog)
            desktop_page.keyboard.press("Escape")
            expect(spell_dialog).to_be_hidden(timeout=5000)
            expect(spell_trigger).to_be_focused(timeout=5000)

            scope.locator("[data-session-character-section-link='inventory']").click()
            expect(
                desktop_page.locator(
                    "[data-session-character-section-root][data-session-character-section='inventory']"
                )
            ).to_be_visible(timeout=5000)
            expect(item_dialog).to_be_visible(timeout=5000)
            assert item_dialog.evaluate("dialog => dialog.matches(':modal')")
            restored_close_button = item_dialog.get_by_role("button", name="Close")
            expect(restored_close_button).to_be_focused(timeout=5000)
            restored_close_button.click()
            expect(item_dialog).to_be_hidden(timeout=5000)
            currency_field = scope.locator(
                "form[data-character-sheet-edit-form='currency'] input[data-session-currency-autosubmit='1']"
            ).first
            next_value = str(int(currency_field.input_value()) + 1)
            currency_field.fill(next_value)
            currency_field.dispatch_event("change")
            expect(desktop_page.locator("[data-session-character-flash-stack] .flash-success")).to_contain_text(
                "Currency updated.", timeout=5000
            )
            replacement_scope = desktop_page.locator("[data-session-character-workspace-root]")
            expect(replacement_scope).to_have_attribute(
                "data-session-character-presentation-dialog-state", "ready", timeout=5000
            )
            expect(replacement_scope.locator("button.item-detail-button").first).to_be_visible(timeout=5000)
            assert desktop_page.evaluate("window.__sessionDialogNoReloadMarker") == "alive"
            expect(desktop_page.locator("html")).not_to_have_class(re.compile(r"app-loading"))
            desktop_page.screenshot(path=str(tmp_path / "session_character_dialog_desktop.png"))
        finally:
            desktop_page.close()
            desktop_context.close()

        mobile_context = browser.new_context(viewport={"width": 390, "height": 800})
        mobile_page = mobile_context.new_page()
        try:
            _sign_in_browser(mobile_page, base_url, users["owner"])
            mobile_page.goto(f"{base_url}/campaigns/linden-pass/session")
            _wait_for_app_loading_cover(mobile_page)
            composer = mobile_page.locator("[data-session-composer-form] textarea")
            expect(composer).to_be_visible(timeout=5000)
            composer.fill("Preserve this Session draft while Character loads.")
            mobile_page.locator("[data-session-switch-target='character']").click()
            mobile_scope = mobile_page.locator("[data-session-character-workspace-root]")
            expect(mobile_scope).to_be_visible(timeout=5000)
            expect(composer).to_have_value("Preserve this Session draft while Character loads.")
            expect(mobile_page.locator("html")).not_to_have_class(re.compile(r"app-loading"))
            mobile_scope.locator("[data-session-character-section-link='spells']").click()
            expect(
                mobile_page.locator(
                    "[data-session-character-section-root][data-session-character-section='spells']"
                )
            ).to_be_visible(timeout=5000)
            expect(mobile_scope).to_have_attribute(
                "data-session-character-presentation-dialog-state", "ready", timeout=5000
            )
            mobile_spell_trigger = mobile_scope.locator(
                "[data-character-spell-modal-trigger]", has_text="Message"
            ).first
            expect(mobile_spell_trigger).to_be_visible(timeout=5000)
            mobile_spell_trigger.click()
            mobile_spell_dialog = mobile_scope.locator(
                "dialog[data-presentation-dialog][open]", has_text="Message"
            )
            expect(mobile_spell_dialog).to_be_visible(timeout=5000)
            mobile_spell_dialog.get_by_role("button", name="Close").click()
            expect(mobile_spell_trigger).to_be_focused(timeout=5000)
            mobile_page.screenshot(path=str(tmp_path / "session_character_dialog_mobile.png"))
        finally:
            mobile_page.close()
            mobile_context.close()

        no_js_context = browser.new_context(
            viewport={"width": 390, "height": 800}, java_script_enabled=False
        )
        no_js_page = no_js_context.new_page()
        try:
            _sign_in_browser(no_js_page, base_url, users["owner"])
            no_js_page.goto(direct_url)
            expect(no_js_page.locator("button.item-detail-button")).to_have_count(0)
            expect(no_js_page.locator("[data-character-spell-modal-trigger]")).to_have_count(0)
            fallback = no_js_page.locator(
                "[data-session-character-section='inventory'] details[data-character-spell-fallback]"
            ).first
            expect(fallback).to_be_visible(timeout=5000)
            fallback.locator("summary").click()
            expect(fallback.locator(".item-description-detail__body")).to_be_visible(timeout=5000)
            expect(no_js_page.get_by_role("link", name="Stormglass Compass").first).to_be_visible()
        finally:
            no_js_page.close()
            no_js_context.close()
            browser.close()


@pytest.mark.parametrize("initialization_mode", ["absent", "no-op", "throws"])
def test_session_character_dialog_adopter_fails_safe_when_shared_controller_is_unavailable(
    initialization_mode,
    app,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
    tmp_path,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    def _link_item(payload: dict) -> None:
        equipment_catalog = list(payload.get("equipment_catalog") or [])
        for index, item in enumerate(equipment_catalog):
            if str(item.get("id") or "") == "light-crossbow-1":
                equipment_catalog[index] = {
                    **dict(item),
                    "name": "Stormglass Compass",
                    "page_ref": "items/stormglass-compass",
                }
                break
        payload["equipment_catalog"] = equipment_catalog

    def _link_item_state(payload: dict) -> None:
        inventory = list(payload.get("inventory") or [])
        for index, item in enumerate(inventory):
            if str(item.get("catalog_ref") or item.get("id") or "") == "light-crossbow-1":
                inventory[index] = {**dict(item), "notes": "Fallback Session item details."}
                break
        payload["inventory"] = inventory

    _write_character_definition(app, "arden-march", _link_item)
    _write_character_state(app, "arden-march", _link_item_state)
    set_campaign_visibility("linden-pass", characters="players")
    base_url = character_read_shell_live_server
    if initialization_mode == "absent":
        controller_body = ""
    else:
        init_body = (
            'throw new Error("shared presentation initialization failed");'
            if initialization_mode == "throws"
            else "return 0;"
        )
        controller_body = f"""
          (() => {{
            window.__playerWikiPresentationController = Object.freeze({{
              init() {{ {init_body} }},
              openDialog() {{ return false; }},
              closeDialog() {{ return false; }},
            }});
          }})();
        """

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 390, "height": 800})
            page = context.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        page.route(
            "**/static/presentation-controller.js*",
            lambda route: route.fulfill(
                status=200, content_type="application/javascript", body=controller_body
            ),
        )
        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=inventory"
            )
            scope = page.locator("[data-session-character-workspace-root]")
            expect(scope.locator("details[data-character-spell-fallback]").first).to_be_visible(
                timeout=5000
            )
            expect(page.locator("html")).not_to_have_class(re.compile(r"spell-modal-js"))
            expect(page.locator("html")).not_to_have_class(re.compile(r"app-loading"))
            expect(scope.locator("[data-session-character-section-link='inventory']")).to_have_attribute(
                "aria-current", "page"
            )
            expect(
                scope.locator(
                    "[data-session-character-section-root][data-session-character-section='inventory']"
                )
            ).to_be_visible()

            fallback_summary = scope.locator(
                "[data-session-character-section='inventory'] "
                "details[data-character-spell-fallback] summary"
            ).first
            fallback_summary.focus()
            expect(fallback_summary).to_be_focused()
            scope.locator("[data-session-character-section-link='spells']").evaluate(
                "link => link.click()"
            )
            expect(
                page.locator(
                    "[data-session-character-section-root][data-session-character-section='spells']"
                )
            ).to_be_visible(timeout=5000)
            scope.locator("[data-session-character-section-link='inventory']").evaluate(
                "link => link.click()"
            )
            expect(
                page.locator(
                    "[data-session-character-section-root][data-session-character-section='inventory']"
                )
            ).to_be_visible(timeout=5000)
            expect(
                scope.locator(
                    "[data-session-character-section='inventory'] "
                    "details[data-character-spell-fallback] summary"
                ).first
            ).to_be_focused(timeout=5000)

            if initialization_mode == "absent":
                expect(scope).not_to_have_attribute(
                    "data-session-character-presentation-dialog-state", re.compile(".+")
                )
                expect(scope.locator("template[data-character-presentation-dialog-trigger-template]")).not_to_have_count(0)
                expect(scope.locator("[data-session-character-presentation-dialog-trigger-gate]")).to_have_count(0)
                expect(scope.locator("[data-character-spell-modal-trigger]")).to_have_count(0)
            else:
                expect(scope).to_have_attribute(
                    "data-session-character-presentation-dialog-state", "unavailable", timeout=5000
                )
                gate = scope.locator(
                    "[data-session-character-presentation-dialog-trigger-gate]"
                ).first
                expect(gate).to_have_attribute("hidden", "")
                trigger = gate.locator(
                    "[data-character-spell-modal-trigger][data-presentation-dialog-trigger]"
                )
                expect(trigger).to_have_count(1)
                assert trigger.evaluate("element => element.getClientRects().length") == 0
                expect(trigger).to_be_hidden()
            expect(scope.locator("dialog[data-presentation-dialog][open]")).to_have_count(0)
            page.screenshot(
                path=str(tmp_path / f"session_dialog_partial_controller_{initialization_mode}.png")
            )
        finally:
            page.close()
            context.close()
            browser.close()


@pytest.mark.parametrize("initialization_mode", ["no-op", "throws"])
def test_character_read_dialog_triggers_stay_gated_when_shared_initialization_fails(
    initialization_mode,
    app,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
    tmp_path,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    spell_entry = _seed_systems_spell_entry(
        app,
        slug="phb-spell-message",
        title="Message",
        rendered_html="<p>Character spell fallback remains available.</p>",
    )

    def _link_spell(payload: dict) -> None:
        spellcasting = dict(payload.get("spellcasting") or {})
        spells = list(spellcasting.get("spells") or [])
        assert spells
        spells[0] = {
            **dict(spells[0]),
            "systems_ref": _systems_ref(spell_entry),
        }
        spellcasting["spells"] = spells
        payload["spellcasting"] = spellcasting

    _write_character_definition(app, "arden-march", _link_spell)
    set_campaign_visibility("linden-pass", characters="players")
    base_url = character_read_shell_live_server
    init_body = (
        'throw new Error("shared presentation initialization failed");'
        if initialization_mode == "throws"
        else "return 0;"
    )
    controller_stub = f"""
      (() => {{
        window.__playerWikiPresentationController = Object.freeze({{
          init() {{ {init_body} }},
          openDialog() {{ return false; }},
          closeDialog() {{ return false; }},
        }});
      }})();
    """

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 390, "height": 800})
            page = context.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        page.route(
            "**/static/presentation-controller.js*",
            lambda route: route.fulfill(
                status=200,
                content_type="application/javascript",
                body=controller_stub,
            ),
        )
        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(
                f"{base_url}/campaigns/linden-pass/characters/arden-march?page=spellcasting"
            )

            shell = page.locator("[data-character-read-shell-root]")
            expect(shell).to_have_attribute(
                "data-character-presentation-dialog-state",
                "unavailable",
                timeout=5000,
            )
            expect(page.locator("html")).not_to_have_class(re.compile(r"spell-modal-js"))
            fallback = page.locator("details.spell-card__fallback").first
            expect(fallback).to_be_visible(timeout=5000)
            fallback.locator("summary").click()
            expect(fallback.locator(".spell-detail-content")).to_be_visible(timeout=5000)

            gate = page.locator("[data-character-presentation-dialog-trigger-gate]").first
            expect(gate).to_have_attribute("hidden", "")
            trigger = gate.locator(
                "[data-character-spell-modal-trigger][data-presentation-dialog-trigger]"
            )
            expect(trigger).to_have_count(1)
            assert trigger.evaluate("element => getComputedStyle(element).display") == "grid"
            assert trigger.evaluate("element => element.getClientRects().length") == 0
            expect(trigger).to_be_hidden()
            expect(page.locator("dialog[data-character-spell-modal][open]")).to_have_count(0)
            page.screenshot(
                path=str(tmp_path / f"character_dialog_partial_controller_{initialization_mode}.png")
            )
        finally:
            page.close()
            context.close()
            browser.close()


def test_session_character_panel_switch_and_resource_submit_stay_no_reload(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page.goto(f"{base_url}/sign-in")
            page.locator("input[name='email']").fill(users["owner"]["email"])
            page.locator("input[name='password']").fill(users["owner"]["password"])
            page.locator("button[type='submit']").click()
            page.wait_for_url(
                re.compile(rf"^{re.escape(base_url)}/.*"),
                timeout=5000,
            )

            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=overview"
            )
            expect(page.locator("[data-session-shell-active='character']")).to_be_visible(timeout=5000)
            expect(
                page.locator(
                    "[data-session-character-section-root][data-session-character-section='overview']"
                )
            ).to_be_visible(timeout=5000)
            expect(page.locator(".glance-grid--quick-row-1")).to_be_visible(timeout=5000)
            expect(page.locator("form[data-character-sheet-edit-form='vitals']")).to_have_count(3)
            page.evaluate("window.__sessionCharacterNoReloadMarker = 'alive'")
            session_pane = page.locator("[data-session-shell-pane='session']")
            expect(session_pane).to_have_attribute("data-session-shell-pane-loaded", "0")
            session_pane.evaluate("pane => { pane.dataset.lazyIdentity = 'preserved'; }")
            session_composer = page.locator(
                "[data-session-shell-pane='session'] [data-session-composer-form] textarea"
            )
            expect(session_composer).to_have_count(0)
            session_fragment_get_count = 0

            def count_session_fragment_get(request):
                nonlocal session_fragment_get_count
                if (
                    request.method == "GET"
                    and "/campaigns/linden-pass/session?fragment=1" in request.url
                ):
                    session_fragment_get_count += 1

            page.on("request", count_session_fragment_get)
            page.locator("[data-session-switch-target='session']").click()
            expect(page.locator("[data-session-shell-active='session']")).to_be_visible(timeout=5000)
            expect(session_composer).to_have_count(1)
            expect(session_pane).to_have_attribute("data-session-shell-pane-loaded", "1")
            assert session_fragment_get_count == 1
            assert session_pane.get_attribute("data-lazy-identity") == "preserved"
            assert session_pane.locator("[data-session-live-root]").evaluate(
                "root => window.__playerWikiSessionLive.snapshot(root) !== null"
            )
            session_message_post_count = 0
            session_composer_action = session_composer.locator(
                "xpath=ancestor::form"
            ).get_attribute("action")
            assert session_composer_action

            def count_session_message_post(request):
                nonlocal session_message_post_count
                if (
                    request.method == "POST"
                    and request.url.startswith(f"{base_url}{session_composer_action}")
                ):
                    session_message_post_count += 1

            page.on("request", count_session_message_post)
            session_composer.evaluate(
                """(field) => {
                    field.value = 'Keep this mounted Session draft.';
                    field.dispatchEvent(new Event('input', { bubbles: true }));
                }"""
            )
            page.locator("[data-session-switch-target='character']").click()
            expect(page.locator("[data-session-shell-active='character']")).to_be_visible(timeout=5000)
            assert session_pane.get_attribute("data-lazy-identity") == "preserved"

            hp_field = page.locator(
                "form[data-character-sheet-edit-form='vitals'][data-character-autosubmit-mode='focus-blur'] "
                "input[name='current_hp']"
            ).first
            expect(hp_field).to_be_visible(timeout=5000)
            hp_field.click()
            hp_field.press("Control+A")
            hp_field.press("Backspace")
            page.wait_for_timeout(700)
            expect(hp_field).to_have_value("")
            assert hp_field.evaluate("element => document.activeElement === element")
            hp_field.type("12", delay=75)
            page.wait_for_timeout(700)
            expect(hp_field).to_have_value("12")
            assert hp_field.evaluate("element => document.activeElement === element")
            hp_field.press("Enter")
            expect(page.locator("[data-session-character-flash-stack] .flash-success")).to_contain_text(
                "Vitals updated.",
                timeout=5000,
            )
            expect(hp_field).to_have_value("12", timeout=5000)
            assert hp_field.evaluate("element => document.activeElement === element")

            fragment_get_count = 0

            def count_character_fragment_get(request):
                nonlocal fragment_get_count
                if (
                    request.method == "GET"
                    and "/session/character" in request.url
                    and "fragment=1" in request.url
                ):
                    fragment_get_count += 1

            page.on("request", count_character_fragment_get)
            page.locator("[data-session-character-section-link='resources']").click()
            expect(
                page.locator(
                    "[data-session-character-section-root][data-session-character-section='resources']"
                )
            ).to_be_visible(timeout=5000)
            expect(
                page.locator("[data-session-character-section-link='resources']")
            ).to_be_focused(timeout=5000)
            assert fragment_get_count == 1

            page.locator("[data-session-character-section-link='overview']").click()
            expect(
                page.locator(
                    "[data-session-character-section-root][data-session-character-section='overview']"
                )
            ).to_be_visible(timeout=5000)
            assert fragment_get_count == 1
            page.locator("[data-session-character-section-link='resources']").click()
            expect(
                page.locator(
                    "[data-session-character-section-root][data-session-character-section='resources']"
                )
            ).to_be_visible(timeout=5000)
            assert fragment_get_count == 1
            resource_form = page.locator(
                "form[data-character-sheet-edit-form='resource']"
                "[data-character-sheet-edit-row-id='sorcery-points']"
            )
            expect(resource_form).to_be_visible(timeout=5000)
            resource_current = resource_form.locator("input[name='current']")
            held_resource_posts = []

            def hold_resource_post(route):
                if route.request.method == "POST":
                    held_resource_posts.append(route)
                else:
                    route.continue_()

            page.route("**/characters/arden-march/session/resources/*", hold_resource_post)
            resource_current.fill("4")
            deadline = time.monotonic() + 5
            while not held_resource_posts and time.monotonic() < deadline:
                page.wait_for_timeout(50)
            assert len(held_resource_posts) == 1
            page.locator("[data-session-switch-target='session']").click()
            expect(page.locator("[data-session-shell-active='character']")).to_be_visible(timeout=1000)
            expect(session_composer).to_have_value("Keep this mounted Session draft.")
            held_resource_post = held_resource_posts.pop()
            resource_response = held_resource_post.fetch()
            held_resource_post.fulfill(response=resource_response)
            expect(page.locator("[data-session-character-flash-stack] .flash-success")).to_contain_text(
                "Resource updated.",
                timeout=5000,
            )
            page.locator("[data-session-switch-target='session']").click()
            expect(page.locator("[data-session-shell-active='session']")).to_be_visible()
            session_composer.locator("xpath=ancestor::form").get_by_role(
                "button", name="Post to chat"
            ).click()
            expect(session_composer).to_have_value("", timeout=5000)
            expect(page.locator("[data-session-chat-card]")).to_contain_text(
                "Keep this mounted Session draft.", timeout=5000
            )
            page.wait_for_timeout(250)
            expect(session_composer).to_have_value("")
            assert session_message_post_count == 1
            page.locator("[data-session-switch-target='character']").click()
            expect(page.locator("[data-session-shell-active='character']")).to_be_visible(timeout=5000)
            expect(page.locator("[data-session-character-flash-stack] .flash-success")).to_contain_text(
                "Resource updated.",
                timeout=5000,
            )
            expect(resource_form.locator("input[name='current']")).to_have_value("4", timeout=5000)
            assert page.evaluate("window.__sessionCharacterNoReloadMarker") == "alive"
            expect(session_composer).to_have_value("")
            assert fragment_get_count == 1
            assert session_fragment_get_count == 1
            assert session_pane.get_attribute("data-lazy-identity") == "preserved"
            page.locator("[data-session-character-section-link='overview']").click()
            expect(
                page.locator(
                    "[data-session-character-section-root][data-session-character-section='overview']"
                )
            ).to_be_visible(timeout=5000)
            assert fragment_get_count == 2
            page.locator("[data-session-character-section-link='resources']").click()
            expect(
                page.locator(
                    "[data-session-character-section-root][data-session-character-section='resources']"
                )
            ).to_be_visible(timeout=5000)
            assert fragment_get_count == 2
            expect(page).to_have_url(
                re.compile(
                    rf"^{re.escape(base_url)}/campaigns/linden-pass/session/character"
                    r"\?character=arden-march&page=resources$"
                ),
                timeout=5000,
            )
            page.go_back(wait_until="commit")
            expect(
                page.locator(
                    "[data-session-character-section-root][data-session-character-section='overview']"
                )
            ).to_be_visible(timeout=5000)
            assert fragment_get_count == 2
            page.go_forward(wait_until="commit")
            expect(
                page.locator(
                    "[data-session-character-section-root][data-session-character-section='resources']"
                )
            ).to_be_visible(timeout=5000)
            assert fragment_get_count == 2

            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=spellcasting"
            )
            expect(
                page.locator(
                    "[data-session-character-section-root][data-session-character-section='spells']"
                )
            ).to_be_visible(timeout=5000)
            page.locator("[data-session-character-section-link='resources']").click()
            expect(
                page.locator(
                    "[data-session-character-section-root][data-session-character-section='resources']"
                )
            ).to_be_visible(timeout=5000)
            page.go_back(wait_until="commit")
            expect(page).to_have_url(re.compile(r"[?&]page=spellcasting(?:&|$)"), timeout=5000)
            expect(
                page.locator(
                    "[data-session-character-section-root][data-session-character-section='spells']"
                )
            ).to_be_visible(timeout=5000)

        finally:
            browser.close()


def test_session_character_manager_dm_pane_lazy_loads_once_and_preserves_outer_node(
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        dm_fragment_get_count = 0

        def count_dm_fragment_get(request):
            nonlocal dm_fragment_get_count
            if (
                request.method == "GET"
                and "/session/dm?" in request.url
                and "shell_fragment=1" in request.url
            ):
                dm_fragment_get_count += 1

        try:
            _sign_in_browser(page, base_url, users["dm"])
            page.on("request", count_dm_fragment_get)
            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=overview"
            )
            dm_pane = page.locator("[data-session-shell-pane='dm']")
            expect(dm_pane).to_have_attribute("data-session-shell-pane-loaded", "0")
            expect(dm_pane.locator("[data-session-live-view='dm']")).to_have_count(0)
            dm_pane.evaluate("pane => { pane.dataset.lazyIdentity = 'preserved'; }")

            page.locator("[data-session-switch-target='dm']").click()
            expect(page.locator("[data-session-shell-active='dm']")).to_be_visible(timeout=5000)
            expect(dm_pane.locator("[data-session-live-view='dm']")).to_be_visible(timeout=5000)
            expect(dm_pane.locator("#session-controls")).to_be_visible(timeout=5000)
            assert dm_fragment_get_count == 1
            assert dm_pane.get_attribute("data-lazy-identity") == "preserved"
            assert dm_pane.locator("[data-session-live-root]").evaluate(
                "root => window.__playerWikiSessionLive.snapshot(root) !== null"
            )

            page.locator("[data-session-switch-target='character']").click()
            expect(page.locator("[data-session-shell-active='character']")).to_be_visible(timeout=5000)
            page.locator("[data-session-switch-target='dm']").click()
            expect(page.locator("[data-session-shell-active='dm']")).to_be_visible(timeout=5000)
            assert dm_fragment_get_count == 1
            assert dm_pane.get_attribute("data-lazy-identity") == "preserved"
        finally:
            browser.close()


def test_session_character_no_js_switch_uses_full_session_href(
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(java_script_enabled=False)
            page = context.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=overview"
            )
            session_link = page.locator("[data-session-switch-target='session']")
            expect(session_link).to_have_attribute(
                "href",
                "/campaigns/linden-pass/session",
            )
            session_link.click()
            page.wait_for_url(f"{base_url}/campaigns/linden-pass/session", timeout=5000)
            expect(page.locator("[data-session-live-view='session']")).to_be_visible(timeout=5000)
        finally:
            context.close()
            browser.close()


def test_session_character_multiple_resource_autosubmits_serialize_before_section_switch(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        held_resource_posts = []
        resource_requests = []

        def hold_resource_post(route):
            if route.request.method == "POST":
                resource_requests.append(route.request)
                held_resource_posts.append(route)
                return
            route.continue_()

        def request_field(request, name):
            post_data = request.post_data or ""
            match = re.search(
                rf'name="{re.escape(name)}"\r?\n\r?\n([^\r\n]*)',
                post_data,
            )
            assert match is not None, post_data
            return match.group(1)

        page.route("**/characters/arden-march/session/resources/*", hold_resource_post)
        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=overview"
            )
            page.evaluate("window.__sessionCharacterMultiAutosubmitMarker = 'alive'")
            character_pane = page.locator("[data-session-shell-pane='character']")
            overview_link = character_pane.locator(
                "[data-session-character-section-link='overview']"
            )
            resources_link = character_pane.locator(
                "[data-session-character-section-link='resources']"
            )

            resources_link.click()
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='resources']"
                )
            ).to_be_visible(timeout=5000)
            overview_link.click()
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='overview']"
                )
            ).to_be_visible(timeout=5000)
            resources_link.click()
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='resources']"
                )
            ).to_be_visible(timeout=5000)

            first_form = character_pane.locator(
                "form[data-character-sheet-edit-form='resource']"
                "[data-character-sheet-edit-row-id='sorcery-points']"
            )
            second_form = character_pane.locator(
                "form[data-character-sheet-edit-form='resource']"
                "[data-character-sheet-edit-row-id='wild-die']"
            )
            first_current = first_form.locator("input[name='current']")
            second_current = second_form.locator("input[name='current']")
            expect(first_current).to_be_visible(timeout=5000)
            expect(second_current).to_be_visible(timeout=5000)

            def changed_value(field):
                current = int(field.input_value())
                minimum = int(field.get_attribute("min") or "0")
                return str(current - 1 if current > minimum else current + 1)

            first_next = changed_value(first_current)
            second_next = changed_value(second_current)
            initial_revision = first_form.locator(
                "input[name='expected_revision']"
            ).input_value()

            page.evaluate(
                """([firstField, firstValue, secondField, secondValue, overview]) => {
                    firstField.value = firstValue;
                    firstField.dispatchEvent(new Event('input', { bubbles: true }));
                    secondField.value = secondValue;
                    secondField.dispatchEvent(new Event('input', { bubbles: true }));
                    overview.click();
                }""",
                [
                    first_current.element_handle(),
                    first_next,
                    second_current.element_handle(),
                    second_next,
                    overview_link.element_handle(),
                ],
            )

            deadline = time.monotonic() + 2
            while len(held_resource_posts) < 1 and time.monotonic() < deadline:
                page.wait_for_timeout(25)
            assert len(held_resource_posts) == 1
            page.wait_for_timeout(600)
            assert len(held_resource_posts) == 1
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='resources']"
                )
            ).to_be_visible(timeout=1000)

            first_post = held_resource_posts.pop(0)
            first_post.fulfill(response=first_post.fetch())
            deadline = time.monotonic() + 5
            while len(held_resource_posts) < 1 and time.monotonic() < deadline:
                page.wait_for_timeout(25)
            assert len(held_resource_posts) == 1
            assert len(resource_requests) == 2
            assert resource_requests[0].url.endswith("/session/resources/sorcery-points")
            assert resource_requests[1].url.endswith("/session/resources/wild-die")
            assert request_field(resource_requests[0], "current") == first_next
            assert request_field(resource_requests[1], "current") == second_next
            assert request_field(resource_requests[0], "expected_revision") == initial_revision
            second_revision = request_field(resource_requests[1], "expected_revision")
            assert second_revision != initial_revision
            assert (
                character_pane.locator(
                    "form[data-character-sheet-edit-form='resource']"
                    "[data-character-sheet-edit-row-id='wild-die'] "
                    "input[name='expected_revision']"
                ).input_value()
                == second_revision
            )
            expect(
                character_pane.locator(
                    "form[data-character-sheet-edit-form='resource']"
                    "[data-character-sheet-edit-row-id='wild-die'] input[name='current']"
                )
            ).to_have_value(second_next)

            overview_link.click()
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='resources']"
                )
            ).to_be_visible(timeout=1000)

            second_post = held_resource_posts.pop(0)
            second_post.fulfill(response=second_post.fetch())
            expect(
                character_pane.locator("[data-session-character-flash-stack] .flash-success")
            ).to_contain_text("Resource updated.", timeout=5000)
            expect(
                character_pane.locator(
                    "form[data-character-sheet-edit-form='resource']"
                    "[data-character-sheet-edit-row-id='sorcery-points'] input[name='current']"
                )
            ).to_have_value(first_next)
            expect(
                character_pane.locator(
                    "form[data-character-sheet-edit-form='resource']"
                    "[data-character-sheet-edit-row-id='wild-die'] input[name='current']"
                )
            ).to_have_value(second_next)
            page.wait_for_timeout(600)
            assert len(resource_requests) == 2

            character_pane.locator(
                "[data-session-character-section-link='overview']"
            ).click()
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='overview']"
                )
            ).to_be_visible(timeout=5000)
            character_pane.locator(
                "[data-session-character-section-link='resources']"
            ).click()
            expect(
                character_pane.locator(
                    "form[data-character-sheet-edit-form='resource']"
                    "[data-character-sheet-edit-row-id='sorcery-points'] input[name='current']"
                )
            ).to_have_value(first_next, timeout=5000)
            expect(
                character_pane.locator(
                    "form[data-character-sheet-edit-form='resource']"
                    "[data-character-sheet-edit-row-id='wild-die'] input[name='current']"
                )
            ).to_have_value(second_next, timeout=5000)
            assert len(resource_requests) == 2
            assert page.evaluate("window.__sessionCharacterMultiAutosubmitMarker") == "alive"
        finally:
            browser.close()


def test_session_character_cached_switch_flushes_queued_autosubmit_once(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        held_resource_posts = []
        resource_post_count = 0

        def hold_resource_post(route):
            nonlocal resource_post_count
            if route.request.method == "POST":
                resource_post_count += 1
                held_resource_posts.append(route)
                return
            route.continue_()

        page.route("**/characters/arden-march/session/resources/*", hold_resource_post)
        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=overview"
            )
            page.evaluate("window.__sessionCharacterQueuedAutosubmitMarker = 'alive'")
            character_pane = page.locator("[data-session-shell-pane='character']")
            overview_link = character_pane.locator(
                "[data-session-character-section-link='overview']"
            )
            resources_link = character_pane.locator(
                "[data-session-character-section-link='resources']"
            )

            resources_link.click()
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='resources']"
                )
            ).to_be_visible(timeout=5000)
            overview_link.click()
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='overview']"
                )
            ).to_be_visible(timeout=5000)
            resources_link.click()
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='resources']"
                )
            ).to_be_visible(timeout=5000)

            resource_form = character_pane.locator(
                "form[data-character-sheet-edit-form='resource']"
                "[data-character-sheet-edit-row-id='sorcery-points']"
            )
            resource_current = resource_form.locator("input[name='current']")
            expect(resource_current).to_be_visible(timeout=5000)
            current_value = int(resource_current.input_value())
            minimum_value = int(resource_current.get_attribute("min") or "0")
            next_value = str(
                current_value - 1 if current_value > minimum_value else current_value + 1
            )
            resource_current.evaluate(
                """(field, value) => {
                    field.value = value;
                    field.dispatchEvent(new Event('input', { bubbles: true }));
                    document.querySelector(
                        "[data-session-character-section-link='overview']",
                    ).click();
                }""",
                next_value,
            )

            deadline = time.monotonic() + 2
            while not held_resource_posts and time.monotonic() < deadline:
                page.wait_for_timeout(25)
            assert len(held_resource_posts) == 1
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='resources']"
                )
            ).to_be_visible(timeout=1000)
            assert page.evaluate("window.__sessionCharacterQueuedAutosubmitMarker") == "alive"

            held_resource_post = held_resource_posts.pop()
            held_resource_post.fulfill(response=held_resource_post.fetch())
            expect(
                character_pane.locator("[data-session-character-flash-stack] .flash-success")
            ).to_contain_text("Resource updated.", timeout=5000)
            expect(
                character_pane.locator(
                    "form[data-character-sheet-edit-form='resource']"
                    "[data-character-sheet-edit-row-id='sorcery-points'] input[name='current']"
                )
            ).to_have_value(next_value, timeout=5000)
            page.wait_for_timeout(600)
            assert resource_post_count == 1
            assert page.evaluate("window.__sessionCharacterQueuedAutosubmitMarker") == "alive"

            character_pane.locator(
                "[data-session-character-section-link='overview']"
            ).click()
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='overview']"
                )
            ).to_be_visible(timeout=5000)
            character_pane.locator(
                "[data-session-character-section-link='resources']"
            ).click()
            expect(
                character_pane.locator(
                    "form[data-character-sheet-edit-form='resource']"
                    "[data-character-sheet-edit-row-id='sorcery-points'] input[name='current']"
                )
            ).to_have_value(next_value, timeout=5000)
            assert resource_post_count == 1
            assert page.evaluate("window.__sessionCharacterQueuedAutosubmitMarker") == "alive"
        finally:
            browser.close()


def test_session_character_rapid_switch_ignores_superseded_fragment_response(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302
    sign_in(users["owner"]["email"], users["owner"]["password"])
    fragment_bodies = {}
    for section in ("overview", "spells", "resources"):
        response = client.get(
            "/campaigns/linden-pass/session/character"
            f"?character=arden-march&page={section}&fragment=1"
        )
        assert response.status_code == 200
        fragment_bodies[section] = response.get_data(as_text=True)

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        page.add_init_script(
            """(() => {
                const NativeAbortController = window.AbortController;
                window.__sessionCharacterAbortCalls = 0;
                window.AbortController = class {
                    constructor() {
                        this.signal = new NativeAbortController().signal;
                    }
                    abort() {
                        window.__sessionCharacterAbortCalls += 1;
                    }
                };
            })();"""
        )
        held_spells = []
        held_generic_character = []
        hold_generic_character = False

        def route_character_fragment(route):
            request_url = route.request.url
            if "page=spells" in request_url:
                held_spells.append(route)
                return
            if "page=resources" in request_url:
                route.fulfill(
                    status=200,
                    content_type="text/html; charset=utf-8",
                    body=fragment_bodies["resources"],
                )
                return
            if hold_generic_character:
                held_generic_character.append(route)
                return
            route.continue_()

        page.route("**/session/character?*fragment=1*", route_character_fragment)
        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=overview"
            )
            page.evaluate("window.__sessionCharacterRaceMarker = 'alive'")

            page.locator("[data-session-character-section-link='spells']").click()
            deadline = time.monotonic() + 5
            while not held_spells and time.monotonic() < deadline:
                page.wait_for_timeout(50)
            assert len(held_spells) == 1
            page.locator("[data-session-character-section-link='resources']").click()
            expect(
                page.locator(
                    "[data-session-character-section-root][data-session-character-section='resources']"
                )
            ).to_be_visible(timeout=5000)
            expect(page).to_have_url(re.compile(r"[?&]page=resources(?:&|$)"), timeout=5000)
            assert page.evaluate("window.__sessionCharacterAbortCalls") >= 1

            held_spells.pop().fulfill(
                status=200,
                content_type="text/html; charset=utf-8",
                body=fragment_bodies["spells"],
            )
            page.wait_for_timeout(300)
            expect(
                page.locator(
                    "[data-session-character-section-root][data-session-character-section='resources']"
                )
            ).to_be_visible()
            expect(
                page.locator(
                    "[data-session-character-section-root][data-session-character-section='spells']"
                )
            ).to_have_count(0)
            assert page.evaluate("window.__sessionCharacterRaceMarker") == "alive"
            expect(page).to_have_url(re.compile(r"[?&]page=resources(?:&|$)"))

            page.locator("[data-session-character-section-link='spells']").click()
            deadline = time.monotonic() + 5
            while not held_spells and time.monotonic() < deadline:
                page.wait_for_timeout(50)
            assert len(held_spells) == 1
            page.locator("[data-session-switch-target='session']").click()
            expect(page.locator("[data-session-shell-active='session']")).to_be_visible(timeout=5000)
            held_spells.pop().fulfill(
                status=200,
                content_type="text/html; charset=utf-8",
                body=fragment_bodies["spells"],
            )
            page.wait_for_timeout(300)
            expect(page.locator("[data-session-shell-active='session']")).to_be_visible()
            expect(
                page.locator(
                    "[data-session-shell-pane='character'] "
                    "[data-session-character-section-root][data-session-character-section='resources']"
                )
            ).to_have_count(1)

            generic_page = context.new_page()
            hold_generic_character = True
            generic_page.route("**/session/character?*fragment=1*", route_character_fragment)
            try:
                generic_page.goto(f"{base_url}/campaigns/linden-pass/session")
                expect(generic_page.locator("[data-session-shell-active='session']")).to_be_visible(
                    timeout=5000
                )
                generic_page.locator("[data-session-switch-target='character']").click()
                deadline = time.monotonic() + 5
                while not held_generic_character and time.monotonic() < deadline:
                    generic_page.wait_for_timeout(50)
                assert len(held_generic_character) == 1
                generic_page.locator("[data-session-switch-target='session']").click()
                expect(generic_page.locator("[data-session-shell-active='session']")).to_be_visible()
                held_generic_character.pop().fulfill(
                    status=200,
                    content_type="text/html; charset=utf-8",
                    body=fragment_bodies["overview"],
                )
                generic_page.wait_for_timeout(300)
                expect(generic_page.locator("[data-session-shell-active='session']")).to_be_visible()
                expect(
                    generic_page.locator(
                        "[data-session-shell-pane='character'] [data-session-character-fragment-root]"
                    )
                ).to_have_count(0)
            finally:
                generic_page.close()
        finally:
            page.close()
            context.close()
            browser.close()


def test_session_currency_change_submits_once_after_character_fragment_replacement(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    _configure_xianxia_campaign(app)
    set_campaign_visibility("linden-pass", characters="public", session="public")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    create_response = client.post(
        "/campaigns/linden-pass/characters/new",
        data={
            **_valid_xianxia_create_data("Currency Crane"),
            "character_slug": "currency-crane",
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    with app.app_context():
        AuthStore().upsert_character_assignment(
            users["owner"]["id"],
            "linden-pass",
            "currency-crane",
        )
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=currency-crane&page=inventory"
            )
            currency_field_selector = (
                "form[data-character-sheet-edit-form='currency'] "
                "input[data-session-currency-autosubmit='1']"
            )
            currency_field = page.locator(currency_field_selector).first
            expect(currency_field).to_be_visible(timeout=5000)

            currency_post_count = 0

            def count_currency_post(request):
                nonlocal currency_post_count
                if (
                    request.method == "POST"
                    and request.url.endswith(
                        "/campaigns/linden-pass/characters/currency-crane/session/currency"
                    )
                ):
                    currency_post_count += 1

            page.on("request", count_currency_post)
            first_value = str(int(currency_field.input_value()) + 1)
            currency_field.fill("-1")
            currency_field.dispatch_event("change")
            page.wait_for_timeout(300)
            assert currency_post_count == 0

            currency_field.fill(first_value)
            currency_field.dispatch_event("change")
            expect(page.locator("[data-session-character-flash-stack] .flash-success")).to_contain_text(
                "Currency updated.",
                timeout=5000,
            )
            expect(page.locator(currency_field_selector).first).to_have_value(
                first_value,
                timeout=5000,
            )
            page.wait_for_timeout(300)
            assert currency_post_count == 1

            currency_post_count = 0
            currency_field = page.locator(currency_field_selector).first
            second_value = str(int(first_value) + 1)
            currency_field.fill(second_value)
            currency_field.dispatch_event("change")
            expect(page.locator("[data-session-character-flash-stack] .flash-success")).to_contain_text(
                "Currency updated.",
                timeout=5000,
            )
            expect(page.locator(currency_field_selector).first).to_have_value(
                second_value,
                timeout=5000,
            )
            page.wait_for_timeout(300)
            assert currency_post_count == 1
        finally:
            browser.close()


def test_session_dnd_currency_change_submits_once(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=inventory"
            )
            currency_field_selector = (
                "form[data-character-sheet-edit-form='currency'] "
                "input[data-session-currency-autosubmit='1']"
            )
            currency_field = page.locator(currency_field_selector).first
            expect(currency_field).to_be_visible(timeout=5000)

            currency_post_count = 0

            def count_currency_post(request):
                nonlocal currency_post_count
                if (
                    request.method == "POST"
                    and request.url.endswith(
                        "/campaigns/linden-pass/characters/arden-march/session/currency"
                    )
                ):
                    currency_post_count += 1

            page.on("request", count_currency_post)
            next_value = str(int(currency_field.input_value()) + 1)
            currency_field.fill("-1")
            currency_field.dispatch_event("change")
            page.wait_for_timeout(300)
            assert currency_post_count == 0

            currency_field.fill(next_value)
            currency_field.dispatch_event("change")
            expect(page.locator("[data-session-character-flash-stack] .flash-success")).to_contain_text(
                "Currency updated.",
                timeout=5000,
            )
            expect(page.locator(currency_field_selector).first).to_have_value(
                next_value,
                timeout=5000,
            )
            page.wait_for_timeout(300)
            assert currency_post_count == 1
        finally:
            browser.close()


def test_session_dnd_currency_synchronous_duplicate_change_submits_once(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=inventory"
            )
            currency_action = (
                f"{base_url}/campaigns/linden-pass/characters/arden-march/session/currency"
            )
            currency_field_selector = (
                "form[data-character-sheet-edit-form='currency'] "
                "input[data-session-currency-autosubmit='1']"
            )
            currency_field = page.locator(currency_field_selector).first
            expect(currency_field).to_be_visible(timeout=5000)

            currency_post_count = 0

            def count_currency_post(request):
                nonlocal currency_post_count
                if request.method == "POST" and request.url == currency_action:
                    currency_post_count += 1

            def delay_currency_post(route):
                time.sleep(0.4)
                route.continue_()

            page.on("request", count_currency_post)
            page.route(currency_action, delay_currency_post)

            next_value = str(int(currency_field.input_value()) + 1)
            currency_field.evaluate(
                """(field, value) => {
                    field.value = value;
                    field.dispatchEvent(new Event("change", { bubbles: true }));
                    field.dispatchEvent(new Event("change", { bubbles: true }));
                }""",
                next_value,
            )

            expect(page.locator("[data-session-character-flash-stack] .flash-success")).to_contain_text(
                "Currency updated.",
                timeout=5000,
            )
            expect(page.locator(currency_field_selector).first).to_have_value(
                next_value,
                timeout=5000,
            )
            page.wait_for_timeout(300)
            assert currency_post_count == 1
        finally:
            browser.close()


@pytest.mark.parametrize("failure_mode", ["non_ok", "rejected"])
def test_session_dnd_currency_failure_retains_safe_session_fragment_with_guidance(
    failure_mode,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["owner"])
            safe_session_url = (
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=inventory"
            )
            currency_action = (
                f"{base_url}/campaigns/linden-pass/characters/arden-march/session/currency"
            )
            page.goto(safe_session_url)
            page.evaluate("window.__sessionCharacterFailureMarker = 'alive'")
            currency_field_selector = (
                "form[data-character-sheet-edit-form='currency'] "
                "input[data-session-currency-autosubmit='1']"
            )
            currency_field = page.locator(currency_field_selector).first
            expect(currency_field).to_be_visible(timeout=5000)

            attempted_post_count = 0
            unsafe_get_count = 0
            safe_get_count = 0

            def track_currency_requests(request):
                nonlocal attempted_post_count, unsafe_get_count, safe_get_count
                if request.method == "GET" and request.url == safe_session_url:
                    safe_get_count += 1
                elif request.url == currency_action and request.method == "POST":
                    attempted_post_count += 1
                elif request.url == currency_action and request.method == "GET":
                    unsafe_get_count += 1

            def fail_currency_post(route):
                if failure_mode == "non_ok":
                    route.fulfill(status=503, body="temporary failure")
                else:
                    route.abort("failed")

            page.on("request", track_currency_requests)
            page.route(currency_action, fail_currency_post)

            next_value = str(int(currency_field.input_value()) + 1)
            currency_field.fill(next_value)
            currency_field.dispatch_event("change")

            expect(page.locator("[data-session-character-section-status]")).to_contain_text(
                "save result could not be confirmed",
                timeout=5000,
            )
            expect(page.locator(currency_field_selector).first).to_be_visible(timeout=5000)
            expect(page.locator(currency_field_selector).first).to_have_value(next_value)
            expect(
                page.locator(
                    "[data-session-character-section-root][data-session-character-section='inventory']"
                )
            ).to_be_visible()
            expect(page.get_by_text("Method Not Allowed")).to_have_count(0)
            assert page.url == safe_session_url
            assert page.evaluate("window.__sessionCharacterFailureMarker") == "alive"
            assert attempted_post_count == 1
            assert safe_get_count == 0
            assert unsafe_get_count == 0
        finally:
            browser.close()


def test_session_character_lifecycle_invalidates_held_lazy_get_before_commit(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302
    sign_in(users["owner"]["email"], users["owner"]["password"])
    fragment_response = client.get(
        "/campaigns/linden-pass/session/character"
        "?character=arden-march&page=overview&fragment=1"
    )
    assert fragment_response.status_code == 200
    fragment_body = fragment_response.get_data(as_text=True)

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        held_lazy_gets = []
        lazy_get_count = 0

        def hold_first_lazy_get(route):
            nonlocal lazy_get_count
            lazy_get_count += 1
            if lazy_get_count == 1:
                held_lazy_gets.append(route)
                return
            route.continue_()

        page.route("**/session/character?*fragment=1*", hold_first_lazy_get)
        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(f"{base_url}/campaigns/linden-pass/session")
            page.evaluate("window.__sessionCharacterLazyLifecycleMarker = 'alive'")
            page.locator("[data-session-switch-target='character']").click()
            deadline = time.monotonic() + 5
            while not held_lazy_gets and time.monotonic() < deadline:
                page.wait_for_timeout(25)
            assert len(held_lazy_gets) == 1

            page.locator("[data-session-shell-pane='session']").evaluate(
                """(pane) => pane.dispatchEvent(new CustomEvent(
                    'playerWiki:session-state-changed',
                    { bubbles: true, detail: { stateToken: 'lazy-generation-2' } },
                ))"""
            )
            held_lazy_gets.pop().fulfill(
                status=200,
                content_type="text/html; charset=utf-8",
                body=fragment_body,
            )
            page.wait_for_timeout(250)
            expect(page.locator("[data-session-shell-active='session']")).to_be_visible()
            expect(
                page.locator(
                    "[data-session-shell-pane='character'] [data-session-character-fragment-root]"
                )
            ).to_have_count(0)
            assert page.evaluate("window.__sessionCharacterLazyLifecycleMarker") == "alive"

            page.locator("[data-session-switch-target='character']").click()
            expect(page.locator("[data-session-shell-active='character']")).to_be_visible(timeout=5000)
            expect(
                page.locator(
                    "[data-session-character-section-root][data-session-character-section='overview']"
                )
            ).to_be_visible(timeout=5000)
            assert lazy_get_count == 2
            assert page.evaluate("window.__sessionCharacterLazyLifecycleMarker") == "alive"
        finally:
            browser.close()


def test_session_character_lifecycle_invalidates_held_post_before_commit_and_stale_clear(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        held_resource_posts = []
        resource_post_count = 0
        fresh_fragment_get_count = 0

        def hold_resource_post(route):
            nonlocal resource_post_count
            if route.request.method == "POST":
                resource_post_count += 1
                held_resource_posts.append(route)
                return
            route.continue_()

        def count_fresh_fragment(request):
            nonlocal fresh_fragment_get_count
            if (
                request.method == "GET"
                and "/session/character" in request.url
                and "page=resources" in request.url
                and "fragment=1" in request.url
            ):
                fresh_fragment_get_count += 1

        page.route("**/characters/arden-march/session/resources/*", hold_resource_post)
        page.on("request", count_fresh_fragment)
        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=resources"
            )
            page.evaluate("window.__sessionCharacterPostLifecycleMarker = 'alive'")
            character_pane = page.locator("[data-session-shell-pane='character']")
            resource_form = character_pane.locator(
                "form[data-character-sheet-edit-form='resource']"
                "[data-character-sheet-edit-row-id='sorcery-points']"
            )
            resource_current = resource_form.locator("input[name='current']")
            expect(resource_current).to_be_visible(timeout=5000)
            current_value = int(resource_current.input_value())
            minimum_value = int(resource_current.get_attribute("min") or "0")
            next_value = str(
                current_value - 1 if current_value > minimum_value else current_value + 1
            )
            resource_current.fill(next_value)
            resource_form.evaluate(
                """(form) => {
                    window.clearTimeout(Number(form.dataset.characterAutosubmitTimer || '0'));
                    form.dataset.characterAutosubmitTimer = '0';
                    form.requestSubmit();
                }"""
            )
            deadline = time.monotonic() + 5
            while not held_resource_posts and time.monotonic() < deadline:
                page.wait_for_timeout(25)
            assert len(held_resource_posts) == 1
            expect(resource_form).to_have_attribute("aria-busy", "true")

            page.locator("[data-session-shell-pane='session']").evaluate(
                """(pane) => pane.dispatchEvent(new CustomEvent(
                    'playerWiki:session-state-changed',
                    { bubbles: true, detail: { stateToken: 'post-generation-2' } },
                ))"""
            )
            held_resource_post = held_resource_posts.pop()
            held_resource_post.fulfill(response=held_resource_post.fetch())
            expect(resource_form).not_to_have_attribute("aria-busy", "true", timeout=5000)
            expect(character_pane).to_have_attribute("data-session-shell-pane-stale", "1")
            expect(character_pane).to_have_attribute("data-session-shell-pane-loaded", "0")
            expect(
                character_pane.locator("[data-session-character-flash-stack] .flash-success")
            ).to_have_count(0)
            assert resource_post_count == 1
            assert page.evaluate("window.__sessionCharacterPostLifecycleMarker") == "alive"

            page.locator("[data-session-switch-target='session']").click()
            expect(page.locator("[data-session-shell-active='session']")).to_be_visible(timeout=5000)
            page.locator("[data-session-switch-target='character']").click()
            expect(page.locator("[data-session-shell-active='character']")).to_be_visible(timeout=5000)
            expect(
                character_pane.locator(
                    "form[data-character-sheet-edit-form='resource']"
                    "[data-character-sheet-edit-row-id='sorcery-points'] input[name='current']"
                )
            ).to_have_value(next_value, timeout=5000)
            assert fresh_fragment_get_count == 1
            assert resource_post_count == 1
            assert page.evaluate("window.__sessionCharacterPostLifecycleMarker") == "alive"
        finally:
            browser.close()


def test_session_character_failed_popstate_read_reconciles_url_to_mounted_section(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302

    base_url = character_read_shell_live_server
    overview_url = (
        f"{base_url}/campaigns/linden-pass/session/character"
        "?character=arden-march&page=overview"
    )
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        failed_resource_get_count = 0

        def fail_resource_popstate_get(route):
            nonlocal failed_resource_get_count
            failed_resource_get_count += 1
            route.fulfill(
                status=503,
                content_type="text/html; charset=utf-8",
                headers={"Retry-After": "2", "Cache-Control": "no-store"},
                body="<h1>Session Character section temporarily unavailable</h1>",
            )

        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=resources"
            )
            page.evaluate("window.__sessionCharacterPopstateMarker = 'alive'")
            session_composer = page.locator(
                "[data-session-shell-pane='session'] [data-session-composer-form] textarea"
            )
            expect(session_composer).to_have_count(0)
            page.locator("[data-session-switch-target='session']").click()
            expect(page.locator("[data-session-shell-active='session']")).to_be_visible(timeout=5000)
            expect(session_composer).to_have_count(1)
            session_composer.evaluate(
                """(field) => {
                    field.value = 'Keep popstate failure draft.';
                    field.dispatchEvent(new Event('input', { bubbles: true }));
                }"""
            )
            page.locator("[data-session-switch-target='character']").click()
            expect(page.locator("[data-session-shell-active='character']")).to_be_visible(timeout=5000)
            character_pane = page.locator("[data-session-shell-pane='character']")
            character_pane.locator(
                "[data-session-character-section-link='overview']"
            ).click()
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='overview']"
                )
            ).to_be_visible(timeout=5000)

            hp_form = character_pane.locator(
                "form[data-character-sheet-edit-form='vitals']"
                "[data-character-autosubmit-mode='focus-blur']"
            ).filter(has=page.locator("input[name='current_hp']")).first
            hp_field = hp_form.locator("input[name='current_hp']")
            current_hp = int(hp_field.input_value())
            hp_field.fill(str(current_hp - 1 if current_hp > 0 else current_hp + 1))
            hp_field.press("Enter")
            expect(
                character_pane.locator("[data-session-character-flash-stack] .flash-success")
            ).to_contain_text("Vitals updated.", timeout=5000)
            expect(page).to_have_url(overview_url)

            page.route(
                "**/session/character?*page=resources*fragment=1*",
                fail_resource_popstate_get,
            )
            page.go_back(wait_until="commit")
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='overview']"
                )
            ).to_be_visible(timeout=5000)
            expect(page).to_have_url(overview_url, timeout=5000)
            expect(session_composer).to_have_value("Keep popstate failure draft.")
            assert failed_resource_get_count == 1
            assert page.evaluate("window.__sessionCharacterPopstateMarker") == "alive"
        finally:
            browser.close()


def test_session_character_aborted_read_clears_busy_before_cached_fragment_reuse(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302
    sign_in(users["owner"]["email"], users["owner"]["password"])
    spells_response = client.get(
        "/campaigns/linden-pass/session/character"
        "?character=arden-march&page=spells&fragment=1"
    )
    assert spells_response.status_code == 200
    spells_body = spells_response.get_data(as_text=True)

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        page.add_init_script(
            """(() => {
                const NativeAbortController = window.AbortController;
                window.__sessionCharacterBusyAbortCalls = 0;
                window.AbortController = class {
                    constructor() {
                        this.signal = new NativeAbortController().signal;
                    }
                    abort() {
                        window.__sessionCharacterBusyAbortCalls += 1;
                    }
                };
            })();"""
        )
        held_spells = []

        def hold_spells_get(route):
            held_spells.append(route)

        page.route("**/session/character?*page=spells*fragment=1*", hold_spells_get)
        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=overview"
            )
            character_pane = page.locator("[data-session-shell-pane='character']")
            character_pane.locator(
                "[data-session-character-section-link='resources']"
            ).click()
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='resources']"
                )
            ).to_be_visible(timeout=5000)
            character_pane.locator(
                "[data-session-character-section-link='overview']"
            ).click()
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='overview']"
                )
            ).to_be_visible(timeout=5000)
            character_pane.locator(
                "[data-session-character-section-link='resources']"
            ).click()
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='resources']"
                )
            ).to_be_visible(timeout=5000)

            character_pane.locator(
                "[data-session-character-section-link='spells']"
            ).click()
            deadline = time.monotonic() + 5
            while not held_spells and time.monotonic() < deadline:
                page.wait_for_timeout(25)
            assert len(held_spells) == 1
            expect(
                character_pane.locator("[data-session-character-section-nav]")
            ).to_have_attribute("aria-busy", "true")
            character_pane.locator(
                "[data-session-character-section-link='overview']"
            ).click()
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='overview']"
                )
            ).to_be_visible(timeout=5000)
            expect(
                character_pane.locator("[data-session-character-section-nav]")
            ).not_to_have_attribute("aria-busy", "true")

            held_spells.pop().fulfill(
                status=200,
                content_type="text/html; charset=utf-8",
                body=spells_body,
            )
            page.wait_for_timeout(200)
            character_pane.locator(
                "[data-session-character-section-link='resources']"
            ).click()
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='resources']"
                )
            ).to_be_visible(timeout=5000)
            expect(
                character_pane.locator("[data-session-character-section-nav]")
            ).not_to_have_attribute("aria-busy", "true")
            assert page.evaluate("window.__sessionCharacterBusyAbortCalls") >= 1
        finally:
            page.close()
            context.close()
            browser.close()


def test_session_character_cached_fragment_does_not_replay_success_flash(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=resources"
            )
            page.evaluate("window.__sessionCharacterFlashCacheMarker = 'alive'")
            character_pane = page.locator("[data-session-shell-pane='character']")
            resource_form = character_pane.locator(
                "form[data-character-sheet-edit-form='resource']"
                "[data-character-sheet-edit-row-id='sorcery-points']"
            )
            resource_current = resource_form.locator("input[name='current']")
            current_value = int(resource_current.input_value())
            minimum_value = int(resource_current.get_attribute("min") or "0")
            next_value = str(
                current_value - 1 if current_value > minimum_value else current_value + 1
            )
            resource_current.fill(next_value)
            resource_form.evaluate(
                """(form) => {
                    window.clearTimeout(Number(form.dataset.characterAutosubmitTimer || '0'));
                    form.dataset.characterAutosubmitTimer = '0';
                    form.requestSubmit();
                }"""
            )
            expect(
                character_pane.locator("[data-session-character-flash-stack] .flash-success")
            ).to_contain_text("Resource updated.", timeout=5000)

            character_pane.locator(
                "[data-session-character-section-link='overview']"
            ).click()
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='overview']"
                )
            ).to_be_visible(timeout=5000)
            character_pane.locator(
                "[data-session-character-section-link='resources']"
            ).click()
            expect(
                character_pane.locator(
                    "form[data-character-sheet-edit-form='resource']"
                    "[data-character-sheet-edit-row-id='sorcery-points'] input[name='current']"
                )
            ).to_have_value(next_value, timeout=5000)
            expect(
                character_pane.locator("[data-session-character-flash-stack] .flash-success")
            ).to_have_count(0)
            assert page.evaluate("window.__sessionCharacterFlashCacheMarker") == "alive"
        finally:
            browser.close()


def test_session_character_conflict_full_document_mounts_only_canonical_fragment_and_get_url(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302
    sign_in(users["owner"]["email"], users["owner"]["password"])
    safe_session_path = (
        "/campaigns/linden-pass/session/character"
        "?character=arden-march&page=inventory"
    )
    full_document_response = client.get(safe_session_path)
    assert full_document_response.status_code == 200
    full_document_html = full_document_response.get_data(as_text=True)
    assert "data-session-shell-root" in full_document_html
    assert "data-session-character-fragment-root" in full_document_html

    base_url = character_read_shell_live_server
    safe_session_url = f"{base_url}{safe_session_path}"
    currency_action = (
        f"{base_url}/campaigns/linden-pass/characters/arden-march/session/currency"
    )
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        unsafe_get_count = 0
        unsafe_405_count = 0
        canonical_fragment_get_count = 0

        def track_character_requests(request):
            nonlocal unsafe_get_count, canonical_fragment_get_count
            if request.method != "GET":
                return
            if request.url.startswith(currency_action):
                unsafe_get_count += 1
            elif (
                "/campaigns/linden-pass/session/character" in request.url
                and "character=arden-march" in request.url
                and "page=inventory" in request.url
                and "fragment=1" in request.url
            ):
                canonical_fragment_get_count += 1

        def track_character_responses(response):
            nonlocal unsafe_405_count
            if response.request.method == "GET" and response.url.startswith(currency_action):
                if response.status == 405:
                    unsafe_405_count += 1

        def return_full_document_conflict(route):
            route.fulfill(
                status=409,
                content_type="text/html; charset=utf-8",
                body=full_document_html,
            )

        page.on("request", track_character_requests)
        page.on("response", track_character_responses)
        page.route(currency_action, return_full_document_conflict)
        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(safe_session_url)
            page.evaluate("window.__sessionCharacterConflictMarker = 'alive'")
            character_pane = page.locator("[data-session-shell-pane='character']")
            currency_field = character_pane.locator(
                "form[data-character-sheet-edit-form='currency'] "
                "input[data-session-currency-autosubmit='1']"
            ).first
            expect(currency_field).to_be_visible(timeout=5000)

            currency_field.fill(str(int(currency_field.input_value()) + 1))
            currency_field.dispatch_event("change")
            expect(
                character_pane.locator(":scope > [data-session-character-fragment-root]")
            ).to_have_count(1, timeout=5000)
            expect(character_pane.locator("[data-session-shell-root]")).to_have_count(0)
            expect(character_pane.locator("[data-session-live-root]")).to_have_count(0)
            expect(character_pane.locator("[data-session-shell-pane='session']")).to_have_count(0)
            assert page.url == safe_session_url
            assert page.evaluate("window.__sessionCharacterConflictMarker") == "alive"

            character_pane.locator(
                "[data-session-character-section-link='overview']"
            ).click()
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='overview']"
                )
            ).to_be_visible(timeout=5000)
            page.go_back(wait_until="commit")
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='inventory']"
                )
            ).to_be_visible(timeout=5000)
            assert page.url == safe_session_url

            page.locator("[data-session-shell-pane='session']").evaluate(
                """(pane) => pane.dispatchEvent(new CustomEvent(
                    'playerWiki:session-state-changed',
                    { bubbles: true, detail: { stateToken: 'conflict-regression' } },
                ))"""
            )
            page.locator("[data-session-switch-target='session']").click()
            expect(page.locator("[data-session-shell-active='session']")).to_be_visible(timeout=5000)
            page.locator("[data-session-switch-target='character']").click()
            expect(page.locator("[data-session-shell-active='character']")).to_be_visible(timeout=5000)
            expect(
                character_pane.locator(
                    "[data-session-character-section-root][data-session-character-section='inventory']"
                )
            ).to_be_visible(timeout=5000)
            assert page.evaluate("window.__sessionCharacterConflictMarker") == "alive"
            assert canonical_fragment_get_count == 1
            assert unsafe_get_count == 0
            assert unsafe_405_count == 0
        finally:
            browser.close()


def test_session_character_reloads_after_session_started_from_another_session_pane(
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page.goto(f"{base_url}/sign-in")
            page.locator("input[name='email']").fill(users["owner"]["email"])
            page.locator("input[name='password']").fill(users["owner"]["password"])
            page.locator("button[type='submit']").click()
            page.wait_for_url(
                re.compile(rf"^{re.escape(base_url)}/.*"),
                timeout=5000,
            )

            page.goto(
                f"{base_url}/campaigns/linden-pass/session/character"
                "?character=arden-march&page=overview"
            )
            expect(page.locator("[data-session-shell-active='character']")).to_be_visible(timeout=5000)
            expect(page.locator("form[data-character-sheet-edit-form='vitals']")).to_have_count(0)

            page.locator("[data-session-switch-target='session']").click()
            expect(page.locator("[data-session-shell-active='session']")).to_be_visible(timeout=5000)

            sign_in(users["dm"]["email"], users["dm"]["password"])
            client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

            expect(page.locator("[data-session-status-card]")).to_contain_text(
                "The session is live for players and the DM.",
                timeout=6000,
            )

            page.locator("[data-session-switch-target='character']").click()
            expect(page.locator("[data-session-shell-active='character']")).to_be_visible(timeout=5000)
            expect(page.locator("form[data-character-sheet-edit-form='vitals']")).to_have_count(3)
            expect(page.locator("text=Save current HP")).to_have_count(0)
            expect(page.locator("text=Save temp HP")).to_have_count(0)
            expect(page.locator("form[data-character-sheet-edit-form='vitals'][data-character-autosubmit]")).to_have_count(3)
        finally:
            browser.close()


def test_feedback_item44_browser_header_combat_spells_and_session_chrome(
    app,
    client,
    sign_in,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    def _mutate(payload: dict) -> None:
        profile = dict(payload.get("profile") or {})
        profile["class_level_text"] = "Sorcerer 5"
        profile["classes"] = [{"class_name": "Sorcerer", "level": 5}]
        payload["profile"] = profile
        payload["spellcasting"] = {
            "spellcasting_class": "Sorcerer",
            "spellcasting_ability": "Charisma",
            "spell_save_dc": 15,
            "spell_attack_bonus": 7,
            "slot_progression": [
                {"level": 1, "max_slots": 4},
                {"level": 2, "max_slots": 3},
                {"level": 3, "max_slots": 2},
            ],
            "spells": [
                {
                    "name": "Message",
                    "level": 0,
                    "school": "Transmutation",
                    "casting_time": "1 action",
                    "range": "120 feet",
                    "source": "Sorcerer",
                },
                {
                    "name": "Magic Missile",
                    "level": 1,
                    "school": "Evocation",
                    "casting_time": "1 action",
                    "range": "120 feet",
                    "mark": "Known",
                    "source": "Sorcerer",
                },
                {
                    "name": "Misty Step",
                    "level": 2,
                    "school": "Conjuration",
                    "casting_time": "1 bonus action",
                    "range": "Self",
                    "mark": "Known",
                    "source": "Sorcerer",
                },
            ],
        }

    _write_character_definition(app, "arden-march", _mutate)
    set_campaign_visibility("linden-pass", characters="players")
    sign_in(users["dm"]["email"], users["dm"]["password"])
    client.post(
        "/campaigns/linden-pass/combat/player-combatants",
        data={"character_slug": "arden-march", "turn_value": 18},
        follow_redirects=False,
    )
    client.post("/campaigns/linden-pass/session/start", follow_redirects=False)

    base_url = character_read_shell_live_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page.goto(f"{base_url}/sign-in")
            page.locator("input[name='email']").fill(users["owner"]["email"])
            page.locator("input[name='password']").fill(users["owner"]["password"])
            page.locator("button[type='submit']").click()
            page.wait_for_url(re.compile(rf"^{re.escape(base_url)}/.*"), timeout=5000)

            page.goto(f"{base_url}/campaigns/linden-pass/combat")
            _wait_for_app_loading_cover(page)
            expect(page.locator(".site-header__campaign")).to_have_text(
                "Echoes of the Alloy Coast",
                timeout=5000,
            )
            expect(page.locator(".site-header__campaign-title")).to_be_visible()
            header_metrics = page.evaluate(
                """() => {
                    const primary = document.querySelector(".site-header__primary").getBoundingClientRect();
                    const actions = document.querySelector(".site-header__actions").getBoundingClientRect();
                    const title = document.querySelector(".site-header__campaign-title").getBoundingClientRect();
                    const titleStyle = getComputedStyle(document.querySelector(".site-header__campaign-title"));
                    return {
                        gapCenter: (primary.right + actions.left) / 2,
                        titleCenter: (title.left + title.right) / 2,
                        backgroundImage: titleStyle.backgroundImage,
                        borderTopStyle: titleStyle.borderTopStyle,
                    };
                }"""
            )
            assert abs(header_metrics["gapCenter"] - header_metrics["titleCenter"]) <= 2
            assert header_metrics["backgroundImage"] != "none"
            assert header_metrics["borderTopStyle"] == "solid"
            expect(page.locator("h1")).to_have_text("Combat", timeout=5000)

            page.locator("[data-combat-section-toggle='spells']").click()
            spells_panel = page.locator("[data-combat-section-panel='spells']")
            expect(spells_panel).to_be_visible(timeout=5000)
            expect(spells_panel.locator(".combat-spell-slot-row")).to_have_count(3)
            expect(spells_panel.locator("text=Use 1")).to_have_count(0)
            expect(spells_panel.locator("text=Restore 1")).to_have_count(0)
            expect(spells_panel.get_by_role("heading", name="Cantrips")).to_be_visible()
            expect(spells_panel.get_by_role("heading", name="1st level")).to_be_visible()
            expect(spells_panel.get_by_role("heading", name="2nd level")).to_be_visible()
            column_count = spells_panel.locator(".combat-spell-slot-list").evaluate(
                """(element) => getComputedStyle(element).gridTemplateColumns.split(" ").length"""
            )
            assert column_count == 3

            page.goto(f"{base_url}/campaigns/linden-pass/session")
            _wait_for_app_loading_cover(page)
            expect(page.locator(".site-header__campaign")).to_have_text(
                "Echoes of the Alloy Coast",
                timeout=5000,
            )
            expect(page.locator("h1")).to_have_text("Session", timeout=5000)
            expect(page.locator("#session-chat-compose")).to_be_visible()
            expect(page.locator("textarea[name='body']")).to_be_visible()
            expect(page.locator("text=Post to chat")).to_be_visible()
            expect(page.locator("text=Search and choose a player-visible wiki article")).to_have_count(0)
            expect(page.locator("text=Live session tools")).to_have_count(0)
        finally:
            browser.close()


def test_session_clear_revealed_confirmation_preserves_dialog_async_and_transport_contracts(
    app,
    client,
    sign_in,
    users,
    character_read_shell_live_server,
    monkeypatch,
    tmp_path,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302
    for article_number, title in enumerate(
        ("First revealed contract", "Second revealed contract", "Staged contract guard"),
        start=1,
    ):
        assert client.post(
            "/campaigns/linden-pass/session/articles",
            data={"title": title, "body_markdown": f"Body for {title}."},
            follow_redirects=False,
        ).status_code == 302
        if article_number < 3:
            assert client.post(
                f"/campaigns/linden-pass/session/articles/{article_number}/reveal",
                follow_redirects=False,
            ).status_code == 302

    service = app.extensions["campaign_session_service"]
    original_clear = service.delete_revealed_articles
    reject_next_clear = {"value": True}

    def controlled_clear(*args, **kwargs):
        if reject_next_clear["value"]:
            reject_next_clear["value"] = False
            raise CampaignSessionValidationError("Known clear validation outcome.")
        return original_clear(*args, **kwargs)

    monkeypatch.setattr(service, "delete_revealed_articles", controlled_clear)
    base_url = character_read_shell_live_server
    clear_pattern = "**/campaigns/linden-pass/session/articles/clear-revealed"

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["dm"])
            page.goto(f"{base_url}/campaigns/linden-pass/session")
            _wait_for_app_loading_cover(page)
            page.evaluate("document.documentElement.dataset.theme = 'parchment'")
            expect(page.locator("html")).to_have_attribute("data-theme", "parchment")

            composer = page.locator("form[data-session-composer-form] textarea[name='body']")
            expect(composer).to_be_visible(timeout=5000)
            composer.fill("Keep this unrelated Session draft through the clear workflow.")
            page.locator("[data-session-switch-target='dm']").click()

            dm_pane = page.locator("[data-session-shell-pane='dm']")
            expect(dm_pane).to_be_visible(timeout=5000)
            dm_pane.locator("[data-session-dm-switch-target='revealed']").click()
            expect(dm_pane.locator("[data-session-dm-pane='revealed']")).to_be_visible(
                timeout=5000
            )

            confirmation = page.locator(
                "[data-session-revealed-root] [data-destructive-confirmation]"
            )
            trigger = confirmation.locator("[data-presentation-dialog-trigger]")
            dialog = confirmation.locator("dialog[data-destructive-confirmation-dialog]")
            scope = confirmation.locator("[data-destructive-confirmation-scope]")
            recovery = confirmation.locator("[data-destructive-confirmation-recovery]")
            expect(confirmation).to_have_count(1, timeout=5000)
            expect(confirmation).to_have_attribute("data-destructive-confirmation-risk", "higher")
            expect(trigger).to_be_visible(timeout=5000)

            trigger.click()
            expect(dialog).to_have_attribute("open", "")
            expect(dialog.get_by_role("button", name="Cancel").first).to_be_focused()
            expect(scope).to_contain_text("all 2 revealed session articles")
            expect(scope).to_contain_text("related reveal chat and log entries")
            expect(scope).to_contain_text("Staged articles remain unchanged.")
            dialog.get_by_role("button", name="Cancel").first.click()
            expect(trigger).to_be_focused(timeout=5000)

            trigger.click()
            page.keyboard.press("Escape")
            expect(dialog).not_to_have_attribute("open", "")
            expect(trigger).to_be_focused(timeout=5000)
            trigger.click()
            dialog.dispatch_event("click")
            expect(dialog).not_to_have_attribute("open", "")
            expect(trigger).to_be_focused(timeout=5000)

            trigger.click()
            form = dialog.locator("form[data-destructive-confirmation-form]")
            acknowledgement = form.locator("input[name='destructive_acknowledgement']")
            submit = form.locator("button[type='submit']")
            expect(acknowledgement).to_have_attribute("required", "")
            assert form.evaluate("element => element.checkValidity()") is False
            submit.click()
            expect(form).to_have_attribute("aria-busy", "false")
            expect(recovery).to_be_hidden()

            acknowledgement.check()
            desktop_scroll_y = page.evaluate("window.scrollY")
            submit.click()
            expect(page.locator("[data-flash-stack-root] [data-feedback]")).to_contain_text(
                "Known clear validation outcome.", timeout=5000
            )
            expect(page.locator("[data-session-revealed-root] [data-destructive-confirmation]")).to_have_count(1)
            confirmation = page.locator(
                "[data-session-revealed-root] [data-destructive-confirmation]"
            )
            trigger = confirmation.locator("[data-presentation-dialog-trigger]")
            expect(trigger).to_be_visible(timeout=5000)
            expect(confirmation.locator("[data-destructive-confirmation-recovery]")).to_be_hidden()
            assert abs(page.evaluate("window.scrollY") - desktop_scroll_y) <= 2
            _check_no_horizontal_overflow(
                page,
                "[data-session-revealed-root] [data-destructive-confirmation]",
                "session-clear-desktop-1280x900",
                required=True,
            )
            expect(page.locator("html.app-loading, html.app-loading-closing")).to_have_count(0)
            page.screenshot(
                path=str(tmp_path / "session_clear_confirmation_1280x900_parchment.png")
            )

            page.set_viewport_size({"width": 390, "height": 800})
            page.evaluate("document.documentElement.dataset.theme = 'moonlit'")
            expect(page.locator("html")).to_have_attribute("data-theme", "moonlit")
            expect(trigger).to_be_visible(timeout=5000)
            trigger.click()
            dialog = confirmation.locator("dialog[data-destructive-confirmation-dialog]")
            form = dialog.locator("form[data-destructive-confirmation-form]")
            acknowledgement = form.locator("input[name='destructive_acknowledgement']")
            assert form.get_attribute("data-session-async") is None
            acknowledgement.check()
            dialog.get_by_role("button", name="Cancel").first.click()
            page.locator("[data-session-switch-target='session']").click()
            expect(page.locator("[data-session-shell-active='session']")).to_be_visible(
                timeout=5000
            )
            page.locator("[data-session-switch-target='dm']").click()
            expect(page.locator("[data-session-shell-active='dm']")).to_be_visible(
                timeout=5000
            )
            confirmation = page.locator(
                "[data-session-revealed-root] [data-destructive-confirmation]"
            )
            trigger = confirmation.locator("[data-presentation-dialog-trigger]")
            dialog = confirmation.locator("dialog[data-destructive-confirmation-dialog]")
            form = dialog.locator("form[data-destructive-confirmation-form]")
            acknowledgement = form.locator("input[name='destructive_acknowledgement']")
            expect(acknowledgement).to_be_checked()
            trigger.click()

            failure_handlers = (
                lambda route: route.fulfill(
                    status=503, content_type="text/plain", body="Unavailable"
                ),
                lambda route: route.abort("failed"),
                lambda route: route.fulfill(
                    status=200, content_type="application/json", body="not-json"
                ),
            )
            for route_handler in failure_handlers:
                page.route(clear_pattern, route_handler)
                form.locator("button[type='submit']").click()
                recovery = dialog.locator("[data-destructive-confirmation-recovery]")
                expect(recovery).to_be_visible(timeout=5000)
                expect(recovery).to_be_focused()
                expect(recovery).to_have_text(
                    "The result could not be confirmed. Refresh Session before repeating this action."
                )
                expect(acknowledgement).to_be_checked()
                expect(form).to_have_attribute("aria-busy", "false")
                expect(form.locator("button[type='submit']")).to_be_enabled()
                expect(page.locator("html.app-loading, html.app-loading-closing")).to_have_count(0)
                page.unroute(clear_pattern)

            _check_no_horizontal_overflow(
                page,
                "[data-session-revealed-root] [data-destructive-confirmation]",
                "session-clear-mobile-390x800",
                required=True,
            )
            expect(composer).to_have_value(
                "Keep this unrelated Session draft through the clear workflow."
            )
            page.screenshot(path=str(tmp_path / "session_clear_confirmation_390x800_moonlit.png"))

            dialog.get_by_role("button", name="Cancel").first.click()
            page.locator("[data-session-switch-target='session']").click()
            expect(page.locator("[data-session-shell-active='session']")).to_be_visible(
                timeout=5000
            )
            page.locator("[data-session-switch-target='dm']").click()
            expect(page.locator("[data-session-shell-active='dm']")).to_be_visible(
                timeout=5000
            )
            confirmation = page.locator(
                "[data-session-revealed-root] [data-destructive-confirmation]"
            )
            trigger = confirmation.locator("[data-presentation-dialog-trigger]")
            dialog = confirmation.locator("dialog[data-destructive-confirmation-dialog]")
            form = dialog.locator("form[data-destructive-confirmation-form]")
            acknowledgement = form.locator("input[name='destructive_acknowledgement']")
            expect(acknowledgement).to_be_checked()
            trigger.click()
            form.locator("button[type='submit']").click()
            expect(page.locator("[data-flash-stack-root] [data-feedback]")).to_contain_text(
                "Cleared 2 revealed session articles.", timeout=5000
            )
            expect(page.locator("[data-session-revealed-root] [data-destructive-confirmation]")).to_have_count(0)

            replacement_title = "Replacement revealed contract"
            assert client.post(
                "/campaigns/linden-pass/session/articles",
                data={"title": replacement_title, "body_markdown": "Replacement body."},
                follow_redirects=False,
            ).status_code == 302
            with app.app_context():
                replacement_article = next(
                    article
                    for article in service.list_articles("linden-pass")
                    if article.title == replacement_title
                )
            assert client.post(
                f"/campaigns/linden-pass/session/articles/{replacement_article.id}/reveal",
                follow_redirects=False,
            ).status_code == 302
            page.evaluate("window.dispatchEvent(new Event('pageshow'))")
            replacement_confirmation = page.locator(
                "[data-session-revealed-root] [data-destructive-confirmation]"
            )
            expect(replacement_confirmation).to_have_count(1, timeout=5000)
            replacement_acknowledgement = replacement_confirmation.locator(
                "input[name='destructive_acknowledgement']"
            )
            expect(replacement_acknowledgement).not_to_be_checked()

            page.locator("[data-session-switch-target='session']").click()
            expect(page.locator("[data-session-shell-active='session']")).to_be_visible(
                timeout=5000
            )
            page.locator("[data-session-switch-target='dm']").click()
            expect(page.locator("[data-session-shell-active='dm']")).to_be_visible(
                timeout=5000
            )
            expect(replacement_acknowledgement).not_to_be_checked()
            dm_pane.locator("[data-session-dm-switch-target='staged']").click()
            staged_pane = dm_pane.locator("[data-session-dm-pane='staged']")
            expect(staged_pane).to_be_visible(timeout=5000)
            expect(staged_pane).to_contain_text("Staged contract guard")
            expect(page.locator("html.app-loading, html.app-loading-closing")).to_have_count(0)
            page.locator("[data-session-switch-target='session']").click()
            expect(composer).to_be_visible(timeout=5000)
            expect(composer).to_have_value(
                "Keep this unrelated Session draft through the clear workflow."
            )
        finally:
            page.close()
            browser.close()


def test_session_clear_revealed_confirmation_keeps_no_javascript_form(
    client,
    sign_in,
    users,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302
    assert client.post(
        "/campaigns/linden-pass/session/articles",
        data={"title": "No-JavaScript revealed article", "body_markdown": "Native clear target."},
        follow_redirects=False,
    ).status_code == 302
    assert client.post(
        "/campaigns/linden-pass/session/articles/1/reveal", follow_redirects=False
    ).status_code == 302
    assert client.post(
        "/campaigns/linden-pass/session/articles",
        data={"title": "No-JavaScript staged guard", "body_markdown": "Keep this staged."},
        follow_redirects=False,
    ).status_code == 302
    base_url = character_read_shell_live_server

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                java_script_enabled=False,
                viewport={"width": 390, "height": 800},
            )
            page = context.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["dm"])
            page.goto(f"{base_url}/campaigns/linden-pass/session/dm?dm_view=revealed")
            fallback = page.locator(
                "[data-session-revealed-root] details[data-destructive-confirmation-fallback]"
            )
            expect(fallback).to_be_visible(timeout=5000)
            fallback.locator("summary").click()
            form = fallback.locator("form")
            expect(form).to_have_attribute(
                "action", "/campaigns/linden-pass/session/articles/clear-revealed"
            )
            expect(form).to_have_attribute("method", "post")
            expect(fallback).to_contain_text("This removes all 1 revealed session article")
            expect(fallback).to_contain_text("Staged articles remain unchanged.")
            _check_no_horizontal_overflow(
                page,
                "[data-session-revealed-root] details[data-destructive-confirmation-fallback]",
                "session-clear-no-js-390x800",
                required=True,
            )
            acknowledgement = form.locator("input[name='destructive_acknowledgement']")
            expect(acknowledgement).to_have_attribute("required", "")
            acknowledgement.check()
            form.locator("button[type='submit']").click()
            page.wait_for_url(
                re.compile(
                    r".*/campaigns/linden-pass/session/dm\?dm_view=revealed#session-revealed-articles$"
                ),
                timeout=5000,
            )
            expect(page.locator("[data-flash-stack-root] [data-feedback]")).to_contain_text(
                "Cleared 1 revealed session article."
            )
            expect(page.locator("[data-session-revealed-root]")).not_to_contain_text(
                "No-JavaScript revealed article"
            )
            page.goto(f"{base_url}/campaigns/linden-pass/session/dm?dm_view=staged")
            expect(page.locator("[data-session-staged-root]")).to_contain_text(
                "No-JavaScript staged guard"
            )
        finally:
            page.close()
            context.close()
            browser.close()


def test_session_composer_feedback_preserves_state_across_success_validation_and_transport(
    app,
    client,
    sign_in,
    users,
    character_read_shell_live_server,
    monkeypatch,
    tmp_path,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302
    service = app.extensions["campaign_session_service"]
    original_post_message = service.post_message
    delayed_message = "Hold this draft while the async request is pending."

    def post_message_with_controlled_delay(*args, **kwargs):
        if kwargs.get("body_text") == delayed_message:
            time.sleep(1.25)
        return original_post_message(*args, **kwargs)

    monkeypatch.setattr(service, "post_message", post_message_with_controlled_delay)

    base_url = character_read_shell_live_server
    session_message_pattern = "**/campaigns/linden-pass/session/messages"
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(f"{base_url}/campaigns/linden-pass/session")
            _wait_for_app_loading_cover(page)
            page.evaluate("document.documentElement.dataset.theme = 'parchment'")
            expect(page.locator("html")).to_have_attribute("data-theme", "parchment")
            expect(page.locator("h1")).to_have_count(1)

            form = page.locator("form[data-session-composer-form]")
            textarea = form.locator("textarea[name='body']")
            local_feedback = form.locator("[data-session-form-feedback]")
            global_feedback = page.locator("[data-flash-stack-root] [data-feedback]")
            expect(form).to_have_attribute(
                "aria-describedby",
                "session-chat-compose-feedback",
            )

            invalid_draft = "x" * 4001
            textarea.fill(invalid_draft)
            textarea.scroll_into_view_if_needed()
            textarea.evaluate("element => { element.focus(); element.setSelectionRange(37, 61); }")
            validation_scroll_y = page.evaluate("window.scrollY")
            form.evaluate("element => element.requestSubmit()")

            expect(local_feedback).to_contain_text(
                "Session chat messages must stay under 4,000 characters.",
                timeout=5000,
            )
            expect(local_feedback.locator("[data-feedback]")).to_have_attribute(
                "data-feedback-placement",
                "persistent",
            )
            expect(local_feedback.locator("[data-feedback]")).to_have_class(
                re.compile(r"\bfeedback--persistent\b"),
            )
            expect(local_feedback.locator("[data-feedback]")).to_have_attribute(
                "aria-live",
                "assertive",
            )
            expect(form).to_have_attribute("aria-invalid", "true")
            expect(textarea).to_have_value(invalid_draft)
            assert textarea.evaluate("element => document.activeElement === element")
            assert textarea.evaluate("element => [element.selectionStart, element.selectionEnd]") == [37, 61]
            assert abs(page.evaluate("window.scrollY") - validation_scroll_y) <= 2
            expect(global_feedback).to_have_count(0)
            expect(page.locator("html.app-loading, html.app-loading-closing")).to_have_count(0)
            page.screenshot(path=str(tmp_path / "session_composer_validation_1280x900_parchment.png"))

            textarea.fill("Keyboard-submitted success from the desktop matrix.")
            submit_button = form.locator("button[type='submit']")
            submit_button.focus()
            submit_button.press("Enter")
            expect(page.locator("[data-flash-stack-root] [data-feedback]")).to_have_text(
                "Message posted.",
                timeout=5000,
            )
            expect(page.locator("[data-flash-stack-root] [data-feedback]")).to_have_attribute(
                "aria-live",
                "polite",
            )
            form = page.locator("form[data-session-composer-form]")
            textarea = form.locator("textarea[name='body']")
            expect(textarea).to_have_value("")
            assert textarea.evaluate("element => document.activeElement === element")
            expect(form.locator("[data-session-form-feedback] [data-feedback]")).to_have_count(0)
            assert form.get_attribute("aria-invalid") is None

            textarea.fill(delayed_message)
            textarea.evaluate("element => { element.focus(); element.setSelectionRange(10, 24); }")
            form.evaluate("element => element.requestSubmit()")
            expect(form).to_have_attribute("aria-busy", "true", timeout=500)
            expect(form.locator("button[type='submit']")).to_be_disabled()
            expect(textarea).to_have_value(delayed_message)
            assert textarea.evaluate("element => [element.selectionStart, element.selectionEnd]") == [10, 24]
            expect(page.locator("html.app-loading, html.app-loading-closing")).to_have_count(0)
            expect(page.locator("form[data-session-composer-form]")).not_to_have_attribute(
                "aria-busy",
                "true",
                timeout=5000,
            )
            expect(page.locator("form[data-session-composer-form] textarea[name='body']")).to_have_value("")

            transport_failures = (
                (
                    "HTTP",
                    lambda route: route.fulfill(
                        status=503,
                        content_type="text/plain",
                        body="Unavailable",
                    ),
                ),
                ("network", lambda route: route.abort("failed")),
            )
            for failure_label, route_handler in transport_failures:
                form = page.locator("form[data-session-composer-form]")
                textarea = form.locator("textarea[name='body']")
                transport_draft = f"Keep this draft through an unavailable {failure_label} transport."
                textarea.fill(transport_draft)
                textarea.evaluate("element => { element.focus(); element.setSelectionRange(8, 19); }")
                transport_scroll_y = page.evaluate("window.scrollY")
                page.route(session_message_pattern, route_handler)
                form.evaluate("element => element.requestSubmit()")
                expect(form.locator("button[type='submit']")).to_be_enabled(timeout=5000)
                assert form.get_attribute("aria-busy") is None
                expect(textarea).to_have_value(transport_draft)
                assert textarea.evaluate("element => document.activeElement === element")
                assert textarea.evaluate("element => [element.selectionStart, element.selectionEnd]") == [8, 19]
                assert abs(page.evaluate("window.scrollY") - transport_scroll_y) <= 2
                expect(form.locator("[data-session-form-feedback] [data-feedback]")).to_have_count(0)
                expect(page.locator("[data-flash-stack-root] [data-feedback]")).to_have_text(
                    "Message posted."
                )
                page.unroute(session_message_pattern)

            page.set_viewport_size({"width": 390, "height": 800})
            page.evaluate("document.documentElement.dataset.theme = 'moonlit'")
            expect(page.locator("html")).to_have_attribute("data-theme", "moonlit")
            textarea.fill(invalid_draft)
            textarea.scroll_into_view_if_needed()
            textarea.evaluate("element => { element.focus(); element.setSelectionRange(101, 125); }")
            mobile_scroll_y = page.evaluate("window.scrollY")
            form.evaluate("element => element.requestSubmit()")
            expect(form.locator("[data-session-form-feedback] [data-feedback]")).to_contain_text(
                "Session chat messages must stay under 4,000 characters.",
                timeout=5000,
            )
            expect(page.locator("[data-flash-stack-root] [data-feedback]")).to_have_count(0)
            expect(textarea).to_have_value(invalid_draft)
            assert textarea.evaluate("element => document.activeElement === element")
            assert textarea.evaluate("element => [element.selectionStart, element.selectionEnd]") == [101, 125]
            assert abs(page.evaluate("window.scrollY") - mobile_scroll_y) <= 2
            document_width = page.evaluate(
                "(document.scrollingElement || document.documentElement).scrollWidth"
            )
            assert document_width <= 392
            expect(page.locator("h1")).to_have_count(1)
            expect(page.locator("html.app-loading, html.app-loading-closing")).to_have_count(0)
            page.screenshot(path=str(tmp_path / "session_composer_validation_390x800_moonlit.png"))
        finally:
            page.close()
            browser.close()


def test_session_composer_feedback_keeps_no_javascript_fallback(
    client,
    sign_in,
    users,
    character_read_shell_live_server,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    sign_in(users["dm"]["email"], users["dm"]["password"])
    assert client.post("/campaigns/linden-pass/session/start", follow_redirects=False).status_code == 302
    base_url = character_read_shell_live_server

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                java_script_enabled=False,
                viewport={"width": 390, "height": 800},
            )
            page = context.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            _sign_in_browser(page, base_url, users["owner"])
            page.goto(f"{base_url}/campaigns/linden-pass/session")
            form = page.locator("form[data-session-composer-form]")
            expect(form).to_be_visible(timeout=5000)
            form.locator("textarea[name='body']").fill("Native no-JavaScript session message.")
            form.locator("button[type='submit']").click()
            page.wait_for_url(
                re.compile(r".*/campaigns/linden-pass/session#session-chat-compose$"),
                timeout=5000,
            )
            expect(page.locator("[data-flash-stack-root] [data-feedback]")).to_have_text(
                "Message posted."
            )
            expect(page.locator("[data-session-chat-card]")).to_contain_text(
                "Native no-JavaScript session message."
            )
            expect(page.locator("h1")).to_have_count(1)
            expect(page.locator("form[data-session-composer-form] textarea[name='body']")).to_have_value("")
        finally:
            page.close()
            context.close()
            browser.close()


def test_character_read_shell_browser_state_and_save_flow(
    app,
    users,
    set_campaign_visibility,
    character_read_shell_live_server,
    tmp_path,
):
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        pytest.skip(f"Playwright unavailable: {exc}")

    set_campaign_visibility("linden-pass", characters="players")
    base_url = character_read_shell_live_server
    arden_character_slug_path = f"{base_url}/campaigns/linden-pass/characters/arden-march"
    notes_url_pattern = re.compile(
        r"^.*/campaigns/linden-pass/characters/arden-march\?.*page=notes.*$"
    )
    personal_url_pattern = re.compile(
        r"^.*/campaigns/linden-pass/characters/arden-march\?.*page=personal.*$"
    )
    portrait_url_pattern = re.compile(
        r"^.*/campaigns/linden-pass/characters/arden-march\?.*page=portrait.*$"
    )

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
        except Exception as exc:
            pytest.skip(f"Playwright browser unavailable: {exc}")

        try:
            page.goto(f"{base_url}/sign-in")
            page.locator("input[name='email']").fill(users["owner"]["email"])
            page.locator("input[name='password']").fill(users["owner"]["password"])
            page.locator("button[type='submit']").click()
            page.wait_for_url(
                re.compile(rf"^{re.escape(base_url)}/.*"),
                timeout=5000,
            )

            page.set_viewport_size({"width": 1365, "height": 768})
            page.goto(arden_character_slug_path)
            expect(page.locator("h2:has-text('At a glance')")).to_be_visible(timeout=5000)
            _wait_for_app_loading_cover(page)
            _set_overflow_test_character_name(page)
            _assert_character_read_no_overflow(page, "desktop-1365")
            page.screenshot(path=str(tmp_path / "character_read_zigzag_1365.png"))

            page.set_viewport_size({"width": 390, "height": 812})
            page.reload()
            expect(page.locator("h2:has-text('At a glance')")).to_be_visible(timeout=5000)
            _wait_for_app_loading_cover(page)
            _set_overflow_test_character_name(page)
            _assert_character_read_no_overflow(page, "mobile-390")
            page.screenshot(path=str(tmp_path / "character_read_zigzag_390.png"))

            page.goto(arden_character_slug_path)
            page.set_viewport_size({"width": 1280, "height": 720})
            expect(page.locator("h2:has-text('At a glance')")).to_be_visible(timeout=5000)
            expect(page.locator("text=Open sheet edit view")).to_have_count(0)
            expect(page.locator("[data-character-sheet-save-bar]")).to_have_count(0)
            expect(page.locator("[data-character-subpage-nav-card]")).to_be_visible(timeout=5000)
            expect(page.locator(".glance-card--vitals input[name='current_hp']")).to_be_visible(timeout=5000)
            expect(page.locator("text=Save vitals")).to_have_count(0)
            quick_row_columns = page.locator(".glance-grid--quick-row-1").evaluate(
                "(element) => getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length"
            )
            assert quick_row_columns == 3
            passive_row_columns = page.locator(".glance-grid--quick-row-3").evaluate(
                "(element) => getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length"
            )
            assert passive_row_columns == 4
            resource_columns = page.locator(".resource-grid--editable").evaluate(
                "(element) => getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length"
            )
            assert resource_columns <= 3
            desktop_columns = page.locator(".ability-grid--skills").evaluate(
                "(element) => getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length"
            )
            assert desktop_columns == 6
            page.set_viewport_size({"width": 640, "height": 900})
            mobile_passive_row_columns = page.locator(".glance-grid--quick-row-3").evaluate(
                "(element) => getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length"
            )
            assert mobile_passive_row_columns == 2
            mobile_columns = page.locator(".ability-grid--skills").evaluate(
                "(element) => getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length"
            )
            assert mobile_columns == 3
            page.set_viewport_size({"width": 1280, "height": 720})
            page.evaluate("window.__characterReadShellMarker = 'alive'")
            hp_field = page.locator("form[data-character-sheet-edit-form='vitals'] input[name='current_hp']")
            hp_field.fill("12")
            expect(page.locator("[data-flash-stack-root] .flash-success")).to_have_text(
                "Vitals updated.",
                timeout=5000,
            )
            expect(hp_field).to_have_value("12", timeout=5000)
            assert page.evaluate("window.__characterReadShellMarker") == "alive"

            _write_character_state(
                app,
                "arden-march",
                lambda state: state.__setitem__(
                    "vitals",
                    {
                        "current_hp": 9,
                        "temp_hp": 0,
                    },
                ),
            )
            hp_field.fill("4")
            expect(page.locator("[data-flash-stack-root] .flash-error")).to_have_text(
                "This sheet changed in another session. Refresh the page and try again.",
                timeout=5000,
            )
            expect(hp_field).to_have_value("4", timeout=5000)
            assert page.evaluate("window.__characterReadShellMarker") == "alive"

            page.locator("[data-character-read-target-subpage='personal']").click()
            expect(page).to_have_url(personal_url_pattern, timeout=5000)
            page.go_back()
            expect(page.locator("h2:has-text('At a glance')")).to_be_visible(timeout=5000)

            page.locator("[data-character-read-target-subpage='spellcasting']").click()
            expect(page.locator("h2:has-text('Spell slots')")).to_be_visible(timeout=5000)
            generic_slot_headings = page.locator("h3.spell-slot-pool-title:has-text('Spell slots')")
            assert generic_slot_headings.count() > 0
            assert generic_slot_headings.evaluate_all(
                "(elements) => elements.every((element) => getComputedStyle(element).position === 'absolute')"
            )
            spell_slot_columns = page.locator(".spell-slot-editor-list--compact").nth(0).evaluate(
                "(element) => getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length"
            )
            assert spell_slot_columns <= 3
            spell_card_columns = page.locator(".spell-card-grid").nth(0).evaluate(
                "(element) => getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length"
            )
            assert spell_card_columns <= 3
            spell_trigger = page.locator("[data-character-spell-modal-trigger]").first
            expect(spell_trigger).to_be_visible(timeout=5000)
            open_page_count = len(page.context.pages)
            spell_trigger.click()
            spell_dialog = page.locator("dialog[data-character-spell-modal][open]").first
            expect(spell_dialog).to_be_visible(timeout=5000)
            assert len(page.context.pages) == open_page_count
            page.keyboard.press("Escape")
            expect(page.locator("dialog[data-character-spell-modal][open]")).to_have_count(0, timeout=5000)
            expect(spell_trigger).to_be_focused(timeout=5000)

            page.goto(f"{arden_character_slug_path}?mode=read&page=notes")
            expect(page).to_have_url(notes_url_pattern, timeout=5000)
            expect(page.locator("textarea[name='player_notes_markdown']")).to_be_visible(timeout=5000)

            notes_draft = "Browser draft to preserve."
            portrait_draft = "Portrait caption draft from browser flow."
            page.locator("textarea[name='player_notes_markdown']").fill(notes_draft)
            page.locator("[data-character-read-target-subpage='portrait']").click()
            expect(page).to_have_url(portrait_url_pattern, timeout=5000)
            expect(page.locator("textarea[name='background_markdown']")).to_have_count(0)
            expect(page.locator("button:has-text('Save personal details')")).to_have_count(0)
            page.locator("input[name='portrait_caption']").fill(portrait_draft)

            page.go_back()
            expect(page.locator("textarea[name='player_notes_markdown']")).to_have_value(
                notes_draft,
                timeout=5000,
            )
            expect(page).to_have_url(notes_url_pattern, timeout=5000)

            page.go_forward()
            expect(page.locator("input[name='portrait_caption']")).to_have_value(
                portrait_draft,
                timeout=5000,
            )
            expect(page).to_have_url(portrait_url_pattern, timeout=5000)

            page.locator("[data-character-read-target-subpage='notes']").click()
            expect(page).to_have_url(notes_url_pattern, timeout=5000)
            expect(page.locator("textarea[name='player_notes_markdown']")).to_have_value(
                notes_draft,
                timeout=5000,
            )

            page.locator("textarea[name='player_notes_markdown']").fill("Saved from JS shell flow.")
            page.locator("button:has-text('Save note')").click()
            expect(page.locator("[data-flash-stack-root] .flash-success")).to_have_text(
                "Note saved.",
                timeout=3000,
            )
            expect(page).to_have_url(notes_url_pattern, timeout=5000)
            assert "session/notes" not in page.url

            _write_character_state(
                app,
                "arden-march",
                lambda state: state.__setitem__(
                    "notes",
                    {
                        **dict(state.get("notes") or {}),
                        "player_notes_markdown": "Concurrent edit from browser flow.",
                    },
                ),
            )

            page.locator("textarea[name='player_notes_markdown']").fill("Conflict should stay in shell.")
            page.locator("button:has-text('Save note')").click()
            expect(page.locator("[data-flash-stack-root] .flash-error")).to_have_text(
                "This sheet changed in another session. Refresh the page and try again.",
                timeout=3000,
            )
            expect(page.locator("textarea[name='player_notes_markdown']")).to_have_value(
                "Conflict should stay in shell.",
                timeout=5000,
            )
            expect(page).to_have_url(notes_url_pattern, timeout=5000)
        finally:
            page.close()
            browser.close()
