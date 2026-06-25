export interface CampaignFixtureSource {
  systems_library?: string;
  slug?: unknown;
  title?: unknown;
  summary?: unknown;
  system?: unknown;
  current_session?: unknown;
}

export interface CampaignViewModel {
  slug: string;
  title: string;
  summary: string;
  system: string;
  current_session: number | null;
  systems_library_slug: string | null;
}

function asString(value: unknown): string {
  if (typeof value !== "string") {
    return "";
  }
  return value.trim();
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.trunc(value);
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value.trim());
    if (Number.isFinite(parsed)) {
      return Math.trunc(parsed);
    }
  }
  return null;
}

export function normalizeCampaignPayload(payload: CampaignFixtureSource): CampaignViewModel {
  const slug = asString(payload.slug);
  const title = asString(payload.title);
  const summary = asString(payload.summary);
  const system = asString(payload.system);
  const systemsLibrarySlug = asString(payload.systems_library);
  return {
    slug,
    title,
    summary,
    system,
    current_session: asNumber(payload.current_session),
    systems_library_slug: systemsLibrarySlug || null,
  };
}

export function isCompleteCampaign(payload: CampaignViewModel): boolean {
  return payload.slug.length > 0 && payload.title.length > 0 && payload.system.length > 0;
}
