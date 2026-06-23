import type { FrontendMode } from "./apiClientContext";

export function normalizeFrontendMode(value: string | null | undefined): FrontendMode {
  return value === "gen2" ? "gen2" : "flask";
}

export function routeFrontendMode(preferredMode: FrontendMode): FrontendMode {
  const browserPathname = window.location.pathname;
  return browserPathname === "/app-next" || browserPathname.startsWith("/app-next/") ? "gen2" : preferredMode;
}

export function campaignRouteHref(campaignSlug: string, suffix = "", frontendMode: FrontendMode = "flask"): string {
  const normalizedCampaignSlug = encodeURIComponent(campaignSlug);
  const base = frontendMode === "gen2" ? `/app-next/campaigns/${normalizedCampaignSlug}` : `/campaigns/${normalizedCampaignSlug}`;
  const normalizedSuffix = suffix.replace(/^\/+/, "");
  return normalizedSuffix ? `${base}/${normalizedSuffix}` : base;
}

export function appNextHrefToRouterPath(href: string): string {
  if (href === "/app-next") {
    return "/";
  }
  if (href.startsWith("/app-next/")) {
    return href.slice("/app-next".length);
  }
  return href || "/";
}

export function preferredCampaignLink(href: string, campaignSlug: string, frontendMode: FrontendMode): string {
  if (!href) {
    return href;
  }
  const normalizedCampaignSlug = encodeURIComponent(campaignSlug);
  const legacyPrefix = `/campaigns/${normalizedCampaignSlug}/`;
  const legacyBase = `/campaigns/${normalizedCampaignSlug}`;
  const gen2Prefix = `/app-next/campaigns/${normalizedCampaignSlug}/`;
  const gen2Base = `/app-next/campaigns/${normalizedCampaignSlug}`;
  const preferredBase = campaignRouteHref(campaignSlug, "", frontendMode);
  if (href === legacyBase || href === gen2Base) {
    return preferredBase;
  }
  if (href.startsWith(legacyPrefix)) {
    return `${preferredBase}/${href.slice(legacyPrefix.length)}`;
  }
  if (href.startsWith(gen2Prefix)) {
    return `${preferredBase}/${href.slice(gen2Prefix.length)}`;
  }
  return href;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function preferredCampaignHtml(html: string, campaignSlug: string, frontendMode: FrontendMode): string {
  if (!html) {
    return html;
  }
  const normalizedCampaignSlug = encodeURIComponent(campaignSlug);
  const preferredBase = campaignRouteHref(campaignSlug, "", frontendMode);
  const campaignPathPattern = new RegExp(
    `href=(["'])(?:/app-next)?/campaigns/${escapeRegExp(normalizedCampaignSlug)}/(pages|sections)/`,
    "g",
  );
  return html.replace(campaignPathPattern, `href=$1${preferredBase}/$2/`);
}
