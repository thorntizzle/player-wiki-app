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
  body_format: "markdown" | "html" | string;
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

export interface SessionLogSummary {
  session: SessionRecord;
  message_count: number;
  last_message_at: string | null;
  detail_url: string;
}

export interface SessionPermissions {
  can_manage_session: boolean;
  can_post_messages: boolean;
  can_access_wiki_lookup?: boolean;
}

export interface SessionPayload extends ApiResponseBase {
  campaign: CampaignRecord;
  permissions: SessionPermissions;
  active_session: SessionRecord | null;
  messages: SessionMessage[];
  staged_articles?: SessionArticle[];
  revealed_articles?: SessionArticle[];
  session_logs?: SessionLogSummary[];
}

export interface MessagePostResponse extends ApiResponseBase {
  message: SessionMessage;
}

export interface SessionStartCloseResponse extends ApiResponseBase {
  session: SessionRecord;
}

export interface SessionArticleCreateResponse extends ApiResponseBase {
  article: SessionArticle;
}

export interface SessionArticleUpdatePayload {
  title?: string;
  body_markdown?: string;
  image_alt_text?: string | null;
  image_caption?: string | null;
}

export interface SessionArticleUpdateResponse extends ApiResponseBase {
  article: SessionArticle;
}

export interface SessionArticleRevealResponse extends ApiResponseBase {
  article: SessionArticle;
  message: SessionMessage;
}

export interface SessionArticleSourcesResponse extends ApiResponseBase {
  results: SessionArticleSourceResult[];
  message: string;
}

export interface SessionArticleSourceResult {
  source_ref: string;
  source_kind: "page" | "systems" | string;
  title: string;
  subtitle: string;
  kind_label: string;
  select_label: string;
}

export interface SessionLogDetailResponse extends ApiResponseBase {
  session: SessionRecord;
  messages: SessionMessage[];
}

export interface SessionLogDeleteResponse extends ApiResponseBase {
  deleted_session_id: number;
}

export interface SessionClearRevealedResponse extends ApiResponseBase {
  deleted_article_ids: number[];
  deleted_articles: SessionArticle[];
}

export interface SessionWikiLookupSearchResult {
  page_ref: string;
  source_ref?: string;
  title: string;
  subtitle: string;
  select_label: string;
}

export interface SessionWikiLookupSearchResponse extends ApiResponseBase {
  results: SessionWikiLookupSearchResult[];
  message: string;
}

export interface SessionWikiLookupPreviewResponse extends ApiResponseBase {
  preview_html: string;
}

export interface CharacterSummary {
  slug: string;
  name: string;
  status: string;
  class_level_text: string;
  species: string;
  background: string;
  current_hp: number;
  max_hp: number;
  temp_hp: number;
  revision: number;
}

export interface CharacterPermissions {
  can_edit_session: boolean;
}

export interface CharacterStateRecord {
  campaign_slug: string;
  character_slug: string;
  revision: number;
  state: Record<string, unknown>;
  updated_at: string | null;
  updated_by_user_id: number | null;
}

export interface CharacterRecord {
  definition: Record<string, unknown>;
  import_metadata: Record<string, unknown>;
  state_record: CharacterStateRecord;
  permissions: CharacterPermissions;
}

export interface CharacterListResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  characters: CharacterSummary[];
}

export interface CharacterDetailResponse extends ApiResponseBase {
  character: CharacterRecord;
}

export interface CharacterVitalsPatchPayload {
  expected_revision: number;
  current_hp?: number | null;
  temp_hp?: number | null;
}

export interface CharacterNotesPatchPayload {
  expected_revision: number;
  player_notes_markdown: string;
}

export interface CharacterVitalsPatchResponse extends ApiResponseBase {
  character: CharacterRecord;
}

export interface CharacterNotesPatchResponse extends ApiResponseBase {
  character: CharacterRecord;
}

export interface SessionArticleCreatePayloadManual {
  mode: "manual";
  title: string;
  body_markdown: string;
  image?: {
    filename: string;
    data_base64: string;
    media_type?: string;
    alt_text?: string | null;
    caption?: string | null;
  } | null;
}

export interface SessionArticleCreatePayloadUpload {
  mode: "upload";
  filename: string;
  markdown_text: string;
  referenced_image?: {
    filename: string;
    data_base64: string;
    media_type?: string;
  } | null;
}

export interface SessionArticleCreatePayloadWiki {
  mode: "wiki";
  source_ref: string;
  page_ref?: string;
}

export type SessionArticleCreatePayload =
  | SessionArticleCreatePayloadManual
  | SessionArticleCreatePayloadUpload
  | SessionArticleCreatePayloadWiki;

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
