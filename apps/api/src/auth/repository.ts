import { createHash } from "node:crypto";
import { existsSync } from "node:fs";

import Database from "better-sqlite3";

type SqliteDatabase = InstanceType<typeof Database>;

export interface AuthUser {
  id: number;
  email: string;
  display_name: string;
  is_admin: boolean;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface AuthMembership {
  id: number;
  campaign_slug: string;
  role: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface AuthPreferences {
  theme_key: string;
  session_chat_order: string;
  frontend_mode: string;
}

export interface ViewAsChoice {
  id: number;
  email: string;
  display_name: string;
  is_admin: boolean;
  status: string;
}

export interface ApiTokenAuthContext {
  authSource: "api_token";
  user: AuthUser;
  memberships: AuthMembership[];
  preferences: AuthPreferences;
  viewAsUserChoices: ViewAsChoice[];
}

export type ApiTokenAuthResult =
  | { kind: "missing" }
  | { kind: "invalid" }
  | { kind: "authenticated"; context: ApiTokenAuthContext };

interface ApiTokenRow {
  id: number;
  user_id: number;
  label: string;
  token_hash: string;
  created_at: string;
  last_used_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  created_by_user_id: number | null;
}

interface UserRow {
  id: number;
  email: string;
  display_name: string;
  is_admin: number | string | boolean;
  status: string;
  created_at: string;
  updated_at: string;
}

interface MembershipRow {
  id: number;
  user_id: number;
  campaign_slug: string;
  role: string;
  status: string;
  created_at: string;
  updated_at: string;
}

type PreferenceRow = Record<string, unknown> & {
  user_id?: number;
  theme_key?: string | null;
  session_chat_order?: string | null;
  frontend_mode?: string | null;
};

const DEFAULT_PREFERENCES: AuthPreferences = {
  theme_key: "parchment",
  session_chat_order: "newest_first",
  frontend_mode: "gen2",
};

const VALID_THEME_KEYS = new Set(["parchment", "moonlit", "verdant", "ember"]);
const VALID_SESSION_CHAT_ORDERS = new Set(["newest_first", "oldest_first"]);
const VALID_FRONTEND_MODES = new Set(["gen2"]);

function parseBearerToken(authorizationHeader: string | undefined): { present: boolean; token: string | null } {
  const rawHeader = (authorizationHeader || "").trim();
  if (!rawHeader) {
    return { present: false, token: null };
  }

  const separatorIndex = rawHeader.indexOf(" ");
  const scheme = separatorIndex === -1 ? rawHeader : rawHeader.slice(0, separatorIndex);
  const credentials = separatorIndex === -1 ? "" : rawHeader.slice(separatorIndex + 1).trim();
  if (scheme.toLowerCase() !== "bearer") {
    return { present: false, token: null };
  }

  return { present: true, token: credentials || null };
}

function hashToken(rawToken: string): string {
  return createHash("sha256").update(rawToken, "utf8").digest("hex");
}

function parseTimestampMs(rawValue: string | null | undefined): number | null {
  const value = String(rawValue || "").trim();
  if (!value) {
    return null;
  }
  const normalized = /(?:z|[+-]\d\d:\d\d)$/i.test(value) ? value : `${value}Z`;
  const timestamp = Date.parse(normalized);
  return Number.isFinite(timestamp) ? timestamp : null;
}

function tokenIsActive(row: ApiTokenRow, nowMs: number): boolean {
  if (String(row.revoked_at || "").trim()) {
    return false;
  }

  const expiresAtMs = parseTimestampMs(row.expires_at);
  return expiresAtMs === null || expiresAtMs > nowMs;
}

function normalizeThemeKey(value: unknown): string {
  const normalized = String(value || "").trim().toLowerCase();
  return VALID_THEME_KEYS.has(normalized) ? normalized : DEFAULT_PREFERENCES.theme_key;
}

function normalizeSessionChatOrder(value: unknown): string {
  const normalized = String(value || "").trim().toLowerCase();
  return VALID_SESSION_CHAT_ORDERS.has(normalized) ? normalized : DEFAULT_PREFERENCES.session_chat_order;
}

function normalizeFrontendMode(value: unknown): string {
  const normalized = String(value || "").trim().toLowerCase();
  return VALID_FRONTEND_MODES.has(normalized) ? normalized : DEFAULT_PREFERENCES.frontend_mode;
}

function serializeUser(row: UserRow): AuthUser {
  return {
    id: Number(row.id),
    email: String(row.email),
    display_name: String(row.display_name),
    is_admin: Boolean(Number(row.is_admin)),
    status: String(row.status),
    created_at: String(row.created_at),
    updated_at: String(row.updated_at),
  };
}

function serializeMembership(row: MembershipRow): AuthMembership {
  return {
    id: Number(row.id),
    campaign_slug: String(row.campaign_slug),
    role: String(row.role),
    status: String(row.status),
    created_at: String(row.created_at),
    updated_at: String(row.updated_at),
  };
}

function serializeViewAsChoice(row: UserRow): ViewAsChoice {
  const user = serializeUser(row);
  return {
    id: user.id,
    email: user.email,
    display_name: user.display_name,
    is_admin: user.is_admin,
    status: user.status,
  };
}

function loadPreferences(database: SqliteDatabase, userId: number): AuthPreferences {
  const row = database
    .prepare("SELECT * FROM user_preferences WHERE user_id = ?")
    .get(userId) as PreferenceRow | undefined;
  if (!row) {
    return { ...DEFAULT_PREFERENCES };
  }
  return {
    theme_key: normalizeThemeKey(row.theme_key),
    session_chat_order: normalizeSessionChatOrder(row.session_chat_order),
    frontend_mode: normalizeFrontendMode(row.frontend_mode),
  };
}

function loadMemberships(database: SqliteDatabase, userId: number): AuthMembership[] {
  const rows = database
    .prepare("SELECT * FROM campaign_memberships WHERE user_id = ? ORDER BY campaign_slug ASC")
    .all(userId) as MembershipRow[];
  return rows.filter((row) => String(row.status) === "active").map(serializeMembership);
}

function loadViewAsChoices(database: SqliteDatabase, actor: AuthUser): ViewAsChoice[] {
  if (!actor.is_admin) {
    return [];
  }
  const rows = database
    .prepare("SELECT * FROM users WHERE status = 'active' ORDER BY email ASC")
    .all() as UserRow[];
  return rows.filter((row) => Number(row.id) !== actor.id).map(serializeViewAsChoice);
}

export function readApiTokenAuthContext(
  dbPath: string,
  authorizationHeader: string | undefined,
): ApiTokenAuthResult {
  const parsedToken = parseBearerToken(authorizationHeader);
  if (!parsedToken.present) {
    return { kind: "missing" };
  }
  if (!parsedToken.token || !existsSync(dbPath)) {
    return { kind: "invalid" };
  }

  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    const tokenRow = database
      .prepare("SELECT * FROM api_tokens WHERE token_hash = ?")
      .get(hashToken(parsedToken.token)) as ApiTokenRow | undefined;
    if (!tokenRow || !tokenIsActive(tokenRow, Date.now())) {
      return { kind: "invalid" };
    }

    const userRow = database.prepare("SELECT * FROM users WHERE id = ?").get(tokenRow.user_id) as UserRow | undefined;
    if (!userRow || String(userRow.status) !== "active") {
      return { kind: "invalid" };
    }

    const user = serializeUser(userRow);
    return {
      kind: "authenticated",
      context: {
        authSource: "api_token",
        user,
        memberships: loadMemberships(database, user.id),
        preferences: loadPreferences(database, user.id),
        viewAsUserChoices: loadViewAsChoices(database, user),
      },
    };
  } catch (error) {
    if (error instanceof Error && (error.message.includes("no such table") || error.message.includes("no such column"))) {
      return { kind: "invalid" };
    }
    throw error;
  } finally {
    database.close();
  }
}
