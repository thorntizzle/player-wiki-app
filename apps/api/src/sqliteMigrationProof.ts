import { existsSync } from "node:fs";
import { relative, resolve, sep } from "node:path";
import { tmpdir } from "node:os";

import { inspectSqliteSchema, openSqliteDatabase, type SqliteDatabase } from "./sqlite.js";

const LEDGER_TABLE = "__cpw_typescript_migration_ledger";
const PROOF_NAME = "current-flask-schema-ledger-proof";

interface CliOptions {
  dbPath: string;
  apply: boolean;
  allowCopiedDb: boolean;
}

interface MigrationProofReport {
  ok: boolean;
  dbPath: string;
  mode: "dry-run" | "apply";
  safety: {
    target: "disposable" | "copied-approved";
    reason: string;
  } | null;
  schema: {
    ok: boolean;
    missing: string[];
  };
  ledger: {
    table: typeof LEDGER_TABLE;
    created: boolean;
    existing: boolean;
  };
  migrations: {
    allowlisted: string[];
    applied: string[];
    skipped: string[];
  };
  note: string;
}

function parseArgs(argv: string[]): CliOptions {
  let dbPath = "";
  let apply = false;
  let allowCopiedDb = false;

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--db") {
      const value = argv[index + 1];
      if (!value) {
        throw new Error("--db requires a SQLite database path.");
      }
      dbPath = value;
      index += 1;
      continue;
    }
    if (arg === "--apply") {
      apply = true;
      continue;
    }
    if (arg === "--allow-copied-db") {
      allowCopiedDb = true;
      continue;
    }
    if (arg === "--help" || arg === "-h") {
      throw new Error("usage");
    }
    throw new Error(`Unknown argument: ${arg}`);
  }

  if (!dbPath) {
    throw new Error("Pass an explicit --db <path>. CPW_DB_PATH is intentionally ignored by this migration proof.");
  }

  return {
    dbPath,
    apply,
    allowCopiedDb,
  };
}

function isInside(parent: string, child: string): boolean {
  const relativePath = relative(resolve(parent), resolve(child));
  return relativePath === "" || (!!relativePath && !relativePath.startsWith("..") && !relativePath.startsWith(sep));
}

function formatPathForCheck(value: string): string {
  return resolve(value).replace(/\\/g, "/").toLowerCase();
}

function classifyTarget(dbPath: string, allowCopiedDb: boolean): MigrationProofReport["safety"] {
  const resolvedPath = resolve(dbPath);
  const normalized = formatPathForCheck(resolvedPath);
  if (normalized.includes("/data/") || normalized.endsWith("/data/player_wiki.sqlite3")) {
    throw new Error("Refusing live-ish SQLite path under /data. Use a disposable or copied database path.");
  }

  const repoRoot = resolve(process.cwd());
  const safeRoots = [tmpdir(), resolve(repoRoot, ".task-temp"), resolve(repoRoot, ".local", "tmp")];
  for (const safeRoot of safeRoots) {
    if (isInside(safeRoot, resolvedPath)) {
      return {
        target: "disposable",
        reason: `database path is under ${safeRoot}`,
      };
    }
  }

  if (allowCopiedDb) {
    return {
      target: "copied-approved",
      reason: "--allow-copied-db was provided for an operator-approved copied database",
    };
  }

  throw new Error(
    "Refusing SQLite migration proof outside disposable roots. Use a temp/.task-temp/.local/tmp path or pass --allow-copied-db for an approved copied database.",
  );
}

function ledgerExists(database: SqliteDatabase): boolean {
  const row = database
    .prepare("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?")
    .get(LEDGER_TABLE) as { name?: string } | undefined;
  return row?.name === LEDGER_TABLE;
}

function ensureLedger(database: SqliteDatabase): { created: boolean; existing: boolean } {
  const existing = ledgerExists(database);
  database.exec(`
    CREATE TABLE IF NOT EXISTS "${LEDGER_TABLE}" (
      "id" TEXT PRIMARY KEY,
      "created_at" TEXT NOT NULL,
      "proof_name" TEXT NOT NULL,
      "summary_json" TEXT NOT NULL
    )
  `);
  if (!existing) {
    database
      .prepare(
        `INSERT INTO "${LEDGER_TABLE}" ("id", "created_at", "proof_name", "summary_json") VALUES (?, datetime('now'), ?, ?)`,
      )
      .run("ledger-created", PROOF_NAME, JSON.stringify({ migrations: [] }));
  }
  return {
    created: !existing,
    existing,
  };
}

export function runSqliteMigrationProof(options: CliOptions): MigrationProofReport {
  const dbPath = resolve(options.dbPath);
  const safety = classifyTarget(dbPath, options.allowCopiedDb);

  if (!existsSync(dbPath)) {
    throw new Error("Refusing missing SQLite database path. Create or copy the database with Flask manage.py init-db first.");
  }

  const schemaInspection = inspectSqliteSchema(dbPath);
  if (!schemaInspection.ok) {
    return {
      ok: false,
      dbPath,
      mode: options.apply ? "apply" : "dry-run",
      safety,
      schema: {
        ok: false,
        missing: schemaInspection.schema.missing,
      },
      ledger: {
        table: LEDGER_TABLE,
        created: false,
        existing: false,
      },
      migrations: {
        allowlisted: [],
        applied: [],
        skipped: [],
      },
      note: "Current proof is intentionally no-op for schema deltas and requires the Flask-initialized schema before creating the TypeScript migration ledger.",
    };
  }

  if (!options.apply) {
    return {
      ok: true,
      dbPath,
      mode: "dry-run",
      safety,
      schema: {
        ok: true,
        missing: [],
      },
      ledger: {
        table: LEDGER_TABLE,
        created: false,
        existing: false,
      },
      migrations: {
        allowlisted: [],
        applied: [],
        skipped: [],
      },
      note: "Dry run only. No migrations, ledger writes, startup hook, or production schema authority change were performed.",
    };
  }

  const database = openSqliteDatabase(dbPath, { fileMustExist: true });
  try {
    const ledger = ensureLedger(database);
    return {
      ok: true,
      dbPath,
      mode: "apply",
      safety,
      schema: {
        ok: true,
        missing: [],
      },
      ledger: {
        table: LEDGER_TABLE,
        ...ledger,
      },
      migrations: {
        allowlisted: [],
        applied: [],
        skipped: [],
      },
      note: "Applied the TypeScript migration hook proof ledger only. No current schema deltas are claimed; Flask manage.py init-db remains schema authority.",
    };
  } finally {
    database.close();
  }
}

function printUsage(): void {
  process.stderr.write(
    [
      "Usage: npm --prefix apps/api run sqlite:migrate-proof -- --db <path> [--apply] [--allow-copied-db]",
      "",
      "Runs the transitional TypeScript SQLite migration hook proof against an explicit copied or disposable database.",
      "Without --apply, the command is a JSON dry run. With --apply, it may create only the TypeScript migration ledger.",
      "The command is never called at API startup and does not replace Flask manage.py init-db.",
      "",
    ].join("\n"),
  );
}

function main(): number {
  let options: CliOptions;
  try {
    options = parseArgs(process.argv.slice(2));
  } catch (error) {
    if (error instanceof Error && error.message === "usage") {
      printUsage();
      return 0;
    }
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    printUsage();
    return 2;
  }

  try {
    const report = runSqliteMigrationProof(options);
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
    return report.ok ? 0 : 1;
  } catch (error) {
    const report = {
      ok: false,
      dbPath: resolve(options.dbPath),
      mode: options.apply ? "apply" : "dry-run",
      safety: null,
      schema: {
        ok: false,
        missing: [],
      },
      ledger: {
        table: LEDGER_TABLE,
        created: false,
        existing: false,
      },
      migrations: {
        allowlisted: [],
        applied: [],
        skipped: [],
      },
      note: error instanceof Error ? error.message : String(error),
    };
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
    return 1;
  }
}

process.exitCode = main();
