import { promises as fs } from "node:fs";
import path from "node:path";
import { parse } from "yaml";
import { isCompleteCampaign, normalizeCampaignPayload } from "./view.js";
export async function listCampaignSlugs(campaignsDir) {
    let entries;
    try {
        entries = await fs.readdir(campaignsDir, { withFileTypes: true });
    }
    catch {
        return [];
    }
    return entries
        .filter((entry) => entry.isDirectory())
        .map((entry) => entry.name)
        .sort((left, right) => left.localeCompare(right));
}
export async function getCampaignBySlug(config, campaignSlug) {
    const targetSlug = campaignSlug.trim();
    if (!isSafeCampaignSlug(targetSlug)) {
        return null;
    }
    const campaignPath = path.resolve(config.campaignsDir, targetSlug, "campaign.yaml");
    const slugCampaignPath = path.resolve(config.campaignsDir, targetSlug);
    try {
        const stats = await fs.stat(slugCampaignPath);
        if (!stats.isDirectory()) {
            return null;
        }
    }
    catch {
        return null;
    }
    let rawPayload;
    try {
        rawPayload = await fs.readFile(campaignPath, "utf-8");
    }
    catch {
        return null;
    }
    const parsed = parse(rawPayload);
    if (typeof parsed !== "object" || parsed === null) {
        return null;
    }
    const normalized = normalizeCampaignPayload(parsed);
    if (!isCompleteCampaign(normalized)) {
        return null;
    }
    if (normalized.slug !== targetSlug) {
        return null;
    }
    return normalized;
}
export async function listCampaigns(config) {
    const campaignSlugs = await listCampaignSlugs(config.campaignsDir);
    const campaigns = [];
    for (const campaignSlug of campaignSlugs) {
        const campaign = await getCampaignBySlug(config, campaignSlug);
        if (campaign) {
            campaigns.push(campaign);
        }
    }
    return campaigns.sort((left, right) => left.title.toLowerCase().localeCompare(right.title.toLowerCase()));
}
function isSafeCampaignSlug(slug) {
    return /^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(slug);
}
