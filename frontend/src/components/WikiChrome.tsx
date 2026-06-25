import type { WikiHomeResponse, WikiPageSummary, WikiSectionNavItem } from "../api/types";
import type { FrontendMode } from "../apiClientContext";
import { useNavigate } from "@tanstack/react-router";
import { appNextHrefToRouterPath, preferredCampaignLink } from "../campaignLinks";
import type { AnchorHTMLAttributes, MouseEvent } from "react";

export type WikiLinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
  href: string;
  frontendMode: FrontendMode;
};

function appNextWikiRouterTarget(href: string): string | null {
  if (!href) {
    return null;
  }

  let url: URL;
  try {
    url = new URL(href, window.location.origin);
  } catch {
    return null;
  }

  if (url.origin !== window.location.origin || !url.pathname.startsWith("/app-next/campaigns/")) {
    return null;
  }
  if (!url.pathname.includes("/sections/") && !url.pathname.includes("/pages/")) {
    return null;
  }
  return `${appNextHrefToRouterPath(url.pathname)}${url.search}${url.hash}`;
}

function isPlainLocalClick(event: MouseEvent<HTMLElement>): boolean {
  return (
    !event.defaultPrevented
    && event.button === 0
    && !event.metaKey
    && !event.ctrlKey
    && !event.shiftKey
    && !event.altKey
  );
}

function useWikiAnchorNavigation(frontendMode: FrontendMode) {
  const navigate = useNavigate();
  return (event: MouseEvent<HTMLElement>, href: string | null | undefined, anchor?: HTMLAnchorElement | null) => {
    if (frontendMode !== "gen2" || !isPlainLocalClick(event) || !href) {
      return;
    }

    const target = anchor?.getAttribute("target");
    if ((target && target !== "_self") || anchor?.hasAttribute("download")) {
      return;
    }

    const routerTarget = appNextWikiRouterTarget(href);
    if (!routerTarget) {
      return;
    }

    event.preventDefault();
    void navigate({ to: routerTarget as never });
  };
}

export function WikiLink({ href, frontendMode, onClick, children, ...props }: WikiLinkProps) {
  const navigateAnchor = useWikiAnchorNavigation(frontendMode);
  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event);
    navigateAnchor(event, href, event.currentTarget);
  };

  return (
    <a {...props} href={href} onClick={handleClick}>
      {children}
    </a>
  );
}

export function useWikiBodyLinkNavigation(frontendMode: FrontendMode) {
  const navigateAnchor = useWikiAnchorNavigation(frontendMode);
  return (event: MouseEvent<HTMLElement>) => {
    const target = event.target instanceof Element ? event.target : null;
    const anchor = target?.closest("a[href]") as HTMLAnchorElement | null;
    if (!anchor || !event.currentTarget.contains(anchor)) {
      return;
    }
    navigateAnchor(event, anchor.getAttribute("href"), anchor);
  };
}

export function splitPinnedPages(pages: WikiPageSummary[]): { pinned: WikiPageSummary[]; regular: WikiPageSummary[] } {
  return {
    pinned: pages.filter((page) => page.is_pinned),
    regular: pages.filter((page) => !page.is_pinned),
  };
}

function WikiPageCard({
  page,
  featured = false,
  campaignSlug,
  frontendMode,
  headingLevel = "h3",
  kickerMode = "displayType",
}: {
  page: WikiPageSummary;
  featured?: boolean;
  campaignSlug: string;
  frontendMode: FrontendMode;
  headingLevel?: "h2" | "h3";
  kickerMode?: "displayType" | "sectionAndDisplayType";
}) {
  const cardKicker =
    kickerMode === "sectionAndDisplayType"
      ? `${page.section} \u00b7 ${page.display_type}`
      : page.display_type;
  const TitleElement = headingLevel;

  return (
    <article className={featured ? "card page-card page-card--featured" : "card page-card"}>
      <p className="card-kicker">{cardKicker}</p>
      <TitleElement>
        <WikiLink
          href={preferredCampaignLink(page.href, campaignSlug, frontendMode)}
          frontendMode={frontendMode}
        >
          {page.title}
        </WikiLink>
      </TitleElement>
      {page.summary ? <p className={featured ? "page-card__summary" : ""}>{page.summary}</p> : null}
    </article>
  );
}

export function WikiPageGrid({
  pages,
  featured = false,
  campaignSlug,
  frontendMode,
  headingLevel,
  kickerMode,
}: {
  pages: WikiPageSummary[];
  featured?: boolean;
  campaignSlug: string;
  frontendMode: FrontendMode;
  headingLevel?: "h2" | "h3";
  kickerMode?: "displayType" | "sectionAndDisplayType";
}) {
  if (!pages.length) {
    return null;
  }
  return (
    <div className={featured ? "page-stack page-stack--featured" : "grid"}>
      {pages.map((page) => (
        <WikiPageCard
          key={page.page_ref}
          page={page}
          featured={featured}
          campaignSlug={campaignSlug}
          frontendMode={frontendMode}
          headingLevel={headingLevel}
          kickerMode={kickerMode}
        />
      ))}
    </div>
  );
}

export function WikiSectionNav({
  sections,
  campaignSlug,
  frontendMode,
  activeSectionSlug = "",
}: {
  sections: WikiSectionNavItem[];
  campaignSlug: string;
  frontendMode: FrontendMode;
  activeSectionSlug?: string;
}) {
  if (!sections.length) {
    return null;
  }
  return (
    <nav className="wiki-section-nav" aria-label="Wiki sections">
      {sections.map((section) => {
        const isActive = section.section_slug === activeSectionSlug;
        return (
          <WikiLink
            key={section.section_slug}
            className={isActive ? "button-link" : "ghost-button"}
            href={preferredCampaignLink(section.href, campaignSlug, frontendMode)}
            aria-current={isActive ? "page" : undefined}
            title={`${section.page_count} page${section.page_count === 1 ? "" : "s"}`}
            frontendMode={frontendMode}
          >
            {section.section_name}
          </WikiLink>
        );
      })}
    </nav>
  );
}

type WikiSectionIconName =
  | "calendar"
  | "fileText"
  | "map"
  | "users"
  | "dna"
  | "flag"
  | "sparkles"
  | "compass"
  | "shield"
  | "package"
  | "wand"
  | "cog"
  | "library"
  | "grid";

const WIKI_SECTION_ICON_BY_SLUG: Record<string, WikiSectionIconName> = {
  sessions: "calendar",
  notes: "fileText",
  locations: "map",
  npcs: "users",
  races: "dna",
  factions: "flag",
  gods: "sparkles",
  discoveries: "compass",
  bestiary: "shield",
  items: "package",
  spells: "wand",
  mechanics: "cog",
  lore: "library",
};

function getWikiSectionIconName(section: WikiSectionNavItem): WikiSectionIconName {
  return WIKI_SECTION_ICON_BY_SLUG[section.section_slug] ?? "grid";
}

function WikiSectionIcon({ icon }: { icon: WikiSectionIconName }) {
  const sharedProps = {
    className: "wiki-home-section-card__icon-svg",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    focusable: false,
  };

  switch (icon) {
    case "calendar":
      return (
        <svg {...sharedProps}>
          <path d="M8 2v4" />
          <path d="M16 2v4" />
          <rect x="3" y="4" width="18" height="18" rx="2" />
          <path d="M3 10h18" />
          <path d="M8 14h.01" />
          <path d="M12 14h.01" />
          <path d="M16 14h.01" />
        </svg>
      );
    case "fileText":
      return (
        <svg {...sharedProps}>
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
          <path d="M14 2v6h6" />
          <path d="M8 13h8" />
          <path d="M8 17h6" />
        </svg>
      );
    case "map":
      return (
        <svg {...sharedProps}>
          <path d="M9 18 3 21V6l6-3 6 3 6-3v15l-6 3Z" />
          <path d="M9 3v15" />
          <path d="M15 6v15" />
        </svg>
      );
    case "users":
      return (
        <svg {...sharedProps}>
          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
          <path d="M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
      );
    case "dna":
      return (
        <svg {...sharedProps}>
          <path d="M4 14c4 0 4-4 8-4s4-4 8-4" />
          <path d="M4 20c4 0 4-4 8-4s4-4 8-4" />
          <path d="M4 4c4 0 4 4 8 4s4 4 8 4" />
          <path d="M7 8h10" />
          <path d="M7 16h10" />
        </svg>
      );
    case "flag":
      return (
        <svg {...sharedProps}>
          <path d="M4 22V4" />
          <path d="M4 4h12l-1 4 1 4H4" />
        </svg>
      );
    case "sparkles":
      return (
        <svg {...sharedProps}>
          <path d="M12 3 10.3 8.3 5 10l5.3 1.7L12 17l1.7-5.3L19 10l-5.3-1.7Z" />
          <path d="M5 3v4" />
          <path d="M3 5h4" />
          <path d="M19 17v4" />
          <path d="M17 19h4" />
        </svg>
      );
    case "compass":
      return (
        <svg {...sharedProps}>
          <circle cx="12" cy="12" r="10" />
          <path d="m16 8-2 6-6 2 2-6Z" />
        </svg>
      );
    case "shield":
      return (
        <svg {...sharedProps}>
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
          <path d="M12 8v6" />
          <path d="M9.5 10.5h5" />
        </svg>
      );
    case "package":
      return (
        <svg {...sharedProps}>
          <path d="m7.5 4.3 9 5.2" />
          <path d="M21 8.5v7a2 2 0 0 1-1 1.7l-7 4a2 2 0 0 1-2 0l-7-4a2 2 0 0 1-1-1.7v-7a2 2 0 0 1 1-1.7l7-4a2 2 0 0 1 2 0l7 4a2 2 0 0 1 1 1.7Z" />
          <path d="M3.3 7 12 12l8.7-5" />
          <path d="M12 22V12" />
        </svg>
      );
    case "wand":
      return (
        <svg {...sharedProps}>
          <path d="M15 4V2" />
          <path d="M15 16v-2" />
          <path d="M8 9h2" />
          <path d="M20 9h2" />
          <path d="m17.8 6.2 1.4-1.4" />
          <path d="m10.8 13.2-1.4 1.4" />
          <path d="m17.8 11.8 1.4 1.4" />
          <path d="M15 9h.01" />
          <path d="m3 21 9-9" />
        </svg>
      );
    case "cog":
      return (
        <svg {...sharedProps}>
          <circle cx="12" cy="12" r="3" />
          <path d="M12 2v3" />
          <path d="M12 19v3" />
          <path d="M4.9 4.9 7 7" />
          <path d="m17 17 2.1 2.1" />
          <path d="M2 12h3" />
          <path d="M19 12h3" />
          <path d="m4.9 19.1 2.1-2.1" />
          <path d="m17 7 2.1-2.1" />
        </svg>
      );
    case "library":
      return (
        <svg {...sharedProps}>
          <path d="M4 19.5V5a2 2 0 0 1 2-2h2v18H6a2 2 0 0 0-2 2" />
          <path d="M10 3h4v18h-4z" />
          <path d="M16 3h2a2 2 0 0 1 2 2v14.5a2 2 0 0 0-2-2h-2z" />
        </svg>
      );
    case "grid":
    default:
      return (
        <svg {...sharedProps}>
          <rect x="3" y="3" width="7" height="7" rx="1" />
          <rect x="14" y="3" width="7" height="7" rx="1" />
          <rect x="3" y="14" width="7" height="7" rx="1" />
          <rect x="14" y="14" width="7" height="7" rx="1" />
        </svg>
      );
  }
}

export function WikiLatestSessionCard({
  page,
  campaignSlug,
  frontendMode,
}: {
  page: WikiPageSummary | null;
  campaignSlug: string;
  frontendMode: FrontendMode;
}) {
  if (!page) {
    return null;
  }
  const sessionLabel = page.reveal_after_session > 0 ? `Session ${page.reveal_after_session}` : page.display_type;
  return (
    <section className="wiki-latest-session" aria-label="Latest session summary">
      <article className="card page-card page-card--featured wiki-latest-session-card">
        <p className="card-kicker">Latest session summary</p>
        <h2>
          <WikiLink
            href={preferredCampaignLink(page.href, campaignSlug, frontendMode)}
            frontendMode={frontendMode}
          >
            {page.title}
          </WikiLink>
        </h2>
        <p className="meta">{sessionLabel}</p>
        {page.summary ? <p className="page-card__summary">{page.summary}</p> : null}
      </article>
    </section>
  );
}

export function WikiHomeSectionGrid({
  sections,
  campaignSlug,
  frontendMode,
}: {
  sections: WikiSectionNavItem[];
  campaignSlug: string;
  frontendMode: FrontendMode;
}) {
  if (!sections.length) {
    return null;
  }
  return (
    <section className="wiki-home-section-grid" aria-label="Campaign wiki sections">
      {sections.map((section) => (
        <WikiLink
          className="card wiki-home-section-card"
          href={preferredCampaignLink(section.href, campaignSlug, frontendMode)}
          key={section.section_slug}
          title={`${section.page_count} page${section.page_count === 1 ? "" : "s"}`}
          frontendMode={frontendMode}
        >
          <span className="wiki-home-section-card__icon">
            <WikiSectionIcon icon={getWikiSectionIconName(section)} />
          </span>
          <span className="wiki-home-section-card__body">
            <span className="wiki-home-section-card__label">{section.section_name}</span>
          </span>
        </WikiLink>
      ))}
    </section>
  );
}

export function WikiSectionBrowse({
  data,
  campaignSlug,
  frontendMode,
}: {
  data: WikiHomeResponse;
  campaignSlug: string;
  frontendMode: FrontendMode;
}) {
  if (!data.grouped_sections.length) {
    return null;
  }
  return (
    <section className="section-list wiki-section-browse">
      <div className="section-block">
        <div className="section-heading">
          <h2>{data.query ? "Search Results" : "Browse By Section"}</h2>
          <p className="meta">
            {data.query
              ? `${data.result_count} match${data.result_count === 1 ? "" : "es"}`
              : `${data.grouped_sections.length} section${data.grouped_sections.length === 1 ? "" : "s"}`}
          </p>
        </div>
        <div className="grid">
          {data.grouped_sections.map((section) =>
            data.query ? (
              section.pages.map((page) => (
                <WikiPageCard
                  key={page.page_ref}
                  page={page}
                  campaignSlug={campaignSlug}
                  frontendMode={frontendMode}
                  headingLevel="h3"
                  kickerMode="sectionAndDisplayType"
                />
              ))
            ) : (
              <article className="card page-card section-card" key={section.section_slug}>
                <p className="card-kicker">Section</p>
                <h3>
                  <WikiLink
                    href={preferredCampaignLink(section.href, campaignSlug, frontendMode)}
                    frontendMode={frontendMode}
                  >
                    {section.section_name}
                  </WikiLink>
                </h3>
                <p>
                  {section.page_count} page{section.page_count === 1 ? "" : "s"} available in this section.
                </p>
              </article>
            ),
          )}
        </div>
      </div>
    </section>
  );
}
