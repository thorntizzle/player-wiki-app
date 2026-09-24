from __future__ import annotations

from html.parser import HTMLParser

import markdown
import pytest

from player_wiki import character_presenter
from player_wiki.models import Campaign, Page
from player_wiki.repository import (
    build_alias_index, extract_obsidian_targets, render_obsidian_links, render_page_content,
    resolve_campaign_links, resolve_link_target, resolve_link_targets,
)
from player_wiki.session_presenter import render_session_article_html


def page(route, *, title=None, aliases=(), **options):
    return Page(title=title or route, route_slug=route, source_path="test://" + route,
                body_markdown="", section="Lore", page_type="lore", aliases=list(aliases), **options)


def campaign(*pages):
    return Campaign(title="Link fixture", slug="link-fixture", summary="", system="DND-5E",
                    current_session=2, source_wiki_root="", player_content_dir="", assets_dir="",
                    pages={item.route_slug: item for item in pages})


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.hrefs = []
        self.tags = []
        self.text = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "a":
            self.hrefs.append(dict(attrs)["href"])

    def handle_data(self, data):
        self.text.append(data)


@pytest.mark.parametrize("target,expected", [
    ("npcs/mara", "npcs/mara"), ("  npcs/mara  ", "npcs/mara"), ("NPCS/MARA", None),
    ("ab/c", "ab/c"), ("a/bc", "a/bc"), ("abc", None),
    ("places/frost-mere", "places/frost-mere"), ("places/frostmere", "places/frostmere"),
    ("PLACES/FROST MERE", None), ("Case/Path", "Case/Path"), ("case/path", "case/path"),
    ("CASE/PATH", None), ("Lore & Runes", "lore/runes"), ("missing", None),
])
def test_exact_canonical_paths_precede_only_unique_normalized_fallback(target, expected):
    pages = [page("rival", title="A first rival", aliases=["npcs/mara"]), page("npcs/mara"),
             page("ab/c"), page("a/bc"), page("places/frost-mere"), page("places/frostmere"),
             page("Case/Path"), page("case/path"), page("lore/runes", aliases=["Lore & Runes"])]
    for order in (pages, list(reversed(pages))):
        index = build_alias_index(campaign(*order))
        assert resolve_link_target(target, index) == expected
        resolved = []
        html = render_obsidian_links(f"[[{target}]]", index, resolved)
        assert resolved == ([] if expected is None else [expected])
        assert resolve_link_targets([target], index) == resolved
        assert ('class="broken-link"' in html) is (expected is None)


def test_alias_title_route_collisions_count_unique_visible_pages_only():
    first = page("first", title="Shared", aliases=["SHARED", "shared", "only one"])
    second = page("second", aliases=["Shared"])
    third = page("shared")
    data = campaign(first, second, third)
    index = build_alias_index(data)
    assert resolve_link_target("shared", index) == "shared"
    assert resolve_link_target("SHARED", index) is None
    assert resolve_link_target("ONLY-ONE", index) == "first"
    second.published = False
    third.reveal_after_session = 3
    index = build_alias_index(data)
    assert resolve_link_target("Shared", index) == "first"
    assert "second" not in repr(index) and "shared'" not in repr(index.canonical_routes)


@pytest.mark.parametrize("visibility", ["unpublished", "future", "overview"])
def test_unavailable_targets_do_not_resolve_or_expose_hidden_metadata(visibility):
    hidden = page("hidden/secret", title="Secret catalog name", aliases=["Secret alias"])
    if visibility == "unpublished":
        hidden.published = False
    elif visibility == "future":
        hidden.reveal_after_session = 3
    else:
        hidden.page_type = "overview"
    index = build_alias_index(campaign(hidden, page("public")))
    for target in ("hidden/secret", "Secret alias"):
        resolved = []
        html = render_obsidian_links(f"[[{target}|Known label]]", index, resolved)
        assert html == '<span class="broken-link">Known label</span>'
        assert resolved == []
    assert "Secret catalog name" not in repr(index)


@pytest.mark.parametrize("link,label", [
    ("[[ target#Heading | Explicit label ]]", "Explicit label"),
    ("[[target#Heading]]", "Heading"), ("[[ target ]]", "target"),
    ("[[target#Heading|   ]]", "Heading"),
    ('[[target|<img src=x onerror="boom"> & text]]', '<img src=x onerror="boom"> & text'),
])
@pytest.mark.parametrize("known", [False, True])
def test_labels_headings_and_safe_text_preserve_link_presentation(link, label, known):
    data = campaign(page("target")) if known else campaign()
    index = build_alias_index(data)
    targets = []
    html = render_obsidian_links(link, index, targets)
    parsed = Links(markdown.markdown(html))
    assert parsed.tags == (["p", "a"] if known else ["p", "span"])
    assert "".join(parsed.text) == label
    assert "#Heading" not in html
    assert resolve_link_targets(extract_obsidian_targets(link), index) == targets
    rendered = render_session_article_html(data, link)
    assert "img" not in Links(rendered).tags
    assert Links(rendered).hrefs == (["/campaigns/link-fixture/pages/target"] if known else [])


def test_repository_backlinks_session_and_character_use_same_resolution(app):
    body = "[[ab/c#Heading|Exact]] [[ABC|Ambiguous]] [[unique alias]] [[hidden/secret|Unavailable]]"
    source = page("source")
    source.raw_link_targets = extract_obsidian_targets(body)
    data = campaign(source, page("ab/c"), page("a/bc"), page("unique", aliases=["unique alias"]),
                    page("hidden/secret", published=False))
    resolve_campaign_links(data)
    assert source.resolved_links == ["ab/c", "unique"]
    assert data.pages["ab/c"].backlinks == ["source"]
    assert data.pages["a/bc"].backlinks == []
    assert data.pages["unique"].backlinks == ["source"]
    assert data.pages["hidden/secret"].backlinks == []
    class Store:
        def get_page_body_markdown(self, campaign_slug, route):
            return body
    repo_html = render_page_content(data, source, Store()).replace("{campaign_slug}", data.slug)
    session_html = render_session_article_html(data, body)
    with app.test_request_context("/"):
        character_html = character_presenter._render_campaign_markdown_html(data, body)
    expected = ["/campaigns/link-fixture/pages/ab/c", "/campaigns/link-fixture/pages/unique"]
    assert Links(repo_html).hrefs == Links(session_html).hrefs == Links(character_html).hrefs == expected
    assert source.resolved_links == ["ab/c", "unique"]
    source.published = False
    resolve_campaign_links(data)
    assert data.pages["ab/c"].backlinks == []


def test_character_cache_tracks_exact_paths_collision_and_visibility_with_reuse(app, monkeypatch):
    data = campaign(page("ab/c", aliases=["shared"]), page("other", aliases=["shared"]))
    text = "[[ab/c]] [[SHARED]]"
    conversions = []
    real_convert = character_presenter.markdown.Markdown.convert
    def convert(renderer, source):
        conversions.append(source)
        return real_convert(renderer, source)
    monkeypatch.setattr(character_presenter.markdown.Markdown, "convert", convert)
    def render():
        first = character_presenter._render_campaign_markdown_html(data, text)
        assert character_presenter._render_campaign_markdown_html(data, text) == first
        return Links(first).hrefs
    with app.test_request_context("/"):
        assert render() == ["/campaigns/link-fixture/pages/ab/c"]
        # Adding a canonical path changes exact resolution even while its normalized key is ambiguous.
        data.pages["a/bc"] = page("a/bc", aliases=["shared"])
        assert render() == ["/campaigns/link-fixture/pages/ab/c"]
        data.pages["ab/c"].published = False
        assert render() == ["/campaigns/link-fixture/pages/a/bc"]
        data.pages["other"].published = False
        assert render() == ["/campaigns/link-fixture/pages/a/bc", "/campaigns/link-fixture/pages/a/bc"]
        data.pages["a/bc"].reveal_after_session = 3
        assert render() == []
        data.current_session = 3
        assert render() == ["/campaigns/link-fixture/pages/a/bc", "/campaigns/link-fixture/pages/a/bc"]
    assert len(conversions) == 5  # Returning to an identical visible index reuses its earlier result.


def test_character_cache_invalidates_when_only_exact_canonical_set_changes(app):
    data = campaign(page("ab/c"), page("a/bc"))
    before = build_alias_index(data)
    with app.test_request_context("/"):
        assert Links(character_presenter._render_campaign_markdown_html(data, "[[abc]]")).hrefs == []
        data.pages["abc"] = page("abc")
        after = build_alias_index(data)
        assert before.unique_targets == after.unique_targets
        assert before.canonical_routes != after.canonical_routes
        assert Links(character_presenter._render_campaign_markdown_html(data, "[[abc]]")).hrefs == [
            "/campaigns/link-fixture/pages/abc"
        ]


@pytest.mark.parametrize("route,encoded", [
    ("places/Frost.Mere+(North)", "places/Frost.Mere%2B%28North%29"),
    ('lore/"runes"', "lore/%22runes%22"),
    ("lore/風", "lore/%E9%A2%A8"),
])
def test_exact_canonical_route_punctuation_is_preserved_and_url_encoded(route, encoded):
    data = campaign(page(route))
    index = build_alias_index(data)
    assert resolve_link_target(route, index) == route
    assert resolve_link_targets([route], index) == [route]
    rendered = render_session_article_html(data, f"[[{route}|Exact destination]]")
    assert Links(rendered).hrefs == [f"/campaigns/link-fixture/pages/{encoded}"]
