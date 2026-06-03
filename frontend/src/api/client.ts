import type {
  ApiAppResponse,
  ApiErrorPayload,
  CampaignsResponse,
  MessagePostResponse,
  SessionPayload,
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
    typeof candidate === "object"
    && candidate !== null
    && typeof (candidate as ApiErrorPayload).error === "object"
    && candidate.error !== null
    && typeof (candidate.error as { code?: string; message?: string }).code === "string"
    && typeof (candidate.error as { code?: string; message?: string }).message === "string"
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
    const headers: Record<string, string> = {};
    if (isJsonBody) {
      headers["Content-Type"] = "application/json";
    }
    headers.Accept = "application/json";
    if (this.bearerToken) {
      headers.Authorization = `Bearer ${this.bearerToken}`;
    }
    return headers;
  }

  private async requestJson<T>(path: string, init?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const response = await fetch(url, {
      credentials: "same-origin",
      ...init,
      headers: {
        ...this.buildHeaders((init?.body || init?.method) !== undefined),
        ...(init?.headers || {}),
      },
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const envelope = getJsonError(
        payload,
        `${response.status} ${response.statusText}`,
        response.status,
      );
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
