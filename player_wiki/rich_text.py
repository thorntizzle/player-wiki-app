from __future__ import annotations

from collections.abc import Collection
from copy import deepcopy
from hashlib import sha256
from html import unescape
import re
import unicodedata
from typing import Any
from urllib.parse import unquote

import bleach
from markdown import Markdown
from markdown.htmlparser import HTMLExtractor
from markupsafe import Markup


# Rich-text fields may contain Markdown plus this deliberately small HTML vocabulary.
# Plain-text fields do not pass through this module and remain Jinja-escaped.
ALLOWED_RICH_TEXT_TAGS = frozenset(
    {
        "a",
        "article",
        "b",
        "blockquote",
        "br",
        "caption",
        "code",
        "dd",
        "del",
        "div",
        "dl",
        "dt",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "i",
        "img",
        "kbd",
        "li",
        "ol",
        "p",
        "pre",
        "s",
        "section",
        "span",
        "strong",
        "sub",
        "sup",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)

ALLOWED_LINK_PROTOCOLS = frozenset({"http", "https", "mailto"})
ALLOWED_IMAGE_PROTOCOLS = frozenset({"http", "https"})

_CLASS_VALUE_PATTERN = re.compile(r"\A[A-Za-z0-9_-]+(?:\s+[A-Za-z0-9_-]+)*\Z")
_ID_VALUE_PATTERN = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_.:-]*\Z")
_ASCII_CONTROL_OR_SPACE_PATTERN = re.compile(r"[\x00-\x20\x7f]+")
_HTML_FIELD_NAMES = frozenset({"html", "body_html", "rendered_html"})
_INLINE_CODE_PATTERN = re.compile(
    r"(?<![\\`])(?:\\\\)*(?P<fence>`+)(?!`)(?P<body>[^\r\n]*?)(?<!`)(?P=fence)(?!`)",
)
_MARKDOWN_AUTOLINK_PATTERN = re.compile(
    r"<(?:(?:https?://|mailto:)[^<>\s]+|[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,})>",
    re.IGNORECASE,
)


def _normalize_markdown_for_block_classification(source: str, *, tab_length: int = 4) -> tuple[str, list[int]]:
    """Mirror Python-Markdown newline/tab normalization while retaining source offsets."""

    normalized_parts: list[str] = []
    source_boundaries = [0]
    column = 0
    source_index = 0
    while source_index < len(source):
        character = source[source_index]
        if character in {"\x02", "\x03"}:
            source_index += 1
            source_boundaries[-1] = source_index
            continue
        if character == "\r":
            consumed = 2 if source_index + 1 < len(source) and source[source_index + 1] == "\n" else 1
            source_index += consumed
            normalized_parts.append("\n")
            source_boundaries.append(source_index)
            column = 0
            continue
        if character == "\n":
            source_index += 1
            normalized_parts.append("\n")
            source_boundaries.append(source_index)
            column = 0
            continue
        if character == "\t":
            source_index += 1
            spaces = tab_length - (column % tab_length)
            for space_index in range(spaces):
                normalized_parts.append(" ")
                source_boundaries.append(
                    source_index if space_index == spaces - 1 else source_index - 1
                )
            column += spaces
            continue
        source_index += 1
        normalized_parts.append(character)
        source_boundaries.append(source_index)
        column += 1
    return "".join(normalized_parts), source_boundaries


def _markdown_leading_indent_width(value: str, *, tab_length: int = 4) -> int:
    column = 0
    for character in value:
        if character == " ":
            column += 1
        elif character == "\t":
            column += tab_length - (column % tab_length)
        else:
            break
    return column


def _python_markdown_fenced_spans(source: str) -> list[tuple[int, int]]:
    """Return source-stable spans accepted by Python-Markdown's fenced preprocessor."""

    parser = Markdown(extensions=["fenced_code", "tables", "sane_lists"])
    fenced_processor = next(
        processor
        for processor in parser.preprocessors
        if processor.__class__.__name__ == "FencedBlockPreprocessor"
    )
    compiled_pattern = fenced_processor.FENCED_BLOCK_RE
    accepted_spans: list[tuple[int, int]] = []

    def accepts_exact_candidate(candidate: str) -> bool:
        candidate_parser = Markdown(extensions=["fenced_code", "tables", "sane_lists"])
        candidate_processor = next(
            processor
            for processor in candidate_parser.preprocessors
            if processor.__class__.__name__ == "FencedBlockPreprocessor"
        )
        candidate_pattern = candidate_processor.FENCED_BLOCK_RE
        current_match: list[Any] = [None]
        accepted_candidate_spans: list[tuple[int, int]] = []

        class RecordingFencePattern:
            def search(self, value: str, index: int = 0):
                match = candidate_pattern.search(value, index)
                current_match[0] = match
                return match

        original_store = candidate_parser.htmlStash.store

        def record_accepted_fence(html: Any) -> str:
            match = current_match[0]
            if match is not None:
                accepted_candidate_spans.append(match.span())
            return original_store(html)

        candidate_processor.FENCED_BLOCK_RE = RecordingFencePattern()
        candidate_parser.htmlStash.store = record_accepted_fence
        candidate_processor.run(candidate.split("\n"))
        return (0, len(candidate)) in accepted_candidate_spans

    search_index = 0
    while search_index < len(source):
        match = compiled_pattern.search(source, search_index)
        if match is None:
            break
        if accepts_exact_candidate(match.group(0)):
            accepted_spans.append(match.span())
            search_index = match.end()
        else:
            search_index = match.start() + 1
    return accepted_spans


def _decode_url_for_policy(value: str) -> str:
    decoded = unicodedata.normalize("NFKC", unescape(str(value or "")))
    for _ in range(3):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return decoded


def _is_allowed_url(value: str, *, allowed_protocols: Collection[str]) -> bool:
    decoded = _decode_url_for_policy(value)
    compact = _ASCII_CONTROL_OR_SPACE_PATTERN.sub("", decoded).replace("\\", "/")
    lowered = compact.casefold()
    if not lowered or lowered.startswith("//"):
        return False

    for protocol in allowed_protocols:
        if lowered.startswith(f"{protocol}:"):
            return True

    if lowered.startswith(("#", "/", "./", "../", "?")):
        return True

    first_delimiter = min(
        (index for index in (lowered.find("/"), lowered.find("?"), lowered.find("#")) if index >= 0),
        default=len(lowered),
    )
    return ":" not in lowered[:first_delimiter]


def _allow_rich_text_attribute(tag: str, name: str, value: str) -> bool:
    normalized_name = name.casefold()
    if normalized_name == "class":
        return bool(_CLASS_VALUE_PATTERN.fullmatch(value.strip()))
    if normalized_name == "id":
        return tag in {"article", "h1", "h2", "h3", "h4", "h5", "h6", "section"} and bool(
            _ID_VALUE_PATTERN.fullmatch(value.strip())
        )
    if normalized_name == "title":
        return tag in {"a", "abbr", "img"}
    if normalized_name == "href":
        return tag == "a" and _is_allowed_url(value, allowed_protocols=ALLOWED_LINK_PROTOCOLS)
    if normalized_name == "src":
        return tag == "img" and _is_allowed_url(value, allowed_protocols=ALLOWED_IMAGE_PROTOCOLS)
    if normalized_name == "alt":
        return tag == "img"
    if normalized_name in {"height", "width"}:
        return tag == "img" and value.strip().isdigit()
    if normalized_name in {"colspan", "rowspan"}:
        return tag in {"td", "th"} and value.strip().isdigit()
    if normalized_name == "scope":
        return tag == "th" and value.casefold() in {"col", "colgroup", "row", "rowgroup"}
    return False


def sanitize_rich_html(value: Any) -> str:
    """Return allowlisted presentation HTML safe for every legacy and current read path."""

    return bleach.clean(
        str(value or ""),
        tags=ALLOWED_RICH_TEXT_TAGS,
        attributes=_allow_rich_text_attribute,
        protocols=ALLOWED_LINK_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )


def sanitize_rich_markdown(value: Any) -> str:
    """Preserve Markdown source while removing active raw HTML embedded in it."""

    source = str(value or "")
    protected_fragments: list[str] = []
    protected_fence_line_breaks: list[tuple[str, str]] = []
    token_prefix = f"RICHMARKDOWNPROTECTED{sha256(source.encode('utf-8')).hexdigest()[:16]}"
    while token_prefix in source:
        token_prefix += "X"

    def protect(fragment: str) -> str:
        token = f"{token_prefix}{len(protected_fragments)}END"
        protected_fragments.append(fragment)
        return token

    fence_classification_source, fence_source_boundaries = _normalize_markdown_for_block_classification(
        source
    )
    fenced_parts: list[str] = []
    source_cursor = 0
    for classification_start, classification_end in _python_markdown_fenced_spans(
        fence_classification_source
    ):
        if (
            classification_start < 0
            or classification_end < classification_start
            or classification_end >= len(fence_source_boundaries)
        ):
            fenced_parts = [sanitize_rich_html(source)]
            source_cursor = len(source)
            break
        fence_start = fence_source_boundaries[classification_start]
        fence_end = fence_source_boundaries[classification_end]
        if fence_start < source_cursor or fence_end < fence_start or fence_end > len(source):
            fenced_parts = [sanitize_rich_html(source)]
            source_cursor = len(source)
            break
        fenced_parts.append(source[source_cursor:fence_start])
        fenced_parts.append(protect(source[fence_start:fence_end]))
        if source.startswith("\r\n", fence_end):
            original_line_break = "\r\n"
        elif fence_end < len(source) and source[fence_end] in {"\r", "\n"}:
            original_line_break = source[fence_end]
        else:
            original_line_break = ""
        if original_line_break:
            line_break_marker = (
                f"{token_prefix}FENCEBREAK{len(protected_fence_line_breaks)}END"
            )
            protected_fence_line_breaks.append((line_break_marker, original_line_break))
            fenced_parts.append(line_break_marker + "\n")
        source_cursor = fence_end + len(original_line_break)
    fenced_parts.append(source[source_cursor:])
    fenced_protected_source = "".join(fenced_parts)
    html_classification_source, html_source_boundaries = _normalize_markdown_for_block_classification(
        fenced_protected_source
    )
    markdown_parser = Markdown()
    html_extractor = HTMLExtractor(markdown_parser)
    html_extractor.feed(html_classification_source)
    html_extractor.close()
    html_block_parts: list[str] = []
    source_cursor = 0
    classification_cursor = 0
    for raw_html_block in markdown_parser.htmlStash.rawHtmlBlocks:
        raw_html_text = str(raw_html_block)
        classification_start = html_classification_source.find(
            raw_html_text,
            classification_cursor,
        )
        if classification_start < 0:
            # Conservatively clean the full source if Python-Markdown ever returns
            # a block that cannot be mapped back to its exact source fragment.
            html_block_parts = [sanitize_rich_html(fenced_protected_source)]
            source_cursor = len(fenced_protected_source)
            break
        classification_end = classification_start + len(raw_html_text)
        block_start = html_source_boundaries[classification_start]
        block_end = html_source_boundaries[classification_end]
        html_block_parts.append(fenced_protected_source[source_cursor:block_start])
        html_block_parts.append(
            protect(sanitize_rich_html(fenced_protected_source[block_start:block_end]))
        )
        source_cursor = block_end
        classification_cursor = classification_end
    html_block_parts.append(fenced_protected_source[source_cursor:])
    html_block_protected_source = "".join(html_block_parts)

    source_lines = html_block_protected_source.splitlines(keepends=True)
    classification_lines = list(source_lines)
    indented_line_markers: dict[int, str] = {}
    for line_index, line in enumerate(source_lines):
        line_without_ending = line.rstrip("\r\n")
        if (
            not line_without_ending.strip()
            or "<" not in line_without_ending
            or _markdown_leading_indent_width(line_without_ending) < 4
        ):
            continue
        line_ending = line[len(line_without_ending) :]
        markup_start = line_without_ending.find("<")
        markup_end = line_without_ending.rfind(">")
        line_prefix = line_without_ending[:markup_start]
        line_suffix = (
            line_without_ending[markup_end + 1 :]
            if markup_end >= markup_start
            else ""
        )
        marker = f"{token_prefix}INDENTCHECK{line_index}END"
        indented_line_markers[line_index] = marker
        classification_lines[line_index] = f"{line_prefix}{marker}{line_suffix}{line_ending}"

    classified_html = Markdown(extensions=["fenced_code", "tables", "sane_lists"]).convert(
        "".join(classification_lines)
    )

    def marker_is_rendered_as_code(marker: str) -> bool:
        marker_position = classified_html.find(marker)
        if marker_position < 0:
            return False
        code_start = classified_html.rfind("<code", 0, marker_position)
        code_end = classified_html.rfind("</code>", 0, marker_position)
        if code_start <= code_end:
            return False
        return classified_html.find(">", code_start, marker_position) >= 0

    protected_lines = []
    for line_index, line in enumerate(source_lines):
        marker = indented_line_markers.get(line_index)
        if marker and marker_is_rendered_as_code(marker):
            protected_lines.append(protect(line))
        else:
            protected_lines.append(line)

    protected_source = "".join(protected_lines)
    protected_source = _INLINE_CODE_PATTERN.sub(
        lambda match: protect(match.group(0)),
        protected_source,
    )
    protected_source = _MARKDOWN_AUTOLINK_PATTERN.sub(
        lambda match: protect(match.group(0)),
        protected_source,
    )
    sanitized = sanitize_rich_html(protected_source)
    for index in range(len(protected_fragments) - 1, -1, -1):
        fragment = protected_fragments[index]
        sanitized = sanitized.replace(f"{token_prefix}{index}END", fragment)
    for line_break_marker, original_line_break in protected_fence_line_breaks:
        sanitized = sanitized.replace(line_break_marker + "\n", original_line_break)
    return sanitized


def safe_rich_html(value: Any) -> Markup:
    """Jinja filter: sanitize first, then mark only the sanitized result as renderable HTML."""

    return Markup(sanitize_rich_html(value))


def sanitize_nested_html_fields(value: Any, *, field_name: str = "") -> Any:
    """Copy structured Systems content and sanitize only declared HTML fragments."""

    if isinstance(value, dict):
        return {
            key: sanitize_nested_html_fields(item, field_name=str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_nested_html_fields(item, field_name=field_name) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_nested_html_fields(item, field_name=field_name) for item in value)
    normalized_field_name = field_name.casefold()
    if isinstance(value, str) and (
        normalized_field_name in _HTML_FIELD_NAMES or normalized_field_name.endswith("_html")
    ):
        return sanitize_rich_html(value)
    return deepcopy(value)


def sanitize_selected_markdown_fields(value: Any, field_names: Collection[str]) -> Any:
    """Copy a structured payload and sanitize only explicitly named Markdown fields."""

    normalized_names = {str(name).casefold() for name in field_names}

    def sanitize_item(item: Any, *, field_name: str = "") -> Any:
        if isinstance(item, dict):
            return {key: sanitize_item(child, field_name=str(key)) for key, child in item.items()}
        if isinstance(item, list):
            return [sanitize_item(child, field_name=field_name) for child in item]
        if isinstance(item, tuple):
            return tuple(sanitize_item(child, field_name=field_name) for child in item)
        if isinstance(item, str) and field_name.casefold() in normalized_names:
            return sanitize_rich_markdown(item)
        return deepcopy(item)

    return sanitize_item(value)
