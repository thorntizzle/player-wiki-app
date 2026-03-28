from __future__ import annotations

from dataclasses import dataclass, field

SECTION_ORDER = {
    "Overview": 0,
    "Sessions": 10,
    "Notes": 15,
    "Locations": 20,
    "NPCs": 30,
    "Races": 35,
    "Factions": 40,
    "Gods": 45,
    "Discoveries": 50,
    "Items": 60,
    "Spells": 70,
    "Mechanics": 80,
    "Lore": 90,
}

SUBSECTION_ORDER = {
    "Factions": {
        "Major Powers": 0,
        "Campaign Institutions": 10,
        "Major Guilds": 20,
        "Minor Guilds": 30,
    },
    "Gods": {
        "Primeval Gods": 0,
        "Modern Gods": 10,
        "Fallen Gods": 20,
    },
    "Locations": {
        "Districts and City Areas": 0,
        "Civic and Institutional Sites": 10,
        "Venues and Residences": 20,
        "Infrastructure and Underworks": 30,
    },
    "Mechanics": {
        "Variant and House Rules": 0,
        "Class Modifications": 10,
        "Weapons": 20,
        "Facilities": 30,
        "Downtime Rules": 40,
    },
}


def section_sort_key(section_name: str) -> tuple[int, str]:
    return (SECTION_ORDER.get(section_name, 1000), section_name.lower())


def subsection_sort_key(section_name: str, subsection_name: str) -> tuple[int, str]:
    normalized_subsection = subsection_name.strip()
    section_subsections = SUBSECTION_ORDER.get(section_name, {})
    return (
        section_subsections.get(normalized_subsection, 1000),
        normalized_subsection.lower(),
    )


def page_sort_key(page: "Page") -> tuple[int, str, int, str, int, int, str]:
    section_rank, normalized_section = section_sort_key(page.section)
    subsection_rank, normalized_subsection = subsection_sort_key(page.section, page.subsection)
    if page.section == "Sessions" and page.page_type == "session":
        session_order = page.reveal_after_session if page.reveal_after_session > 0 else 10_000
        return (
            section_rank,
            normalized_section,
            subsection_rank,
            normalized_subsection,
            page.display_order,
            session_order,
            page.title.lower(),
        )
    return (
        section_rank,
        normalized_section,
        subsection_rank,
        normalized_subsection,
        page.display_order,
        10_000,
        page.title.lower(),
    )


@dataclass(slots=True)
class Page:
    title: str
    route_slug: str
    source_path: str
    body_markdown: str
    section: str
    page_type: str
    subsection: str = ""
    display_order: int = 10_000
    published: bool = True
    aliases: list[str] = field(default_factory=list)
    summary: str = ""
    image_path: str = ""
    image_alt: str = ""
    image_caption: str = ""
    reveal_after_session: int = 0
    source_ref: str = ""
    body_html: str = ""
    raw_link_targets: list[str] = field(default_factory=list)
    resolved_links: list[str] = field(default_factory=list)
    backlinks: list[str] = field(default_factory=list)
    content_loaded: bool = False
    html_loaded: bool = False

    @property
    def searchable_text(self) -> str:
        parts = [self.title, self.subsection, self.summary, self.body_markdown, " ".join(self.aliases)]
        return " ".join(part for part in parts if part).lower()

    @property
    def is_pinned(self) -> bool:
        return self.display_order < 10_000

    @property
    def display_type(self) -> str:
        if self.section == "Gods":
            return {
                "Primeval Gods": "primeval god",
                "Modern Gods": "modern god",
                "Fallen Gods": "fallen god",
            }.get(self.subsection, self.page_type)
        return self.page_type


@dataclass(slots=True)
class Campaign:
    title: str
    slug: str
    summary: str
    system: str
    current_session: int
    source_wiki_root: str
    player_content_dir: str
    assets_dir: str
    systems_library_slug: str = ""
    systems_source_defaults: list[dict[str, object]] = field(default_factory=list)
    pages: dict[str, Page] = field(default_factory=dict)
    alias_index: dict[str, str] = field(default_factory=dict)

    def is_page_visible(self, page: Page) -> bool:
        return page.published and page.reveal_after_session <= self.current_session

    def get_visible_page(self, page_slug: str) -> Page | None:
        page = self.pages.get(page_slug)
        if page is None or not self.is_page_visible(page):
            return None
        return page

    def visible_pages(self) -> list[Page]:
        pages = [page for page in self.pages.values() if self.is_page_visible(page)]
        return sorted(pages, key=page_sort_key)

    def visible_backlinks_for(self, page: Page) -> list[Page]:
        backlinks = [self.pages[backlink_slug] for backlink_slug in page.backlinks if backlink_slug in self.pages]
        visible_backlinks = [backlink for backlink in backlinks if self.is_page_visible(backlink)]
        return sorted(visible_backlinks, key=page_sort_key)
