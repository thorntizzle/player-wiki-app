import type {
  CampaignConfigRecord,
  CampaignPageFileRecord,
  ContentPagePayload,
  ContentPageRemovalSafety,
} from "./types.js";

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

const FIXTURE_REMOVAL_SAFETY: ContentPageRemovalSafety = {
  can_hard_delete: true,
  hard_delete_blockers: [],
  removal_status_label: "Hard delete available",
  removal_guidance: "Hard delete is available after confirmation.",
  blockers_by_type: {
    backlinks: [],
    character_hooks: [],
    session_provenance: [],
  },
  samples: {
    backlinks: "",
    character_hooks: "",
    session_provenance: "",
  },
  page_title: "",
};

function normalizeRemovalSafety(
  record: CampaignPageFileRecord,
  removalSafety?: ContentPageRemovalSafety,
): ContentPageRemovalSafety {
  const source = removalSafety ?? FIXTURE_REMOVAL_SAFETY;
  return {
    can_hard_delete: source.can_hard_delete ?? true,
    hard_delete_blockers: source.hard_delete_blockers?.length ? source.hard_delete_blockers : [],
    blockers_by_type: {
      backlinks: source.blockers_by_type?.backlinks || [],
      character_hooks: source.blockers_by_type?.character_hooks || [],
      session_provenance: source.blockers_by_type?.session_provenance || [],
    },
    samples: {
      backlinks: source.samples?.backlinks || "",
      character_hooks: source.samples?.character_hooks || "",
      session_provenance: source.samples?.session_provenance || "",
    },
    page_title: source.page_title || record.page.title,
    removal_status_label: source.removal_status_label || "Hard delete available",
    removal_guidance: source.removal_guidance || "Hard delete is available after confirmation.",
  };
}

function withVisibilityDefaults(record: CampaignPageFileRecord): ContentPagePayload {
  return {
    page_ref: record.page_ref,
    relative_path: record.relative_path,
    updated_at: record.updated_at,
    metadata: record.metadata,
    page: record.page,
    removal_safety: normalizeRemovalSafety(record, FIXTURE_REMOVAL_SAFETY),
    can_hard_delete: true,
    hard_delete_blockers: [],
    removal_status_label: "Hard delete available",
    removal_guidance: "Hard delete is available after confirmation.",
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

function buildContentPageFilePayload(
  record: CampaignPageFileRecord,
  includeBody: boolean,
  removalSafety?: ContentPageRemovalSafety,
): ContentPagePayload {
  const payload = withVisibilityDefaults(record);
  payload.removal_safety = normalizeRemovalSafety(record, removalSafety);
  payload.can_hard_delete = payload.removal_safety.can_hard_delete;
  payload.hard_delete_blockers = [...payload.removal_safety.hard_delete_blockers];
  payload.removal_status_label = payload.removal_safety.removal_status_label;
  payload.removal_guidance = payload.removal_safety.removal_guidance;

  if (includeBody) {
    payload.body_markdown = record.body_markdown;
  } else {
    delete payload.body_markdown;
  }
  return payload;
}

export function buildContentPageListPayload(
  records: CampaignPageFileRecord[],
  removalSafety?: Record<string, ContentPageRemovalSafety>,
): { ok: true; pages: ContentPagePayload[] } {
  return {
    ok: true,
    pages: records.map((record) =>
      buildContentPageFilePayload(record, false, removalSafety?.[record.page_ref]),
    ),
  };
}

export function buildContentPageDetailPayload(
  record: CampaignPageFileRecord,
  removalSafety?: ContentPageRemovalSafety,
): { ok: true; page_file: ContentPagePayload } {
  const payload = buildContentPageFilePayload(record, true, removalSafety);
  return {
    ok: true,
    page_file: payload,
  };
}
