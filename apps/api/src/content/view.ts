import type {
  CampaignAssetFileRecord,
  CampaignCharacterFileRecord,
  CampaignConfigRecord,
  CampaignPageFileRecord,
  ContentPagePayload,
  ContentPageRemovalSafety,
  DeletedCharacterContent,
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

function recordString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value : "";
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

function buildContentCharacterSummaryPayload(record: CampaignCharacterFileRecord) {
  return {
    character_slug: record.character_slug,
    updated_at: record.updated_at,
    name: recordString(record.definition, "name"),
    status: recordString(record.definition, "status"),
    import_status: recordString(record.import_metadata, "import_status"),
  };
}

export function buildContentCharacterListPayload(
  records: CampaignCharacterFileRecord[],
): { ok: true; characters: ReturnType<typeof buildContentCharacterSummaryPayload>[] } {
  return {
    ok: true,
    characters: records.map(buildContentCharacterSummaryPayload),
  };
}

export function buildContentCharacterDetailPayload(
  record: CampaignCharacterFileRecord,
): {
  ok: true;
  character_file: {
    character_slug: string;
    updated_at: string;
    definition: Record<string, unknown>;
    import_metadata: Record<string, unknown>;
    state_created: boolean;
  };
} {
  return {
    ok: true,
    character_file: {
      character_slug: record.character_slug,
      updated_at: record.updated_at,
      definition: record.definition,
      import_metadata: record.import_metadata,
      state_created: record.state_created,
    },
  };
}

export function buildContentCharacterDeletePayload(
  deleted: DeletedCharacterContent,
): {
  ok: true;
  deleted: DeletedCharacterContent;
} {
  return {
    ok: true,
    deleted,
  };
}

function buildContentAssetFilePayload(
  campaignSlug: string,
  record: CampaignAssetFileRecord,
  includeData: boolean,
) {
  const payload: {
    asset_ref: string;
    relative_path: string;
    size_bytes: number;
    media_type: string;
    updated_at: string;
    url: string;
    data_base64?: string;
  } = {
    asset_ref: record.asset_ref,
    relative_path: record.relative_path,
    size_bytes: record.size_bytes,
    media_type: record.media_type,
    updated_at: record.updated_at,
    url: `/campaigns/${campaignSlug}/assets/${record.asset_ref}`,
  };

  if (includeData) {
    payload.data_base64 = record.data_base64 || "";
  }
  return payload;
}

export function buildContentAssetListPayload(
  campaignSlug: string,
  records: CampaignAssetFileRecord[],
): { ok: true; assets: ReturnType<typeof buildContentAssetFilePayload>[] } {
  return {
    ok: true,
    assets: records.map((record) => buildContentAssetFilePayload(campaignSlug, record, false)),
  };
}

export function buildContentAssetDetailPayload(
  campaignSlug: string,
  record: CampaignAssetFileRecord,
): { ok: true; asset_file: ReturnType<typeof buildContentAssetFilePayload> } {
  return {
    ok: true,
    asset_file: buildContentAssetFilePayload(campaignSlug, record, true),
  };
}

export function buildContentAssetWritePayload(
  campaignSlug: string,
  record: CampaignAssetFileRecord,
): { ok: true; asset_file: ReturnType<typeof buildContentAssetFilePayload> } {
  return {
    ok: true,
    asset_file: buildContentAssetFilePayload(campaignSlug, record, false),
  };
}

export function buildContentAssetDeletePayload(
  record: CampaignAssetFileRecord,
): { ok: true; deleted: { asset_ref: string; relative_path: string } } {
  return {
    ok: true,
    deleted: {
      asset_ref: record.asset_ref,
      relative_path: record.relative_path,
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

export function buildContentPageDeletePayload(
  record: CampaignPageFileRecord,
): { ok: true; deleted: { page_ref: string; relative_path: string } } {
  return {
    ok: true,
    deleted: {
      page_ref: record.page_ref,
      relative_path: record.relative_path,
    },
  };
}
