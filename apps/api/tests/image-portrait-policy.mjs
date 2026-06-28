import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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

  CREATE TABLE character_assignments (
    id INTEGER PRIMARY KEY,
    campaign_slug TEXT NOT NULL,
    character_slug TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    assigned_by_user_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(campaign_slug, character_slug)
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
const definitionPath = path.join(campaignsDir, "linden-pass", "characters", "arden-march", "definition.yaml");
const importPath = path.join(campaignsDir, "linden-pass", "characters", "arden-march", "import.yaml");
const existingWebpAssetRef = "characters/arden-march/portrait.webp";
const existingWebpBytes = Buffer.from([0x52, 0x49, 0x46, 0x46, 0x77, 0x65, 0x62, 0x70, 0x30]);
const pngBytes = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x70, 0x6e, 0x67]);
const jpgBytes = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0x6a, 0x70, 0x67, 0xff, 0xd9]);
const gifBytes = Buffer.from([0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0x67, 0x69, 0x66]);
const webpBytes = Buffer.from([0x52, 0x49, 0x46, 0x46, 0x77, 0x65, 0x62, 0x70, 0x31]);

mkdirSync(portraitDir, { recursive: true });
writeFileSync(path.join(portraitDir, "portrait.webp"), existingWebpBytes);
writeFileSync(
  definitionPath,
  readFileSync(definitionPath, "utf8").replace(
    /profile:\r?\n/,
    `profile:\n  portrait_asset_ref: ${existingWebpAssetRef}\n  portrait_alt: Existing WebP portrait\n  portrait_caption: Existing WebP fixture.\n`,
  ),
);

function assetPath(assetRef) {
  return path.join(campaignsDir, "linden-pass", "assets", ...assetRef.split("/"));
}

function assertImportMetadataPreserved() {
  const importText = readFileSync(importPath, "utf8");
  assert.match(importText, /parser_version:\s*fixture/);
  assert.match(importText, /import_status:\s*clean/);
  assert.match(importText, /source_path:/);
}

function assertProfileMetadata(assetRef, altText, caption) {
  const definitionText = readFileSync(definitionPath, "utf8");
  assert.match(definitionText, new RegExp(`portrait_asset_ref:\\s*${assetRef.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`));
  assert.match(definitionText, new RegExp(`portrait_alt:\\s*${altText.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`));
  assert.match(definitionText, new RegExp(`portrait_caption:\\s*${caption.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`));
}

function readCharacterStateRow() {
  const assertionDb = new Database(dbPath, { readonly: true });
  try {
    return assertionDb
      .prepare(
        "SELECT revision, state_json, updated_by_user_id FROM character_state WHERE campaign_slug = ? AND character_slug = ?",
      )
      .get("linden-pass", "arden-march");
  } finally {
    assertionDb.close();
  }
}

async function assertProtectedAsset(assetRef, expectedContentType, expectedBytes) {
  const served = await requestBytes(`/campaigns/linden-pass/assets/${assetRef}`);
  assert.equal(served.status, 200);
  assert.match(served.contentType, expectedContentType);
  assert.deepEqual(served.bytes, expectedBytes);
}

async function uploadPortrait({ expectedRevision, filename, bytes, assetRef, mediaType, contentType, altText, caption, removedRefs }) {
  const upload = await requestJson(portraitPath, {
    method: "PUT",
    headers: authHeaders,
    body: {
      expected_revision: expectedRevision,
      portrait_file: {
        filename,
        data_base64: bytes.toString("base64"),
      },
      alt_text: altText,
      caption,
    },
  });
  assert.equal(upload.status, 200);
  assert.equal(upload.payload.character.portrait.asset_ref, assetRef);
  assert.equal(upload.payload.character.portrait.media_type, mediaType);
  assert.equal(upload.payload.character.portrait.alt_text, altText);
  assert.equal(upload.payload.character.portrait.caption, caption);
  assert.deepEqual(readFileSync(assetPath(assetRef)), bytes);
  for (const removedRef of removedRefs) {
    assert.equal(existsSync(assetPath(removedRef)), false);
  }
  await assertProtectedAsset(assetRef, contentType, bytes);
  assertProfileMetadata(assetRef, altText, caption);
  assertImportMetadataPreserved();
  const stateRow = readCharacterStateRow();
  assert.equal(stateRow.revision, expectedRevision + 1);
  assert.equal(stateRow.updated_by_user_id, 81);
  return upload;
}

try {
  const existingDetail = await requestJson("/api/v1/campaigns/linden-pass/characters/arden-march", {
    headers: authHeaders,
  });
  assert.equal(existingDetail.status, 200);
  assert.equal(existingDetail.payload.character.portrait.asset_ref, existingWebpAssetRef);
  assert.equal(existingDetail.payload.character.portrait.media_type, "image/webp");
  assert.equal(existingDetail.payload.character.portrait.url, "/campaigns/linden-pass/characters/arden-march/portrait");
  await assertProtectedAsset(existingWebpAssetRef, /^image\/webp\b/, existingWebpBytes);

  await uploadPortrait({
    expectedRevision: 1,
    filename: "Arden.PNG",
    bytes: pngBytes,
    assetRef: "characters/arden-march/portrait.png",
    mediaType: "image/png",
    contentType: /^image\/png\b/,
    altText: "Arden portrait PNG",
    caption: "PNG source preserved.",
    removedRefs: [existingWebpAssetRef],
  });

  await uploadPortrait({
    expectedRevision: 2,
    filename: "arden.JPG",
    bytes: jpgBytes,
    assetRef: "characters/arden-march/portrait.jpg",
    mediaType: "image/jpeg",
    contentType: /^image\/jpeg\b/,
    altText: "Arden portrait JPG",
    caption: "JPG replacement preserved.",
    removedRefs: ["characters/arden-march/portrait.png"],
  });

  await uploadPortrait({
    expectedRevision: 3,
    filename: "arden.gif",
    bytes: gifBytes,
    assetRef: "characters/arden-march/portrait.gif",
    mediaType: "image/gif",
    contentType: /^image\/gif\b/,
    altText: "Arden portrait GIF",
    caption: "GIF replacement preserved.",
    removedRefs: ["characters/arden-march/portrait.jpg"],
  });

  await uploadPortrait({
    expectedRevision: 4,
    filename: "arden.webp",
    bytes: webpBytes,
    assetRef: "characters/arden-march/portrait.webp",
    mediaType: "image/webp",
    contentType: /^image\/webp\b/,
    altText: "Arden portrait WEBP",
    caption: "WEBP replacement preserved.",
    removedRefs: ["characters/arden-march/portrait.gif"],
  });

  const portraitDelete = await requestJson(portraitPath, {
    method: "DELETE",
    headers: authHeaders,
    body: { expected_revision: 5 },
  });
  assert.equal(portraitDelete.status, 200);
  assert.equal(portraitDelete.payload.character.portrait, null);
  assert.equal(portraitDelete.payload.character.deleted_portrait.asset_ref, "characters/arden-march/portrait.webp");
  assert.equal(portraitDelete.payload.character.deleted_portrait.media_type, "image/webp");
  assert.equal(existsSync(path.join(portraitDir, "portrait.webp")), false);
  const definitionAfterDelete = readFileSync(definitionPath, "utf8");
  assert.equal(definitionAfterDelete.includes("portrait_asset_ref"), false);
  assert.equal(definitionAfterDelete.includes("portrait_alt"), false);
  assert.equal(definitionAfterDelete.includes("portrait_caption"), false);
  assertImportMetadataPreserved();
  const stateAfterDelete = readCharacterStateRow();
  assert.equal(stateAfterDelete.revision, 6);
  assert.equal(stateAfterDelete.updated_by_user_id, 81);

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
