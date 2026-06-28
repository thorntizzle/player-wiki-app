import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
const tempDir = mkdtempSync(path.join(tmpdir(), "cpw-browser-json-compat-"));
process.env.CPW_CAMPAIGNS_DIR = path.join(repoRoot, "tests", "fixtures", "sample_campaigns");
process.env.CPW_DB_PATH = path.join(tempDir, "player_wiki.sqlite3");

const { getApp } = await import("../dist/server.js");
const app = getApp();

async function requestJson(pathname, headers = {}) {
  const response = await app.request(pathname, {
    headers: {
      Accept: "application/json",
      ...headers,
    },
  });
  const contentType = response.headers.get("content-type") || "";
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  return { status: response.status, contentType, payload };
}

function assertJson(response) {
  assert.match(response.contentType, /^application\/json\b/);
}

function assertPreviewIncludes(response, expected) {
  assert.equal(response.status, 200);
  assertJson(response);
  assert.equal(typeof response.payload.preview_html, "string");
  for (const fragment of expected) {
    assert.ok(
      response.payload.preview_html.includes(fragment),
      `Expected preview_html to include ${JSON.stringify(fragment)} in ${response.payload.preview_html}`,
    );
  }
}

const emptyGlobalSearch = await requestJson("/campaigns/linden-pass/global-search?q=c");
assert.equal(emptyGlobalSearch.status, 200);
assertJson(emptyGlobalSearch);
assert.deepEqual(emptyGlobalSearch.payload.results, []);
assert.equal(emptyGlobalSearch.payload.message, "Type at least 2 letters to search wiki pages and Systems entries.");

const globalSearch = await requestJson("/campaigns/linden-pass/global-search?q=lyra");
assert.equal(globalSearch.status, 200);
assertJson(globalSearch);
assert.equal(globalSearch.payload.message, "Found 1 matching reference.");
assert.deepEqual(Object.keys(globalSearch.payload.results[0]).sort(), [
  "kind",
  "kind_label",
  "result_id",
  "select_label",
  "subtitle",
  "title",
]);
assert.deepEqual(globalSearch.payload.results[0], {
  result_id: "wiki:npcs/captain-lyra-vale",
  kind: "wiki",
  kind_label: "Wiki",
  title: "Captain Lyra Vale",
  subtitle: "NPCs",
  select_label: "Captain Lyra Vale - Wiki - NPCs",
});

assertPreviewIncludes(
  await requestJson("/campaigns/linden-pass/global-search/preview?result_id=wiki:npcs/captain-lyra-vale"),
  [
    "Captain Lyra Vale",
    "Open dedicated page",
    "/campaigns/linden-pass/pages/npcs/captain-lyra-vale",
    "Captain Lyra Vale coordinates inspections",
  ],
);

const blankGlobalPreview = await requestJson("/campaigns/linden-pass/global-search/preview");
assert.equal(blankGlobalPreview.status, 200);
assertJson(blankGlobalPreview);
assert.deepEqual(blankGlobalPreview.payload, { preview_html: "" });

const missingGlobalPreview = await requestJson(
  "/campaigns/linden-pass/global-search/preview?result_id=wiki:npcs/hidden-quartermaster",
);
assert.equal(missingGlobalPreview.status, 404);
assertJson(missingGlobalPreview);
assert.ok(missingGlobalPreview.payload.preview_html.includes("That reference is not currently visible."));

const missingGlobalCampaign = await requestJson("/campaigns/definitely-not-a-campaign/global-search?q=capt");
assert.equal(missingGlobalCampaign.status, 404);
assertJson(missingGlobalCampaign);
assert.equal(missingGlobalCampaign.payload.error.code, "campaign_not_found");

const missingGlobalPreviewCampaign = await requestJson(
  "/campaigns/definitely-not-a-campaign/global-search/preview?result_id=wiki:npcs/captain-lyra-vale",
);
assert.equal(missingGlobalPreviewCampaign.status, 404);
assertJson(missingGlobalPreviewCampaign);
assert.equal(missingGlobalPreviewCampaign.payload.error.code, "campaign_not_found");

const unauthenticatedSessionSearch = await requestJson("/campaigns/linden-pass/session/wiki-lookup/search?q=capt");
assert.equal(unauthenticatedSessionSearch.status, 401);
assertJson(unauthenticatedSessionSearch);
assert.equal(unauthenticatedSessionSearch.payload.error.code, "auth_required");

const playerHeaders = { "X-CPW-Fixture-Role": "player" };
const emptySessionSearch = await requestJson("/campaigns/linden-pass/session/wiki-lookup/search?q=c", playerHeaders);
assert.equal(emptySessionSearch.status, 200);
assertJson(emptySessionSearch);
assert.deepEqual(emptySessionSearch.payload.results, []);
assert.equal(emptySessionSearch.payload.message, "Type at least 2 letters to search player-visible wiki articles.");

const sessionSearch = await requestJson("/campaigns/linden-pass/session/wiki-lookup/search?q=lyra", playerHeaders);
assert.equal(sessionSearch.status, 200);
assertJson(sessionSearch);
assert.equal(sessionSearch.payload.message, "Found 1 matching article.");
assert.deepEqual(Object.keys(sessionSearch.payload.results[0]).sort(), [
  "page_ref",
  "select_label",
  "subtitle",
  "title",
]);
assert.deepEqual(sessionSearch.payload.results[0], {
  page_ref: "npcs/captain-lyra-vale",
  title: "Captain Lyra Vale",
  subtitle: "NPCs",
  select_label: "Captain Lyra Vale - NPCs",
});

assertPreviewIncludes(
  await requestJson(
    "/campaigns/linden-pass/session/wiki-lookup/preview?page_ref=notes/operations-brief",
    playerHeaders,
  ),
  [
    "Operations Brief",
    "All crew members are expected to keep a low profile",
    'target="_blank"',
    "/campaigns/linden-pass/pages/notes/operations-brief",
  ],
);

const blankSessionPreview = await requestJson("/campaigns/linden-pass/session/wiki-lookup/preview", playerHeaders);
assert.equal(blankSessionPreview.status, 200);
assertJson(blankSessionPreview);
assert.deepEqual(blankSessionPreview.payload, { preview_html: "" });

const hiddenSessionPreview = await requestJson(
  "/campaigns/linden-pass/session/wiki-lookup/preview?page_ref=npcs/hidden-quartermaster",
  playerHeaders,
);
assert.equal(hiddenSessionPreview.status, 404);
assertJson(hiddenSessionPreview);
assert.ok(hiddenSessionPreview.payload.preview_html.includes("That article is not currently visible to players."));

const missingSessionCampaign = await requestJson(
  "/campaigns/definitely-not-a-campaign/session/wiki-lookup/search?q=capt",
  playerHeaders,
);
assert.equal(missingSessionCampaign.status, 404);
assertJson(missingSessionCampaign);
assert.equal(missingSessionCampaign.payload.error.code, "campaign_not_found");

const missingSessionPreviewCampaign = await requestJson(
  "/campaigns/definitely-not-a-campaign/session/wiki-lookup/preview?page_ref=notes/operations-brief",
  playerHeaders,
);
assert.equal(missingSessionPreviewCampaign.status, 404);
assertJson(missingSessionPreviewCampaign);
assert.equal(missingSessionPreviewCampaign.payload.error.code, "campaign_not_found");
