import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import Database from "better-sqlite3";

const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
const sourceCampaignsDir = path.join(repoRoot, "tests", "fixtures", "sample_campaigns");
const tempDir = mkdtempSync(path.join(tmpdir(), "cpw-image-portrait-policy-"));
const campaignsDir = path.join(tempDir, "campaigns");
const dbPath = path.join(tempDir, "player_wiki.sqlite3");
const dmApiToken = "fixture-image-policy-dm-token";
const hashToken = (rawToken) => createHash("sha256").update(rawToken, "utf8").digest("hex");

cpSync(sourceCampaignsDir, campaignsDir, { recursive: true });
process.env.CPW_CAMPAIGNS_DIR = campaignsDir;
process.env.CPW_DB_PATH = dbPath;

const db = new Database(dbPath);
db.exec(`
  CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    password_hash TEXT,
    auth_version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );

  CREATE TABLE user_preferences (
    user_id INTEGER PRIMARY KEY,
    theme_key TEXT NOT NULL DEFAULT 'parchment',
    session_chat_order TEXT NOT NULL DEFAULT 'newest_first',
    frontend_mode TEXT NOT NULL DEFAULT 'gen2',
    updated_at TEXT NOT NULL
  );

  CREATE TABLE campaign_memberships (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    campaign_slug TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );

  CREATE TABLE api_tokens (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    last_used_at TEXT NOT NULL,
    expires_at TEXT,
    revoked_at TEXT,
    created_by_user_id INTEGER
  );

  CREATE TABLE character_state (
    campaign_slug TEXT NOT NULL,
    character_slug TEXT NOT NULL,
    revision INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by_user_id INTEGER,
    PRIMARY KEY (campaign_slug, character_slug)
  );
`);

const now = "2026-06-27T12:00:00+00:00";
db.prepare(
  "INSERT INTO users (id, email, display_name, is_admin, status, password_hash, auth_version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
).run(81, "fixture-image-policy-dm@example.com", "Image Policy DM", 0, "active", null, 1, now, now);
db.prepare(
  "INSERT INTO campaign_memberships (id, user_id, campaign_slug, role, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
).run(1, 81, "linden-pass", "dm", "active", now, now);
db.prepare(
  "INSERT INTO api_tokens (id, user_id, label, token_hash, created_at, last_used_at, expires_at, revoked_at, created_by_user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
).run(1, 81, "image policy", hashToken(dmApiToken), now, now, null, null, 81);
db.prepare(
  "INSERT INTO character_state (campaign_slug, character_slug, revision, state_json, updated_at, updated_by_user_id) VALUES (?, ?, ?, ?, ?, ?)",
).run("linden-pass", "arden-march", 1, JSON.stringify({ status: "active" }), now, 81);
db.close();

const { getApp } = await import("../dist/server.js");
const app = getApp();

async function requestJson(pathname, options = {}) {
  const response = await app.request(pathname, {
    method: options.method || "GET",
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const text = await response.text();
  return {
    status: response.status,
    contentType: response.headers.get("content-type") || "",
    payload: text ? JSON.parse(text) : null,
  };
}

async function requestBytes(pathname) {
  const response = await app.request(pathname);
  return {
    status: response.status,
    contentType: response.headers.get("content-type") || "",
    bytes: Buffer.from(await response.arrayBuffer()),
  };
}

const authHeaders = { Authorization: `Bearer ${dmApiToken}` };
const portraitPath = "/api/v1/campaigns/linden-pass/characters/arden-march/portrait";
const portraitDir = path.join(campaignsDir, "linden-pass", "assets", "characters", "arden-march");
const pngBytes = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x70, 0x6e, 0x67]);
const jpgBytes = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0x6a, 0x70, 0x67, 0xff, 0xd9]);

try {
  const pngUpload = await requestJson(portraitPath, {
    method: "PUT",
    headers: authHeaders,
    body: {
      expected_revision: 1,
      portrait_file: {
        filename: "Arden.PNG",
        data_base64: pngBytes.toString("base64"),
      },
      alt_text: "Arden portrait",
      caption: "PNG source preserved.",
    },
  });
  assert.equal(pngUpload.status, 200);
  assert.equal(pngUpload.payload.character.portrait.asset_ref, "characters/arden-march/portrait.png");
  assert.equal(pngUpload.payload.character.portrait.media_type, "image/png");
  assert.deepEqual(readFileSync(path.join(portraitDir, "portrait.png")), pngBytes);

  const servedPng = await requestBytes("/campaigns/linden-pass/assets/characters/arden-march/portrait.png");
  assert.equal(servedPng.status, 200);
  assert.match(servedPng.contentType, /^image\/png\b/);
  assert.deepEqual(servedPng.bytes, pngBytes);

  const jpgUpload = await requestJson(portraitPath, {
    method: "PUT",
    headers: authHeaders,
    body: {
      expected_revision: 2,
      portrait_file: {
        filename: "arden.jpg",
        data_base64: jpgBytes.toString("base64"),
      },
      alt_text: "Arden portrait",
      caption: "JPG replacement preserved.",
    },
  });
  assert.equal(jpgUpload.status, 200);
  assert.equal(jpgUpload.payload.character.portrait.asset_ref, "characters/arden-march/portrait.jpg");
  assert.equal(jpgUpload.payload.character.portrait.media_type, "image/jpeg");
  assert.equal(existsSync(path.join(portraitDir, "portrait.png")), false);
  assert.deepEqual(readFileSync(path.join(portraitDir, "portrait.jpg")), jpgBytes);

  const servedJpg = await requestBytes("/campaigns/linden-pass/assets/characters/arden-march/portrait.jpg");
  assert.equal(servedJpg.status, 200);
  assert.match(servedJpg.contentType, /^image\/jpeg\b/);
  assert.deepEqual(servedJpg.bytes, jpgBytes);

  const portraitDelete = await requestJson(portraitPath, {
    method: "DELETE",
    headers: authHeaders,
    body: { expected_revision: 3 },
  });
  assert.equal(portraitDelete.status, 200);
  assert.equal(portraitDelete.payload.character.portrait, null);
  assert.equal(existsSync(path.join(portraitDir, "portrait.jpg")), false);
  const definitionAfterDelete = readFileSync(
    path.join(campaignsDir, "linden-pass", "characters", "arden-march", "definition.yaml"),
    "utf8",
  );
  assert.equal(definitionAfterDelete.includes("portrait_asset_ref"), false);

  const assetBytes = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x61, 0x73, 0x73, 0x65, 0x74]);
  const assetRef = "wiki-pages/policy-proof.png";
  const assetPut = await requestJson(`/api/v1/campaigns/linden-pass/content/assets/${assetRef}`, {
    method: "PUT",
    headers: authHeaders,
    body: {
      asset_file: {
        filename: "source-image.png",
        data_base64: assetBytes.toString("base64"),
      },
    },
  });
  assert.equal(assetPut.status, 200);
  assert.equal(assetPut.payload.asset_file.asset_ref, assetRef);
  assert.equal(assetPut.payload.asset_file.media_type, "image/png");

  const servedAsset = await requestBytes(`/campaigns/linden-pass/assets/${assetRef}`);
  assert.equal(servedAsset.status, 200);
  assert.match(servedAsset.contentType, /^image\/png\b/);
  assert.deepEqual(servedAsset.bytes, assetBytes);

  const assetDelete = await requestJson(`/api/v1/campaigns/linden-pass/content/assets/${assetRef}`, {
    method: "DELETE",
    headers: authHeaders,
  });
  assert.equal(assetDelete.status, 200);
  assert.equal(assetDelete.payload.deleted.asset_ref, assetRef);
} finally {
  rmSync(tempDir, { recursive: true, force: true });
}
