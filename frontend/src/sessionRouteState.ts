import type { SessionLiveStatePayload, SessionPayload, SessionUnchangedPayload } from "./api/types";
import { isApiError } from "./api/client";

export type SessionRoutePane = "session" | "character" | "dm";

export function isSessionUnchangedPayload(payload: SessionLiveStatePayload): payload is SessionUnchangedPayload {
  return payload.changed === false;
}

export interface SessionRoutePayloadReuse {
  state: "reuse";
  payload: SessionPayload;
}

export interface SessionRoutePayloadNeedsRefresh {
  state: "needs-refresh";
}

export type SessionRoutePayloadResolution = SessionRoutePayloadReuse | SessionRoutePayloadNeedsRefresh | { state: "full"; payload: SessionPayload };

export function resolveSessionLivePayload(
  previous: SessionPayload | undefined,
  liveResponse: SessionLiveStatePayload,
): SessionRoutePayloadResolution {
  if (isSessionUnchangedPayload(liveResponse)) {
    if (previous === undefined) {
      return { state: "needs-refresh" };
    }
    return { state: "reuse", payload: previous };
  }

  return { state: "full", payload: liveResponse };
}

export function coerceSessionPane(activePane: SessionRoutePane, canManage: boolean): SessionRoutePane {
  if (!canManage && activePane === "dm") {
    return "session";
  }
  return activePane;
}

export function isAuthRequiredFromError(error: unknown): boolean {
  return isApiError(error) && error.status === 401;
}
