export interface AppMeta {
  version?: string;
  build_id?: string;
  git_sha?: string;
  runtime?: string;
}

export interface ApiResponseBase {
  ok: boolean;
}

export interface CampaignVisibilityScopeState {
  effective: string;
  can_access: boolean;
  configured?: string;
}

export interface CampaignVisibilityMap {
  [scope: string]: CampaignVisibilityScopeState;
}

export interface CampaignPermissions {
  can_manage_content?: boolean;
  can_manage_systems?: boolean;
  can_manage_combat?: boolean;
  can_manage_session?: boolean;
  can_manage_dm_content?: boolean;
  can_manage_visibility?: boolean;
  can_access_dm_content?: boolean;
  can_access_systems?: boolean;
  can_post_session_messages?: boolean;
  can_record_xianxia_dao_immolating_use?: boolean;
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
  visibility?: CampaignVisibilityMap;
  permissions?: CampaignPermissions;
}

export interface CampaignDetailResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  role: string;
  auth_source: string;
  visibility: CampaignVisibilityMap;
  permissions: CampaignPermissions;
}

export interface UserMembership {
  id: number;
  campaign_slug: string;
  role: string;
  status: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface UserProfile {
  id: number;
  email: string;
  display_name: string;
  is_admin: boolean;
  status: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface ViewAsUserChoice {
  id: number;
  email: string;
  display_name: string;
  is_admin: boolean;
  status: string;
}

export interface ViewAsState {
  can_view_as: boolean;
  active_user: ViewAsUserChoice | null;
  user_choices: ViewAsUserChoice[];
}

export interface UserPreferences {
  theme_key?: string | null;
  session_chat_order?: string | null;
  frontend_mode?: string | null;
}

export interface ThemePreset {
  key: string;
  label: string;
  description: string;
  preview_colors: string[];
}

export interface SessionChatOrderChoice {
  value: string;
  label: string;
  description: string;
}

export interface MeResponse extends ApiResponseBase {
  app: AppMeta;
  auth_source: string;
  user: UserProfile;
  memberships: UserMembership[];
  preferences?: UserPreferences;
  view_as?: ViewAsState;
}

export interface ViewAsUpdateResponse extends ApiResponseBase {
  view_as: ViewAsState;
}

export interface AccountSettingsResponse extends ApiResponseBase {
  user: UserProfile;
  preferences: UserPreferences;
  theme_presets: ThemePreset[];
  session_chat_order_choices: SessionChatOrderChoice[];
}

export interface AccountSettingsUpdatePayload {
  theme_key?: string;
  session_chat_order?: string;
}

export interface AccountSettingsUpdateResponse extends ApiResponseBase {
  user: UserProfile;
  preferences: UserPreferences;
}

export interface AdminCampaignChoice {
  slug: string;
  title: string;
}

export interface AdminCharacterChoice {
  campaign_slug: string;
  character_slug: string;
  label: string;
  value: string;
}

export interface AdminAuditEventTypeChoice {
  value: string;
  label: string;
}

export interface AdminActivityFilters {
  query: string;
  event_type: string;
  campaign_slug: string;
  page: number;
}

export interface AdminPagination {
  current_page: number;
  page_size: number;
  total_events: number;
  total_pages: number;
  has_previous: boolean;
  has_next: boolean;
  previous_url: string;
  next_url: string;
}

export interface AdminUserReference {
  label: string;
  meta: string;
  href: string;
  flask_href?: string;
}

export interface AdminAuditEvent {
  id: number;
  event_type: string;
  title: string;
  timestamp: string;
  actor: AdminUserReference | null;
  target: AdminUserReference | null;
  actor_email: string;
  target_email: string;
  campaign_slug: string;
  character_slug: string;
  scope: string;
  details: string;
}

export interface AdminUserCard {
  id: number;
  email: string;
  display_name: string;
  status: string;
  is_admin: boolean;
  href: string;
  flask_href: string;
  membership_summary: string[];
  assignment_summary: string[];
}

export interface AdminMembership {
  id: number;
  campaign_slug: string;
  campaign_title: string;
  role: string;
  status: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface AdminAssignment {
  id: number;
  user_id: number;
  campaign_slug: string;
  campaign_title: string;
  character_slug: string;
  character_label: string;
  assignment_type: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface AdminLinks {
  gen2_admin_url: string;
  flask_admin_url: string;
  gen2_user_url?: string;
  flask_user_url?: string;
}

export interface AdminDashboardResponse extends ApiResponseBase {
  admin_user: UserProfile | null;
  campaign_choices: AdminCampaignChoice[];
  invite_form_defaults: {
    user_type: string;
    campaign_slug: string;
  };
  audit_event_type_choices: AdminAuditEventTypeChoice[];
  user_cards: AdminUserCard[];
  activity_filters: AdminActivityFilters;
  pagination: AdminPagination;
  export_url: string;
  recent_audit_events: AdminAuditEvent[];
  links: AdminLinks;
  message?: string;
}

export interface AdminUserDetailResponse extends ApiResponseBase {
  managed_user: UserProfile;
  campaign_choices: AdminCampaignChoice[];
  character_choices: AdminCharacterChoice[];
  memberships: AdminMembership[];
  assignments: AdminAssignment[];
  audit_event_type_choices: AdminAuditEventTypeChoice[];
  membership_form_defaults: {
    campaign_slug: string;
    role: string;
    status: string;
  };
  assignment_form_defaults: {
    character_ref: string;
  };
  can_manage_account: boolean;
  activity_filters: AdminActivityFilters;
  pagination: AdminPagination;
  export_url: string;
  recent_audit_events: AdminAuditEvent[];
  links: AdminLinks;
  message?: string;
  invite_url?: string;
  reset_url?: string;
}

export interface AdminInvitePayload {
  email: string;
  display_name: string;
  user_type: string;
  campaign_slug?: string;
}

export interface AdminMembershipPayload {
  campaign_slug: string;
  role: string;
  status: string;
}

export interface AdminAssignmentPayload {
  character_ref?: string;
  campaign_slug?: string;
  character_slug?: string;
}

export interface AdminDeleteUserPayload {
  confirm_email: string;
}

export interface CampaignsResponse extends ApiResponseBase {
  campaigns: CampaignEntry[];
}

export interface ApiAppResponse extends ApiResponseBase {
  app: AppMeta;
}

export interface WikiImage {
  asset_ref: string;
  url: string;
  media_type: string;
  alt_text: string;
  caption: string;
}

export interface WikiPageSummary {
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
}

export interface WikiPageDetail extends WikiPageSummary {
  body_html: string;
  image: WikiImage | null;
}

export interface WikiSectionGroup {
  section_name: string;
  section_slug: string;
  href: string;
  page_count: number;
  pages: WikiPageSummary[];
}

export interface WikiSectionNavItem {
  section_name: string;
  section_slug: string;
  href: string;
  page_count: number;
}

export interface WikiSubsectionGroup {
  subsection_name: string;
  page_count: number;
  pages: WikiPageSummary[];
}

export interface WikiHomeLinks {
  flask_campaign_url: string;
  campaign_url?: string;
  gen2_campaign_url: string;
}

export interface CampaignControlVisibilityChoice {
  value: string;
  label: string;
}

export interface CampaignControlVisibilityRow {
  scope: string;
  label: string;
  selected_visibility: string;
  selected_visibility_label: string;
  configured_visibility: string;
  configured_visibility_label: string;
  default_visibility: string;
  default_visibility_label: string;
  effective_visibility: string;
  effective_visibility_label: string;
  choices: CampaignControlVisibilityChoice[];
  is_overridden_by_campaign: boolean;
}

export interface CampaignControlRule {
  label: string;
  description: string;
}

export interface CampaignControlResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  visibility_rows: CampaignControlVisibilityRow[];
  can_set_private_visibility: boolean;
  rules: CampaignControlRule[];
  notes: string[];
  links: {
    flask_control_url: string;
    gen2_control_url: string;
  };
}

export interface CampaignControlVisibilityUpdatePayload {
  visibility: Record<string, string>;
}

export interface CampaignControlVisibilityUpdateResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  visibility_rows: CampaignControlVisibilityRow[];
  changed_scopes: string[];
  message: string;
}

export interface CampaignHelpLink {
  label: string;
  href: string;
}

export interface CampaignHelpGuidanceCard {
  title: string;
  body: string;
  items: string[];
  meta: string;
}

export interface CampaignHelpSurface {
  anchor: string;
  label: string;
  summary: string;
  status_label: string;
  access_note: string;
  capabilities: string[];
  limits: string[];
  links: CampaignHelpLink[];
  guidance_cards: CampaignHelpGuidanceCard[];
}

export interface CampaignHelpVisibilityRow {
  label: string;
  visibility_label: string;
  viewer_can_open: boolean;
}

export interface CampaignHelpResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  viewer_role_label: string;
  viewer_role_summary: string;
  campaign_system_label: string;
  is_authenticated: boolean;
  available_surface_labels: string[];
  cross_cutting_limits: string[];
  visibility_rows: CampaignHelpVisibilityRow[];
  surfaces: CampaignHelpSurface[];
  account_note: string;
  links: {
    flask_help_url: string;
    gen2_help_url: string;
    account_url: string;
    flask_account_url: string;
    sign_in_url: string;
  };
}

export interface WikiHomeResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  frontend_mode?: string | null;
  can_view_wiki: boolean;
  wiki_visibility_label: string;
  query: string;
  result_count: number;
  grouped_sections: WikiSectionGroup[];
  section_navigation: WikiSectionNavItem[];
  overview_page: WikiPageDetail | null;
  latest_session_summary: WikiPageSummary | null;
  message: string;
  links: WikiHomeLinks;
}

export interface WikiSectionResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  frontend_mode?: string | null;
  section_name: string;
  section_slug: string;
  page_count: number;
  pages: WikiPageSummary[];
  top_level_pages: WikiPageSummary[];
  subsection_groups: WikiSubsectionGroup[];
  show_subsections: boolean;
  section_navigation: WikiSectionNavItem[];
  links: {
    flask_section_url: string;
    campaign_url?: string;
    gen2_campaign_url: string;
  };
}

export interface WikiPageResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  frontend_mode?: string | null;
  page: WikiPageDetail;
  backlinks: WikiPageSummary[];
  section_navigation: WikiSectionNavItem[];
  links: {
    flask_page_url: string;
    campaign_url?: string;
    section_url?: string;
    gen2_campaign_url: string;
    gen2_section_url: string;
  };
}

export interface SessionArticleImage {
  filename: string;
  media_type: string;
  alt_text: string | null;
  caption: string | null;
  updated_at: string | null;
  url: string;
}

export interface SessionArticleLinks {
  source_url?: string | null;
  published_page_url?: string | null;
  player_wiki_editor_url?: string | null;
  convert_url?: string | null;
}

export interface SessionArticleSourceMetadata {
  title?: string | null;
  label?: string | null;
  action_label?: string | null;
  missing_message?: string | null;
}

export interface SessionArticleConvertedPage {
  title?: string | null;
  is_visible?: boolean;
  reveal_after_session?: number | null;
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
  links?: SessionArticleLinks;
  source?: SessionArticleSourceMetadata;
  converted_page?: SessionArticleConvertedPage | null;
}

export interface SessionMessage {
  id: number;
  session_id: number;
  campaign_slug: string;
  message_type: string;
  body_text: string;
  author_user_id: number | null;
  author_display_name: string;
  recipient_scope?: string;
  recipient_user_id?: number | null;
  recipient_label?: string | null;
  article_id: number | null;
  created_at: string | null;
  article: SessionArticle | null;
}

export interface SessionMessageRecipientPlayerChoice {
  user_id: number;
  label: string;
}

export interface SessionMessagePostPayload {
  body: string;
  recipient_scope?: "global" | "dm_only" | "player";
  recipient_user_id?: number | null;
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

export interface SessionDmPassiveScoreRow {
  name: string;
  passive_perception: string;
  passive_insight: string;
  passive_investigation: string;
}

export interface SessionPermissions {
  can_manage_session: boolean;
  can_post_messages: boolean;
  can_access_wiki_lookup?: boolean;
}

export interface SessionPayload extends ApiResponseBase {
  session_revision: number;
  session_view_token: string;
  changed?: true;
  campaign: CampaignRecord;
  permissions: SessionPermissions;
  active_session: SessionRecord | null;
  messages: SessionMessage[];
  session_message_recipient_player_choices?: SessionMessageRecipientPlayerChoice[];
  staged_articles?: SessionArticle[];
  revealed_articles?: SessionArticle[];
  session_logs?: SessionLogSummary[];
  session_dm_passive_scores?: SessionDmPassiveScoreRow[];
  show_session_dm_passive_scores?: boolean;
}

export interface SessionUnchangedPayload extends ApiResponseBase {
  changed: false;
  session_revision: number;
  session_view_token: string;
}

export type SessionLiveStatePayload = SessionPayload | SessionUnchangedPayload;

export interface CombatCondition {
  id: number;
  name: string;
  duration_text: string;
}

export interface CombatNpcResourceCounter {
  resource_key: string;
  label: string;
  current_value: number;
  max_value: number;
  reset_label: string;
  source_label: string;
  can_edit: boolean;
}

export interface CombatNpcResourceNote {
  label: string;
  note: string;
  source_label: string;
}

export interface CombatantSummary {
  id: number;
  name: string;
  character_slug: string;
  source_kind: string;
  source_ref: string;
  source_label: string;
  type_label: string;
  subtitle: string;
  show_detail: boolean;
  player_detail_visible: boolean;
  turn_value: number;
  initiative_bonus_label: string;
  dexterity_modifier?: number | null;
  dexterity_modifier_label?: string;
  initiative_priority?: number;
  initiative_priority_label?: string;
  current_hp?: number | null;
  max_hp?: number | null;
  temp_hp?: number | null;
  hit_dice?: { value?: string; pools?: Array<Record<string, unknown>> } | null;
  movement_total?: number | null;
  movement_remaining?: number | null;
  speed_label?: string;
  has_action: boolean;
  has_bonus_action: boolean;
  has_reaction: boolean;
  is_current_turn: boolean;
  can_edit_vitals: boolean;
  can_edit_resources: boolean;
  can_open_character_page: boolean;
  can_open_status_page: boolean;
  can_toggle_player_detail_visibility: boolean;
  can_manage_combat: boolean;
  combatant_revision: number;
  state_revision?: number | null;
  npc_resource_counters: CombatNpcResourceCounter[];
  npc_resource_notes: CombatNpcResourceNote[];
  conditions: CombatCondition[];
}

export interface CombatTrackerPayload {
  round_number: number;
  current_turn_label: string;
  has_current_turn: boolean;
  combatant_count: number;
  combatants: CombatantSummary[];
}

export interface CombatPlayerCharacterTarget {
  combatant_id: number;
  character_slug: string;
  name: string;
  subtitle: string;
  is_selected: boolean;
  href: string;
  flask_href: string;
}

export interface CombatCharacterWorkspaceFeature {
  name: string;
  href: string;
  group_title: string;
  metadata: string[];
  description_html: string;
}

export interface CombatCharacterWorkspaceAttack {
  name: string;
  attack_bonus: string;
  damage: string;
  range: string;
  notes: string;
}

export interface CombatCharacterWorkspaceHiddenAttack {
  name: string;
  href: string;
}

export interface CombatCharacterWorkspaceFeatureGroup {
  title: string;
  features: CombatCharacterWorkspaceFeature[];
}

export interface CombatCharacterWorkspaceSection {
  slug: string;
  label: string;
  count: number;
  features?: CombatCharacterWorkspaceFeature[];
  attacks?: CombatCharacterWorkspaceAttack[];
  hidden_attacks?: CombatCharacterWorkspaceHiddenAttack[];
  feature_groups?: CombatCharacterWorkspaceFeatureGroup[];
  empty_message: string;
}

export interface CombatAvailableCharacterChoice {
  slug: string;
  name: string;
  subtitle: string;
  initiative_bonus: string;
}

export interface CombatAvailableStatblockChoice {
  id: string;
  title: string;
  subtitle: string;
  initiative_bonus: string;
}

export interface CombatSystemsMonsterSearchResult {
  entry_key: string;
  title: string;
  source_id: string;
  subtitle: string;
  initiative_bonus: string;
}

export interface CombatSystemsMonsterSearchResponse extends ApiResponseBase {
  results: CombatSystemsMonsterSearchResult[];
  message: string;
}

export interface CombatPayload extends ApiResponseBase {
  changed?: true;
  campaign: CampaignRecord;
  combat_system_supported: boolean;
  live_revision: number;
  live_view_token: string;
  tracker: CombatTrackerPayload;
  selected_combatant_id?: number | null;
  selected_combatant?: CombatantSummary | null;
  selected_player_character?: CombatantSummary | null;
  selected_player_combat_sections?: CombatCharacterWorkspaceSection[];
  player_character_targets: CombatPlayerCharacterTarget[];
  available_character_choices?: CombatAvailableCharacterChoice[];
  available_statblock_choices?: CombatAvailableStatblockChoice[];
  combat_condition_options?: string[];
  poll_settings?: {
    active_interval_ms?: number;
    idle_interval_ms?: number;
    idle_threshold_ms?: number;
  };
  links?: {
    flask_combat_url?: string;
    flask_campaign_url?: string;
    flask_characters_url?: string;
    flask_session_url?: string;
    flask_dm_status_url?: string;
    flask_dm_controls_url?: string;
    flask_status_url?: string;
  };
  permissions: CampaignPermissions;
}

export interface CombatUnchangedPayload extends ApiResponseBase {
  changed: false;
  live_revision: number;
  live_view_token: string;
}

export type CombatLiveStatePayload = CombatPayload | CombatUnchangedPayload;

export interface CombatAddPlayerPayload {
  character_slug: string;
  turn_value?: number | string | null;
  initiative_priority?: number | string | null;
}

export interface CombatAddNpcPayload {
  display_name: string;
  turn_value?: number | string | null;
  initiative_bonus?: number | string | null;
  dexterity_modifier?: number | string | null;
  initiative_priority?: number | string | null;
  current_hp?: number | string | null;
  max_hp?: number | string | null;
  temp_hp?: number | string | null;
  movement_total?: number | string | null;
}

export interface CombatAddStatblockPayload {
  statblock_id: number | string;
  display_name?: string;
  turn_value?: number | string | null;
  initiative_priority?: number | string | null;
}

export interface CombatAddSystemsMonsterPayload {
  entry_key: string;
  display_name?: string;
  turn_value?: number | string | null;
  initiative_priority?: number | string | null;
}

export interface CombatTurnPatchPayload {
  expected_combatant_revision?: number | string | null;
  turn_value?: number | string | null;
  initiative_priority?: number | string | null;
}

export interface CombatVitalsPatchPayload {
  expected_revision?: number | string | null;
  expected_combatant_revision?: number | string | null;
  current_hp?: number | string | null;
  max_hp?: number | string | null;
  temp_hp?: number | string | null;
  movement_total?: number | string | null;
}

export interface CombatResourcesPatchPayload {
  expected_combatant_revision?: number | string | null;
  has_action?: boolean;
  has_bonus_action?: boolean;
  has_reaction?: boolean;
  movement_remaining?: number | string | null;
}

export interface CombatNpcResourceCounterPatchPayload {
  resource_key: string;
  current_value: number | string | null;
}

export interface CombatNpcResourcesPatchPayload {
  expected_combatant_revision?: number | string | null;
  counters: CombatNpcResourceCounterPatchPayload[];
}

export interface CombatConditionAddPayload {
  name: string;
  duration_text?: string;
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
  image?: {
    filename: string;
    data_base64: string;
    media_type?: string;
    alt_text?: string | null;
    caption?: string | null;
  } | null;
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

export interface DmContentParserFeedback {
  armor_class: number | null;
  max_hp: number;
  speed_text: string;
  movement_total: number;
  initiative_bonus: number;
  summary: string;
}

export interface DmContentStatblock {
  id: number;
  campaign_slug: string;
  title: string;
  body_markdown: string;
  source_filename: string;
  subsection: string;
  armor_class: number | null;
  max_hp: number;
  speed_text: string;
  movement_total: number;
  initiative_bonus: number;
  parser_feedback: DmContentParserFeedback;
  created_at: string;
  updated_at: string;
  created_by_user_id: number | null;
  updated_by_user_id: number | null;
}

export interface DmContentConditionDefinition {
  id: number;
  campaign_slug: string;
  name: string;
  description_markdown: string;
  created_at: string;
  updated_at: string;
  created_by_user_id: number | null;
  updated_by_user_id: number | null;
}

export interface DmContentConditionCreatePayload {
  name: string;
  description_markdown: string;
}

export interface DmContentConditionUpdatePayload {
  name?: string;
  description_markdown?: string;
}

export interface DmContentConditionResponse extends ApiResponseBase {
  condition: DmContentConditionDefinition;
}

export interface DmContentSubpageCounts {
  statblocks: number;
  player_wiki: number;
  staged_articles: number;
  conditions: number;
  systems: number;
}

export interface ContentPageRemovalSafety {
  can_hard_delete: boolean;
  hard_delete_blockers: string[];
  removal_status_label: string;
  removal_guidance: string;
  page_title?: string;
}

export interface ContentPageRecord {
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
  is_visible?: boolean;
}

export type ContentPageMetadata = Record<string, unknown>;

export interface ContentPageFileSummary {
  page_ref: string;
  relative_path: string;
  updated_at: string | null;
  metadata: ContentPageMetadata;
  page: ContentPageRecord;
  removal_safety?: ContentPageRemovalSafety;
  can_hard_delete?: boolean;
  hard_delete_blockers?: string[];
  removal_status_label?: string;
  removal_guidance?: string;
}

export interface ContentPageFileRecord extends ContentPageFileSummary {
  body_markdown: string;
}

export interface ContentPageListResponse extends ApiResponseBase {
  pages: ContentPageFileSummary[];
}

export interface ContentPageDetailResponse extends ApiResponseBase {
  page_file: ContentPageFileRecord;
}

export interface ContentPageUpsertPayload {
  metadata: ContentPageMetadata;
  body_markdown: string;
}

export interface ContentPageDeleteResponse extends ApiResponseBase {
  deleted: {
    page_ref: string;
    relative_path: string;
  };
}

export interface ContentAssetFileSummary {
  asset_ref: string;
  relative_path: string;
  size_bytes: number;
  media_type: string;
  updated_at: string | null;
  url: string;
}

export interface ContentAssetUpsertPayload {
  asset_file: {
    filename: string;
    data_base64: string;
    media_type?: string;
  };
}

export interface ContentAssetResponse extends ApiResponseBase {
  asset_file: ContentAssetFileSummary;
}

export interface DmContentResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  permissions: CampaignPermissions;
  statblocks: DmContentStatblock[];
  conditions: DmContentConditionDefinition[];
  subpage_counts?: DmContentSubpageCounts;
}

export interface SystemsLibraryRecord {
  library_slug: string;
  title: string;
  system_code: string;
  status: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface SystemsVisibilityChoice {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SystemsSourceRow {
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
  selected_visibility?: string;
  is_configured: boolean;
  entry_count: number;
  choices?: SystemsVisibilityChoice[];
  permissions: {
    can_access: boolean;
    can_manage: boolean;
  };
}

export interface SystemsEntryOverride {
  entry_key: string;
  visibility_override: string | null;
  is_enabled_override: boolean | null;
  updated_at: string | null;
  updated_by_user_id: number | null;
}

export interface SystemsEntryOverrideRow extends SystemsEntryOverride {
  entry_title: string;
  entry_type: string;
  entry_type_label: string;
  entry_slug: string;
  entry_href: string;
  source_id: string;
  source_label: string;
  visibility_label: string;
  enablement_label: string;
}

export interface SystemsEntryTypeChoice {
  value: string;
  label: string;
}

export interface SystemsEntrySummary {
  id: number;
  library_slug: string;
  source_id: string;
  entry_key: string;
  entry_type: string;
  entry_type_label: string;
  slug: string;
  title: string;
  source_page: string | number | null;
  source_path: string;
  player_safe_default: boolean;
  dm_heavy: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface SystemsRulesReferenceResult {
  title: string;
  entry_type: string;
  entry_type_label: string;
  source_id: string;
  slug: string;
  reference_scope: string;
}

export interface SystemsSourceBrowseGroup {
  entry_type: string;
  entry_type_label: string;
  count: number;
}

export interface SystemsBrowseSourceRow extends SystemsSourceRow {
  has_rules_reference_entries?: boolean;
  rules_reference_search_scope?: string;
}

export interface SystemsIndexResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  library: SystemsLibraryRecord | null;
  query: string;
  reference_query: string;
  sources: SystemsBrowseSourceRow[];
  search_results: SystemsEntrySummary[];
  has_rules_reference_search: boolean;
  rules_reference_results: SystemsRulesReferenceResult[];
  source_scoped_rules_reference_sources: SystemsBrowseSourceRow[];
  permissions: {
    can_manage_systems: boolean;
  };
}

export interface SystemsSourceResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  source: SystemsSourceRow;
  entry_groups: SystemsSourceBrowseGroup[];
  book_entries: SystemsEntrySummary[];
  entry_count: number;
  browsable_entry_count: number;
  hidden_entry_types: string[];
  has_rules_reference_search: boolean;
  rules_reference_search_meta: string;
  rules_reference_scope_note: string;
  reference_query: string;
  rules_reference_results: SystemsRulesReferenceResult[];
  book_visibility_policy_note: string;
  permissions: {
    can_manage_systems: boolean;
  };
}

export interface SystemsSourceCategoryResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  source: SystemsSourceRow;
  entry_groups: SystemsSourceBrowseGroup[];
  entry_type: string;
  entry_type_label: string;
  query: string;
  entry_count: number;
  filtered_entry_count: number;
  entries: SystemsEntrySummary[];
  permissions: {
    can_manage_systems: boolean;
  };
}

export interface SystemsEntryRecord extends SystemsEntrySummary {
  metadata: Record<string, unknown>;
  body: Record<string, unknown>;
  rendered_html: string;
  source_state: SystemsSourceRow | null;
  override: SystemsEntryOverride | null;
}

export interface SystemsEntryResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  entry: SystemsEntryRecord;
  permissions: {
    can_manage_systems: boolean;
  };
  links: {
    flask_entry_url: string;
    flask_source_url: string;
    flask_source_category_url: string;
    dm_content_systems_url?: string;
  };
}

export interface CustomSystemsEntry {
  id: number;
  library_slug: string;
  source_id: string;
  entry_key: string;
  entry_type: string;
  entry_type_label: string;
  slug: string;
  title: string;
  source_page: string;
  source_path: string;
  player_safe_default: boolean;
  dm_heavy: boolean;
  created_at: string | null;
  updated_at: string | null;
  visibility: string;
  visibility_label: string;
  status_label: string;
  is_archived: boolean;
  provenance: string;
  search_metadata: string;
  body_markdown: string;
  linked_published_page_ref?: string;
  source_page_ref?: string;
  item_mechanics?: CampaignItemMechanicsReview | null;
  rendered_html: string;
  href: string;
  override: SystemsEntryOverride | null;
}

export interface CampaignItemMechanicsReview {
  version: string;
  review_status: string;
  support_state: string;
  modeled_fields: string[];
  flags: Array<Record<string, string>>;
  field_provenance: Record<string, unknown>;
  source_page_ref?: string;
  intake_mode?: string;
}

export interface CampaignItemPageRow {
  page_ref: string;
  title: string;
  source_ref: string;
  route_slug: string;
  has_structured_item: boolean;
  entry_slug: string;
  entry_title: string;
  item_mechanics?: CampaignItemMechanicsReview | null;
}

export interface CustomSystemsSourceRow {
  source_id: string;
  title: string;
  is_enabled: boolean;
  default_visibility: string;
  default_visibility_label: string;
  entry_count: number;
  active_entry_count: number;
  archived_entry_count: number;
  entries: CustomSystemsEntry[];
}

export interface SystemsImportRunReview {
  id: number;
  library_slug: string;
  source_id: string;
  status: string;
  import_version: string;
  imported_count: number | null;
  type_summary: Array<{
    entry_type: string;
    entry_type_label: string;
    count: number;
  }>;
  source_files: string[];
  source_file_count: number | null;
  error: string;
  started_at: string | null;
  completed_at: string | null;
  started_by_user_id: number | null;
}

export interface DmContentSystemsResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  library: SystemsLibraryRecord | null;
  systems_library: string;
  systems_scope_visibility_label: string;
  policy: {
    allow_dm_shared_core_entry_edits: boolean;
    proprietary_acknowledged: boolean;
  };
  source_rows: SystemsSourceRow[];
  source_count: number;
  has_proprietary_sources: boolean;
  entry_override_rows: SystemsEntryOverrideRow[];
  entry_override_count: number;
  campaign_item_page_rows: CampaignItemPageRow[];
  custom_entry_source_rows: CustomSystemsSourceRow[];
  custom_entry_count: number;
  custom_entry_default_visibility: string;
  custom_entry_type_choices: SystemsEntryTypeChoice[];
  custom_entry_visibility_choices: SystemsVisibilityChoice[];
  import_source_choices: Array<{
    source_id: string;
    title: string;
    license_class_label: string;
    entry_count: number;
  }>;
  import_entry_type_choices: SystemsEntryTypeChoice[];
  import_run_rows: SystemsImportRunReview[];
  import_run_count: number;
  supports_dnd5e_import: boolean;
  permissions: {
    can_manage_systems: boolean;
    can_import_shared_systems: boolean;
    can_set_private_visibility: boolean;
    can_manage_shared_core_entry_edit_permission: boolean;
  };
  links: {
    flask_systems_lane_url: string;
    flask_systems_control_url: string;
  };
}

export interface SystemsSourceUpdatePayload {
  updates: Array<{
    source_id: string;
    is_enabled: boolean;
    default_visibility: string;
  }>;
  acknowledge_proprietary?: boolean;
}

export interface SystemsSourceUpdateResponse extends ApiResponseBase {
  sources: SystemsSourceRow[];
}

export interface SystemsEntryOverridePayload {
  visibility_override?: string | null;
  is_enabled_override?: boolean | null;
}

export interface SystemsEntryOverrideResponse extends ApiResponseBase {
  override: SystemsEntryOverride;
  entry: unknown;
}

export interface CustomSystemsEntryPayload {
  title: string;
  slug_leaf?: string;
  entry_type: string;
  visibility: string;
  provenance: string;
  search_metadata: string;
  body_markdown: string;
  source_page_ref?: string;
  item_mechanics_review_status?: string;
  item_mechanics?: Record<string, unknown>;
}

export interface CampaignItemMechanicsImportPayload {
  page_ref: string;
  visibility?: string;
  item_mechanics_review_status?: string;
  item_mechanics?: Record<string, unknown>;
}

export interface CustomSystemsEntryResponse extends ApiResponseBase {
  entry: CustomSystemsEntry;
  systems: DmContentSystemsResponse;
}

export interface DmContentStatblockCreatePayload {
  filename: string;
  subsection?: string;
  markdown_text: string;
}

export interface DmContentStatblockUpdatePayload {
  subsection?: string;
  markdown_text?: string;
  body_markdown?: string;
}

export interface DmContentStatblockResponse extends ApiResponseBase {
  statblock: DmContentStatblock;
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

export interface CampaignReferenceSearchResult {
  result_id: string;
  kind: string;
  kind_label: string;
  title: string;
  subtitle: string;
  select_label: string;
}

export interface CampaignReferenceSearchResponse extends ApiResponseBase {
  results: CampaignReferenceSearchResult[];
  message: string;
}

export interface CampaignReferencePreviewResponse extends ApiResponseBase {
  preview_html: string;
}

export interface CharacterSummary {
  slug: string;
  name: string;
  status: string;
  class_level_text: string;
  species: string;
  background: string;
  system?: string;
  href?: string;
  flask_href?: string;
  search_text?: string;
  current_hp: number;
  max_hp: number;
  temp_hp: number;
  hit_dice?: {
    value?: string;
    pools?: Array<Record<string, unknown>>;
  };
  resource_preview?: Array<{
    label: string;
    value: string;
  }>;
  portrait?: CharacterPortrait | null;
  revision: number;
}

export interface CharacterPortrait {
  asset_ref: string;
  url: string;
  media_type?: string;
  alt_text: string;
  caption?: string;
}

export interface CharacterPermissions {
  can_edit_session: boolean;
  can_manage_session?: boolean;
  can_use_controls?: boolean;
  can_record_xianxia_dao_immolating_use?: boolean;
}

export interface CharacterControlsAssignment {
  user_id: number;
  assignment_type: string;
  display_name: string;
  email?: string | null;
  admin_href?: string | null;
}

export interface CharacterControlsPlayerChoice {
  user_id: number;
  label: string;
  is_current: boolean;
}

export interface CharacterControls {
  available: boolean;
  assignment?: CharacterControlsAssignment | null;
  can_assign_owner: boolean;
  can_delete_character: boolean;
  current_user_is_owner: boolean;
  player_choices: CharacterControlsPlayerChoice[];
  links?: {
    flask_controls_url?: string;
    gen2_roster_url?: string;
  };
}

export interface CharacterEquipmentWieldOption {
  value: string;
  label: string;
}

export interface CharacterEquipmentRow {
  id: string;
  name: string;
  quantity: number;
  weight: string;
  notes: string;
  tags: string[];
  href: string;
  description_html: string;
  source_label: string;
  is_equipped: boolean;
  equipped_label: string;
  is_attuned: boolean;
  requires_attunement: boolean;
  supports_attunement: boolean;
  supports_weapon_wield_mode: boolean;
  weapon_wield_mode: string;
  weapon_wield_options: CharacterEquipmentWieldOption[];
  attunement_hint: string;
}

export interface CharacterArcaneArmorState {
  available: boolean;
  feature_key?: string;
  label?: string;
  enabled?: boolean;
  status_label?: string;
  hands_free?: boolean;
  hands_label?: string;
  thunder_gauntlets_available?: boolean;
  defensive_field_available?: boolean;
}

export interface CharacterArtificerInfusionTargetOption {
  value: string;
  label: string;
}

export interface CharacterArtificerKnownInfusion {
  infusion_key: string;
  name: string;
  source_feature_id?: string;
  effect_key?: string;
  supported_effect: boolean;
  automation_status: string;
  effect_summary: string;
  selected_target_item_ref: string;
  target_options: CharacterArtificerInfusionTargetOption[];
}

export interface CharacterArtificerActiveInfusion {
  infusion_key: string;
  name: string;
  target_item_ref: string;
  target_item_name: string;
  supported_effect: boolean;
  automation_status: string;
  effect_summary: string;
}

export interface CharacterArtificerInfusionsState {
  available: boolean;
  artificer_level: number;
  known_capacity: number;
  known_count: number;
  active_capacity: number;
  active_count: number;
  known: CharacterArtificerKnownInfusion[];
  active: CharacterArtificerActiveInfusion[];
}

export interface CharacterEquipmentState {
  rows: CharacterEquipmentRow[];
  attuned_count: number;
  equipped_count: number;
  max_attuned_items: number;
  equipment_item_refs: string[];
  attunable_item_refs: string[];
  at_attunement_limit: boolean;
  over_attunement_limit: boolean;
  arcane_armor_state: CharacterArcaneArmorState;
  artificer_infusions_state?: CharacterArtificerInfusionsState;
}

export interface CharacterPresentedSpell {
  name: string;
  href: string;
  description_html: string;
  level_label: string;
  school: string;
  casting_time: string;
  range: string;
  duration: string;
  components: string;
  save_or_hit: string;
  source: string;
  reference: string;
  at_higher_levels?: string;
  badges: string[];
  class_row_id: string;
  management_note: string;
}

export interface CharacterPresentedSpellSection {
  class_row_id: string;
  title: string;
  spells: CharacterPresentedSpell[];
  spell_level_sections?: Array<{
    title: string;
    groups: Array<{
      title?: string;
      spells: CharacterPresentedSpell[];
    }>;
  }>;
}

export interface CharacterPresentedSpellcasting {
  spellcasting_class: string;
  spellcasting_ability: string;
  spell_save_dc: number | string | null;
  spell_attack_bonus: string;
  current_row_sections: CharacterPresentedSpellSection[];
  row_sections: CharacterPresentedSpellSection[];
}

export interface CharacterPresentedInventoryItem {
  id: string;
  item_ref: string;
  name: string;
  href: string;
  description_html: string;
  quantity: number;
  weight: string;
  notes: string;
  tags: string[];
}

export interface CharacterAbilitySkill {
  name: string;
  bonus: string;
  proficiency_label?: string;
  is_proficient?: boolean;
  ability_key?: string;
}

export interface CharacterAbility {
  key: string;
  abbr: string;
  name: string;
  score: number;
  modifier: string;
  save_bonus: string;
  skills?: CharacterAbilitySkill[];
}

export interface CharacterProficiencyGroup {
  title: string;
  values_list: string[];
}

export interface CharacterReferenceSection {
  title?: string;
  html?: string;
}

export interface CharacterXianxiaNamedRecord {
  name: string;
  href?: string;
  body_html?: string;
  description_html?: string;
  current_rank_label?: string;
  source_label?: string;
  rank_progress_label?: string;
  notes?: string;
  status?: string;
  status_key?: string;
  status_label?: string;
  type?: string;
  type_label?: string;
  reason?: string;
  approval_timestamp?: string;
  insight_cost?: number;
  insight_spent?: number;
  one_use?: boolean;
  one_use_status?: string;
  one_use_status_label?: string;
  used?: boolean;
  use_notes?: string;
  prepared_record_name?: string;
  prepared_record_notes?: string;
  prepared_record_index?: number;
  use_record_index?: number;
  base_ability_ref?: string;
  base_ability_kind?: string;
  technique_anchor_label?: string;
  technique_anchor_warning?: string;
}

export interface CharacterXianxiaPool {
  key: string;
  label: string;
  current: number;
  max: number;
  temp?: number;
}

export interface CharacterXianxiaInventoryItem {
  id: string;
  name: string;
  quantity: number;
  item_nature: string;
  item_type: string;
  notes: string;
  tags: string[];
  catalog_ref?: string;
  equippable: boolean;
  is_equipped: boolean;
  systems_ref?: Record<string, unknown> | null;
}

export interface CharacterOverviewStat {
  label: string;
  value: string;
}

export type CharacterOverviewStatRows = CharacterOverviewStat[][];

export interface CharacterPresentedXianxia {
  system_label?: string;
  subpages?: Array<{ slug: string; label: string }>;
  identity?: Record<string, unknown>;
  attributes?: Array<{ key: string; label: string; score: number }>;
  efforts?: Array<{ key: string; label: string; score: number; damage?: string }>;
  resources?: {
    durability?: CharacterXianxiaPool[];
    energies?: CharacterXianxiaPool[];
    yin_yang?: CharacterXianxiaPool[];
    dao?: { current: number; max: number };
    insight?: { available: number; spent: number };
  };
  skills?: {
    trained?: Array<{ name: string }>;
  };
  equipment?: {
    manual_armor_bonus?: number;
    defense?: number;
    equipped_items?: CharacterXianxiaInventoryItem[];
    equipped_weapons?: CharacterXianxiaInventoryItem[];
    equipped_armor?: CharacterXianxiaInventoryItem[];
    equipped_artifacts?: CharacterXianxiaInventoryItem[];
    necessary_weapons?: CharacterXianxiaNamedRecord[];
    necessary_tools?: CharacterXianxiaNamedRecord[];
  };
  martial_arts?: CharacterXianxiaNamedRecord[];
  generic_techniques?: CharacterXianxiaNamedRecord[];
  basic_actions?: CharacterXianxiaNamedRecord[];
  inventory?: {
    enabled?: boolean;
    currency?: Array<{ key: string; label: string; amount: number; description?: string }>;
    quantities?: CharacterXianxiaInventoryItem[];
  };
  approval?: {
    variants?: CharacterXianxiaNamedRecord[];
    dao_immolating_prepared?: CharacterXianxiaNamedRecord[];
    dao_immolating_use_history?: CharacterXianxiaNamedRecord[];
    approval_requests?: CharacterXianxiaNamedRecord[];
    status_groups?: Array<{
      key: string;
      title: string;
      empty_message: string;
      records: CharacterXianxiaNamedRecord[];
    }>;
  };
  active_state?: {
    stance?: { label?: string; name?: string; status_label?: string };
    aura?: { label?: string; name?: string; status_label?: string };
  };
  quick_reference?: Record<string, unknown>;
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
  overview_stat_rows?: CharacterOverviewStatRows;
  overview_stats?: CharacterOverviewStat[];
  player_notes_markdown?: string;
  player_notes_html?: string;
  reference_sections?: CharacterReferenceSection[];
  physical_description_markdown?: string;
  physical_description_html?: string;
  personal_background_markdown?: string;
  personal_background_html?: string;
  equipment_state?: CharacterEquipmentState;
  arcane_armor_state?: CharacterArcaneArmorState;
  presented_spellcasting?: CharacterPresentedSpellcasting;
  presented_inventory?: CharacterPresentedInventoryItem[];
  abilities?: CharacterAbility[];
  skills?: CharacterAbilitySkill[];
  proficiency_groups?: CharacterProficiencyGroup[];
  presented_xianxia?: CharacterPresentedXianxia;
  portrait?: CharacterPortrait | null;
  controls?: CharacterControls | null;
  permissions: CharacterPermissions;
}

export interface CharacterListResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  characters: CharacterSummary[];
  query?: string;
  result_count?: number;
  tools?: {
    can_create_characters?: boolean;
    can_import_xianxia_characters?: boolean;
    native_character_tools_supported?: boolean;
    native_character_create_supported?: boolean;
    character_create_lane?: string;
  };
  links?: {
    flask_roster_url?: string;
    gen2_roster_url?: string;
    flask_create_character_url?: string;
    create_character_url?: string;
    flask_import_xianxia_url?: string;
    import_xianxia_url?: string;
  };
}

export interface CharacterAuthoringLinks {
  flask_roster_url?: string;
  gen2_roster_url?: string;
  flask_create_character_url?: string;
  create_character_url?: string;
  flask_import_xianxia_url?: string;
  import_xianxia_url?: string;
  flask_create_url?: string;
  gen2_create_url?: string;
  gen2_import_xianxia_url?: string;
  character_url?: string;
  flask_character_url?: string;
}

export interface CharacterBuilderOption {
  key?: string;
  value?: string;
  slug?: string;
  label?: string;
  title?: string;
  source_id?: string;
  entry_key?: string;
  name?: string;
  insight_cost?: number;
  selected?: boolean;
  available_rank_labels?: string[];
  martial_art_style?: string;
}

export interface CharacterDndChoiceField {
  name: string;
  label: string;
  selected?: string;
  help_text?: string;
  options: CharacterBuilderOption[];
}

export interface CharacterDndChoiceSection {
  title: string;
  fields: CharacterDndChoiceField[];
}

export interface CharacterDndCreateContext {
  lane: "dnd5e";
  builder_ready: boolean;
  values: Record<string, string>;
  class_options: CharacterBuilderOption[];
  species_options: CharacterBuilderOption[];
  background_options: CharacterBuilderOption[];
  subclass_options: CharacterBuilderOption[];
  requires_subclass: boolean;
  choice_sections: CharacterDndChoiceSection[];
  preview: Record<string, unknown>;
  limitations: string[];
}

export interface CharacterXianxiaField {
  key?: string;
  label: string;
  input_name: string;
  value: string;
  max?: number;
  min?: number;
}

export interface CharacterXianxiaMartialArtField {
  index: number;
  art_input_name: string;
  rank_input_name: string;
  selected_slug: string;
  selected_rank: string;
}

export interface CharacterXianxiaCreateContext {
  lane: "xianxia";
  values: Record<string, unknown>;
  attribute_fields: CharacterXianxiaField[];
  effort_fields: CharacterXianxiaField[];
  energy_fields: CharacterXianxiaField[];
  trained_skill_fields: CharacterXianxiaField[];
  martial_art_fields: CharacterXianxiaMartialArtField[];
  martial_art_options: CharacterBuilderOption[];
  martial_art_rank_choices: CharacterBuilderOption[];
  manual_armor_field: CharacterXianxiaField;
  dao_field: CharacterXianxiaField;
  generic_technique_options: CharacterBuilderOption[];
  gm_granted_generic_technique_input: string;
  defaults: Record<string, unknown>;
}

export interface CharacterCreateContextResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  lane: string;
  tools?: CharacterListResponse["tools"];
  links: CharacterAuthoringLinks;
  create: CharacterDndCreateContext | CharacterXianxiaCreateContext | Record<string, unknown>;
}

export interface CharacterCreateSubmitPayload {
  values: Record<string, string | string[]>;
}

export interface CharacterCreateSubmitResponse extends ApiResponseBase {
  message: string;
  character: CharacterRecord;
  links: CharacterAuthoringLinks;
}

export interface CharacterXianxiaManualImportRow {
  index: number;
  slug_input_name: string;
  name_input_name: string;
  rank_input_name: string;
  teacher_input_name: string;
  breakthrough_input_name: string;
  notes_input_name: string;
  selected_slug: string;
  name: string;
  rank: string;
  teacher: string;
  breakthrough: string;
  notes: string;
}

export interface CharacterXianxiaManualImportContext {
  values: Record<string, string>;
  realm_choices: string[];
  honor_choices: string[];
  martial_art_rank_choices: string[];
  martial_art_rows: CharacterXianxiaManualImportRow[];
  attribute_fields: CharacterXianxiaField[];
  effort_fields: CharacterXianxiaField[];
  energy_fields: Array<{
    key: string;
    label: string;
    max_input_name: string;
    max_value: string;
  }>;
  martial_art_options: CharacterBuilderOption[];
  preview?: Record<string, unknown> | null;
}

export interface CharacterXianxiaManualImportResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  lane: "xianxia";
  links: CharacterAuthoringLinks;
  import_context: CharacterXianxiaManualImportContext;
  message?: string;
}

export interface CharacterXianxiaManualImportPayload {
  values: Record<string, string>;
  confirm_import?: boolean;
}

export interface CharacterEditorField {
  name: string;
  label: string;
  value?: string;
  help_text?: string;
}

export interface CharacterEditorChoiceField {
  name: string;
  label: string;
  selected?: string;
  help_text?: string;
  options: CharacterBuilderOption[];
}

export interface CharacterEditorRecoverablePenaltyRow {
  index: number;
  id?: string;
  source?: string;
  target?: string;
  amount?: string;
  notes?: string;
}

export interface CharacterEditorFeatureRow {
  index: number;
  id?: string;
  name?: string;
  page_ref?: string;
  activation_type?: string;
  summary?: string;
  description_markdown?: string;
  resource_max?: string;
  resource_reset_on?: string;
  choice_fields?: CharacterEditorChoiceField[];
}

export interface CharacterEditorEquipmentRow {
  index: number;
  id?: string;
  name?: string;
  page_ref?: string;
  quantity?: string;
  weight?: string;
  notes?: string;
}

export interface CharacterEditorManagedEquipmentRow {
  name: string;
  quantity?: number;
  weight?: string;
}

export interface CharacterAdvancedEditorContext {
  state_revision: number;
  values?: Record<string, string>;
  proficiency_fields: CharacterEditorField[];
  reference_fields: CharacterEditorField[];
  stat_adjustment_fields: CharacterEditorField[];
  recoverable_penalty_rows: CharacterEditorRecoverablePenaltyRow[];
  feature_rows: CharacterEditorFeatureRow[];
  equipment_rows: CharacterEditorEquipmentRow[];
  activation_options: CharacterBuilderOption[];
  resource_reset_options: CharacterBuilderOption[];
  recoverable_penalty_target_options: CharacterBuilderOption[];
  campaign_page_options: CharacterBuilderOption[];
  equipment_page_options: CharacterBuilderOption[];
  linked_feature_authoring_supported: boolean;
  linked_feature_authoring_message?: string;
  existing_managed_equipment?: CharacterEditorManagedEquipmentRow[];
}

export interface CharacterAdvancedEditorResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  character: CharacterRecord;
  lane: "dnd5e" | "unsupported";
  supported: boolean;
  message?: string | null;
  unsupported_message?: string;
  editor?: CharacterAdvancedEditorContext | null;
  links: {
    character_url?: string;
    flask_character_url?: string;
    advanced_editor_url?: string;
    flask_advanced_editor_url?: string;
    retraining_url?: string;
    flask_retraining_url?: string;
    cultivation_url?: string;
    flask_cultivation_url?: string;
    level_up_url?: string;
    flask_level_up_url?: string;
    progression_repair_url?: string;
    flask_progression_repair_url?: string;
  };
}

export interface CharacterAdvancedEditorPayload {
  expected_revision: number;
  values: Record<string, string>;
}

export interface CharacterRetrainingContext {
  state_revision: number;
  values?: Record<string, string>;
  feature_rows: CharacterEditorFeatureRow[];
  supported_scope: string[];
}

export interface CharacterRetrainingResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  character: CharacterRecord;
  lane: "dnd5e" | "repairable" | "unsupported";
  supported: boolean;
  message?: string | null;
  unsupported_message?: string;
  readiness?: Record<string, unknown>;
  retraining?: CharacterRetrainingContext | null;
  links: {
    character_url?: string;
    flask_character_url?: string;
    advanced_editor_url?: string;
    flask_advanced_editor_url?: string;
    retraining_url?: string;
    flask_retraining_url?: string;
    progression_repair_url?: string;
    flask_progression_repair_url?: string;
    cultivation_url?: string;
    flask_cultivation_url?: string;
  };
}

export interface CharacterRetrainingPayload {
  expected_revision: number;
  values: Record<string, string>;
}

export interface CharacterLevelUpContext {
  state_revision: number;
  values?: Record<string, string>;
  character_name?: string;
  current_level: number;
  next_level: number;
  advancement_mode?: string;
  mode_options: CharacterBuilderOption[];
  can_add_class?: boolean;
  current_class_rows: string[];
  target_row_options: CharacterBuilderOption[];
  target_class_row_id?: string;
  row_current_level?: number;
  row_target_level?: number;
  new_class_options: CharacterBuilderOption[];
  new_subclass_options: CharacterBuilderOption[];
  multiclass_requirement_text?: string;
  multiclass_requirements_met?: boolean;
  subclass_options: CharacterBuilderOption[];
  requires_subclass?: boolean;
  choice_sections: CharacterDndChoiceSection[];
  limitations: string[];
  preview: Record<string, unknown>;
  field_live_preview?: Record<string, unknown>;
  preview_region_ids?: string[];
  live_region_ids?: string[];
}

export interface CharacterLevelUpResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  character: CharacterRecord;
  lane: "dnd5e" | "ready" | "repairable" | "unsupported";
  supported: boolean;
  message?: string | null;
  unsupported_message?: string;
  readiness?: Record<string, unknown>;
  level_up?: CharacterLevelUpContext | null;
  links: {
    character_url?: string;
    flask_character_url?: string;
    advanced_editor_url?: string;
    flask_advanced_editor_url?: string;
    retraining_url?: string;
    flask_retraining_url?: string;
    level_up_url?: string;
    flask_level_up_url?: string;
    progression_repair_url?: string;
    flask_progression_repair_url?: string;
    cultivation_url?: string;
    flask_cultivation_url?: string;
  };
}

export interface CharacterLevelUpPayload {
  expected_revision: number;
  values: Record<string, string>;
}

export interface CharacterProgressionRepairClassRow {
  row_id?: string;
  row_level?: number;
  class_name?: string;
  class_field_name: string;
  class_selected?: string;
  class_options: CharacterBuilderOption[];
  subclass_field_name: string;
  subclass_selected?: string;
  subclass_options: CharacterBuilderOption[];
}

export interface CharacterProgressionRepairChoiceRow {
  index?: number;
  name: string;
  selected?: string;
  options: CharacterBuilderOption[];
}

export interface CharacterProgressionRepairSpellRow {
  name?: string;
  field_name: string;
  selected?: string;
  options: CharacterBuilderOption[];
  class_row_field_name?: string;
  class_row_selected?: string;
  class_row_options?: CharacterBuilderOption[];
}

export interface CharacterProgressionRepairContext {
  state_revision: number;
  values?: Record<string, string>;
  character_name?: string;
  current_level?: number;
  readiness?: {
    message?: string;
    reasons?: string[];
    [key: string]: unknown;
  };
  class_rows: CharacterProgressionRepairClassRow[];
  species_options: CharacterBuilderOption[];
  background_options: CharacterBuilderOption[];
  feat_rows: CharacterProgressionRepairChoiceRow[];
  optionalfeature_rows: CharacterProgressionRepairChoiceRow[];
  spell_rows: CharacterProgressionRepairSpellRow[];
}

export interface CharacterProgressionRepairResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  character: CharacterRecord;
  lane: "repairable" | "ready" | "unsupported";
  supported: boolean;
  message?: string | null;
  unsupported_message?: string;
  readiness?: Record<string, unknown>;
  repair?: CharacterProgressionRepairContext | null;
  links: {
    character_url?: string;
    flask_character_url?: string;
    advanced_editor_url?: string;
    flask_advanced_editor_url?: string;
    retraining_url?: string;
    flask_retraining_url?: string;
    level_up_url?: string;
    flask_level_up_url?: string;
    progression_repair_url?: string;
    flask_progression_repair_url?: string;
    cultivation_url?: string;
    flask_cultivation_url?: string;
  };
}

export interface CharacterProgressionRepairPayload {
  expected_revision: number;
  values: Record<string, string>;
}

export interface CharacterCultivationStatRow {
  key?: string;
  label?: string;
  score?: number;
  current?: number;
  max?: number;
  cap?: number;
  insight_cost?: number;
  shortfall?: number;
  has_enough_insight?: boolean;
  can_increase?: boolean;
  [key: string]: unknown;
}

export interface CharacterCultivationContext {
  insight: {
    available: number;
    spent: number;
  };
  energies: CharacterCultivationStatRow[];
  yin_yang: CharacterCultivationStatRow[];
  conditioning: {
    hp: CharacterCultivationStatRow;
    efforts: CharacterCultivationStatRow[];
  };
  training: {
    stance: CharacterCultivationStatRow;
    attributes: CharacterCultivationStatRow[];
  };
  martial_arts: Array<Record<string, unknown>>;
  generic_techniques: Array<Record<string, unknown>>;
  generic_technique_options: Array<Record<string, unknown>>;
  realm_ascension: Record<string, unknown>;
  history: Array<{
    index: number;
    action: string;
    details?: Array<{ label: string; value: string }>;
  }>;
}

export interface CharacterCultivationResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  character: CharacterRecord;
  lane: "xianxia" | "unsupported";
  supported: boolean;
  message?: string | null;
  anchor?: string | null;
  unsupported_message?: string;
  cultivation?: CharacterCultivationContext | null;
  links: {
    character_url?: string;
    flask_character_url?: string;
    advanced_editor_url?: string;
    flask_advanced_editor_url?: string;
    retraining_url?: string;
    flask_retraining_url?: string;
    progression_repair_url?: string;
    flask_progression_repair_url?: string;
    cultivation_url?: string;
    flask_cultivation_url?: string;
  };
}

export interface CharacterCultivationActionPayload {
  expected_revision: number;
  action: string;
  values?: Record<string, string>;
}

export interface CharacterDetailResponse extends ApiResponseBase {
  character: CharacterRecord;
  links?: {
    flask_roster_url?: string;
    flask_character_url?: string;
    advanced_editor_url?: string;
    flask_advanced_editor_url?: string;
    retraining_url?: string;
    flask_retraining_url?: string;
    level_up_url?: string;
    flask_level_up_url?: string;
    progression_repair_url?: string;
    flask_progression_repair_url?: string;
    cultivation_url?: string;
    flask_cultivation_url?: string;
  };
}

export interface CharacterVitalsPatchPayload {
  expected_revision: number;
  current_hp?: number | null;
  temp_hp?: number | null;
  current_stance?: number | null;
  temp_stance?: number | null;
  current_jing?: number | null;
  current_qi?: number | null;
  current_shen?: number | null;
  current_yin?: number | null;
  current_yang?: number | null;
  current_dao?: number | null;
}

export interface CharacterResourcePatchPayload {
  expected_revision: number;
  current?: number | null;
}

export interface CharacterSpellSlotsPatchPayload {
  expected_revision: number;
  slot_lane_id?: string;
  used?: number | null;
}

export interface CharacterInventoryPatchPayload {
  expected_revision: number;
  quantity?: number | null;
}

export interface CharacterEquipmentStatePatchPayload {
  expected_revision: number;
  is_equipped?: boolean;
  is_attuned?: boolean;
  weapon_wield_mode?: string;
}

export interface CharacterFeatureStatePatchPayload {
  expected_revision: number;
  enabled: boolean;
}

export interface CharacterArtificerInfusionsPatchPayload {
  expected_revision: number;
  active: Array<{
    infusion_key: string;
    target_item_ref: string;
  }>;
}

export interface CharacterCurrencyPatchPayload {
  expected_revision: number;
  cp?: number | null;
  sp?: number | null;
  ep?: number | null;
  gp?: number | null;
  pp?: number | null;
  coin?: number | null;
  supply?: number | null;
  spirit_stones?: number | null;
}

export interface CharacterXianxiaActiveStatePatchPayload {
  expected_revision: number;
  active_stance_name?: string;
  active_aura_name?: string;
}

export interface CharacterXianxiaInventoryItemPayload {
  id?: string;
  name: string;
  quantity?: number | null;
  item_nature?: string;
  item_type?: string;
  notes?: string;
  tags?: string[];
  catalog_ref?: string;
  systems_ref?: Record<string, unknown> | null;
  equippable?: boolean;
  is_equipped?: boolean;
}

export interface CharacterXianxiaInventoryAddPayload {
  expected_revision: number;
  item: CharacterXianxiaInventoryItemPayload;
}

export interface CharacterXianxiaInventoryUpdatePayload {
  expected_revision: number;
  item: CharacterXianxiaInventoryItemPayload;
}

export interface CharacterXianxiaInventoryEquippedPatchPayload {
  expected_revision: number;
  is_equipped: boolean;
}

export interface CharacterXianxiaInventoryRemovePayload {
  expected_revision: number;
}

export interface CharacterXianxiaDaoUseRequestPayload {
  expected_revision: number;
  request_name?: string;
  notes?: string;
  prepared_record_index?: number | null;
}

export interface CharacterXianxiaDaoUseRecordPayload {
  expected_revision: number;
  use_record_index: number;
  notes?: string;
}

export interface CharacterNotesPatchPayload {
  expected_revision: number;
  player_notes_markdown: string;
}

export interface CharacterPersonalPatchPayload {
  expected_revision: number;
  physical_description_markdown?: string | null;
  background_markdown?: string | null;
}

export interface CharacterPortraitUpsertPayload {
  expected_revision: number;
  portrait_file: {
    filename: string;
    data_base64: string;
    media_type?: string | null;
  };
  alt_text?: string;
  caption?: string;
}

export interface CharacterPortraitDeletePayload {
  expected_revision: number;
}

export interface CharacterAssignmentUpdatePayload {
  user_id: number;
}

export interface CharacterDeletePayload {
  confirm_character_slug: string;
}

export interface CharacterVitalsPatchResponse extends ApiResponseBase {
  character: CharacterRecord;
}

export interface CharacterNotesPatchResponse extends ApiResponseBase {
  character: CharacterRecord;
}

export interface CharacterPersonalPatchResponse extends ApiResponseBase {
  character: CharacterRecord;
}

export interface CharacterPortraitMutationResponse extends ApiResponseBase {
  character: CharacterRecord;
}

export interface CharacterControlsMutationResponse extends ApiResponseBase {
  message?: string;
  character: CharacterRecord;
}

export interface CharacterDeleteResponse extends ApiResponseBase {
  message?: string;
  deleted_character_slug: string;
  deleted_character_name?: string;
  links?: {
    gen2_roster_url?: string;
    flask_roster_url?: string;
  };
}

export interface CharacterRestPreviewChange {
  label: string;
  from_value: string;
  to_value: string;
}

export interface CharacterRestPreviewResponse extends ApiResponseBase {
  preview: {
    rest_type: "short" | "long" | string;
    label: string;
    changes: CharacterRestPreviewChange[];
    adjustments?: {
      current_hp?: number;
      hit_dice?: {
        value?: string;
        pools?: Array<{
          faces?: number;
          label?: string;
          current?: number;
          max?: number;
          input_name?: string;
        }>;
      };
    };
  };
}

export interface CharacterRestApplyPayload {
  expected_revision: number;
  current_hp?: number;
  hit_dice_current?: Record<string, number>;
}

export interface CharacterRestApplyResponse extends ApiResponseBase {
  character: CharacterRecord;
}

export interface SessionArticleCreatePayloadManual {
  mode: "manual";
  title: string;
  body_markdown?: string;
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
