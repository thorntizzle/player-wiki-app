import { searchSessionArticleSystemsSources, } from "../systems/sources.js";
import { campaignWikiRepository } from "../wiki/repository.js";
function canManageSession(role) {
    return role === "dm" || role === "admin";
}
function pageContextLabel(page) {
    return [page.section, page.subsection].map((part) => part.trim()).filter(Boolean).join(" / ");
}
function serializePageSourceResult(page) {
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
function resultMessage(count) {
    if (count === 30) {
        return "Showing the first 30 matching articles.";
    }
    if (count === 0) {
        return "No published wiki or Systems articles matched that search.";
    }
    return `Found ${count} matching article${count === 1 ? "" : "s"}.`;
}
export async function buildSessionArticleSourceSearchPayload(dbPath, campaign, campaignConfig, role, query, limit = 30) {
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
    const results = [];
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
    const systemsResults = searchSessionArticleSystemsSources(dbPath, campaign, campaignConfig, role, cleanedQuery, safeLimit * 2);
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
