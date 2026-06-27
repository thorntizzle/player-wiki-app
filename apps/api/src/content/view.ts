import type {
  CampaignAssetFileRecord,
  CampaignCharacterFileRecord,
  CampaignConfigRecord,
  CampaignPageFileRecord,
  ContentPagePayload,
  ContentPageRemovalSafety,
  DeletedCharacterContent,
} from "./types.js";
import type { CharacterStateSnapshot } from "./characterState.js";
import type { CampaignViewModel } from "../campaigns/view.js";

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

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function asInt(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.trunc(value);
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value.trim());
    return Number.isFinite(parsed) ? Math.trunc(parsed) : fallback;
  }
  return fallback;
}

const STANDARD_DND_CLASS_HIT_DICE: Record<string, number> = {
  artificer: 8,
  barbarian: 12,
  bard: 8,
  cleric: 8,
  druid: 8,
  fighter: 10,
  monk: 8,
  paladin: 10,
  ranger: 10,
  rogue: 8,
  sorcerer: 6,
  warlock: 8,
  wizard: 6,
};

const VALID_HIT_DIE_FACES = new Set([4, 6, 8, 10, 12]);

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

function campaignHref(campaignSlug: string, suffix = ""): string {
  const normalized = suffix.replace(/^\/+|\/+$/g, "");
  return normalized ? `/app-next/campaigns/${campaignSlug}/${normalized}` : `/app-next/campaigns/${campaignSlug}`;
}

function flaskCampaignHref(campaignSlug: string, suffix = ""): string {
  const normalized = suffix.replace(/^\/+|\/+$/g, "");
  return normalized ? `/campaigns/${campaignSlug}/${normalized}` : `/campaigns/${campaignSlug}`;
}

function profileClassLevelText(profile: Record<string, unknown>, fallback = "Character"): string {
  const classRows = asArray(profile.classes)
    .map(asRecord)
    .map((row) => {
      const systemsRef = asRecord(row.systems_ref);
      const className = asString(systemsRef.title) || asString(row.class_name);
      const classLevel = asInt(row.level, 0);
      if (className && classLevel > 0) {
        return `${className} ${classLevel}`;
      }
      if (className) {
        return className;
      }
      return classLevel > 0 ? `Level ${classLevel}` : "";
    })
    .filter((item) => item.length > 0);
  if (classRows.length > 0) {
    return classRows.join(" / ");
  }
  return asString(profile.class_level_text) || fallback;
}

function summarizeResourceValue(resource: Record<string, unknown>): string {
  const current = asInt(resource.current, 0);
  if (resource.max === null || resource.max === undefined) {
    return String(current);
  }
  return `${current} / ${asInt(resource.max, 0)}`;
}

function buildResourcePreview(state: Record<string, unknown>): Array<{ label: string; value: string }> {
  return asArray(state.resources)
    .map(asRecord)
    .sort((left, right) => {
      const leftOrder = asInt(left.display_order, 0);
      const rightOrder = asInt(right.display_order, 0);
      if (leftOrder !== rightOrder) {
        return leftOrder - rightOrder;
      }
      return (asString(left.label) || "resource").toLowerCase().localeCompare((asString(right.label) || "resource").toLowerCase());
    })
    .slice(0, 3)
    .map((resource) => ({
      label: asString(resource.label) || "Resource",
      value: summarizeResourceValue(resource),
    }));
}

function normalizeSystemKey(value: unknown): string {
  return asString(value).toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function isXianxiaSystem(value: unknown): boolean {
  return normalizeSystemKey(value) === "xianxia";
}

function extractHitDieFaces(value: unknown): number {
  if (value === null || value === undefined || value === "") {
    return 0;
  }
  if (typeof value === "object" && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    return extractHitDieFaces(record.faces ?? record.face ?? record.die);
  }
  let text = String(value).trim().toLowerCase();
  if (text.startsWith("d")) {
    text = text.slice(1);
  }
  const faces = Number.parseInt(text, 10);
  return VALID_HIT_DIE_FACES.has(faces) ? faces : 0;
}

function normalizeClassName(value: unknown): string {
  return asString(value)
    .toLowerCase()
    .replace(/[^a-z]/g, "");
}

function profileClassRows(profile: Record<string, unknown>): Record<string, unknown>[] {
  const rows = asArray(profile.classes)
    .map(asRecord)
    .filter((row) => Object.keys(row).length > 0);
  if (rows.length > 0) {
    return rows;
  }

  const classLevelText = asString(profile.class_level_text);
  const match = classLevelText.match(/^([A-Za-z][A-Za-z '\-]*)\s+(\d+)$/);
  if (!match) {
    return [];
  }
  return [{ class_name: match[1]?.trim() || "", level: asInt(match[2], 0) }];
}

function hitDieFacesForClassRow(classRow: Record<string, unknown>): number {
  for (const key of ["hit_die_faces", "hit_die_face", "hit_die"]) {
    const faces = extractHitDieFaces(classRow[key]);
    if (faces) {
      return faces;
    }
  }

  const metadata = asRecord(classRow.metadata);
  const metadataFaces = extractHitDieFaces(metadata.hit_die ?? metadata.hitDie);
  if (metadataFaces) {
    return metadataFaces;
  }

  const systemsRef = asRecord(classRow.systems_ref);
  const systemsRefFaces = extractHitDieFaces(systemsRef.hit_die ?? systemsRef.hitDie);
  if (systemsRefFaces) {
    return systemsRefFaces;
  }
  const systemsRefMetadata = asRecord(systemsRef.metadata);
  const systemsRefMetadataFaces = extractHitDieFaces(systemsRefMetadata.hit_die ?? systemsRefMetadata.hitDie);
  if (systemsRefMetadataFaces) {
    return systemsRefMetadataFaces;
  }

  const className = normalizeClassName(classRow.class_name ?? classRow.name);
  return STANDARD_DND_CLASS_HIT_DICE[className] ?? (className ? 8 : 0);
}

function deriveHitDiceMaxPools(definition: Record<string, unknown>): Array<{ faces: number; max: number }> {
  if (isXianxiaSystem(definition.system)) {
    return [];
  }

  const maxByFaces = new Map<number, number>();
  for (const classRow of profileClassRows(asRecord(definition.profile))) {
    const level = asInt(classRow.level, 0);
    if (level <= 0) {
      continue;
    }
    const faces = hitDieFacesForClassRow(classRow);
    if (!faces) {
      continue;
    }
    maxByFaces.set(faces, (maxByFaces.get(faces) ?? 0) + level);
  }

  return [...maxByFaces.entries()]
    .sort(([leftFaces], [rightFaces]) => leftFaces - rightFaces)
    .map(([faces, max]) => ({ faces, max }))
    .filter((pool) => pool.max > 0);
}

function existingHitDiceCurrentByFaces(rawState: unknown): Map<number, number> {
  const hitDiceState = asRecord(rawState);
  const currentByFaces = new Map<number, number>();

  for (const pool of asArray(hitDiceState.pools).map(asRecord)) {
    const faces = extractHitDieFaces(pool.faces ?? pool.die ?? pool.label);
    if (faces) {
      currentByFaces.set(faces, asInt(pool.current, 0));
    }
  }

  for (const [key, value] of Object.entries(hitDiceState)) {
    const faces = extractHitDieFaces(key);
    if (faces) {
      currentByFaces.set(faces, asInt(value, 0));
    }
  }
  return currentByFaces;
}

function hitDiceLongRestRegainAmount(definition: Record<string, unknown>): number {
  const totalLevel = deriveHitDiceMaxPools(definition).reduce((sum, pool) => sum + pool.max, 0);
  return totalLevel > 0 ? Math.max(1, Math.floor(totalLevel / 2)) : 0;
}

function buildHitDiceSummary(definition: Record<string, unknown>, state: Record<string, unknown>) {
  const existingCurrentByFaces = existingHitDiceCurrentByFaces(state.hit_dice);
  const pools = deriveHitDiceMaxPools(definition)
    .map((pool) => {
      const current = existingCurrentByFaces.get(pool.faces) ?? pool.max;
      return {
        faces: pool.faces,
        label: `d${pool.faces}`,
        current: Math.max(0, Math.min(current, pool.max)),
        max: pool.max,
        input_name: `hit_dice_d${pool.faces}`,
      };
    })
    .filter((pool) => pool.faces > 0);
  const value = pools.map((pool) => `${pool.label} ${pool.current}/${pool.max}`).join(" | ");
  const fullValue = pools
    .filter((pool) => pool.max > 0)
    .map((pool) => `${pool.max}d${pool.faces}`)
    .join(" + ");
  return {
    pools,
    value: value || "--",
    full_value: fullValue || "--",
    regain_on_long_rest: hitDiceLongRestRegainAmount(definition),
  };
}

function buildCharacterPortraitPayload(
  campaignSlug: string,
  record: CampaignCharacterFileRecord,
  assetByRef: Map<string, CampaignAssetFileRecord>,
) {
  const profile = asRecord(record.definition.profile);
  const assetRef = asString(profile.portrait_asset_ref);
  if (!assetRef) {
    return null;
  }
  const asset = assetByRef.get(assetRef);
  if (!asset) {
    return null;
  }
  return {
    asset_ref: assetRef,
    url: `/campaigns/${campaignSlug}/characters/${record.character_slug}/portrait`,
    media_type: asset.media_type,
    alt_text: asString(profile.portrait_alt) || asString(record.definition.name) || record.character_slug,
    caption: asString(profile.portrait_caption),
  };
}

export function buildCharacterRosterPayload({
  campaign,
  records,
  stateBySlug,
  assetByRef,
  query,
  canManageSession,
}: {
  campaign: CampaignViewModel;
  records: CampaignCharacterFileRecord[];
  stateBySlug: Map<string, CharacterStateSnapshot>;
  assetByRef: Map<string, CampaignAssetFileRecord>;
  query: string;
  canManageSession: boolean;
}) {
  const characterCards = records
    .map((record) => {
      const definition = record.definition;
      const profile = asRecord(definition.profile);
      const stats = asRecord(definition.stats);
      const snapshot = stateBySlug.get(record.character_slug) ?? { revision: 1, state: {} };
      const vitals = asRecord(snapshot.state.vitals);
      const classLevelText = profileClassLevelText(profile);
      const species = asString(profile.species);
      const background = asString(profile.background);
      const name = asString(definition.name) || record.character_slug;
      const searchText = [name, profileClassLevelText(profile, ""), species, background]
        .filter((item) => item.length > 0)
        .join(" ")
        .toLowerCase();
      return {
        slug: record.character_slug,
        name,
        status: asString(definition.status),
        class_level_text: classLevelText,
        species,
        background,
        system: asString(definition.system),
        href: campaignHref(campaign.slug, `characters/${record.character_slug}`),
        flask_href: flaskCampaignHref(campaign.slug, `characters/${record.character_slug}`),
        search_text: searchText,
        current_hp: asInt(vitals.current_hp, 0),
        max_hp: asInt(stats.max_hp, 0),
        temp_hp: asInt(vitals.temp_hp, 0),
        hit_dice: buildHitDiceSummary(definition, snapshot.state),
        resource_preview: buildResourcePreview(snapshot.state),
        portrait: buildCharacterPortraitPayload(campaign.slug, record, assetByRef),
        revision: snapshot.revision,
      };
    })
    .filter((card) => (query ? card.search_text.includes(query.toLowerCase()) : true));

  const systemKey = normalizeSystemKey(campaign.system);
  const characterCreateLane = systemKey === "xianxia" ? "xianxia" : systemKey === "dnd5e" ? "dnd5e" : "";
  const nativeCharacterCreateSupported = Boolean(characterCreateLane);
  const nativeCharacterToolsSupported = systemKey === "dnd5e";
  const canCreateCharacters = canManageSession && nativeCharacterCreateSupported;
  const canImportXianxiaCharacters = canCreateCharacters && characterCreateLane === "xianxia";
  return {
    ok: true,
    campaign,
    characters: characterCards,
    query,
    result_count: characterCards.length,
    tools: {
      can_create_characters: canCreateCharacters,
      can_import_xianxia_characters: canImportXianxiaCharacters,
      native_character_tools_supported: nativeCharacterToolsSupported,
      native_character_create_supported: nativeCharacterCreateSupported,
      character_create_lane: characterCreateLane,
    },
    links: {
      flask_roster_url: flaskCampaignHref(campaign.slug, "characters"),
      gen2_roster_url: campaignHref(campaign.slug, "characters"),
      ...(canCreateCharacters
        ? {
            flask_create_character_url: flaskCampaignHref(campaign.slug, "characters/new"),
            create_character_url: campaignHref(campaign.slug, "characters/new"),
          }
        : {}),
      ...(canImportXianxiaCharacters
        ? {
            flask_import_xianxia_url: flaskCampaignHref(campaign.slug, "characters/import/xianxia-manual"),
            import_xianxia_url: campaignHref(campaign.slug, "characters/import/xianxia-manual"),
          }
        : {}),
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
