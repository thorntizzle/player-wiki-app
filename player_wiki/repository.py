from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

import markdown
import yaml

from .models import Campaign, Page, WikiLinkIndex, is_session_summary_page, page_sort_key, session_summary_sort_key
from .rich_text import sanitize_rich_html
from .system_policy import default_systems_library_slug, normalize_system_code

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
    input_specs: tuple[tuple[Path, Path], ...] = ()
    config_specs: tuple[CampaignConfig, ...] = ()

    @classmethod
    def load(cls, campaigns_dir: Path, page_store: Any) -> "Repository":
        from .committed_publication import active
        if active():
            from .repository_store import RepositoryStore
            return RepositoryStore(campaigns_dir, page_store=page_store, reload_enabled=False, scan_interval_seconds=0).refresh_from_database()
        campaigns: dict[str, Campaign] = {}
        input_specs: list[tuple[Path, Path]] = []
        config_specs: list[CampaignConfig] = []

        for config_path in sorted(campaigns_dir.glob("*/campaign.yaml")):
            spec = load_campaign_config(config_path)
            config_specs.append(spec)
            campaign = load_campaign(config_path, page_store, config_spec=spec)
            input_specs.append((config_path, Path(campaign.player_content_dir)))
            campaigns[campaign.slug] = campaign

        for campaign in campaigns.values():
            resolve_campaign_links(campaign)

        return cls(
            campaigns=campaigns,
            page_store=page_store,
            input_specs=tuple(input_specs),
            config_specs=tuple(config_specs),
        )

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

    def get_page_redirect(self, campaign_slug: str, page_slug: str) -> str | None:
        campaign = self.get_campaign(campaign_slug)
        if not campaign:
            return None

        target_slug = campaign.page_redirects.get(slugify(page_slug))
        if not target_slug:
            return None
        target_page = campaign.get_visible_page(target_slug)
        return target_page.route_slug if target_page is not None else None

    def get_page_body_html(self, campaign_slug: str, page_slug: str) -> str | None:
        campaign = self.get_campaign(campaign_slug)
        if not campaign:
            return None

        page = campaign.get_visible_page(page_slug)
        if page is None:
            return None

        from .committed_publication import CommittedSourceConflict
        try:
            return render_page_content(campaign, page, self.page_store)
        except CommittedSourceConflict:
            return None

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

        from .committed_publication import active, config, current, page_rows, read_snapshot
        if active():
            @read_snapshot
            def committed_search():
                settings_source, settings = config(campaign_slug)
                normalized = query.strip().lower()
                matching = []
                for row in page_rows(campaign_slug):
                    if normalized and normalized not in row["searchable_text"]:
                        continue
                    cached = campaign.pages.get(row["route_slug"])
                    if (cached is None or cached.source_path != f"db://{campaign_slug}/{row['page_ref']}" or
                            cached.committed_config_revision != settings_source["revision"]):
                        continue
                    source = current(campaign_slug, "page", row["page_ref"])
                    if source is None or cached.committed_revision != source["revision"]:
                        continue
                    if not row["published"] or row["reveal_after_session"] > int(settings["current_session"]):
                        continue
                    if cached.is_deprecated_wiki_overview:
                        continue
                    matching.append(cached)
                return sorted(matching, key=page_sort_key)
            return committed_search()

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

    def get_latest_session_summary_page(self, campaign_slug: str) -> Page | None:
        campaign = self.get_campaign(campaign_slug)
        if not campaign:
            return None
        candidates = [page for page in campaign.visible_pages() if is_session_summary_page(page)]
        if not candidates:
            return None
        return max(candidates, key=session_summary_sort_key)

    def get_backlinks(self, campaign_slug: str, page_slug: str) -> list[Page]:
        campaign = self.get_campaign(campaign_slug)
        page = self.get_page(campaign_slug, page_slug)
        if not campaign or not page:
            return []
        return campaign.visible_backlinks_for(page)

@dataclass(frozen=True, slots=True)
class CampaignConfig:
    config_path: Path
    config: dict[str, Any]
    content_root: Path
    slug: str
    witnesses: tuple


def load_campaign_config(config_path: Path) -> CampaignConfig:
    # Local import avoids a cycle with the independent page normalization owner.
    from .campaign_page_refresh import ancestor_witnesses, validate_witnesses

    from .committed_publication import active, config as committed_config
    if active():
        _, config = committed_config(config_path.parent.name)
        return CampaignConfig(config_path, config, config_path.parent / config.get("player_content_dir", "content"), config["slug"], ())
    witnesses = ancestor_witnesses(config_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    content_root = config_path.parent / config.get("player_content_dir", "content")
    slug = config.get("slug", slugify(config["title"]))
    validate_witnesses(witnesses, reason="config")
    return CampaignConfig(config_path, config, content_root, slug, witnesses)


def load_campaign(config_path: Path, page_store: Any, *, config_spec: CampaignConfig | None = None,
                  page_snapshot: list[Page] | None = None) -> Campaign:
    from .committed_publication import active
    if active():
        config_spec = load_campaign_config(config_path)
        page_snapshot = page_store.list_pages(config_spec.slug)
    spec = config_spec if config_spec is not None else load_campaign_config(config_path)
    config = spec.config
    content_root = spec.content_root
    assets_root = config_path.parent / config.get("asset_dir", "assets")

    campaign = Campaign(
        title=config["title"],
        slug=config.get("slug", slugify(config["title"])),
        summary=config.get("summary", ""),
        system=normalize_system_code(config.get("system", "")),
        current_session=int(config.get("current_session", 0)),
        source_wiki_root=config.get("source_wiki_root", ""),
        player_content_dir=str(content_root),
        assets_dir=str(assets_root),
        systems_library_slug=default_systems_library_slug(config.get("systems_library", "")),
        systems_source_defaults=list(config.get("systems_sources") or []),
    )

    if page_snapshot is None:
        page_store.ensure_campaign_seeded(campaign.slug, content_root)
        page_snapshot = page_store.list_pages(campaign.slug)
    for page in page_snapshot:
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
    redirect_from = metadata.get("redirect_from") or []
    if isinstance(redirect_from, str):
        redirect_from = [redirect_from]

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
        redirect_from=[str(value).strip() for value in redirect_from if str(value).strip()],
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


def build_alias_index(campaign: Campaign) -> WikiLinkIndex:
    candidates: defaultdict[str, set[str]] = defaultdict(set)
    visible_pages = campaign.visible_pages()
    for page in visible_pages:
        keys = {page.route_slug, page.title, *page.aliases}
        for key in keys:
            normalized = normalize_lookup(key)
            if normalized:
                candidates[normalized].add(page.route_slug)
    return WikiLinkIndex(
        canonical_routes=frozenset(page.route_slug for page in visible_pages),
        unique_targets={key: next(iter(targets)) for key, targets in candidates.items() if len(targets) == 1},
    )


def resolve_link_target(raw_target: str, alias_index: WikiLinkIndex) -> str | None:
    target_core = raw_target.split("|", 1)[0].split("#", 1)[0].strip()
    if target_core in alias_index.canonical_routes:
        return target_core
    return alias_index.unique_targets.get(normalize_lookup(target_core))


def resolve_link_targets(raw_targets: list[str], alias_index: WikiLinkIndex) -> list[str]:
    resolved_links: list[str] = []
    for raw_target in raw_targets:
        page_slug = resolve_link_target(raw_target, alias_index)
        if page_slug:
            resolved_links.append(page_slug)
    return resolved_links


def build_page_redirect_index(campaign: Campaign) -> dict[str, str]:
    redirects: dict[str, str] = {}
    visible_pages = campaign.visible_pages()
    visible_route_slugs = {page.route_slug for page in visible_pages}

    for page in visible_pages:
        for raw_redirect in page.redirect_from:
            redirect_slug = slugify(raw_redirect)
            if (
                not redirect_slug
                or redirect_slug == page.route_slug
                or redirect_slug in visible_route_slugs
            ):
                continue
            existing_target = redirects.get(redirect_slug)
            if existing_target is not None and existing_target != page.route_slug:
                raise ValueError(
                    f"Duplicate page redirect '{redirect_slug}' in campaign '{campaign.slug}'"
                )
            redirects[redirect_slug] = page.route_slug

    return redirects


def resolve_campaign_links(campaign: Campaign) -> None:
    alias_index = build_alias_index(campaign)
    campaign.alias_index = alias_index
    campaign.page_redirects = build_page_redirect_index(campaign)
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
    from .committed_publication import active, config, current, page_row, read_snapshot, CommittedSourceConflict
    if active():
        @read_snapshot
        def committed_body():
            if not page.source_path.startswith(f"db://{campaign.slug}/"):
                raise CommittedSourceConflict("Page identity is unavailable.")
            ref = page.source_path[len(f"db://{campaign.slug}/"):]
            settings_source, settings = config(campaign.slug)
            source = current(campaign.slug, "page", ref)
            row = page_row(campaign.slug, ref)
            if (source is None or row is None or
                    page.committed_revision != source["revision"] or
                    page.committed_config_revision != settings_source["revision"] or
                    row["route_slug"] != page.route_slug or
                    not row["published"] or
                    row["reveal_after_session"] > int(settings["current_session"]) or
                    page.is_deprecated_wiki_overview):
                raise CommittedSourceConflict("Page changed or is not visible.")
            return str(row["body_markdown"] or "")
        return committed_body()
    if page.content_loaded:
        return page.body_markdown

    body = page_store.get_page_body_markdown(campaign.slug, page.route_slug)
    if body is None:
        body = ""
    page.body_markdown = body
    page.content_loaded = True
    return body


def render_page_content(campaign: Campaign, page: Page, page_store: Any) -> str:
    from .committed_publication import active
    if page.html_loaded and not active():
        return page.body_html

    body = load_page_content(campaign, page, page_store)
    renderer = markdown.Markdown(extensions=["fenced_code", "tables", "sane_lists"])
    resolved_links: list[str] = []
    linked_markdown = render_obsidian_links(body, campaign.alias_index, resolved_links)
    page.body_html = sanitize_rich_html(renderer.convert(linked_markdown))
    page.resolved_links = resolved_links
    page.html_loaded = True
    return page.body_html


def render_obsidian_links(
    markdown_text: str, alias_index: WikiLinkIndex, resolved_links: list[str]
) -> str:
    def replace(match: re.Match[str]) -> str:
        raw_target = match.group(1).strip()
        target_part, _, label_part = raw_target.partition("|")
        target_core, _, heading = target_part.partition("#")
        label = label_part.strip() or heading.strip() or target_core.strip()
        page_slug = resolve_link_target(raw_target, alias_index)
        safe_label = escape(label)

        if not page_slug:
            return f"<span class=\"broken-link\">{safe_label}</span>"

        resolved_links.append(page_slug)
        safe_label = safe_label.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
        return f'[{safe_label}](/campaigns/{{campaign_slug}}/pages/{quote(page_slug, safe="/")})'

    return OBSIDIAN_LINK_PATTERN.sub(replace, markdown_text)
