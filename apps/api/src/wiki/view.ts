import type {
  WikiCampaignConfig,
  WikiImagePayload,
  WikiPagePayload,
  WikiPageRecord,
  WikiSectionGroup,
  WikiSectionNavigationItem,
  WikiSectionSplit,
} from "./types.js";
import { sectionSortKey, slugify, subsectionSortKey } from "./repository.js";

function campaignHref(campaignSlug: string, suffix: string = ""): string {
  const normalized = suffix.replace(/^\/+|\/+$/g, "");
  return normalized ? `/app-next/campaigns/${campaignSlug}/${normalized}` : `/app-next/campaigns/${campaignSlug}`;
}

function resolveImagePayload(
  campaign: WikiCampaignConfig,
  page: WikiPageRecord,
  assetExists: (candidate: string) => Promise<boolean>,
): Promise<WikiImagePayload | null> {
  if (!page.image_ref) {
    return Promise.resolve(null);
  }
  return (async () => {
    const exists = await assetExists(page.image_ref);
    if (!exists) {
      return null;
    }
    return {
      asset_ref: page.image_ref,
      url: `/campaigns/${campaign.slug}/assets/${page.image_ref}`,
      media_type: imageMediaType(page.image_ref),
      alt_text: page.image_alt || page.title,
      caption: page.image_caption,
    };
  })();
}

function imageMediaType(imageRef: string): string {
  const ext = imageRef.split(".").pop()?.toLowerCase() ?? "";
  const overrides: Record<string, string> = {
    png: "image/png",
    jpg: "image/jpeg",
    jpeg: "image/jpeg",
    webp: "image/webp",
    gif: "image/gif",
  };
  return overrides[ext] || "application/octet-stream";
}

export function serializePublicWikiPage(
  campaign: WikiCampaignConfig,
  page: WikiPageRecord,
  options: { includeImage?: boolean; assetsExist: (assetRef: string) => Promise<boolean> },
): Promise<WikiPagePayload> {
  return (async () => {
    const pageSlug = page.route_slug;
    const payload: WikiPagePayload = {
      page_ref: page.page_ref,
      title: page.title,
      route_slug: pageSlug,
      href: campaignHref(campaign.slug, `pages/${pageSlug}`),
      section: page.section,
      section_slug: slugify(page.section),
      section_href: campaignHref(campaign.slug, `sections/${slugify(page.section)}`),
      subsection: page.subsection,
      page_type: page.page_type,
      display_type: page.display_type,
      summary: page.summary,
      display_order: page.display_order,
      reveal_after_session: page.reveal_after_session,
      is_pinned: page.is_pinned,
    };
    if (options.includeImage) {
      payload.image = await resolveImagePayload(campaign, page, options.assetsExist);
    }
    return payload;
  })();
}

export function serializeSectionNavigation(
  campaign: WikiCampaignConfig,
  pages: WikiPageRecord[],
): WikiSectionNavigationItem[] {
  const grouped = new Map<string, WikiPageRecord[]>();
  for (const page of pages) {
    if (!grouped.has(page.section)) {
      grouped.set(page.section, []);
    }
    grouped.get(page.section)!.push(page);
  }
  return [...grouped.entries()]
    .sort(([sectionA], [sectionB]) => {
      const sortA = sectionSortKey(sectionA);
      const sortB = sectionSortKey(sectionB);
      if (sortA[0] !== sortB[0]) {
        return sortA[0] - sortB[0];
      }
      return sortA[1] < sortB[1] ? -1 : sortA[1] > sortB[1] ? 1 : 0;
    })
    .map(([sectionName, sectionPages]) => ({
      section_name: sectionName,
      section_slug: slugify(sectionName),
      href: campaignHref(campaign.slug, `sections/${slugify(sectionName)}`),
      page_count: sectionPages.length,
    }));
}

export function serializePublicWikiSectionGroup(
  campaign: WikiCampaignConfig,
  sectionName: string,
  pages: WikiPageRecord[],
  options: { includeImage?: boolean; assetsExist: (assetRef: string) => Promise<boolean> },
): Promise<WikiSectionGroup> {
  return (async () => {
    const pagePayloads = await Promise.all(
      pages.map((page) => serializePublicWikiPage(campaign, page, { ...options, includeImage: false })),
    );
    return {
      section_name: sectionName,
      section_slug: slugify(sectionName),
      href: campaignHref(campaign.slug, `sections/${slugify(sectionName)}`),
      page_count: pages.length,
      pages: pagePayloads,
    };
  })();
}

export async function splitPagesBySubsection(
  campaign: WikiCampaignConfig,
  sectionName: string,
  pages: WikiPageRecord[],
  options: { includeImage?: boolean; assetsExist: (assetRef: string) => Promise<boolean> },
): Promise<WikiSectionSplit> {
  const topLevelPages = pages.filter((page) => !page.subsection);
  const grouped = new Map<string, WikiPageRecord[]>();
  for (const page of pages) {
    if (!page.subsection) {
      continue;
    }
    if (!grouped.has(page.subsection)) {
      grouped.set(page.subsection, []);
    }
    grouped.get(page.subsection)!.push(page);
  }

  const subsectionGroups = (
    await Promise.all(
      [...grouped.entries()]
        .sort(([left], [right]) => {
          const leftSort = subsectionSortKey(sectionName, left);
          const rightSort = subsectionSortKey(sectionName, right);
          if (leftSort[0] !== rightSort[0]) {
            return leftSort[0] - rightSort[0];
          }
          return leftSort[1] < rightSort[1] ? -1 : leftSort[1] > rightSort[1] ? 1 : 0;
        })
        .map(async ([subsectionName, subsectionPages]) => ({
          subsection_name: subsectionName,
          page_count: subsectionPages.length,
          pages: await Promise.all(
            subsectionPages.map((page) =>
              serializePublicWikiPage(campaign, page, { ...options, includeImage: false }),
            ),
          ),
        })),
    )
  );

  return {
    top_level_pages: await Promise.all(
      topLevelPages.map((page) => serializePublicWikiPage(campaign, page, { ...options, includeImage: false })),
    ),
    subsection_groups: subsectionGroups,
    show_subsections: subsectionGroups.length > 0,
  };
}

export function serializeCampaign(campaign: WikiCampaignConfig) {
  return {
    slug: campaign.slug,
    title: campaign.title,
    summary: campaign.summary,
    system: campaign.system,
    current_session: campaign.current_session,
    systems_library_slug: campaign.systems_library_slug,
  };
}
