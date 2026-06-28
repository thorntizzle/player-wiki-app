import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import {
  CURRENT_SQLITE_SCHEMA_REQUIREMENTS,
  SQLITE_BUSY_TIMEOUT_MS,
  assertSqliteStartupSchema,
  listMissingSqliteSchema,
  openSqliteDatabase,
} from "../dist/sqlite.js";

const tempDir = mkdtempSync(path.join(tmpdir(), "cpw-sqlite-startup-posture-"));

function sqliteIdentifier(value) {
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(value)) {
    throw new Error(`Unsafe SQLite identifier in test: ${value}`);
  }
  return `"${value}"`;
}

function createSyntheticCurrentSchema(database) {
  for (const tableName of CURRENT_SQLITE_SCHEMA_REQUIREMENTS.tables) {
    const columns = CURRENT_SQLITE_SCHEMA_REQUIREMENTS.columns[tableName] || ["id"];
    const uniqueColumns = [...new Set(columns)];
    database.exec(
      `CREATE TABLE ${sqliteIdentifier(tableName)} (${uniqueColumns
        .map((columnName) => `${sqliteIdentifier(columnName)} TEXT`)
        .join(", ")})`,
    );
  }
  for (const indexName of CURRENT_SQLITE_SCHEMA_REQUIREMENTS.indexes) {
    database.exec(`CREATE INDEX ${sqliteIdentifier(indexName)} ON "users" ("id")`);
  }
}

try {
  const dbPath = path.join(tempDir, "player_wiki.sqlite3");
  const database = openSqliteDatabase(dbPath);
  try {
    assert.equal(Number(database.pragma("foreign_keys", { simple: true })), 1);
    assert.equal(Number(database.pragma("busy_timeout", { simple: true })), SQLITE_BUSY_TIMEOUT_MS);
    assert.equal(String(database.pragma("journal_mode", { simple: true })).toLowerCase(), "wal");
    assert.equal(Number(database.pragma("synchronous", { simple: true })), 1);

    const missingBeforeSchema = listMissingSqliteSchema(database);
    assert.ok(missingBeforeSchema.includes("table users"));
    assert.ok(missingBeforeSchema.includes("table campaign_page_sync_state"));

    createSyntheticCurrentSchema(database);
    assert.deepEqual(listMissingSqliteSchema(database), []);
  } finally {
    database.close();
  }

  assert.doesNotThrow(() => assertSqliteStartupSchema(dbPath));

  const partialDbPath = path.join(tempDir, "partial.sqlite3");
  const partialDatabase = openSqliteDatabase(partialDbPath);
  try {
    partialDatabase.exec('CREATE TABLE "user_preferences" ("user_id" TEXT, "theme_key" TEXT)');
    const missing = listMissingSqliteSchema(partialDatabase);
    assert.ok(missing.includes("column user_preferences.session_chat_order"));
    assert.ok(missing.includes("column user_preferences.frontend_mode"));
  } finally {
    partialDatabase.close();
  }

  assert.throws(
    () => assertSqliteStartupSchema(path.join(tempDir, "missing.sqlite3")),
    /manage\.py init-db/,
  );
} finally {
  rmSync(tempDir, { recursive: true, force: true });
}
