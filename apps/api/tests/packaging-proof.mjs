import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

function readRepoFile(relativePath) {
  return readFileSync(path.join(repoRoot, relativePath), "utf-8");
}

function assertIncludes(text, needle, label) {
  if (!text.includes(needle)) {
    throw new Error(`Missing ${label}: ${needle}`);
  }
}

const dockerfile = readRepoFile("Dockerfile");
const dockerignore = readRepoFile(".dockerignore");
const flyConfig = readRepoFile("fly.toml");
const entrypoint = readRepoFile("deploy/ts-api-proof-entrypoint.sh");

const proofTargetIndex = dockerfile.indexOf("FROM node:22-slim AS ts-api-runtime-proof");
const flaskFinalIndex = dockerfile.lastIndexOf("FROM python:3.12-slim");

if (proofTargetIndex === -1) {
  throw new Error("Dockerfile is missing the ts-api-runtime-proof target.");
}
if (flaskFinalIndex === -1 || flaskFinalIndex < proofTargetIndex) {
  throw new Error("Dockerfile must keep the Flask/Python stage as the default final image.");
}

assertIncludes(dockerfile, "FROM node:22-slim AS ts-api-build", "TypeScript API build stage");
assertIncludes(dockerfile, "RUN npm run build", "TypeScript API Docker build command");
assertIncludes(dockerfile, "npm prune --omit=dev", "production dependency prune");
assertIncludes(dockerfile, "COPY --from=ts-api-build /app/apps/api/dist ./apps/api/dist", "compiled API artifact copy");
assertIncludes(dockerfile, "CMD [\"/app/deploy/ts-api-proof-entrypoint.sh\"]", "proof target command");
assertIncludes(dockerfile, "CMD [\"/app/deploy/fly-entrypoint.sh\"]", "Flask default command");

assertIncludes(entrypoint, 'export PORT="${PORT:-$PLAYER_WIKI_PORT}"', "PORT mapping");
assertIncludes(entrypoint, 'export CPW_DB_PATH="${CPW_DB_PATH:-$PLAYER_WIKI_DB_PATH}"', "DB env mapping");
assertIncludes(
  entrypoint,
  'export CPW_CAMPAIGNS_DIR="${CPW_CAMPAIGNS_DIR:-$PLAYER_WIKI_CAMPAIGNS_DIR}"',
  "campaign env mapping",
);
assertIncludes(entrypoint, "exec node /app/apps/api/dist/server.js", "TypeScript API startup");
if (entrypoint.includes("manage.py init-db")) {
  throw new Error("TypeScript proof entrypoint must not imply Flask schema initialization.");
}

assertIncludes(dockerignore, "apps/**/dist", "ignored host-built API dist");
assertIncludes(dockerignore, "apps/**/node_modules", "ignored host API node_modules");
assertIncludes(dockerignore, ".task-temp*", "ignored local proof scratch");

assertIncludes(flyConfig, "app = 'campaign-player-wiki-example'", "sanitized Fly placeholder app");
assertIncludes(flyConfig, "PLAYER_WIKI_DB_PATH = '/data/player_wiki.sqlite3'", "Fly DB path");
assertIncludes(flyConfig, "PLAYER_WIKI_CAMPAIGNS_DIR = '/data/campaigns'", "Fly campaigns path");

console.log("TypeScript API packaging proof static checks passed.");
