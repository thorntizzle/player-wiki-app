import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";

import type { CampaignHelpResponse } from "../api/types";
import { getApiErrorMessage } from "../apiErrors";
import { useApiClient } from "../apiClientContext";
import { ApiErrorNotice } from "../components/feedback";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";

function HelpList({ items, emptyText }: { items: string[]; emptyText: string }) {
  if (!items.length) {
    if (!emptyText) {
      return null;
    }
    return <p className="meta">{emptyText}</p>;
  }
  return (
    <ul className="plain-list help-list">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

export function CampaignHelpPage() {
  const { campaignSlug } = useParams({
    from: "/campaigns/$campaignSlug/help",
  });
  const resolvedCampaignSlug = campaignSlug ?? "";
  const { apiClient, setAuthRequired } = useApiClient();

  const helpQuery = useQuery({
    queryKey: ["campaign-help", resolvedCampaignSlug],
    queryFn: () => apiClient.getCampaignHelp(resolvedCampaignSlug),
    enabled: Boolean(resolvedCampaignSlug),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(helpQuery.error)) {
      setAuthRequired(true);
    }
  }, [helpQuery.error, setAuthRequired]);

  const data: CampaignHelpResponse | undefined = helpQuery.data;
  const error = getApiErrorMessage(helpQuery.error);

  return (
    <>
      <section className="hero compact campaign-help-hero">
        <p className="eyebrow">Help</p>
        <h1>Help</h1>
        <p className="lede">
          Use this page for what each app surface is for, what the current access rules allow,
          and which first-pass limits still shape the workflow.
        </p>
        {data?.surfaces.length ? (
          <div className="hero-actions" aria-label="Help sections">
            {data.surfaces.map((surface) => (
              <a className="ghost-button" href={`#${surface.anchor}`} key={surface.anchor}>
                {surface.label}
              </a>
            ))}
          </div>
        ) : null}
      </section>

      <ApiErrorNotice isLoading={helpQuery.isLoading} message={error} onAuth={() => setAuthRequired(true)} />

      {data ? (
        <div className="page-layout campaign-help-layout">
          <section className="session-column campaign-help-main">
            <article className="card campaign-help-current">
              <div className="section-heading">
                <div>
                  <h2>Current access</h2>
                  <p className="meta">This page holds the broader workflow notes so the main UI can stay focused on actions.</p>
                </div>
              </div>
              <div className="detail-grid help-detail-grid">
                <article className="help-panel">
                  <h3>Viewer role</h3>
                  <p><strong>{data.viewer_role_label}</strong></p>
                  <p className="meta">{data.viewer_role_summary}</p>
                </article>
                <article className="help-panel">
                  <h3>Campaign system</h3>
                  <p><strong>{data.campaign_system_label}</strong></p>
                  <p className="meta">Some workflows below stay narrower when the campaign is not using DND-5E.</p>
                </article>
                <article className="help-panel">
                  <h3>Open now</h3>
                  {data.available_surface_labels.length ? (
                    <p>{data.available_surface_labels.join(", ")}</p>
                  ) : (
                    <p className="meta">No additional campaign surfaces are open to this viewer right now.</p>
                  )}
                </article>
              </div>
            </article>

            {data.surfaces.map((surface) => (
              <article className="card campaign-help-surface" id={surface.anchor} key={surface.anchor}>
                <div className="section-heading">
                  <div>
                    <h2>{surface.label}</h2>
                    <p className="meta">{surface.summary}</p>
                  </div>
                  <span className="meta-badge">{surface.status_label}</span>
                </div>

                {surface.links.length ? (
                  <div className="hero-actions campaign-help-surface-actions">
                    {surface.links.map((link, index) => (
                      <a
                        className={index === 0 ? "button-link" : "ghost-button"}
                        href={link.href}
                        key={`${surface.anchor}-${link.href}`}
                      >
                        {link.label}
                      </a>
                    ))}
                  </div>
                ) : null}

                <div className="detail-grid help-detail-grid">
                  <article className="help-panel">
                    <h3>Use it for</h3>
                    <HelpList items={surface.capabilities} emptyText="No capabilities are listed for this surface." />
                  </article>
                  <article className="help-panel">
                    <h3>Current limits</h3>
                    <HelpList items={surface.limits} emptyText="No limits are listed for this surface." />
                  </article>
                  <article className="help-panel">
                    <h3>Access</h3>
                    <p><strong>{surface.status_label}</strong></p>
                    <p className="meta">{surface.access_note}</p>
                  </article>
                </div>

                {surface.guidance_cards.length ? (
                  <div className="detail-grid help-detail-grid">
                    {surface.guidance_cards.map((card) => (
                      <article className="help-panel" key={`${surface.anchor}-${card.title}`}>
                        <h3>{card.title}</h3>
                        {card.body ? <p>{card.body}</p> : null}
                        <HelpList items={card.items} emptyText="" />
                        {card.meta ? <p className="meta">{card.meta}</p> : null}
                      </article>
                    ))}
                  </div>
                ) : null}
              </article>
            ))}
          </section>

          <aside className="session-sidebar campaign-help-sidebar">
            <article className="card sidebar-card session-sidebar-card">
              <div className="section-heading">
                <div>
                  <h2>Visibility by scope</h2>
                  <p className="meta">The effective visibility here is the current floor after campaign-level and scope-level rules combine.</p>
                </div>
              </div>
              <div className="reference-stack">
                {data.visibility_rows.map((row) => (
                  <article className="help-panel" key={row.label}>
                    <div className="section-heading">
                      <h3>{row.label}</h3>
                      <span className="meta-badge">{row.visibility_label}</span>
                    </div>
                    <p className="meta">
                      {row.viewer_can_open
                        ? "This viewer can currently open this scope."
                        : "This viewer cannot currently open this scope."}
                    </p>
                  </article>
                ))}
              </div>
            </article>

            <article className="card sidebar-card session-sidebar-card">
              <div className="section-heading">
                <div>
                  <h2>Cross-cutting limits</h2>
                  <p className="meta">These are the app-level constraints most likely to affect multiple surfaces.</p>
                </div>
              </div>
              <HelpList items={data.cross_cutting_limits} emptyText="No cross-cutting limits are visible for this viewer." />
            </article>

            <article className="card sidebar-card session-sidebar-card">
              <div className="section-heading">
                <div>
                  <h2>Account settings</h2>
                  <p className="meta">{data.account_note}</p>
                </div>
              </div>
              <div className="hero-actions">
                {data.is_authenticated ? (
                  <a className="button-link" href={data.links.account_url}>Open Account</a>
                ) : (
                  <a className="button-link" href={data.links.sign_in_url}>Sign in</a>
                )}
              </div>
            </article>
          </aside>
        </div>
      ) : null}
    </>
  );
}
