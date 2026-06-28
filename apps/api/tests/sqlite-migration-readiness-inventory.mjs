import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

import {
  CURRENT_SQLITE_SCHEMA_REQUIREMENTS,
  inspectSqliteSchema,
} from "../dist/sqlite.js";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const apiRoot = path.resolve(testDir, "..");
const repoRoot = path.resolve(apiRoot, "..", "..");
const migrationCliPath = path.join(apiRoot, "dist", "sqliteMigrationProof.js");
const tempRoot = mkdtempSync(path.join(tmpdir(), "cpw-sqlite-migration-readiness-"));

function runPython(args, env = {}) {
  const pythonPath = process.env.CPW_PYTHON_PATH || process.env.PYTHON || "python";
  return spawnSync(pythonPath, args, {
    cwd: repoRoot,
    env: {
      ...process.env,
      ...env,
    },
    encoding: "utf8",
  });
}

function runNodeCli(args, env = {}) {
  return spawnSync(process.execPath, [migrationCliPath, ...args], {
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

function countRequiredColumns() {
  return Object.values(CURRENT_SQLITE_SCHEMA_REQUIREMENTS.columns).reduce(
    (total, columnNames) => total + columnNames.length,
    0,
  );
}

try {
  const campaignsDir = path.join(tempRoot, "campaigns");
  const tempDir = path.join(tempRoot, "tmp");
  mkdirSync(campaignsDir, { recursive: true });
  mkdirSync(tempDir, { recursive: true });

  const flaskDbPath = path.join(tempRoot, "flask-initialized.sqlite3");
  const initResult = runPython([path.join(repoRoot, "manage.py"), "init-db"], {
    PLAYER_WIKI_DB_PATH: flaskDbPath,
    PLAYER_WIKI_CAMPAIGNS_DIR: campaignsDir,
    PLAYER_WIKI_TEMP_DIR: tempDir,
  });
  assertSuccessfulProcess(initResult, "Flask init-db scratch setup");

  const inspection = inspectSqliteSchema(flaskDbPath);
  assert.equal(inspection.ok, true);
  assert.deepEqual(inspection.schema.missing, []);
  assert.equal(inspection.schema.required.tables, 34);
  assert.equal(inspection.schema.required.columns, countRequiredColumns());
  assert.equal(inspection.schema.required.indexes, 21);
  assert.deepEqual(inspection.schema.present, inspection.schema.required);
  assert.equal(inspection.pragmas.connection.foreign_keys.actual, 1);
  assert.equal(inspection.pragmas.connection.busy_timeout_ms.actual, 30000);

  const migrationDryRun = runNodeCli(["--db", flaskDbPath]);
  assertSuccessfulProcess(migrationDryRun, "TypeScript migration proof dry run");
  const migrationReport = JSON.parse(migrationDryRun.stdout);
  assert.equal(migrationReport.ok, true);
  assert.equal(migrationReport.mode, "dry-run");
  assert.equal(migrationReport.safety.target, "disposable");
  assert.deepEqual(migrationReport.migrations.allowlisted, []);
  assert.deepEqual(migrationReport.migrations.applied, []);
  assert.deepEqual(migrationReport.migrations.skipped, []);
  assert.equal(migrationReport.ledger.created, false);

  console.log(
    JSON.stringify({
      status: "sqlite-migration-readiness-inventory",
      required: inspection.schema.required,
      present: inspection.schema.present,
      missing: inspection.schema.missing,
      allowlistedTypeScriptDeltas: migrationReport.migrations.allowlisted,
      appliedTypeScriptDeltas: migrationReport.migrations.applied,
      note: "Flask-initialized scratch DB matches TypeScript required schema; migration proof has no real TypeScript schema deltas.",
    }),
  );
} finally {
  rmSync(tempRoot, { recursive: true, force: true });
}
