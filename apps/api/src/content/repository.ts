import { promises as fs } from "node:fs";
import path from "node:path";

import { parse } from "yaml";

import type { ApiConfig } from "../config.js";
import { getCampaignBySlug } from "../campaigns/repository.js";
import type { CampaignConfigRecord } from "./types.js";

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function normalizeCampaignSlugFromConfig(value: unknown): string {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : "";
}

function toIsoTimestamp(value: Date): string {
  const normalized = new Date(value);
  normalized.setMilliseconds(0);
  return normalized.toISOString().replace(/\.\d{3}Z$/, "+00:00");
}

function toCampaignConfigRecord(
  campaignSlug: string,
  config: Record<string, unknown>,
  updatedAt: string,
): CampaignConfigRecord {
  const parsedSlug = normalizeCampaignSlugFromConfig(config.slug);
  return {
    campaign_slug: parsedSlug || campaignSlug,
    updated_at: updatedAt,
    config,
  };
}

export async function getCampaignConfigFile(
  config: ApiConfig,
  campaignSlug: string,
): Promise<CampaignConfigRecord | null> {
  const safeCampaign = await getCampaignBySlug(config, campaignSlug);
  if (!safeCampaign) {
    return null;
  }

  const campaignConfigPath = path.resolve(config.campaignsDir, campaignSlug, "campaign.yaml");
  let rawPayload: string;
  let fileStats;

  try {
    [rawPayload, fileStats] = await Promise.all([
      fs.readFile(campaignConfigPath, "utf-8"),
      fs.stat(campaignConfigPath),
    ]);
  } catch {
    return null;
  }

  let parsed: unknown;
  try {
    parsed = parse(rawPayload);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return null;
  }

  const configRecord = asRecord(parsed);
  return toCampaignConfigRecord(
    safeCampaign.slug,
    configRecord,
    toIsoTimestamp(fileStats.mtime),
  );
}
