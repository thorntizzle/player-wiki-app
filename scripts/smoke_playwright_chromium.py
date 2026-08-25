"""Fail closed unless the validation image can launch its real Chromium."""

from importlib.metadata import version
import json
import re

from playwright.sync_api import sync_playwright


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        browser_version = browser.version
        if re.fullmatch(r"\d+(?:\.\d+)+", browser_version) is None:
            raise RuntimeError(f"unexpected Chromium version: {browser_version!r}")
        page = browser.new_page()
        page.set_content("<title>candidate gate</title><main>ready</main>")
        assert page.title() == "candidate gate"
        assert page.locator("main").text_content() == "ready"
        browser.close()
    print(
        json.dumps(
            {
                "chromium_version": browser_version,
                "playwright_package_version": version("playwright"),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
