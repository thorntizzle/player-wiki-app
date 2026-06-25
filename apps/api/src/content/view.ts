import type { CampaignConfigRecord } from "./types.js";

const EDITABLE_FIELDS = [
  "current_session",
  "source_wiki_root",
  "summary",
  "system",
  "systems_library",
  "title",
];

export interface CampaignConfigPayload {
  ok: true;
  config_file: {
    campaign_slug: string;
    updated_at: string;
    config: Record<string, unknown>;
    editable_fields: string[];
  };
}

export function buildCampaignConfigPayload(record: CampaignConfigRecord): CampaignConfigPayload {
  return {
    ok: true,
    config_file: {
      campaign_slug: record.campaign_slug,
      updated_at: record.updated_at,
      config: record.config,
      editable_fields: [...EDITABLE_FIELDS].sort(),
    },
  };
}
