from __future__ import annotations

from html import unescape
from html.parser import HTMLParser

from player_wiki.auth import VIEW_AS_SESSION_KEY
from player_wiki.campaign_visibility import (
    VISIBILITY_DM,
    VISIBILITY_PLAYERS,
    VISIBILITY_PRIVATE,
)


class _PresentationParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.labelledby: list[str] = []
        self.nested_cards = 0
        self.static_live_regions = 0
        self._element_stack: list[tuple[str, bool]] = []
        self._card_depth = 0
        self._hidden_depth = 0
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set(str(attributes.get("class") or "").split())
        is_card = "card" in classes
        if is_card and self._card_depth:
            self.nested_cards += 1
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}:
            self._element_stack.append((tag, is_card))
            if is_card:
                self._card_depth += 1
        element_id = str(attributes.get("id") or "").strip()
        if element_id:
            self.ids.add(element_id)
        labelledby = str(attributes.get("aria-labelledby") or "").strip()
        if labelledby:
            self.labelledby.extend(labelledby.split())
        if "state-panel" in classes and (
            attributes.get("aria-live") is not None
            or attributes.get("role") in {"status", "alert"}
        ):
            self.static_live_regions += 1
        if tag in {"script", "style"}:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        while self._element_stack:
            open_tag, was_card = self._element_stack.pop()
            if was_card:
                self._card_depth -= 1
            if open_tag == tag:
                break
        if tag in {"script", "style"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth and data.strip():
            self.text.append(data.strip())


def _inspect(html: str) -> tuple[_PresentationParser, str]:
    parser = _PresentationParser()
    parser.feed(html)
    return parser, unescape(" ".join(" ".join(parser.text).split()))


def _entry(
    source_id: str,
    entry_type: str,
    slug: str,
    title: str,
    *,
    metadata: dict[str, object] | None = None,
    body: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "entry_key": f"dnd-5e|{entry_type}|{source_id.lower()}|{slug}",
        "entry_type": entry_type,
        "slug": slug,
        "title": title,
        "source_path": rf"C:\private\imports\{source_id.lower()}.json",
        "search_text": f"{title} private-search-index-marker",
        "player_safe_default": True,
        "metadata": {
            "support_state": "private-support-marker",
            "import_run_id": "private-import-marker",
            "storage_state": "private-storage-marker",
            "provenance": "private-provenance-marker",
            **dict(metadata or {}),
        },
        "body": dict(body or {}),
        "rendered_html": f"<p>{title} reference text.</p>",
    }


def _upsert_source(
    app,
    source_id: str,
    title: str,
    entries: list[dict[str, object]],
    *,
    enabled: bool = True,
    visibility: str = VISIBILITY_PLAYERS,
) -> None:
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        store.upsert_source(
            library_slug,
            source_id,
            title=title,
            license_class="open_license",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        store.upsert_campaign_enabled_source(
            "linden-pass",
            library_slug=library_slug,
            source_id=source_id,
            is_enabled=enabled,
            default_visibility=visibility,
        )
        store.replace_entries_for_source(
            library_slug,
            source_id,
            entries=entries,
        )


def _assert_friendly_surface(html: str, *, forbidden_visible: tuple[str, ...]) -> str:
    parser, text = _inspect(html)
    assert parser.nested_cards == 0
    assert parser.static_live_regions == 0
    assert parser.labelledby
    assert set(parser.labelledby) <= parser.ids
    for marker in (
        *forbidden_visible,
        "open_license",
        "Open License",
        "Default visibility",
        "Source ID:",
        "private-support-marker",
        "private-import-marker",
        "private-storage-marker",
        "private-provenance-marker",
        r"C:\private\imports",
        "entry_key",
        "source_path",
        "SQLite",
        "import run",
        "management inventory",
    ):
        assert marker.casefold() not in text.casefold()
    return text


def test_systems_source_navigation_presents_categories_chapters_search_and_static_states(
    app,
    client,
    sign_in,
    users,
):
    source_id = "P74B-SOURCE-INTERNAL"
    source_title = "Adventurer's Field Guide"
    entries = [
        _entry(
            source_id,
            "book",
            "second-chapter",
            "Second Chapter",
            metadata={"section_label": "Chapter 2", "target_order": 2},
        ),
        _entry(
            source_id,
            "book",
            "first-chapter",
            "First Chapter",
            metadata={"section_label": "Chapter 1", "target_order": 1},
        ),
        _entry(source_id, "class", "wayfinder", "Wayfinder"),
        _entry(source_id, "classfeature", "wayfinder-feature", "Wayfinder Feature"),
        _entry(source_id, "subclassfeature", "trail-feature", "Trail Feature"),
        _entry(source_id, "optionalfeature", "optional-trick", "Optional Trick"),
        _entry(source_id, "spell", "amber-beacon", "Amber Beacon"),
        _entry(source_id, "spell", "azure-current", "Azure Current"),
        _entry(
            source_id,
            "rule",
            "guarded-measure",
            "Guarded Measure",
            metadata={"aliases": ["Measured Guard"], "formula": "12 focus"},
        ),
    ]
    empty_source_id = "P74B-EMPTY-INTERNAL"
    _upsert_source(app, source_id, source_title, entries)
    _upsert_source(app, empty_source_id, "Quiet Field Guide", [])
    _upsert_source(
        app,
        "DMG",
        "Dungeon Master's Guide (2014)",
        [
            _entry("DMG", "book", "guarded-dmg-chapter", "Guarded DMG Chapter"),
            _entry("DMG", "item", "player-dmg-item", "Player DMG Item"),
        ],
    )

    sign_in(users["party"]["email"], users["party"]["password"])
    source = client.get(f"/campaigns/linden-pass/systems/sources/{source_id}")
    populated_search = client.get(
        f"/campaigns/linden-pass/systems/sources/{source_id}"
        "?reference_q=Measured+Guard"
    )
    empty_search = client.get(
        f"/campaigns/linden-pass/systems/sources/{source_id}?reference_q=missing"
    )
    source_empty = client.get(
        f"/campaigns/linden-pass/systems/sources/{empty_source_id}"
    )
    guarded_dmg_source = client.get("/campaigns/linden-pass/systems/sources/DMG")

    assert [response.status_code for response in (source, populated_search, empty_search, source_empty)] == [
        200,
        200,
        200,
        200,
    ]
    assert guarded_dmg_source.status_code == 200
    source_html = source.get_data(as_text=True)
    source_text = _assert_friendly_surface(
        source_html,
        forbidden_visible=(source_id, empty_source_id),
    )
    assert source_text.count(source_title) >= 1
    assert "Explore the categories, chapters, and rules references available to you" in source_text
    assert "6 browsable entries across 4 categories" in source_text
    for entry_type, label, count in (
        ("book", "Book Chapters", 2),
        ("class", "Classes", 1),
        ("spell", "Spells", 2),
        ("rule", "Rules", 1),
    ):
        href = (
            f"/campaigns/linden-pass/systems/sources/{source_id}/types/{entry_type}"
        )
        assert f'href="{href}"' in source_html
        assert f"{label} {count} {'entry' if count == 1 else 'entries'}" in source_text
    assert "Class Features are folded into their Class pages" in source_text
    assert "Subclass Features are folded into their Subclass pages" in source_text
    assert "Optional Features are surfaced under their related Class and Subclass pages" in source_text
    assert source_html.index("/systems/entries/first-chapter") < source_html.index(
        "/systems/entries/second-chapter"
    )
    assert source_html.count('name="reference_q"') == 1
    assert (
        f'action="/campaigns/linden-pass/systems/sources/{source_id}"'
        in source_html
    )
    assert 'value=""' in source_html
    assert ">Search rules</button>" in source_html
    assert "Start with a rules reference search" in source_text
    assert "Wayfinder Feature" not in source_text
    assert "Trail Feature" not in source_text
    assert "Optional Trick" not in source_text

    populated_html = populated_search.get_data(as_text=True)
    populated_text = _assert_friendly_surface(
        populated_html,
        forbidden_visible=(source_id, empty_source_id),
    )
    assert 'name="reference_q" value="Measured Guard"' in populated_html
    assert "Rules reference results" in populated_text
    assert "Guarded Measure" in populated_text
    assert (
        'href="/campaigns/linden-pass/systems/entries/guarded-measure"'
        in populated_html
    )

    empty_text = _assert_friendly_surface(
        empty_search.get_data(as_text=True),
        forbidden_visible=(source_id, empty_source_id),
    )
    assert "No rules references found" in empty_text
    assert "Guarded Measure" not in empty_text

    source_empty_html = source_empty.get_data(as_text=True)
    source_empty_text = _assert_friendly_surface(
        source_empty_html,
        forbidden_visible=(source_id, empty_source_id),
    )
    assert "No entries available from this source" in source_empty_text
    assert "Browse other Systems sources" in source_empty_text
    assert "Rules Reference Search" not in source_empty_text

    guarded_dmg_text = _assert_friendly_surface(
        guarded_dmg_source.get_data(as_text=True),
        forbidden_visible=(source_id, empty_source_id, "Guarded DMG Chapter"),
    )
    assert (
        "DMG chapter-backed rules pages default to DM visibility even if a campaign lowers "
        "the broader DMG source to surface specific player-facing DMG rows. Use entry "
        "overrides only when a chapter page should be intentionally exposed more broadly."
        in guarded_dmg_text
    )


def test_systems_category_navigation_preserves_one_type_query_counts_and_deep_links(
    app,
    client,
    sign_in,
    users,
):
    source_id = "P74B-CATEGORY-INTERNAL"
    source_title = "Wayfinder Compendium"
    entries = [
        _entry(source_id, "spell", "amber-beacon-category", "Amber Beacon"),
        _entry(source_id, "spell", "azure-current-category", "Azure Current"),
        _entry(
            source_id,
            "spell",
            "body-only-category",
            "Quiet Current",
            body={"summary": "body-only-needle"},
        ),
        _entry(source_id, "feat", "hidden-feat-category", "Amber Adept"),
    ]
    _upsert_source(app, source_id, source_title, entries)

    sign_in(users["party"]["email"], users["party"]["password"])
    category_path = (
        f"/campaigns/linden-pass/systems/sources/{source_id}/types/spell"
    )
    unfiltered = client.get(category_path)
    filtered = client.get(f"{category_path}?q=Amber+spell")
    title_and_type_miss = client.get(f"{category_path}?q=Amber+feat")
    body_miss = client.get(f"{category_path}?q=body-only-needle")
    inaccessible_type = client.get(
        f"/campaigns/linden-pass/systems/sources/{source_id}/types/condition"
    )
    missing_type = client.get(
        f"/campaigns/linden-pass/systems/sources/{source_id}/types/missing"
    )

    assert unfiltered.status_code == 200
    assert filtered.status_code == 200
    assert title_and_type_miss.status_code == 200
    assert body_miss.status_code == 200
    assert inaccessible_type.status_code == 404
    assert missing_type.status_code == 404

    unfiltered_html = unfiltered.get_data(as_text=True)
    unfiltered_text = _assert_friendly_surface(
        unfiltered_html,
        forbidden_visible=(source_id,),
    )
    assert 'nav aria-label="Systems breadcrumb"' in unfiltered_html
    assert 'href="/campaigns/linden-pass/systems">Systems</a>' in unfiltered_html
    assert (
        f'href="/campaigns/linden-pass/systems/sources/{source_id}"'
        in unfiltered_html
    )
    assert f"{source_title}: Spells" in unfiltered_text
    assert "Showing all 3 spells in this source." in unfiltered_text
    assert 'name="q" value=""' in unfiltered_html
    assert f'action="{category_path}"' in unfiltered_html
    for slug, title in (
        ("amber-beacon-category", "Amber Beacon"),
        ("azure-current-category", "Azure Current"),
        ("body-only-category", "Quiet Current"),
    ):
        assert (
            f'href="/campaigns/linden-pass/systems/entries/{slug}"'
            in unfiltered_html
        )
        assert title in unfiltered_text
    assert "Amber Adept" not in unfiltered_text
    assert "/systems/entries/hidden-feat-category" not in unfiltered_html

    filtered_html = filtered.get_data(as_text=True)
    filtered_text = _assert_friendly_surface(
        filtered_html,
        forbidden_visible=(source_id,),
    )
    assert 'name="q" value="Amber spell"' in filtered_html
    assert "Showing 1 matching entries out of 3 spells in this source." in filtered_text
    assert "Amber Beacon" in filtered_text
    assert "Azure Current" not in filtered_text
    assert "Quiet Current" not in filtered_text

    for response in (title_and_type_miss, body_miss):
        html = response.get_data(as_text=True)
        text = _assert_friendly_surface(html, forbidden_visible=(source_id,))
        assert "No matching Spells" in text
        assert "No spells matched that title/type search." in text
        assert "Amber Beacon" not in text
        assert "Quiet Current" not in text


def _seed_actor_visibility_matrix(app) -> dict[str, str]:
    source_rows = (
        ("P74B-ACTOR-PLAYER", "Player Field Guide", True, VISIBILITY_PLAYERS),
        ("P74B-ACTOR-DM", "Game Master Field Guide", True, VISIBILITY_DM),
        ("P74B-ACTOR-PRIVATE", "Archivist Field Guide", True, VISIBILITY_PRIVATE),
        ("P74B-ACTOR-DISABLED", "Dormant Field Guide", False, VISIBILITY_PLAYERS),
    )
    entries_by_source = {
        "P74B-ACTOR-PLAYER": [
            _entry("P74B-ACTOR-PLAYER", "spell", "actor-player-spell", "Player Spell"),
            _entry("P74B-ACTOR-PLAYER", "spell", "actor-dm-spell", "DM Spell"),
            _entry("P74B-ACTOR-PLAYER", "spell", "actor-private-spell", "Private Spell"),
            _entry("P74B-ACTOR-PLAYER", "spell", "actor-disabled-spell", "Disabled Spell"),
            _entry("P74B-ACTOR-PLAYER", "rule", "actor-player-rule", "Player Rule"),
        ],
        "P74B-ACTOR-DM": [
            _entry("P74B-ACTOR-DM", "spell", "actor-dm-source-spell", "DM Source Spell"),
        ],
        "P74B-ACTOR-PRIVATE": [
            _entry(
                "P74B-ACTOR-PRIVATE",
                "spell",
                "actor-private-source-spell",
                "Private Source Spell",
            ),
        ],
        "P74B-ACTOR-DISABLED": [
            _entry(
                "P74B-ACTOR-DISABLED",
                "spell",
                "actor-disabled-source-spell",
                "Disabled Source Spell",
            ),
        ],
    }
    for source_id, title, enabled, visibility in source_rows:
        _upsert_source(
            app,
            source_id,
            title,
            entries_by_source[source_id],
            enabled=enabled,
            visibility=visibility,
        )
    with app.app_context():
        service = app.extensions["systems_service"]
        store = app.extensions["systems_store"]
        library_slug = service.get_campaign_library_slug("linden-pass")
        entry_by_slug = {
            entry["slug"]: entry["entry_key"]
            for entry in entries_by_source["P74B-ACTOR-PLAYER"]
        }
        for slug, visibility, enabled in (
            ("actor-dm-spell", VISIBILITY_DM, None),
            ("actor-private-spell", VISIBILITY_PRIVATE, None),
            ("actor-disabled-spell", None, False),
        ):
            store.upsert_campaign_entry_override(
                "linden-pass",
                library_slug=library_slug,
                entry_key=entry_by_slug[slug],
                visibility_override=visibility,
                is_enabled_override=enabled,
            )
    return {source_id: title for source_id, title, *_ in source_rows}


def test_systems_source_category_effective_actor_visibility_matrix(
    app,
    client,
    sign_in,
    users,
):
    source_titles = _seed_actor_visibility_matrix(app)
    player_source = "/campaigns/linden-pass/systems/sources/P74B-ACTOR-PLAYER"
    player_spells = f"{player_source}/types/spell"
    dm_source = "/campaigns/linden-pass/systems/sources/P74B-ACTOR-DM"
    private_source = "/campaigns/linden-pass/systems/sources/P74B-ACTOR-PRIVATE"
    disabled_source = "/campaigns/linden-pass/systems/sources/P74B-ACTOR-DISABLED"

    def read_for(actor: str) -> tuple[str, str]:
        sign_in(users[actor]["email"], users[actor]["password"])
        source_response = client.get(player_source)
        category_response = client.get(player_spells)
        assert source_response.status_code == 200
        assert category_response.status_code == 200
        source_text = _assert_friendly_surface(
            source_response.get_data(as_text=True),
            forbidden_visible=tuple(source_titles),
        )
        category_text = _assert_friendly_surface(
            category_response.get_data(as_text=True),
            forbidden_visible=tuple(source_titles),
        )
        return source_text, category_text

    player_source_text, player_category_text = read_for("party")
    assert "2 entries are available to you." in player_source_text
    assert "Spells 1 entry" in player_source_text
    assert "Showing all 1 spells in this source." in player_category_text
    assert "Player Spell" in player_category_text
    assert "DM Spell" not in player_category_text
    assert "Private Spell" not in player_category_text
    assert "Disabled Spell" not in player_category_text
    assert "Systems settings" not in player_source_text
    assert client.get(dm_source).status_code == 404
    assert client.get(private_source).status_code == 404
    assert client.get(disabled_source).status_code == 404

    dm_source_text, dm_category_text = read_for("dm")
    assert "3 entries are available to you." in dm_source_text
    assert "Spells 2 entries" in dm_source_text
    assert "Showing all 2 spells in this source." in dm_category_text
    assert "Player Spell" in dm_category_text
    assert "DM Spell" in dm_category_text
    assert "Private Spell" not in dm_category_text
    assert "Disabled Spell" not in dm_category_text
    assert "Systems settings" in dm_source_text
    assert client.get(dm_source).status_code == 200
    assert client.get(private_source).status_code == 404
    assert client.get(disabled_source).status_code == 404

    admin_source_text, admin_category_text = read_for("admin")
    assert "4 entries are available to you." in admin_source_text
    assert "Spells 3 entries" in admin_source_text
    assert "Showing all 3 spells in this source." in admin_category_text
    assert "Player Spell" in admin_category_text
    assert "DM Spell" in admin_category_text
    assert "Private Spell" in admin_category_text
    assert "Disabled Spell" not in admin_category_text
    assert "Systems settings" in admin_source_text
    assert client.get(dm_source).status_code == 200
    assert client.get(private_source).status_code == 200
    assert client.get(disabled_source).status_code == 404

    with client.session_transaction() as browser_session:
        browser_session[VIEW_AS_SESSION_KEY] = users["party"]["id"]
    projected_source = client.get(player_source)
    projected_category = client.get(player_spells)
    assert projected_source.status_code == 200
    assert projected_category.status_code == 200
    projected_source_text = _assert_friendly_surface(
        projected_source.get_data(as_text=True),
        forbidden_visible=tuple(source_titles),
    )
    projected_category_text = _assert_friendly_surface(
        projected_category.get_data(as_text=True),
        forbidden_visible=tuple(source_titles),
    )
    assert "2 entries are available to you." in projected_source_text
    assert "Showing all 1 spells in this source." in projected_category_text
    assert "Player Spell" in projected_category_text
    assert "DM Spell" not in projected_category_text
    assert "Private Spell" not in projected_category_text
    assert "Systems settings" not in projected_source_text
    assert client.get(dm_source).status_code == 404
    assert client.get(private_source).status_code == 404
    assert client.get(disabled_source).status_code == 404
