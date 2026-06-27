import { createHash, randomBytes } from "node:crypto";
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

export interface CharacterAssignment {
  id: number;
  user_id: number;
  campaign_slug: string;
  character_slug: string;
  assignment_type: string;
  created_at: string;
  updated_at: string;
}

export interface ApiTokenAuthContext {
  authSource: "api_token";
  user: AuthUser;
  memberships: AuthMembership[];
  preferences: AuthPreferences;
  viewAsUserChoices: ViewAsChoice[];
}

export type AuthRouteRole = "player" | "dm" | "admin";

export type ApiTokenAuthResult =
  | { kind: "missing" }
  | { kind: "invalid" }
  | { kind: "authenticated"; context: ApiTokenAuthContext };

export type AccountSettingsUpdateResult =
  | { status: "ok"; preferences: AuthPreferences }
  | { status: "validation_error"; message: string };

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
  password_hash?: string | null;
  auth_version?: number | string | null;
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

interface CharacterAssignmentRow {
  id: number;
  user_id: number;
  campaign_slug: string;
  character_slug: string;
  assignment_type: string;
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
const DEFAULT_API_TOKEN_TOUCH_INTERVAL_SECONDS = 300;

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

function utcIsoTimestamp(date = new Date()): string {
  return date.toISOString().replace("Z", "+00:00");
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

function apiTokenTouchIntervalMs(): number {
  const configured = Number(process.env.PLAYER_WIKI_SESSION_TOUCH_INTERVAL_SECONDS || "");
  const intervalSeconds = Number.isFinite(configured) && configured >= 0
    ? configured
    : DEFAULT_API_TOKEN_TOUCH_INTERVAL_SECONDS;
  return intervalSeconds * 1000;
}

function touchApiTokenIfStale(database: SqliteDatabase, tokenRow: ApiTokenRow, nowMs: number): void {
  const lastUsedAtMs = parseTimestampMs(tokenRow.last_used_at);
  if (lastUsedAtMs !== null && nowMs - lastUsedAtMs < apiTokenTouchIntervalMs()) {
    return;
  }
  database
    .prepare("UPDATE api_tokens SET last_used_at = ? WHERE id = ?")
    .run(utcIsoTimestamp(new Date(nowMs)), tokenRow.id);
}

function normalizeThemeKey(value: unknown): string {
  const normalized = String(value || "").trim().toLowerCase();
  return VALID_THEME_KEYS.has(normalized) ? normalized : DEFAULT_PREFERENCES.theme_key;
}

function isValidThemeKey(value: unknown): boolean {
  return VALID_THEME_KEYS.has(String(value || "").trim().toLowerCase());
}

function normalizeSessionChatOrder(value: unknown): string {
  const normalized = String(value || "").trim().toLowerCase();
  return VALID_SESSION_CHAT_ORDERS.has(normalized) ? normalized : DEFAULT_PREFERENCES.session_chat_order;
}

function isValidSessionChatOrder(value: unknown): boolean {
  return VALID_SESSION_CHAT_ORDERS.has(String(value || "").trim().toLowerCase());
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

function serializeCharacterAssignment(row: CharacterAssignmentRow): CharacterAssignment {
  return {
    id: Number(row.id),
    user_id: Number(row.user_id),
    campaign_slug: String(row.campaign_slug),
    character_slug: String(row.character_slug),
    assignment_type: String(row.assignment_type || "owner"),
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

function setUserThemeKey(database: SqliteDatabase, userId: number, themeKey: string, now: string) {
  database
    .prepare(
      `INSERT INTO user_preferences (
        user_id,
        theme_key,
        session_chat_order,
        frontend_mode,
        updated_at
      ) VALUES (?, ?, ?, ?, ?)
      ON CONFLICT(user_id) DO UPDATE SET
        theme_key = excluded.theme_key,
        updated_at = excluded.updated_at`,
    )
    .run(userId, normalizeThemeKey(themeKey), DEFAULT_PREFERENCES.session_chat_order, DEFAULT_PREFERENCES.frontend_mode, now);
}

function setUserSessionChatOrder(database: SqliteDatabase, userId: number, sessionChatOrder: string, now: string) {
  database
    .prepare(
      `INSERT INTO user_preferences (
        user_id,
        theme_key,
        session_chat_order,
        frontend_mode,
        updated_at
      ) VALUES (?, ?, ?, ?, ?)
      ON CONFLICT(user_id) DO UPDATE SET
        session_chat_order = excluded.session_chat_order,
        updated_at = excluded.updated_at`,
    )
    .run(
      userId,
      DEFAULT_PREFERENCES.theme_key,
      normalizeSessionChatOrder(sessionChatOrder),
      DEFAULT_PREFERENCES.frontend_mode,
      now,
    );
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

  const database = new Database(dbPath, { fileMustExist: true });
  try {
    const nowMs = Date.now();
    const tokenRow = database
      .prepare("SELECT * FROM api_tokens WHERE token_hash = ?")
      .get(hashToken(parsedToken.token)) as ApiTokenRow | undefined;
    if (!tokenRow || !tokenIsActive(tokenRow, nowMs)) {
      return { kind: "invalid" };
    }

    const userRow = database.prepare("SELECT * FROM users WHERE id = ?").get(tokenRow.user_id) as UserRow | undefined;
    if (!userRow || String(userRow.status) !== "active") {
      return { kind: "invalid" };
    }

    const user = serializeUser(userRow);
    touchApiTokenIfStale(database, tokenRow, nowMs);
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

export function updateApiTokenAccountSettings(
  dbPath: string,
  authContext: ApiTokenAuthContext,
  payload: Record<string, unknown>,
): AccountSettingsUpdateResult {
  const requestedThemeKey = Object.hasOwn(payload, "theme_key") ? payload.theme_key : "";
  const requestedChatOrder = Object.hasOwn(payload, "session_chat_order") ? payload.session_chat_order : "";
  const hasThemeUpdate = Boolean(String(requestedThemeKey).trim());
  const hasChatOrderUpdate = Boolean(String(requestedChatOrder).trim());

  if (Object.hasOwn(payload, "frontend_mode")) {
    return {
      status: "validation_error",
      message: "Preferred frontend selection is no longer available.",
    };
  }

  if (!hasThemeUpdate && !hasChatOrderUpdate) {
    return {
      status: "validation_error",
      message: "No account settings were provided.",
    };
  }

  if (hasThemeUpdate && !isValidThemeKey(requestedThemeKey)) {
    return {
      status: "validation_error",
      message: "Choose a valid theme preset.",
    };
  }

  if (hasChatOrderUpdate && !isValidSessionChatOrder(requestedChatOrder)) {
    return {
      status: "validation_error",
      message: "Choose a valid live session chat order.",
    };
  }

  const database = new Database(dbPath, { fileMustExist: true });
  try {
    const currentPreferences = loadPreferences(database, authContext.user.id);
    const normalizedThemeKey = hasThemeUpdate ? normalizeThemeKey(requestedThemeKey) : currentPreferences.theme_key;
    const normalizedChatOrder = hasChatOrderUpdate
      ? normalizeSessionChatOrder(requestedChatOrder)
      : currentPreferences.session_chat_order;
    const now = utcIsoTimestamp();

    const writePreferences = database.transaction(() => {
      if (hasThemeUpdate && normalizedThemeKey !== currentPreferences.theme_key) {
        setUserThemeKey(database, authContext.user.id, normalizedThemeKey, now);
      }
      if (hasChatOrderUpdate && normalizedChatOrder !== currentPreferences.session_chat_order) {
        setUserSessionChatOrder(database, authContext.user.id, normalizedChatOrder, now);
      }
    });

    writePreferences();

    return {
      status: "ok",
      preferences: loadPreferences(database, authContext.user.id),
    };
  } finally {
    database.close();
  }
}

export function apiTokenRoleForCampaign(authContext: ApiTokenAuthContext, campaignSlug: string): AuthRouteRole | null {
  if (authContext.user.is_admin) {
    return "admin";
  }

  const membership = authContext.memberships.find(
    (item) => item.campaign_slug === campaignSlug && item.status === "active",
  );
  if (membership?.role === "dm" || membership?.role === "player") {
    return membership.role;
  }
  return null;
}

export function getActiveUserById(dbPath: string, userId: number): AuthUser | null {
  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    const row = database
      .prepare("SELECT * FROM users WHERE id = ? AND status = 'active'")
      .get(userId) as UserRow | undefined;
    return row ? serializeUser(row) : null;
  } finally {
    database.close();
  }
}

export function getUserById(dbPath: string, userId: number): AuthUser | null {
  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    const row = database
      .prepare("SELECT * FROM users WHERE id = ?")
      .get(userId) as UserRow | undefined;
    return row ? serializeUser(row) : null;
  } finally {
    database.close();
  }
}

export function disableUser(dbPath: string, userId: number): AuthUser {
  const database = new Database(dbPath, { fileMustExist: true });
  try {
    const now = utcIsoTimestamp();
    const writeUser = database.transaction(() => {
      database
        .prepare(
          `UPDATE users
           SET status = 'disabled',
               auth_version = COALESCE(auth_version, 0) + 1,
               updated_at = ?
           WHERE id = ?`,
        )
        .run(now, userId);
      return database.prepare("SELECT * FROM users WHERE id = ?").get(userId) as UserRow | undefined;
    });
    const row = writeUser();
    if (!row) {
      throw new Error("User was not readable after disable.");
    }
    return serializeUser(row);
  } finally {
    database.close();
  }
}

export function enableUser(dbPath: string, userId: number): AuthUser {
  const database = new Database(dbPath, { fileMustExist: true });
  try {
    const now = utcIsoTimestamp();
    const writeUser = database.transaction(() => {
      const current = database.prepare("SELECT * FROM users WHERE id = ?").get(userId) as UserRow | undefined;
      if (!current) {
        return undefined;
      }
      const enabledStatus = String(current.password_hash || "").trim() ? "active" : "invited";
      database
        .prepare(
          `UPDATE users
           SET status = ?,
               auth_version = COALESCE(auth_version, 0) + 1,
               updated_at = ?
           WHERE id = ?`,
        )
        .run(enabledStatus, now, userId);
      return database.prepare("SELECT * FROM users WHERE id = ?").get(userId) as UserRow | undefined;
    });
    const row = writeUser();
    if (!row) {
      throw new Error("User was not readable after enable.");
    }
    return serializeUser(row);
  } finally {
    database.close();
  }
}

export function revokeAllUserSessions(dbPath: string, userId: number): void {
  const database = new Database(dbPath, { fileMustExist: true });
  try {
    database
      .prepare("UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL")
      .run(utcIsoTimestamp(), userId);
  } finally {
    database.close();
  }
}

export function revokeAllUserApiTokens(dbPath: string, userId: number): void {
  const database = new Database(dbPath, { fileMustExist: true });
  try {
    database
      .prepare("UPDATE api_tokens SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL")
      .run(utcIsoTimestamp(), userId);
  } finally {
    database.close();
  }
}

export function hasActivePlayerMembership(dbPath: string, userId: number, campaignSlug: string): boolean {
  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    const row = database
      .prepare(
        `SELECT id
         FROM campaign_memberships
         WHERE user_id = ?
           AND campaign_slug = ?
           AND role = 'player'
           AND status = 'active'
         LIMIT 1`,
      )
      .get(userId, campaignSlug);
    return Boolean(row);
  } finally {
    database.close();
  }
}

export function getMembership(
  dbPath: string,
  userId: number,
  campaignSlug: string,
  statuses: string[] | null = ["active"],
): AuthMembership | null {
  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    const row = database
      .prepare("SELECT * FROM campaign_memberships WHERE user_id = ? AND campaign_slug = ?")
      .get(userId, campaignSlug) as MembershipRow | undefined;
    if (!row) {
      return null;
    }
    const membership = serializeMembership(row);
    if (statuses !== null && !statuses.includes(membership.status)) {
      return null;
    }
    return membership;
  } finally {
    database.close();
  }
}

export function upsertMembership(
  dbPath: string,
  userId: number,
  campaignSlug: string,
  {
    role,
    status = "active",
  }: {
    role: string;
    status?: string;
  },
): AuthMembership {
  const database = new Database(dbPath, { fileMustExist: true });
  try {
    const now = utcIsoTimestamp();
    const writeMembership = database.transaction(() => {
      const existing = database
        .prepare("SELECT * FROM campaign_memberships WHERE user_id = ? AND campaign_slug = ?")
        .get(userId, campaignSlug) as MembershipRow | undefined;
      if (!existing) {
        database
          .prepare(
            `INSERT INTO campaign_memberships (
              user_id,
              campaign_slug,
              role,
              status,
              created_at,
              updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)`,
          )
          .run(userId, campaignSlug, role, status, now, now);
      } else {
        database
          .prepare(
            `UPDATE campaign_memberships
             SET role = ?, status = ?, updated_at = ?
             WHERE user_id = ? AND campaign_slug = ?`,
          )
          .run(role, status, now, userId, campaignSlug);
      }
      return database
        .prepare("SELECT * FROM campaign_memberships WHERE user_id = ? AND campaign_slug = ?")
        .get(userId, campaignSlug) as MembershipRow | undefined;
    });
    const row = writeMembership();
    if (!row) {
      throw new Error("Membership was not readable after write.");
    }
    return serializeMembership(row);
  } finally {
    database.close();
  }
}

export function listActivePlayerMembershipUsers(dbPath: string, campaignSlug: string): AuthUser[] {
  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    const rows = database
      .prepare(
        `SELECT users.*
         FROM users
         JOIN campaign_memberships ON campaign_memberships.user_id = users.id
         WHERE campaign_memberships.campaign_slug = ?
           AND campaign_memberships.role = 'player'
           AND campaign_memberships.status = 'active'
           AND users.status = 'active'
         ORDER BY users.email ASC`,
      )
      .all(campaignSlug) as UserRow[];
    return rows.map(serializeUser);
  } finally {
    database.close();
  }
}

export function getCharacterAssignment(
  dbPath: string,
  campaignSlug: string,
  characterSlug: string,
): CharacterAssignment | null {
  const database = new Database(dbPath, { fileMustExist: true, readonly: true });
  try {
    const row = database
      .prepare("SELECT * FROM character_assignments WHERE campaign_slug = ? AND character_slug = ?")
      .get(campaignSlug, characterSlug) as CharacterAssignmentRow | undefined;
    return row ? serializeCharacterAssignment(row) : null;
  } finally {
    database.close();
  }
}

export function upsertCharacterAssignment(
  dbPath: string,
  userId: number,
  campaignSlug: string,
  characterSlug: string,
): CharacterAssignment {
  const database = new Database(dbPath, { fileMustExist: true });
  try {
    const now = utcIsoTimestamp();
    const writeAssignment = database.transaction(() => {
      database
        .prepare(
          `INSERT INTO character_assignments (
            user_id,
            campaign_slug,
            character_slug,
            assignment_type,
            created_at,
            updated_at
          ) VALUES (?, ?, ?, 'owner', ?, ?)
          ON CONFLICT(campaign_slug, character_slug) DO UPDATE SET
            user_id = excluded.user_id,
            assignment_type = excluded.assignment_type,
            updated_at = excluded.updated_at`,
        )
        .run(userId, campaignSlug, characterSlug, now, now);
      return database
        .prepare("SELECT * FROM character_assignments WHERE campaign_slug = ? AND character_slug = ?")
        .get(campaignSlug, characterSlug) as CharacterAssignmentRow | undefined;
    });
    const row = writeAssignment();
    if (!row) {
      throw new Error("Character assignment was not readable after write.");
    }
    return serializeCharacterAssignment(row);
  } finally {
    database.close();
  }
}

export function deleteCharacterAssignment(
  dbPath: string,
  campaignSlug: string,
  characterSlug: string,
): CharacterAssignment | null {
  const database = new Database(dbPath, { fileMustExist: true });
  try {
    const deleteAssignment = database.transaction(() => {
      const row = database
        .prepare("SELECT * FROM character_assignments WHERE campaign_slug = ? AND character_slug = ?")
        .get(campaignSlug, characterSlug) as CharacterAssignmentRow | undefined;
      if (!row) {
        return null;
      }
      const result = database
        .prepare("DELETE FROM character_assignments WHERE campaign_slug = ? AND character_slug = ?")
        .run(campaignSlug, characterSlug);
      return result.changes > 0 ? row : null;
    });
    const row = deleteAssignment();
    return row ? serializeCharacterAssignment(row) : null;
  } finally {
    database.close();
  }
}

export function issuePasswordResetToken(
  dbPath: string,
  userId: number,
  {
    ttlHours,
    createdByUserId,
  }: {
    ttlHours: number;
    createdByUserId: number | null;
  },
): string {
  const database = new Database(dbPath, { fileMustExist: true });
  try {
    const rawToken = randomBytes(32).toString("base64url");
    const nowDate = new Date();
    const now = utcIsoTimestamp(nowDate);
    const expiresAt = utcIsoTimestamp(new Date(nowDate.getTime() + ttlHours * 60 * 60 * 1000));
    const writeToken = database.transaction(() => {
      database
        .prepare("UPDATE password_reset_tokens SET used_at = ? WHERE user_id = ? AND used_at IS NULL")
        .run(now, userId);
      database
        .prepare(
          `INSERT INTO password_reset_tokens (
            user_id,
            token_hash,
            expires_at,
            used_at,
            created_by_user_id,
            created_at
          ) VALUES (?, ?, ?, NULL, ?, ?)`,
        )
        .run(userId, hashToken(rawToken), expiresAt, createdByUserId, now);
    });
    writeToken();
    return rawToken;
  } finally {
    database.close();
  }
}

export function insertAuthAuditLog(
  dbPath: string,
  {
    actorUserId,
    targetUserId,
    campaignSlug,
    characterSlug,
    eventType,
    metadata,
  }: {
    actorUserId: number | null;
    targetUserId: number | null;
    campaignSlug: string | null;
    characterSlug: string | null;
    eventType: string;
    metadata: Record<string, unknown>;
  },
): void {
  const database = new Database(dbPath, { fileMustExist: true });
  try {
    database
      .prepare(
        `INSERT INTO auth_audit_log (
          actor_user_id,
          target_user_id,
          campaign_slug,
          character_slug,
          event_type,
          metadata_json,
          created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)`,
      )
      .run(
        actorUserId,
        targetUserId,
        campaignSlug,
        characterSlug,
        eventType,
        JSON.stringify(metadata),
        utcIsoTimestamp(),
      );
  } finally {
    database.close();
  }
}
