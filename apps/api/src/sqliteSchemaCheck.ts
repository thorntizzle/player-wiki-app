import { inspectSqliteSchema, type SqliteSchemaInspection } from "./sqlite.js";

interface CliOptions {
  dbPath: string;
  json: boolean;
}

function parseArgs(argv: string[]): CliOptions {
  let dbPath = String(process.env.CPW_DB_PATH || "").trim();
  let json = false;

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--json") {
      json = true;
      continue;
    }
    if (arg === "--db") {
      const value = argv[index + 1];
      if (!value) {
        throw new Error("--db requires a SQLite database path.");
      }
      dbPath = value;
      index += 1;
      continue;
    }
    if (arg === "--help" || arg === "-h") {
      throw new Error("usage");
    }
    throw new Error(`Unknown argument: ${arg}`);
  }

  if (!dbPath) {
    throw new Error("Set CPW_DB_PATH or pass --db <path>.");
  }

  return {
    dbPath,
    json,
  };
}

function formatTextReport(report: SqliteSchemaInspection): string {
  const lines = [
    `SQLite schema check: ${report.ok ? "PASS" : "FAIL"}`,
    `Database: ${report.dbPath}`,
    "Mode: read-only preflight; no migrations or writes were run.",
    `Required schema: ${report.schema.required.tables} tables, ${report.schema.required.columns} columns, ${report.schema.required.indexes} indexes`,
    `Present schema: ${report.schema.present.tables} tables, ${report.schema.present.columns} columns, ${report.schema.present.indexes} indexes`,
  ];

  if (report.schema.missing.length > 0) {
    lines.push("Missing schema items:");
    for (const item of report.schema.missing) {
      lines.push(`- ${item}`);
    }
  } else {
    lines.push("Missing schema items: none");
  }

  if (report.pragmas) {
    lines.push(
      `Connection PRAGMAs: foreign_keys=${report.pragmas.connection.foreign_keys.actual} (expected ${report.pragmas.connection.foreign_keys.expected}), busy_timeout=${report.pragmas.connection.busy_timeout_ms.actual} ms (expected ${report.pragmas.connection.busy_timeout_ms.expected} ms)`,
      `Observed database PRAGMAs: journal_mode=${report.pragmas.observed_database.journal_mode}, synchronous=${report.pragmas.observed_database.synchronous}`,
      `Writable open policy: TypeScript writable opens apply journal_mode=${report.pragmas.writable_open_policy.journal_mode} and synchronous=${report.pragmas.writable_open_policy.synchronous}; this command does not apply them.`,
    );
  }

  lines.push(report.note);
  return `${lines.join("\n")}\n`;
}

function printUsage(): void {
  process.stderr.write(
    [
      "Usage: npm --prefix apps/api run sqlite:schema-check -- [--json] [--db <path>]",
      "",
      "Checks the current TypeScript SQLite startup schema requirements against CPW_DB_PATH or --db.",
      "The command opens the database read-only and does not run migrations or schema writes.",
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

  const report = inspectSqliteSchema(options.dbPath);
  if (options.json) {
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  } else {
    process.stdout.write(formatTextReport(report));
  }

  return report.ok ? 0 : 1;
}

process.exitCode = main();
