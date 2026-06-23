import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";

import type {
  WikiHomeResponse,
  WikiPageDetail,
  WikiPageResponse,
  WikiPageSummary,
  WikiSectionNavItem,
  WikiSubsectionGroup,
} from "../api/types";
import { getApiErrorMessage } from "../apiErrors";
import { useApiClient, type FrontendMode } from "../apiClientContext";
import {
  normalizeFrontendMode,
  preferredCampaignHtml,
  preferredCampaignLink,
  routeFrontendMode,
} from "../campaignLinks";
import { ApiErrorNotice } from "../components/feedback";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";

function splitPinnedPages(pages: WikiPageSummary[]): { pinned: WikiPageSummary[]; regular: WikiPageSummary[] } {
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
        <a href={preferredCampaignLink(page.href, campaignSlug, frontendMode)}>{page.title}</a>
      </TitleElement>
      {page.summary ? <p className={featured ? "page-card__summary" : ""}>{page.summary}</p> : null}
    </article>
  );
}

function WikiPageGrid({
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

function WikiSectionNav({
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
          <a
            key={section.section_slug}
            className={isActive ? "button-link" : "ghost-button"}
            href={preferredCampaignLink(section.href, campaignSlug, frontendMode)}
            aria-current={isActive ? "page" : undefined}
            title={`${section.page_count} page${section.page_count === 1 ? "" : "s"}`}
          >
            {section.section_name}
          </a>
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

function WikiHomeSectionGrid({
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
        <a
          className="card wiki-home-section-card"
          href={preferredCampaignLink(section.href, campaignSlug, frontendMode)}
          key={section.section_slug}
          title={`${section.page_count} page${section.page_count === 1 ? "" : "s"}`}
        >
          <span className="wiki-home-section-card__icon">
            <WikiSectionIcon icon={getWikiSectionIconName(section)} />
          </span>
          <span className="wiki-home-section-card__body">
            <span className="wiki-home-section-card__label">{section.section_name}</span>
          </span>
        </a>
      ))}
    </section>
  );
}

function WikiSectionBrowse({
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
                  <a href={preferredCampaignLink(section.href, campaignSlug, frontendMode)}>{section.section_name}</a>
                </h3>
                <p>
                  {section.page_count} page{section.page_count === 1 ? "" : "s"} available in this section.
                </p>
                <p>
                  <a href={preferredCampaignLink(section.href, campaignSlug, frontendMode)}>Open {section.section_name}</a>
                </p>
              </article>
            ),
          )}
        </div>
      </div>
    </section>
  );
}

export function WikiHomePage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const { apiClient, setAuthRequired, preferredFrontendMode } = useApiClient();
  const query = new URLSearchParams(window.location.search).get("q") || "";

  const wikiQuery = useQuery({
    queryKey: ["wiki-home", resolvedCampaignSlug, query],
    queryFn: () => apiClient.getWikiHome(resolvedCampaignSlug, query),
    enabled: Boolean(resolvedCampaignSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(wikiQuery.error)) {
      setAuthRequired(true);
    }
  }, [wikiQuery.error, setAuthRequired]);

  const error = getApiErrorMessage(wikiQuery.error);
  const data = wikiQuery.data;
  const wikiFrontendMode = routeFrontendMode(normalizeFrontendMode(data?.frontend_mode ?? preferredFrontendMode));

  return (
    <>
      <section className="hero compact wiki-home">
        <p className="meta">Campaign</p>
        <h1>Campaign Home</h1>
        <p className="lede">{data?.campaign.summary}</p>
      </section>
      <ApiErrorNotice isLoading={wikiQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {data ? (
        <>
          {!data.can_view_wiki ? (
            <section className="card">
              <h2>Wiki visibility restricted</h2>
              <p>{data.message}</p>
            </section>
          ) : data.query ? (
            data.grouped_sections.length ? (
              <WikiSectionBrowse data={data} campaignSlug={resolvedCampaignSlug} frontendMode={wikiFrontendMode} />
            ) : (
              <section className="card">
                <h2>No matching pages</h2>
                <p>Try a broader search term or remove the query.</p>
              </section>
            )
          ) : data.section_navigation.length ? (
            <WikiHomeSectionGrid
              sections={data.section_navigation}
              campaignSlug={resolvedCampaignSlug}
              frontendMode={wikiFrontendMode}
            />
          ) : (
            <section className="card">
              <h2>No visible pages yet</h2>
              <p>This campaign does not currently have any published pages available to players.</p>
            </section>
          )}
        </>
      ) : null}
    </>
  );
}

export function WikiSectionPage() {
  const { campaignSlug, sectionSlug } = useParams({
    from: "/campaigns/$campaignSlug/sections/$sectionSlug",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const resolvedSectionSlug = sectionSlug ?? "";
  const { apiClient, setAuthRequired, preferredFrontendMode } = useApiClient();
  const [collapsedSubsections, setCollapsedSubsections] = useState<Set<string>>(() => new Set());

  const sectionQuery = useQuery({
    queryKey: ["wiki-section", resolvedCampaignSlug, resolvedSectionSlug],
    queryFn: () => apiClient.getWikiSection(resolvedCampaignSlug, resolvedSectionSlug),
    enabled: Boolean(resolvedCampaignSlug && resolvedSectionSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(sectionQuery.error)) {
      setAuthRequired(true);
    }
  }, [sectionQuery.error, setAuthRequired]);

  useEffect(() => {
    setCollapsedSubsections(new Set());
  }, [resolvedCampaignSlug, resolvedSectionSlug]);

  const data = sectionQuery.data;
  const error = getApiErrorMessage(sectionQuery.error);
  const wikiFrontendMode = routeFrontendMode(normalizeFrontendMode(data?.frontend_mode ?? preferredFrontendMode));
  const topLevel = splitPinnedPages(data?.top_level_pages ?? []);
  const allPages = splitPinnedPages(data?.pages ?? []);

  const setAllSubsectionsOpen = (open: boolean) => {
    if (!data) {
      return;
    }
    setCollapsedSubsections(open ? new Set() : new Set(data.subsection_groups.map((group) => group.subsection_name)));
  };

  const setSubsectionOpen = (group: WikiSubsectionGroup, open: boolean) => {
    const next = new Set(collapsedSubsections);
    if (open) {
      next.delete(group.subsection_name);
    } else {
      next.add(group.subsection_name);
    }
    setCollapsedSubsections(next);
  };

  return (
    <>
      <section className="hero compact wiki-section-page">
        <p className="meta">Section</p>
        <h1>{data?.section_name ?? resolvedSectionSlug}</h1>
        <p className="lede">Published player-facing pages in this section.</p>
      </section>
      <ApiErrorNotice isLoading={sectionQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {data ? (
        <>
          <WikiSectionNav
            sections={data.section_navigation}
            campaignSlug={resolvedCampaignSlug}
            frontendMode={wikiFrontendMode}
            activeSectionSlug={data.section_slug}
          />
          {data.show_subsections ? (
            <>
              <div className="section-list__controls">
                <button className="ghost-button section-list__control" type="button" onClick={() => setAllSubsectionsOpen(false)}>
                  Collapse all
                </button>
                <button className="ghost-button section-list__control" type="button" onClick={() => setAllSubsectionsOpen(true)}>
                  Expand all
                </button>
              </div>
              <WikiPageGrid
                pages={topLevel.pinned}
                featured
                campaignSlug={resolvedCampaignSlug}
                frontendMode={wikiFrontendMode}
                headingLevel="h2"
                kickerMode="displayType"
              />
              <WikiPageGrid
                pages={topLevel.regular}
                campaignSlug={resolvedCampaignSlug}
                frontendMode={wikiFrontendMode}
                headingLevel="h2"
                kickerMode="displayType"
              />
              <section className="section-list">
                {data.subsection_groups.map((group) => {
                  const split = splitPinnedPages(group.pages);
                  const isOpen = !collapsedSubsections.has(group.subsection_name);
                  return (
                    <details
                      className="section-block section-block--collapsible"
                      key={group.subsection_name}
                      open={isOpen}
                      onToggle={(event) => setSubsectionOpen(group, event.currentTarget.open)}
                    >
                      <summary className="section-toggle-summary">
                        <span className="section-toggle-summary__content">
                          <span className="section-title">{group.subsection_name}</span>
                          <span className="meta">
                            {group.page_count} page{group.page_count === 1 ? "" : "s"}
                          </span>
                        </span>
                        <span className="section-toggle-chevron" aria-hidden="true"></span>
                      </summary>
                      <div className="section-block__body">
                        <WikiPageGrid
                          pages={split.pinned}
                          featured
                          campaignSlug={resolvedCampaignSlug}
                          frontendMode={wikiFrontendMode}
                          headingLevel="h3"
                          kickerMode="displayType"
                        />
                        <WikiPageGrid
                          pages={split.regular}
                          campaignSlug={resolvedCampaignSlug}
                          frontendMode={wikiFrontendMode}
                          headingLevel="h3"
                          kickerMode="displayType"
                        />
                      </div>
                    </details>
                  );
                })}
              </section>
            </>
          ) : (
          <>
            <WikiPageGrid
              pages={allPages.pinned}
              featured
              campaignSlug={resolvedCampaignSlug}
              frontendMode={wikiFrontendMode}
              headingLevel="h2"
              kickerMode="displayType"
            />
            <WikiPageGrid
              pages={allPages.regular}
              campaignSlug={resolvedCampaignSlug}
              frontendMode={wikiFrontendMode}
              headingLevel="h2"
              kickerMode="displayType"
            />
          </>
          )}
        </>
      ) : null}
    </>
  );
}

export function WikiArticlePage() {
  const params = useParams({
    from: "/campaigns/$campaignSlug/pages/$",
  });
  const campaignSlug = params.campaignSlug ?? "";
  const pageSlug = params._splat ?? "";
  const { apiClient, setAuthRequired, preferredFrontendMode } = useApiClient();

  const pageQuery = useQuery({
    queryKey: ["wiki-page", campaignSlug, pageSlug],
    queryFn: () => apiClient.getWikiPage(campaignSlug, pageSlug),
    enabled: Boolean(campaignSlug && pageSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(pageQuery.error)) {
      setAuthRequired(true);
    }
  }, [pageQuery.error, setAuthRequired]);

  const data: WikiPageResponse | undefined = pageQuery.data;
  const page: WikiPageDetail | undefined = data?.page;
  const error = getApiErrorMessage(pageQuery.error);
  const wikiFrontendMode = routeFrontendMode(normalizeFrontendMode(data?.frontend_mode ?? preferredFrontendMode));
  const showSummary = page?.summary && !["item", "spell", "mechanic"].includes(page.page_type);
  const hasBacklinks = Boolean(data?.backlinks.length);

  return (
    <>
      <ApiErrorNotice isLoading={pageQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {page ? (
        <>
          <WikiSectionNav
            sections={data?.section_navigation ?? []}
            campaignSlug={campaignSlug}
            frontendMode={wikiFrontendMode}
            activeSectionSlug={page.section_slug}
          />
          <section className={hasBacklinks ? "page-layout wiki-article-page" : "page-layout wiki-article-page wiki-article-page--single"}>
            <article className="article card">
              <h1>{page.title}</h1>
              {showSummary ? <p className="lede">{page.summary}</p> : null}
              {page.image ? (
                <figure className="article-figure">
                  <img className="article-image" src={page.image.url} alt={page.image.alt_text || page.title} />
                  {page.image.caption ? <figcaption className="meta article-image__caption">{page.image.caption}</figcaption> : null}
                </figure>
              ) : null}
              <div
                className="article-body html-body"
                dangerouslySetInnerHTML={{
                  __html: preferredCampaignHtml(page.body_html, campaignSlug, wikiFrontendMode),
                }}
              />
            </article>
            {hasBacklinks ? (
              <aside className="sidebar">
                <section className="card sidebar-card">
                  <h2>Linked From</h2>
                  <ul className="plain-list">
                    {data?.backlinks.map((backlink) => (
                      <li key={backlink.page_ref}>
                        <a href={preferredCampaignLink(backlink.href, campaignSlug, wikiFrontendMode)}>{backlink.title}</a>
                      </li>
                    ))}
                  </ul>
                </section>
              </aside>
            ) : null}
          </section>
        </>
      ) : null}
    </>
  );
}
