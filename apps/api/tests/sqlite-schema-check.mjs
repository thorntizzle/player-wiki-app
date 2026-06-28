import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

import Database from "better-sqlite3";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const apiRoot = path.resolve(testDir, "..");
const repoRoot = path.resolve(apiRoot, "..", "..");
const cliPath = path.join(apiRoot, "dist", "sqliteSchemaCheck.js");
const tempRoot = mkdtempSync(path.join(tmpdir(), "cpw-sqlite-schema-check-"));

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

function assertSuccessfulProcess(result, label) {
  if (result.error) {
    throw result.error;
  }
  assert.equal(result.status, 0, `${label} failed\nSTDOUT:\n${result.stdout}\nSTDERR:\n${result.stderr}`);
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

  const passResult = runNodeCli(["--json"], {
    CPW_DB_PATH: flaskDbPath,
  });
  assertSuccessfulProcess(passResult, "TypeScript SQLite schema check");
  const passReport = JSON.parse(passResult.stdout);
  assert.equal(passReport.ok, true);
  assert.equal(passReport.mode, "readonly");
  assert.equal(passReport.schema.required.tables, 34);
  assert.deepEqual(passReport.schema.missing, []);
  assert.equal(passReport.pragmas.connection.foreign_keys.actual, 1);
  assert.equal(passReport.pragmas.connection.busy_timeout_ms.actual, 30000);
  assert.equal(passReport.pragmas.writable_open_policy.applied_by_readonly_check, false);

  const textResult = runNodeCli(["--db", flaskDbPath]);
  assertSuccessfulProcess(textResult, "TypeScript SQLite text schema check");
  assert.match(textResult.stdout, /SQLite schema check: PASS/);
  assert.match(textResult.stdout, /Mode: read-only preflight; no migrations or writes were run\./);

  const partialDbPath = path.join(tempRoot, "partial.sqlite3");
  const partialDatabase = new Database(partialDbPath);
  try {
    partialDatabase.exec('CREATE TABLE "users" ("id" TEXT)');
  } finally {
    partialDatabase.close();
  }

  const failResult = runNodeCli(["--json", "--db", partialDbPath]);
  assert.equal(failResult.status, 1, `Partial schema should fail\nSTDOUT:\n${failResult.stdout}\nSTDERR:\n${failResult.stderr}`);
  const failReport = JSON.parse(failResult.stdout);
  assert.equal(failReport.ok, false);
  assert.ok(failReport.schema.missing.includes("column users.email"));
  assert.ok(failReport.schema.missing.includes("table campaign_page_sync_state"));

  const missingPath = path.join(tempRoot, "missing.sqlite3");
  const missingResult = runNodeCli(["--json", "--db", missingPath]);
  assert.equal(missingResult.status, 1, `Missing database should fail\nSTDOUT:\n${missingResult.stdout}\nSTDERR:\n${missingResult.stderr}`);
  const missingReport = JSON.parse(missingResult.stdout);
  assert.equal(missingReport.ok, false);
  assert.deepEqual(missingReport.schema.missing, ["database file"]);
} finally {
  rmSync(tempRoot, { recursive: true, force: true });
}
