export interface WikiImagePayload {
  asset_ref: string;
  url: string;
  media_type: string;
  alt_text: string;
  caption: string;
}

export interface WikiPageRecord {
  page_ref: string;
  title: string;
  route_slug: string;
  section: string;
  subsection: string;
  page_type: string;
  display_type: string;
  summary: string;
  display_order: number;
  reveal_after_session: number;
  is_pinned: boolean;
  image_ref: string;
  image_alt: string;
  image_caption: string;
  body_markdown: string;
  body_html: string | null;
  aliases: string[];
  source_path: string;
  raw_link_targets: string[];
  resolved_links: string[];
  backlinks: string[];
  published: boolean;
}

export interface WikiPagePayload {
  page_ref: string;
  title: string;
  route_slug: string;
  href: string;
  section: string;
  section_slug: string;
  section_href: string;
  subsection: string;
  page_type: string;
  display_type: string;
  summary: string;
  display_order: number;
  reveal_after_session: number;
  is_pinned: boolean;
  image?: WikiImagePayload | null;
}

export interface WikiCampaignConfig {
  title: string;
  slug: string;
  summary: string;
  system: string;
  current_session: number;
  systems_library_slug: string | null;
  content_dir: string;
  assets_dir: string;
}

export interface WikiCampaignRepository {
  campaign: WikiCampaignConfig;
  pages: Map<string, WikiPageRecord>;
}

export interface WikiSectionGroup {
  section_name: string;
  section_slug: string;
  href: string;
  page_count: number;
  pages: Array<WikiPagePayload>;
}

export interface WikiSectionNavigationItem {
  section_name: string;
  section_slug: string;
  href: string;
  page_count: number;
}

export interface WikiSubsectionGroup {
  subsection_name: string;
  page_count: number;
  pages: Array<WikiPagePayload>;
}

export interface WikiSectionSplit {
  top_level_pages: Array<WikiPagePayload>;
  subsection_groups: Array<WikiSubsectionGroup>;
  show_subsections: boolean;
}
