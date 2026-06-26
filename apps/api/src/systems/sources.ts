import { existsSync } from "node:fs";

import Database from "better-sqlite3";

import type { CampaignViewModel } from "../campaigns/view.js";

export type FixtureSystemsRole = "player" | "dm" | "admin";

export interface SystemsLibrary {
  library_slug: string;
  title: string;
  system_code: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface SystemsSourceState {
  source_id: string;
  title: string;
  library_slug: string;
  license_class: string;
  license_class_label: string;
  public_visibility_allowed: boolean;
  requires_unofficial_notice: boolean;
  status: string;
  is_enabled: boolean;
  default_visibility: string;
  is_configured: boolean;
  entry_count: number;
  permissions: {
    can_access: boolean;
    can_manage: boolean;
  };
}

export interface SystemsSourceListPayload {
  campaign: CampaignViewModel;
  library: SystemsLibrary | null;
  sources: SystemsSourceState[];
  permissions: {
    can_manage_systems: boolean;
  };
}

interface SystemsLibraryRow {
  library_slug: string;
  title: string;
  system_code: string;
  status: string;
  created_at: string;
  updated_at: string;
}

interface SystemsSourceRow {
  source_id: string;
  title: string;
  library_slug: string;
  license_class: string;
  public_visibility_allowed: number;
  requires_unofficial_notice: number;
  status: string;
  configured_enabled: number | null;
  configured_visibility: string | null;
  entry_count: number;
}

interface CampaignSourceSeed {
  source_id: string;
  enabled?: boolean;
  default_visibility?: string;
}

const LICENSE_CLASS_LABELS: Record<string, string> = {
  app_reference: "App-authored reference",
  proprietary_private: "Proprietary - private campaign use",
  srd_cc: "SRD - Creative Commons",
  open_license: "Open license",
  custom_campaign: "Custom campaign",
};

const VISIBILITY_VALUES = new Set(["public", "players", "dm", "private"]);

function titleCaseFallback(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asBoolean(value: unknown): boolean | undefined {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value !== 0;
  }
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["1", "true", "yes", "on"].includes(normalized)) {
      return true;
    }
    if (["0", "false", "no", "off"].includes(normalized)) {
      return false;
    }
  }
  return undefined;
}

function normalizeVisibility(value: unknown, fallback = "dm"): string {
  const normalized = typeof value === "string" ? value.trim().toLowerCase() : "";
  return VISIBILITY_VALUES.has(normalized) ? normalized : fallback;
}

function clampVisibilityForSource(source: SystemsSourceRow, visibility: string): string {
  if (visibility === "public" && !Boolean(source.public_visibility_allowed)) {
    return "players";
  }
  return visibility;
}

function parseSourceSeeds(campaignConfig: Record<string, unknown>): Map<string, CampaignSourceSeed> {
  const seeds = new Map<string, CampaignSourceSeed>();
  const rawSources = campaignConfig.systems_sources;
  if (!Array.isArray(rawSources)) {
    return seeds;
  }

  for (const rawSource of rawSources) {
    const record = asRecord(rawSource);
    const sourceId = String(record.source_id || "").trim();
    if (!sourceId) {
      continue;
    }
    seeds.set(sourceId, {
      source_id: sourceId,
      enabled: asBoolean(record.enabled),
      default_visibility: normalizeVisibility(record.default_visibility, ""),
    });
  }
  return seeds;
}

function serializeLibrary(row: SystemsLibraryRow | undefined): SystemsLibrary | null {
  if (!row) {
    return null;
  }
  return {
    library_slug: String(row.library_slug),
    title: String(row.title),
    system_code: String(row.system_code),
    status: String(row.status),
    created_at: String(row.created_at),
    updated_at: String(row.updated_at),
  };
}

function canManageSystems(role: FixtureSystemsRole): boolean {
  return role === "dm" || role === "admin";
}

function canAccessSource(role: FixtureSystemsRole, isEnabled: boolean, visibility: string): boolean {
  if (canManageSystems(role)) {
    return true;
  }
  if (!isEnabled) {
    return false;
  }
  return visibility === "public" || visibility === "players";
}

function serializeSourceState(
  row: SystemsSourceRow,
  seed: CampaignSourceSeed | undefined,
  role: FixtureSystemsRole,
): SystemsSourceState {
  const isConfigured = row.configured_enabled !== null || Boolean(row.configured_visibility);
  const seededEnabled = seed?.enabled ?? false;
  const isEnabled = isConfigured ? Boolean(row.configured_enabled) : seededEnabled;
  const fallbackVisibility = seed?.default_visibility || "dm";
  const configuredVisibility = row.configured_visibility || "";
  const defaultVisibility = clampVisibilityForSource(
    row,
    normalizeVisibility(isConfigured ? configuredVisibility : fallbackVisibility, "dm"),
  );
  const canManage = canManageSystems(role);
  const canAccess = canAccessSource(role, isEnabled, defaultVisibility);

  return {
    source_id: String(row.source_id),
    title: String(row.title),
    library_slug: String(row.library_slug),
    license_class: String(row.license_class),
    license_class_label: LICENSE_CLASS_LABELS[row.license_class] || titleCaseFallback(String(row.license_class)),
    public_visibility_allowed: Boolean(row.public_visibility_allowed),
    requires_unofficial_notice: Boolean(row.requires_unofficial_notice),
    status: String(row.status),
    is_enabled: isEnabled,
    default_visibility: defaultVisibility,
    is_configured: isConfigured,
    entry_count: isEnabled ? Number(row.entry_count || 0) : 0,
    permissions: {
      can_access: canAccess,
      can_manage: canManage,
    },
  };
}

function emptyPayload(campaign: CampaignViewModel, canManage: boolean): SystemsSourceListPayload {
  return {
    campaign,
    library: null,
    sources: [],
    permissions: {
      can_manage_systems: canManage,
    },
  };
}

export function buildCampaignSystemsSourceListPayload(
  dbPath: string,
  campaign: CampaignViewModel,
  campaignConfig: Record<string, unknown>,
  role: FixtureSystemsRole,
): SystemsSourceListPayload {
  const canManage = canManageSystems(role);
  const librarySlug = campaign.systems_library_slug || "";
  if (!librarySlug || !existsSync(dbPath)) {
    return emptyPayload(campaign, canManage);
  }

  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    const library = serializeLibrary(
      database
        .prepare(
          `
            SELECT library_slug, title, system_code, status, created_at, updated_at
            FROM systems_libraries
            WHERE library_slug = ?
          `,
        )
        .get(librarySlug) as SystemsLibraryRow | undefined,
    );
    if (!library) {
      return emptyPayload(campaign, canManage);
    }

    const seeds = parseSourceSeeds(campaignConfig);
    const rows = database
      .prepare(
        `
          SELECT
            systems_sources.source_id,
            systems_sources.title,
            systems_sources.library_slug,
            systems_sources.license_class,
            systems_sources.public_visibility_allowed,
            systems_sources.requires_unofficial_notice,
            systems_sources.status,
            campaign_enabled_sources.is_enabled AS configured_enabled,
            campaign_enabled_sources.default_visibility AS configured_visibility,
            (
              SELECT COUNT(*)
              FROM systems_entries
              WHERE systems_entries.library_slug = systems_sources.library_slug
                AND systems_entries.source_id = systems_sources.source_id
            ) AS entry_count
          FROM systems_sources
          LEFT JOIN campaign_enabled_sources
            ON campaign_enabled_sources.campaign_slug = ?
           AND campaign_enabled_sources.library_slug = systems_sources.library_slug
           AND campaign_enabled_sources.source_id = systems_sources.source_id
          WHERE systems_sources.library_slug = ?
          ORDER BY LOWER(systems_sources.title), systems_sources.source_id
        `,
      )
      .all(campaign.slug, librarySlug) as SystemsSourceRow[];
    const sources = rows
      .map((row) => serializeSourceState(row, seeds.get(row.source_id), role))
      .filter((state) => canManage || (state.is_enabled && state.permissions.can_access));

    return {
      campaign,
      library,
      sources,
      permissions: {
        can_manage_systems: canManage,
      },
    };
  } catch (error) {
    if (error instanceof Error && error.message.includes("no such table")) {
      return emptyPayload(campaign, canManage);
    }
    throw error;
  } finally {
    database.close();
  }
}
