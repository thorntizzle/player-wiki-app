import { existsSync } from "node:fs";

import { openSqliteDatabase, type SqliteDatabase } from "../sqlite.js";

export interface SystemsImportRun {
  id: number;
  library_slug: string;
  source_id: string;
  status: string;
  import_version: string;
  source_path: string;
  summary: Record<string, unknown>;
  started_at: string;
  completed_at: string | null;
  started_by_user_id: number | null;
}

export interface SystemsImportRunFilters {
  librarySlug?: string | null;
  sourceId?: string | null;
  limit: number;
}

interface SystemsImportRunRow {
  id: number;
  library_slug: string;
  source_id: string;
  status: string;
  import_version: string | null;
  source_path: string | null;
  summary_json: string | null;
  started_at: string;
  completed_at: string | null;
  started_by_user_id: number | null;
}

function parseSummary(rawValue: string | null): Record<string, unknown> {
  if (!rawValue) {
    return {};
  }
  try {
    const parsed = JSON.parse(rawValue);
    if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    // Keep malformed legacy rows readable instead of failing the whole list.
  }
  return {};
}

function serializeImportRun(row: SystemsImportRunRow): SystemsImportRun {
  return {
    id: Number(row.id),
    library_slug: String(row.library_slug),
    source_id: String(row.source_id),
    status: String(row.status),
    import_version: String(row.import_version || ""),
    source_path: String(row.source_path || ""),
    summary: parseSummary(row.summary_json),
    started_at: String(row.started_at),
    completed_at: row.completed_at === null ? null : String(row.completed_at),
    started_by_user_id: row.started_by_user_id === null ? null : Number(row.started_by_user_id),
  };
}

const importRunSelectColumns = `
  id,
  library_slug,
  source_id,
  status,
  import_version,
  source_path,
  summary_json,
  started_at,
  completed_at,
  started_by_user_id
`;

export function listSystemsImportRuns(dbPath: string, filters: SystemsImportRunFilters): SystemsImportRun[] {
  if (!existsSync(dbPath)) {
    return [];
  }

  const clauses: string[] = [];
  const parameters: Array<string | number> = [];
  if (filters.librarySlug) {
    clauses.push("library_slug = ?");
    parameters.push(filters.librarySlug.trim());
  }
  if (filters.sourceId) {
    clauses.push("source_id = ?");
    parameters.push(filters.sourceId.trim().toUpperCase());
  }

  let query = `
    SELECT ${importRunSelectColumns}
    FROM systems_import_runs
  `;
  if (clauses.length > 0) {
    query += ` WHERE ${clauses.join(" AND ")}`;
  }
  query += " ORDER BY started_at DESC, id DESC LIMIT ?";
  parameters.push(Math.max(1, Math.trunc(filters.limit)));

  const database = openSqliteDatabase(dbPath, { fileMustExist: true, readonly: true });
  try {
    const rows = database.prepare(query).all(...parameters) as SystemsImportRunRow[];
    return rows.map(serializeImportRun);
  } catch (error) {
    if (error instanceof Error && error.message.includes("no such table")) {
      return [];
    }
    throw error;
  } finally {
    database.close();
  }
}

export function getSystemsImportRun(dbPath: string, importRunId: number): SystemsImportRun | null {
  if (!existsSync(dbPath)) {
    return null;
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true, readonly: true });
  try {
    const row = database
      .prepare(
        `
          SELECT ${importRunSelectColumns}
          FROM systems_import_runs
          WHERE id = ?
        `,
      )
      .get(importRunId) as SystemsImportRunRow | undefined;
    return row ? serializeImportRun(row) : null;
  } catch (error) {
    if (error instanceof Error && error.message.includes("no such table")) {
      return null;
    }
    throw error;
  } finally {
    database.close();
  }
}
