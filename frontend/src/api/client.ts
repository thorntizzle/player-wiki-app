import type {
  AccountSettingsResponse,
  AccountSettingsUpdatePayload,
  AccountSettingsUpdateResponse,
  ApiAppResponse,
  ApiErrorPayload,
  CampaignControlResponse,
  CampaignControlVisibilityUpdatePayload,
  CampaignControlVisibilityUpdateResponse,
  CampaignHelpResponse,
  CampaignDetailResponse,
  MeResponse,
  CampaignsResponse,
  CharacterAdvancedEditorPayload,
  CharacterAdvancedEditorResponse,
  CharacterCultivationActionPayload,
  CharacterCultivationResponse,
  CharacterDetailResponse,
  CharacterAssignmentUpdatePayload,
  CharacterControlsMutationResponse,
  CharacterCurrencyPatchPayload,
  CharacterDeletePayload,
  CharacterDeleteResponse,
  CharacterCreateContextResponse,
  CharacterCreateSubmitPayload,
  CharacterCreateSubmitResponse,
  CharacterEquipmentStatePatchPayload,
  CharacterFeatureStatePatchPayload,
  CharacterListResponse,
  CharacterInventoryPatchPayload,
  CharacterNotesPatchPayload,
  CharacterNotesPatchResponse,
  CharacterPortraitDeletePayload,
  CharacterPortraitMutationResponse,
  CharacterPortraitUpsertPayload,
  CharacterResourcePatchPayload,
  CharacterRestApplyPayload,
  CharacterRestApplyResponse,
  CharacterRestPreviewResponse,
  CharacterSpellSlotsPatchPayload,
  CharacterVitalsPatchPayload,
  CharacterVitalsPatchResponse,
  CharacterXianxiaActiveStatePatchPayload,
  CharacterXianxiaDaoUseRecordPayload,
  CharacterXianxiaDaoUseRequestPayload,
  CharacterXianxiaInventoryAddPayload,
  CharacterXianxiaInventoryEquippedPatchPayload,
  CharacterXianxiaInventoryRemovePayload,
  CharacterXianxiaInventoryUpdatePayload,
  CharacterXianxiaManualImportPayload,
  CharacterXianxiaManualImportResponse,
  ContentAssetResponse,
  ContentAssetUpsertPayload,
  ContentPageDeleteResponse,
  ContentPageDetailResponse,
  ContentPageListResponse,
  ContentPageUpsertPayload,
  CombatAddNpcPayload,
  CombatAddPlayerPayload,
  CombatAddStatblockPayload,
  CombatAddSystemsMonsterPayload,
  CombatConditionAddPayload,
  CombatResourcesPatchPayload,
  CombatSystemsMonsterSearchResponse,
  CombatTurnPatchPayload,
  CombatVitalsPatchPayload,
  CombatLiveStatePayload,
  CombatPayload,
  DmContentResponse,
  DmContentConditionCreatePayload,
  DmContentConditionResponse,
  DmContentConditionUpdatePayload,
  DmContentSystemsResponse,
  DmContentStatblockCreatePayload,
  DmContentStatblockResponse,
  DmContentStatblockUpdatePayload,
  MessagePostResponse,
  SessionArticleCreatePayload,
  SessionArticleCreateResponse,
  SessionArticleUpdatePayload,
  SessionArticleUpdateResponse,
  SessionArticleRevealResponse,
  SessionArticleSourcesResponse,
  SessionClearRevealedResponse,
  SessionLiveStatePayload,
  SessionLogDeleteResponse,
  SessionLogDetailResponse,
  SessionPayload,
  SessionStartCloseResponse,
  SessionWikiLookupPreviewResponse,
  SessionWikiLookupSearchResponse,
  SystemsEntryResponse,
  CustomSystemsEntryPayload,
  CustomSystemsEntryResponse,
  SystemsIndexResponse,
  SystemsSourceCategoryResponse,
  SystemsSourceResponse,
  SystemsEntryOverridePayload,
  SystemsEntryOverrideResponse,
  SystemsSourceUpdatePayload,
  SystemsSourceUpdateResponse,
  WikiHomeResponse,
  WikiPageResponse,
  WikiSectionResponse,
} from "./types";

const DEFAULT_BASE_PATH = "";

function encodePathSegments(value: string): string {
  return value
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
}

export interface CampaignApiClientOptions {
  baseUrl?: string;
  bearerToken?: string;
}

export interface SessionLiveStateRequest {
  sessionRevision?: number;
  sessionViewToken?: string;
}

export interface CombatLiveStateRequest {
  liveRevision?: number;
  liveViewToken?: string;
  combatantId?: number | null;
}

export class ApiError extends Error {
  public readonly status: number;
  public readonly code: string;

  constructor({ message, code, status }: { message: string; code: string; status: number }) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

function getJsonError(payload: unknown, fallbackMessage: string, status: number): ApiErrorPayload {
  const candidate = payload as ApiErrorPayload;
  if (
    typeof candidate === "object" &&
    candidate !== null &&
    typeof candidate.error === "object" &&
    candidate.error !== null &&
    typeof candidate.error.code === "string" &&
    typeof candidate.error.message === "string"
  ) {
    return candidate as ApiErrorPayload;
  }

  return {
    ok: false,
    error: {
      code: "http_error",
      message: fallbackMessage,
      details: { status },
    },
  };
}

export class CampaignApiClient {
  private readonly baseUrl: string;
  private bearerToken: string | null;

  constructor({ baseUrl = DEFAULT_BASE_PATH, bearerToken = "" }: CampaignApiClientOptions = {}) {
    this.baseUrl = baseUrl;
    this.bearerToken = bearerToken.trim() || null;
  }

  setBearerToken(token: string): void {
    this.bearerToken = token.trim() || null;
  }

  getBearerToken(): string | null {
    return this.bearerToken;
  }

  private buildHeaders(isJsonBody: boolean): HeadersInit {
    const headers: Record<string, string> = {
      Accept: "application/json",
    };
    if (isJsonBody) {
      headers["Content-Type"] = "application/json";
    }
    if (this.bearerToken) {
      headers.Authorization = `Bearer ${this.bearerToken}`;
    }
    return headers;
  }

  private async requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      credentials: "same-origin",
      ...init,
      headers: {
        ...this.buildHeaders(Boolean(init.body) || init.method === "POST" || init.method === "PATCH" || init.method === "PUT" || init.method === "DELETE"),
        ...(init.headers || {}),
      },
    });

    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const envelope = getJsonError(payload, `${response.status} ${response.statusText}`, response.status);
      throw new ApiError({
        message: envelope.error.message,
        code: envelope.error.code,
        status: response.status,
      });
    }

    return payload as T;
  }

  private async requestBrowserJson<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      credentials: "same-origin",
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.headers || {}),
      },
    });

    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const envelope = getJsonError(payload, `${response.status} ${response.statusText}`, response.status);
      throw new ApiError({
        message: envelope.error.message,
        code: envelope.error.code,
        status: response.status,
      });
    }

    return payload as T;
  }

  async getAppState(): Promise<ApiAppResponse> {
    return this.requestJson<ApiAppResponse>("/api/v1/app");
  }

  async getMe(): Promise<MeResponse> {
    return this.requestJson<MeResponse>("/api/v1/me");
  }

  async getAccountSettings(): Promise<AccountSettingsResponse> {
    return this.requestJson<AccountSettingsResponse>("/api/v1/me/settings");
  }

  async patchAccountSettings(
    payload: AccountSettingsUpdatePayload,
  ): Promise<AccountSettingsUpdateResponse> {
    return this.requestJson<AccountSettingsUpdateResponse>("/api/v1/me/settings", {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  }

  async getCampaign(slug: string): Promise<CampaignDetailResponse> {
    return this.requestJson<CampaignDetailResponse>(`/api/v1/campaigns/${encodeURIComponent(slug)}`);
  }

  async getCampaignHelp(slug: string): Promise<CampaignHelpResponse> {
    return this.requestJson<CampaignHelpResponse>(`/api/v1/campaigns/${encodeURIComponent(slug)}/help`);
  }

  async getCampaignControl(slug: string): Promise<CampaignControlResponse> {
    return this.requestJson<CampaignControlResponse>(`/api/v1/campaigns/${encodeURIComponent(slug)}/control`);
  }

  async patchCampaignControlVisibility(
    slug: string,
    payload: CampaignControlVisibilityUpdatePayload,
  ): Promise<CampaignControlVisibilityUpdateResponse> {
    return this.requestJson<CampaignControlVisibilityUpdateResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/control/visibility`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    );
  }

  async getCampaigns(): Promise<CampaignsResponse> {
    return this.requestJson<CampaignsResponse>("/api/v1/campaigns");
  }

  async getWikiHome(slug: string, q = ""): Promise<WikiHomeResponse> {
    const query = q.trim();
    const suffix = query ? `?q=${encodeURIComponent(query)}` : "";
    return this.requestJson<WikiHomeResponse>(`/api/v1/campaigns/${encodeURIComponent(slug)}/wiki${suffix}`);
  }

  async getWikiSection(slug: string, sectionSlug: string): Promise<WikiSectionResponse> {
    return this.requestJson<WikiSectionResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/wiki/sections/${encodeURIComponent(sectionSlug)}`,
    );
  }

  async getWikiPage(slug: string, pageSlug: string): Promise<WikiPageResponse> {
    return this.requestJson<WikiPageResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/wiki/pages/${pageSlug
        .split("/")
        .map((part) => encodeURIComponent(part))
        .join("/")}`,
    );
  }

  async getSession(slug: string): Promise<SessionPayload> {
    return this.requestJson<SessionPayload>(`/api/v1/campaigns/${encodeURIComponent(slug)}/session`);
  }

  async getSessionLiveState(
    slug: string,
    liveState: SessionLiveStateRequest = {},
  ): Promise<SessionLiveStatePayload> {
    const headers: Record<string, string> = {};
    if (liveState.sessionRevision !== undefined && liveState.sessionViewToken) {
      headers["X-Live-Revision"] = String(liveState.sessionRevision);
      headers["X-Live-View-Token"] = liveState.sessionViewToken;
    }

    return this.requestJson<SessionLiveStatePayload>(`/api/v1/campaigns/${encodeURIComponent(slug)}/session`, {
      headers,
    });
  }

  async getCombat(slug: string, combatantId?: number | null): Promise<CombatPayload> {
    const suffix = combatantId ? `?combatant=${encodeURIComponent(String(combatantId))}` : "";
    return this.requestJson<CombatPayload>(`/api/v1/campaigns/${encodeURIComponent(slug)}/combat${suffix}`);
  }

  async getCombatLiveState(
    slug: string,
    liveState: CombatLiveStateRequest = {},
  ): Promise<CombatLiveStatePayload> {
    const headers: Record<string, string> = {};
    if (liveState.liveRevision !== undefined && liveState.liveViewToken) {
      headers["X-Live-Revision"] = String(liveState.liveRevision);
      headers["X-Live-View-Token"] = liveState.liveViewToken;
    }
    const suffix = liveState.combatantId ? `?combatant=${encodeURIComponent(String(liveState.combatantId))}` : "";
    return this.requestJson<CombatLiveStatePayload>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/combat/live-state${suffix}`,
      { headers },
    );
  }

  private combatFocusSuffix(combatantId?: number | null): string {
    return combatantId ? `?combatant=${encodeURIComponent(String(combatantId))}` : "";
  }

  async addCombatPlayer(
    slug: string,
    payload: CombatAddPlayerPayload,
    combatantId?: number | null,
  ): Promise<CombatPayload> {
    return this.requestJson<CombatPayload>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/combat/player-combatants${this.combatFocusSuffix(combatantId)}`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  }

  async addCombatNpc(
    slug: string,
    payload: CombatAddNpcPayload,
    combatantId?: number | null,
  ): Promise<CombatPayload> {
    return this.requestJson<CombatPayload>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/combat/npc-combatants${this.combatFocusSuffix(combatantId)}`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  }

  async addCombatStatblock(
    slug: string,
    payload: CombatAddStatblockPayload,
    combatantId?: number | null,
  ): Promise<CombatPayload> {
    return this.requestJson<CombatPayload>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/combat/statblock-combatants${this.combatFocusSuffix(combatantId)}`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  }

  async searchCombatSystemsMonsters(slug: string, query: string): Promise<CombatSystemsMonsterSearchResponse> {
    const suffix = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : "";
    return this.requestJson<CombatSystemsMonsterSearchResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/combat/systems-monsters/search${suffix}`,
    );
  }

  async addCombatSystemsMonster(
    slug: string,
    payload: CombatAddSystemsMonsterPayload,
    combatantId?: number | null,
  ): Promise<CombatPayload> {
    return this.requestJson<CombatPayload>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/combat/systems-monsters${this.combatFocusSuffix(combatantId)}`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  }

  async advanceCombatTurn(slug: string, combatantId?: number | null): Promise<CombatPayload> {
    return this.requestJson<CombatPayload>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/combat/advance-turn${this.combatFocusSuffix(combatantId)}`,
      { method: "POST" },
    );
  }

  async clearCombat(slug: string): Promise<CombatPayload> {
    return this.requestJson<CombatPayload>(`/api/v1/campaigns/${encodeURIComponent(slug)}/combat/clear`, {
      method: "POST",
    });
  }

  async setCurrentCombatant(slug: string, combatantId: number): Promise<CombatPayload> {
    return this.requestJson<CombatPayload>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/combat/combatants/${combatantId}/set-current${this.combatFocusSuffix(combatantId)}`,
      { method: "POST" },
    );
  }

  async patchCombatantTurn(
    slug: string,
    combatantId: number,
    payload: CombatTurnPatchPayload,
  ): Promise<CombatPayload> {
    return this.requestJson<CombatPayload>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/combat/combatants/${combatantId}/turn${this.combatFocusSuffix(combatantId)}`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    );
  }

  async patchCombatantVitals(
    slug: string,
    combatantId: number,
    payload: CombatVitalsPatchPayload,
  ): Promise<CombatPayload> {
    return this.requestJson<CombatPayload>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/combat/combatants/${combatantId}/vitals${this.combatFocusSuffix(combatantId)}`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    );
  }

  async patchCombatantResources(
    slug: string,
    combatantId: number,
    payload: CombatResourcesPatchPayload,
  ): Promise<CombatPayload> {
    return this.requestJson<CombatPayload>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/combat/combatants/${combatantId}/resources${this.combatFocusSuffix(combatantId)}`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    );
  }

  async addCombatCondition(
    slug: string,
    combatantId: number,
    payload: CombatConditionAddPayload,
  ): Promise<CombatPayload> {
    return this.requestJson<CombatPayload>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/combat/combatants/${combatantId}/conditions${this.combatFocusSuffix(combatantId)}`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  }

  async deleteCombatCondition(slug: string, conditionId: number, combatantId?: number | null): Promise<CombatPayload> {
    return this.requestJson<CombatPayload>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/combat/conditions/${conditionId}${this.combatFocusSuffix(combatantId)}`,
      {
        method: "DELETE",
      },
    );
  }

  async deleteCombatant(slug: string, combatantId: number): Promise<CombatPayload> {
    return this.requestJson<CombatPayload>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/combat/combatants/${combatantId}`,
      {
        method: "DELETE",
      },
    );
  }

  async getDmContent(slug: string): Promise<DmContentResponse> {
    return this.requestJson<DmContentResponse>(`/api/v1/campaigns/${encodeURIComponent(slug)}/dm-content`);
  }

  async getDmContentSystems(slug: string): Promise<DmContentSystemsResponse> {
    return this.requestJson<DmContentSystemsResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/dm-content/systems`,
    );
  }

  async getSystemsIndex(slug: string, q = "", referenceQ = ""): Promise<SystemsIndexResponse> {
    const params = new URLSearchParams();
    if (q.trim()) {
      params.set("q", q.trim());
    }
    if (referenceQ.trim()) {
      params.set("reference_q", referenceQ.trim());
    }
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return this.requestJson<SystemsIndexResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/systems${suffix}`,
    );
  }

  async getSystemsSource(slug: string, sourceId: string, referenceQ = ""): Promise<SystemsSourceResponse> {
    const suffix = referenceQ.trim() ? `?reference_q=${encodeURIComponent(referenceQ.trim())}` : "";
    return this.requestJson<SystemsSourceResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/systems/sources/${encodeURIComponent(sourceId)}${suffix}`,
    );
  }

  async getSystemsSourceCategory(
    slug: string,
    sourceId: string,
    entryType: string,
    q = "",
  ): Promise<SystemsSourceCategoryResponse> {
    const suffix = q.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
    return this.requestJson<SystemsSourceCategoryResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/systems/sources/${encodeURIComponent(sourceId)}/types/${encodeURIComponent(entryType)}${suffix}`,
    );
  }

  async getSystemsEntry(slug: string, entrySlug: string): Promise<SystemsEntryResponse> {
    return this.requestJson<SystemsEntryResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/systems/entries/${encodeURIComponent(entrySlug)}`,
    );
  }

  async updateSystemsSources(
    slug: string,
    payload: SystemsSourceUpdatePayload,
  ): Promise<SystemsSourceUpdateResponse> {
    return this.requestJson<SystemsSourceUpdateResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/systems/sources`,
      {
        method: "PUT",
        body: JSON.stringify(payload),
      },
    );
  }

  async updateSystemsEntryOverride(
    slug: string,
    entryKey: string,
    payload: SystemsEntryOverridePayload,
  ): Promise<SystemsEntryOverrideResponse> {
    return this.requestJson<SystemsEntryOverrideResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/systems/overrides/${encodePathSegments(entryKey)}`,
      {
        method: "PUT",
        body: JSON.stringify(payload),
      },
    );
  }

  async createSystemsCustomEntry(
    slug: string,
    payload: CustomSystemsEntryPayload,
  ): Promise<CustomSystemsEntryResponse> {
    return this.requestJson<CustomSystemsEntryResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/systems/custom-entries`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  }

  async updateSystemsCustomEntry(
    slug: string,
    entrySlug: string,
    payload: CustomSystemsEntryPayload,
  ): Promise<CustomSystemsEntryResponse> {
    return this.requestJson<CustomSystemsEntryResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/systems/custom-entries/${encodeURIComponent(entrySlug)}`,
      {
        method: "PUT",
        body: JSON.stringify(payload),
      },
    );
  }

  async archiveSystemsCustomEntry(slug: string, entrySlug: string): Promise<CustomSystemsEntryResponse> {
    return this.requestJson<CustomSystemsEntryResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/systems/custom-entries/${encodeURIComponent(entrySlug)}/archive`,
      {
        method: "POST",
      },
    );
  }

  async restoreSystemsCustomEntry(slug: string, entrySlug: string): Promise<CustomSystemsEntryResponse> {
    return this.requestJson<CustomSystemsEntryResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/systems/custom-entries/${encodeURIComponent(entrySlug)}/restore`,
      {
        method: "POST",
      },
    );
  }

  async createDmContentStatblock(
    slug: string,
    payload: DmContentStatblockCreatePayload,
  ): Promise<DmContentStatblockResponse> {
    return this.requestJson<DmContentStatblockResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/dm-content/statblocks`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  }

  async updateDmContentStatblock(
    slug: string,
    statblockId: number,
    payload: DmContentStatblockUpdatePayload,
  ): Promise<DmContentStatblockResponse> {
    return this.requestJson<DmContentStatblockResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/dm-content/statblocks/${statblockId}`,
      {
        method: "PUT",
        body: JSON.stringify(payload),
      },
    );
  }

  async deleteDmContentStatblock(slug: string, statblockId: number): Promise<DmContentStatblockResponse> {
    return this.requestJson<DmContentStatblockResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/dm-content/statblocks/${statblockId}`,
      {
        method: "DELETE",
      },
    );
  }

  async createDmContentCondition(
    slug: string,
    payload: DmContentConditionCreatePayload,
  ): Promise<DmContentConditionResponse> {
    return this.requestJson<DmContentConditionResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/dm-content/conditions`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  }

  async updateDmContentCondition(
    slug: string,
    conditionId: number,
    payload: DmContentConditionUpdatePayload,
  ): Promise<DmContentConditionResponse> {
    return this.requestJson<DmContentConditionResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/dm-content/conditions/${conditionId}`,
      {
        method: "PUT",
        body: JSON.stringify(payload),
      },
    );
  }

  async deleteDmContentCondition(slug: string, conditionId: number): Promise<DmContentConditionResponse> {
    return this.requestJson<DmContentConditionResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/dm-content/conditions/${conditionId}`,
      {
        method: "DELETE",
      },
    );
  }

  async getContentPages(slug: string): Promise<ContentPageListResponse> {
    return this.requestJson<ContentPageListResponse>(`/api/v1/campaigns/${encodeURIComponent(slug)}/content/pages`);
  }

  async getContentPage(slug: string, pageRef: string): Promise<ContentPageDetailResponse> {
    return this.requestJson<ContentPageDetailResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/content/pages/${encodePathSegments(pageRef)}`,
    );
  }

  async upsertContentPage(
    slug: string,
    pageRef: string,
    payload: ContentPageUpsertPayload,
  ): Promise<ContentPageDetailResponse> {
    return this.requestJson<ContentPageDetailResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/content/pages/${encodePathSegments(pageRef)}`,
      {
        method: "PUT",
        body: JSON.stringify(payload),
      },
    );
  }

  async deleteContentPage(slug: string, pageRef: string): Promise<ContentPageDeleteResponse> {
    return this.requestJson<ContentPageDeleteResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/content/pages/${encodePathSegments(pageRef)}`,
      {
        method: "DELETE",
      },
    );
  }

  async upsertContentAsset(
    slug: string,
    assetRef: string,
    payload: ContentAssetUpsertPayload,
  ): Promise<ContentAssetResponse> {
    return this.requestJson<ContentAssetResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/content/assets/${encodePathSegments(assetRef)}`,
      {
        method: "PUT",
        body: JSON.stringify(payload),
      },
    );
  }

  async postSessionMessage(slug: string, body: string): Promise<MessagePostResponse> {
    return this.requestJson<MessagePostResponse>(`/api/v1/campaigns/${encodeURIComponent(slug)}/session/messages`, {
      method: "POST",
      body: JSON.stringify({ body }),
    });
  }

  async searchSessionArticleSources(slug: string, q: string): Promise<SessionArticleSourcesResponse> {
    return this.requestJson<SessionArticleSourcesResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/session/article-sources/search?q=${encodeURIComponent(q)}`,
    );
  }

  async startSession(slug: string): Promise<SessionStartCloseResponse> {
    return this.requestJson<SessionStartCloseResponse>(`/api/v1/campaigns/${encodeURIComponent(slug)}/session/start`, {
      method: "POST",
    });
  }

  async closeSession(slug: string): Promise<SessionStartCloseResponse> {
    return this.requestJson<SessionStartCloseResponse>(`/api/v1/campaigns/${encodeURIComponent(slug)}/session/close`, {
      method: "POST",
    });
  }

  async createSessionArticle(
    slug: string,
    payload: SessionArticleCreatePayload,
  ): Promise<SessionArticleCreateResponse> {
    return this.requestJson<SessionArticleCreateResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/session/articles`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  }

  async updateSessionArticle(
    slug: string,
    articleId: number,
    payload: SessionArticleUpdatePayload,
  ): Promise<SessionArticleUpdateResponse> {
    return this.requestJson<SessionArticleUpdateResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/session/articles/${articleId}`,
      {
        method: "PUT",
        body: JSON.stringify(payload),
      },
    );
  }

  async revealSessionArticle(slug: string, articleId: number): Promise<SessionArticleRevealResponse> {
    return this.requestJson<SessionArticleRevealResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/session/articles/${articleId}/reveal`,
      {
        method: "POST",
      },
    );
  }

  async deleteSessionArticle(slug: string, articleId: number): Promise<{ ok: boolean }> {
    return this.requestJson<{ ok: boolean }>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/session/articles/${articleId}`,
      {
        method: "DELETE",
      },
    );
  }

  async clearRevealedSessionArticles(slug: string): Promise<SessionClearRevealedResponse> {
    return this.requestJson<SessionClearRevealedResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/session/articles/revealed`,
      {
        method: "DELETE",
      },
    );
  }

  async getSessionLog(slug: string, sessionId: number): Promise<SessionLogDetailResponse> {
    return this.requestJson<SessionLogDetailResponse>(`/api/v1/campaigns/${encodeURIComponent(slug)}/session/logs/${sessionId}`);
  }

  async deleteSessionLog(slug: string, sessionId: number): Promise<SessionLogDeleteResponse> {
    return this.requestJson<SessionLogDeleteResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/session/logs/${sessionId}`,
      {
        method: "DELETE",
      },
    );
  }

  getSessionArticleImageUrl(slug: string, articleId: number): string {
    return `/api/v1/campaigns/${encodeURIComponent(slug)}/session/articles/${articleId}/image`;
  }

  async searchPlayerSessionWiki(slug: string, q: string): Promise<SessionWikiLookupSearchResponse> {
    return this.requestBrowserJson<SessionWikiLookupSearchResponse>(
      `/campaigns/${encodeURIComponent(slug)}/session/wiki-lookup/search?q=${encodeURIComponent(q)}`,
    );
  }

  async previewPlayerSessionWiki(slug: string, pageRef: string): Promise<SessionWikiLookupPreviewResponse> {
    return this.requestBrowserJson<SessionWikiLookupPreviewResponse>(
      `/campaigns/${encodeURIComponent(slug)}/session/wiki-lookup/preview?page_ref=${encodeURIComponent(pageRef)}`,
    );
  }

  async getCharacters(slug: string, query = ""): Promise<CharacterListResponse> {
    const search = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : "";
    return this.requestJson<CharacterListResponse>(`/api/v1/campaigns/${encodeURIComponent(slug)}/characters${search}`);
  }

  async getCharacter(slug: string, characterSlug: string): Promise<CharacterDetailResponse> {
    return this.requestJson<CharacterDetailResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(characterSlug)}`,
    );
  }

  async getCharacterAdvancedEditor(slug: string, characterSlug: string): Promise<CharacterAdvancedEditorResponse> {
    return this.requestJson<CharacterAdvancedEditorResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(characterSlug)}/advanced-editor`,
    );
  }

  async updateCharacterAdvancedEditor(
    slug: string,
    characterSlug: string,
    payload: CharacterAdvancedEditorPayload,
  ): Promise<CharacterAdvancedEditorResponse> {
    return this.requestJson<CharacterAdvancedEditorResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(characterSlug)}/advanced-editor`,
      {
        method: "PUT",
        body: JSON.stringify(payload),
      },
    );
  }

  async getCharacterCultivation(slug: string, characterSlug: string): Promise<CharacterCultivationResponse> {
    return this.requestJson<CharacterCultivationResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(characterSlug)}/cultivation`,
    );
  }

  async runCharacterCultivationAction(
    slug: string,
    characterSlug: string,
    payload: CharacterCultivationActionPayload,
  ): Promise<CharacterCultivationResponse> {
    return this.requestJson<CharacterCultivationResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(characterSlug)}/cultivation`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  }

  async getCharacterCreateContext(slug: string, values: Record<string, string | string[]> = {}): Promise<CharacterCreateContextResponse> {
    const params = new URLSearchParams();
    Object.entries(values).forEach(([key, value]) => {
      if (Array.isArray(value)) {
        value.forEach((item) => params.append(key, item));
      } else if (value) {
        params.set(key, value);
      }
    });
    const search = params.toString() ? `?${params.toString()}` : "";
    return this.requestJson<CharacterCreateContextResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/create${search}`,
    );
  }

  async createCharacter(slug: string, payload: CharacterCreateSubmitPayload): Promise<CharacterCreateSubmitResponse> {
    return this.requestJson<CharacterCreateSubmitResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/create`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  }

  async getXianxiaManualImportContext(
    slug: string,
    values: Record<string, string> = {},
  ): Promise<CharacterXianxiaManualImportResponse> {
    const params = new URLSearchParams();
    Object.entries(values).forEach(([key, value]) => {
      if (value) {
        params.set(key, value);
      }
    });
    const search = params.toString() ? `?${params.toString()}` : "";
    return this.requestJson<CharacterXianxiaManualImportResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/import/xianxia-manual${search}`,
    );
  }

  async submitXianxiaManualImport(
    slug: string,
    payload: CharacterXianxiaManualImportPayload,
  ): Promise<CharacterXianxiaManualImportResponse | CharacterCreateSubmitResponse> {
    return this.requestJson<CharacterXianxiaManualImportResponse | CharacterCreateSubmitResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/import/xianxia-manual`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  }

  async upsertCharacterPortrait(
    slug: string,
    characterSlug: string,
    payload: CharacterPortraitUpsertPayload,
  ): Promise<CharacterPortraitMutationResponse> {
    return this.requestJson<CharacterPortraitMutationResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(characterSlug)}/portrait`,
      {
        method: "PUT",
        body: JSON.stringify(payload),
      },
    );
  }

  async deleteCharacterPortrait(
    slug: string,
    characterSlug: string,
    payload: CharacterPortraitDeletePayload,
  ): Promise<CharacterPortraitMutationResponse> {
    return this.requestJson<CharacterPortraitMutationResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(characterSlug)}/portrait`,
      {
        method: "DELETE",
        body: JSON.stringify(payload),
      },
    );
  }

  async assignCharacterOwner(
    slug: string,
    characterSlug: string,
    payload: CharacterAssignmentUpdatePayload,
  ): Promise<CharacterControlsMutationResponse> {
    return this.requestJson<CharacterControlsMutationResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(characterSlug)}/controls/assignment`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  }

  async clearCharacterOwner(slug: string, characterSlug: string): Promise<CharacterControlsMutationResponse> {
    return this.requestJson<CharacterControlsMutationResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(characterSlug)}/controls/assignment`,
      {
        method: "DELETE",
      },
    );
  }

  async deleteCharacter(
    slug: string,
    characterSlug: string,
    payload: CharacterDeletePayload,
  ): Promise<CharacterDeleteResponse> {
    return this.requestJson<CharacterDeleteResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(characterSlug)}/controls`,
      {
        method: "DELETE",
        body: JSON.stringify(payload),
      },
    );
  }

  async patchCharacterVitals(
    slug: string,
    characterSlug: string,
    payload: CharacterVitalsPatchPayload,
  ): Promise<CharacterVitalsPatchResponse> {
    return this.requestJson<CharacterVitalsPatchResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(
        characterSlug,
      )}/session/vitals`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    );
  }

  async patchCharacterResource(
    slug: string,
    characterSlug: string,
    resourceId: string,
    payload: CharacterResourcePatchPayload,
  ): Promise<CharacterVitalsPatchResponse> {
    return this.requestJson<CharacterVitalsPatchResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(
        characterSlug,
      )}/session/resources/${encodeURIComponent(resourceId)}`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    );
  }

  async patchCharacterSpellSlots(
    slug: string,
    characterSlug: string,
    level: number,
    payload: CharacterSpellSlotsPatchPayload,
  ): Promise<CharacterVitalsPatchResponse> {
    return this.requestJson<CharacterVitalsPatchResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(
        characterSlug,
      )}/session/spell-slots/${level}`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    );
  }

  async patchCharacterInventory(
    slug: string,
    characterSlug: string,
    itemId: string,
    payload: CharacterInventoryPatchPayload,
  ): Promise<CharacterVitalsPatchResponse> {
    return this.requestJson<CharacterVitalsPatchResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(
        characterSlug,
      )}/session/inventory/${encodeURIComponent(itemId)}`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    );
  }

  async patchCharacterEquipmentState(
    slug: string,
    characterSlug: string,
    itemId: string,
    payload: CharacterEquipmentStatePatchPayload,
  ): Promise<CharacterVitalsPatchResponse> {
    return this.requestJson<CharacterVitalsPatchResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(
        characterSlug,
      )}/session/equipment/${encodeURIComponent(itemId)}`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    );
  }

  async patchCharacterFeatureState(
    slug: string,
    characterSlug: string,
    featureKey: string,
    payload: CharacterFeatureStatePatchPayload,
  ): Promise<CharacterVitalsPatchResponse> {
    return this.requestJson<CharacterVitalsPatchResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(
        characterSlug,
      )}/session/feature-states/${encodeURIComponent(featureKey)}`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    );
  }

  async patchCharacterXianxiaActiveState(
    slug: string,
    characterSlug: string,
    payload: CharacterXianxiaActiveStatePatchPayload,
  ): Promise<CharacterVitalsPatchResponse> {
    return this.requestJson<CharacterVitalsPatchResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(
        characterSlug,
      )}/session/xianxia-active-state`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    );
  }

  async postCharacterXianxiaDaoUseRequest(
    slug: string,
    characterSlug: string,
    payload: CharacterXianxiaDaoUseRequestPayload,
  ): Promise<CharacterVitalsPatchResponse> {
    return this.requestJson<CharacterVitalsPatchResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(
        characterSlug,
      )}/session/xianxia-dao-immolating-use-requests`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  }

  async postCharacterXianxiaDaoUseRecord(
    slug: string,
    characterSlug: string,
    payload: CharacterXianxiaDaoUseRecordPayload,
  ): Promise<CharacterVitalsPatchResponse> {
    return this.requestJson<CharacterVitalsPatchResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(
        characterSlug,
      )}/session/xianxia-dao-immolating-use-records`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  }

  async addCharacterXianxiaInventoryItem(
    slug: string,
    characterSlug: string,
    payload: CharacterXianxiaInventoryAddPayload,
  ): Promise<CharacterVitalsPatchResponse> {
    return this.requestJson<CharacterVitalsPatchResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(
        characterSlug,
      )}/session/xianxia-inventory`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  }

  async patchCharacterXianxiaInventoryItem(
    slug: string,
    characterSlug: string,
    itemId: string,
    payload: CharacterXianxiaInventoryUpdatePayload,
  ): Promise<CharacterVitalsPatchResponse> {
    return this.requestJson<CharacterVitalsPatchResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(
        characterSlug,
      )}/session/xianxia-inventory/${encodeURIComponent(itemId)}`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    );
  }

  async removeCharacterXianxiaInventoryItem(
    slug: string,
    characterSlug: string,
    itemId: string,
    payload: CharacterXianxiaInventoryRemovePayload,
  ): Promise<CharacterVitalsPatchResponse> {
    return this.requestJson<CharacterVitalsPatchResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(
        characterSlug,
      )}/session/xianxia-inventory/${encodeURIComponent(itemId)}`,
      {
        method: "DELETE",
        body: JSON.stringify(payload),
      },
    );
  }

  async patchCharacterXianxiaInventoryEquipped(
    slug: string,
    characterSlug: string,
    itemId: string,
    payload: CharacterXianxiaInventoryEquippedPatchPayload,
  ): Promise<CharacterVitalsPatchResponse> {
    return this.requestJson<CharacterVitalsPatchResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(
        characterSlug,
      )}/session/xianxia-inventory/${encodeURIComponent(itemId)}/equipped`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    );
  }

  async patchCharacterCurrency(
    slug: string,
    characterSlug: string,
    payload: CharacterCurrencyPatchPayload,
  ): Promise<CharacterVitalsPatchResponse> {
    return this.requestJson<CharacterVitalsPatchResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(characterSlug)}/session/currency`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    );
  }

  async patchCharacterNotes(
    slug: string,
    characterSlug: string,
    payload: CharacterNotesPatchPayload,
  ): Promise<CharacterNotesPatchResponse> {
    return this.requestJson<CharacterNotesPatchResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(characterSlug)}/session/notes`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    );
  }

  async getCharacterRestPreview(
    slug: string,
    characterSlug: string,
    restType: "short" | "long",
  ): Promise<CharacterRestPreviewResponse> {
    return this.requestJson<CharacterRestPreviewResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(
        characterSlug,
      )}/rest-preview/${encodeURIComponent(restType)}`,
    );
  }

  async applyCharacterRest(
    slug: string,
    characterSlug: string,
    restType: "short" | "long",
    payload: CharacterRestApplyPayload,
  ): Promise<CharacterRestApplyResponse> {
    return this.requestJson<CharacterRestApplyResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(
        characterSlug,
      )}/session/rest/${encodeURIComponent(restType)}`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function apiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Unexpected error.";
}
