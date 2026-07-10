from __future__ import annotations

from copy import deepcopy
import json

import markdown
import pytest
import yaml

from player_wiki.campaign_content_service import (
    write_campaign_character_file,
    write_campaign_page_file,
)
from player_wiki.db import get_db
from player_wiki.rich_text import (
    safe_rich_html,
    sanitize_nested_html_fields,
    sanitize_rich_html,
    sanitize_rich_markdown,
    sanitize_selected_markdown_fields,
)
from player_wiki.session_presenter import present_session_articles


ACTIVE_MARKUP = """
<script>alert(1)</script>
<style>body { background: red }</style>
<iframe src="https://attacker.example"></iframe>
<object data="https://attacker.example/payload"></object>
<embed src="https://attacker.example/payload">
<form action="https://attacker.example"><input name="secret"></form>
<svg><a href="javascript:alert(1)"><circle onload="alert(1)"></circle></a></svg>
<math><mtext><img src=x onerror=alert(1)></mtext></math>
"""


def assert_no_active_markup(value: str) -> None:
    lowered = value.casefold()
    for fragment in (
        "<script",
        "<style",
        "<iframe",
        "<object",
        "<embed",
        "<form",
        "<input",
        "<svg",
        "<math",
        "onload=",
        "onerror=",
        "javascript:",
        "vbscript:",
        "data:",
        "file:",
    ):
        assert fragment not in lowered


def test_rich_html_preserves_allowed_formatting_and_systems_semantics() -> None:
    source = (
        '<section id="3-advantage-and-disadvantage" class="systems-book-section systems-entry-summary">'
        "<h2>Combat</h2>"
        '<div class="table-scroll"><table><caption>Actions</caption><thead><tr>'
        '<th scope="col">Action</th></tr></thead><tbody><tr><td rowspan="2">Strike</td>'
        "</tr></tbody></table></div>"
        '<article id="rank-iron" class="xianxia-embedded-rank-entry">'
        "<p><strong>Iron</strong> <em>rank</em><br>Ready.</p>"
        '<a href="/campaigns/linden-pass/systems/entries/strike" title="Strike">Read</a>'
        '<img src="https://assets.example/strike.webp" alt="Strike" width="320" height="180">'
        "</article></section>"
    )

    sanitized = sanitize_rich_html(source)

    assert sanitized == source
    assert 'id="3-advantage-and-disadvantage"' in sanitized
    assert sanitize_rich_html(sanitized) == sanitized


def test_rich_html_strips_active_elements_event_handlers_and_comments() -> None:
    sanitized = sanitize_rich_html(
        '<!-- hidden --><p class="callout" onclick="alert(1)">Visible</p>' + ACTIVE_MARKUP
    )

    assert '<p class="callout">Visible</p>' in sanitized
    assert "hidden" not in sanitized
    assert_no_active_markup(sanitized)


@pytest.mark.parametrize(
    "attribute,value",
    [
        ("href", "javascript:alert(1)"),
        ("href", "JaVaScRiPt:alert(1)"),
        ("href", "java\nscript:alert(1)"),
        ("href", "jav&#x61;script:alert(1)"),
        ("href", "java%73cript:alert(1)"),
        ("href", "%256a%2561%2576%2561script:alert(1)"),
        ("href", "vbscript:msgbox(1)"),
        ("href", "data:text/html,<script>alert(1)</script>"),
        ("href", "file:///etc/passwd"),
        ("href", "//attacker.example/payload"),
        ("src", "javascript:alert(1)"),
        ("src", "data:image/svg+xml,<svg onload=alert(1)></svg>"),
        ("src", "file:///etc/passwd"),
        ("src", "//attacker.example/payload"),
    ],
)
def test_rich_html_strips_dangerous_link_and_image_urls(attribute: str, value: str) -> None:
    tag = "a" if attribute == "href" else "img"
    body = "link" if tag == "a" else ""

    sanitized = sanitize_rich_html(f'<{tag} {attribute}="{value}">{body}</{tag}>')

    assert f"{attribute}=" not in sanitized
    assert_no_active_markup(sanitized)


@pytest.mark.parametrize(
    "source,expected_fragment",
    [
        ('<a href="https://example.com/path?q=1#part">link</a>', 'href="https://example.com/path?q=1#part"'),
        ('<a href="mailto:player@example.com">mail</a>', 'href="mailto:player@example.com"'),
        ('<a href="../systems/entries/strike">relative</a>', 'href="../systems/entries/strike"'),
        ('<img src="/campaigns/linden-pass/assets/map.webp" alt="Map">', 'src="/campaigns/linden-pass/assets/map.webp"'),
    ],
)
def test_rich_html_preserves_allowed_link_and_image_urls(source: str, expected_fragment: str) -> None:
    assert expected_fragment in sanitize_rich_html(source)


def test_rich_html_strips_malformed_nesting_without_reactivating_markup() -> None:
    sanitized = sanitize_rich_html(
        '<p><strong>Start<table><tr><td>Cell</strong>'
        '<svg><style><img src=x onerror=alert(1)></style></svg></table><p>End'
    )

    assert "Start" in sanitized
    assert "Cell" in sanitized
    assert "End" in sanitized
    assert_no_active_markup(sanitized)
    assert sanitize_rich_html(sanitized) == sanitized


def test_rich_html_enforces_id_class_and_attribute_policy() -> None:
    sanitized = sanitize_rich_html(
        '<section id="valid:section.1" class="valid-class second_class" style="color:red" data-x="1">'
        '<p id="not-allowed" class="bad/class good" aria-label="hidden">Text</p>'
        '<img src="/map.webp" width="320px" height="180" alt="Map" title="Map" usemap="#x">'
        '<table><tr><td colspan="2" rowspan="bad">Cell</td></tr></table>'
        "</section>"
    )

    assert 'id="valid:section.1"' in sanitized
    assert 'class="valid-class second_class"' in sanitized
    assert "style=" not in sanitized
    assert "data-x=" not in sanitized
    assert '<p>Text</p>' in sanitized
    assert "width=" not in sanitized
    assert 'height="180"' in sanitized
    assert 'alt="Map"' in sanitized
    assert 'title="Map"' in sanitized
    assert "usemap=" not in sanitized
    assert 'colspan="2"' in sanitized
    assert "rowspan=" not in sanitized


def test_markdown_sanitizer_preserves_source_semantics_and_code_examples() -> None:
    source = """---
title: Example-like body text
---

# Heading

Keep **bold**, *emphasis*, [[Obsidian Link]], [web](https://example.com), and <https://example.com/docs>.

Inline code: `<script>alert(1)</script>` and ``<img src=x onerror=alert(1)>``.

```html
<script>alert(1)</script>
<img src="x" onerror="alert(1)">
```

    <iframe src="example.html"></iframe>

<p class="callout" onclick="alert(1)">Allowed raw HTML, unsafe attribute removed.</p>
<script>alert(2)</script>
"""

    sanitized = sanitize_rich_markdown(source)

    assert "---\ntitle: Example-like body text\n---" in sanitized
    assert "**bold**" in sanitized
    assert "[[Obsidian Link]]" in sanitized
    assert "[web](https://example.com)" in sanitized
    assert "<https://example.com/docs>" in sanitized
    assert "`<script>alert(1)</script>`" in sanitized
    assert "``<img src=x onerror=alert(1)>``" in sanitized
    assert "```html\n<script>alert(1)</script>" in sanitized
    assert '    <iframe src="example.html"></iframe>' in sanitized
    assert '<p class="callout">Allowed raw HTML, unsafe attribute removed.</p>' in sanitized
    assert "<script>alert(2)</script>" not in sanitized
    assert sanitize_rich_markdown(sanitized) == sanitized


@pytest.mark.parametrize(
    "source",
    [
        "`<script>alert(1)</script>``",
        "`<script>alert(1)</script>",
        "<script>alert(1)</script>`",
        "``<script>alert(1)</script>`",
        "`<script>alert(1)</script>```",
        "```<script>alert(1)</script>``",
    ],
)
def test_markdown_sanitizer_does_not_protect_mismatched_or_unmatched_backtick_runs(
    source: str,
) -> None:
    sanitized = sanitize_rich_markdown(source)
    rendered = markdown.Markdown(extensions=["fenced_code", "tables", "sane_lists"]).convert(
        sanitized
    )

    assert "<script" not in sanitized.casefold()
    assert "<script" not in rendered.casefold()
    assert sanitize_rich_html(rendered) == rendered


@pytest.mark.parametrize("fence", ["`", "``", "```"])
def test_markdown_sanitizer_preserves_only_exact_valid_inline_code_runs(fence: str) -> None:
    source = f"Before {fence}<script>alert(1)</script>{fence} after."

    sanitized = sanitize_rich_markdown(source)
    rendered = markdown.Markdown(extensions=["fenced_code", "tables", "sane_lists"]).convert(
        sanitized
    )

    assert sanitized == source
    assert "<script" not in rendered.casefold()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered


@pytest.mark.parametrize(
    "source",
    [
        "\\`<script>alert(1)</script>`",
        "\\\\\\`<script>alert(1)</script>`",
    ],
)
def test_markdown_sanitizer_does_not_protect_odd_backslash_escaped_opening_runs(
    source: str,
) -> None:
    sanitized = sanitize_rich_markdown(source)
    rendered = markdown.Markdown(extensions=["fenced_code", "tables", "sane_lists"]).convert(
        sanitized
    )

    assert "<script" not in sanitized.casefold()
    assert "<script" not in rendered.casefold()


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_markdown_sanitizer_does_not_protect_multiline_inline_code_candidates(
    newline: str,
) -> None:
    source = f"`{newline}<script>alert(1)</script>{newline}`"

    sanitized = sanitize_rich_markdown(source)
    rendered = markdown.Markdown(extensions=["fenced_code", "tables", "sane_lists"]).convert(
        sanitized
    )

    assert "<script" not in sanitized.casefold()
    assert "<script" not in rendered.casefold()


@pytest.mark.parametrize(
    "source",
    [
        "`<script>alert(1)</script>\\`",
        "\\\\`<script>alert(1)</script>`",
        "`<script>alert(1)</script>\\\\`",
    ],
)
def test_markdown_sanitizer_follows_python_markdown_backslash_code_span_behavior(
    source: str,
) -> None:
    sanitized = sanitize_rich_markdown(source)
    rendered = markdown.Markdown(extensions=["fenced_code", "tables", "sane_lists"]).convert(
        sanitized
    )

    assert sanitized == source
    assert "<script" not in rendered.casefold()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered


@pytest.mark.parametrize(
    "source",
    [
        "<div>`<script>alert(1)</script>`</div>",
        "<section>`<script>alert(1)</script>`</section>",
        "<article>`<script>alert(1)</script>`</article>",
        "<p>`<script>alert(1)</script>`</p>",
        "<table><tbody><tr><td>`<script>alert(1)</script>`</td></tr></tbody></table>",
        (
            '<section class="systems-entry-summary">\n'
            '<article id="nested-rule">\n'
            '<div><p>`<script>alert(1)</script>`</p></div>\n'
            "</article>\n"
            "</section>"
        ),
        "<div>\n    <script>alert(1)</script>\n</div>",
        "<div>\n\t<script>alert(1)</script>\n</div>",
    ],
)
def test_markdown_sanitizer_does_not_treat_backticks_as_code_inside_raw_html_blocks(
    source: str,
) -> None:
    sanitized = sanitize_rich_markdown(source)
    rendered = markdown.Markdown(extensions=["fenced_code", "tables", "sane_lists"]).convert(
        sanitized
    )

    assert "<script" not in sanitized.casefold()
    assert "<script" not in rendered.casefold()
    assert "alert(1)" in sanitized


def test_markdown_sanitizer_preserves_allowed_safe_raw_html_blocks() -> None:
    source = (
        '<section id="3-safe-rule" class="systems-book-section systems-entry-summary">\n'
        '<article id="safe-detail"><p><strong>Safe detail.</strong></p></article>\n'
        "</section>"
    )

    assert sanitize_rich_markdown(source) == source


def test_markdown_sanitizer_preserves_fenced_code_processed_before_raw_html_blocks() -> None:
    source = (
        "<div>\n"
        "```html\n"
        "<script>alert(1)</script>\n"
        "```\n"
        "</div>"
    )

    sanitized = sanitize_rich_markdown(source)
    rendered = markdown.Markdown(extensions=["fenced_code", "tables", "sane_lists"]).convert(
        sanitized
    )

    assert sanitized == source
    assert "<script" not in rendered.casefold()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered


@pytest.mark.parametrize(
    "source",
    [
        " ```html\n<script>alert(1)</script>\n ```",
        "  ```html\n<script>alert(1)</script>\n  ```",
        "   ```html\n<script>alert(1)</script>\n   ```",
        "```html\n<script>alert(1)</script>\n````",
        "````html\n<script>alert(1)</script>\n```",
        "```html\n<script>alert(1)</script>\n ```",
        "```bad`info\n<script>alert(1)</script>\n```",
        "```{.html\n<script>alert(1)</script>\n```",
        "```javascript:bad\n<script>alert(1)</script>\n```",
        "```html\n<script>alert(1)</script>",
        "<div>\n ```html\n<script>alert(1)</script>\n ```\n</div>",
    ],
)
def test_markdown_sanitizer_rejects_apparent_fences_python_markdown_does_not_accept(
    source: str,
) -> None:
    original_rendered = markdown.Markdown(
        extensions=["fenced_code", "tables", "sane_lists"]
    ).convert(source)
    sanitized = sanitize_rich_markdown(source)
    sanitized_rendered = markdown.Markdown(
        extensions=["fenced_code", "tables", "sane_lists"]
    ).convert(sanitized)

    assert "<script" in original_rendered.casefold()
    assert "<script" not in sanitized.casefold()
    assert "<script" not in sanitized_rendered.casefold()


@pytest.mark.parametrize(
    "source",
    [
        "```\n<script>alert(1)</script>\n```",
        "```html\n<script>alert(1)</script>\n```",
        "~~~html\n<script>alert(1)</script>\n~~~",
        "````c++\n<script>alert(1)</script>\n````",
        "```{.html #sample-code}\n<script>alert(1)</script>\n```",
        "```html\n<script>alert(1)</script>\n```   ",
        "```html\n<script>alert(1)</script>\n```\t",
        "```html\r\n<script>alert(1)</script>\r\n```",
        "<div>\n```html\n<script>alert(1)</script>\n```\n</div>",
    ],
)
def test_markdown_sanitizer_preserves_only_fences_python_markdown_accepts(
    source: str,
) -> None:
    original_rendered = markdown.Markdown(
        extensions=["fenced_code", "tables", "sane_lists"]
    ).convert(source)
    sanitized = sanitize_rich_markdown(source)
    sanitized_rendered = markdown.Markdown(
        extensions=["fenced_code", "tables", "sane_lists"]
    ).convert(sanitized)

    assert "<script" not in original_rendered.casefold()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in original_rendered
    assert sanitized == source
    assert "<script" not in sanitized_rendered.casefold()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in sanitized_rendered
    assert sanitize_rich_markdown(sanitized) == sanitized


def test_markdown_sanitizer_maps_multiple_fences_against_stable_source_offsets() -> None:
    first_fence = "```txt\n" + ("A" * 26) + "\n```"
    second_fence = "```txt\n<script>safe()</script>\n```"
    source = first_fence + "\n<script>evil()</script>\n" + second_fence

    sanitized = sanitize_rich_markdown(source)
    rendered = markdown.Markdown(extensions=["fenced_code", "tables", "sane_lists"]).convert(
        sanitized
    )

    assert first_fence in sanitized
    assert second_fence in sanitized
    assert "<script>evil()</script>" not in sanitized
    assert "<script" not in rendered.casefold()
    assert "&lt;script&gt;safe()&lt;/script&gt;" in rendered
    assert sanitize_rich_markdown(sanitized) == sanitized


@pytest.mark.parametrize("fence_count", [0, 1, 2, 3, 4])
def test_markdown_sanitizer_handles_repeated_and_adjacent_valid_fences(
    fence_count: int,
) -> None:
    identical_fence = "```txt\n<script>safe()</script>\n```"
    source = "\n".join(identical_fence for _ in range(fence_count))

    sanitized = sanitize_rich_markdown(source)
    rendered = markdown.Markdown(extensions=["fenced_code", "tables", "sane_lists"]).convert(
        sanitized
    )

    assert sanitized == source
    assert sanitized.count(identical_fence) == fence_count
    assert "<script" not in rendered.casefold()
    assert sanitize_rich_markdown(sanitized) == sanitized


@pytest.mark.parametrize("raw_position", ["before", "between", "after"])
def test_markdown_sanitizer_sanitizes_raw_html_around_multiple_mixed_fences(
    raw_position: str,
) -> None:
    backtick_fence = "```html\n<script>backtick_safe()</script>\n```"
    tilde_fence = "~~~html\n<script>tilde_safe()</script>\n~~~"
    raw = "<script>raw_evil()</script>"
    parts = [backtick_fence, tilde_fence]
    parts.insert({"before": 0, "between": 1, "after": 2}[raw_position], raw)
    source = "\n".join(parts)

    sanitized = sanitize_rich_markdown(source)
    rendered = markdown.Markdown(extensions=["fenced_code", "tables", "sane_lists"]).convert(
        sanitized
    )

    assert backtick_fence in sanitized
    assert tilde_fence in sanitized
    assert raw not in sanitized
    assert "<script" not in rendered.casefold()
    assert sanitize_rich_markdown(sanitized) == sanitized


def test_markdown_sanitizer_preserves_multifence_crlf_tabs_and_marker_like_text() -> None:
    source = (
        "```txt\r\n"
        "RICHMARKDOWNPROTECTEDdeadbeef0END\r\n"
        "<script>first_safe()</script>\r\n"
        "```\t\r\n"
        "~~~txt\r\n"
        "<script>second_safe()</script>\r\n"
        "~~~"
    )

    sanitized = sanitize_rich_markdown(source)
    rendered = markdown.Markdown(extensions=["fenced_code", "tables", "sane_lists"]).convert(
        sanitized
    )

    assert sanitized == source
    assert "RICHMARKDOWNPROTECTEDdeadbeef0END" in sanitized
    assert "<script" not in rendered.casefold()
    assert sanitize_rich_markdown(sanitized) == sanitized


def test_markdown_sanitizer_small_fence_search_never_throws_or_renders_active_html() -> None:
    openings = ["```", "~~~", "````", " ```", "```txt", "```javascript:bad"]
    closings = ["```", "~~~", "````", " ```", "```\t", ""]
    payloads = [
        "<script>evil()</script>",
        "A<script>evil()</script>",
        ("A" * 26) + "<script>evil()</script>",
    ]

    for opening in openings:
        for closing in closings:
            for payload in payloads:
                source = f"{opening}\n{payload}\n{closing}" if closing else f"{opening}\n{payload}"
                sanitized = sanitize_rich_markdown(source)
                rendered = markdown.Markdown(
                    extensions=["fenced_code", "tables", "sane_lists"]
                ).convert(sanitized)

                assert "<script" not in rendered.casefold(), repr(source)
                assert sanitize_rich_markdown(sanitized) == sanitized, repr(source)


@pytest.mark.parametrize(
    "source",
    [
        "text\n    <script>alert(1)</script>",
        "- item\n    <script>alert(1)</script>",
        "- outer\n    - <script>alert(1)</script>",
        "- item\n\n    <script>alert(1)</script>",
        "- outer\n    - inner\n\n        <script>alert(1)</script>",
    ],
)
def test_markdown_sanitizer_does_not_protect_indentation_python_markdown_renders_active(
    source: str,
) -> None:
    original_rendered = markdown.Markdown(
        extensions=["fenced_code", "tables", "sane_lists"]
    ).convert(source)
    sanitized = sanitize_rich_markdown(source)
    sanitized_rendered = markdown.Markdown(
        extensions=["fenced_code", "tables", "sane_lists"]
    ).convert(sanitized)

    assert "<script" in original_rendered.casefold()
    assert "<script" not in sanitized.casefold()
    assert "<script" not in sanitized_rendered.casefold()


@pytest.mark.parametrize(
    "source",
    [
        "    <script>alert(1)</script>",
        "text\n\n    <script>alert(1)</script>",
        "    <script>alert(1)</script>\n    <img src=x onerror=alert(2)>",
        "    <script>alert(1)</script>\n\n    <img src=x onerror=alert(2)>",
        "    <script>alert(1)</script>\r\n    <img src=x onerror=alert(2)>",
        "- item\n\n        <script>alert(1)</script>",
        "- outer\n    - inner\n\n            <script>alert(1)</script>",
    ],
)
def test_markdown_sanitizer_preserves_indented_code_recognized_by_python_markdown(
    source: str,
) -> None:
    original_rendered = markdown.Markdown(
        extensions=["fenced_code", "tables", "sane_lists"]
    ).convert(source)
    sanitized = sanitize_rich_markdown(source)
    sanitized_rendered = markdown.Markdown(
        extensions=["fenced_code", "tables", "sane_lists"]
    ).convert(sanitized)

    assert "<script" not in original_rendered.casefold()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in original_rendered
    assert "<script>alert(1)</script>" in sanitized
    assert "<script" not in sanitized_rendered.casefold()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in sanitized_rendered
    assert sanitize_rich_markdown(sanitized) == sanitized


@pytest.mark.parametrize(
    "source",
    [
        "text\n\t<script>alert(1)</script>",
        "- item\n\t<script>alert(1)</script>",
        "- item\n\n\t<script>alert(1)</script>",
        "- item\n\n \t <script>alert(1)</script>",
        "- outer\n\t- inner\n\n\t\t<script>alert(1)</script>",
    ],
)
def test_markdown_sanitizer_sanitizes_tab_indentation_not_rendered_as_code(
    source: str,
) -> None:
    original_rendered = markdown.Markdown(
        extensions=["fenced_code", "tables", "sane_lists"]
    ).convert(source)
    sanitized = sanitize_rich_markdown(source)
    sanitized_rendered = markdown.Markdown(
        extensions=["fenced_code", "tables", "sane_lists"]
    ).convert(sanitized)

    assert "<script" in original_rendered.casefold()
    assert "<script" not in sanitized.casefold()
    assert "<script" not in sanitized_rendered.casefold()


@pytest.mark.parametrize(
    "source",
    [
        "\t<script>alert(1)</script>",
        "text\n\n\t<script>alert(1)</script>",
        "\t<script>alert(1)</script>\n\t<img src=x onerror=alert(2)>",
        "\t<script>alert(1)</script>\r\n\t<img src=x onerror=alert(2)>",
        " \t<script>alert(1)</script>",
        "- item\n\n\t\t<script>alert(1)</script>",
        "- item\n\n\t    <script>alert(1)</script>",
        "- outer\n\t- inner\n\n\t\t\t<script>alert(1)</script>",
    ],
)
def test_markdown_sanitizer_preserves_tab_indented_code_recognized_by_python_markdown(
    source: str,
) -> None:
    original_rendered = markdown.Markdown(
        extensions=["fenced_code", "tables", "sane_lists"]
    ).convert(source)
    sanitized = sanitize_rich_markdown(source)
    sanitized_rendered = markdown.Markdown(
        extensions=["fenced_code", "tables", "sane_lists"]
    ).convert(sanitized)

    assert "<script" not in original_rendered.casefold()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in original_rendered
    assert "<script>alert(1)</script>" in sanitized
    assert "<script" not in sanitized_rendered.casefold()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in sanitized_rendered
    assert sanitize_rich_markdown(sanitized) == sanitized


def test_structured_sanitizers_only_change_declared_rich_fields() -> None:
    payload = {
        "title": '<script id="plain-field">plain metadata</script>',
        "body_html": '<p onclick="alert(1)">Body</p><script>alert(1)</script>',
        "nested": {
            "summary_html": '<section class="systems-entry-summary">Summary</section><svg></svg>',
            "description": '<iframe src="plain-field"></iframe>',
        },
        "rows": [{"rendered_html": '<strong onmouseover="alert(1)">Row</strong>'}],
    }

    nested = sanitize_nested_html_fields(payload)
    selected = sanitize_selected_markdown_fields(payload, {"description"})

    assert nested["title"] == payload["title"]
    assert nested["nested"]["description"] == payload["nested"]["description"]
    assert nested["body_html"] == "<p>Body</p>alert(1)"
    assert nested["nested"]["summary_html"] == '<section class="systems-entry-summary">Summary</section>'
    assert nested["rows"][0]["rendered_html"] == "<strong>Row</strong>"
    assert selected["title"] == payload["title"]
    assert selected["body_html"] == payload["body_html"]
    assert "<iframe" not in selected["nested"]["description"]


def test_safe_rich_html_marks_only_the_sanitized_result() -> None:
    sanitized = safe_rich_html('<p onclick="alert(1)">Safe</p><script>alert(1)</script>')

    assert str(sanitized) == "<p>Safe</p>alert(1)"
    assert hasattr(sanitized, "__html__")


def test_campaign_page_write_mirrors_sanitized_markdown_and_legacy_api_render_is_safe(
    app,
    client,
    sign_in,
    users,
) -> None:
    submitted = (
        "## Security Note\n\n"
        '<p class="callout" onclick="alert(1)">Allowed raw HTML.</p>\n'
        "<script>alert('stored')</script>\n"
        "Inline example: `<img src=x onerror=alert(1)>`.\n"
    )
    with app.app_context():
        repository_store = app.extensions["repository_store"]
        page_store = app.extensions["campaign_page_store"]
        campaign = repository_store.get().get_campaign("linden-pass")
        assert campaign is not None
        record = write_campaign_page_file(
            campaign,
            "notes/security-boundary",
            metadata={
                "title": "Security Boundary",
                "section": "Notes",
                "type": "note",
                "published": True,
            },
            body_markdown=submitted,
            page_store=page_store,
        )

        persisted = page_store.get_page_record(
            "linden-pass",
            "notes/security-boundary",
            include_body=True,
        )
        assert persisted is not None
        assert persisted.body_markdown == record.body_markdown
        assert '<p class="callout">Allowed raw HTML.</p>' in persisted.body_markdown
        assert "<script>alert('stored')</script>" not in persisted.body_markdown
        assert "`<img src=x onerror=alert(1)>`" in persisted.body_markdown

        mirrored = record.file_path.read_text(encoding="utf-8")
        assert record.body_markdown.strip() in mirrored
        assert "<script>alert('stored')</script>" not in mirrored

        legacy_body = (
            "## Legacy Security Note\n\n"
            '<p class="callout" onclick="alert(1)">Legacy visible text.</p>'
            '<script>alert("legacy")</script><img src="/map.webp" onerror="alert(2)">'
        )
        legacy_mirror = mirrored.replace(record.body_markdown.strip(), legacy_body)
        record.file_path.write_text(legacy_mirror, encoding="utf-8")
        repository_store.refresh()

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/api/v1/campaigns/linden-pass/wiki/pages/notes/security-boundary")

    assert response.status_code == 200
    body_html = response.get_json()["page"]["body_html"]
    assert "Legacy visible text." in body_html
    assert '<p class="callout">Legacy visible text.</p>' in body_html
    assert '<img src="/map.webp">' in body_html
    assert_no_active_markup(body_html)


def test_session_systems_snapshot_write_and_legacy_presenter_are_safe(app) -> None:
    submitted = (
        '<section id="rules" class="systems-book-section"><h2>Rules</h2>'
        '<div class="table-scroll"><table><tr><th scope="col">Action</th></tr></table></div>'
        '<p onclick="alert(1)">Strike.</p><script>alert("stored")</script></section>'
    )
    with app.app_context():
        campaign = app.extensions["repository_store"].get().get_campaign("linden-pass")
        service = app.extensions["campaign_session_service"]
        assert campaign is not None
        article = service.create_article(
            "linden-pass",
            title="Security Systems Snapshot",
            body_markdown=submitted,
            source_page_ref="systems:security-snapshot",
        )

        assert '<section id="rules" class="systems-book-section">' in article.body_markdown
        assert "onclick=" not in article.body_markdown
        assert "<script" not in article.body_markdown

        legacy = (
            '<section class="systems-entry-summary"><p onmouseover="alert(1)">Legacy snapshot.</p>'
            '<svg><a href="javascript:alert(1)">bad</a></svg></section>'
        )
        connection = get_db()
        connection.execute(
            "UPDATE campaign_session_articles SET body_markdown = ? WHERE id = ?",
            (legacy, article.id),
        )
        connection.commit()
        legacy_article = service.get_article("linden-pass", article.id)
        assert legacy_article is not None
        presented = present_session_articles(
            campaign,
            [legacy_article],
            {},
            image_url_builder=lambda _article_id: "",
        )[0]

    assert presented["body_html"] == (
        '<section class="systems-entry-summary"><p>Legacy snapshot.</p><a>bad</a></section>'
    )
    assert_no_active_markup(str(presented["body_html"]))


def test_character_rich_field_writes_mirror_safely_and_legacy_api_html_is_safe(
    app,
    client,
    sign_in,
    users,
) -> None:
    campaigns_dir = app.config["TEST_CAMPAIGNS_DIR"]
    definition_path = campaigns_dir / "linden-pass" / "characters" / "arden-march" / "definition.yaml"
    definition_payload = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    definition_payload["profile"]["biography_markdown"] = (
        '<p class="bio" onload="alert(1)">Biography.</p><script>alert(1)</script>'
    )
    definition_payload["features"][0]["description_markdown"] = (
        "Feature **detail**. <iframe src=bad></iframe>"
    )
    definition_payload["reference_notes"]["custom_sections"][0]["body_markdown"] = (
        "Literal example: `<script>example()</script>`. <object data=bad></object>"
    )

    with app.app_context():
        state_store = app.extensions["character_state_store"]
        written = write_campaign_character_file(
            campaigns_dir,
            "linden-pass",
            "arden-march",
            definition_payload=definition_payload,
            import_metadata_payload=None,
            state_store=state_store,
        )
        mirrored = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
        assert written.definition.profile["biography_markdown"] == '<p class="bio">Biography.</p>alert(1)'
        assert mirrored["profile"]["biography_markdown"] == '<p class="bio">Biography.</p>alert(1)'
        assert "<iframe" not in mirrored["features"][0]["description_markdown"]
        assert "`<script>example()</script>`" in mirrored["reference_notes"]["custom_sections"][0][
            "body_markdown"
        ]

        repository = app.extensions["character_repository"]
        service = app.extensions["character_state_service"]
        record = repository.get_visible_character("linden-pass", "arden-march")
        assert record is not None
        noted = service.update_player_notes(
            record,
            expected_revision=record.state_record.revision,
            notes_markdown='<p onclick="alert(1)">Player note.</p><script>alert(1)</script>',
        )
        refreshed = repository.get_visible_character("linden-pass", "arden-march")
        assert refreshed is not None
        personalized = service.update_personal_details(
            refreshed,
            expected_revision=noted.revision,
            physical_description_markdown='<strong onmouseover="alert(1)">Tall.</strong>',
            background_markdown='<img src="javascript:alert(1)">Background.',
        )
        assert personalized.state["notes"]["player_notes_markdown"] == "<p>Player note.</p>alert(1)"
        assert personalized.state["notes"]["physical_description_markdown"] == "<strong>Tall.</strong>"
        assert personalized.state["notes"]["background_markdown"] == "<img>Background."

        legacy_state = deepcopy(personalized.state)
        legacy_state["notes"]["player_notes_markdown"] = (
            '<p onclick="alert(1)">Legacy player note.</p><svg onload="alert(2)"></svg>'
        )
        connection = get_db()
        connection.execute(
            "UPDATE character_state SET state_json = ? WHERE campaign_slug = ? AND character_slug = ?",
            (json.dumps(legacy_state), "linden-pass", "arden-march"),
        )
        connection.commit()

    sign_in(users["dm"]["email"], users["dm"]["password"])
    response = client.get("/api/v1/campaigns/linden-pass/characters/arden-march")

    assert response.status_code == 200
    player_notes_html = response.get_json()["character"]["player_notes_html"]
    assert "<p>Legacy player note.</p>" in player_notes_html
    assert_no_active_markup(player_notes_html)


def test_dm_statblock_and_condition_write_boundaries_sanitize_persisted_markdown(app) -> None:
    statblock_markdown = b"""---
title: Security Beast
---

Armor Class 12
Hit Points 10
Speed 30 ft.

## Actions

<p class="action" onclick="alert(1)">Claw.</p>
<script>alert(1)</script>
"""
    with app.app_context():
        service = app.extensions["campaign_dm_content_service"]
        statblock = service.create_statblock(
            "linden-pass",
            filename="security-beast.md",
            data_blob=statblock_markdown,
        )
        condition = service.create_condition_definition(
            "linden-pass",
            name="Security Marked",
            description_markdown=(
                '<p class="condition" onmouseenter="alert(1)">Marked.</p>'
                '<form><input autofocus onfocus="alert(2)"></form>'
            ),
        )
        stored_statblock = service.get_statblock("linden-pass", statblock.id)
        stored_condition = next(
            row
            for row in service.list_condition_definitions("linden-pass")
            if row.id == condition.id
        )

    assert stored_statblock is not None
    assert '<p class="action">Claw.</p>' in stored_statblock.body_markdown
    assert "<script" not in stored_statblock.body_markdown
    assert stored_condition.description_markdown == '<p class="condition">Marked.</p>'


def test_systems_custom_shared_nested_and_legacy_read_boundaries_are_safe(app, users) -> None:
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        custom = service.create_custom_campaign_entry(
            "linden-pass",
            title="Security Custom Rule",
            entry_type="rule",
            slug_leaf="security-custom-rule",
            body_markdown=(
                "## Safe Heading\n\n"
                '<section class="systems-entry-summary"><p onclick="alert(1)">Custom rule.</p></section>'
                '<script>alert(1)</script>'
            ),
            actor_user_id=users["dm"]["id"],
            can_set_private=False,
        )
        assert "<script" not in custom.body["markdown"]
        assert '<section class="systems-entry-summary">' in custom.rendered_html
        assert_no_active_markup(custom.rendered_html)

        store.upsert_library("DND-5E", title="DND 5E", system_code="DND-5E")
        store.upsert_source(
            "DND-5E",
            "SECURITY",
            title="Security Test Source",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        shared = store.upsert_entry(
            "DND-5E",
            "SECURITY",
            entry_key="dnd-5e|rule|security|shared",
            entry_type="rule",
            slug="security-shared-rule",
            title="Security Shared Rule",
            player_safe_default=True,
            body={
                "rendered": {
                    "summary_html": '<section class="systems-entry-summary" onclick="x">Summary.</section>',
                    "option_groups": [{"body_html": '<p onload="x">Option.</p><svg></svg>'}],
                    "plain_markdown": '<script id="plain">preserve plain field</script>',
                }
            },
            rendered_html='<article class="systems-entry-summary" onmouseover="x">Shared.</article><iframe></iframe>',
        )
        assert shared.rendered_html == '<article class="systems-entry-summary">Shared.</article>'
        assert shared.body["rendered"]["summary_html"] == (
            '<section class="systems-entry-summary">Summary.</section>'
        )
        assert shared.body["rendered"]["option_groups"][0]["body_html"] == "<p>Option.</p>"
        assert shared.body["rendered"]["plain_markdown"] == (
            '<script id="plain">preserve plain field</script>'
        )

        legacy_body = {
            "rendered": {
                "summary_html": '<p onclick="alert(1)">Legacy nested.</p><math></math>',
                "plain_text": '<script>plain field remains data</script>',
            }
        }
        connection = get_db()
        connection.execute(
            "UPDATE systems_entries SET body_json = ?, rendered_html = ? WHERE library_slug = ? AND entry_key = ?",
            (
                json.dumps(legacy_body),
                '<section class="systems-entry-summary"><img src="javascript:alert(1)">Legacy shared.</section>',
                "DND-5E",
                shared.entry_key,
            ),
        )
        connection.commit()
        legacy = store.get_entry("DND-5E", shared.entry_key)

    assert legacy is not None
    assert legacy.rendered_html == (
        '<section class="systems-entry-summary"><img>Legacy shared.</section>'
    )
    assert legacy.body["rendered"]["summary_html"] == "<p>Legacy nested.</p>"
    assert legacy.body["rendered"]["plain_text"] == '<script>plain field remains data</script>'
    assert_no_active_markup(legacy.rendered_html)
    assert_no_active_markup(legacy.body["rendered"]["summary_html"])
