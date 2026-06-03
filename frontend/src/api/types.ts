export interface AppMeta {
  version?: string;
  build_id?: string;
  git_sha?: string;
  runtime?: string;
}

export interface ApiResponseBase {
  ok: boolean;
}

export interface CampaignRecord {
  slug: string;
  title: string;
  summary: string;
  system: string;
  current_session: number | null;
  systems_library_slug: string;
}

export interface CampaignEntry {
  campaign: CampaignRecord;
  role: string;
  auth_source?: string | null;
  visibility?: Record<string, unknown>;
  permissions?: Record<string, unknown>;
}

export interface CampaignsResponse extends ApiResponseBase {
  campaigns: CampaignEntry[];
}

export interface ApiAppResponse extends ApiResponseBase {
  app: AppMeta;
}

export interface SessionArticleImage {
  filename: string;
  media_type: string;
  alt_text: string | null;
  caption: string | null;
  updated_at: string | null;
  url: string;
}

export interface SessionArticle {
  id: number;
  title: string;
  body_markdown: string;
  body_format: string;
  source_page_ref: string;
  source_kind: string;
  source_ref: string;
  status: string;
  created_at: string | null;
  created_by_user_id: number | null;
  revealed_at: string | null;
  revealed_by_user_id: number | null;
  revealed_in_session_id: number | null;
  is_revealed: boolean;
  image: SessionArticleImage | null;
}

export interface SessionMessage {
  id: number;
  session_id: number;
  campaign_slug: string;
  message_type: string;
  body_text: string;
  author_user_id: number | null;
  author_display_name: string;
  article_id: number | null;
  created_at: string | null;
  article: SessionArticle | null;
}

export interface SessionRecord {
  id: number;
  campaign_slug: string;
  status: string;
  started_at: string | null;
  started_by_user_id: number | null;
  ended_at: string | null;
  ended_by_user_id: number | null;
  is_active: boolean;
}

export interface SessionPermissions {
  can_manage_session: boolean;
  can_post_messages: boolean;
}

export interface SessionPayload extends ApiResponseBase {
  campaign: CampaignRecord;
  permissions: SessionPermissions;
  active_session: SessionRecord | null;
  messages: SessionMessage[];
  staged_articles?: SessionArticle[];
  revealed_articles?: SessionArticle[];
}

export interface MessagePostResponse extends ApiResponseBase {
  message: SessionMessage;
}

export interface ApiErrorPayload {
  ok: false;
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export interface ApiErrorEnvelope {
  status: number;
  error: ApiErrorPayload["error"];
}
