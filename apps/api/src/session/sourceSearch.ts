import type { CampaignViewModel } from "../campaigns/view.js";
import {
  searchSessionArticleSystemsSources,
  type FixtureSystemsRole,
  type SessionArticleSystemsSourceResult,
} from "../systems/sources.js";
import { campaignWikiRepository } from "../wiki/repository.js";
import type { WikiPageRecord } from "../wiki/types.js";

export interface SessionArticlePageSourceResult {
  source_ref: string;
  source_kind: "page";
  title: string;
  subtitle: string;
  kind_label: "Wiki";
  select_label: string;
}

export type SessionArticleSourceResult = SessionArticlePageSourceResult | SessionArticleSystemsSourceResult;

export interface SessionArticleSourceSearchPayload {
  results: SessionArticleSourceResult[];
  message: string;
}

export interface SessionArticleSourceSearchResultPayload {
  status: "ok" | "forbidden";
  message?: string;
  payload?: SessionArticleSourceSearchPayload;
}

function canManageSession(role: FixtureSystemsRole): boolean {
  return role === "dm" || role === "admin";
}

function pageContextLabel(page: WikiPageRecord): string {
  return [page.section, page.subsection].map((part) => part.trim()).filter(Boolean).join(" / ");
}

function serializePageSourceResult(page: WikiPageRecord): SessionArticlePageSourceResult {
  const contextLabel = pageContextLabel(page);
  return {
    source_ref: page.page_ref,
    source_kind: "page",
    title: page.title,
    subtitle: contextLabel,
    kind_label: "Wiki",
    select_label: `${page.title} - Wiki - ${contextLabel}`,
  };
}

function resultMessage(count: number): string {
  if (count === 30) {
    return "Showing the first 30 matching articles.";
  }
  if (count === 0) {
    return "No published wiki or Systems articles matched that search.";
  }
  return `Found ${count} matching article${count === 1 ? "" : "s"}.`;
}

export async function buildSessionArticleSourceSearchPayload(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  role: FixtureSystemsRole,
  query: string,
  limit = 30,
): Promise<SessionArticleSourceSearchResultPayload> {
  if (!canManageSession(role)) {
    return {
      status: "forbidden",
      message: "You do not have permission to manage this session.",
    };
  }

  const cleanedQuery = String(query || "").trim();
  if (cleanedQuery.length < 2) {
    return {
      status: "ok",
      payload: {
        results: [],
        message: "Type at least 2 letters to search published wiki pages and Systems entries.",
      },
    };
  }

  const safeLimit = Math.max(1, Math.trunc(limit));
  const results: SessionArticleSourceResult[] = [];
  const pageResults = await campaignWikiRepository.searchPages(campaign.slug, cleanedQuery);
  for (const page of pageResults) {
    results.push(serializePageSourceResult(page));
    if (results.length >= safeLimit) {
      return {
        status: "ok",
        payload: {
          results,
          message: resultMessage(results.length),
        },
      };
    }
  }

  const systemsResults = searchSessionArticleSystemsSources(
    dbPath,
    campaign,
    campaignConfig,
    role,
    cleanedQuery,
    safeLimit * 2,
  );
  for (const result of systemsResults) {
    results.push(result);
    if (results.length >= safeLimit) {
      break;
    }
  }

  return {
    status: "ok",
    payload: {
      results,
      message: resultMessage(results.length),
    },
  };
}
