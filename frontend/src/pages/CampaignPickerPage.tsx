import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";

import type { CampaignEntry } from "../api/types";
import { getApiErrorMessage } from "../apiErrors";
import { useApiClient } from "../apiClientContext";
import { campaignRouteHref, routeFrontendMode } from "../campaignLinks";
import { ApiErrorNotice } from "../components/feedback";
import { isAuthRequiredFromError as isAuthError } from "../sessionRouteState";

function campaignRoleLabel(value: string): string {
  return value
    .replace(/_/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((segment) => `${segment[0].toUpperCase()}${segment.slice(1)}`)
    .join(" ");
}

export function CampaignListPage() {
  const { apiClient, setAuthRequired, preferredFrontendMode, user } = useApiClient();

  const appQuery = useQuery({
    queryKey: ["app"],
    queryFn: () => apiClient.getAppState(),
    retry: false,
  });

  const campaignsQuery = useQuery({
    queryKey: ["campaigns"],
    queryFn: () => apiClient.getCampaigns(),
    retry: false,
  });

  useEffect(() => {
    if (isAuthError(appQuery.error) || isAuthError(campaignsQuery.error)) {
      setAuthRequired(true);
    }
  }, [appQuery.error, campaignsQuery.error, setAuthRequired]);

  const appError = getApiErrorMessage(appQuery.error);
  const campaignError = getApiErrorMessage(campaignsQuery.error);
  const campaigns: CampaignEntry[] = campaignsQuery.data?.campaigns ?? [];
  const campaignPickerHeroEyebrow = user
    ? "Campaign access"
    : "Campaign wiki";
  const campaignPickerHeadline = user
    ? "Select a campaign."
    : "Browse available campaigns.";
  const campaignPickerLede = user
    ? "Your account can see the campaigns listed here based on app-wide admin access, campaign membership, or public visibility."
    : "Public campaign wiki pages are available without signing in. Use an account only when you need admin or character access.";
  const emptyHeading = user ? "No campaign access assigned" : "No public campaigns available";
  const emptyLede = user
    ? "Your account is active, but it is not currently assigned to any campaigns."
    : "There are currently no public campaign wiki pages to browse.";
  const pickerRouteMode = routeFrontendMode(preferredFrontendMode);
  const signInHref = `/sign-in?next=${encodeURIComponent(`${window.location.pathname}${window.location.search}`)}`;

  return (
    <>
      <section className="hero compact campaign-picker-hero">
        <p className="eyebrow">{campaignPickerHeroEyebrow}</p>
        <h1>{campaignPickerHeadline}</h1>
        <p className="lede">
          {campaignPickerLede}
        </p>
      </section>
      <ApiErrorNotice
        isLoading={appQuery.isLoading || campaignsQuery.isLoading}
        message={appError ?? campaignError}
        onAuth={() => setAuthRequired(true)}
      />
      {campaigns.length ? (
        <section className="grid campaign-picker-grid">
          {campaigns.map((entry) => (
            <article className="card campaign-card" key={entry.campaign.slug}>
              <p className="card-kicker">{campaignRoleLabel(entry.role)}</p>
              <h2>{entry.campaign.title}</h2>
              <p>{entry.campaign.summary}</p>
              {entry.campaign.system ? <p className="meta">System: {entry.campaign.system}</p> : null}
              <p className="meta">Visible through session {entry.campaign.current_session}</p>
              <a className="button-link" href={campaignRouteHref(entry.campaign.slug, "", pickerRouteMode)}>
                Open campaign
              </a>
            </article>
          ))}
        </section>
      ) : null}
      {!appQuery.isLoading && !campaignsQuery.isLoading && !campaigns.length && !campaignError ? (
        <section className="card auth-card campaign-picker-empty">
          <h2>{emptyHeading}</h2>
          <p>{emptyLede}</p>
          {!user ? (
            <div className="hero-actions">
              <a className="ghost-button" href={signInHref}>
                Sign in
              </a>
            </div>
          ) : null}
        </section>
      ) : null}
    </>
  );
}
