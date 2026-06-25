export interface CampaignConfigRecord {
  campaign_slug: string;
  updated_at: string;
  config: Record<string, unknown>;
}

export interface ContentPage {
  title: string;
  route_slug: string;
  section: string;
  subsection: string;
  page_type: string;
  display_order: number;
  published: boolean;
  aliases: string[];
  summary: string;
  image_path: string;
  image_alt: string;
  image_caption: string;
  reveal_after_session: number;
  source_ref: string;
  is_pinned: boolean;
  is_visible: boolean;
}

export interface CampaignPageFileRecord {
  page_ref: string;
  relative_path: string;
  updated_at: string;
  metadata: Record<string, unknown>;
  body_markdown: string;
  page: ContentPage;
}

export interface ContentPageRemovalSafety {
  blockers_by_type: Record<string, string[]>;
  samples: Record<string, string>;
  hard_delete_blockers: string[];
  page_title: string;
  can_hard_delete: boolean;
  removal_status_label: string;
  removal_guidance: string;
}

export interface ContentPagePayload {
  page_ref: string;
  relative_path: string;
  updated_at: string;
  metadata: Record<string, unknown>;
  body_markdown?: string;
  page: ContentPage;
  removal_safety: ContentPageRemovalSafety;
  can_hard_delete: boolean;
  hard_delete_blockers: string[];
  removal_status_label: string;
  removal_guidance: string;
}
