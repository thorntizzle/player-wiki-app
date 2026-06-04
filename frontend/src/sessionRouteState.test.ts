import type { SessionPayload, SessionUnchangedPayload, SessionLiveStatePayload } from "./api/types";
import { ApiError } from "./api/client";
import {
  coerceSessionPane,
  isAuthRequiredFromError,
  isSessionUnchangedPayload,
  resolveSessionLivePayload,
} from "./sessionRouteState";

let failures = 0;

function run(name: string, fn: () => void): void {
  try {
    fn();
    console.log(`pass ${name}`);
  } catch (error) {
    failures += 1;
    console.error(`fail ${name}`, error);
  }
}

function assertTrue(condition: unknown, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

function sessionPayload(overrides: Partial<SessionPayload> = {}): SessionPayload {
  return {
    ok: true,
    session_revision: 1,
    session_view_token: "session-view-token",
    campaign: {
      slug: "campaign-slug",
      title: "Campaign",
      summary: "",
      system: "system",
      current_session: null,
      systems_library_slug: "",
    },
    permissions: {
      can_manage_session: true,
      can_post_messages: true,
    },
    active_session: null,
    messages: [],
    ...overrides,
  };
}

run("resolveSessionLivePayload reuses previous payload when unchanged response has prior state", () => {
  const previous = sessionPayload({ session_revision: 9 });
  const live = {
    changed: false,
    ok: true,
    session_revision: 10,
    session_view_token: "live-token",
  } satisfies SessionUnchangedPayload;
  const result = resolveSessionLivePayload(previous, live);

  if (result.state !== "reuse") {
    throw new Error("expected reuse when unchanged and prior payload exists");
  }
  assertTrue(result.payload === previous, "expected unchanged polling to return the previous payload instance");
});

run("resolveSessionLivePayload requests full fetch when unchanged response has no prior payload", () => {
  const live = {
    changed: false,
    ok: true,
    session_revision: 10,
    session_view_token: "live-token",
  } satisfies SessionUnchangedPayload;
  const result = resolveSessionLivePayload(undefined, live);
  assertTrue(result.state === "needs-refresh", "expected needs-refresh when there is no prior payload");
});

run("resolveSessionLivePayload returns live response when payload has changes", () => {
  const previous = sessionPayload({ session_revision: 1 });
  const live = sessionPayload({ session_revision: 2 });
  const result = resolveSessionLivePayload(previous, live);

  if (result.state !== "full") {
    throw new Error("expected full payload when response is not unchanged");
  }
  assertTrue(result.payload === live, "expected full response payload to be returned");
});

run("coerceSessionPane forces session tab when DM permission is removed", () => {
  assertTrue(coerceSessionPane("dm", false) === "session", "non-DM user should be forced to Session pane");
  assertTrue(coerceSessionPane("character", false) === "character", "non-DM user on non-DM pane should stay there");
  assertTrue(coerceSessionPane("dm", true) === "dm", "DM user should keep DM pane");
});

run("isAuthRequiredFromError identifies 401 responses", () => {
  const unauthorized = new ApiError({ message: "Unauthorized", code: "api_error", status: 401 });
  const forbidden = new ApiError({ message: "Forbidden", code: "api_error", status: 403 });
  assertTrue(isAuthRequiredFromError(unauthorized), "401 should require auth");
  assertTrue(!isAuthRequiredFromError(forbidden), "403 should not trigger auth-required");
  assertTrue(!isAuthRequiredFromError(new Error("network")), "non-ApiError should not trigger auth-required");
});

run("isSessionUnchangedPayload type guard only matches unchanged live payload marker", () => {
  const unchanged: SessionLiveStatePayload = {
    changed: false,
    ok: true,
    session_revision: 3,
    session_view_token: "token",
  };
  const changed: SessionLiveStatePayload = sessionPayload({ changed: true });
  assertTrue(isSessionUnchangedPayload(unchanged), "changed=false payload should be detected as unchanged");
  assertTrue(!isSessionUnchangedPayload(changed), "changed payloads should not be treated as unchanged");
});

if (failures > 0) {
  throw new Error(`${failures} test(s) failed`);
}
