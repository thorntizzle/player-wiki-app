# Rich-Text Security

Last updated: 2026-07-10

## Owns

- The shared sanitization contract for stored Markdown and HTML rendered by the Flask browser and JSON presenters.

## Current Security Contract

- `player_wiki/rich_text.py` is the single sanitizer implementation. It uses explicit tag, attribute, and protocol allowlists, removes dangerous elements, event attributes, URL schemes, malformed active markup, and comments, and constrains `class` and `id` values.
- Rich links may use relative targets or `http`, `https`, and `mailto`; rich images may use relative targets or `http` and `https`. Protocol-relative and dangerous encoded or obfuscated targets are rejected.
- Declared rich-text fields may contain Markdown plus the allowlisted HTML vocabulary. Plain fields do not pass through the rich-text helpers and remain Jinja-escaped.
- Structured payload helpers sanitize only declared Markdown keys or HTML-valued keys; unrelated strings remain data.
- Markdown sanitization follows Python-Markdown's parsing boundaries so valid inline, fenced, and indented code examples and autolinks remain usable while raw HTML is cleaned. Rendered HTML receives a final sanitization pass before it can be marked safe.

## Write And Legacy-Read Coverage

- Player Wiki page writes sanitize the body before updating the SQLite read model and mirrored Markdown.
- Session article snapshots, DM statblocks, and condition descriptions sanitize rich Markdown before persistence.
- Character definition/import rich fields, player notes, physical descriptions, and backgrounds sanitize before file or state writes.
- Systems custom entries, shared/imported rendered HTML, and nested declared HTML fragments sanitize at service and store boundaries.
- Wiki, Session, Character, and Systems presenters sanitize rendered HTML again. Legacy records remain readable and do not require a database cleanup or bulk rewrite to render safely.
- New writes store sanitized rich content; existing records are preserved and made safe at read/render boundaries.

## Jinja And Dependency Contract

- Flask registers `safe_rich_html`, which sanitizes first and marks only the sanitized result as renderable markup.
- The template inventory contains exactly 51 `safe_rich_html` sinks. The only two remaining bare `|safe` sinks are the `header_secondary_content` framework fragments in `player_wiki/templates/base.html`; they are trusted application-composed header content rather than stored user rich text.
- Runtime dependencies require `bleach>=6.2,<7.0`.

## Preserved Invariants

- This hardening does not change public URLs, routes, JSON response shapes, authorization or role behavior, visibility rules, the SQLite schema or existing records, or mirrored-content contracts.

## Verification Evidence

- `tests/test_rich_text_security.py` covers allowlisted formatting, malicious elements and attributes, dangerous and encoded URLs, malformed markup, parser-aligned Markdown/code behavior, structured-field selection, write boundaries, and legacy read/render boundaries.
- `tests/test_contract_smoke.py` covers unsanitized legacy database-backed
  Player Wiki content through `/global-search/preview` and a raw legacy DM
  statblock through Combat status live-state `detail_html`. Both paths preserve
  allowed formatting and link text while stripping active markup and dangerous
  URLs.
- Accepted Phase 0 verification evidence records 112 focused security tests passing, the exact TCE Systems importer anchor passing, a 26-test wiki/session API subset passing, and the complete 1,389-test regression suite passing.
- Independent verifier property sweeps covered 9,801 two-region and 1,885 mixed-region Markdown cases with no exceptions, active rendering, idempotence failures, or protected-content preservation failures.
- Documentation close-out spot-checks confirmed the sanitizer entry points, dependency bound, exact 51/2 template sink inventory, and write/read call sites. The larger test counts above are accepted integration evidence, not commands rerun during this documentation-only close-out.

## Browser Boundary

- The global-search and Combat legacy-fragment checks use Flask's test client;
  they do not constitute dedicated end-to-end execution in a real browser.

## Source Pointers

- `player_wiki/rich_text.py`
- `player_wiki/campaign_content_service.py`
- `player_wiki/campaign_session_service.py`
- `player_wiki/campaign_dm_content_service.py`
- `player_wiki/character_importer.py`
- `player_wiki/character_state_service.py`
- `player_wiki/character_presenter.py`
- `player_wiki/session_presenter.py`
- `player_wiki/systems_service.py`
- `player_wiki/systems_store.py`
- `tests/test_rich_text_security.py`
- `tests/test_contract_smoke.py`
- `requirements.txt`
