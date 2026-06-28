import { existsSync } from "node:fs";

import Database from "better-sqlite3";

export type SqliteDatabase = Database.Database;
export type SqliteOpenOptions = Database.Options;

export const SQLITE_BUSY_TIMEOUT_MS = 30_000;
export const SQLITE_JOURNAL_MODE = "WAL";
export const SQLITE_SYNCHRONOUS = "NORMAL";

export interface SqliteSchemaRequirements {
  tables: readonly string[];
  columns: Readonly<Record<string, readonly string[]>>;
  indexes: readonly string[];
}

export interface SqliteSchemaInspection {
  dbPath: string;
  mode: "readonly";
  ok: boolean;
  schema: {
    required: {
      tables: number;
      columns: number;
      indexes: number;
    };
    present: {
      tables: number;
      columns: number;
      indexes: number;
    };
    missing: string[];
  };
  pragmas: {
    connection: {
      foreign_keys: {
        expected: 1;
        actual: number;
        ok: boolean;
      };
      busy_timeout_ms: {
        expected: typeof SQLITE_BUSY_TIMEOUT_MS;
        actual: number;
        ok: boolean;
      };
    };
    observed_database: {
      journal_mode: string;
      synchronous: number;
    };
    writable_open_policy: {
      journal_mode: typeof SQLITE_JOURNAL_MODE;
      synchronous: typeof SQLITE_SYNCHRONOUS;
      applied_by_readonly_check: false;
    };
  } | null;
  note: string;
}

export const CURRENT_SQLITE_SCHEMA_REQUIREMENTS: SqliteSchemaRequirements = {
  tables: [
    "users",
    "user_preferences",
    "campaign_memberships",
    "campaign_visibility_settings",
    "character_assignments",
    "invite_tokens",
    "password_reset_tokens",
    "sessions",
    "api_tokens",
    "auth_audit_log",
    "character_state",
    "campaign_sessions",
    "campaign_session_states",
    "campaign_session_articles",
    "campaign_session_article_images",
    "campaign_session_messages",
    "campaign_dm_statblocks",
    "campaign_dm_condition_definitions",
    "campaign_combatants",
    "campaign_combat_trackers",
    "campaign_combat_conditions",
    "campaign_combatant_resource_counters",
    "campaign_combatant_resource_notes",
    "systems_libraries",
    "systems_sources",
    "systems_import_runs",
    "systems_entries",
    "systems_shared_entry_edit_events",
    "systems_entry_links",
    "campaign_system_policies",
    "campaign_enabled_sources",
    "campaign_entry_overrides",
    "campaign_pages",
    "campaign_page_sync_state",
  ],
  columns: {
    users: ["id", "email", "display_name", "is_admin", "status", "auth_version"],
    user_preferences: ["user_id", "theme_key", "session_chat_order", "frontend_mode", "updated_at"],
    campaign_memberships: ["id", "user_id", "campaign_slug", "role", "status"],
    campaign_visibility_settings: ["campaign_slug", "scope", "visibility", "updated_by_user_id"],
    character_assignments: ["id", "user_id", "campaign_slug", "character_slug", "assignment_type"],
    invite_tokens: ["id", "user_id", "token_hash", "expires_at", "used_at", "created_by_user_id"],
    password_reset_tokens: ["id", "user_id", "token_hash", "expires_at", "used_at", "created_by_user_id"],
    sessions: ["id", "user_id", "token_hash", "last_seen_at", "expires_at", "revoked_at"],
    api_tokens: ["id", "user_id", "label", "token_hash", "last_used_at", "expires_at", "revoked_at"],
    auth_audit_log: ["id", "actor_user_id", "target_user_id", "campaign_slug", "character_slug", "event_type"],
    character_state: ["campaign_slug", "character_slug", "revision", "state_json", "updated_by_user_id"],
    campaign_sessions: ["id", "campaign_slug", "status", "started_at", "ended_at", "started_by_user_id", "ended_by_user_id"],
    campaign_session_states: ["campaign_slug", "revision", "updated_at", "updated_by_user_id"],
    campaign_session_articles: ["id", "campaign_slug", "status", "source_page_ref", "created_by_user_id", "revealed_by_user_id"],
    campaign_session_article_images: ["article_id", "filename", "media_type", "data_blob", "updated_at"],
    campaign_session_messages: ["id", "session_id", "author_user_id", "recipient_scope", "recipient_user_id", "body_text", "created_at"],
    campaign_dm_statblocks: ["id", "campaign_slug", "title", "subsection", "body_markdown", "updated_by_user_id"],
    campaign_dm_condition_definitions: ["id", "campaign_slug", "name", "description_markdown", "updated_by_user_id"],
    campaign_combatants: [
      "id",
      "campaign_slug",
      "combatant_type",
      "character_slug",
      "player_detail_visible",
      "source_kind",
      "source_ref",
      "display_name",
      "turn_value",
      "dexterity_modifier",
      "initiative_priority",
      "revision",
      "updated_by_user_id",
    ],
    campaign_combat_trackers: ["campaign_slug", "round_number", "current_combatant_id", "revision", "updated_by_user_id"],
    campaign_combat_conditions: ["id", "combatant_id", "name", "duration_text", "created_at"],
    campaign_combatant_resource_counters: [
      "id",
      "combatant_id",
      "resource_key",
      "label",
      "current_value",
      "max_value",
      "reset_label",
      "source_label",
      "updated_by_user_id",
    ],
    campaign_combatant_resource_notes: ["id", "combatant_id", "label", "note", "source_label", "created_by_user_id"],
    systems_libraries: ["library_slug", "title", "system_code", "status"],
    systems_sources: ["id", "library_slug", "source_id", "title", "license_class", "public_visibility_allowed", "status"],
    systems_import_runs: ["id", "library_slug", "source_id", "status", "summary_json", "started_by_user_id"],
    systems_entries: ["id", "library_slug", "source_id", "entry_key", "entry_type", "slug", "title", "metadata_json", "body_json"],
    systems_shared_entry_edit_events: ["id", "campaign_slug", "library_slug", "source_id", "entry_key", "entry_slug", "actor_user_id", "created_at"],
    systems_entry_links: ["id", "library_slug", "from_entry_key", "to_entry_key", "relation_type"],
    campaign_system_policies: [
      "campaign_slug",
      "library_slug",
      "status",
      "allow_dm_shared_core_entry_edits",
      "updated_by_user_id",
    ],
    campaign_enabled_sources: ["campaign_slug", "library_slug", "source_id", "is_enabled", "default_visibility", "updated_by_user_id"],
    campaign_entry_overrides: ["campaign_slug", "library_slug", "entry_key", "visibility_override", "is_enabled_override", "updated_by_user_id"],
    campaign_pages: ["campaign_slug", "page_ref", "route_slug", "section", "subsection", "title", "body_markdown", "metadata_json"],
    campaign_page_sync_state: ["campaign_slug", "seeded_at"],
  },
  indexes: [
    "idx_api_tokens_user",
    "idx_campaign_sessions_active",
    "idx_campaign_session_articles_campaign_status",
    "idx_campaign_session_messages_session",
    "idx_campaign_session_messages_session_recipient",
    "idx_campaign_dm_statblocks_campaign",
    "idx_campaign_dm_condition_definitions_campaign",
    "idx_campaign_combatants_campaign_order",
    "idx_campaign_combatants_campaign_order_v2",
    "idx_campaign_combat_conditions_combatant",
    "idx_campaign_combatant_resource_counters_combatant",
    "idx_campaign_combatant_resource_notes_combatant",
    "idx_systems_sources_library",
    "idx_systems_import_runs_library_source",
    "idx_systems_entries_source",
    "idx_systems_entries_search",
    "idx_systems_shared_entry_edit_events_entry",
    "idx_campaign_enabled_sources_campaign",
    "idx_campaign_entry_overrides_campaign",
    "idx_campaign_pages_campaign_route",
    "idx_campaign_pages_campaign_section",
  ],
};

export class SqliteStartupSchemaError extends Error {
  readonly dbPath: string;
  readonly missing: string[];

  constructor(dbPath: string, missing: string[]) {
    super(formatSqliteStartupSchemaError(dbPath, missing));
    this.name = "SqliteStartupSchemaError";
    this.dbPath = dbPath;
    this.missing = missing;
  }
}

function sqliteIdentifier(value: string): string {
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(value)) {
    throw new Error(`Unsafe SQLite identifier: ${value}`);
  }
  return `"${value}"`;
}

function normalizeSqliteNameRow(row: unknown): string {
  if (typeof row === "object" && row !== null && "name" in row) {
    return String((row as { name?: unknown }).name || "");
  }
  return "";
}

function formatSqliteStartupSchemaError(dbPath: string, missing: string[]): string {
  return [
    `TypeScript API SQLite startup preflight failed for ${dbPath}.`,
    `Missing schema items: ${missing.join(", ") || "unknown"}.`,
    "Current transitional startup posture: run Flask `manage.py init-db` against this SQLite database before starting the TypeScript API.",
  ].join(" ");
}

function countRequiredColumns(requirements: SqliteSchemaRequirements): number {
  return Object.values(requirements.columns).reduce((total, columnNames) => total + columnNames.length, 0);
}

function readSimplePragma(database: SqliteDatabase, pragmaName: string): unknown {
  return database.pragma(pragmaName, { simple: true });
}

function readNumberPragma(database: SqliteDatabase, pragmaName: string): number {
  return Number(readSimplePragma(database, pragmaName));
}

function readStringPragma(database: SqliteDatabase, pragmaName: string): string {
  return String(readSimplePragma(database, pragmaName) || "");
}

export function applySqliteConnectionPragmas(database: SqliteDatabase, options: SqliteOpenOptions = {}): void {
  database.pragma("foreign_keys = ON");
  database.pragma(`busy_timeout = ${SQLITE_BUSY_TIMEOUT_MS}`);
  if (!options.readonly) {
    database.pragma(`journal_mode = ${SQLITE_JOURNAL_MODE}`);
    database.pragma(`synchronous = ${SQLITE_SYNCHRONOUS}`);
  }
}

export function openSqliteDatabase(filename: string, options: SqliteOpenOptions = {}): SqliteDatabase {
  const database = new Database(filename, options);
  applySqliteConnectionPragmas(database, options);
  return database;
}

export function listMissingSqliteSchema(
  database: SqliteDatabase,
  requirements: SqliteSchemaRequirements = CURRENT_SQLITE_SCHEMA_REQUIREMENTS,
): string[] {
  const tableRows = database.prepare("SELECT name FROM sqlite_master WHERE type = 'table'").all();
  const tableNames = new Set(tableRows.map(normalizeSqliteNameRow).filter(Boolean));
  const missing: string[] = [];

  for (const tableName of requirements.tables) {
    if (!tableNames.has(tableName)) {
      missing.push(`table ${tableName}`);
    }
  }

  for (const [tableName, columnNames] of Object.entries(requirements.columns)) {
    if (!tableNames.has(tableName)) {
      continue;
    }
    const columnRows = database.prepare(`PRAGMA table_info(${sqliteIdentifier(tableName)})`).all() as Array<{ name?: string }>;
    const existingColumns = new Set(columnRows.map((row) => String(row.name || "")).filter(Boolean));
    for (const columnName of columnNames) {
      if (!existingColumns.has(columnName)) {
        missing.push(`column ${tableName}.${columnName}`);
      }
    }
  }

  const indexRows = database.prepare("SELECT name FROM sqlite_master WHERE type = 'index'").all();
  const indexNames = new Set(indexRows.map(normalizeSqliteNameRow).filter(Boolean));
  for (const indexName of requirements.indexes) {
    if (!indexNames.has(indexName)) {
      missing.push(`index ${indexName}`);
    }
  }

  return missing;
}

export function inspectSqliteSchema(
  dbPath: string,
  requirements: SqliteSchemaRequirements = CURRENT_SQLITE_SCHEMA_REQUIREMENTS,
): SqliteSchemaInspection {
  const required = {
    tables: requirements.tables.length,
    columns: countRequiredColumns(requirements),
    indexes: requirements.indexes.length,
  };

  if (!existsSync(dbPath)) {
    return {
      dbPath,
      mode: "readonly",
      ok: false,
      schema: {
        required,
        present: {
          tables: 0,
          columns: 0,
          indexes: 0,
        },
        missing: ["database file"],
      },
      pragmas: null,
      note: "Read-only schema check did not open the database because the file is missing.",
    };
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true, readonly: true });
  try {
    const missing = listMissingSqliteSchema(database, requirements);
    const missingTables = missing.filter((item) => item.startsWith("table ")).length;
    const missingColumns = missing.filter((item) => item.startsWith("column ")).length;
    const missingIndexes = missing.filter((item) => item.startsWith("index ")).length;
    const foreignKeys = readNumberPragma(database, "foreign_keys");
    const busyTimeoutMs = readNumberPragma(database, "busy_timeout");
    const pragmaFailures = [
      foreignKeys === 1 ? "" : "PRAGMA foreign_keys",
      busyTimeoutMs === SQLITE_BUSY_TIMEOUT_MS ? "" : "PRAGMA busy_timeout",
    ].filter(Boolean);

    return {
      dbPath,
      mode: "readonly",
      ok: missing.length === 0 && pragmaFailures.length === 0,
      schema: {
        required,
        present: {
          tables: required.tables - missingTables,
          columns: required.columns - missingColumns,
          indexes: required.indexes - missingIndexes,
        },
        missing: [...missing, ...pragmaFailures],
      },
      pragmas: {
        connection: {
          foreign_keys: {
            expected: 1,
            actual: foreignKeys,
            ok: foreignKeys === 1,
          },
          busy_timeout_ms: {
            expected: SQLITE_BUSY_TIMEOUT_MS,
            actual: busyTimeoutMs,
            ok: busyTimeoutMs === SQLITE_BUSY_TIMEOUT_MS,
          },
        },
        observed_database: {
          journal_mode: readStringPragma(database, "journal_mode"),
          synchronous: readNumberPragma(database, "synchronous"),
        },
        writable_open_policy: {
          journal_mode: SQLITE_JOURNAL_MODE,
          synchronous: SQLITE_SYNCHRONOUS,
          applied_by_readonly_check: false,
        },
      },
      note: "Read-only schema check; no migrations, PRAGMA journal changes, or schema writes were run.",
    };
  } finally {
    database.close();
  }
}

export function assertSqliteStartupSchema(dbPath: string): void {
  if (!existsSync(dbPath)) {
    throw new SqliteStartupSchemaError(dbPath, ["database file"]);
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true });
  try {
    const missing = listMissingSqliteSchema(database);
    if (missing.length > 0) {
      throw new SqliteStartupSchemaError(dbPath, missing);
    }
  } finally {
    database.close();
  }
}
