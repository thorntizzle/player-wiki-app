import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

import {
  CURRENT_SQLITE_SCHEMA_REQUIREMENTS,
  openSqliteDatabase,
} from "../dist/sqlite.js";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const apiRoot = path.resolve(testDir, "..");
const repoRoot = path.resolve(apiRoot, "..", "..");
const cliPath = path.join(apiRoot, "dist", "sqliteMigrationProof.js");
const tempRoot = mkdtempSync(path.join(tmpdir(), "cpw-sqlite-migrate-proof-"));
const ledgerTable = "__cpw_typescript_migration_ledger";

function runNodeCli(args, env = {}) {
  return spawnSync(process.execPath, [cliPath, ...args], {
    cwd: repoRoot,
    env: {
      ...process.env,
      ...env,
    },
    encoding: "utf8",
  });
}

function assertSuccessfulProcess(result, label) {
  if (result.error) {
    throw result.error;
  }
  assert.equal(result.status, 0, `${label} failed\nSTDOUT:\n${result.stdout}\nSTDERR:\n${result.stderr}`);
}

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

function ledgerRowCount(database) {
  const row = database.prepare(`SELECT count(*) AS count FROM "${ledgerTable}"`).get();
  return Number(row?.count || 0);
}

try {
  const dbPath = path.join(tempRoot, "current.sqlite3");
  const database = openSqliteDatabase(dbPath);
  try {
    createSyntheticCurrentSchema(database);
  } finally {
    database.close();
  }

  const dryRun = runNodeCli(["--db", dbPath]);
  assertSuccessfulProcess(dryRun, "TypeScript migration proof dry run");
  const dryRunReport = JSON.parse(dryRun.stdout);
  assert.equal(dryRunReport.ok, true);
  assert.equal(dryRunReport.mode, "dry-run");
  assert.deepEqual(dryRunReport.migrations.applied, []);
  assert.deepEqual(dryRunReport.migrations.skipped, []);
  assert.equal(dryRunReport.ledger.created, false);

  const dryRunDatabase = openSqliteDatabase(dbPath);
  try {
    const row = dryRunDatabase
      .prepare("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?")
      .get(ledgerTable);
    assert.equal(row, undefined, "dry run should not create the migration ledger");
  } finally {
    dryRunDatabase.close();
  }

  const envOnlyResult = runNodeCli([], { CPW_DB_PATH: dbPath });
  assert.equal(envOnlyResult.status, 2, `CPW_DB_PATH-only migration proof should fail\nSTDOUT:\n${envOnlyResult.stdout}\nSTDERR:\n${envOnlyResult.stderr}`);
  assert.match(envOnlyResult.stderr, /explicit --db/);

  const applyResult = runNodeCli(["--db", dbPath, "--apply"]);
  assertSuccessfulProcess(applyResult, "TypeScript migration proof apply");
  const applyReport = JSON.parse(applyResult.stdout);
  assert.equal(applyReport.ok, true);
  assert.equal(applyReport.mode, "apply");
  assert.equal(applyReport.safety.target, "disposable");
  assert.equal(applyReport.ledger.created, true);
  assert.equal(applyReport.ledger.existing, false);
  assert.deepEqual(applyReport.migrations.allowlisted, []);
  assert.deepEqual(applyReport.migrations.applied, []);

  const afterApplyDatabase = openSqliteDatabase(dbPath);
  try {
    assert.equal(ledgerRowCount(afterApplyDatabase), 1);
  } finally {
    afterApplyDatabase.close();
  }

  const secondApply = runNodeCli(["--db", dbPath, "--apply"]);
  assertSuccessfulProcess(secondApply, "TypeScript migration proof idempotent apply");
  const secondApplyReport = JSON.parse(secondApply.stdout);
  assert.equal(secondApplyReport.ledger.created, false);
  assert.equal(secondApplyReport.ledger.existing, true);
  const afterSecondApplyDatabase = openSqliteDatabase(dbPath);
  try {
    assert.equal(ledgerRowCount(afterSecondApplyDatabase), 1);
  } finally {
    afterSecondApplyDatabase.close();
  }

  const partialDbPath = path.join(tempRoot, "partial.sqlite3");
  const partialDatabase = openSqliteDatabase(partialDbPath);
  try {
    partialDatabase.exec('CREATE TABLE "users" ("id" TEXT)');
  } finally {
    partialDatabase.close();
  }
  const partialResult = runNodeCli(["--db", partialDbPath, "--apply"]);
  assert.equal(partialResult.status, 1, `Partial schema should fail\nSTDOUT:\n${partialResult.stdout}\nSTDERR:\n${partialResult.stderr}`);
  const partialReport = JSON.parse(partialResult.stdout);
  assert.equal(partialReport.ok, false);
  assert.ok(partialReport.schema.missing.includes("column users.email"));

  const missingPath = path.join(tempRoot, "missing.sqlite3");
  const missingResult = runNodeCli(["--db", missingPath, "--apply"]);
  assert.equal(missingResult.status, 1, `Missing database should fail\nSTDOUT:\n${missingResult.stdout}\nSTDERR:\n${missingResult.stderr}`);
  const missingReport = JSON.parse(missingResult.stdout);
  assert.match(missingReport.note, /Refusing missing SQLite database path/);

  const liveishResult = runNodeCli(["--db", path.join(path.parse(repoRoot).root, "data", "player_wiki.sqlite3"), "--apply"]);
  assert.equal(liveishResult.status, 1, `Live-ish database path should fail\nSTDOUT:\n${liveishResult.stdout}\nSTDERR:\n${liveishResult.stderr}`);
  const liveishReport = JSON.parse(liveishResult.stdout);
  assert.match(liveishReport.note, /Refusing live-ish SQLite path/);
} finally {
  rmSync(tempRoot, { recursive: true, force: true });
}
