from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import markdown
import yaml

from .models import Campaign, Page, page_sort_key

FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
OBSIDIAN_LINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\s/-]", "", value).strip().lower()
    cleaned = cleaned.replace("\\", "/")
    parts = [re.sub(r"\s+", "-", part.strip()) for part in cleaned.split("/") if part.strip()]
    return "/".join(parts)


def normalize_lookup(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def title_from_slug(value: str) -> str:
    tail = value.split("/")[-1]
    words = tail.replace("-", " ").strip()
    return words.title() if words else value


def parse_frontmatter(raw_text: str) -> tuple[dict[str, Any], str]:
    normalized = raw_text.replace("\r\n", "\n")
    match = FRONTMATTER_PATTERN.match(normalized)
    if not match:
        return {}, normalized

    metadata = yaml.safe_load(match.group(1)) or {}
    body = normalized[match.end() :]
    return metadata, body


def extract_obsidian_targets(markdown_text: str) -> list[str]:
    targets: list[str] = []
    for raw_target in OBSIDIAN_LINK_PATTERN.findall(markdown_text):
        link_target = raw_target.split("|", 1)[0].split("#", 1)[0].strip()
        if link_target:
            targets.append(link_target)
    return targets


@dataclass(slots=True)
class Repository:
    campaigns: dict[str, Campaign]
    page_store: Any

    @classmethod
    def load(cls, campaigns_dir: Path, page_store: Any) -> "Repository":
        campaigns: dict[str, Campaign] = {}

        for config_path in sorted(campaigns_dir.glob("*/campaign.yaml")):
            campaign = load_campaign(config_path, page_store)
            campaigns[campaign.slug] = campaign

        for campaign in campaigns.values():
            resolve_campaign_links(campaign)

        return cls(campaigns=campaigns, page_store=page_store)

    def get_campaign(self, slug: str) -> Campaign | None:
        return self.campaigns.get(slug)

    def visible_pages(self, campaign_slug: str) -> list[Page]:
        campaign = self.get_campaign(campaign_slug)
        if not campaign:
            return []
        return campaign.visible_pages()

    def get_page(self, campaign_slug: str, page_slug: str) -> Page | None:
        campaign = self.get_campaign(campaign_slug)
        if not campaign:
            return None

        return campaign.get_visible_page(page_slug)

    def get_page_body_html(self, campaign_slug: str, page_slug: str) -> str | None:
        campaign = self.get_campaign(campaign_slug)
        if not campaign:
            return None

        page = campaign.get_visible_page(page_slug)
        if page is None:
            return None

        return render_page_content(campaign, page, self.page_store)

    def get_section_pages(self, campaign_slug: str, section_slug: str) -> list[Page]:
        campaign = self.get_campaign(campaign_slug)
        if not campaign:
            return []
        return [
            page for page in campaign.visible_pages() if slugify(page.section) == section_slug
        ]

    def search_pages(self, campaign_slug: str, query: str) -> list[Page]:
        campaign = self.get_campaign(campaign_slug)
        if not campaign:
            return []

        normalized_query = query.strip().lower()
        if not normalized_query:
            return campaign.visible_pages()

        matching_slugs = set(self.page_store.search_route_slugs(campaign_slug, normalized_query))
        results = [
            page
            for page in campaign.visible_pages()
            if page.route_slug in matching_slugs
        ]
        return sorted(results, key=page_sort_key)

    def get_backlinks(self, campaign_slug: str, page_slug: str) -> list[Page]:
        campaign = self.get_campaign(campaign_slug)
        page = self.get_page(campaign_slug, page_slug)
        if not campaign or not page:
            return []
        return campaign.visible_backlinks_for(page)

def load_campaign(config_path: Path, page_store: Any) -> Campaign:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    content_root = config_path.parent / config.get("player_content_dir", "content")
    assets_root = config_path.parent / config.get("asset_dir", "assets")

    campaign = Campaign(
        title=config["title"],
        slug=config.get("slug", slugify(config["title"])),
        summary=config.get("summary", ""),
        system=config.get("system", "").strip(),
        current_session=int(config.get("current_session", 0)),
        source_wiki_root=config.get("source_wiki_root", ""),
        player_content_dir=str(content_root),
        assets_dir=str(assets_root),
        systems_library_slug=str(config.get("systems_library", "") or "").strip(),
        systems_source_defaults=list(config.get("systems_sources") or []),
    )

    for page in page_store.list_pages(campaign.slug, content_dir=content_root):
        if page.route_slug in campaign.pages:
            raise ValueError(f"Duplicate page slug '{page.route_slug}' in campaign '{campaign.slug}'")
        campaign.pages[page.route_slug] = page

    return campaign


def build_page_from_content(
    *,
    source_path: str,
    default_slug: str,
    metadata: dict[str, Any],
    body_markdown: str,
    raw_link_targets: list[str] | None = None,
    content_loaded: bool = False,
) -> Page:
    title = metadata.get("title") or title_from_slug(default_slug)
    aliases = metadata.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]

    default_parts = Path(default_slug).parts
    if default_parts:
        default_section = default_parts[0].replace("-", " ").title()
    else:
        default_section = "Pages"

    route_slug = slugify(metadata.get("slug", default_slug))
    raw_display_order = metadata.get("display_order")
    display_order = 10_000 if raw_display_order in (None, "") else int(raw_display_order)

    return Page(
        title=title,
        route_slug=route_slug,
        source_path=source_path,
        body_markdown=body_markdown if content_loaded else "",
        section=metadata.get("section", default_section),
        subsection=metadata.get("subsection", "").strip(),
        page_type=metadata.get("type", "page"),
        display_order=display_order,
        published=bool(metadata.get("published", True)),
        aliases=list(aliases),
        summary=metadata.get("summary", "").strip(),
        image_path=metadata.get("image", "").strip(),
        image_alt=metadata.get("image_alt", "").strip(),
        image_caption=metadata.get("image_caption", "").strip(),
        reveal_after_session=int(metadata.get("reveal_after_session", 0) or 0),
        source_ref=metadata.get("source_ref", "").strip(),
        raw_link_targets=list(raw_link_targets or extract_obsidian_targets(body_markdown)),
        content_loaded=content_loaded,
    )


def load_page(file_path: Path, content_root: Path) -> Page:
    raw_text = file_path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(raw_text)

    rel_path = file_path.relative_to(content_root).with_suffix("")
    return build_page_from_content(
        source_path=str(file_path),
        default_slug=slugify(rel_path.as_posix()),
        metadata=metadata,
        body_markdown=body,
        raw_link_targets=extract_obsidian_targets(body),
        content_loaded=False,
    )


def build_alias_index(campaign: Campaign) -> dict[str, str]:
    index: dict[str, str] = {}
    for page in campaign.visible_pages():
        keys = {page.route_slug, page.title, *page.aliases}
        for key in keys:
            normalized = normalize_lookup(key)
            if normalized and normalized not in index:
                index[normalized] = page.route_slug
    return index


def resolve_link_targets(raw_targets: list[str], alias_index: dict[str, str]) -> list[str]:
    resolved_links: list[str] = []
    for raw_target in raw_targets:
        target_part = raw_target.split("|", 1)[0]
        target_core = target_part.split("#", 1)[0].strip()
        lookup_key = normalize_lookup(target_core)
        page_slug = alias_index.get(lookup_key)
        if page_slug:
            resolved_links.append(page_slug)
    return resolved_links


def resolve_campaign_links(campaign: Campaign) -> None:
    alias_index = build_alias_index(campaign)
    campaign.alias_index = alias_index
    backlinks: defaultdict[str, set[str]] = defaultdict(set)

    for page in campaign.pages.values():
        page.body_markdown = ""
        page.body_html = ""
        page.content_loaded = False
        page.html_loaded = False
        page.resolved_links = []
        page.backlinks = []

    for page in campaign.visible_pages():
        resolved_links = resolve_link_targets(page.raw_link_targets, alias_index)
        page.resolved_links = resolved_links
        for target_slug in resolved_links:
            backlinks[target_slug].add(page.route_slug)

    for route_slug, incoming_links in backlinks.items():
        if route_slug in campaign.pages:
            campaign.pages[route_slug].backlinks = sorted(incoming_links)


def load_page_content(campaign: Campaign, page: Page, page_store: Any) -> str:
    if page.content_loaded:
        return page.body_markdown

    body = page_store.get_page_body_markdown(campaign.slug, page.route_slug)
    if body is None:
        body = ""
    page.body_markdown = body
    page.content_loaded = True
    return body


def render_page_content(campaign: Campaign, page: Page, page_store: Any) -> str:
    if page.html_loaded:
        return page.body_html

    body = load_page_content(campaign, page, page_store)
    renderer = markdown.Markdown(extensions=["fenced_code", "tables", "sane_lists"])
    resolved_links: list[str] = []
    linked_markdown = render_obsidian_links(body, campaign.alias_index, resolved_links)
    page.body_html = renderer.convert(linked_markdown)
    page.resolved_links = resolved_links
    page.html_loaded = True
    return page.body_html


def render_obsidian_links(
    markdown_text: str, alias_index: dict[str, str], resolved_links: list[str]
) -> str:
    def replace(match: re.Match[str]) -> str:
        raw_target = match.group(1).strip()
        target_part, _, label_part = raw_target.partition("|")
        target_core, _, heading = target_part.partition("#")
        label = label_part.strip() or heading.strip() or target_core.strip()
        lookup_key = normalize_lookup(target_core.strip())
        page_slug = alias_index.get(lookup_key)

        if not page_slug:
            return f"<span class=\"broken-link\">{label}</span>"

        resolved_links.append(page_slug)
        return f"[{label}](/campaigns/{{campaign_slug}}/pages/{page_slug})"

    return OBSIDIAN_LINK_PATTERN.sub(replace, markdown_text)
