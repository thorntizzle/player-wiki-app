import type {
  ApiAppResponse,
  ApiErrorPayload,
  CampaignsResponse,
  CharacterDetailResponse,
  CharacterCurrencyPatchPayload,
  CharacterListResponse,
  CharacterInventoryPatchPayload,
  CharacterNotesPatchPayload,
  CharacterNotesPatchResponse,
  CharacterResourcePatchPayload,
  CharacterRestApplyPayload,
  CharacterRestApplyResponse,
  CharacterRestPreviewResponse,
  CharacterSpellSlotsPatchPayload,
  CharacterVitalsPatchPayload,
  CharacterVitalsPatchResponse,
  MessagePostResponse,
  SessionArticleCreatePayload,
  SessionArticleCreateResponse,
  SessionArticleUpdatePayload,
  SessionArticleUpdateResponse,
  SessionArticleRevealResponse,
  SessionArticleSourcesResponse,
  SessionClearRevealedResponse,
  SessionLogDeleteResponse,
  SessionLogDetailResponse,
  SessionPayload,
  SessionStartCloseResponse,
  SessionWikiLookupPreviewResponse,
  SessionWikiLookupSearchResponse,
} from "./types";

const DEFAULT_BASE_PATH = "";

export interface CampaignApiClientOptions {
  baseUrl?: string;
  bearerToken?: string;
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

  async getCampaigns(): Promise<CampaignsResponse> {
    return this.requestJson<CampaignsResponse>("/api/v1/campaigns");
  }

  async getSession(slug: string): Promise<SessionPayload> {
    return this.requestJson<SessionPayload>(`/api/v1/campaigns/${encodeURIComponent(slug)}/session`);
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

  async getCharacters(slug: string): Promise<CharacterListResponse> {
    return this.requestJson<CharacterListResponse>(`/api/v1/campaigns/${encodeURIComponent(slug)}/characters`);
  }

  async getCharacter(slug: string, characterSlug: string): Promise<CharacterDetailResponse> {
    return this.requestJson<CharacterDetailResponse>(
      `/api/v1/campaigns/${encodeURIComponent(slug)}/characters/${encodeURIComponent(characterSlug)}`,
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
