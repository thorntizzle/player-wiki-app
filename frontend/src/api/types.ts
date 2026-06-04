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

export interface UserPreferences {
  theme_key?: string | null;
  session_chat_order?: string | null;
}

export interface MeResponse extends ApiResponseBase {
  app: AppMeta;
  auth_source: string;
  user: UserProfile;
  memberships: UserMembership[];
  preferences?: UserPreferences;
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

export interface WikiSubsectionGroup {
  subsection_name: string;
  page_count: number;
  pages: WikiPageSummary[];
}

export interface WikiHomeLinks {
  flask_campaign_url: string;
  gen2_campaign_url: string;
}

export interface WikiHomeResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  can_view_wiki: boolean;
  wiki_visibility_label: string;
  query: string;
  result_count: number;
  grouped_sections: WikiSectionGroup[];
  overview_page: WikiPageDetail | null;
  message: string;
  links: WikiHomeLinks;
}

export interface WikiSectionResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  section_name: string;
  section_slug: string;
  page_count: number;
  pages: WikiPageSummary[];
  top_level_pages: WikiPageSummary[];
  subsection_groups: WikiSubsectionGroup[];
  show_subsections: boolean;
  links: {
    flask_section_url: string;
    gen2_campaign_url: string;
  };
}

export interface WikiPageResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  page: WikiPageDetail;
  backlinks: WikiPageSummary[];
  links: {
    flask_page_url: string;
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
  session_revision: number;
  session_view_token: string;
  changed?: true;
  campaign: CampaignRecord;
  permissions: SessionPermissions;
  active_session: SessionRecord | null;
  messages: SessionMessage[];
  staged_articles?: SessionArticle[];
  revealed_articles?: SessionArticle[];
  session_logs?: SessionLogSummary[];
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
  player_character_targets: CombatPlayerCharacterTarget[];
  poll_settings?: {
    active_interval_ms?: number;
    idle_interval_ms?: number;
    idle_threshold_ms?: number;
  };
  links?: {
    flask_combat_url?: string;
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

export interface DmContentResponse extends ApiResponseBase {
  campaign: CampaignRecord;
  permissions: CampaignPermissions;
  statblocks: DmContentStatblock[];
  conditions: DmContentConditionDefinition[];
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
  can_record_xianxia_dao_immolating_use?: boolean;
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
  equipment_state?: CharacterEquipmentState;
  arcane_armor_state?: CharacterArcaneArmorState;
  presented_spellcasting?: CharacterPresentedSpellcasting;
  presented_inventory?: CharacterPresentedInventoryItem[];
  presented_xianxia?: CharacterPresentedXianxia;
  portrait?: CharacterPortrait | null;
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
    create_character_url?: string;
    import_xianxia_url?: string;
  };
}

export interface CharacterDetailResponse extends ApiResponseBase {
  character: CharacterRecord;
  links?: {
    flask_roster_url?: string;
    flask_character_url?: string;
    advanced_editor_url?: string;
    cultivation_url?: string;
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

export interface CharacterVitalsPatchResponse extends ApiResponseBase {
  character: CharacterRecord;
}

export interface CharacterNotesPatchResponse extends ApiResponseBase {
  character: CharacterRecord;
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
  };
}

export interface CharacterRestApplyPayload {
  expected_revision: number;
}

export interface CharacterRestApplyResponse extends ApiResponseBase {
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
