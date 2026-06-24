import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";

import type {
  WikiPageDetail,
  WikiPageResponse,
  WikiSubsectionGroup,
} from "../api/types";
import { getApiErrorMessage } from "../apiErrors";
import { useApiClient } from "../apiClientContext";
import {
  normalizeFrontendMode,
  preferredCampaignHtml,
  preferredCampaignLink,
  routeFrontendMode,
} from "../campaignLinks";
import { ApiErrorNotice } from "../components/feedback";
import {
  splitPinnedPages,
  WikiHomeSectionGrid,
  WikiPageGrid,
  WikiSectionBrowse,
  WikiSectionNav,
} from "../components/WikiChrome";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";

export function WikiHomePage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug/",
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
          {hasBacklinks ? (
            <nav className="wiki-backlink-strip" aria-label="Pages linking here">
              <span className="wiki-backlink-strip__label">Linked from</span>
              <ul className="wiki-backlink-list">
                {data?.backlinks.map((backlink) => (
                  <li key={backlink.page_ref}>
                    <a href={preferredCampaignLink(backlink.href, campaignSlug, wikiFrontendMode)}>{backlink.title}</a>
                  </li>
                ))}
              </ul>
            </nav>
          ) : null}
          <section className="page-layout wiki-article-page wiki-article-page--single">
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
          </section>
        </>
      ) : null}
    </>
  );
}
