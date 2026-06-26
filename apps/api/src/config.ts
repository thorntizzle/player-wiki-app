import path from "node:path";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const API_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PROJECT_ROOT = path.resolve(API_ROOT, "..", "..");

const DEFAULT_CAMPAIGNS_DIR = path.resolve(
  PROJECT_ROOT,
  "tests",
  "fixtures",
  "sample_campaigns",
);
const DEFAULT_DB_PATH = path.resolve(PROJECT_ROOT, ".local", "player_wiki.sqlite3");

export type ApiRuntimeEnvironment = "fixture";

export interface ApiConfig {
  campaignsDir: string;
  dbPath: string;
  environment: string;
  runtimeMode: ApiRuntimeEnvironment;
  app: AppMetadata;
}

export interface AppMetadata {
  version: string;
  build_id: string;
  git_sha: string;
  git_dirty: boolean;
  runtime: string;
  instance_name: string;
  environment: string;
  base_url: string;
}

function envString(name: string, fallback = ""): string {
  return (process.env[name] || "").trim() || fallback;
}

function envBoolean(name: string, fallback = false): boolean {
  const rawValue = (process.env[name] || "").trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(rawValue)) {
    return true;
  }
  if (["0", "false", "no", "off"].includes(rawValue)) {
    return false;
  }
  return fallback;
}

function readVersion(): string {
  const override = envString("PLAYER_WIKI_VERSION");
  if (override) {
    return override;
  }
  const versionPath = path.join(PROJECT_ROOT, "VERSION");
  if (!existsSync(versionPath)) {
    return "0.0.0";
  }
  return readFileSync(versionPath, "utf-8").trim() || "0.0.0";
}

function gitCommand(...args: string[]): string {
  try {
    return execFileSync("git", ["-C", PROJECT_ROOT, ...args], { encoding: "utf-8" }).trim();
  } catch {
    return "";
  }
}

function resolveGitSha(): string {
  return envString("PLAYER_WIKI_GIT_SHA") || gitCommand("rev-parse", "--short=12", "HEAD") || "unknown";
}

function resolveGitDirty(): boolean {
  const override = envString("PLAYER_WIKI_GIT_DIRTY");
  if (override) {
    return envBoolean("PLAYER_WIKI_GIT_DIRTY");
  }
  return Boolean(gitCommand("status", "--short"));
}

function resolveBuildId(gitSha: string, gitDirty: boolean): string {
  const override = envString("PLAYER_WIKI_BUILD_ID");
  if (override) {
    return override;
  }
  if (gitSha === "unknown") {
    return "unknown";
  }
  return gitDirty ? `${gitSha}-dirty` : gitSha;
}

function defaultBaseUrl(): string {
  const port = envString("PORT", "3000");
  return `http://127.0.0.1:${port}`;
}

function buildAppMetadata(environment: string): AppMetadata {
  const gitSha = resolveGitSha();
  const gitDirty = resolveGitDirty();
  return {
    version: readVersion(),
    build_id: resolveBuildId(gitSha, gitDirty),
    git_sha: gitSha,
    git_dirty: gitDirty,
    runtime: envString("PLAYER_WIKI_RUNTIME", "fixture"),
    instance_name: envString("PLAYER_WIKI_INSTANCE_NAME", "typescript-fixture"),
    environment,
    base_url: envString("PLAYER_WIKI_BASE_URL", defaultBaseUrl()),
  };
}

export function getApiConfig(): ApiConfig {
  const campaignsEnv = envString("CPW_CAMPAIGNS_DIR");
  const dbEnv = envString("CPW_DB_PATH");
  const environment = envString("PLAYER_WIKI_ENV", "development").toLowerCase();
  return {
    campaignsDir: campaignsEnv ? path.resolve(process.cwd(), campaignsEnv) : DEFAULT_CAMPAIGNS_DIR,
    dbPath: dbEnv ? path.resolve(process.cwd(), dbEnv) : DEFAULT_DB_PATH,
    environment,
    runtimeMode: "fixture",
    app: buildAppMetadata(environment),
  };
}
