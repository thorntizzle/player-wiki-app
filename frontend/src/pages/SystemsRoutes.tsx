import React, { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";

import type {
  SystemsEntryResponse,
  SystemsIndexResponse,
  SystemsSourceCategoryResponse,
  SystemsSourceResponse,
} from "../api/types";
import { getApiErrorMessage } from "../apiErrors";
import { useApiClient } from "../apiClientContext";
import { ApiErrorNotice } from "../components/feedback";
import {
  systemsIndexHref,
  systemsSourceCategoryHref,
  systemsSourceHref,
  SystemsEntryList,
  SystemsManageLink,
  SystemsRulesReferenceList,
  SystemsSourceNav,
} from "../components/SystemsChrome";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";

export function SystemsIndexPage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug/systems/",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const params = new URLSearchParams(window.location.search);
  const query = params.get("q") || "";
  const referenceQuery = params.get("reference_q") || "";

  const systemsQuery = useQuery({
    queryKey: ["systems-index", resolvedCampaignSlug, query, referenceQuery],
    queryFn: () => apiClient.getSystemsIndex(resolvedCampaignSlug, query, referenceQuery),
    enabled: Boolean(resolvedCampaignSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(systemsQuery.error)) {
      setAuthRequired(true);
    }
  }, [systemsQuery.error, setAuthRequired]);

  const data: SystemsIndexResponse | undefined = systemsQuery.data;
  const error = getApiErrorMessage(systemsQuery.error);
  const action = systemsIndexHref(resolvedCampaignSlug);

  return (
    <>
      <section className="hero compact systems-hero">
        <div>
          <p className="eyebrow">Systems wiki</p>
          <h1>Systems</h1>
          <p className="lede">Browse campaign-approved system sources and reference entries.</p>
        </div>
        {data ? (
          data.permissions.can_manage_systems ? (
            <div className="hero-actions systems-hero-actions">
              <SystemsManageLink campaignSlug={resolvedCampaignSlug} canManage />
            </div>
          ) : null
        ) : null}
      </section>
      <ApiErrorNotice isLoading={systemsQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {data ? (
        <div className="systems-browse-grid page-layout">
          <section className="systems-search-band article card">
            <h2>Systems Search</h2>
            <form method="get" action={action} className="stack-form">
              {referenceQuery ? <input type="hidden" name="reference_q" value={referenceQuery} /> : null}
              <label className="field" htmlFor="systems-entry-search">
                <span>Search systems entries</span>
                <input id="systems-entry-search" type="search" name="q" defaultValue={data.query} placeholder="title, type, or source" />
              </label>
              <button type="submit">Search</button>
            </form>
            <p className="meta">Search matches titles and entry types.</p>
            {data.query ? (
              <>
                <h3>Search Results</h3>
                <SystemsEntryList
                  campaignSlug={resolvedCampaignSlug}
                  entries={data.search_results}
                  emptyText="No imported systems entries matched that search yet."
                />
              </>
            ) : null}

            <section>
              <h2>Rules Reference Search</h2>
              {data.has_rules_reference_search ? (
                <>
                  <form method="get" action={action} className="stack-form">
                    {query ? <input type="hidden" name="q" value={query} /> : null}
                    <label className="field" htmlFor="systems-rules-search">
                      <span>Search rules references</span>
                      <input
                        id="systems-rules-search"
                        type="search"
                        name="reference_q"
                        defaultValue={data.reference_query}
                        placeholder="chapter heading, rule alias, or facet"
                      />
                    </label>
                    <button type="submit">Search</button>
                  </form>
                  <p className="meta">
                    Searches landing-page book-backed chapter pages and RULES entries by curated metadata, not full body text.
                  </p>
                </>
              ) : (
                <p className="meta">No landing-page rules-reference sources are currently available to this viewer.</p>
              )}
              {data.source_scoped_rules_reference_sources.length ? (
                <p className="meta">
                  Source-scoped rules searches stay on their source pages:{" "}
                  {data.source_scoped_rules_reference_sources.map((source, index) => (
                    <React.Fragment key={source.source_id}>
                      {index > 0 ? ", " : ""}
                      <a href={systemsSourceHref(resolvedCampaignSlug, source.source_id)}>{source.title}</a>
                    </React.Fragment>
                  ))}
                  .
                </p>
              ) : null}
              {data.reference_query ? (
                <>
                  <h3>Rules Reference Results</h3>
                  <SystemsRulesReferenceList
                    campaignSlug={resolvedCampaignSlug}
                    results={data.rules_reference_results}
                    emptyText="No rules references matched that metadata search yet."
                  />
                </>
              ) : null}
            </section>
          </section>
          <aside className="sidebar systems-browse-sidebar">
            <section className="card sidebar-card systems-source-card">
              <h2>Available Sources</h2>
              {data.sources.length ? (
                <ul className="plain-list systems-entry-list">
                  {data.sources.map((source) => (
                    <li className="systems-list-row" key={source.source_id}>
                      <a href={systemsSourceHref(resolvedCampaignSlug, source.source_id)}>{source.title}</a>
                      <p className="meta">Source policy: {source.license_class_label}</p>
                      <p className="meta">{source.entry_count} available entr{source.entry_count === 1 ? "y" : "ies"}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="meta">No systems sources are currently available to this viewer.</p>
              )}
            </section>
          </aside>
        </div>
      ) : null}
    </>
  );
}

export function SystemsSourcePage() {
  const { campaignSlug, sourceId } = useParams({
    from: "/campaigns/$campaignSlug/systems/sources/$sourceId/",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const resolvedSourceId = sourceId ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const referenceQuery = new URLSearchParams(window.location.search).get("reference_q") || "";

  const sourceQuery = useQuery({
    queryKey: ["systems-source", resolvedCampaignSlug, resolvedSourceId, referenceQuery],
    queryFn: () => apiClient.getSystemsSource(resolvedCampaignSlug, resolvedSourceId, referenceQuery),
    enabled: Boolean(resolvedCampaignSlug && resolvedSourceId),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(sourceQuery.error)) {
      setAuthRequired(true);
    }
  }, [sourceQuery.error, setAuthRequired]);

  const data: SystemsSourceResponse | undefined = sourceQuery.data;
  const error = getApiErrorMessage(sourceQuery.error);
  const action = systemsSourceHref(resolvedCampaignSlug, resolvedSourceId);

  return (
    <>
      <section className="hero compact systems-hero">
        <div>
          <p className="eyebrow">Systems source</p>
          <h1>{data?.source.title ?? resolvedSourceId}</h1>
          {data ? (
            <p className="lede">
              {data.source.license_class_label} | {data.browsable_entry_count} visible entr{data.browsable_entry_count === 1 ? "y" : "ies"}
            </p>
          ) : null}
        </div>
        {data ? (
          data.permissions.can_manage_systems ? (
            <div className="hero-actions systems-hero-actions">
              <SystemsManageLink campaignSlug={resolvedCampaignSlug} canManage />
            </div>
          ) : null
        ) : null}
      </section>
      <ApiErrorNotice isLoading={sourceQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {data ? (
        <div className="systems-browse-grid page-layout">
          <section className="systems-source-band article card">
            <h2>Browse This Source</h2>
            {data.rules_reference_scope_note ? <p className="meta">{data.rules_reference_scope_note}</p> : null}
            {data.book_visibility_policy_note ? <p className="meta">{data.book_visibility_policy_note}</p> : null}
            {data.book_entries.length ? (
              <section>
                <h3>Book Chapters</h3>
                <SystemsEntryList
                  campaignSlug={resolvedCampaignSlug}
                  entries={data.book_entries}
                  emptyText="No book chapters are visible in this source."
                />
              </section>
            ) : null}
            {data.has_rules_reference_search ? (
              <section>
                <h3>Rules Reference Search</h3>
                <form method="get" action={action} className="stack-form">
                  <label className="field" htmlFor="systems-source-rules-search">
                    <span>Search this source's rules references</span>
                    <input
                      id="systems-source-rules-search"
                      type="search"
                      name="reference_q"
                      defaultValue={data.reference_query}
                      placeholder="chapter heading, rule alias, or facet"
                    />
                  </label>
                  <button type="submit">Search</button>
                </form>
                {data.rules_reference_search_meta ? <p className="meta">{data.rules_reference_search_meta}</p> : null}
                {data.reference_query ? (
                  <SystemsRulesReferenceList
                    campaignSlug={resolvedCampaignSlug}
                    results={data.rules_reference_results}
                    emptyText="No rules references matched that metadata search in this source."
                  />
                ) : null}
              </section>
            ) : null}
            {data.hidden_entry_types.length ? (
              <p className="meta">
                Some entry types are folded into their parent pages and remain searchable without appearing as separate source categories.
              </p>
            ) : null}
            <p className="meta">
              This source currently has {data.browsable_entry_count} browsable entr{data.browsable_entry_count === 1 ? "y" : "ies"} across {data.entry_groups.length} categor{data.entry_groups.length === 1 ? "y" : "ies"}.
            </p>
            <SystemsSourceNav
              campaignSlug={resolvedCampaignSlug}
              sourceId={data.source.source_id}
              sourceTitle={data.source.title}
              groups={data.entry_groups}
              emptyText="No systems entries are currently available in this source for your access level."
            />
          </section>
          <aside className="sidebar systems-browse-sidebar">
            <section className="card sidebar-card">
              <h2>Browse Summary</h2>
              <p className="meta">Source policy: {data.source.license_class_label}</p>
              <p className="meta">Visible entries: {data.browsable_entry_count}</p>
              <p className="meta">Categories: {data.entry_groups.length}</p>
            </section>
          </aside>
        </div>
      ) : null}
    </>
  );
}

export function SystemsSourceCategoryPage() {
  const { campaignSlug, sourceId, entryType } = useParams({
    from: "/campaigns/$campaignSlug/systems/sources/$sourceId/types/$entryType",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const resolvedSourceId = sourceId ?? "";
  const resolvedEntryType = entryType ?? "";
  const { apiClient, setAuthRequired } = useApiClient();
  const query = new URLSearchParams(window.location.search).get("q") || "";

  const categoryQuery = useQuery({
    queryKey: ["systems-source-category", resolvedCampaignSlug, resolvedSourceId, resolvedEntryType, query],
    queryFn: () => apiClient.getSystemsSourceCategory(resolvedCampaignSlug, resolvedSourceId, resolvedEntryType, query),
    enabled: Boolean(resolvedCampaignSlug && resolvedSourceId && resolvedEntryType),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(categoryQuery.error)) {
      setAuthRequired(true);
    }
  }, [categoryQuery.error, setAuthRequired]);

  const data: SystemsSourceCategoryResponse | undefined = categoryQuery.data;
  const error = getApiErrorMessage(categoryQuery.error);
  const action = systemsSourceCategoryHref(resolvedCampaignSlug, resolvedSourceId, resolvedEntryType);

  return (
    <>
      <section className="hero compact systems-hero">
        <div>
          <p className="eyebrow">Systems source category</p>
          <h1>{data ? `${data.source.title}: ${data.entry_type_label}` : resolvedEntryType}</h1>
          {data ? <p className="lede">{data.source.license_class_label} | {data.entry_count} entr{data.entry_count === 1 ? "y" : "ies"}</p> : null}
        </div>
        {data ? (
          data.permissions.can_manage_systems ? (
            <div className="hero-actions systems-hero-actions">
              <SystemsManageLink campaignSlug={resolvedCampaignSlug} canManage />
            </div>
          ) : null
        ) : null}
      </section>
      <ApiErrorNotice isLoading={categoryQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {data ? (
        <div className="systems-browse-grid page-layout">
          <section className="systems-category-band article card">
            <h2>Browse {data.entry_type_label}</h2>
            <SystemsSourceNav
              campaignSlug={resolvedCampaignSlug}
              sourceId={data.source.source_id}
              sourceTitle={data.source.title}
              groups={data.entry_groups}
              activeEntryType={data.entry_type}
            />
            <form method="get" action={action} className="stack-form">
              <label className="field" htmlFor="systems-category-search">
                <span>Search this category</span>
                <input id="systems-category-search" type="search" name="q" defaultValue={data.query} placeholder="Search by title" />
              </label>
              <button type="submit">Search</button>
            </form>
            <p className="meta">Search matches titles and entry types only.</p>
            <p className="meta">
              {data.query
                ? `Showing ${data.filtered_entry_count} matching entries out of ${data.entry_count}.`
                : `Showing all ${data.entry_count} ${data.entry_type_label.toLowerCase()}.`}
            </p>
            <SystemsEntryList
              campaignSlug={resolvedCampaignSlug}
              entries={data.entries}
              emptyText={`No ${data.entry_type_label.toLowerCase()} matched that title/type search.`}
              showMeta={false}
            />
          </section>
          <aside className="sidebar systems-browse-sidebar">
            <section className="card sidebar-card">
              <h2>Category Summary</h2>
              <p className="meta">Source: {data.source.title}</p>
              <p className="meta">Category: {data.entry_type_label}</p>
              <p className="meta">Available entries: {data.entry_count}</p>
            </section>
          </aside>
        </div>
      ) : null}
    </>
  );
}

export function SystemsEntryPage() {
  const { campaignSlug, entrySlug } = useParams({
    from: "/campaigns/$campaignSlug/systems/entries/$entrySlug",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const resolvedEntrySlug = entrySlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();

  const entryQuery = useQuery({
    queryKey: ["systems-entry", resolvedCampaignSlug, resolvedEntrySlug],
    queryFn: () => apiClient.getSystemsEntry(resolvedCampaignSlug, resolvedEntrySlug),
    enabled: Boolean(resolvedCampaignSlug && resolvedEntrySlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(entryQuery.error)) {
      setAuthRequired(true);
    }
  }, [entryQuery.error, setAuthRequired]);

  const data: SystemsEntryResponse | undefined = entryQuery.data;
  const entry = data?.entry;
  const error = getApiErrorMessage(entryQuery.error);
  const sourceState = entry?.source_state;

  return (
    <>
      {entry ? (
        <section className="hero compact systems-hero">
          <p className="eyebrow">Systems entry</p>
          <h1>{entry.title}</h1>
          <p className="lede">
            {entry.entry_type_label}
            {sourceState?.title ? ` | ${sourceState.title}` : ""}
            {sourceState?.license_class_label ? ` | ${sourceState.license_class_label}` : ""}
          </p>
        </section>
      ) : null}
      <ApiErrorNotice isLoading={entryQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />
      {entry ? (
        <div className="page-layout">
          <article className="article card systems-entry-band">
            {entry.rendered_html ? (
              <div className="article-body html-body" dangerouslySetInnerHTML={{ __html: entry.rendered_html }} />
            ) : (
              <>
                <p className="meta">This entry has been imported into the systems library, but it does not have rendered content yet.</p>
              </>
            )}
          </article>
          <aside className="sidebar systems-entry-sidebar">
            <section className="card sidebar-card systems-sidebar-card">
              <h2>Entry Reference</h2>
              <section className="sidebar-card-section">
                <h3>Metadata</h3>
                <p className="meta">Type: {entry.entry_type_label}</p>
                {sourceState?.title ? <p className="meta">Source: {sourceState.title}</p> : null}
                {entry.source_page ? <p className="meta">Source page: {entry.source_page}</p> : null}
              </section>
              <section className="sidebar-card-section">
                <h3>Navigation</h3>
                <ul className="plain-list systems-entry-navigation">
                  <li><a href={systemsIndexHref(resolvedCampaignSlug)}>Systems landing</a></li>
                  <li><a href={systemsSourceHref(resolvedCampaignSlug, entry.source_id)}>Source page</a></li>
                  <li><a href={systemsSourceCategoryHref(resolvedCampaignSlug, entry.source_id, entry.entry_type)}>Source category</a></li>
                </ul>
              </section>
            </section>
            {data?.permissions.can_manage_systems ? (
              <section className="card sidebar-card systems-sidebar-card" id="systems-entry-management">
                <h2>Entry Management</h2>
                <p className="meta">Entry key: {entry.entry_key}</p>
                <p className="meta">
                  Shared library entry. Campaign DMs normally use overrides; app admins can allow trusted campaign DMs to edit shared/core content directly.
                </p>
                <div className="badge-list">
                  {data.links.dm_content_systems_url ? (
                    <a className="ghost-button" href={data.links.dm_content_systems_url}>Manage campaign override</a>
                  ) : (
                    <SystemsManageLink campaignSlug={resolvedCampaignSlug} canManage />
                  )}
                </div>
              </section>
            ) : null}
          </aside>
        </div>
      ) : null}
    </>
  );
}
